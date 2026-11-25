from django.utils import timezone

from words import services
from words import telegram as tg
from words.models import BotState, Profile, Word

HELP = (
    "Commands:\n"
    "/link CODE – connect this chat to your website account (code is on the dashboard)\n"
    "/add word | translation | meaning | example | pronunciation – add a word (everything after the translation is optional)\n"
    "/edit word | translation | meaning | example | pronunciation – change a word (empty = keep, - = clear)\n"
    "/words – show your latest words\n"
    "/archive word – hide a word from quizzes; /unarchive word – bring it back\n"
    "/opposite word | other – link opposites; /similar word | other | more – link similar words; /unlink word | other\n"
    "/show word – full details of a word, with its linked words\n"
    "/search text – find words (in word, translation, meaning or example)\n"
    "/quiz 20 or /quiz 30 – start a quiz"
)


def label(w):
    pron = f" [{w.pronunciation}]" if w.pronunciation else ""
    return ("🗄 " if w.archived else "") + f"{w.term}{pron} – {w.translation}"


def save(chat, st):
    BotState.objects.update_or_create(chat_id=chat, defaults={"data": st})


def ask(chat, user, st):
    while st["i"] < len(st["ids"]):
        word = Word.objects.filter(pk=st["ids"][st["i"]], user=user, archived=False).first()
        if word:
            break
        st["i"] += 1  # word was deleted meanwhile
    else:
        BotState.objects.filter(chat_id=chat).delete()
        return tg.send(chat, f"Finished! Score: {st['score']}/{len(st['ids'])} 🎉")
    st["q"], st["word"] = services.make_question(word, user), word.pk
    save(chat, st)
    text = f"{st['i'] + 1}/{len(st['ids'])}\n\n{services.prompt_of(word, st['q']['kind'])}"
    if st["q"]["kind"] == "choice":
        kb = {"inline_keyboard": [[{"text": o, "callback_data": f"a:{st['i']}:{k}"}]
                                  for k, o in enumerate(st["q"]["options"])]}
        pron = f" [{word.pronunciation}]" if word.pronunciation else ""
        tg.send(chat, text + pron + "\n\nPick the translation:", kb)
    elif st["q"]["kind"] == "meaning":
        tg.send(chat, text + "\n\n✍️ Which word has this meaning? Type it:")
    else:
        tg.send(chat, text + "\n\n✍️ Type the word in the language you learn:")


def answer(chat, user, st, given):
    word, kind = Word.objects.get(pk=st["word"], user=user), st["q"]["kind"]
    result = services.check_answer(word, kind, given)
    if result == "synonym" and not st["q"].get("retried"):
        st["q"]["retried"] = True
        save(chat, st)
        return tg.send(chat, f"🟡 “{given.strip()}” is a similar word, but not the one I'm looking for. Try again!")
    ok = result == "correct"
    word.review(ok)
    st["score"] += ok
    st["i"] += 1
    pron = f" [{word.pronunciation}]" if word.pronunciation and kind != "choice" else ""
    tg.send(chat, "✅ Correct!" if ok else f"❌ Right answer: {services.answer_of(word, kind)}{pron}")
    ask(chat, user, st)


