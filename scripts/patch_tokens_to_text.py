import os

p = r"c:\Users\Solanki Divyang\OneDrive\Desktop\Medikiosk-main\.venv_speech\Lib\site-packages\nemo\collections\common\tokenizers\aggregate_tokenizer.py"
with open(p, "r", encoding="utf-8") as f:
    c = f.read()

old = """    def tokens_to_text(self, tokens, lang_id):
        if isinstance(tokens, np.ndarray):
            tokens = tokens.tolist()

        tokenizer = self.tokenizers_dict[lang_id]
        return tokenizer.decode_pieces(tokens)"""

new = """    def tokens_to_text(self, tokens, lang_id=None):
        if isinstance(tokens, np.ndarray):
            tokens = tokens.tolist()

        if lang_id is None:
            lang_id = getattr(self, 'selected_language', None) or getattr(self, 'current_lang', None)

        if lang_id is not None and lang_id in self.tokenizers_dict:
            tokenizer = self.tokenizers_dict[lang_id]
            return tokenizer.decode_pieces(tokens)

        # Fallback: each piece in sentencepiece starts with   (\u2581)
        return "".join(tokens).replace("\u2581", " ").strip()"""

if old in c:
    c = c.replace(old, new, 1)
    with open(p, "w", encoding="utf-8") as f:
        f.write(c)
    print("Patched tokens_to_text in aggregate_tokenizer.py")
else:
    print("Pattern not found in aggregate_tokenizer.py")
