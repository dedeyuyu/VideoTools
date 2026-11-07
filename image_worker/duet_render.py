"""
duet_render.py — 合拍视频：画面合成预览 & 字幕卡片 / 水印绘制（基于 QPainter）

预览与最终导出共用同一套绘制逻辑：
  * 预览：compose_preview() 把模板 + 两路视频帧 + 卡片/水印图层合成到 1080x1920 画布
  * 导出：render_card_layer() / render_watermark_layer() 生成透明 PNG，交给 ffmpeg overlay
"""
import os
import re
import random

from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import (QPainterPathStroker, QImage, QPainter, QColor, QFont, QFontMetricsF, QPainterPath,
                         QPen, QBrush, QPixmap, QIcon, QFontDatabase, QLinearGradient, QPolygonF,
                         QTransform)

from image_worker.duet_worker import (CANVAS_W, CANVAS_H, REF_W, REF_H, get_canvas_size, box_layout, get_install_root,
                                     tpl_cells, ordered_cells, cell_rect_px, place_in_cell, cell_rotation, SRC_LABELS,
                                     tpl_bg_color, tpl_divider, divider_rects, divider_lines,
                                     cell_poly_px, cell_label_rect_px, tpl_diag_ys)

PERSON_COLOR = QColor("#90CDF4")   # 浅蓝：人物
VIRAL_COLOR = QColor("#FBB6CE")    # 浅粉：主视频
SRC_COLORS = {
    "viral":    QColor("#FBB6CE"),   # 浅粉：主视频
    "person":   QColor("#90CDF4"),   # 浅蓝：人物1
    "person2":  QColor("#9AE6B4"),   # 浅绿：人物2
    "person3":  QColor("#FBD38D"),   # 浅橙：人物3
    "person4":  QColor("#D6BCFA"),   # 浅紫：人物4
    "person5":  QColor("#81E6D9"),   # 浅青：人物5
    "person6":  QColor("#FEB2B2"),   # 珊瑚粉：人物6
    "person7":  QColor("#FAF089"),   # 浅黄：人物7
    "person8":  QColor("#B2F5EA"),   # 薄荷绿：人物8
    "person9":  QColor("#E9D8FD"),   # 薰衣草：人物9
    "person10": QColor("#FBB6CE"),   # 樱花粉：人物10
    "person11": QColor("#C6F6D5"),   # 嫩芽绿：人物11
    "person12": QColor("#FEEBC8"),   # 杏仁黄：人物12
}

_loaded_fonts = {}
_bundled_loaded = False


def load_font_file(path: str) -> str:
    """注册本地字体文件，返回字体族名（失败返回空串）。"""
    if not path or not os.path.isfile(path):
        return ""
    if path in _loaded_fonts:
        return _loaded_fonts[path]
    fid = QFontDatabase.addApplicationFont(path)
    fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
    fam = fams[0] if fams else ""
    _loaded_fonts[path] = fam
    return fam


def load_bundled_fonts():
    """加载软件自带的预设字体（duet_fonts 目录以及 videokit 目录）。"""
    global _bundled_loaded
    if _bundled_loaded:
        return
    _bundled_loaded = True
    
    dirs_to_check = [
        os.path.join(get_install_root(), "duet_fonts"),
        r"C:\Users\DYcomputer\AppData\Local\Programs\videokit\resources\assets\fonts"
    ]
    
    for d in dirs_to_check:
        if os.path.isdir(d):
            for root, dirs, files in os.walk(d):
                for fn in files:
                    if fn.lower().endswith((".ttf", ".otf", ".ttc")):
                        load_font_file(os.path.join(root, fn))


# ── 卡片默认参数 ──────────────────────────────────────────────────────────────

def default_card(kind: str = "title") -> dict:
    return {
        "enabled": True,
        "mode": "text",                 # text / image
        "time": 8.0 if kind == "title" else 30.0,  # 标题=结束时间；电话=开始时间
        # 文本基础
        "font_family": "Microsoft YaHei", "font_file": "",
        "size": 72, "bold": True, "italic": False, "weight": 700,
        "auto_size": False, "max_lines": 3, "max_size": 96, "min_size": 24,
        "letter_spacing": 0, "rtl": False, "uppercase": False,
        "color": "#FFFFFF", "hl_color": "#FFD400",
        # 自动着色
        "keywords": "", "hl_numbers": False, "hl_english": False,
        # 描边与特效
        "stroke": True, "stroke_color": "#000000", "stroke_width": 6,
        "shadow": False, "shadow_color": "#000000", "shadow_blur": 6, "shadow_x": 4, "shadow_y": 4,
        "shadow_alpha": 100,
        "multi_stroke": False, "ms_layers": 2, "ms_step": 6, "ms_feather": 0,
        "ms_colors": "#FFFFFF,#E53E3E",
        "text_texture": "none",         # none / crackle / grunge_h / grunge_dots
        # 背景
        "bg": False, "bg_fit": False, "bg_shape": "rounded", "bg_color": "#000000", "bg_alpha": 170,
        "bg_radius": 18, "bg_pad_x": 30, "bg_pad_y": 16,
        "bg_border_w": 0, "bg_border_color": "#FFFFFF",
        "bg_bottom_w": 0, "bg_bottom_color": "#D90429",
        "bg_shadow": False, "bg_shadow_color": "#000000", "bg_shadow_x": 0, "bg_shadow_y": 8,
        "bg_shadow_blur": 16, "bg_shadow_alpha": 30,
        "bg_texture": "none",           # none / speckles / grunge_brush / crumpled
        # 结构（引导语 / 副文本 / 双色拼接 / 图标）
        "lead_text": "", "lead_color": "#FFFFFF", "lead_scale": 50, "lead_inline": False,
        "sub_text": "", "sub_color": "#FFFFFF", "sub_scale": 40,
        "sub_enabled": False, "sub_size": 40, "sub_hl_color": "#FFD400", "sub_stroke": True, "sub_stroke_color": "#000000", "sub_stroke_width": 6,
        "sub_text_texture": "none", "sub_bg_texture": "none",
        "split": "none", "split_color2": "#FFFFFF", "split_alpha2": 255,
        "icon": "none",
        "underline": False, "underline_color": "#25D366", "underline_w": 4,
        # 排版
        "pos_x": 540, "pos_y": 960, "width": 960, "wrap": True,
        "line_spacing": 8, "rand_height": 0, "rotation": 0,
        "show_range": False, "snap_split": True,
        # 图片卡片
        "image_path": "", "image_scale": 100,
    }


def default_watermark() -> dict:
    return {
        "enabled": True, "type": "text",            # text / image
        "text": "Watermark", "image_path": "",
        "position": "br",                           # tl / tr / bl / br / bc(底部居中)
        "ox": 0, "oy": 0,
        "scale": 30, "opacity": 100, "flip_h": False, "flip_v": False,
        "font_family": "Microsoft YaHei", "font_size": 32, "color": "#FFFFFF", "text_opacity": 100,
        "bg_color": "#000000", "bg_opacity": 50,
    }


# ── 模板缩略图 ────────────────────────────────────────────────────────────────

