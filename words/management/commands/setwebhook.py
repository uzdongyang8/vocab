from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from words.telegram import call


class Command(BaseCommand):
    help = "Register the webhook: python manage.py setwebhook https://USER.pythonanywhere.com/telegram/webhook/"

    def add_arguments(self, parser):
        parser.add_argument("url")

    def handle(self, *args, url, **opts):
        if not settings.TELEGRAM_WEBHOOK_SECRET:
            raise CommandError("Set TELEGRAM_WEBHOOK_SECRET first.")
        call("setWebhook", url=url, secret_token=settings.TELEGRAM_WEBHOOK_SECRET,
             allowed_updates=["message", "callback_query"])
        self.stdout.write(f"Webhook set to {url}")
