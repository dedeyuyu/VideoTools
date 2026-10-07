import json
import copy

path = r"d:\Antigravity\VideoTools\duet_data\card_presets.json"
with open(path, 'r', encoding='utf-8') as f:
    d = json.load(f)

# Get a base text template (not image)
base = list(d.values())[1]  # The second one is usually text

p1 = copy.deepcopy(base)
p1["mode"] = "text"
p1["font_family"] = "Lora"
p1["color"] = "#F26C24"
p1["hl_color"] = "#FF0000"
p1["stroke"] = False
p1["shadow"] = False
p1["bg"] = True
p1["bg_shape"] = "hug"
p1["bg_color"] = "#FFFFFF"
p1["bg_alpha"] = 255
p1["bg_radius"] = 25
p1["bg_pad_x"] = 35
p1["bg_pad_y"] = 20
p1["line_spacing"] = -2
p1["bold"] = True

p2 = copy.deepcopy(base)
p2["mode"] = "text"
p2["font_family"] = "Oswald"
p2["color"] = "#4A2000"
p2["hl_color"] = "#990000"
p2["stroke"] = True
p2["stroke_color"] = "#FFFFFF"
p2["stroke_width"] = 12
p2["shadow"] = False
p2["bg"] = False
p2["bg_shape"] = "rounded"
p2["bold"] = True

p3 = copy.deepcopy(base)
p3["mode"] = "text"
p3["font_family"] = "Oswald"
p3["color"] = "#1A1A80"
p3["hl_color"] = "#990000"
p3["stroke"] = False
p3["shadow"] = False
p3["bg"] = True
p3["bg_shape"] = "rounded"
p3["bg_fit"] = False
p3["bg_color"] = "#FFFFFF"
p3["bg_alpha"] = 255
p3["bg_radius"] = 30
p3["bg_pad_x"] = 40
p3["bg_pad_y"] = 25
p3["bold"] = True

p4 = copy.deepcopy(base)
p4["mode"] = "text"
p4["font_family"] = "Oswald"
p4["color"] = "#FFFFFF"
p4["hl_color"] = "#FFD400"
p4["stroke"] = False
p4["shadow"] = True
p4["shadow_color"] = "#000000"
p4["shadow_blur"] = 8
p4["bg"] = True
p4["bg_shape"] = "banner"
p4["bg_fit"] = False
p4["bg_color"] = "#2B3568"
p4["bg_alpha"] = 190
p4["bg_radius"] = 0
p4["bg_pad_x"] = 40
p4["bg_pad_y"] = 40
p4["bold"] = True

d["橙色包裹 (Abrazo Naranja)"] = p1
d["深棕白边 (Borde Blanco Marrón)"] = p2
d["圆润海军蓝 (Azul Marino Redondeado)"] = p3
d["深蓝通栏横幅 (Banner Azul Oscuro)"] = p4

with open(path, 'w', encoding='utf-8') as f:
    json.dump(d, f, ensure_ascii=False, indent=2)

print("Added 4 new templates")
