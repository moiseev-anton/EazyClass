# from unittest.mock import patch, AsyncMock
#
# import pytest
# from django.test import TestCase
# from ..tasks.schedule_parser import update_schedule_task, ScheduleSyncManager
#
#
# @pytest.mark.asyncio
# async def test_fetch_data_success():
#     # Мокаем асинхронный запрос
#     mock_response = AsyncMock()
#     mock_response.text.return_value = "<html><body><h1>Test Data</h1></body></html>"
#
#     with patch("aiohttp.ClientSession.get", return_value=mock_response):
#         parser = ScheduleSyncManager(groups=[{"id": 1, "link": "http://example.com"}])
#         result = await parser.fetch_data("http://example.com")
#
#         assert result == "<html><body><h1>Test Data</h1></body></html>"
#
# @pytest.mark.asyncio
# async def test_parse_data():
#     # Пример HTML для парсинга
#     html_data = "<html><body><h1>Group Schedule</h1></body></html>"
#     parser = ScheduleSyncManager(groups=[])
#
#     # Имитация парсинга
#     result = parser.parse(html_data)
#
#     assert result is not None
#     # Проверка, что нужные данные извлечены
#     assert "Group Schedule" in result
#
# @pytest.mark.asyncio
# async def test_update_database(mocker):
#     # Mock для данных
#     mocker.patch("scheduler.models.Lesson.objects.bulk_update_or_create")
#     parser = ScheduleSyncManager(groups=[])
#     parser.parsed_lessons = [{"id": 1, "name": "Math"}]
#
#     # Вызываем обновление БД
#     await parser.update_database()
#
#     # Проверяем, что bulk-операции вызваны
#     # scheduler.models.Lesson.objects.bulk_update_or_create.assert_called_once()
#
#
#
#
# class ScheduleParserTestCase(TestCase):
#
#     @patch('scheduler.tasks.schedule_parser.Group.objects.groups_links')
#     @patch('scheduler.tasks.schedule_parser.aiohttp.ClientSession')
#     def test_update_schedule_task(self, mock_session, mock_groups_links):
#         """Test the main update_schedule_task function."""
#         # Mock group links
#         mock_groups_links.return_value = [
#             {'id': 1, 'link': 'https://example.com/group1'},
#             {'id': 2, 'link': 'https://example.com/group2'}
#         ]
#
#         # Mock aiohttp session
#         mock_session.return_value = AsyncMock()
#         mock_session.return_value.get.return_value.__aenter__.return_value.json.side_effect = [
#             {"schedule": [{"day": "Monday"}]},
#             {"schedule": [{"day": "Tuesday"}]}
#         ]
#
#         # Run the task
#         result = update_schedule_task()
#
#         # Verify the result is None (successful execution)
#         self.assertIsNone(result)
#
#         # Check if the session was called for each group
#         mock_session.return_value.get.assert_any_call('https://example.com/group1')
#         mock_session.return_value.get.assert_any_call('https://example.com/group2')
#
#     @patch('scheduler.tasks.schedule_parser.aiohttp.ClientSession')
#     def test_schedule_parser_class(self, mock_session):
#         """Test the ScheduleParser class behavior."""
#         groups = [
#             {'id': 1, 'link': 'https://example.com/group1'},
#             {'id': 2, 'link': 'https://example.com/group2'}
#         ]
#
#         # Mock aiohttp session
#         mock_session.return_value = AsyncMock()
#         mock_session.return_value.get.return_value.__aenter__.return_value.json.side_effect = [
#             {"schedule": [{"day": "Monday"}]},
#             {"schedule": [{"day": "Tuesday"}]}
#         ]
#
#         parser = ScheduleSyncManager(groups=groups, session=mock_session.return_value)
#
#         # Run the parser
#         success_ids, fetch_failed_ids, parse_failed_ids = parser.run()
#
#         # Verify results
#         self.assertEqual(success_ids, {1, 2})
#         self.assertEqual(fetch_failed_ids, set())
#         self.assertEqual(parse_failed_ids, set())
#
#         # Check API calls
#         mock_session.return_value.get.assert_any_call('https://example.com/group1')
#         mock_session.return_value.get.assert_any_call('https://example.com/group2')
#
#     @patch('scheduler.tasks.schedule_parser.aiohttp.ClientSession')
#     def test_schedule_parser_fetch_failure(self, mock_session):
#         """Test the ScheduleParser class when a fetch fails."""
#         groups = [
#             {'id': 1, 'link': 'https://example.com/group1'},
#             {'id': 2, 'link': 'https://example.com/group2'}
#         ]
#
#         # Mock aiohttp session with one failure
#         mock_session.return_value = AsyncMock()
#         mock_session.return_value.get.side_effect = [
#             Exception("Connection error"),
#             AsyncMock(return_value={"schedule": [{"day": "Tuesday"}]})
#         ]
#
#         parser = ScheduleSyncManager(groups=groups, session=mock_session.return_value)
#
#         # Run the parser
#         success_ids, fetch_failed_ids, parse_failed_ids = parser.run()
#
#         # Verify results
#         self.assertEqual(success_ids, {2})
#         self.assertEqual(fetch_failed_ids, {1})
#         self.assertEqual(parse_failed_ids, set())
#
#     @patch('scheduler.tasks.schedule_parser.aiohttp.ClientSession')
#     def test_schedule_parser_parse_failure(self, mock_session):
#         """Test the ScheduleParser class when parsing fails."""
#         groups = [
#             {'id': 1, 'link': 'https://example.com/group1'},
#             {'id': 2, 'link': 'https://example.com/group2'}
#         ]
#
#         # Mock aiohttp session with invalid JSON
#         mock_session.return_value = AsyncMock()
#         mock_session.return_value.get.return_value.__aenter__.return_value.json.side_effect = [
#             {"invalid_key": "no schedule here"},
#             {"schedule": [{"day": "Tuesday"}]}
#         ]
#
#         parser = ScheduleSyncManager(groups=groups, session=mock_session.return_value)
#
#         # Run the parser
#         success_ids, fetch_failed_ids, parse_failed_ids = parser.run()
#
#         # Verify results
#         self.assertEqual(success_ids, {2})
#         self.assertEqual(fetch_failed_ids, set())
#         self.assertEqual(parse_failed_ids, {1})

