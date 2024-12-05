from django.core.management.base import BaseCommand

from scheduler.tasks import update_groups


class Command(BaseCommand):
    def handle(self, *args, **options):
        update_groups()
