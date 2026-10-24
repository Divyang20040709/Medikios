import os

p = r"c:\Users\Solanki Divyang\OneDrive\Desktop\Medikiosk-main\.venv_speech\Lib\site-packages\nemo\collections\common\tokenizers\aggregate_tokenizer.py"
with open(p, "r", encoding="utf-8") as f:
    c = f.read()

target = """        if lang_id is not None and lang_id in self.tokenizers_dict:
            tokenizer = self.tokenizers_dict[lang_id]
            return tokenizer.decode_pieces(tokens)"""

replacement = """        if lang_id is not None and lang_id in self.tokenizers_dict:
            tok = self.tokenizers_dict[lang_id]
            if hasattr(tok, 'tokens_to_text'):
                return tok.tokens_to_text(tokens)
            elif hasattr(tok, 'decode_pieces'):
                return tok.decode_pieces(tokens)"""

if target in c:
    c = c.replace(target, replacement, 1)
    with open(p, "w", encoding="utf-8") as f:
        f.write(c)
    print("Patched tokens_to_text with hasattr checks")
else:
    print("Target block not found in aggregate_tokenizer.py")
