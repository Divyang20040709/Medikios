import os

p = r"c:\Users\Solanki Divyang\OneDrive\Desktop\Medikiosk-main\backend\app\speech\indicconformer_infer.py"
with open(p, "r", encoding="utf-8") as f:
    c = f.read()

target = '    except Exception as e:\n        errors.append(f"NeMo inference failed: {e}")'
replacement = """    except Exception as e:
        import traceback
        errors.append(f"NeMo inference failed: {e}\\n{traceback.format_exc()}")"""

if target in c:
    c = c.replace(target, replacement, 1)
    with open(p, "w", encoding="utf-8") as f:
        f.write(c)
    print("Traceback printing enabled in indicconformer_infer.py")
else:
    print("Target not found")