def handle_message(chat, text):
    profile = Profile.objects.filter(telegram_id=chat).select_related("user").first()
    cmd, _, arg = text.partition(" ")
    cmd = cmd.split("@")[0].lower()
    if cmd == "/link":
        target = Profile.objects.filter(link_code=arg.strip().upper()).first()
        if not target:
            return tg.send(chat, "Code not found. Copy it from your dashboard.")
        Profile.objects.filter(telegram_id=chat).update(telegram_id=None)
        target.telegram_id = chat
        target.save()
        return tg.send(chat, f"Linked to {target.user.username} ✅\n\n{HELP}")
    if not profile:
        return tg.send(chat, "Welcome! Log in on the website, then send /link CODE here.")
    user = profile.user
    if cmd in ("/start", "/help"):
        return tg.send(chat, HELP)
    if cmd == "/add":
        parts = [p.strip() for p in arg.split("|")] + [""] * 4
        if not parts[0] or not parts[1]:
            return tg.send(chat, "Format: /add word | translation | meaning | example | pronunciation")
        _, created = Word.objects.get_or_create(user=user, term=parts[0], defaults={
            "translation": parts[1], "meaning": parts[2], "example": parts[3], "pronunciation": parts[4]})
        return tg.send(chat, f"Added “{parts[0]}” ✅" if created else "You already have this word.")
    if cmd == "/edit":
        parts = [p.strip() for p in arg.split("|")] + [""] * 5
        word = services.find_word(user, parts[0])
        if not word:
            return tg.send(chat, "Format: /edit word | translation | meaning | example | pronunciation\n"
                                 "Word must already exist. Empty part = keep, - = clear (not the translation).")
        for field, val in zip(("translation", "meaning", "example", "pronunciation"), parts[1:5]):
            if not val:
                continue
            if val == "-":
                if field == "translation":
                    continue
                val = ""
            setattr(word, field, val)
        word.save()
        return tg.send(chat, f"Updated “{word.term}” ✅")
    if cmd in ("/opposite", "/similar", "/unlink"):
        names = [p.strip() for p in arg.split("|") if p.strip()]
        if len(names) < 2:
            return tg.send(chat, f"Format: {cmd} word | other word" + (" | more" if cmd != "/opposite" else ""))
        first = services.find_word(user, names[0])
        others = [(n, services.find_word(user, n)) for n in names[1:]]
        missing = [n for n, w in [(names[0], first)] + others if w is None]
        if missing:
            return tg.send(chat, "Not found (add them first): " + ", ".join(missing))
        done = []
        for n, other in others:
            if other == first:
                continue
            if cmd == "/unlink":
                first.opposites.remove(other)
                first.similar.remove(other)
            elif cmd == "/opposite":
                first.similar.remove(other)
                first.opposites.add(other)
            else:
                first.opposites.remove(other)
                first.similar.add(other)
            done.append(other.term)
        sign = {"/opposite": "↔ opposite of", "/similar": "≈ similar to", "/unlink": "unlinked from"}[cmd]
        return tg.send(chat, f"🔗 {first.term} {sign} {', '.join(done)} ✅" if done else "A word can't be linked to itself.")
    if cmd == "/show":
        w = services.find_word(user, arg)
        if not w:
            return tg.send(chat, "Format: /show word (the word must already exist)")
        rows = [label(w)]
        if w.meaning:
            rows.append(f"📖 {w.meaning}")
        if w.example:
            rows.append(f"💬 {w.example}")
        if w.opposites.exists():
            rows.append("↔ Opposite: " + ", ".join(o.term for o in w.opposites.all()))
        if w.similar.exists():
            rows.append("≈ Similar: " + ", ".join(o.term for o in w.similar.all()))
        rows.append(f"Added {timezone.localtime(w.created):%d %b %Y} · next review {w.next_review} · stage {w.stage}/5")
        return tg.send(chat, "\n".join(rows))
    if cmd in ("/archive", "/unarchive"):
        word = services.find_word(user, arg)
        if not word:
            return tg.send(chat, f"Format: {cmd} word (the word must already exist)")
        word.archived = cmd == "/archive"
        word.save(update_fields=["archived"])
        return tg.send(chat, f"{'Archived' if word.archived else 'Restored'} “{word.term}” ✅")
    if cmd == "/search":
        if not arg.strip():
            return tg.send(chat, "Format: /search text")
        found = services.search_words(user, arg)
        if not found:
            return tg.send(chat, f"No words match “{arg.strip()}”.")
        more = f"\n… and {len(found) - 20} more" if len(found) > 20 else ""
        return tg.send(chat, f"🔎 {len(found)} found\n\n" + "\n".join(label(w) for w in found[:20]) + more)
    if cmd == "/words":
        active = Word.objects.filter(user=user, archived=False)
        total, archived = active.count(), Word.objects.filter(user=user, archived=True).count()
        if not total and not archived:
            return tg.send(chat, "No words yet. Use /add.")
        due = active.filter(next_review__lte=timezone.localdate()).count()
        head = f"📚 {total} words ({due} due today" + (f", {archived} archived)" if archived else ")")
        more = f"\n… and {total - 20} more" if total > 20 else ""
        return tg.send(chat, head + "\n\n" + "\n".join(label(w) for w in active[:20]) + more)
    if cmd == "/quiz":
        ids = services.build_quiz(user, 30 if arg.strip() == "30" else 20)
        if not ids:
            return tg.send(chat, "Add some words first with /add.")
        return ask(chat, user, {"ids": ids, "i": 0, "score": 0, "q": None, "word": None})
    state = BotState.objects.filter(chat_id=chat).first()
    if state and state.data["q"]["kind"] != "choice" and not text.startswith("/"):
        return answer(chat, user, state.data, text)
    tg.send(chat, HELP)


def handle_update(u):
    cq = u.get("callback_query")
    if cq:
        tg.call("answerCallbackQuery", callback_query_id=cq["id"])
        chat = cq["message"]["chat"]["id"]
        state = BotState.objects.filter(chat_id=chat).first()
        profile = Profile.objects.filter(telegram_id=chat).select_related("user").first()
        _, i, k = cq["data"].split(":")
        if state and profile and int(i) == state.data["i"] and state.data["q"]["kind"] == "choice":
            answer(chat, profile.user, state.data, state.data["q"]["options"][int(k)])
        return
    m = u.get("message") or {}
    if m.get("text"):
        handle_message(m["chat"]["id"], m["text"].strip())
