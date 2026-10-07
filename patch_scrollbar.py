import codecs

path = r"d:\Antigravity\VideoTools\main\main.py"
with codecs.open(path, 'r', 'utf-8') as f:
    code = f.read()

old_css = "QScrollBar::handle:vertical { background: #333333; min-height: 20px; border-radius: 3px; }"
new_css = "QScrollBar::handle:vertical { background: #ECC94B; min-height: 20px; border-radius: 3px; }"

old_hover = "QScrollBar::handle:vertical:hover { background: #555555; }"
new_hover = "QScrollBar::handle:vertical:hover { background: #D69E2E; }"

if old_css in code:
    code = code.replace(old_css, new_css)
    code = code.replace(old_hover, new_hover)
    with codecs.open(path, 'w', 'utf-8') as f:
        f.write(code)
    print("Patched main.py successfully.")
else:
    print("CSS string not found in main.py")
