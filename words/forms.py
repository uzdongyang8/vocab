from django import forms

from .models import Word


class WordForm(forms.ModelForm):
    opposite_terms = forms.CharField(
        required=False, label="Opposite words",
        help_text="Words you already added, separated by commas (e.g. cold, freezing).")
    similar_terms = forms.CharField(
        required=False, label="Similar words",
        help_text="Words with a similar meaning that you already added, separated by commas.")

    class Meta:
        model = Word
        fields = ["term", "pronunciation", "translation", "meaning", "example"]
        widgets = {"pronunciation": forms.TextInput(attrs={"placeholder": "e.g. /həˈləʊ/ or how it sounds"}),
                   "meaning": forms.Textarea(attrs={"rows": 2}), "example": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.links = ([], [])
        self.missing = {"opposite_terms": [], "similar_terms": []}
        if self.instance.pk and not self.is_bound:
            self.fields["opposite_terms"].initial = ", ".join(w.term for w in self.instance.opposites.all())
            self.fields["similar_terms"].initial = ", ".join(w.term for w in self.instance.similar.all())

    def clean(self):
        data = super().clean()
        term = (data.get("term") or "").strip().casefold()
        mine = {w.term.casefold(): w for w in Word.objects.filter(user=self.user)}
        self.links = ([], [])
        self.missing = {"opposite_terms": [], "similar_terms": []}
        for i, name in enumerate(("opposite_terms", "similar_terms")):
            missing = []
            for t in [x.strip() for x in (data.get(name) or "").split(",") if x.strip()]:
                w = mine.get(t.casefold())
                if t.casefold() == term:
                    self.add_error(name, "A word can't be linked to itself.")
                elif w is None:
                    missing.append(t)
                elif w not in self.links[i]:
                    self.links[i].append(w)
            if missing:
                self.missing[name] = missing
                self.add_error(name, "Not found: " + ", ".join(missing) + ". Use “+ Add a new word” below to create it.")
        both = [w.term for w in self.links[0] if w in self.links[1]]
        if both:
            self.add_error("similar_terms", "Can't be both opposite and similar: " + ", ".join(both))
        return data

    def save_links(self, word):
        word.opposites.set(self.links[0])
        word.similar.set(self.links[1])
