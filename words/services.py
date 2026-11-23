import random

from django.utils import timezone

from .models import Word


def build_quiz(user, size):
    """Due words first; most-failed words before others; then upcoming words to fill the quiz."""
    today = timezone.localdate()
    words = sorted(Word.objects.filter(user=user, archived=False),
                   key=lambda w: (w.next_review > today, -w.fails, w.next_review))
    ids = [w.id for w in words[:size]]
    random.shuffle(ids)
    return ids


def make_question(word, user):
    """Kinds: choice (term -> pick translation), type (translation -> type term),
    meaning (meaning -> type term; only for words that have a meaning)."""
    others = set(Word.objects.filter(user=user, archived=False).exclude(pk=word.pk)
                 .values_list("translation", flat=True))
    others.discard(word.translation)
    kinds = ["type"]
    if len(others) >= 3:
        kinds.append("choice")
    if word.meaning.strip():
        kinds.append("meaning")
    q = {"kind": random.choice(kinds)}
    if q["kind"] == "choice":
        q["options"] = random.sample(sorted(others), 3) + [word.translation]
        random.shuffle(q["options"])
    return q


def prompt_of(word, kind):
    return {"choice": word.term, "type": word.translation, "meaning": word.meaning}[kind]


def answer_of(word, kind):
    return word.translation if kind == "choice" else word.term


def is_correct(word, kind, given):
    return given.strip().casefold() == answer_of(word, kind).strip().casefold()


def search_words(user, query):
    """Searches ALL words (active and archived). Case-insensitive search in word, pronunciation, translation,
    meaning and example. Done in Python because SQLite's own case-insensitive match only works for ASCII."""
    words = list(Word.objects.filter(user=user))
    q = query.strip().casefold()
    if not q:
        return words
    return [w for w in words
            if q in " ".join((w.term, w.pronunciation, w.translation, w.meaning, w.example)).casefold()]
