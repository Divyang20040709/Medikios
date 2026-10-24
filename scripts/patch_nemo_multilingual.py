import os

base = r"c:\Users\Solanki Divyang\OneDrive\Desktop\Medikiosk-main\.venv_speech\Lib\site-packages\nemo\collections\asr"
for root, _, files in os.walk(base):
    for f in files:
        if f.endswith('.py'):
            p = os.path.join(root, f)
            with open(p, 'r', encoding='utf-8', errors='ignore') as fp:
                content = fp.read()
            
            modified = False
            # Look for agg checks
            for old in [
                'if self.tokenizer_type == "agg":',
                "if self.tokenizer_type == 'agg':",
                'elif tokenizer_type.lower() == "agg":',
                "elif tokenizer_type.lower() == 'agg':",
                'if new_tokenizer_type == "agg":',
                "if new_tokenizer_type == 'agg':",
            ]:
                if old in content:
                    new = old.replace('== "agg"', 'in ("agg", "multilingual")').replace("== 'agg'", "in ('agg', 'multilingual')")
                    content = content.replace(old, new)
                    modified = True
                    print(f"Patched in {os.path.basename(p)}: {old} -> {new}")
            
            if modified:
                with open(p, 'w', encoding='utf-8') as fp:
                    fp.write(content)
print("Patching complete.")
