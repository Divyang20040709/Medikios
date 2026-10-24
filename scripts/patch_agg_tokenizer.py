import os

p = r"c:\Users\Solanki Divyang\OneDrive\Desktop\Medikiosk-main\.venv_speech\Lib\site-packages\nemo\collections\common\tokenizers\aggregate_tokenizer.py"
with open(p, "r", encoding="utf-8") as f:
    c = f.read()

old = """    def _call_agg_tokenizer(self, text: str, lang: str | None = None):
        assert lang is not None, "Expected 'lang' to be set for AggregateTokenizer."
        return self._tokenizer.text_to_ids(text, lang)"""

new = """    def _call_agg_tokenizer(self, text: str, lang: str | None = None):
        if not text:
            return []
        if lang is None:
            lang = getattr(self._tokenizer, 'selected_language', None) or 'hi'
        return self._tokenizer.text_to_ids(text, lang)"""

if old in c:
    c = c.replace(old, new, 1)
    with open(p, "w", encoding="utf-8") as f:
        f.write(c)
    print("Patched _call_agg_tokenizer in aggregate_tokenizer.py")
else:
    print("Old pattern not found in aggregate_tokenizer.py")
