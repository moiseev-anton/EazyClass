from .schedule_parser import update_schedule
from .group_parser import update_groups
from .timetable_manager import fill_lesson_times
from .db_queries import synchronize_lessons
from .update_last_active import update_last_active_records, delete_inactive_records
from .dummy import dummy_task
