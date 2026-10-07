import codecs

path = r"d:\Antigravity\VideoTools\image_worker\duet_render.py"
with codecs.open(path, 'r', 'utf-8') as f:
    code = f.read()

old_load = """    for d in dirs_to_check:
        if os.path.isdir(d):
            for fn in sorted(os.listdir(d)):
                if fn.lower().endswith((".ttf", ".otf", ".ttc")):
                    load_font_file(os.path.join(d, fn))"""

new_load = """    for d in dirs_to_check:
        if os.path.isdir(d):
            for root, dirs, files in os.walk(d):
                for fn in files:
                    if fn.lower().endswith((".ttf", ".otf", ".ttc")):
                        load_font_file(os.path.join(root, fn))"""

code = code.replace(old_load, new_load)

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(code)

print("Patched load_bundled_fonts with os.walk")
