import codecs

path_render = r"d:\Antigravity\VideoTools\image_worker\duet_render.py"
with codecs.open(path_render, 'r', 'utf-8') as f:
    code = f.read()

old_logic = """                outline = stroker.createStroke(card_path)
                card_path.addPath(outline)
                card_path = card_path.simplified()
                card_path.setFillRule(Qt.FillRule.WindingFill)"""

new_logic = """                outline = stroker.createStroke(card_path)
                card_path = card_path.united(outline)
                card_path = card_path.simplified()"""

code = code.replace(old_logic, new_logic)

with codecs.open(path_render, 'w', 'utf-8') as f:
    f.write(code)

print("Patched fill rule to use united()")
