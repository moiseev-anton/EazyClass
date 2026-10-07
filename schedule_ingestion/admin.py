from django.contrib import admin

from .models import ExportRevision, Publication, PublicationDelivery


@admin.register(ExportRevision, Publication, PublicationDelivery)
class IngestionHistoryAdmin(admin.ModelAdmin):
    """Read-only history; publication/edit actions will use dedicated services."""
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]
