# -*- coding: utf-8 -*-
import codecs
import pprint
import sys
import os

sys.path.insert(0, os.path.abspath('UI'))
try:
    from default_presets import DEFAULT_PRESETS
except ImportError:
    DEFAULT_PRESETS = {}

new_presets = {}

# Helper to generate base dict
def base_card():
    return {
        "enabled": True, "mode": "text", "time": 8.0,
        "font_family": "Microsoft YaHei", "font_file": "",
        "size": 72, "bold": True, "italic": False, "weight": 700,
        "letter_spacing": 0, "rtl": False, "uppercase": False,
        "color": "#FFFFFF", "hl_color": "#FFD400",
        "keywords": "", "hl_numbers": False, "hl_english": False,
        "stroke": False, "stroke_color": "#000000", "stroke_width": 0,
        "shadow": False, "shadow_color": "#000000", "shadow_blur": 6, "shadow_x": 4, "shadow_y": 4, "shadow_alpha": 100,
        "multi_stroke": False, "ms_layers": 2, "ms_step": 6, "ms_feather": 0, "ms_colors": "",
        "bg": False, "bg_fit": False, "bg_shape": "rect", "bg_color": "#000000", "bg_alpha": 170,
        "bg_radius": 18, "bg_pad_x": 30, "bg_pad_y": 16, "bg_border_w": 0, "bg_border_color": "#FFFFFF",
        "bg_bottom_w": 0, "bg_bottom_color": "#D90429", "bg_shadow": False,
        "sub_enabled": False, "sub_size": 40, "sub_color": "#FFFFFF", "sub_hl_color": "#FFD400",
        "sub_stroke": False, "sub_stroke_color": "#000000", "sub_stroke_width": 6,
        "split": "none", "split_color2": "#FFFFFF", "split_alpha2": 255,
        "icon": "none", "pos_x": 540, "pos_y": 960, "width": 960, "wrap": True, "line_spacing": 8
    }

# Category 1: Light BG + Dark Text
# 20 combos
light_bgs = [
    ("#FFFFFF", "白"), ("#FDE8E8", "浅粉"), ("#E8FDE8", "浅绿"), ("#E8E8FD", "浅蓝"),
    ("#FFF9E6", "浅黄"), ("#F3E8FD", "浅紫"), ("#E8FDFD", "浅青"), ("#FDF5E8", "浅橙"),
    ("#F0F0F0", "浅灰"), ("#FDF0F5", "浅玫")
] * 2

dark_texts = [
    ("#2C3E50", "深灰蓝"), ("#1A5276", "海军蓝"), ("#512E5F", "深紫"), ("#7B241C", "深红"),
    ("#0E6251", "深翠绿"), ("#7D6608", "深金暗黄"), ("#4A2311", "深棕"), ("#154360", "深海蓝"),
    ("#641E16", "酒红"), ("#145A32", "森林绿")
] * 2

for i in range(20):
    bg_color, bg_name = light_bgs[i]
    txt_color, txt_name = dark_texts[i]
    p = base_card()
    p["bg"] = True
    p["bg_color"] = bg_color
    p["bg_alpha"] = 255
    p["color"] = txt_color
    p["hl_color"] = "#E74C3C" if txt_color != "#7B241C" else "#2980B9"
    name = f"热门 - 纯净浅色 {i+1:02d} ({bg_name}底{txt_name}字)"
    new_presets[name] = p

# Category 2: Light BG + Light Text + Thick Dark Stroke
# 20 combos
for i in range(20):
    bg_color, bg_name = light_bgs[i]
    stroke_color, strk_name = dark_texts[19-i]  # reverse to get different combos
    txt_color = "#FFFFFF" if i % 2 == 0 else "#FFF9C4"
    txt_name = "白" if i % 2 == 0 else "浅黄"
    
    p = base_card()
    p["bg"] = True
    p["bg_color"] = bg_color
    p["bg_alpha"] = 255
    p["color"] = txt_color
    p["hl_color"] = "#F1C40F" if txt_color == "#FFFFFF" else "#FFFFFF"
    p["stroke"] = True
    p["stroke_width"] = 10 + (i % 3) * 2  # 10, 12, 14
    p["stroke_color"] = stroke_color
    name = f"热门 - 粗描边 {i+1:02d} ({bg_name}底{strk_name}边{txt_name}字)"
    new_presets[name] = p

