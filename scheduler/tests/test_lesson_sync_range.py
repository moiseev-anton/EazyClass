from datetime import date, datetime, timezone as dt_timezone
from unittest.mock import MagicMock, patch

import orjson
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from scrapy.http import HtmlResponse, Request

from enums import KeyEnum
from scheduler.dtos.lesson_sync_range import LessonSyncRange
from scheduler.fetched_data_sync.lessons.lessons_sync_manager import LessonsSyncManager
from scheduler.models import Group, Lesson, Period
from scheduler.tasks import refresh, scraping, synchronisation
from scrapy_app.response_processor import ResponseProcessor
from scrapy_app.spiders.schedule_spyder import ScheduleSpider


class RangeTests(SimpleTestCase):
    def test_dict_round_trip_through_json(self):
        for end in [None, date(2026, 9, 15), date(2026, 9, 21)]:
            with self.subTest(end=end):
                original = LessonSyncRange(date(2026, 9, 15), end)
                payload = orjson.loads(orjson.dumps(original.to_dict()))
                self.assertEqual(payload, {
                    "start": "2026-09-15", "end": end.isoformat() if end else None,
                })
                restored = LessonSyncRange.from_dict(payload)
                self.assertEqual(restored, original)
                self.assertEqual(restored.cache_scope, original.cache_scope)

    def test_constructor_validates_boundaries(self):
        for start, end in [(None, None), ("2026-09-15", None),
                           (datetime(2026, 9, 15), None),
                           (date(2026, 9, 15), "2026-09-16"),
                           (date(2026, 9, 15), date(2026, 9, 14))]:
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                LessonSyncRange(start, end)

    def test_scraping_task_passes_cache_scope_to_spider(self):
        with patch.object(scraping, "SpiderRunner") as runner, patch(
            "scheduler.dtos.lesson_sync_range.timezone.localdate", return_value=date(2026, 9, 16)
        ):
            scraping.run_schedule_spider.run(cache_scope="2026-09-15:unbounded:")
            runner.assert_called_once_with(ScheduleSpider, cache_scope="2026-09-15:unbounded:")
            runner.return_value.run.assert_called_once()

    def test_offsets(self):
        with patch("scheduler.dtos.lesson_sync_range.timezone.localdate", return_value=date(2026, 9, 15)):
            for kwargs, start, end in [
                ({}, 15, None),
                ({"start_day_offset": 1}, 16, None),
                ({"end_day_offset": 0}, 15, 15),
                ({"end_day_offset": 6}, 15, 21),
                ({"start_day_offset": 1, "end_day_offset": 3}, 16, 18),
                ({"start_day_offset": -1, "end_day_offset": 0}, 14, 15),
            ]:
                with self.subTest(kwargs=kwargs):
                    result = LessonSyncRange.from_offsets(**kwargs)
                    self.assertEqual(result.start, date(2026, 9, start))
                    self.assertEqual(result.end, date(2026, 9, end) if end else None)

    def test_invalid_configuration(self):
        for kwargs in [
            {"start_day_offset": 2, "end_day_offset": 1},
            {"start_day_offset": True}, {"start_day_offset": None},
            {"end_day_offset": "3"}, {"end_day_offset": 1.5},
            {"end_day_offset": 10**20},
        ]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                LessonSyncRange.from_offsets(**kwargs)

    def test_project_timezone(self):
        with timezone.override("Europe/Moscow"), patch(
            "django.utils.timezone.now", return_value=datetime(2026, 9, 14, 22, tzinfo=dt_timezone.utc)
        ):
            self.assertEqual(LessonSyncRange.from_offsets().start, date(2026, 9, 15))

    def test_pipeline_freezes_dates_and_preserves_previous_result(self):
        for task in [refresh.run_lessons_refresh_pipeline, refresh.run_lessons_refresh_by_google_docs]:
            with self.subTest(task=task.name), patch.object(refresh, "chain") as chain, patch(
                "scheduler.dtos.lesson_sync_range.timezone.localdate", return_value=date(2026, 9, 15)
            ):
                task.run(start_day_offset=1, end_day_offset=3)
                signatures = chain.call_args.args
                sync = signatures[1]
                self.assertEqual(sync.kwargs, {"_resolved_range": {"start": "2026-09-16", "end": "2026-09-18"}})
                self.assertEqual(sync.clone(args=({"previous": "result"},)).args, ({"previous": "result"},))
                if task is refresh.run_lessons_refresh_pipeline:
                    self.assertEqual(signatures[0].kwargs, {"cache_scope": "2026-09-16:2026-09-18:"})
                chain.return_value.apply_async.assert_called_once()

    def test_invalid_range_does_not_start_pipeline_or_retry_sync(self):
        with patch.object(refresh, "chain") as chain:
            for task in [refresh.run_lessons_refresh_pipeline, refresh.run_lessons_refresh_by_google_docs]:
                with self.assertRaises(ValueError):
                    task.run(start_day_offset=2, end_day_offset=1)
            chain.assert_not_called()
        with patch.object(synchronisation.RedisClientManager, "get_client") as client, patch.object(
            synchronisation.sync_lessons, "retry"
        ) as retry:
            with self.assertRaises(ValueError):
                synchronisation.sync_lessons.run(end_day_offset=-1)
            client.assert_not_called()
            retry.assert_not_called()

    def test_sync_passes_range_to_manager(self):
        with patch.object(synchronisation.RedisClientManager, "get_client") as client, patch.object(
            synchronisation, "LessonsSyncManager"
        ) as manager:
            client.return_value.get.return_value = b"{}"
            manager.return_value.update_schedule.return_value = {"added": [], "updated": [], "removed": []}
            with patch("scheduler.dtos.lesson_sync_range.timezone.localdate", return_value=date(2026, 9, 15)):
                synchronisation.sync_lessons.run({"previous": "result"}, end_day_offset=2)
            manager.assert_called_once_with(redis_client=client.return_value, start_sync_day=date(2026, 9, 15), end_sync_day=date(2026, 9, 17))

    def test_retry_keeps_resolved_dates(self):
        failure = RuntimeError("Redis unavailable")
        with patch.object(synchronisation.RedisClientManager, "get_client", side_effect=failure), patch.object(
            synchronisation.sync_lessons, "retry", side_effect=failure
        ) as retry, patch("scheduler.dtos.lesson_sync_range.timezone.localdate", return_value=date(2026, 9, 15)):
            with self.assertRaises(RuntimeError):
                synchronisation.sync_lessons.run(start_day_offset=1, end_day_offset=3)
            retry.assert_called_once_with(exc=failure, args=(), kwargs={
                "_": None, "_resolved_range": {"start": "2026-09-16", "end": "2026-09-18"}
            })

    def test_absolute_dates_are_not_configuration_arguments(self):
        for task in [refresh.run_lessons_refresh_pipeline, refresh.run_lessons_refresh_by_google_docs,
                     synchronisation.sync_lessons]:
            with self.subTest(task=task.name), self.assertRaises(TypeError):
                task.run(start_date="2026-09-15", end_date="2026-09-17")

    def test_resolved_range_survives_midnight(self):
        with patch.object(synchronisation.RedisClientManager, "get_client") as client, patch.object(
            synchronisation, "LessonsSyncManager"
        ) as manager, patch("scheduler.dtos.lesson_sync_range.timezone.localdate", return_value=date(2026, 9, 16)):
            client.return_value.get.return_value = b"{}"
            manager.return_value.update_schedule.return_value = {"added": [], "updated": [], "removed": []}
            synchronisation.sync_lessons.run(_resolved_range={"start": "2026-09-15", "end": "2026-09-17"})
            manager.assert_called_once_with(redis_client=client.return_value,
                                            start_sync_day=date(2026, 9, 15), end_sync_day=date(2026, 9, 17))

    def test_invalid_internal_range_is_rejected_before_io(self):
        with patch.object(synchronisation.RedisClientManager, "get_client") as client:
            for payload in [{}, {"start": "2026-09-15"}, {"start": None, "end": None},
                            {"start": "invalid", "end": None},
                            {"start": "2026-09-17", "end": "2026-09-15"}]:
                with self.subTest(payload=payload), self.assertRaises(ValueError):
                    synchronisation.sync_lessons.run(_resolved_range=payload)
            with self.assertRaises(ValueError):
                synchronisation.sync_lessons.run(start_day_offset=1,
                    _resolved_range={"start": "2026-09-15", "end": None})
            for offsets in [{"end_day_offset": 0}, {"start_day_offset": False}]:
                with self.subTest(offsets=offsets), self.assertRaises(ValueError):
                    synchronisation.sync_lessons.run(**offsets,
                        _resolved_range={"start": "2026-09-15", "end": None})
            client.assert_not_called()

    def test_cache_reads_and_writes_are_scoped_by_range(self):
        redis = MagicMock()
        redis.get.return_value = "main-hash"
        redis.smembers.return_value = set()
        with patch("scrapy_app.spiders.schedule_spyder.RedisClientManager.get_client", return_value=redis):
            for end in [date(2026, 9, 15), date(2026, 9, 21), None]:
                manager = LessonsSyncManager(redis, date(2026, 9, 15), end)
                scope = manager.date_range.cache_scope
                manager._save_to_redis({"1": "page-hash"}, set())
                redis.pipeline.return_value.__enter__.return_value.setex.assert_called_with(
                    f"{KeyEnum.PAGE_HASH_PREFIX}{scope}1", manager.PAGE_HASH_TIMEOUT, "page-hash"
                )
                manager_key = redis.sadd.call_args.args[0]
                spider = ScheduleSpider(cache_scope=scope)
                spider.main_page_hash = "main-hash"
                self.assertEqual(spider._separate_groups([("1", "group")]), [("1", "group")])
                redis.smembers.assert_called_with(manager_key)
                response = HtmlResponse(url="https://example.invalid/", body=b"<html/>", request=Request(
                    "https://example.invalid/", meta={"group_id": "1"}
                ))
                ResponseProcessor(response, redis, cache_scope=scope)
                redis.get.assert_called_with(f"{KeyEnum.PAGE_HASH_PREFIX}{scope}1")
        self.assertNotEqual(LessonSyncRange(date(2026, 9, 15)).cache_scope, LessonSyncRange(date(2026, 9, 16)).cache_scope)


