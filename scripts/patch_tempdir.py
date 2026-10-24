import os

p = r"c:\Users\Solanki Divyang\OneDrive\Desktop\Medikiosk-main\.venv_speech\Lib\site-packages\nemo\collections\asr\parts\mixins\transcription.py"
with open(p, "r", encoding="utf-8") as f:
    c = f.read()

old = "with tempfile.TemporaryDirectory() as tmpdir:"
new = "with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:"

if old in c:
    c = c.replace(old, new, 1)
    with open(p, "w", encoding="utf-8") as f:
        f.write(c)
    print("Patched TemporaryDirectory in transcription.py")
else:
    print("Old pattern not found in transcription.py")
