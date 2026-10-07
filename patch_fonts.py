import codecs

path = r"d:\Antigravity\VideoTools\image_worker\duet_render.py"
with codecs.open(path, 'r', 'utf-8') as f:
    code = f.read()

old_load = """def load_bundled_fonts():
    \"\"\"加载软件自带的预设字体（duet_fonts 目录）。\"\"\"
    global _bundled_loaded
    if _bundled_loaded:
        return
    _bundled_loaded = True
    d = os.path.join(get_install_root(), "duet_fonts")
    if os.path.isdir(d):
        for fn in sorted(os.listdir(d)):
            if fn.lower().endswith((".ttf", ".otf")):
                load_font_file(os.path.join(d, fn))"""

new_load = """def load_bundled_fonts():
    \"\"\"加载软件自带的预设字体（duet_fonts 目录以及 videokit 目录）。\"\"\"
    global _bundled_loaded
    if _bundled_loaded:
        return
    _bundled_loaded = True
    
    dirs_to_check = [
        os.path.join(get_install_root(), "duet_fonts"),
        r"C:\\Users\\DYcomputer\\AppData\\Local\\Programs\\videokit\\resources\\assets\\fonts"
    ]
    
    for d in dirs_to_check:
        if os.path.isdir(d):
            for fn in sorted(os.listdir(d)):
                if fn.lower().endswith((".ttf", ".otf", ".ttc")):
                    load_font_file(os.path.join(d, fn))"""

code = code.replace(old_load, new_load)

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(code)

print("Patched load_bundled_fonts")