def template_icon(tpl: dict, w: int = 54, h: int = 96) -> QIcon:
    pm = QPixmap(w, h)
    pm.fill(QColor(tpl_bg_color(tpl)) if tpl.get("bg_color") else QColor("#2D3748"))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    canv_w, canv_h = get_canvas_size(tpl)
    sx, sy = w / canv_w, h / canv_h
    f = QFont("Microsoft YaHei")
    f.setBold(True)
    for num, cell in ordered_cells(tpl):
        poly_pts = cell_poly_px(cell, tpl)
        col = SRC_COLORS.get(cell.get("src"), QColor("#A0AEC0"))
        if poly_pts:
            poly = QPolygonF([QPointF(px * sx, py * sy) for px, py in poly_pts])
            p.setPen(QPen(QColor("#FFFFFF"), 1.2))
            p.setBrush(col)
            p.drawPolygon(poly)
            lx, ly, lw, lh = cell_label_rect_px(cell, tpl)
            r = QRectF(lx * sx, ly * sy, lw * sx, lh * sy)
        else:
            x, y, cw, ch = cell_rect_px(cell, tpl)
            r = QRectF(x * sx, y * sy, cw * sx, ch * sy)
            p.fillRect(r, col)
            p.setPen(QPen(QColor("#FFFFFF"), 1.5 if cell.get("pip") else 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(r.adjusted(0.5, 0.5, -0.5, -0.5))
        f.setPixelSize(max(6, int(min(r.width(), r.height()) * 0.55)))
        p.setFont(f)
        p.setPen(QColor("#1A202C"))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, str(num + 1))
    p.end()
    return QIcon(pm)


# ── 画面合成（预览用） ─────────────────────────────────────────────────────────

def _draw_cell(p: QPainter, num: int, cell: dict, img, adj: dict, tpl: dict = None):
    x, y, w, h = cell_rect_px(cell, tpl)
    poly_pts = cell_poly_px(cell, tpl)
    b = int(cell.get("border", 0) or 0)
    if b > 0 and not poly_pts:
        p.fillRect(x - b, y - b, w + 2 * b, h + 2 * b, QColor("#FFFFFF"))
    p.save()
    if poly_pts:
        clip_path = QPainterPath()
        clip_path.addPolygon(QPolygonF([QPointF(px, py) for px, py in poly_pts]))
        clip_path.closeSubpath()
        p.setClipPath(clip_path)
    else:
        p.setClipRect(x, y, w, h)
    src = cell.get("src", "")
    if img is None or img.isNull():
        p.fillRect(x, y, w, h, SRC_COLORS.get(src, QColor("#A0AEC0")))
        lx, ly, lw, lh = cell_label_rect_px(cell, tpl) if poly_pts else (x, y, w, h)
        f = QFont("Microsoft YaHei")
        f.setBold(True)
        f.setPixelSize(max(18, min(56, int(min(w, h) * 0.11))))
        p.setFont(f)
        p.setPen(QColor("#1A202C"))
        p.drawText(QRectF(lx, ly, lw, lh), Qt.AlignmentFlag.AlignCenter,
                   f"{num + 1}\n{SRC_LABELS.get(src, src)}")
    else:
        p.fillRect(x, y, w, h, QColor("#000000"))
        rot = cell_rotation(cell, adj)
        if rot:
            img = img.transformed(QTransform().rotate(float(rot)))
        sw, sh, ox, oy = place_in_cell(img.width(), img.height(), w, h, cell, adj, tpl, already_rotated=True)
        p.drawImage(QRectF(x + ox, y + oy, sw, sh), img)
    p.restore()


def _paint_dividers(p: QPainter, div_rects: list, div_lines: list, div_w: int, div_color: QColor):
    for x, y, w, h in div_rects:
        p.fillRect(QRectF(x, y, w, h), div_color)
    if div_lines and div_w > 0:
        pen = QPen(div_color, float(div_w), Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap, Qt.PenJoinStyle.MiterJoin)
        p.save()
        p.setPen(pen)
        for x1, y1, x2, y2 in div_lines:
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
        p.restore()


def compose_preview(tpl: dict, frames=None, viral_img=None, adj: dict = None,
                    overlays: list = None, show_split: bool = True, selected: int = -1,
                    scale: float = 1.0) -> QImage:
    """frames: {来源: QImage}。兼容旧调用 compose_preview(tpl, person_img, viral_img, ...)。
    scale < 1 时输出缩小的画面（播放预览用，速度更快）；尺寸与画布同比例的 overlay 会直接贴图。"""
    if not isinstance(frames, dict):
        frames = {"person": frames, "viral": viral_img}
    adj = adj or {}
    canv_w, canv_h = get_canvas_size(tpl)
    cw, ch = max(2, int(round(canv_w * scale))), max(2, int(round(canv_h * scale)))
    canvas = QImage(cw, ch, QImage.Format.Format_ARGB32_Premultiplied)
    canvas.fill(QColor(tpl_bg_color(tpl)))
    p = QPainter(canvas)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    if abs(scale - 1.0) > 1e-6:
        p.scale(cw / canv_w, ch / canv_h)
    div_rects = divider_rects(tpl)
    div_lines = divider_lines(tpl)
    div_w, div_col_hex = tpl_divider(tpl)
    div_color = QColor(div_col_hex)
    div_done = (not div_rects) and (not div_lines)
    for num, cell in ordered_cells(tpl):
        if not div_done and cell.get("pip"):
            _paint_dividers(p, div_rects, div_lines, div_w, div_color)
            div_done = True
        _draw_cell(p, num, cell, frames.get(cell.get("src")), adj.get(cell.get("src")), tpl)
    if not div_done:
        _paint_dividers(p, div_rects, div_lines, div_w, div_color)
    for ov in overlays or []:
        if ov is not None and not ov.isNull():
            if ov.width() == cw and ov.height() == ch and (cw, ch) != (canv_w, canv_h):
                p.save()
                p.resetTransform()
                p.drawImage(0, 0, ov)
                p.restore()
            elif (ov.width(), ov.height()) == (canv_w, canv_h):
                p.drawImage(0, 0, ov)
            else:
                p.drawImage(QRectF(0, 0, canv_w, canv_h), ov)
    if show_split:
        pen = QPen(QColor("#F6E05E"), 4, Qt.PenStyle.DashLine)
        p.setPen(pen)
        diag = tpl_diag_ys(tpl_cells(tpl))
        if diag is not None:
            p.drawLine(QPointF(0, diag[0] * canv_h), QPointF(canv_w, diag[1] * canv_h))
        else:
            sy = box_layout(tpl)["split_y"]
            p.drawLine(0, sy, canv_w, sy)
    if 0 <= selected < len(tpl_cells(tpl)):
        sel_cell = tpl_cells(tpl)[selected]
        poly_pts = cell_poly_px(sel_cell, tpl)
        p.setPen(QPen(QColor("#00E5FF"), 8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        if poly_pts:
            p.drawPolygon(QPolygonF([QPointF(px, py) for px, py in poly_pts]))
        else:
            x, y, w, h = cell_rect_px(sel_cell, tpl)
            p.drawRect(x + 4, y + 4, w - 8, h - 8)
    p.end()
    return canvas


# ── 通用：模糊阴影 ────────────────────────────────────────────────────────────

def _draw_blurred(p: QPainter, draw_fn, bounds: QRectF, blur: float, dx: float, dy: float,
                  opacity: float):
    """draw_fn(painter) 在局部坐标绘制形状；先渲染到离屏图再缩放模糊，然后按偏移绘制。"""
    blur = max(0.0, float(blur))
    m = int(blur * 2 + 4)
    r = bounds.adjusted(-m, -m, m, m)
    w, h = max(1, int(r.width())), max(1, int(r.height()))
    img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    q = QPainter(img)
    q.setRenderHint(QPainter.RenderHint.Antialiasing)
    q.translate(-r.left(), -r.top())
    draw_fn(q)
    q.end()
    if blur >= 1:
        f = max(1.0, blur / 2.5)
        for _ in range(2):
            sw, sh = max(1, int(w / f)), max(1, int(h / f))
            img = img.scaled(sw, sh, Qt.AspectRatioMode.IgnoreAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
            img = img.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
    p.save()
    p.setOpacity(max(0.0, min(1.0, opacity)))
    p.drawImage(QPointF(r.left() + dx, r.top() + dy), img)
    p.restore()


# ── 字幕卡片绘制 ──────────────────────────────────────────────────────────────

def _make_font(cfg: dict, scale: float = 1.0) -> QFont:
    load_bundled_fonts()
    fam = cfg.get("font_family") or "Microsoft YaHei"
    if cfg.get("font_file"):
        f2 = load_font_file(cfg["font_file"])
        if f2:
            fam = f2
    f = QFont(fam)
    f.setPixelSize(max(6, int(float(cfg.get("size", 72)) * scale)))
    w = int(cfg.get("weight", 400))
    if cfg.get("bold"):
        w = max(w, 700)
    try:
        f.setWeight(QFont.Weight(w))
    except Exception:
        f.setBold(w >= 600)
    f.setItalic(bool(cfg.get("italic")))
    ls = float(cfg.get("letter_spacing", 0))
    if ls:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, ls * scale)
    return f


def _hl_mask(text: str, cfg: dict) -> list:
    hl = [False] * len(text)
    kws = [k.strip() for k in re.split(r"[,，;；\n]", cfg.get("keywords", "")) if k.strip()]
    for kw in kws:
        for m in re.finditer(re.escape(kw), text, flags=re.I):
            for i in range(m.start(), m.end()):
                hl[i] = True
    if cfg.get("hl_numbers"):
        for m in re.finditer(r"\d+(?:[.,:]\d+)*%?", text):
            for i in range(m.start(), m.end()):
                hl[i] = True
    if cfg.get("hl_english"):
        for m in re.finditer(r"[A-Za-zÀ-ÿ]+(?:['’][A-Za-zÀ-ÿ]+)*", text):
            for i in range(m.start(), m.end()):
                hl[i] = True
    return hl


def _wrap(text: str, fm: QFontMetricsF, max_w: float, wrap: bool) -> list:
    """返回 [(start, end)] 字符区间（相对 text）。"""
    lines = []
    pos = 0
    for para in text.split("\n"):
        start, end = pos, pos + len(para)
        if not wrap or max_w <= 0 or start == end:
            lines.append((start, end))
        else:
            i = start
            while i < end:
                j = i
                last_space = -1
                while j < end:
                    if text[j] == " ":
                        last_space = j
                    if fm.horizontalAdvance(text[i:j + 1]) > max_w and j > i:
                        break
                    j += 1
                if j < end and last_space > i and re.match(r"[\wÀ-ÿ]", text[j]):
                    j = last_space + 1
                lines.append((i, j))
                i = j
                while i < end and text[i] == " ":
                    i += 1
        pos = end + 1
    return lines


class _Line:
    """一行文字：位置在布局阶段确定。"""
    def __init__(self, text, font, color, hl_color, hl, kind):
        self.text, self.font, self.color, self.hl_color, self.hl, self.kind = text, font, color, hl_color, hl, kind
        self.fm = QFontMetricsF(font)
        self.w = self.fm.horizontalAdvance(text) if text else 0.0
        self.h = self.fm.height()
        self.x = 0.0
        self.y = 0.0     # 行顶部


def card_center(cfg: dict, split_y: int, task_index: int = 0, cw: int = None, ch: int = None) -> tuple:
    if cw is None or ch is None:
        cw, ch = get_canvas_size()
    if cfg.get("snap_split"):
        cx, cy = cw / 2.0, float(split_y)
    else:
        ref = cfg.get("pos_ref_size")
        if isinstance(ref, (list, tuple)) and len(ref) == 2 and ref[0] > 0 and ref[1] > 0:
            rw, rh_ref = float(ref[0]), float(ref[1])
        else:
            rw, rh_ref = float(REF_W), float(REF_H)
        cx = float(cfg.get("pos_x", 540)) * (cw / rw)
        cy = float(cfg.get("pos_y", 960)) * (ch / rh_ref)
    rh = float(cfg.get("rand_height", 0))
    if rh:
        rnd = random.Random(task_index * 7919 + 13)
        cy += rnd.uniform(-rh, rh) / 100.0 * ch
    return cx, cy


def render_card_layer(cfg: dict, text: str, split_y: int, task_index: int = 0,
                      draw_guides: bool = False, canvas_wh: tuple = None) -> QImage:
    cw, ch = canvas_wh if (canvas_wh and len(canvas_wh) == 2) else get_canvas_size()
    img = QImage(cw, ch, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    if not cfg.get("enabled", True):
        return img
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    cx, cy = card_center(cfg, split_y, task_index, cw, ch)
    rot = float(cfg.get("rotation", 0))
    p.translate(cx, cy)
    if rot:
        p.rotate(rot)

    if cfg.get("mode") == "image":
        _draw_image_card(p, cfg)
    else:
        _draw_text_card(p, cfg, text or "", cx, cw)

    if draw_guides and cfg.get("show_range"):
        w = float(cfg.get("width", 960))
        p.setPen(QPen(QColor("#00E5FF"), 3, Qt.PenStyle.DashLine))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(QRectF(-w / 2, -200, w, 400))
    p.end()
    return img


def _draw_image_card(p: QPainter, cfg: dict):
    path = cfg.get("image_path", "")
    if not path or not os.path.isfile(path):
        return
    im = QImage(path)
    if im.isNull():
        return
    s = float(cfg.get("image_scale", 100)) / 100.0
    w, h = im.width() * s, im.height() * s
    p.drawImage(QRectF(-w / 2, -h / 2, w, h), im)


# ---- 图标 ----

def _draw_whatsapp(p: QPainter, c: QPointF, r: float):
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#25D366"))
    p.drawEllipse(c, r, r)
    # 对话气泡
    pen = QPen(QColor("#FFFFFF"), r * 0.13, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
               Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    br = r * 0.6
    p.drawArc(QRectF(c.x() - br, c.y() - br, 2 * br, 2 * br), 250 * 16, 330 * 16)
    tail = QPolygonF([QPointF(c.x() - br * 0.55, c.y() + br * 0.8),
                      QPointF(c.x() - br * 0.95, c.y() + br * 1.05),
                      QPointF(c.x() - br * 0.85, c.y() + br * 0.55)])
    p.drawPolyline(tail)
    # 听筒
    hp = QPen(QColor("#FFFFFF"), r * 0.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    p.setPen(hp)
    hr = r * 0.26
    p.drawArc(QRectF(c.x() - hr, c.y() - hr, 2 * hr, 2 * hr), 200 * 16, 140 * 16)
    p.restore()


def _draw_arrow(p: QPainter, c: QPointF, size: float, color: QColor):
    p.save()
    pen = QPen(color, size * 0.14, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.drawLine(QPointF(c.x() - size * 0.4, c.y()), QPointF(c.x() + size * 0.35, c.y()))
    p.drawPolyline(QPolygonF([QPointF(c.x() + size * 0.05, c.y() - size * 0.3),
                              QPointF(c.x() + size * 0.38, c.y()),
                              QPointF(c.x() + size * 0.05, c.y() + size * 0.3)]))
    p.restore()


# ---- 背景形状 ----

def _brush_banner_path(rect: QRectF, seed: int = 7, feather: bool = False) -> QPainterPath:
    """水平笔刷涂抹条：上下边缘微起伏，左右两端呈现横向刷毛锯齿 / 撕裂笔触。"""
    rnd = random.Random(seed)
    pts = []
    l, r, t, b = rect.left(), rect.right(), rect.top(), rect.bottom()
    w, h = max(10.0, rect.width()), max(10.0, rect.height())
    steps_x = max(20, int(w / 22))
    teeth = max(11, int(h / 5.2))
    end_amp = min(14.0, max(7.0, h * (0.13 if feather else 0.16)))

    # 顶部边缘（左 -> 右）
    cur_dy = 0.0
    for i in range(steps_x + 1):
        u = i / steps_x
        if rnd.random() < 0.22:
            cur_dy = rnd.uniform(-1.5, 1.5)
        y = t + cur_dy + rnd.uniform(-0.5, 0.5)
        pts.append(QPointF(l + w * u, y))

    # 右侧刷毛锯齿（上 -> 下）
    for i in range(teeth):
        u0 = i / teeth
        u1 = (i + 1) / teeth
        ym = t + h * (u0 + u1) * 0.5
        taper = 0.45 + 0.55 * (1.0 - abs(2.0 * (u0 + 0.5 / teeth) - 1.0) ** 1.8)
        kind = rnd.random()
        if kind < 0.38:
            dx = rnd.uniform(0.3, 1.0) * end_amp * taper
        elif kind < 0.72:
            dx = rnd.uniform(-0.2, 0.3) * end_amp * taper
        else:
            dx = -rnd.uniform(0.25, 0.75) * end_amp * taper
        pts.append(QPointF(r + dx, t + h * u0))
        pts.append(QPointF(r + dx + rnd.uniform(-1.5, 1.5), ym))
        pts.append(QPointF(r + dx * 0.6, t + h * u1))

    # 底部边缘（右 -> 左）
    cur_dy = 0.0
    for i in range(steps_x, -1, -1):
        u = i / steps_x
        if rnd.random() < 0.22:
            cur_dy = rnd.uniform(-1.5, 1.5)
        y = b + cur_dy + rnd.uniform(-0.5, 0.5)
        pts.append(QPointF(l + w * u, y))

    # 左侧刷毛锯齿（下 -> 上）
    for i in range(teeth - 1, -1, -1):
        u0 = i / teeth
        u1 = (i + 1) / teeth
        ym = t + h * (u0 + u1) * 0.5
        taper = 0.45 + 0.55 * (1.0 - abs(2.0 * (u0 + 0.5 / teeth) - 1.0) ** 1.8)
        kind = rnd.random()
        if kind < 0.38:
            dx = rnd.uniform(0.3, 1.0) * end_amp * taper
        elif kind < 0.72:
            dx = rnd.uniform(-0.2, 0.3) * end_amp * taper
        else:
            dx = -rnd.uniform(0.25, 0.75) * end_amp * taper
        pts.append(QPointF(l - dx * 0.6, t + h * u1))
        pts.append(QPointF(l - dx + rnd.uniform(-1.5, 1.5), ym))
        pts.append(QPointF(l - dx, t + h * u0))

    path = QPainterPath()
    path.setFillRule(Qt.FillRule.WindingFill)
    path.addPolygon(QPolygonF(pts))
    path.closeSubpath()
    return path


def _shape_path(shape: str, rect: QRectF, radius: float, seed: int = 7) -> QPainterPath:
    path = QPainterPath()
    if shape == "pill":
        rr = rect.height() / 2
        path.addRoundedRect(rect, rr, rr)
    elif shape in ("rect", "banner", "gradient"):
        path.addRect(rect)
    elif shape == "brush":
        return _brush_banner_path(rect, seed=seed, feather=False)
    elif shape == "brush_feather":
        return _brush_banner_path(rect, seed=seed, feather=True)
    elif shape == "notch":
        c = min(rect.height() * 0.32, 30.0)
        path.addPolygon(QPolygonF([
            QPointF(rect.left() + c, rect.top()), QPointF(rect.right(), rect.top()),
            QPointF(rect.right(), rect.bottom() - c), QPointF(rect.right() - c, rect.bottom()),
            QPointF(rect.left(), rect.bottom()), QPointF(rect.left(), rect.top() + c),
        ]))
        path.closeSubpath()
    elif shape == "torn":
        rnd = random.Random(seed)
        pts = []
        steps = max(8, int(rect.width() / 40))
        for i in range(steps + 1):
            pts.append(QPointF(rect.left() + rect.width() * i / steps, rect.top() + rnd.uniform(-4, 4)))
        for i in range(10):
            pts.append(QPointF(rect.right() + rnd.uniform(-10, 6), rect.top() + rect.height() * (i + 0.5) / 10))
        for i in range(steps, -1, -1):
            pts.append(QPointF(rect.left() + rect.width() * i / steps, rect.bottom() + rnd.uniform(-4, 4)))
        for i in range(9, -1, -1):
            pts.append(QPointF(rect.left() + rnd.uniform(-6, 10), rect.top() + rect.height() * (i + 0.5) / 10))
        path.addPolygon(QPolygonF(pts))
        path.closeSubpath()
    elif shape == "ribbon":
        c = min(rect.height() * 0.4, 40.0)
        path.addPolygon(QPolygonF([
            QPointF(rect.left(), rect.top()), 
            QPointF(rect.right(), rect.top()),
            QPointF(rect.right() - c, rect.top() + rect.height()/2),
            QPointF(rect.right(), rect.bottom()),
            QPointF(rect.left(), rect.bottom()), 
            QPointF(rect.left() + c, rect.top() + rect.height()/2),
        ]))
        path.closeSubpath()
    elif shape == "bow":
        c = min(rect.height() * 0.2, 20.0)
        path.addPolygon(QPolygonF([
            QPointF(rect.left(), rect.top()), 
            QPointF(rect.right(), rect.top()),
            QPointF(rect.right() - c, rect.top() + rect.height()/2),
            QPointF(rect.right(), rect.bottom()),
            QPointF(rect.left(), rect.bottom()), 
            QPointF(rect.left() + c, rect.top() + rect.height()/2),
        ]))
        path.closeSubpath()
    elif shape == "wave":
        c = min(rect.height() * 0.2, 20.0)
        path.moveTo(rect.topLeft())
        path.lineTo(rect.topRight())
        path.lineTo(rect.bottomRight() - QPointF(0, c))
        path.quadTo(QPointF(rect.center().x() + rect.width()*0.25, rect.bottom()),
                    QPointF(rect.center().x(), rect.bottom() - c/2))
        path.quadTo(QPointF(rect.center().x() - rect.width()*0.25, rect.bottom() - c),
                    rect.bottomLeft() - QPointF(0, c))
        path.closeSubpath()
    else:   # rounded / outline
        path.addRoundedRect(rect, radius, radius)
    return path


def _draw_bg_texture(p: QPainter, rect: QRectF, clip_path: QPainterPath, tex: str,
                     base_color: QColor, seed: int = 11):
    """在底框内绘制做旧纹理：speckles(斑驳噪点+笔刷边线) / grunge_brush(干笔刷飞白泼墨) / crumpled(折纸褶皱+暗角)。"""
    if not tex or tex == "none":
        return
    rnd = random.Random(seed)
    l, r, t, b = rect.left(), rect.right(), rect.top(), rect.bottom()
    w, h = max(10.0, rect.width()), max(10.0, rect.height())
    is_light = base_color.lightness() > 145

    if tex == "speckles":
        p.save()
        p.setClipPath(clip_path)
        # 上下边缘笔刷刻痕细线（如图1/图3蓝色底条上下边沿的断续笔触沟槽线）
        groove_dark = QColor(0, 0, 0, 125)
        groove_light = QColor(255, 255, 255, 70)
        for edge_y, sign in ((t + 4.5, 1.0), (b - 4.5, -1.0)):
            x = l - 10
            while x < r + 10:
                seg = rnd.uniform(28, 95)
                if rnd.random() < 0.82:
                    p.setPen(QPen(groove_dark, rnd.uniform(1.6, 2.6), Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
                    p.drawLine(QPointF(x, edge_y + rnd.uniform(-0.8, 0.8)),
                               QPointF(x + seg, edge_y + rnd.uniform(-0.8, 0.8)))
                    if rnd.random() < 0.55:
                        p.setPen(QPen(groove_light, 1.1))
                        p.drawLine(QPointF(x + 4, edge_y + sign * 2.2),
                                   QPointF(x + seg * 0.7, edge_y + sign * 2.2))
                x += seg + rnd.uniform(6, 22)

        # 斑驳白点与细微划痕
        n_dots = max(60, int(w * h / 520))
        for _ in range(n_dots):
            px = rnd.uniform(l - 12, r + 12)
            py = rnd.uniform(t, b)
            alpha = rnd.randint(55, 145)
            col = QColor(220, 238, 255, alpha) if not is_light else QColor(20, 20, 20, alpha)
            if rnd.random() < 0.35:
                # 细小斜划痕
                ang_dx = rnd.uniform(-5.5, 5.5)
                ang_dy = rnd.uniform(-5.5, 5.5)
                p.setPen(QPen(col, rnd.uniform(1.0, 1.8)))
                p.drawLine(QPointF(px, py), QPointF(px + ang_dx, py + ang_dy))
            else:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(col)
                sz = rnd.uniform(1.2, 3.2)
                p.drawEllipse(QPointF(px, py), sz, sz * rnd.uniform(0.6, 1.3))
        p.restore()

    elif tex == "grunge_brush":
        # 外侧飞白毛刺（不裁剪，让左右两端有干笔刷飞丝与飞沫）
        p.save()
        for side_x, dir_sign in ((l, -1.0), (r, 1.0)):
            for _ in range(32):
                sy = rnd.uniform(t + 2, b - 2)
                len_out = rnd.uniform(4, 18)
                len_in = rnd.uniform(6, 24)
                c_out = QColor(base_color.red(), base_color.green(), base_color.blue(), rnd.randint(110, 235))
                p.setPen(QPen(c_out, rnd.uniform(1.1, 2.4), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                p.drawLine(QPointF(side_x - dir_sign * len_in, sy),
                           QPointF(side_x + dir_sign * len_out, sy + rnd.uniform(-0.7, 0.7)))
                if rnd.random() < 0.45:
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(c_out)
                    r_dot = rnd.uniform(1.0, 2.2)
                    p.drawEllipse(QPointF(side_x + dir_sign * (len_out + rnd.uniform(2, 9)),
                                          sy + rnd.uniform(-1.5, 1.5)), r_dot, r_dot)
        p.restore()

        p.save()
        p.setClipPath(clip_path)
        if is_light:
            # 浅色底（如图3白底）：仅在左右两端留白区与上下极窄边缘绘制干笔刷飞白刮痕，保持中间文字区洁白清晰
            edge_reach = min(34.0, w * 0.065)
            for side_x, dir_in in ((l - 10, 1.0), (r + 10, -1.0)):
                for _ in range(55):
                    sy = rnd.uniform(t, b)
                    reach = rnd.uniform(6, edge_reach)
                    x0 = side_x + dir_in * rnd.uniform(0, 8)
                    x1 = x0 + dir_in * reach
                    ink = QColor(14, 14, 14, rnd.randint(95, 215))
                    p.setPen(QPen(ink, rnd.uniform(0.9, 2.1), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                    p.drawLine(QPointF(x0, sy), QPointF(x1, sy + rnd.uniform(-0.6, 0.6)))
            # 上下边缘极窄干刷斑驳（不侵入中间字身）
            for edge_y, dir_in in ((t, 1.0), (b, -1.0)):
                for _ in range(70):
                    sx = rnd.uniform(l, r)
                    sy = edge_y + dir_in * rnd.uniform(0.3, 4.8)
                    seg = rnd.uniform(5, 28)
                    ink = QColor(15, 15, 15, rnd.randint(80, 195))
                    p.setPen(QPen(ink, rnd.uniform(0.8, 1.8)))
                    p.drawLine(QPointF(sx, sy), QPointF(sx + seg, sy + rnd.uniform(-0.5, 0.5)))
            # 边缘细碎泼墨颗粒
            for _ in range(130):
                dx = rnd.uniform(l, r)
                dy = rnd.uniform(t, b)
                in_lr = (dx - l) < edge_reach * 1.15 or (r - dx) < edge_reach * 1.15
                in_tb = (dy - t) < 6.5 or (b - dy) < 6.5
                if not (in_lr or in_tb) and rnd.random() < 0.88:
                    continue
                ink = QColor(15, 15, 15, rnd.randint(80, 195))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(ink)
                sz = rnd.uniform(0.9, 2.2)
                p.drawEllipse(QPointF(dx, dy), sz * rnd.uniform(0.8, 1.8), sz)
        else:
            # 深色底（如图2黑底）：细腻横向干笔刷拉丝纹理 + 上下边沿微斑驳
            for _ in range(75):
                sx = rnd.uniform(l - 10, r - 20)
                sy = rnd.uniform(t + 2, b - 2)
                seg = rnd.uniform(25, 120)
                col = QColor(255, 255, 255, rnd.randint(10, 28))
                p.setPen(QPen(col, rnd.uniform(0.8, 1.6)))
                p.drawLine(QPointF(sx, sy), QPointF(min(r + 10, sx + seg), sy + rnd.uniform(-0.5, 0.5)))
            for edge_y in (t + 3.0, b - 3.0):
                x = l
                while x < r:
                    seg = rnd.uniform(20, 65)
                    p.setPen(QPen(QColor(255, 255, 255, rnd.randint(20, 48)), rnd.uniform(0.9, 1.5)))
                    p.drawLine(QPointF(x, edge_y), QPointF(x + seg, edge_y + rnd.uniform(-0.5, 0.5)))
                    x += seg + rnd.uniform(8, 24)
        p.restore()

    elif tex == "crumpled":
        # 如图2下排冰蓝底：柔和折纸多边形明暗褶皱 + 左右边缘柔和暗角羽化 + 顶部投影
        p.save()
        p.setClipPath(clip_path)
        cols = max(14, int(w / 42))
        rows = 4
        cw, rh = w / cols, h / rows
        grid = []
        for r_i in range(rows + 1):
            row_pts = []
            for c_i in range(cols + 1):
                jx = rnd.uniform(-cw * 0.26, cw * 0.26) if 0 < c_i < cols else 0.0
                jy = rnd.uniform(-rh * 0.26, rh * 0.26) if 0 < r_i < rows else 0.0
                row_pts.append(QPointF(l + c_i * cw + jx, t + r_i * rh + jy))
            grid.append(row_pts)

        p.setPen(Qt.PenStyle.NoPen)
        for r_i in range(rows):
            for c_i in range(cols):
                p00, p10 = grid[r_i][c_i], grid[r_i][c_i + 1]
                p01, p11 = grid[r_i + 1][c_i], grid[r_i + 1][c_i + 1]
                cx_norm = (c_i + 0.5) / cols
                edge_fade = min(1.0, min(cx_norm, 1.0 - cx_norm) / 0.16) ** 1.4
                for tri in ((p00, p10, p11), (p00, p11, p01)):
                    shade = rnd.uniform(-1.0, 1.0)
                    if shade >= 0:
                        fc = QColor(255, 255, 255, int(shade * 26 * edge_fade))
                    else:
                        fc = QColor(0, 18, 40, int(-shade * 30 * edge_fade))
                    p.setBrush(fc)
                    p.drawPolygon(QPolygonF(list(tri)))

        # 顶部交界阴影
        g_top = QLinearGradient(QPointF(0, t), QPointF(0, t + min(14.0, h * 0.2)))
        g_top.setColorAt(0.0, QColor(0, 0, 0, 95))
        g_top.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(QRectF(l + w * 0.08, t, w * 0.84, min(14.0, h * 0.2)), QBrush(g_top))
        p.restore()


def _draw_text_texture(p: QPainter, path: QPainterPath, tex: str, text_color: str, seed: int = 23):
    """在文字笔画内部绘制做旧纹理：crackle(斜向裂纹刮痕) / grunge_h(横向干笔刷斑驳) / grunge_dots(复古颗粒)。"""
    if not tex or tex == "none" or path.isEmpty():
        return
    rnd = random.Random(seed)
    b = path.boundingRect()
    l, r, t, bot = b.left(), b.right(), b.top(), b.bottom()
    w, h = max(10.0, b.width()), max(10.0, b.height())
    tc = QColor(text_color or "#FFFFFF")
    is_light_text = tc.lightness() > 125

    p.save()
    p.setClipPath(path)

    if tex == "crackle":
        # 如图1/图3白字内部：纤细锐利的深色斜向裂纹/分叉细刮痕 + 微小剥落点（保持白字主体干净醒目）
        crack_col = QColor(10, 18, 28, 175) if is_light_text else QColor(255, 255, 255, 175)
        n_cracks = max(15, int(w / 24))
        for i in range(n_cracks):
            cx = l + (i + rnd.uniform(0.15, 0.85)) * (w / n_cracks)
            cy = rnd.uniform(t + h * 0.12, bot - h * 0.12)
            dir_x = rnd.choice((-1.0, 1.0)) * rnd.uniform(0.55, 0.9)
            dir_y = rnd.choice((-1.0, 1.0)) * rnd.uniform(0.75, 1.1)
            segs = rnd.randint(2, 4)
            pts = [QPointF(cx, cy)]
            px_cur, py_cur = cx, cy
            for _ in range(segs):
                step = rnd.uniform(5.5, 11.5)
                px_cur += dir_x * step + rnd.uniform(-1.8, 1.8)
                py_cur += dir_y * step + rnd.uniform(-1.8, 1.8)
                pts.append(QPointF(px_cur, py_cur))
            pen = QPen(crack_col, rnd.uniform(1.0, 1.65), Qt.PenStyle.SolidLine,
                       Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.drawPolyline(QPolygonF(pts))
            if len(pts) >= 3 and rnd.random() < 0.5:
                bp = pts[1]
                bx = bp.x() - dir_x * rnd.uniform(4.5, 9.5) + rnd.uniform(-2.5, 2.5)
                by = bp.y() + dir_y * rnd.uniform(4.5, 9.5) + rnd.uniform(-2.5, 2.5)
                p.setPen(QPen(crack_col, rnd.uniform(0.8, 1.25), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                p.drawLine(bp, QPointF(bx, by))

        n_chips = max(45, int(w * h / 650))
        p.setPen(Qt.PenStyle.NoPen)
        for _ in range(n_chips):
            p.setBrush(crack_col)
            rx = rnd.uniform(l, r)
            ry = rnd.uniform(t, bot)
            sz = rnd.uniform(0.8, 1.8)
            p.drawEllipse(QPointF(rx, ry), sz, sz * rnd.uniform(0.6, 1.4))

    elif tex == "grunge_h":
        # 如图2首行白字 / 图3首行黑字：适度细腻的横向干笔刷刮擦飞白条纹与斑驳颗粒
        n_streaks = max(55, int(w * h / 460))
        for _ in range(n_streaks):
            sx = rnd.uniform(l - 6, r)
            sy = rnd.uniform(t, bot)
            slen = rnd.uniform(5.0, 24.0)
            alpha = rnd.randint(95, 175) if not is_light_text else rnd.randint(80, 150)
            scol = QColor(255, 255, 255, alpha) if not is_light_text else QColor(18, 18, 18, alpha)
            p.setPen(QPen(scol, rnd.uniform(0.8, 1.5), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(sx, sy), QPointF(sx + slen, sy + rnd.uniform(-0.5, 0.5)))
        n_dots = max(75, int(w * h / 380))
        p.setPen(Qt.PenStyle.NoPen)
        for _ in range(n_dots):
            alpha = rnd.randint(90, 175) if not is_light_text else rnd.randint(80, 150)
            scol = QColor(255, 255, 255, alpha) if not is_light_text else QColor(18, 18, 18, alpha)
            p.setBrush(scol)
            rx, ry = rnd.uniform(l, r), rnd.uniform(t, bot)
            sz = rnd.uniform(0.8, 1.8)
            p.drawEllipse(QPointF(rx, ry), sz * rnd.uniform(1.0, 2.0), sz)

    elif tex == "grunge_dots":
        n_dots = max(90, int(w * h / 360))
        p.setPen(Qt.PenStyle.NoPen)
        for _ in range(n_dots):
            alpha = rnd.randint(95, 185)
            scol = QColor(15, 15, 15, alpha) if is_light_text else QColor(255, 255, 255, alpha)
            p.setBrush(scol)
            rx, ry = rnd.uniform(l, r), rnd.uniform(t, bot)
            sz = rnd.uniform(0.9, 2.2)
            p.drawEllipse(QPointF(rx, ry), sz, sz * rnd.uniform(0.7, 1.4))

    p.restore()


def _alpha_color(hexc: str, alpha: int) -> QColor:
    c = QColor(hexc)
    c.setAlpha(max(0, min(255, int(alpha))))
    return c


def _draw_text_card(p: QPainter, cfg: dict, text: str, cx: float, canv_w: int = None):
    if canv_w is None:
        canv_w = get_canvas_size()[0]
    text = text.replace("\r", "")
    upper = bool(cfg.get("uppercase"))
    lead = (cfg.get("lead_text") or "").replace("\r", "")
    sub = (cfg.get("sub_text") or "").replace("\r", "")
    if upper:
        text, lead, sub = text.upper(), lead.upper(), sub.upper()
    if not text.strip() and not lead.strip():
        return

    split = cfg.get("split", "none")
    icon = cfg.get("icon", "none")
    lead_inline = bool(cfg.get("lead_inline")) and split == "none"
    main_font = _make_font(cfg)
    lead_font = _make_font(cfg, float(cfg.get("lead_scale", 50)) / 100.0)
    sub_font = _make_font(cfg, float(cfg.get("sub_scale", 40)) / 100.0)
    fm_main = QFontMetricsF(main_font)
    icon_r = fm_main.height() * 0.48 if icon != "none" else 0.0
    gap = fm_main.height() * 0.25
    ls = float(cfg.get("line_spacing", 0))
    max_w = float(cfg.get("width", 960))
    col, hl_col = cfg.get("color", "#FFFFFF"), cfg.get("hl_color", "#FFD400")

    sub_enabled = bool(cfg.get("sub_enabled"))
    if sub_enabled:
        sub_font_cfg = dict(cfg)
        sub_font_cfg["size"] = cfg.get("sub_size", cfg.get("size", 40))
        sub_actual_font = _make_font(sub_font_cfg)
        sub_color_val = cfg.get("sub_color", "#FFFFFF")
        sub_hl_color_val = cfg.get("sub_hl_color", hl_col)
    else:
        sub_actual_font = main_font
        sub_color_val = col
        sub_hl_color_val = hl_col

    def make_lines(s, font, color, kind, avail, sub_f=None):
        out = []
        if not s.strip():
            return out
        use_sub_font = sub_f if sub_f is not None else sub_actual_font
        
        mask = _hl_mask(s, cfg) if kind == "main" else [False] * len(s)
        do_wrap = bool(cfg.get("wrap", True))
        
        if kind == "main" and sub_enabled:
            fm_main_local = QFontMetricsF(font)
            s_clean = s.strip()
            # 双色上下分离且未手动换行时，自动按约 54% 处均衡拆分为上下两行（避免首行极长、次行仅剩一词）
            if split == "vertical" and "\n" not in s_clean and do_wrap:
                words = list(re.finditer(r"\S+", s_clean))
                if len(words) >= 2:
                    target = len(s_clean) * 0.54
                    best_end = None
                    best_dist = 1e9
                    for m in words[:-1]:
                        end_idx = m.end()
                        if fm_main_local.horizontalAdvance(s_clean[:end_idx]) <= avail * 1.05:
                            d = abs(end_idx - target)
                            if d < best_dist:
                                best_dist = d
                                best_end = end_idx
                    if best_end is not None:
                        s = s_clean[:best_end] + "\n" + s_clean[best_end:].lstrip()
                        mask = _hl_mask(s, cfg)

            # Wrap first line using main_font
            wrap_indices = _wrap(s, fm_main_local, avail, do_wrap)
            if not wrap_indices: return out
            
            a, b = wrap_indices[0]
            out.append(_Line(s[a:b], font, color, hl_col, mask[a:b], "main"))
            
            # Wrap remaining text using sub_font
            if b < len(s):
                rem_text = s[b:].lstrip()
                if rem_text:
                    fm_sub = QFontMetricsF(use_sub_font)
                    rem_mask = _hl_mask(rem_text, cfg)
                    for sa, sb in _wrap(rem_text, fm_sub, avail, do_wrap):
                        out.append(_Line(rem_text[sa:sb], use_sub_font, sub_color_val, sub_hl_color_val, rem_mask[sa:sb], "sub_line"))
            return out
        else:
            fm = QFontMetricsF(font)
            for a, b in _wrap(s, fm, avail, do_wrap):
                out.append(_Line(s[a:b], font, color, hl_col, mask[a:b], kind))
            return out

    icon_in_main = icon == "whatsapp" and split != "horizontal"
    if bool(cfg.get("auto_size")) and text.strip():
        max_lines_lim = max(1, int(cfg.get("max_lines", 3) or 3))
        base_sz = max(1.0, float(cfg.get("size", 72) or 72))
        max_sz = max(10, int(cfg.get("max_size", max(int(base_sz), 96)) or 96))
        min_sz = max(6, min(max_sz, int(cfg.get("min_size", 24) or 24)))
        sub_ratio = float(cfg.get("sub_size", 40) or 40) / base_sz

        def _try_sz(sz_val: int):
            c_try = dict(cfg)
            c_try["size"] = sz_val
            f_m = _make_font(c_try)
            if sub_enabled:
                c_sub = dict(cfg)
                c_sub["size"] = max(6, int(round(sz_val * sub_ratio)))
                f_s = _make_font(c_sub)
            else:
                f_s = f_m
            fm_m = QFontMetricsF(f_m)
            ir = fm_m.height() * 0.48 if icon != "none" else 0.0
            gp = fm_m.height() * 0.25
            av = max(40.0, max_w - (2 * ir + gp if icon_in_main else 0.0))
            lns = make_lines(text, f_m, col, "main", av, sub_f=f_s)
            fits = (len(lns) <= max_lines_lim) and all(ln.w <= av * 1.01 for ln in lns)
            return fits, lns, f_m, f_s, fm_m, ir, gp, av, c_try

        fits_top, lns, f_m, f_s, fm_m, ir, gp, av, c_best = _try_sz(max_sz)
        if fits_top:
            best_pack = (lns, f_m, f_s, fm_m, ir, gp, av, c_best)
        else:
            lo, hi = min_sz, max_sz - 1
            best_sz = min_sz
            best_pack = None
            while lo <= hi:
                mid = (lo + hi) // 2
                ok, lns, f_m, f_s, fm_m, ir, gp, av, c_try = _try_sz(mid)
                if ok:
                    best_sz = mid
                    best_pack = (lns, f_m, f_s, fm_m, ir, gp, av, c_try)
                    lo = mid + 1
                else:
                    hi = mid - 1
            # 微调向上探测 1~3 字号，确保离散换行边界处取到可容纳的最大字号
            for extra_sz in range(best_sz + 1, min(max_sz, best_sz + 3) + 1):
                ok, lns, f_m, f_s, fm_m, ir, gp, av, c_try = _try_sz(extra_sz)
                if ok:
                    best_sz = extra_sz
                    best_pack = (lns, f_m, f_s, fm_m, ir, gp, av, c_try)
            if best_pack is None:
                _, lns, f_m, f_s, fm_m, ir, gp, av, c_try = _try_sz(min_sz)
                best_pack = (lns, f_m, f_s, fm_m, ir, gp, av, c_try)

        main_lines, main_font, sub_actual_font, fm_main, icon_r, gap, main_avail, c_best = best_pack
        lead_font = _make_font(c_best, float(cfg.get("lead_scale", 50)) / 100.0)
        sub_font = _make_font(c_best, float(cfg.get("sub_scale", 40)) / 100.0)
    else:
        main_avail = max_w - (2 * icon_r + gap if icon_in_main else 0)
        main_lines = make_lines(text, main_font, col, "main", main_avail)
    lead_lines = make_lines(lead, lead_font, cfg.get("lead_color", "#FFFFFF"), "lead", max_w)
    sub_lines = make_lines(sub, sub_font, cfg.get("sub_color", "#FFFFFF"), "sub", max_w)

    def stack(lines, top):
        """竖向堆叠居中，返回 (宽, 高)。"""
        y = top
        w = 0.0
        for i, ln in enumerate(lines):
            ln.y = y
            y += ln.h + (ls if i < len(lines) - 1 else 0)
            w = max(w, ln.w)
        return w, y - top

    # 组织分区：每个分区 = {'lines': [...], 'icon': bool, 'arrow': bool}
    if (sub_enabled or not lead_lines) and split == "vertical":
        # First line goes to section 0, the rest to section 1
        line1 = [main_lines[0]] if main_lines else []
        rest = main_lines[1:] if len(main_lines) > 1 else []
        sections = [{"lines": lead_lines + line1, "icon": False}, {"lines": rest + sub_lines, "icon": icon_in_main}]
    elif split == "vertical":
        sections = [{"lines": lead_lines, "icon": False}, {"lines": main_lines + sub_lines, "icon": icon_in_main}]
    elif split == "horizontal":
        sections = [{"lines": [], "icon": icon != "none", "arrow": icon == "whatsapp_arrow"},
                    {"lines": lead_lines + main_lines + sub_lines, "icon": False}]
    else:
        if lead_inline and lead_lines and main_lines:
            sections = [{"lines": main_lines + sub_lines, "icon": icon_in_main, "inline_lead": lead_lines[0]}]
        else:
            sections = [{"lines": lead_lines + main_lines + sub_lines, "icon": icon_in_main}]
    sections = [s for s in sections if s["lines"] or s.get("icon")]
    if not sections:
        return

    px, py = float(cfg.get("bg_pad_x", 30)), float(cfg.get("bg_pad_y", 16))
    use_bg = bool(cfg.get("bg"))
    if not use_bg:
        px = py = 0.0

    # 测量每个分区内容
    for s in sections:
        cw, ch = stack(s["lines"], 0.0) if s["lines"] else (0.0, 0.0)
        il = s.get("inline_lead")
        if il is not None:
            cw += il.w + gap
        iw = 0.0
        if s.get("icon"):
            iw = 2 * icon_r + (gap if s["lines"] else 0)
            if s.get("arrow"):
                iw += 2 * icon_r * 0.9 + gap
            ch = max(ch, 2 * icon_r)
        s["cw"], s["ch"], s["iw"] = cw + iw, ch, iw

    # 计算卡片矩形（局部坐标，以 (0,0) 为中心）
    if split == "horizontal" and len(sections) == 2:
        H = max(s["ch"] for s in sections) + 2 * py
        widths = [s["cw"] + 2 * px for s in sections]
        W = sum(widths)
        x0 = -W / 2
        for s, wv in zip(sections, widths):
            s["rect"] = QRectF(x0, -H / 2, wv, H)
            x0 += wv
    else:
        W = max(s["cw"] for s in sections) + 2 * px
        heights = [s["ch"] + 2 * py for s in sections]
        H = sum(heights)
        y0 = -H / 2
        for s, hv in zip(sections, heights):
            s["rect"] = QRectF(-W / 2, y0, W, hv)
            y0 += hv
    card = QRectF(-W / 2, -H / 2, W, H)

    shape = cfg.get("bg_shape", "rounded")
    if use_bg and shape in ("banner", "gradient"):
        card = QRectF(-cx, card.top(), canv_w, card.height())
        if shape == "gradient":
            card = card.adjusted(0, -card.height() * 1.2, 0, py)
        for s in sections:
            s["rect"] = QRectF(card.left(), s["rect"].top(), card.width(), s["rect"].height()) \
                if split != "horizontal" else s["rect"]

    # 放置每个分区内的文字与图标
    icon_spots = []
    for s_idx, s in enumerate(sections):
        r = s["rect"]
        content_left = r.center().x() - s["cw"] / 2
        top = r.center().y() - s["ch"] / 2
        if s.get("icon"):
            ic = QPointF(content_left + icon_r, r.center().y())
            icon_spots.append(("whatsapp", ic))
            if s.get("arrow"):
                icon_spots.append(("arrow", QPointF(content_left + 2 * icon_r + gap + icon_r * 0.9, r.center().y())))
            content_left += s["iw"]
        lines_h = stack(s["lines"], 0.0)[1] if s["lines"] else 0.0
        ty = r.center().y() - lines_h / 2
        tw = s["cw"] - s["iw"]
        il = s.get("inline_lead")
        if il is not None:
            il.x = content_left
            il.y = ty + (s["lines"][0].h - il.h) / 2 if s["lines"] else ty
            il._sec_idx = s_idx
            content_left += il.w + gap
            tw -= il.w + gap
        stack(s["lines"], ty)
        for ln in s["lines"]:
            ln.x = content_left + (tw - ln.w) / 2
            ln._sec_idx = s_idx
        s["top"] = top

    all_lines = []
    for s in sections:
        if s.get("inline_lead") is not None:
            all_lines.append(s["inline_lead"])
        all_lines.extend(s["lines"])

    # 笔刷涂抹条（brush / brush_feather）：按字高紧凑居中排版，每行拥有独立贴合底条
    is_brush_shape = use_bg and shape in ("brush", "brush_feather") and icon == "none"
    if is_brush_shape and all_lines:
        line_caps = []
        for ln in all_lines:
            ch_val = ln.fm.capHeight() if ln.fm.capHeight() > 0 else ln.fm.ascent() * 0.74
            if re.search(r"[\u4e00-\u9fff]", ln.text):
                ch_val = max(ch_val, ln.fm.ascent() * 0.82)
            line_caps.append(ch_val)
        b_heights = [max(16.0, ch_val + 2 * py) for ch_val in line_caps]
        total_bh = sum(b_heights) + ls * max(0, len(all_lines) - 1)
        cur_y = -total_bh / 2.0
        for ln, ch_val, bh in zip(all_lines, line_caps, b_heights):
            ln._banner_rect = QRectF(-ln.w / 2.0 - px, cur_y, ln.w + 2 * px, bh)
            ln.x = -ln.w / 2.0
            baseline_y = cur_y + py + ch_val
            ln.y = baseline_y - ln.fm.ascent()
            cur_y += bh + ls

    # ── 预先构建文字路径（按颜色分组 & 逐行路径） ──
    color_paths = {}
    full_main = QPainterPath()
    full_sub = QPainterPath()
    rtl = bool(cfg.get("rtl"))
    for ln in all_lines:
        baseline = ln.y + ln.fm.ascent()
        ln_path = QPainterPath()
        runs = []
        i = 0
        while i < len(ln.text):
            j = i
            while j < len(ln.text) and ln.hl[j] == ln.hl[i]:
                j += 1
            runs.append((ln.text[i:j], ln.hl[i]))
            i = j
        cur = ln.x + ln.w if rtl else ln.x
        for s, is_hl in runs:
            rw = ln.fm.horizontalAdvance(s)
            if rtl:
                cur -= rw
            path = QPainterPath()
            path.addText(QPointF(cur, baseline), ln.font, s)
            ln_path.addPath(path)
            key = ln.hl_color if is_hl else ln.color
            color_paths.setdefault(key, QPainterPath()).addPath(path)
            if ln.kind == "sub_line":
                full_sub.addPath(path)
            else:
                full_main.addPath(path)
            if not rtl:
                cur += rw
        ln._glyph_path = ln_path

    # ── 1) 背景 ──
    if use_bg:
        radius = float(cfg.get("bg_radius", 18))
        c1 = _alpha_color(cfg.get("bg_color", "#000000"), cfg.get("bg_alpha", 170))
        c2 = _alpha_color(cfg.get("split_color2", "#FFFFFF"), cfg.get("split_alpha2", 255))
        bg_tex1 = cfg.get("bg_texture", "none") or "none"
        bg_tex2 = (cfg.get("sub_bg_texture", "none") or "none") if (sub_enabled or split == "vertical") else bg_tex1

        fit = bool(cfg.get("bg_fit", True)) and not lead_lines and not sub_lines \
            and icon == "none" and shape in ("rounded", "rect", "pill", "torn", "notch", "ribbon", "bow", "wave")

        if is_brush_shape or (fit and split == "vertical" and len(all_lines) >= 1):
            # 逐行独立底框（支持上下双色各自贴合行宽 + 笔刷/折纸/斑驳纹理）
            line_items = []
            full_bg_path = QPainterPath()
            for idx, ln in enumerate(all_lines):
                is_sec = (split == "vertical" and getattr(ln, "_sec_idx", 0) >= 1) or ln.kind == "sub_line"
                lr = getattr(ln, "_banner_rect", None)
                if lr is None:
                    lr = QRectF(ln.x - px, ln.y - py, ln.w + 2 * px, ln.h + 2 * py)
                l_tex = bg_tex2 if is_sec else bg_tex1
                l_col = c2 if is_sec else c1
                if l_tex == "crumpled":
                    l_path = _shape_path("rect", lr, 0, seed=17 + idx * 31)
                else:
                    l_path = _shape_path(shape, lr, radius, seed=17 + idx * 31)
                # 若字母上方有重音符号（如 Ñ 的波浪号）超出笔刷条顶边，自动融合一圈实心笔刷轮廓突起
                if is_brush_shape and hasattr(ln, "_glyph_path") and not ln._glyph_path.isEmpty():
                    gb = ln._glyph_path.boundingRect()
                    if gb.top() < lr.top() + 3.0:
                        top_clip = QPainterPath()
                        top_clip.addRect(QRectF(lr.left(), gb.top() - 20.0, lr.width(), (lr.top() + 8.0) - (gb.top() - 20.0)))
                        accent_part = ln._glyph_path.intersected(top_clip)
                        if not accent_part.isEmpty():
                            ab = accent_part.boundingRect().adjusted(-9.0, -6.0, 9.0, 8.0)
                            bump = QPainterPath()
                            bump.addRoundedRect(ab, 8.0, 8.0)
                            l_path = l_path.united(bump)
                line_items.append((lr, l_path, l_col, l_tex, 17 + idx * 31))
                full_bg_path.addPath(l_path)

            if cfg.get("bg_shadow") and not full_bg_path.isEmpty():
                sc = QColor(cfg.get("bg_shadow_color", "#000000"))
                _draw_blurred(p, lambda q: q.fillPath(full_bg_path, sc), full_bg_path.boundingRect(),
                              cfg.get("bg_shadow_blur", 16), cfg.get("bg_shadow_x", 0), cfg.get("bg_shadow_y", 8),
                              float(cfg.get("bg_shadow_alpha", 30)) / 100.0)

            # 若次行是折纸条且首行是深色笔刷条，先画次行再画首行（让首行笔刷压在次行上方更自然）
            draw_order = list(reversed(line_items)) if (len(line_items) > 1 and line_items[-1][3] == "crumpled") else line_items
            for lr, l_path, l_col, l_tex, l_seed in draw_order:
                if l_tex == "crumpled":
                    g_base = QLinearGradient(QPointF(lr.left(), 0), QPointF(lr.right(), 0))
                    c_zero = QColor(l_col.red(), l_col.green(), l_col.blue(), 0)
                    c_edge = QColor(int(l_col.red() * 0.35), int(l_col.green() * 0.35), int(l_col.blue() * 0.35), int(l_col.alpha() * 0.7))
                    g_base.setColorAt(0.0, c_zero)
                    g_base.setColorAt(0.05, c_edge)
                    g_base.setColorAt(0.14, l_col)
                    g_base.setColorAt(0.86, l_col)
                    g_base.setColorAt(0.95, c_edge)
                    g_base.setColorAt(1.0, c_zero)
                    p.fillPath(l_path, QBrush(g_base))
                else:
                    p.fillPath(l_path, l_col)
                _draw_bg_texture(p, lr, l_path, l_tex, l_col, seed=l_seed)
                bdw = float(cfg.get("bg_border_w", 0))
                if bdw > 0:
                    p.strokePath(l_path, QPen(QColor(cfg.get("bg_border_color", "#FFFFFF")), bdw,
                                              Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        else:
            if shape == "hug":
                card_path = QPainterPath()
                for i, ln in enumerate(all_lines):
                    y1 = ln.y
                    y2 = ln.y + ln.h
                    if i > 0:
                        y1 = min(y1, all_lines[i-1].y + all_lines[i-1].h)
                    if i < len(all_lines) - 1:
                        y2 = max(y2, all_lines[i+1].y)
                    card_path.addRect(QRectF(ln.x, y1, ln.w, y2 - y1))
                
                card_path = card_path.simplified()
                if not card_path.isEmpty():
                    stroker = QPainterPathStroker()
                    # The radius of the stroke determines the padding
                    stroker.setWidth(max(px, py) * 2 if max(px, py) > 0 else 20)
                    stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                    stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
                    outline = stroker.createStroke(card_path)
                    card_path = card_path.united(outline)
                    card_path = card_path.simplified()
            elif fit:
                card_path = QPainterPath()
                for ln in all_lines:
                    lr = QRectF(ln.x - px, ln.y - py, ln.w + 2 * px, ln.h + 2 * py)
                    card_path.addPath(_shape_path(shape, lr, radius))
                card_path = card_path.simplified()
            else:
                card_path = _shape_path(shape, card, radius)

            if cfg.get("bg_shadow"):
                sc = QColor(cfg.get("bg_shadow_color", "#000000"))
                _draw_blurred(p, lambda q: q.fillPath(card_path, sc), card_path.boundingRect(),
                              cfg.get("bg_shadow_blur", 16), cfg.get("bg_shadow_x", 0), cfg.get("bg_shadow_y", 8),
                              float(cfg.get("bg_shadow_alpha", 30)) / 100.0)

            if shape == "outline":
                pass
            elif shape == "gradient":
                g = QLinearGradient(QPointF(0, card.bottom()), QPointF(0, card.top()))
                g.setColorAt(0.0, c1)
                g.setColorAt(1.0, _alpha_color(cfg.get("bg_color", "#000000"), 0))
                p.fillPath(card_path, QBrush(g))
            else:
                p.save()
                p.setClipPath(card_path)
                if len(sections) == 2 and split in ("vertical", "horizontal"):
                    for k, s in enumerate(sections):
                        sr = s["rect"].adjusted(-1, -1, 1, 1)
                        scol = c1 if k == 0 else c2
                        stex = bg_tex1 if k == 0 else bg_tex2
                        p.fillRect(sr, scol)
                        sp = QPainterPath()
                        sp.addRect(sr)
                        _draw_bg_texture(p, sr, sp.intersected(card_path), stex, scol, seed=19 + k * 29)
                else:
                    p.fillPath(card_path, c1)
                    _draw_bg_texture(p, card_path.boundingRect(), card_path, bg_tex1, c1, seed=19)
                bw = float(cfg.get("bg_bottom_w", 0))
                if bw > 0:
                    br = card_path.boundingRect()
                    p.fillRect(QRectF(br.left(), br.bottom() - bw, br.width(), bw), QColor(cfg.get("bg_bottom_color", "#D90429")))
                p.restore()
            bdw = float(cfg.get("bg_border_w", 0))
            if bdw > 0:
                p.strokePath(card_path, QPen(QColor(cfg.get("bg_border_color", "#FFFFFF")), bdw,
                                             Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))

    base_sw = float(cfg.get("stroke_width", 6)) if cfg.get("stroke") else 0.0
    ms_extra = float(cfg.get("ms_step", 6)) * int(cfg.get("ms_layers", 2)) if cfg.get("multi_stroke") else 0.0
    outline_w = (base_sw + ms_extra) * 2

    sub_sw = float(cfg.get("sub_stroke_width", 6)) if cfg.get("sub_stroke") else 0.0
    sub_outline_w = sub_sw * 2

    def round_pen(color, w):
        return QPen(color, w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)

    # ── 3) 阴影 / 发光（真实模糊 + 透明度） ──
    if cfg.get("shadow"):
        sc = QColor(cfg.get("shadow_color", "#000000"))

        def _shadow(q):
            if not full_main.isEmpty():
                q.fillPath(full_main, sc)
                if outline_w > 0:
                    q.strokePath(full_main, round_pen(sc, outline_w))
            if not full_sub.isEmpty():
                q.fillPath(full_sub, sc)
                if sub_outline_w > 0:
                    q.strokePath(full_sub, round_pen(sc, sub_outline_w))
                    
        full = full_main.united(full_sub)
        b = full.boundingRect().adjusted(-max(outline_w, sub_outline_w), -max(outline_w, sub_outline_w), max(outline_w, sub_outline_w), max(outline_w, sub_outline_w))
        _draw_blurred(p, _shadow, b, cfg.get("shadow_blur", 6), cfg.get("shadow_x", 4), cfg.get("shadow_y", 4),
                      float(cfg.get("shadow_alpha", 100)) / 100.0)

    # ── 4) 多层扩展描边 (仅限主样式) ──
    if cfg.get("multi_stroke") and not full_main.isEmpty():
        layers = max(1, int(cfg.get("ms_layers", 2)))
        step = float(cfg.get("ms_step", 6))
        feather = max(0, int(cfg.get("ms_feather", 0)))
        colors = [c.strip() for c in str(cfg.get("ms_colors", "")).split(",") if c.strip()] or ["#FFFFFF"]
        for k in range(layers, 0, -1):
            colr = QColor(colors[min(k - 1, len(colors) - 1)])
            w = (base_sw + step * k) * 2
            if feather:
                _draw_blurred(p, lambda q, c=colr, ww=w: q.strokePath(full_main, round_pen(c, ww)),
                              full_main.boundingRect().adjusted(-w, -w, w, w), feather, 0, 0, 1.0)
            p.strokePath(full_main, round_pen(colr, w))

    # ── 5) 基础描边 ──
    if base_sw > 0 and not full_main.isEmpty():
        p.strokePath(full_main, round_pen(QColor(cfg.get("stroke_color", "#000000")), base_sw * 2))
    if sub_sw > 0 and not full_sub.isEmpty():
        p.strokePath(full_sub, round_pen(QColor(cfg.get("sub_stroke_color", "#000000")), sub_sw * 2))

    # ── 6) 填充 ──
    for key, path in color_paths.items():
        p.fillPath(path, QBrush(QColor(key)))

    # ── 6.5) 文字做旧纹理（斜向裂纹 / 横向干笔刷斑驳 / 复古颗粒） ──
    tex_main = cfg.get("text_texture", "none") or "none"
    tex_sub = (cfg.get("sub_text_texture", "none") or "none") if sub_enabled else tex_main
    if tex_main != "none" and not full_main.isEmpty():
        _draw_text_texture(p, full_main, tex_main, col, seed=31)
    if tex_sub != "none" and not full_sub.isEmpty():
        _draw_text_texture(p, full_sub, tex_sub, sub_color_val, seed=67)

    # ── 7) 下划线 ──
    if cfg.get("underline"):
        uw = float(cfg.get("underline_w", 4))
        pen = QPen(QColor(cfg.get("underline_color", "#25D366")), uw, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        for ln in all_lines:
            if ln.kind == "main" and ln.text.strip():
                y = ln.y + ln.fm.ascent() + ln.fm.descent() * 0.55 + uw / 2
                p.drawLine(QPointF(ln.x, y), QPointF(ln.x + ln.w, y))

    # ── 8) 图标 ──
    for kind, pt in icon_spots:
        if kind == "whatsapp":
            _draw_whatsapp(p, pt, icon_r)
        else:
            _draw_arrow(p, pt, icon_r * 1.8, QColor("#FFFFFF"))


# ── 水印 ──────────────────────────────────────────────────────────────────────

WM_MARGIN = 30


def render_watermark_layer(items: list, canvas_wh: tuple = None) -> QImage:
    cw, ch = canvas_wh if (canvas_wh and len(canvas_wh) == 2) else get_canvas_size()
    img = QImage(cw, ch, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    for wm in items or []:
        base = default_watermark()
        base.update(wm or {})
        if base.get("enabled"):
            try:
                _draw_watermark(p, base, cw, ch)
            except Exception as e:
                print("watermark draw failed:", e)
    p.end()
    return img


def _wm_pos(pos: str, w: float, h: float, ox: float, oy: float, cw: int = None, ch: int = None) -> tuple:
    if cw is None or ch is None:
        cw, ch = get_canvas_size()
    m = WM_MARGIN
    if pos == "tl":
        x, y = m, m
    elif pos == "tr":
        x, y = cw - m - w, m
    elif pos == "bl":
        x, y = m, ch - m - h
    elif pos == "bc":
        x, y = (cw - w) / 2, ch - m - h
    else:  # br
        x, y = cw - m - w, ch - m - h
    return x + ox, y + oy


def _draw_watermark(p: QPainter, wm: dict, cw: int = None, ch: int = None):
    if cw is None or ch is None:
        cw, ch = get_canvas_size()
    if wm["type"] == "image":
        path = wm.get("image_path", "")
        if not path or not os.path.isfile(path):
            return
        im = QImage(path)
        if im.isNull():
            return
        if wm.get("flip_h") or wm.get("flip_v"):
            im = im.mirrored(bool(wm.get("flip_h")), bool(wm.get("flip_v")))
        s = float(wm.get("scale", 30)) / 100.0
        w, h = im.width() * s, im.height() * s
        x, y = _wm_pos(wm.get("position", "br"), w, h, float(wm.get("ox", 0)), float(wm.get("oy", 0)), cw, ch)
        p.save()
        p.setOpacity(float(wm.get("opacity", 100)) / 100.0)
        p.drawImage(QRectF(x, y, w, h), im)
        p.restore()
    else:
        text = (wm.get("text") or "").replace("\r", "")
        if not text.strip():
            return
        load_bundled_fonts()
        f = QFont(wm.get("font_family") or "Microsoft YaHei")
        f.setPixelSize(max(6, int(wm.get("font_size", 32))))
        fm = QFontMetricsF(f)
        lines = text.split("\n")
        tw = max(fm.horizontalAdvance(l) for l in lines)
        th = fm.height() * len(lines)
        padx, pady = fm.height() * 0.4, fm.height() * 0.2
        w, h = tw + 2 * padx, th + 2 * pady
        x, y = _wm_pos(wm.get("position", "br"), w, h, float(wm.get("ox", 0)), float(wm.get("oy", 0)), cw, ch)
        bga = float(wm.get("bg_opacity", 50))
        if bga > 0:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(_alpha_color(wm.get("bg_color", "#000000"), bga / 100.0 * 255))
            p.drawRoundedRect(QRectF(x, y, w, h), 8, 8)
        p.setFont(f)
        p.setPen(_alpha_color(wm.get("color", "#FFFFFF"), float(wm.get("text_opacity", 100)) / 100.0 * 255))
        for i, l in enumerate(lines):
            lw = fm.horizontalAdvance(l)
            p.drawText(QPointF(x + padx + (tw - lw) / 2, y + pady + i * fm.height() + fm.ascent()), l)