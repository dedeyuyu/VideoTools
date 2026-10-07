import json
import copy

path = r"d:\Antigravity\VideoTools\duet_data\card_presets.json"
with open(path, 'r', encoding='utf-8') as f:
    d = json.load(f)

base = None
for k, v in d.items():
    if v.get("mode") == "text":
        base = copy.deepcopy(v)
        break
if not base:
    base = list(d.values())[0]

def make_tpl(font, color, hl, stroke_w=0, stroke_c="#000000", 
             bg=True, bg_shape="hug", bg_color="#FFFFFF", bg_alpha=255, 
             bg_rad=18, px=30, py=15, bold=True, italic=False, shadow=False, shadow_c="#000000"):
    t = copy.deepcopy(base)
    t["mode"] = "text"
    t["font_family"] = font
    t["color"] = color
    t["hl_color"] = hl
    t["bold"] = bold
    t["italic"] = italic
    t["stroke"] = stroke_w > 0
    t["stroke_width"] = stroke_w
    t["stroke_color"] = stroke_c
    t["bg"] = bg
    t["bg_shape"] = bg_shape
    t["bg_fit"] = False
    t["bg_color"] = bg_color
    t["bg_alpha"] = bg_alpha
    t["bg_radius"] = bg_rad
    t["bg_pad_x"] = px
    t["bg_pad_y"] = py
    t["shadow"] = shadow
    t["shadow_color"] = shadow_c
    t["line_spacing"] = -2 if bg_shape == "hug" else 5
    return t

keys_to_remove = []
old_templates = {}
for k in d.keys():
    if "Abrazo Naranja" in k or "Borde Blanco" in k or "Azul Marino" in k or "Banner Azul" in k:
        keys_to_remove.append(k)
        new_name = "热门 - " + k.replace("热门 - ", "")
        old_templates[new_name] = d[k]

for k in keys_to_remove:
    del d[k]

d.update(old_templates)

# 2. Add the 4 new templates from the screenshot
d["热门 - 醒目大字 (Impacto Marrón)"] = make_tpl("Oswald", "#4A2C10", "#990000", bg=True, bg_shape="rounded", bg_color="#FFFFFF", px=40, py=20, bg_rad=20)
d["热门 - 经典包裹 (Abrazo Clásico)"] = make_tpl("Lora", "#632F14", "#FF0000", bg=True, bg_shape="hug", bg_color="#FFFFFF", px=20, py=12, bg_rad=20)
d["热门 - 温柔信笺 (Cartel Beige)"] = make_tpl("Lora", "#703016", "#C00000", bg=True, bg_shape="rounded", bg_color="#F4E3D7", px=60, py=20, bg_rad=10)
d["热门 - 红色强调 (Alerta Crema)"] = make_tpl("Oswald", "#C00000", "#FF0000", bg=True, bg_shape="hug", bg_color="#F0E6CD", px=25, py=15, italic=True)

# 3. Generate 20 more viral templates
d["热门 - 黑黄冲击 (Impacto Amarillo)"] = make_tpl("Oswald", "#000000", "#FF0000", bg=True, bg_shape="hug", bg_color="#FFD700")
d["热门 - 纯白深红 (Carmesí Profundo)"] = make_tpl("Oswald", "#FFFFFF", "#FFD700", bg=True, bg_shape="rounded", bg_color="#9E0B0F", bg_rad=15)
d["热门 - 翠绿奶油 (Crema Esmeralda)"] = make_tpl("Lora", "#0A4222", "#000000", bg=True, bg_shape="hug", bg_color="#F5F2E6")
d["热门 - 黑底荧光 (Neón Urbano)"] = make_tpl("Impact", "#00FF41", "#FFFFFF", bg=True, bg_shape="pill", bg_color="#000000", px=40)
d["热门 - 强效白边 (Borde Grueso)"] = make_tpl("Oswald", "#000000", "#FF0000", stroke_w=10, stroke_c="#FFFFFF", bg=False)
d["热门 - 薄荷巧克力 (Menta Cacao)"] = make_tpl("Lora", "#3E2723", "#000000", bg=True, bg_shape="hug", bg_color="#D7F2E3")
d["热门 - 紫罗兰药丸 (Píldora Violeta)"] = make_tpl("Microsoft YaHei", "#FFFFFF", "#FFD700", bg=True, bg_shape="pill", bg_color="#2D0A42", px=40)
d["热门 - 橘色警报 (Alerta Naranja)"] = make_tpl("Oswald", "#FFFFFF", "#000000", bg=True, bg_shape="banner", bg_color="#FF6B00", py=30, bg_rad=0)
d["热门 - 玫瑰情书 (Carta Rosa)"] = make_tpl("Lora", "#5E0A0E", "#000000", bg=True, bg_shape="rounded", bg_color="#FADCDD", bg_rad=25)
d["热门 - 冰蓝海军 (Marina Glacial)"] = make_tpl("Oswald", "#0B1B3D", "#FF0000", bg=True, bg_shape="hug", bg_color="#DCE5F2")
d["热门 - 黑金贵族 (Oro Negro)"] = make_tpl("Lora", "#FFD700", "#FFFFFF", bg=True, bg_shape="banner", bg_color="#000000", bg_alpha=220, py=35, bg_rad=0)
d["热门 - 焦糖可可 (Cacao Caramelo)"] = make_tpl("Oswald", "#FFFFFF", "#FFD700", bg=True, bg_shape="pill", bg_color="#4E342E", px=35)
d["热门 - 赛博青黑 (Cyber Cyan)"] = make_tpl("Impact", "#000000", "#FFFFFF", bg=True, bg_shape="hug", bg_color="#00E5FF")
d["热门 - 珊瑚夜空 (Coral Nocturno)"] = make_tpl("Microsoft YaHei", "#FF7F50", "#FFFFFF", bg=True, bg_shape="rounded", bg_color="#000080")
d["热门 - 品红狂热 (Fiebre Magenta)"] = make_tpl("Oswald", "#FFFFFF", "#FFD700", bg=True, bg_shape="hug", bg_color="#C51162")
d["热门 - 复古黄绿 (Retro Mostaza)"] = make_tpl("Lora", "#004D40", "#000000", bg=True, bg_shape="rect", bg_color="#FFF59D", bg_rad=0)
d["热门 - 红色重击 (Golpe Rojo)"] = make_tpl("Impact", "#FFFFFF", "#FFFF00", stroke_w=12, stroke_c="#D50000", bg=False)
d["热门 - 熏衣草梦 (Sueño Lavanda)"] = make_tpl("Lora", "#E1BEE7", "#FFFFFF", bg=True, bg_shape="rounded", bg_color="#311B92", bg_rad=18)
d["热门 - 煤炭亮黄 (Carbón Limón)"] = make_tpl("Oswald", "#FFEB3B", "#FFFFFF", bg=True, bg_shape="hug", bg_color="#263238")
d["热门 - 极致投影 (Sombra Extrema)"] = make_tpl("Oswald", "#000000", "#FF0000", bg=True, bg_shape="hug", bg_color="#FFFFFF", shadow=True, shadow_c="#000000")

with open(path, 'w', encoding='utf-8') as f:
    json.dump(d, f, ensure_ascii=False, indent=2)

print("Batch templates updated!")
