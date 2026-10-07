import codecs

# 1. Patch UI
path_ui = r"d:\Antigravity\VideoTools\UI\ui_duet_video.py"
with codecs.open(path_ui, 'r', 'utf-8') as f:
    code = f.read()

old_items = """        self._add(g, "bg_shape", "combo", "底框形状", items=[
            ("rect", "直角长方形"),"""
new_items = """        self._add(g, "bg_shape", "combo", "底框形状", items=[
            ("hug", "紧密包裹 (无缝连体)"),
            ("rect", "直角长方形"),"""
code = code.replace(old_items, new_items)

with codecs.open(path_ui, 'w', 'utf-8') as f:
    f.write(code)


# 2. Patch Render
path_render = r"d:\Antigravity\VideoTools\image_worker\duet_render.py"
with codecs.open(path_render, 'r', 'utf-8') as f:
    code = f.read()

# Make sure to import QPainterPathStroker if not imported, though it might be in PyQt6.QtGui
# Let's just import it locally or check if it exists. Actually, it's safer to import it at the top.
if "QPainterPathStroker" not in code:
    code = code.replace("from PyQt6.QtGui import (", "from PyQt6.QtGui import (QPainterPathStroker, ")
    if "from PyQt6.QtGui import (" not in code:
        # If it doesn't use parentheses
        code = code.replace("QPainterPath,", "QPainterPath, QPainterPathStroker,")
        if "QPainterPath," not in code:
            code = code.replace("import QPainterPath", "import QPainterPath, QPainterPathStroker")

old_fit_logic = """        if fit:
            card_path = QPainterPath()"""

new_fit_logic = """        if shape == "hug":
            from PyQt6.QtGui import QPainterPathStroker
            from PyQt6.QtCore import Qt
            card_path = QPainterPath()
            for i, ln in enumerate(all_lines):
                y1 = ln.y
                y2 = ln.y + ln.h
                if i > 0:
                    y1 = min(y1, all_lines[i-1].y + all_lines[i-1].h)
                if i < len(all_lines) - 1:
                    y2 = max(y2, all_lines[i+1].y)
                card_path.addRect(QRectF(ln.x, y1, ln.w, y2 - y1))
            
            card_path = card_path.simplified()
            if not card_path.isEmpty():
                stroker = QPainterPathStroker()
                # The radius of the stroke determines the padding
                stroker.setWidth(max(px, py) * 2 if max(px, py) > 0 else 20)
                stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
                outline = stroker.createStroke(card_path)
                card_path.addPath(outline)
                card_path = card_path.simplified()
        elif fit:
            card_path = QPainterPath()"""

code = code.replace(old_fit_logic, new_fit_logic)

with codecs.open(path_render, 'w', 'utf-8') as f:
    f.write(code)

print("Patched UI and Render for hug shape")