# Category 3: Multi-layer Stroke (多层扩展描边)
# 20 combos
ms_palettes = [
    ("#FFFFFF", "#E74C3C,#C0392B", "红系"), ("#FFF9C4", "#D35400,#A04000", "橙系"),
    ("#FFFFFF", "#2980B9,#1A5276", "蓝系"), ("#E8FDFD", "#117A65,#0E6251", "青系"),
    ("#FDE8E8", "#8E44AD,#5B2C6F", "紫系"), ("#FFFFFF", "#F39C12,#D68910", "金系"),
    ("#E8FDE8", "#27AE60,#145A32", "绿系"), ("#FFFFFF", "#34495E,#2C3E50", "灰蓝系"),
    ("#FDF0F5", "#E83A59,#B00020", "玫红系"), ("#FFFFFF", "#1ABC9C,#117A65", "湖绿系")
] * 2

for i in range(20):
    txt_color, ms_colors, pal_name = ms_palettes[i]
    p = base_card()
    p["color"] = txt_color
    p["multi_stroke"] = True
    p["ms_layers"] = 2 if i % 2 == 0 else 3
    p["ms_step"] = 6
    p["ms_colors"] = ms_colors
    # Mostly with BG
    if i < 15:
        p["bg"] = True
        p["bg_color"] = "#2C3E50" if i % 2 == 0 else "#BDC3C7"
        p["bg_alpha"] = 180 if i % 2 == 0 else 255
    name = f"热门 - 多层发光 {i+1:02d} ({pal_name})"
    new_presets[name] = p

# Category 4: Dual-line Styling (首行独立排版)
# 20 combos
dual_palettes = [
    # Top Text, Top Stroke, Top BG, Bot Text, Bot Stroke, Bot BG, Top Strk Color, Bot Strk Color
    ("#FFFFFF", True, "#E74C3C", "#2C3E50", False, "#FFFFFF", "#C0392B", ""),
    ("#F1C40F", True, "#2980B9", "#FFFFFF", True, "#1A5276", "#154360", "#154360"),
    ("#FFFFFF", False, "#8E44AD", "#FFFFFF", True, "#5B2C6F", "", "#111111"),
    ("#2C3E50", False, "#F1C40F", "#FFFFFF", False, "#E74C3C", "", ""),
    ("#FFFFFF", True, "#16A085", "#117A65", False, "#E8FDFD", "#0E6251", ""),
    ("#FFFFFF", False, "#34495E", "#FDF0F5", True, "#E83A59", "", "#B00020"),
    ("#E83A59", False, "#FDF0F5", "#FFFFFF", False, "#34495E", "", ""),
    ("#FFFFFF", True, "#D35400", "#FFF9C4", True, "#A04000", "#A04000", "#7E3300"),
    ("#27AE60", False, "#E8FDE8", "#FFFFFF", True, "#145A32", "", "#0E3A20"),
    ("#FFFFFF", True, "#F39C12", "#2C3E50", False, "#FDF5E8", "#D68910", ""),
] * 2

for i in range(20):
    t_c, t_s, t_bg, b_c, b_s, b_bg, t_sc, b_sc = dual_palettes[i]
    p = base_card()
    p["sub_enabled"] = True
    p["size"] = 72
    p["sub_size"] = 60
    
    p["color"] = t_c
    p["stroke"] = t_s
    if t_s:
        p["stroke_color"] = t_sc
        p["stroke_width"] = 8
        
    p["sub_color"] = b_c
    p["sub_stroke"] = b_s
    if b_s:
        p["sub_stroke_color"] = b_sc
        p["sub_stroke_width"] = 8
        
    p["bg"] = True
    p["bg_shape"] = "rect"
    p["split"] = "vertical"
    p["bg_color"] = t_bg
    p["bg_alpha"] = 255
    p["split_color2"] = b_bg
    p["split_alpha2"] = 255
    
    name = f"热门 - 双排版高阶 {i+1:02d}"
    new_presets[name] = p

# Merge and Write
DEFAULT_PRESETS.update(new_presets)

with codecs.open('UI/default_presets.py', 'w', 'utf-8') as f:
    f.write("# -*- coding: utf-8 -*-\n")
    f.write("DEFAULT_PRESETS = \\\n")
    f.write(pprint.pformat(DEFAULT_PRESETS, width=120, sort_dicts=True))
    f.write("\n")

print("Generated 80 new presets and updated UI/default_presets.py")
