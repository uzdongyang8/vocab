import random

from django.utils import timezone

from .models import Word


def build_quiz(user, size):
    """Due words first; most-failed words before others; then upcoming words to fill the quiz."""
    today = timezone.localdate()
    words = sorted(Word.objects.filter(user=user), key=lambda w: (w.next_review > today, -w.fails, w.next_review))
    ids = [w.id for w in words[:size]]
    random.shuffle(ids)
    return ids


def make_question(word, user):
    kind = random.choice(["choice", "type"])
    others = {t for t in Word.objects.filter(user=user).exclude(pk=word.pk).values_list("translation", flat=True)}
    others.discard(word.translation)
    if kind == "choice" and len(others) < 3:
        kind = "type"
    q = {"kind": kind}
    if kind == "choice":
        q["options"] = random.sample(sorted(others), 3) + [word.translation]
        random.shuffle(q["options"])
    return q


def prompt_of(word, kind):   # choice: term -> pick translation; type: translation -> type the term
    return word.term if kind == "choice" else word.translation


def answer_of(word, kind):
    return word.translation if kind == "choice" else word.term


def is_correct(word, kind, given):
    return given.strip().casefold() == answer_of(word, kind).strip().casefold()
