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

from image_worker.duet_worker import CANVAS_W, CANVAS_H, box_layout, place_in_box, get_install_root

PERSON_COLOR = QColor("#90CDF4")   # 浅蓝：人物
VIRAL_COLOR = QColor("#FBB6CE")    # 浅粉：爆款

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
        # 背景
        "bg": False, "bg_fit": False, "bg_shape": "rounded", "bg_color": "#000000", "bg_alpha": 170,
        "bg_radius": 18, "bg_pad_x": 30, "bg_pad_y": 16,
        "bg_border_w": 0, "bg_border_color": "#FFFFFF",
        "bg_bottom_w": 0, "bg_bottom_color": "#D90429",
        "bg_shadow": False, "bg_shadow_color": "#000000", "bg_shadow_x": 0, "bg_shadow_y": 8,
        "bg_shadow_blur": 16, "bg_shadow_alpha": 30,
        # 结构（引导语 / 副文本 / 双色拼接 / 图标）
        "lead_text": "", "lead_color": "#FFFFFF", "lead_scale": 50, "lead_inline": False,
        "sub_text": "", "sub_color": "#FFFFFF", "sub_scale": 40,
        "sub_enabled": False, "sub_size": 40, "sub_hl_color": "#FFD400", "sub_stroke": True, "sub_stroke_color": "#000000", "sub_stroke_width": 6,
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
    pm.fill(QColor("#2D3748"))
    p = QPainter(pm)
    lay = box_layout(tpl)
    sy = h / CANVAS_H
    py, ph, _ = lay["person"]
    vy, vh, _ = lay["viral"]
    p.fillRect(QRectF(0, py * sy, w, ph * sy), PERSON_COLOR)
    p.fillRect(QRectF(0, vy * sy, w, vh * sy), VIRAL_COLOR)
    p.setPen(QPen(QColor("#F6E05E"), 2))
    p.drawLine(QPointF(0, lay["split_y"] * sy), QPointF(w, lay["split_y"] * sy))
    p.end()
    return QIcon(pm)


# ── 画面合成（预览用） ─────────────────────────────────────────────────────────

def _draw_box(p: QPainter, img, y: int, h: int, cfg: dict, adj: dict,
              color: QColor, label: str):
    p.save()
    p.setClipRect(0, y, CANVAS_W, h)
    if img is None or img.isNull():
        p.fillRect(0, y, CANVAS_W, h, color)
        f = QFont("Microsoft YaHei", 42)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("#FFFFFF"))
        p.drawText(QRectF(0, y, CANVAS_W, h), Qt.AlignmentFlag.AlignCenter, label)
    else:
        p.fillRect(0, y, CANVAS_W, h, QColor("#000000"))
        sw, sh, x, yy = place_in_box(img.width(), img.height(), h, cfg, adj)
        p.drawImage(QRectF(x, y + yy, sw, sh), img)
    p.restore()


