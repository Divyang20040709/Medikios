import os

p = r"c:\Users\Solanki Divyang\OneDrive\Desktop\Medikiosk-main\backend\app\speech\indicconformer_infer.py"
with open(p, "r", encoding="utf-8") as f:
    c = f.read()

# Add stdout/stderr reconfigure after warnings
target_top = "warnings.filterwarnings(\"ignore\")"
replacement_top = """warnings.filterwarnings("ignore")

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')"""

if target_top in c and "sys.stdout.reconfigure" not in c:
    c = c.replace(target_top, replacement_top, 1)

# Update print(json.dumps(...)) to use buffer write or safe stdout
target_print = "    # Output JSON to stdout\n    print(json.dumps(result, ensure_ascii=False))"
replacement_print = """    # Output JSON to stdout (UTF-8 safe for Windows)
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode('utf-8') + b'\\n')
    sys.stdout.buffer.flush()"""

if target_print in c:
    c = c.replace(target_print, replacement_print, 1)

with open(p, "w", encoding="utf-8") as f:
    f.write(c)

print("indicconformer_infer.py patched for UTF-8 stdout encoding.")
