import os
import shutil

src_dir = r"C:\Users\DYcomputer\AppData\Local\Programs\videokit\resources\assets\fonts"
dst_dir = r"d:\Antigravity\VideoTools\duet_fonts"

os.makedirs(dst_dir, exist_ok=True)

count = 0
for root, dirs, files in os.walk(src_dir):
    for fn in files:
        if fn.lower().endswith((".ttf", ".otf", ".ttc")):
            src_path = os.path.join(root, fn)
            dst_path = os.path.join(dst_dir, fn)
            if not os.path.exists(dst_path):
                shutil.copy2(src_path, dst_path)
                count += 1

print(f"Copied {count} new fonts to duet_fonts!")
