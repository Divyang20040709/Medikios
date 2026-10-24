import os

p = r"c:\Users\Solanki Divyang\OneDrive\Desktop\Medikiosk-main\backend\app\speech\indicconformer_provider.py"
with open(p, "r", encoding="utf-8") as f:
    c = f.read()

# 1. Update _resolve_device default
old_dev = '    return "cuda"  # Will fall back to cpu in the inference script if unavailable'
new_dev = '    return "cpu"  # Safe default (use INDICCONFORMER_DEVICE=cuda if GPU compute capability is supported)'
if old_dev in c:
    c = c.replace(old_dev, new_dev, 1)

# 2. Update JSON parsing in _run_inference_subprocess
old_json = """            # Parse JSON output from inference script
            try:
                result = json.loads(stdout_text)
                return result
            except json.JSONDecodeError:"""

new_json = """            # Parse JSON output from inference script (find JSON line from output)
            for line in reversed(stdout_text.splitlines()):
                line = line.strip()
                if line.startswith("{") and line.endswith("}"):
                    try:
                        return json.loads(line)
                    except json.JSONDecodeError:
                        continue

            try:
                result = json.loads(stdout_text)
                return result
            except json.JSONDecodeError:"""

if old_json in c:
    c = c.replace(old_json, new_json, 1)

with open(p, "w", encoding="utf-8") as f:
    f.write(c)

print("indicconformer_provider.py successfully updated.")
