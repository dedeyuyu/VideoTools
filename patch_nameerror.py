import codecs

path = r"d:\Antigravity\VideoTools\image_worker\duet_render.py"
with codecs.open(path, 'r', 'utf-8') as f:
    lines = f.read().splitlines()

# Filter out the local imports
new_lines = [l for i, l in enumerate(lines) if i not in (600, 601)] # wait, let's verify line numbers

# Safer: check the exact strings
filtered_lines = []
for l in lines:
    if "from PyQt6.QtGui import QPainterPathStroker" in l and l.startswith("            from "):
        continue
    if "from PyQt6.QtCore import Qt" in l and l.startswith("            from "):
        continue
    filtered_lines.append(l)

with codecs.open(path, 'w', 'utf-8') as f:
    f.write('\n'.join(filtered_lines))

print("Removed local imports causing NameError")
