"""
Management command to periodically clear expired cart reservations
Run with: python manage.py clear_expired_reservations
Or configure in a task scheduler like Celery Beat
"""
from django.core.management.base import BaseCommand
from JOE.websocket_utils import clear_expired_reservations


class Command(BaseCommand):
    help = 'Clear expired cart reservations and return stock'

    def handle(self, *args, **options):
        cleared_count = clear_expired_reservations()
        self.stdout.write(
            self.style.SUCCESS(f'Successfully cleared {cleared_count} expired reservations')
        )
