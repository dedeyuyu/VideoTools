import re
import codecs

path = r"d:\Antigravity\VideoTools\UI\ui_duet_video.py"
with codecs.open(path, 'r', 'utf-8') as f:
    code = f.read()

# 1. Move line_spacing
old_text_group = """        self._add(g, "hl_color", "color", "高亮颜色")"""
new_text_group = """        self._add(g, "hl_color", "color", "高亮颜色")
        self._add(g, "line_spacing", "dspin", "行间距", rng=(-100, 300), step=1)"""
code = code.replace(old_text_group, new_text_group)

old_layout_group = """        g = self._group("📐 排版与定位")
        self._add(g, "snap_split", "check", "以分割线为中心（Y 吸附分割线，X 居中）")
        self._add(g, "pos_x", "spin", "自定义中心 X", rng=(-2000, 4000))
        self._add(g, "pos_y", "spin", "自定义中心 Y", rng=(-2000, 4000))
        self._add(g, "width", "spin", "最大段落宽度", rng=(100, 3000))
        self._add(g, "wrap", "check", "超长自动换行")
        self._add(g, "line_spacing", "spin", "行距", rng=(-100, 300))
        self._add(g, "rand_height", "spin", "随机高度范围(%)", rng=(0, 100))
        self._add(g, "rotation", "spin", "整体旋转度数", rng=(-180, 180))
        self._add(g, "show_range", "check", "显示辅助排版边框")"""

new_layout_group = """        g = self._group("📐 排版与定位")
        self._add(g, "snap_split", "check", "以分割线为中心（Y 吸附分割线，X 居中）")
        self._add(g, "pos_x", "spin", "自定义中心 X", rng=(-2000, 4000))
        self._add(g, "pos_y", "spin", "自定义中心 Y", rng=(-2000, 4000))
        self._add(g, "width", "spin", "最大段落宽度", rng=(100, 3000))
        self._add(g, "wrap", "check", "超长自动换行")
        self._add(g, "rand_height", "spin", "随机高度范围(%)", rng=(0, 100))
        self._add(g, "rotation", "spin", "整体旋转度数", rng=(-180, 180))
        self._add(g, "show_range", "check", "显示辅助排版边框")"""
code = code.replace(old_layout_group, new_layout_group)


# 2. Add bg_shape combo
old_bg_group = """        g = self._group("🟫 字幕背景与装饰")
        self._add(g, "bg", "check", "启用字幕底框")
        self._add(g, "bg_fit", "check", "贴合行宽")
        self._add(g, "bg_color", "color", "底框颜色")"""

new_bg_group = """        g = self._group("🟫 字幕背景与装饰")
        self._add(g, "bg", "check", "启用字幕底框")
        self._add(g, "bg_fit", "check", "贴合行宽")
        self._add(g, "bg_shape", "combo", "底框形状", items=[
            ("rect", "直角长方形"),
            ("rounded", "圆角长方形"),
            ("pill", "胶囊形状"),
            ("notch", "切角多边形"),
            ("ribbon", "丝带/燕尾"),
            ("bow", "向内凹多边形"),
            ("wave", "底部波浪"),
            ("torn", "撕裂边缘"),
        ])
        self._add(g, "bg_color", "color", "底框颜色")"""
code = code.replace(old_bg_group, new_bg_group)

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(code)

print("Patched ui_duet_video.py for shape and line spacing")
