from django.dispatch import receiver

from scheduler.schedule_write_guard import schedule_applied
from .models import ScheduleWriteEvent


@receiver(schedule_applied, dispatch_uid='ingestion.schedule_write_event')
def record_schedule_write(sender, *, group_ids, date_range, observed_at, **kwargs):
    # Emitted inside the lesson transaction, so event and schedule commit together.
    ScheduleWriteEvent.objects.create(group_ids=[str(key) for key in group_ids],
        start_date=date_range.start, end_date=date_range.end, observed_at=observed_at)
