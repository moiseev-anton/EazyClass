import uuid

from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ObjectDoesNotExist

from schedule_ingestion.delivery_recovery import resolve_delivery


class Command(BaseCommand):
    help = 'Record an operator decision about an ambiguous delivery; does not enqueue or send.'

    def add_arguments(self, parser):
        parser.add_argument('publication_id', type=uuid.UUID)
        parser.add_argument('--phase', choices=['notifications', 'report'], required=True)
        parser.add_argument('--decision', choices=['retry', 'skip'], required=True)
        parser.add_argument('--request-id', type=uuid.UUID, required=True)
        parser.add_argument('--expected-token', type=uuid.UUID, required=True)
        parser.add_argument('--actor', required=True)
        parser.add_argument('--reason', required=True)
        parser.add_argument('--worker-stopped', action='store_true',
                            help='Confirm the old sender has stopped; required for status sending.')

    def handle(self, *args, **options):
        try:
            result = resolve_delivery(**{key: options[key] for key in (
                'publication_id', 'phase', 'decision', 'request_id', 'expected_token',
                'actor', 'reason', 'worker_stopped')})
        except ValueError as error:
            raise CommandError(str(error)) from error
        except ObjectDoesNotExist as error:
            raise CommandError('Publication or delivery does not exist') from error
        self.stdout.write(str(result.pk))
