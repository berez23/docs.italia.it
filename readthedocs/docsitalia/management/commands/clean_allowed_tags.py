"""Command to remove unallowed tags from existing documents."""
from django.core.management.base import BaseCommand

from readthedocs.docsitalia.models import AllowedTag


class Command(BaseCommand):
    help = "Remove unallowed tags from the existing documents."

    def handle(self, *args, **options):
        AllowedTag.remove_unallowed()
