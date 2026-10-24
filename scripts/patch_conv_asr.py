import os

p = r"c:\Users\Solanki Divyang\OneDrive\Desktop\Medikiosk-main\.venv_speech\Lib\site-packages\nemo\collections\asr\modules\conv_asr.py"
with open(p, "r", encoding="utf-8") as f:
    c = f.read()

old = 'def __init__(self, feat_in, num_classes, init_mode="xavier_uniform", vocabulary=None, add_blank=True):'
new = 'def __init__(self, feat_in, num_classes, init_mode="xavier_uniform", vocabulary=None, add_blank=True, **kwargs):'

if old in c:
    c = c.replace(old, new, 1)
    with open(p, "w", encoding="utf-8") as f:
        f.write(c)
    print("Patched ConvASRDecoder.__init__ with **kwargs")
elif new in c:
    print("ConvASRDecoder already patched")
else:
    print("Target not found in conv_asr.py")
