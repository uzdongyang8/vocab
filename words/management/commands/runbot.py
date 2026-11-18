import time

from django.core.management.base import BaseCommand

from words.bot import handle_update
from words.telegram import call


class Command(BaseCommand):
    help = "Run the bot with long polling (for your own PC/VPS). On hosting without always-on tasks use the webhook."

    def handle(self, *args, **opts):
        offset = None
        self.stdout.write("Bot started. Press Ctrl+C to stop.")
        while True:
            try:
                for u in call("getUpdates", offset=offset, timeout=30) or []:
                    offset = u["update_id"] + 1
                    handle_update(u)
            except Exception as e:
                self.stderr.write(f"error: {e}")
                time.sleep(3)
