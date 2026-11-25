import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

INTERVALS = [1, 3, 7, 14, 30]  # days; stage 5 = mastered (keeps repeating every 30 days)


def new_code():
    return secrets.token_hex(3).upper()


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    telegram_id = models.BigIntegerField(null=True, blank=True, unique=True)
    link_code = models.CharField(max_length=12, default=new_code, unique=True)

    def __str__(self):
        return self.user.username


class Word(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    term = models.CharField(max_length=200)          # word in the language you learn
    pronunciation = models.CharField(max_length=200, blank=True)
    translation = models.CharField(max_length=200)
    meaning = models.TextField(blank=True)
    example = models.TextField(blank=True)
    stage = models.PositiveSmallIntegerField(default=0)
    next_review = models.DateField(default=timezone.localdate)
    fails = models.PositiveIntegerField(default=0)
    opposites = models.ManyToManyField("self", blank=True)  # symmetric: if A is opposite of B, B is opposite of A
    similar = models.ManyToManyField("self", blank=True)    # symmetric: words with a similar meaning
    archived = models.BooleanField(default=False)  # archived words are left out of quizzes and reminders
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "term")
        ordering = ["-created"]

    def review(self, correct):
        today = timezone.localdate()
        if correct:
            self.next_review = today + timedelta(days=INTERVALS[min(self.stage, 4)])
            self.stage = min(self.stage + 1, 5)
        else:  # failed words restart the 1+3+7+14+30 path and are due again right away
            self.stage, self.next_review = 0, today
            self.fails += 1
        self.save()

    def __str__(self):
        return f"{self.term} = {self.translation}"


class BotState(models.Model):
    """Running Telegram quiz for a chat (kept in the DB so any web worker can continue it)."""
    chat_id = models.BigIntegerField(unique=True)
    data = models.JSONField(default=dict)