class RangeDatabaseTests(TestCase):
    def setUp(self):
        self.group = Group.objects.create(title="Range test")
        self.redis = MagicMock()
        self.groups = {str(self.group.pk): "hash"}

    def sync(self, start, end, days, title="Math"):
        items = [{"group_id": self.group.pk, "period": {"date": f"2026-09-{day:02d}", "lesson_number": 1},
                  "subject": {"title": title}, "classroom": {"title": "101"}, "teacher": {"full_name": None}}
                 for day in days]
        payload = {KeyEnum.SCRAPED_LESSONS: orjson.dumps(items), KeyEnum.SCRAPED_GROUPS: orjson.dumps(self.groups),
                   KeyEnum.UNCHANGED_GROUPS: b"[]"}
        self.redis.get.side_effect = payload.get
        return LessonsSyncManager(self.redis, date(2026, 9, start), date(2026, 9, end) if end else None).update_schedule()

    def test_create_update_delete_only_inside_inclusive_range(self):
        self.sync(14, None, [14, 15, 16, 17, 18])
        summary = self.sync(15, 17, [14, 15, 17, 18, 19], "Physics")
        self.assertEqual(len(summary["updated"]), 2)
        self.assertEqual(len(summary["removed"]), 1)
        self.assertEqual(summary["added"], [])
        self.assertEqual(dict(Lesson.objects.values_list("period__date", "subject__title")), {
            date(2026, 9, 14): "Math", date(2026, 9, 15): "Physics",
            date(2026, 9, 17): "Physics", date(2026, 9, 18): "Math",
        })
        self.assertFalse(Period.objects.filter(date=date(2026, 9, 19)).exists())
        self.sync(15, 17, [15, 16, 17])
        self.assertTrue(Lesson.objects.filter(period__date=date(2026, 9, 16)).exists())

    def test_empty_source_deletes_only_selected_day(self):
        self.sync(14, None, [14, 15, 16])
        self.sync(15, 15, [])
        self.assertEqual(set(Lesson.objects.values_list("period__date", flat=True)), {date(2026, 9, 14), date(2026, 9, 16)})