def compose_preview(tpl: dict, person_img=None, viral_img=None, adj: dict = None,
                    overlays: list = None, show_split: bool = True) -> QImage:
    adj = adj or {}
    canvas = QImage(CANVAS_W, CANVAS_H, QImage.Format.Format_ARGB32_Premultiplied)
    canvas.fill(QColor("#000000"))
    p = QPainter(canvas)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    lay = box_layout(tpl)
    py, ph, pcfg = lay["person"]
    vy, vh, vcfg = lay["viral"]
    _draw_box(p, person_img, py, ph, pcfg, adj.get("person"), PERSON_COLOR, "人物视频")
    _draw_box(p, viral_img, vy, vh, vcfg, adj.get("viral"), VIRAL_COLOR, "爆款视频")
    for ov in overlays or []:
        if ov is not None and not ov.isNull():
            p.drawImage(0, 0, ov)
    if show_split:
        pen = QPen(QColor("#F6E05E"), 4, Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.drawLine(0, lay["split_y"], CANVAS_W, lay["split_y"])
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


def card_center(cfg: dict, split_y: int, task_index: int = 0) -> tuple:
    if cfg.get("snap_split"):
        cx, cy = CANVAS_W / 2, float(split_y)
    else:
        cx, cy = float(cfg.get("pos_x", 540)), float(cfg.get("pos_y", 960))
    rh = float(cfg.get("rand_height", 0))
    if rh:
        rnd = random.Random(task_index * 7919 + 13)
        cy += rnd.uniform(-rh, rh) / 100.0 * CANVAS_H
    return cx, cy


def render_card_layer(cfg: dict, text: str, split_y: int, task_index: int = 0,
                      draw_guides: bool = False) -> QImage:
    img = QImage(CANVAS_W, CANVAS_H, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    if not cfg.get("enabled", True):
        return img
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    cx, cy = card_center(cfg, split_y, task_index)
    rot = float(cfg.get("rotation", 0))
    p.translate(cx, cy)
    if rot:
        p.rotate(rot)

    if cfg.get("mode") == "image":
        _draw_image_card(p, cfg)
    else:
        _draw_text_card(p, cfg, text or "", cx)

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

def _shape_path(shape: str, rect: QRectF, radius: float, seed: int = 7) -> QPainterPath:
    path = QPainterPath()
    if shape == "pill":
        rr = rect.height() / 2
        path.addRoundedRect(rect, rr, rr)
    elif shape in ("rect", "banner", "gradient"):
        path.addRect(rect)
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


def _alpha_color(hexc: str, alpha: int) -> QColor:
    c = QColor(hexc)
    c.setAlpha(max(0, min(255, int(alpha))))
    return c


def _draw_text_card(p: QPainter, cfg: dict, text: str, cx: float):
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

    def make_lines(s, font, color, kind, avail):
        out = []
        if not s.strip():
            return out
        
        mask = _hl_mask(s, cfg) if kind == "main" else [False] * len(s)
        do_wrap = bool(cfg.get("wrap", True))
        
        if kind == "main" and sub_enabled:
            # Wrap first line using main_font
            fm_main_local = QFontMetricsF(font)
            wrap_indices = _wrap(s, fm_main_local, avail, do_wrap)
            if not wrap_indices: return out
            
            a, b = wrap_indices[0]
            out.append(_Line(s[a:b], font, color, hl_col, mask[a:b], "main"))
            
            # Wrap remaining text using sub_font
            if b < len(s):
                rem_text = s[b:].lstrip()
                if rem_text:
                    fm_sub = QFontMetricsF(sub_actual_font)
                    rem_mask = _hl_mask(rem_text, cfg)
                    for sa, sb in _wrap(rem_text, fm_sub, avail, do_wrap):
                        out.append(_Line(rem_text[sa:sb], sub_actual_font, sub_color_val, sub_hl_color_val, rem_mask[sa:sb], "sub_line"))
            return out
        else:
            fm = QFontMetricsF(font)
            for a, b in _wrap(s, fm, avail, do_wrap):
                out.append(_Line(s[a:b], font, color, hl_col, mask[a:b], kind))
            return out

    icon_in_main = icon == "whatsapp" and split != "horizontal"
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
    if sub_enabled and split == "vertical":
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
        card = QRectF(-cx, card.top(), CANVAS_W, card.height())
        if shape == "gradient":
            card = card.adjusted(0, -card.height() * 1.2, 0, py)
        for s in sections:
            s["rect"] = QRectF(card.left(), s["rect"].top(), card.width(), s["rect"].height()) \
                if split != "horizontal" else s["rect"]

    # 放置每个分区内的文字与图标
    icon_spots = []
    for s in sections:
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
            content_left += il.w + gap
            tw -= il.w + gap
        stack(s["lines"], ty)
        for ln in s["lines"]:
            ln.x = content_left + (tw - ln.w) / 2
        s["top"] = top

    all_lines = []
    for s in sections:
        if s.get("inline_lead") is not None:
            all_lines.append(s["inline_lead"])
        all_lines.extend(s["lines"])

    # ── 1) 背景 ──
    if use_bg:
        radius = float(cfg.get("bg_radius", 18))
        fit = bool(cfg.get("bg_fit", True)) and split == "none" and not lead_lines and not sub_lines \
            and icon == "none" and shape in ("rounded", "rect", "pill")
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

        c1 = _alpha_color(cfg.get("bg_color", "#000000"), cfg.get("bg_alpha", 170))
        c2 = _alpha_color(cfg.get("split_color2", "#FFFFFF"), cfg.get("split_alpha2", 255))
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
                    p.fillRect(s["rect"].adjusted(-1, -1, 1, 1), c1 if k == 0 else c2)
            else:
                p.fillPath(card_path, c1)
            bw = float(cfg.get("bg_bottom_w", 0))
            if bw > 0:
                br = card_path.boundingRect()
                p.fillRect(QRectF(br.left(), br.bottom() - bw, br.width(), bw), QColor(cfg.get("bg_bottom_color", "#D90429")))
            p.restore()
        bdw = float(cfg.get("bg_border_w", 0))
        if bdw > 0:
            p.strokePath(card_path, QPen(QColor(cfg.get("bg_border_color", "#FFFFFF")), bdw,
                                         Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))

    # ── 2) 文字路径（按颜色分组） ──
    color_paths = {}
    full_main = QPainterPath()
    full_sub = QPainterPath()
    rtl = bool(cfg.get("rtl"))
    for ln in all_lines:
        baseline = ln.y + ln.fm.ascent()
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
            key = ln.hl_color if is_hl else ln.color
            color_paths.setdefault(key, QPainterPath()).addPath(path)
            if ln.kind == "sub_line":
                full_sub.addPath(path)
            else:
                full_main.addPath(path)
            if not rtl:
                cur += rw

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


def render_watermark_layer(items: list) -> QImage:
    img = QImage(CANVAS_W, CANVAS_H, QImage.Format.Format_ARGB32_Premultiplied)
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
                _draw_watermark(p, base)
            except Exception as e:
                print("watermark draw failed:", e)
    p.end()
    return img


def _wm_pos(pos: str, w: float, h: float, ox: float, oy: float) -> tuple:
    m = WM_MARGIN
    if pos == "tl":
        x, y = m, m
    elif pos == "tr":
        x, y = CANVAS_W - m - w, m
    elif pos == "bl":
        x, y = m, CANVAS_H - m - h
    elif pos == "bc":
        x, y = (CANVAS_W - w) / 2, CANVAS_H - m - h
    else:  # br
        x, y = CANVAS_W - m - w, CANVAS_H - m - h
    return x + ox, y + oy


def _draw_watermark(p: QPainter, wm: dict):
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
        x, y = _wm_pos(wm.get("position", "br"), w, h, float(wm.get("ox", 0)), float(wm.get("oy", 0)))
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
        x, y = _wm_pos(wm.get("position", "br"), w, h, float(wm.get("ox", 0)), float(wm.get("oy", 0)))
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