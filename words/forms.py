from django import forms

from .models import Word


class WordForm(forms.ModelForm):
    class Meta:
        model = Word
        fields = ["term", "pronunciation", "translation", "meaning", "example"]
        widgets = {"pronunciation": forms.TextInput(attrs={"placeholder": "e.g. /həˈləʊ/ or how it sounds"}), "meaning": forms.Textarea(attrs={"rows": 2}), "example": forms.Textarea(attrs={"rows": 2})}
