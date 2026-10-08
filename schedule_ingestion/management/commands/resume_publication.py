import json
import uuid

from django.core.management.base import BaseCommand, CommandError

from schedule_ingestion.models import Publication


class Command(BaseCommand):
    help = 'Inspect a saved publication, or resume its chain with --enqueue.'

    def add_arguments(self, parser):
        parser.add_argument('publication_id', type=uuid.UUID)
        parser.add_argument('--enqueue', action='store_true')

    def handle(self, *args, **options):
        try:
            publication = Publication.objects.get(pk=options['publication_id'])
        except Publication.DoesNotExist as error:
            raise CommandError('Publication does not exist') from error
        deliveries = list(publication.deliveries.order_by('phase').values('phase', 'status', 'token', 'error_type'))
        result = dict(publication_id=str(publication.pk), status=publication.status, deliveries=deliveries)
        if options['enqueue']:
            if any(row['status'] in ('sending', 'uncertain') for row in deliveries):
                raise CommandError('Resolve sending/uncertain delivery before resuming')
            from schedule_ingestion.tasks import resume_publication_chain
            result['task_id'] = resume_publication_chain(publication.pk).apply_async().id
        self.stdout.write(json.dumps(result, default=str))
