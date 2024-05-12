from django.core.management.base import BaseCommand

from scheduler.tasks import parse_lessons, update_all_lessons
from scheduler.models import Group


class Command(BaseCommand):
    def handle(self, *args, **options):
        group = Group.objects.first()
        parse_lessons(group)
        # update_all_lessons()