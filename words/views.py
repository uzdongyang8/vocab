import json
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.utils.http import url_has_allowed_host_and_scheme
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import bot, services
from .forms import WordForm
from .models import Profile, Word


def register(request):
    form = UserCreationForm(request.POST or None)
    if form.is_valid():
        login(request, form.save())
        return redirect("dashboard")
    return render(request, "registration/register.html", {"form": form})


@login_required
def dashboard(request):
    qs = Word.objects.filter(user=request.user, archived=False)
    return render(request, "dashboard.html", {
        "archived": Word.objects.filter(user=request.user, archived=True).count(),
        "total": qs.count(),
        "due": qs.filter(next_review__lte=timezone.localdate()).count(),
        "mastered": qs.filter(stage__gte=5).count(),
        "profile": Profile.objects.get_or_create(user=request.user)[0],
    })


@login_required
def add_word(request):
    form = WordForm(request.POST or None, user=request.user)
    if form.is_valid():
        word = form.save(commit=False)
        word.user = request.user
        if Word.objects.filter(user=request.user, term__iexact=word.term).exists():
            form.add_error("term", "You already have this word.")
        else:
            word.save()
            form.save_links(word)
            messages.success(request, f"Added “{word.term}”.")
            return redirect("add_word")
    return render(request, "add_word.html", {"form": form})


@login_required
def edit_word(request, pk):
    word = get_object_or_404(Word, pk=pk, user=request.user)
    form = WordForm(request.POST or None, instance=word, user=request.user)
    if form.is_valid():
        if Word.objects.filter(user=request.user, term__iexact=form.cleaned_data["term"]).exclude(pk=pk).exists():
            form.add_error("term", "You already have this word.")
        else:
            form.save()  # learning progress (stage, next review) is kept
            form.save_links(word)
            messages.success(request, f"Saved “{word.term}”.")
            return redirect("word_list")
    return render(request, "add_word.html", {"form": form, "editing": True})


def _back(request):
    nxt = request.POST.get("next", "")
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        return redirect(nxt)
    return redirect("word_list")


@login_required
@require_POST
def quick_add(request):
    """Pop-up on the add/edit form: create a word with just a name and translation."""
    term, translation = request.POST.get("term", "").strip(), request.POST.get("translation", "").strip()
    if not term or not translation:
        return JsonResponse({"ok": False, "error": "Enter the word and its translation."}, status=400)
    if len(term) > 200 or len(translation) > 200:
        return JsonResponse({"ok": False, "error": "Too long (200 characters max)."}, status=400)
    existing = services.find_word(request.user, term)
    if existing:  # already there: just use it
        return JsonResponse({"ok": True, "term": existing.term, "existed": True})
    word = Word.objects.create(user=request.user, term=term, translation=translation)
    return JsonResponse({"ok": True, "term": word.term, "existed": False})


@login_required
def word_list(request):
    q = request.GET.get("q", "").strip()
    show = "archived" if request.GET.get("show") == "archived" else "active"
    mine = Word.objects.filter(user=request.user).prefetch_related("opposites", "similar")
    active = mine.filter(archived=False)
    if q:  # search looks through active and archived words
        words = services.search_words(request.user, q)
    else:
        words = list(mine.filter(archived=True) if show == "archived" else active)
    return render(request, "word_list.html", {
        "words": words, "q": q, "show": show, "total": mine.count(), "active": active.count(),
        "due": active.filter(next_review__lte=timezone.localdate()).count(),
        "archived": mine.filter(archived=True).count()})


@login_required
@require_POST
def delete_word(request, pk):
    get_object_or_404(Word, pk=pk, user=request.user).delete()
    return _back(request)


@login_required
@require_POST
def set_archived(request, pk, value):
    word = get_object_or_404(Word, pk=pk, user=request.user)
    word.archived = value
    word.save(update_fields=["archived"])
    messages.success(request, f"{'Archived' if value else 'Restored'} “{word.term}”.")
    return _back(request)


@login_required
def quiz_start(request):
    if request.method == "POST":
        size = 30 if request.POST.get("size") == "30" else 20
        ids = services.build_quiz(request.user, size)
        if not ids:
            messages.error(request, "Add some words first.")
            return redirect("add_word")
        request.session["quiz"] = {"ids": ids, "i": 0, "score": 0, "q": None, "fb": None}
        return redirect("quiz")
    return render(request, "quiz_start.html", {"count": Word.objects.filter(user=request.user, archived=False).count()})


@login_required
def quiz(request):
    st = request.session.get("quiz")
    if not st:
        return redirect("quiz_start")
    if st["i"] >= len(st["ids"]):
        request.session.pop("quiz")
        return render(request, "quiz_result.html", {"score": st["score"], "total": len(st["ids"]), "fb": st["fb"]})
    word = get_object_or_404(Word, pk=st["ids"][st["i"]], user=request.user)
    if st["q"] is None:
        st["q"] = services.make_question(word, request.user)
    q = st["q"]
    if request.method == "POST":
        given = request.POST.get("answer", "")
        result = services.check_answer(word, q["kind"], given)
        if result == "synonym" and not q.get("retried"):
            q["retried"] = True
            st["q"], st["fb"] = q, {"hint": f"“{given.strip()}” is a similar word, but not the one I'm looking for. Try again!"}
            request.session["quiz"] = st
            return redirect("quiz")
        ok = result == "correct"
        word.review(ok)
        st.update(score=st["score"] + ok, i=st["i"] + 1, q=None,
                  fb={"ok": ok, "answer": services.answer_of(word, q["kind"]),
                      "pron": word.pronunciation if q["kind"] != "choice" else ""})
        request.session["quiz"] = st
        return redirect("quiz")
    fb, st["fb"] = st["fb"], None
    request.session["quiz"] = st
    return render(request, "quiz.html", {
        "q": q, "prompt": services.prompt_of(word, q["kind"]), "word": word,
        "n": st["i"] + 1, "total": len(st["ids"]), "fb": fb,
    })


@csrf_exempt
@require_POST
def telegram_webhook(request):
    secret = settings.TELEGRAM_WEBHOOK_SECRET
    if not secret or request.headers.get("X-Telegram-Bot-Api-Secret-Token") != secret:
        return HttpResponseForbidden()
    try:
        bot.handle_update(json.loads(request.body))
    except Exception:  # always answer 200 so Telegram does not resend the same update
        logging.getLogger(__name__).exception("telegram update failed")
    return HttpResponse("ok")
