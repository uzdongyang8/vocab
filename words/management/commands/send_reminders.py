from django.core.management.base import BaseCommand
from django.utils import timezone

from words.models import Profile, Word
from words.telegram import send


class Command(BaseCommand):
    help = "Send a daily Telegram reminder to users who have words due. Run from cron once a day."

    def handle(self, *args, **opts):
        today = timezone.localdate()
        for p in Profile.objects.exclude(telegram_id=None):
            due = Word.objects.filter(user=p.user, archived=False, next_review__lte=today).count()
            if due:
                send(p.telegram_id, f"📚 You have {due} word(s) to review today. Send /quiz 20 to start.")
