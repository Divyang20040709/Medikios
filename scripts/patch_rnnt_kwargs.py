import os

p = r"c:\Users\Solanki Divyang\OneDrive\Desktop\Medikiosk-main\.venv_speech\Lib\site-packages\nemo\collections\asr\modules\rnnt.py"
with open(p, "r", encoding="utf-8") as f:
    c = f.read()

# Patch RNNTDecoder.__init__
old_decoder = "        blank_as_pad: bool = True,\n    ):"
new_decoder = "        blank_as_pad: bool = True,\n        **kwargs,\n    ):"
if old_decoder in c:
    c = c.replace(old_decoder, new_decoder, 1)
    print("Patched RNNTDecoder.__init__ to accept **kwargs")

# Patch RNNTJoint.__init__
old_joint = "        masking_prob: float = -1.0,\n    ):"
new_joint = "        masking_prob: float = -1.0,\n        **kwargs,\n    ):"
if old_joint in c:
    c = c.replace(old_joint, new_joint, 1)
    print("Patched RNNTJoint.__init__ to accept **kwargs")

with open(p, "w", encoding="utf-8") as f:
    f.write(c)

print("rnnt.py patching complete.")
