import re
import codecs

path = r"d:\Antigravity\VideoTools\image_worker\duet_worker.py"
with codecs.open(path, 'r', 'utf-8') as f:
    code = f.read()

# 1. Update build_render_cmd arguments
code = code.replace(
    '                     phone_png: str = "", phone_start: float = 0.0,',
    '                     phone_png: str = "", phone_start: float = 0.0,\n                     wm_png: str = "",'
)

# 2. Add wm_idx logic
wm_idx_code = """
    if phone_png and os.path.isfile(phone_png):
        cmd += ["-loop", "1", "-t", f"{D:.3f}", "-i", phone_png]
        phone_idx = idx
        idx += 1
        
    wm_idx = None
    if wm_png and os.path.isfile(wm_png):
        cmd += ["-loop", "1", "-t", f"{D:.3f}", "-i", wm_png]
        wm_idx = idx
        idx += 1
"""
code = code.replace(
    '    if phone_png and os.path.isfile(phone_png):\n        cmd += ["-loop", "1", "-t", f"{D:.3f}", "-i", phone_png]\n        phone_idx = idx\n        idx += 1',
    wm_idx_code.strip('\n')
)

# 3. Add to filter complex
fc_code = """
    if phone_idx is not None:
        fc.append(f"[{last}][{phone_idx}:v]overlay=0:0:enable='gte(t,{phone_start:.3f})'[s4]")
        last = "s4"
    if wm_idx is not None:
        fc.append(f"[{last}][{wm_idx}:v]overlay=0:0[s5]")
        last = "s5"
"""
code = code.replace(
    '    if phone_idx is not None:\n        fc.append(f"[{last}][{phone_idx}:v]overlay=0:0:enable=\'gte(t,{phone_start:.3f})\'[s4]")\n        last = "s4"',
    fc_code.strip('\n')
)

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(code)

print("Patched duet_worker.py")
