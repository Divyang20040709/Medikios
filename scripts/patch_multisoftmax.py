import os

p = r"c:\Users\Solanki Divyang\OneDrive\Desktop\Medikiosk-main\.venv_speech\Lib\site-packages\nemo\collections\asr\modules\rnnt.py"
with open(p, "r", encoding="utf-8") as f:
    c = f.read()

# 1. Add MultiSoftmaxHead class if not present
if "class MultiSoftmaxHead" not in c:
    class_def = """
class MultiSoftmaxHead(torch.nn.ModuleDict):
    def __init__(self, in_features, langs, out_features=257):
        super().__init__({lang: torch.nn.Linear(in_features, out_features) for lang in langs})
        self.current_lang = 'hi'

    def forward(self, x):
        return self[getattr(self, 'current_lang', 'hi')](x)

"""
    # Insert right before class RNNTJoint
    target_cls = "class RNNTJoint("
    c = c.replace(target_cls, class_def + target_cls, 1)
    print("Added MultiSoftmaxHead class definition")

# 2. Update RNNTJoint.__init__ to store multilingual and language_keys
target_init = "self.masking_prob = masking_prob"
replacement_init = """self.masking_prob = masking_prob
        self.multilingual = kwargs.get('multilingual', False)
        self.language_keys = kwargs.get('language_keys', None)"""
if target_init in c and "self.multilingual = kwargs" not in c:
    c = c.replace(target_init, replacement_init, 1)
    print("Added multilingual and language_keys storage in RNNTJoint.__init__")

# 3. Update _joint_net_modules in RNNTJoint
target_layers = """        layers = (
            [activation]
            + ([torch.nn.Dropout(p=dropout)] if dropout else [])
            + [torch.nn.Linear(joint_n_hidden, num_classes)]
        )"""

replacement_layers = """        if getattr(self, 'multilingual', False) and getattr(self, 'language_keys', None):
            final_layer = MultiSoftmaxHead(joint_n_hidden, self.language_keys, 257)
        else:
            final_layer = torch.nn.Linear(joint_n_hidden, num_classes)

        layers = (
            [activation]
            + ([torch.nn.Dropout(p=dropout)] if dropout else [])
            + [final_layer]
        )"""

if target_layers in c:
    c = c.replace(target_layers, replacement_layers, 1)
    print("Updated _joint_net_modules with MultiSoftmaxHead support")
elif "if getattr(self, 'multilingual', False)" in c:
    print("MultiSoftmaxHead in _joint_net_modules already present")

with open(p, "w", encoding="utf-8") as f:
    f.write(c)

print("rnnt.py patching complete.")
