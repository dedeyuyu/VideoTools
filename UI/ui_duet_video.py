"""
ui_duet_video.py — 合拍视频批量合成

流程：
  1. 素材与时间线：导入两组视频 + 选择模板 → 点击「对齐时间线」生成缓存（后台分批处理）
  2. 画面排版模板：随时可进入，编辑/保存/重命名/删除模板（模板库带色块缩略图）
  3. 字幕卡片微调：实时画面预览（真实视频帧 + 模板 + 卡片），逐任务微调
  4. 全局导出设置：命名、分辨率、画质、音量、GPU、并发（最多 4 路）
"""
import os
import io
import csv
import json
import shutil
import hashlib

from PyQt6.QtWidgets import (QApplication, 
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QStackedWidget, QFrame,
    QListWidget, QListWidgetItem, QCheckBox, QDoubleSpinBox, QSpinBox, QComboBox,
    QSlider, QFormLayout, QLineEdit, QFileDialog, QMessageBox, QProgressBar, QSplitter, QRadioButton,
    QScrollArea, QTabWidget, QGroupBox, QPlainTextEdit, QDialog, QDialogButtonBox,
    QInputDialog, QColorDialog, QFontComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QSizePolicy, QAbstractItemView, QStyledItemDelegate, QStyle,
)
from PyQt6.QtCore import Qt, QThread, QPoint, QPointF, pyqtSignal, QTimer, QRectF, QSize, QUrl
from PyQt6.QtGui import QImage, QIcon, QPixmap, QPainterPath, QPainter, QColor, QPen, QFont, QDesktopServices, QFontDatabase, QPalette

from image_worker.duet_worker import (
    get_data_dir, get_cache_dir, probe_info, align_person_video, extract_frame_png,
    set_cache_root, new_task_cache_dir, list_task_cache_dirs, get_card_lib_dir,
    default_template, box_layout, build_render_cmd, run_cmd, CANVAS_W, CANVAS_H,
    SOURCES, SRC_LABELS, FILL_MODES, LAYOUT_PRESETS, template_from_cells, tpl_cells,
    sources_used, cell_rect_px, task_source,
)
from image_worker.duet_render import (
 render_watermark_layer,    default_card, template_icon, compose_preview, render_card_layer, load_font_file,
)

VIDEO_EXTS = ("mp4", "mov", "avi", "mkv", "flv", "wmv", "m4v", "webm")
SAMPLE_TITLE = "【示例】标题卡片文字"
SAMPLE_PHONE = "【示例】电话 400-000-0000"


# ══════════════════════════════════════════════════════════════════════════════
#  通用小工具
# ══════════════════════════════════════════════════════════════════════════════

def _get_all_presets():
    from UI.default_presets import DEFAULT_PRESETS
    import copy
    presets = copy.deepcopy(DEFAULT_PRESETS)
    presets.update(_load_json("card_presets.json", {}))
    return presets


def _load_json(name, default):
    path = os.path.join(get_data_dir(), name)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


PROJECT_FILE = "project.json"   # 每个对齐文件夹里的工程文件
PROJECT_BACKUP_KEEP = 30        # 每个工程最多保留的历史快照数
PROJECT_BACKUP_GAP = 120        # 两次快照之间至少间隔（秒）


def _atomic_write(path, text):
    """先写临时文件再替换，避免崩溃/断电时把文件写坏。"""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _save_json(name, data):
    """全局文件（预设 / 模板 / 软件偏好），固定存放在 duet_data。"""
    path = os.path.join(get_data_dir(), name)
    try:
        _atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2))
    except Exception as e:
        print("save json failed:", e)


def project_backup_dir(proj_dir):
    d = os.path.join(proj_dir, "backups")
    os.makedirs(d, exist_ok=True)
    return d


def save_project(proj_dir, data):
    """把一次任务的全部参数写到它自己的对齐文件夹：<对齐文件夹>/project.json，并保留历史快照。"""
    import time, glob
    if not proj_dir or not os.path.isdir(proj_dir):
        return False
    text = json.dumps(data, ensure_ascii=False, indent=2)
    path = os.path.join(proj_dir, PROJECT_FILE)
    try:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                if f.read() == text:
                    return True          # 没有变化，不重复写
    except Exception:
        pass
    _atomic_write(path, text)
    try:
        bdir = project_backup_dir(proj_dir)
        olds = sorted(glob.glob(os.path.join(bdir, "project_*.json")))
        if not olds or time.time() - os.path.getmtime(olds[-1]) >= PROJECT_BACKUP_GAP:
            with open(os.path.join(bdir, f"project_{time.strftime('%Y%m%d_%H%M%S')}.json"),
                      "w", encoding="utf-8") as f:
                f.write(text)
            olds = sorted(glob.glob(os.path.join(bdir, "project_*.json")))
            for old in olds[:-PROJECT_BACKUP_KEEP]:
                try:
                    os.remove(old)
                except Exception:
                    pass
    except Exception as e:
        print("project snapshot failed:", e)
    return True


def load_project(proj_dir):
    """读取对齐文件夹里的工程；若文件夹被移动过，自动把缓存视频路径修正到新位置。"""
    path = os.path.join(proj_dir, PROJECT_FILE)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    for t in data.get("tasks") or []:
        old_dir = t.get("task_dir", "")
        t["task_dir"] = proj_dir
        cache = t.get("cache", "")
        if cache and not os.path.isfile(cache) and old_dir and \
                os.path.normcase(os.path.dirname(cache)) == os.path.normcase(old_dir):
            moved = os.path.join(proj_dir, os.path.basename(cache))
            if os.path.isfile(moved):
                t["cache"] = moved
    return data


def _parse_pasted(text: str) -> list:
    """解析从 Excel 复制的内容：取第一列，支持单元格内换行（带引号）。去掉末尾空行。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    rows = []
    try:
        for row in csv.reader(io.StringIO(text), delimiter="\t"):
            rows.append(row[0] if row else "")
    except Exception:
        rows = text.split("\n")
    while rows and not rows[-1].strip():
        rows.pop()
    return rows


def _card_title(text):
    lbl = QLabel(text)
    lbl.setProperty("class", "CardTitle")
    return lbl


def _card():
    f = QFrame()
    f.setProperty("class", "Card")
    return f


class VideoListWidget(QListWidget):
    """支持从资源管理器拖入视频文件，以及内部上下拖拽排序。"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

    def add_files(self, paths):
        for p in paths:
            if os.path.isfile(p) and p.lower().rsplit(".", 1)[-1] in VIDEO_EXTS:
                it = QListWidgetItem(f"{os.path.basename(p)}")
                it.setData(Qt.ItemDataRole.UserRole, p)
                it.setToolTip(p)
                self.addItem(it)
        self._renumber()

    def _renumber(self):
        for i in range(self.count()):
            it = self.item(i)
            it.setText(f"{i + 1:02d}.  {os.path.basename(it.data(Qt.ItemDataRole.UserRole))}")

    def paths(self):
        return [self.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.count())]

    def move_selected(self, delta):
        row = self.currentRow()
        new = row + delta
        if row < 0 or new < 0 or new >= self.count():
            return
        it = self.takeItem(row)
        self.insertItem(new, it)
        self.setCurrentRow(new)
        self._renumber()

    def remove_selected(self):
        for it in self.selectedItems():
            self.takeItem(self.row(it))
        self._renumber()

    def dragEnterEvent(self, e):
        e.accept() if e.mimeData().hasUrls() else e.ignore()

    def dragMoveEvent(self, e):
        e.accept() if e.mimeData().hasUrls() else e.ignore()

    def dropEvent(self, e):
        if e.source() == self:
            super().dropEvent(e)
            self._renumber()
            return
        if e.mimeData().hasUrls():
            paths = []
            for url in e.mimeData().urls():
                p = url.toLocalFile()
                if os.path.isdir(p):
                    for fn in sorted(os.listdir(p)):
                        paths.append(os.path.join(p, fn))
                else:
                    paths.append(p)
            self.add_files(paths)
            e.accept()


class CanvasView(QWidget):
    """按 9:16 比例显示合成画面；可编辑模式下：拖动格子分界线、拖动/缩放画中画小窗、点击选中格子。"""
    splitDragged = pyqtSignal(float)
    cellsChanged = pyqtSignal(list)
    cellSelected = pyqtSignal(int)

    MIN_FRAC = 0.05

    def __init__(self, draggable=False, parent=None):
        super().__init__(parent)
        self._img = None
        self._split = 0.5
        self._draggable = draggable
        self._cells = None
        self._drag = None
        self.setMinimumSize(240, 427)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)

    def set_image(self, img, split_ratio=None):
        self._img = img
        if split_ratio is not None:
            self._split = split_ratio
        self.update()

    def set_cells(self, cells):
        import copy
        self._cells = copy.deepcopy(cells) if cells is not None else None
        self.update()

    def _rect(self):
        w, h = self.width(), self.height()
        s = min(w / CANVAS_W, h / CANVAS_H)
        tw, th = CANVAS_W * s, CANVAS_H * s
        return QRectF((w - tw) / 2, (h - th) / 2, tw, th)

    def _to_frac(self, pos):
        r = self._rect()
        return (pos.x() - r.left()) / max(1, r.width()), (pos.y() - r.top()) / max(1, r.height())

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = self._rect()
        if self._img is not None and not self._img.isNull():
            p.drawImage(r, self._img)
        else:
            p.fillRect(r, QColor("#2D3748"))
        p.setPen(QPen(QColor("#718096"), 1))
        p.drawRect(r)
        if self._draggable and self._cells:
            pen = QPen(QColor("#F6E05E"), 2)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            for cl in self._cells:
                x = r.left() + cl["x"] * r.width()
                y = r.top() + cl["y"] * r.height()
                w, h = cl["w"] * r.width(), cl["h"] * r.height()
                if cl.get("pip"):
                    p.setPen(QPen(QColor("#F6E05E"), 2, Qt.PenStyle.DashLine))
                    p.drawRect(QRectF(x, y, w, h))
                    p.setBrush(QColor("#F6E05E"))
                    p.drawRect(QRectF(x + w - 8, y + h - 8, 8, 8))
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.setPen(pen)
                else:
                    if cl["x"] + cl["w"] < 0.999:
                        p.drawLine(QPointF(x + w, y), QPointF(x + w, y + h))
                    if cl["y"] + cl["h"] < 0.999:
                        p.drawLine(QPointF(x, y + h), QPointF(x + w, y + h))
        elif self._draggable:
            y = r.top() + r.height() * self._split
            p.setPen(QPen(QColor("#F6E05E"), 2))
            p.drawLine(int(r.left()), int(y), int(r.right()), int(y))
        p.end()

    # —— 命中检测 ——
    def _hit(self, pos):
        if not self._cells:
            return None
        r = self._rect()
        fx, fy = self._to_frac(pos)
        tolx, toly = 8 / max(1, r.width()), 8 / max(1, r.height())
        # 1) 画中画小窗（最上层优先）
        for i in reversed(range(len(self._cells))):
            cl = self._cells[i]
            if not cl.get("pip"):
                continue
            x2, y2 = cl["x"] + cl["w"], cl["y"] + cl["h"]
            if abs(fx - x2) < tolx * 1.6 and abs(fy - y2) < toly * 1.6:
                return ("resize", i)
            if cl["x"] <= fx <= x2 and cl["y"] <= fy <= y2:
                return ("move", i)
        # 2) 普通格子的内部分界线
        best = None
        for cl in self._cells:
            if cl.get("pip"):
                continue
            for axis, v, lo, hi, d in (
                    ("x", cl["x"], cl["y"], cl["y"] + cl["h"], abs(fx - cl["x"])),
                    ("x", cl["x"] + cl["w"], cl["y"], cl["y"] + cl["h"], abs(fx - cl["x"] - cl["w"])),
                    ("y", cl["y"], cl["x"], cl["x"] + cl["w"], abs(fy - cl["y"])),
                    ("y", cl["y"] + cl["h"], cl["x"], cl["x"] + cl["w"], abs(fy - cl["y"] - cl["h"]))):
                if v <= 0.001 or v >= 0.999:
                    continue
                along = fy if axis == "x" else fx
                tol = tolx if axis == "x" else toly
                if d < tol and lo <= along <= hi and (best is None or d < best[3]):
                    best = ("edge", axis, v, d)
        if best:
            return best[:3]
        # 3) 普通格子内部 → 选中
        for i, cl in enumerate(self._cells):
            if not cl.get("pip") and cl["x"] <= fx <= cl["x"] + cl["w"] and cl["y"] <= fy <= cl["y"] + cl["h"]:
                return ("select", i)
        return None

    def mousePressEvent(self, e):
        if not self._draggable:
            return
        if self._cells is None:
            r = self._rect()
            if abs(e.position().y() - (r.top() + r.height() * self._split)) < 10:
                self._drag = ("split",)
            return
        hit = self._hit(e.position())
        if not hit:
            return
        fx, fy = self._to_frac(e.position())
        if hit[0] in ("move", "resize", "select"):
            self.cellSelected.emit(hit[1])
        if hit[0] == "move":
            cl = self._cells[hit[1]]
            self._drag = ("move", hit[1], fx - cl["x"], fy - cl["y"])
        elif hit[0] == "resize":
            cl = self._cells[hit[1]]
            self._drag = ("resize", hit[1], cl["h"] / max(1e-6, cl["w"]))
        elif hit[0] == "edge":
            self._drag = ("edge", hit[1], hit[2])

    def mouseMoveEvent(self, e):
        fx, fy = self._to_frac(e.position())
        d = self._drag
        if d is None:
            if self._draggable:
                hit = self._hit(e.position()) if self._cells is not None else None
                cur = Qt.CursorShape.ArrowCursor
                if self._cells is None:
                    r = self._rect()
                    if abs(e.position().y() - (r.top() + r.height() * self._split)) < 10:
                        cur = Qt.CursorShape.SizeVerCursor
                elif hit and hit[0] == "edge":
                    cur = Qt.CursorShape.SizeHorCursor if hit[1] == "x" else Qt.CursorShape.SizeVerCursor
                elif hit and hit[0] == "move":
                    cur = Qt.CursorShape.SizeAllCursor
                elif hit and hit[0] == "resize":
                    cur = Qt.CursorShape.SizeFDiagCursor
                self.setCursor(cur)
            return
        if d[0] == "split":
            ratio = max(0.05, min(0.95, fy))
            self._split = ratio
            self.splitDragged.emit(ratio)
            self.update()
            return
        m = self.MIN_FRAC
        if d[0] == "move":
            cl = self._cells[d[1]]
            cl["x"] = max(0.0, min(1 - cl["w"], fx - d[2]))
            cl["y"] = max(0.0, min(1 - cl["h"], fy - d[3]))
        elif d[0] == "resize":
            cl = self._cells[d[1]]
            w = max(m, min(1 - cl["x"], fx - cl["x"]))
            h = w * d[2]
            if cl["y"] + h > 1:
                h = 1 - cl["y"]
                w = h / d[2]
            cl["w"], cl["h"] = w, h
        elif d[0] == "edge":
            axis, v0 = d[1], d[2]
            pos, size = ("x", "w") if axis == "x" else ("y", "h")
            v = fx if axis == "x" else fy
            eps = 0.002
            before = [cl for cl in self._cells if not cl.get("pip") and abs(cl[pos] + cl[size] - v0) < eps]
            after = [cl for cl in self._cells if not cl.get("pip") and abs(cl[pos] - v0) < eps]
            lo = max([cl[pos] + m for cl in before] + [m])
            hi = min([cl[pos] + cl[size] - m for cl in after] + [1 - m])
            v = max(lo, min(hi, v))
            for cl in before:
                cl[size] = v - cl[pos]
            for cl in after:
                cl[size] = cl[pos] + cl[size] - v
                cl[pos] = v
            self._drag = ("edge", axis, v)
        self.cellsChanged.emit([dict(cl) for cl in self._cells])
        self.update()

    def mouseReleaseEvent(self, e):
        self._drag = None


class ScreenPicker(QWidget):
    colorPicked = pyqtSignal(QColor)
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)
        self.setGeometry(QApplication.primaryScreen().virtualGeometry())
        self._pos = QPoint(-1000, -1000)
        self._mag = None
        self._hex = ""

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 1))
        
        if self._mag and self._pos.x() > -1000:
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            cx = self._pos.x() + 40
            cy = self._pos.y() + 40
            
            sc = QApplication.screenAt(self._pos) or QApplication.primaryScreen()
            sg = sc.geometry()
            vx, vy, vw, vh = sg.x(), sg.y(), sg.width(), sg.height()
            
            r = 60
            if cx + r > vx + vw: cx = self._pos.x() - 40 - r
            if cy + r > vy + vh: cy = self._pos.y() - 40 - r
            
            p.setPen(QPen(QColor(200, 200, 200), 4))
            p.drawEllipse(cx, cy, r*2, r*2)
            
            path = QPainterPath()
            path.addEllipse(cx, cy, r*2, r*2)
            p.setClipPath(path)
            
            p.drawPixmap(cx, cy, self._mag)
            
            p.setPen(QPen(QColor(255, 255, 255, 180), 2))
            p.drawLine(cx + r - 10, cy + r, cx + r + 10, cy + r)
            p.drawLine(cx + r, cy + r - 10, cx + r, cy + r + 10)
            
            p.setClipping(False)
            p.setPen(Qt.GlobalColor.white)
            p.setBrush(QColor(0, 0, 0, 150))
            p.drawRect(cx + r - 35, cy + r*2 + 5, 70, 24)
            p.drawText(cx + r - 35, cy + r*2 + 5, 70, 24, Qt.AlignmentFlag.AlignCenter, self._hex)

    def mouseMoveEvent(self, event):
        pos = event.globalPosition().toPoint()
        self._pos = pos
        sc = QApplication.screenAt(pos) or QApplication.primaryScreen()
        
        rx = pos.x() - sc.geometry().x() - 7
        ry = pos.y() - sc.geometry().y() - 7
        px = sc.grabWindow(0, rx, ry, 15, 15)
        self._mag = px.scaled(120, 120, Qt.AspectRatioMode.KeepAspectRatio)
        self._hex = px.toImage().pixelColor(7, 7).name().upper()
        self.update()

    def mousePressEvent(self, event):
        self.hide()
        QApplication.processEvents()
        import time
        time.sleep(0.05)
        pos = event.globalPosition().toPoint()
        sc = QApplication.screenAt(pos) or QApplication.primaryScreen()
        px = sc.grabWindow(0, pos.x() - sc.geometry().x(), pos.y() - sc.geometry().y(), 1, 1)
        self.colorPicked.emit(px.toImage().pixelColor(0, 0))
        self.close()

    def keyPressEvent(self, event):
        self.close()


class ColorButton(QWidget):
    colorChanged = pyqtSignal()

    def __init__(self, color="#FFFFFF", parent=None):
        super().__init__(parent)
        self._color = color
        self.setFixedHeight(30)
        
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        
        self.btn_color = QPushButton()
        self.btn_color.setFixedHeight(30)
        self.btn_color.clicked.connect(self._pick)
        
        self.btn_drop = QPushButton()
        self.btn_drop.setFixedSize(30, 30)
        import os
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        icon_path = os.path.join(base_dir, "theme_icons", "eyedropper.svg")
        self.btn_drop.setIcon(QIcon(icon_path))
        self.btn_drop.setToolTip("屏幕吸管：点击后，再点击屏幕任意位置吸取颜色")
        self.btn_drop.clicked.connect(self._start_eyedropper)
        
        lay.addWidget(self.btn_color, 1)
        lay.addWidget(self.btn_drop)
        
        self._refresh()

    def color(self):
        return self._color

    def set_color(self, c):
        self._color = c
        self._refresh()

    def _refresh(self):
        txt = "#000000" if QColor(self._color).lightness() > 140 else "#FFFFFF"
        self.btn_color.setText(self._color.upper())
        self.btn_color.setStyleSheet(f"background-color: {self._color}; color: {txt}; "
                                     f"border: 1px solid #A0AEC0; border-radius: 6px;")

    def _pick(self):
        c = QColorDialog.getColor(QColor(self._color), self, "选择颜色", options=QColorDialog.ColorDialogOption.DontUseNativeDialog)
        if c.isValid():
            self.set_color(c.name())
            self.colorChanged.emit()

    def _start_eyedropper(self):
        self.picker = ScreenPicker()
        self.picker.colorPicked.connect(self._on_picked)
        self.picker.show()
        
    def _on_picked(self, c):
        self.set_color(c.name())
        self.colorChanged.emit()


class PasteDialog(QDialog):
    """批量粘贴对话框（从 Excel 复制一列内容粘贴）。"""
    def __init__(self, title, hint, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(520, 420)
        lay = QVBoxLayout(self)
        lbl = QLabel(hint)
        lbl.setWordWrap(True)
        lay.addWidget(lbl)
        self.edit = QPlainTextEdit()
        self.edit.setPlaceholderText("在此粘贴（Ctrl+V）……每行对应一个任务")
        lay.addWidget(self.edit)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                              QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def rows(self):
        return _parse_pasted(self.edit.toPlainText())


# ══════════════════════════════════════════════════════════════════════════════
#  后台线程
# ══════════════════════════════════════════════════════════════════════════════

def _persist_file(path: str) -> str:
    """把图片 / 字体复制到软件目录的卡片库中，返回库内路径（已在库中则原样返回）。"""
    if not path or not os.path.isfile(path):
        return path
    lib = os.path.abspath(get_card_lib_dir())
    ap = os.path.abspath(path)
    if os.path.dirname(ap).lower() == lib.lower():
        return ap
    h = hashlib.md5()
    with open(ap, "rb") as fp:
        for chunk in iter(lambda: fp.read(1 << 20), b""):
            h.update(chunk)
    stem, ext = os.path.splitext(os.path.basename(ap))
    dst = os.path.join(lib, f"{stem}_{h.hexdigest()[:8]}{ext}")
    if not os.path.isfile(dst):
        shutil.copy2(ap, dst)
    return dst


FONT_SAMPLE = "Gracias a Dios"   # “感谢上帝”（西班牙语）


class _FontSampleDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        return QSize(option.rect.width(), 50)

    def paint(self, p, opt, index):
        fam = index.data(Qt.ItemDataRole.UserRole)
        p.save()
        r = opt.rect
        if opt.state & QStyle.StateFlag.State_Selected:
            p.fillRect(r, QColor("#3182CE"))
            name_c = sample_c = QColor("#FFFFFF")
        else:
            if opt.state & QStyle.StateFlag.State_MouseOver:
                hc = QColor("#3182CE")
                hc.setAlpha(40)
                p.fillRect(r, hc)
            sample_c = opt.palette.color(QPalette.ColorRole.Text)
            name_c = QColor("#718096")
        nf = QFont(opt.font)
        nf.setPointSize(9)
        p.setFont(nf)
        p.setPen(name_c)
        p.drawText(r.adjusted(12, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   fam if len(fam) <= 26 else fam[:25] + "…")
        sf = QFont(fam)
        sf.setPixelSize(26)
        p.setFont(sf)
        p.setPen(sample_c)
        p.drawText(r.adjusted(230, 0, -10, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   FONT_SAMPLE)
        p.setPen(QPen(QColor(128, 128, 128, 60), 1))
        p.drawLine(r.bottomLeft(), r.bottomRight())
        p.restore()


class FontLibraryDialog(QDialog):
    """字体库：每个字体用同一句话「Gracias a Dios」展示样式，直观挑选。"""
    def __init__(self, current="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("🔤 字体库 —— 示例文字：Gracias a Dios（感谢上帝）")
        self.resize(720, 620)
        lay = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍 搜索字体名称……")
        self.search.textChanged.connect(self._filter)
        lay.addWidget(self.search)
        self.lst = QListWidget()
        self.lst.setMouseTracking(True)
        self.lst.setUniformItemSizes(True)
        self.lst.setItemDelegate(_FontSampleDelegate(self.lst))
        fams = [f for f in QFontDatabase.families() if not f.startswith("@")]
        for fam in fams:
            it = QListWidgetItem(fam)
            it.setData(Qt.ItemDataRole.UserRole, fam)
            self.lst.addItem(it)
            if fam == current:
                self.lst.setCurrentItem(it)
        if self.lst.currentItem():
            self.lst.scrollToItem(self.lst.currentItem(), QAbstractItemView.ScrollHint.PositionAtCenter)
        self.lst.itemDoubleClicked.connect(lambda *_: self.accept())
        lay.addWidget(self.lst, 1)
        lay.addWidget(QLabel(f"共 {len(fams)} 个字体。双击或选中后点「确定」即可使用；上传的本地字体也会出现在这里。"))
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _filter(self, txt):
        txt = txt.strip().lower()
        for i in range(self.lst.count()):
            it = self.lst.item(i)
            it.setHidden(bool(txt) and txt not in it.text().lower())

    def selected_family(self):
        it = self.lst.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else ""


class AlignThread(QThread):
    progress = pyqtSignal(int, int, str)
    done = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, items, mute_person, speed, out_dir, skip_align=False, parent=None):
        """items: [(主视频, [人物视频1, 人物视频2, ...]), ...]"""
        super().__init__(parent)
        self.items = items
        self.out_dir = out_dir
        self.mute_person = mute_person
        self.speed = speed
        self.skip_align = skip_align
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        out_dir = self.out_dir
        os.makedirs(out_dir, exist_ok=True)
        n = len(self.items)
        results = []
        for i, (vv, pvs) in enumerate(self.items):
            if self._stop:
                self.failed.emit("已取消对齐")
                return
            self.progress.emit(i, n, f"处理中 {i + 1}/{n}：{os.path.basename(vv)}")
            try:
                vi = probe_info(vv)
                persons = []
                dur = vi.get("duration", 0)
                for k, pv in enumerate(pvs):
                    if self.skip_align:
                        pi = probe_info(pv)
                        cache = pv
                        dur = max(dur, pi.get("duration", 0))
                    else:
                        stem = os.path.splitext(os.path.basename(pv))[0]
                        tag = "" if k == 0 else f"p{k + 1}_"
                        out = os.path.join(out_dir, f"{i + 1:03d}_{tag}{stem}_aligned.mp4")
                        r = align_person_video(pv, vv, out, self.mute_person, self.speed)
                        cache = r["cache"]
                        dur = r["duration"]
                        pi = probe_info(cache)
                    persons.append({"person": pv, "cache": cache, "w": pi.get("width", 1080),
                                    "h": pi.get("height", 1920), "audio": pi.get("has_audio", False)})
            except Exception as e:
                self.failed.emit(str(e))
                return
            p0 = persons[0]
            results.append({
                "person": p0["person"], "viral": vv, "task_dir": out_dir, "cache": p0["cache"], "duration": dur,
                "p_w": p0["w"], "p_h": p0["h"], "p_audio": p0["audio"],
                "v_w": vi.get("width", 1080), "v_h": vi.get("height", 1920), "v_audio": vi.get("has_audio", False),
                "extra": persons[1:],
            })
        self.progress.emit(n, n, "处理完成")
        self.done.emit(results)


class FrameThread(QThread):
    done = pyqtSignal(str, object, float, int)   # tag, {来源: png 字节}, t, req

    def __init__(self, tag, paths, t, req, parent=None):
        super().__init__(parent)
        self.tag, self.paths, self.t, self.req = tag, dict(paths), t, req

    def run(self):
        out = {k: (extract_frame_png(pth, self.t) if pth else b"") for k, pth in self.paths.items()}
        self.done.emit(self.tag, out, self.t, self.req)


class LayoutPickerDialog(QDialog):
    """新建模板时选择版式：常用 / 多格 / 画中画。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择画面版式")
        self.resize(520, 460)
        self.result_cells = None
        self.result_name = ""
        v = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self._lists = []
        groups = {}
        for tab, name, cells in LAYOUT_PRESETS:
            groups.setdefault(tab, []).append((name, cells))
        for tab, items in groups.items():
            lw = QListWidget()
            lw.setViewMode(QListWidget.ViewMode.IconMode)
            lw.setIconSize(QSize(54, 96))
            lw.setGridSize(QSize(150, 140))
            lw.setResizeMode(QListWidget.ResizeMode.Adjust)
            lw.setMovement(QListWidget.Movement.Static)
            for name, cells in items:
                it = QListWidgetItem(template_icon(template_from_cells(name, cells)), name)
                it.setData(Qt.ItemDataRole.UserRole, (name, cells))
                lw.addItem(it)
            lw.itemDoubleClicked.connect(lambda *_: self._accept())
            self.tabs.addTab(lw, tab)
            self._lists.append(lw)
        v.addWidget(self.tabs, 1)
        tip = QLabel("格子里的数字：1 = 主视频，2/3/4/5 = 人物视频1/2/3/4。创建后可在右侧修改每个格子放哪个视频。")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#718096;")
        v.addWidget(tip)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def _accept(self):
        lw = self._lists[self.tabs.currentIndex()]
        it = lw.currentItem()
        if it is None:
            QMessageBox.information(self, "提示", "请先选择一个版式。")
            return
        self.result_name, self.result_cells = it.data(Qt.ItemDataRole.UserRole)
        self.accept()


class RenderThread(QThread):
    progress = pyqtSignal(int, int)
    task_progress = pyqtSignal(int, float)
    log = pyqtSignal(str)
    finished_all = pyqtSignal(int, int)

    def __init__(self, jobs, workers, enc_key, parent=None):
        super().__init__(parent)
        self.jobs, self.workers, self.enc_key = jobs, workers, enc_key

    def run(self):
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import subprocess

        def run_with_progress(cmd, dur, idx):
            p = subprocess.Popen(cmd, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="ignore", creationflags=0x08000000)
            err_lines = []
            for line in p.stderr:
                err_lines.append(line)
                if "time=" in line:
                    try:
                        t_str = line.split("time=")[1].split(" ")[0]
                        h, m, s = t_str.split(":")
                        sec = int(h)*3600 + int(m)*60 + float(s)
                        if dur > 0:
                            pct = min(99.0, sec / dur * 100.0)
                            self.task_progress.emit(idx, pct)
                    except:
                        pass
            p.wait()
            return p.returncode, "".join(err_lines)

        def work(job):
            try:
                return _work(job)
            except Exception as e:
                import traceback
                return job, -1, traceback.format_exc(), False

        def _work(job):
            idx = job.get("index", 0)
            dur = job["task"]["duration"] / max(0.1, job["kw"].get("global_speed", 1.0))
            if job["kw"].get("max_3min") and dur > 180:
                dur = 180

            self.task_progress.emit(idx, 1.0)
            cmd = build_render_cmd(job["task"], job["tpl"], job["out"], enc_key=self.enc_key, **job["kw"])
            rc, err = run_with_progress(cmd, dur, idx)
            fb = False
            if rc != 0 and self.enc_key != "cpu":
                fb = True
                cmd = build_render_cmd(job["task"], job["tpl"], job["out"], enc_key="cpu", **job["kw"])
                rc, err = run_with_progress(cmd, dur, idx)
            if rc == 0:
                self.task_progress.emit(idx, 100.0)
            return job, rc, err, fb

        n = len(self.jobs)
        ok = 0
        done = 0
        with ThreadPoolExecutor(max_workers=max(1, min(4, self.workers))) as ex:
            futs = [ex.submit(work, j) for j in self.jobs]
            for f in as_completed(futs):
                job, rc, err, fb = f.result()
                done += 1
                name = os.path.basename(job["out"])
                if rc == 0:
                    ok += 1
                    self.log.emit(f"✅ 完成：{name}" + ("（GPU 失败，已自动改用 CPU）" if fb else ""))
                else:
                    self.log.emit(f"❌ 失败：{name}\n{(err or '')[-600:]}")
                self.progress.emit(done, n)
        self.finished_all.emit(ok, n)


# ══════════════════════════════════════════════════════════════════════════════
#  卡片参数编辑器
# ══════════════════════════════════════════════════════════════════════════════

class CardEditor(QWidget):
    changed = pyqtSignal()

    def __init__(self, kind="title", parent=None):
        super().__init__(parent)
        self.kind = kind
        self.w = {}
        self._font_file = ""
        self._loading = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # 预设
        pr = QHBoxLayout()
        self.cmb_preset = QComboBox()
        self.cmb_preset.setMinimumWidth(120)
        self.cmb_preset.activated.connect(self._apply_preset)
        
        pr.addWidget(QLabel("预设:"))
        pr.addWidget(self.cmb_preset, 1)
        
        import os
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        b_rename = QPushButton()
        b_rename.setIcon(QIcon(os.path.join(base_dir, "theme_icons", "rename.svg")))
        b_rename.setFixedSize(32, 32)
        b_rename.setToolTip("重命名当前预设")
        b_rename.clicked.connect(self._rename_preset)
        pr.addWidget(b_rename)
        
        b_update = QPushButton()
        b_update.setIcon(QIcon(os.path.join(base_dir, "theme_icons", "update.svg")))
        b_update.setFixedSize(32, 32)
        b_update.setToolTip("将当前修改更新到此预设")
        b_update.clicked.connect(self._update_preset)
        pr.addWidget(b_update)
        
        b_save_as = QPushButton()
        b_save_as.setIcon(QIcon(os.path.join(base_dir, "theme_icons", "save_as.svg")))
        b_save_as.setFixedSize(32, 32)
        b_save_as.setToolTip("另存为新的预设")
        b_save_as.clicked.connect(self._save_preset)
        pr.addWidget(b_save_as)
        
        b_del = QPushButton()
        b_del.setIcon(QIcon(os.path.join(base_dir, "theme_icons", "delete.svg")))
        b_del.setFixedSize(32, 32)
        b_del.setToolTip("删除选中的预设")
        b_del.clicked.connect(self._del_preset)
        pr.addWidget(b_del)
        
        # 加一个竖线分隔符
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        pr.addWidget(line)
        
        b_import = QPushButton()
        b_import.setIcon(QIcon(os.path.join(base_dir, "theme_icons", "import.svg")))
        b_import.setFixedSize(32, 32)
        b_import.setToolTip("导入预设 (支持导入单个或批量预设文件)")
        b_import.clicked.connect(self._import_preset)
        pr.addWidget(b_import)
        
        b_export = QPushButton()
        b_export.setIcon(QIcon(os.path.join(base_dir, "theme_icons", "export.svg")))
        b_export.setFixedSize(32, 32)
        b_export.setToolTip("导出当前选中的预设")
        b_export.clicked.connect(self._export_preset)
        pr.addWidget(b_export)
        
        outer.addLayout(pr)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        self.vbox = QVBoxLayout(inner)
        self.vbox.setSpacing(10)
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        g = self._group("⏱ 时间线与类型")
        self._add(g, "enabled", "check", "启用该卡片")
        self._add(g, "mode", "combo", "卡片类型", items=[("text", "文字卡片"), ("image", "图片卡片（贴图）")])
        self._add(g, "time", "dspin",
                  "结束时间(秒)" if kind == "title" else "开始时间(秒)", rng=(0, 3600), step=0.5)
        tip = QLabel("标题卡片固定从 0 秒开始" if kind == "title" else "电话卡片固定持续到视频结尾")
        tip.setStyleSheet("color:#718096;")
        g.addRow("", tip)

        g = self._group("🖼 图片卡片")
        self._add(g, "image_path", "file", "图片文件")
        self._add(g, "image_scale", "spin", "缩放(%)", rng=(1, 1000))

        g = self._group("🅰 文本基础属性")
        self._add(g, "font_family", "font", "字体")
        b_lib = QPushButton("🔤 打开字体库（直观预览样式）")
        b_lib.clicked.connect(self._open_font_lib)
        g.addRow("", b_lib)
        b_font = QPushButton("📂 上传本地字体 (ttf/otf)")
        b_font.clicked.connect(self._upload_font)
        g.addRow("", b_font)
        self.lbl_font_file = QLabel("")
        self.lbl_font_file.setStyleSheet("color:#718096;")
        g.addRow("", self.lbl_font_file)
        self._add(g, "size", "spin", "字号", rng=(6, 400))
        self._add(g, "bold", "check", "加粗 (B)")
        self._add(g, "italic", "check", "斜体 (I)")
        self._add(g, "weight", "combo", "字重",
                  items=[(v, str(v)) for v in (100, 200, 300, 400, 500, 600, 700, 800, 900)])
        self._add(g, "letter_spacing", "dspin", "文字间距", rng=(-50, 200), step=1)
        self._add(g, "rtl", "combo", "文字方向", items=[(False, "自动 / 从左到右"), (True, "阿拉伯语 RTL")])
        self._add(g, "color", "color", "常规颜色")
        self._add(g, "hl_color", "color", "高亮颜色")
        self._add(g, "line_spacing", "dspin", "行间距", rng=(-100, 300), step=1)

        g = self._group("🎨 自动着色规则")
        self._add(g, "keywords", "line", "关键词", placeholder="多个关键词用逗号分隔")
        self._add(g, "hl_numbers", "check", "数字高亮")
        self._add(g, "hl_english", "check", "英文高亮")


        g = self._group("🅱 换行后独立样式 (双色底框)")
        self._add(g, "sub_enabled", "check", "启用首行/次行独立排版")
        self._add(g, "split", "combo", "底框拆分模式", items=[("none", "单色连体"), ("vertical", "上下双色分离")])
        self._add(g, "split_color2", "color", "次行底框颜色")
        self._add(g, "split_alpha2", "spin", "次行底框透明度", rng=(0, 255))
        self._add(g, "sub_size", "spin", "次行字号", rng=(6, 400))
        self._add(g, "sub_color", "color", "次行文本颜色")
        self._add(g, "sub_hl_color", "color", "次行高亮颜色")
        self._add(g, "sub_stroke", "check", "次行启用描边")
        self._add(g, "sub_stroke_color", "color", "次行描边颜色")
        self._add(g, "sub_stroke_width", "spin", "次行描边宽度", rng=(0, 60))

        g = self._group("✒ 描边与特效")
        self._add(g, "stroke", "check", "启用基础描边")
        self._add(g, "stroke_color", "color", "描边颜色")
        self._add(g, "stroke_width", "spin", "描边宽度", rng=(0, 60))
        self._add(g, "shadow", "check", "启用阴影")
        self._add(g, "shadow_color", "color", "阴影颜色")
        self._add(g, "shadow_blur", "spin", "模糊度", rng=(0, 40))
        self._add(g, "shadow_x", "spin", "X 偏移", rng=(-100, 100))
        self._add(g, "shadow_y", "spin", "Y 偏移", rng=(-100, 100))
        self._add(g, "multi_stroke", "check", "启用多层扩展描边")
        self._add(g, "ms_layers", "spin", "扩展层数", rng=(1, 10))
        self._add(g, "ms_step", "spin", "步进值", rng=(1, 60))
        self._add(g, "ms_feather", "spin", "羽化值", rng=(0, 20))
        self._add(g, "ms_colors", "line", "各层颜色", placeholder="由内到外，逗号分隔，如 #FFFFFF,#E53E3E")

        g = self._group("🟫 字幕背景与装饰")
        self._add(g, "bg", "check", "启用字幕底框")
        self._add(g, "bg_fit", "check", "贴合行宽")
        self._add(g, "bg_shape", "combo", "底框形状", items=[
            ("hug", "紧密包裹 (无缝连体)"),
            ("rect", "直角长方形"),
            ("rounded", "圆角长方形"),
            ("pill", "胶囊形状"),
            ("notch", "切角多边形"),
            ("ribbon", "丝带/燕尾"),
            ("bow", "向内凹多边形"),
            ("wave", "底部波浪"),
            ("torn", "撕裂边缘"),
        ])
        self._add(g, "bg_color", "color", "底框颜色")
        self._add(g, "bg_alpha", "spin", "透明度 (0-255)", rng=(0, 255))
        self._add(g, "bg_radius", "spin", "圆角", rng=(0, 200))
        self._add(g, "bg_pad_x", "spin", "内距 X", rng=(0, 300))
        self._add(g, "bg_pad_y", "spin", "内距 Y", rng=(0, 300))

        g = self._group("📐 排版与定位")
        self._add(g, "snap_split", "check", "以分割线为中心（Y 吸附分割线，X 居中）")
        self._add(g, "pos_x", "spin", "位置 X (中心)", rng=(-2000, 3000), step=10)
        self._add(g, "pos_y", "spin", "位置 Y (中心)", rng=(-2000, 4000), step=10)
        self._add(g, "width", "spin", "限定宽度", rng=(50, 3000))
        self._add(g, "wrap", "check", "超长字幕自动断行")
        self._add(g, "line_spacing", "spin", "行距", rng=(-100, 300))
        self._add(g, "rand_height", "spin", "随机高度 (%)", rng=(0, 50))
        self._add(g, "rotation", "spin", "旋转角度", rng=(0, 360))
        self._add(g, "show_range", "check", "显示字幕范围辅助线（仅预览）")
        self.vbox.addStretch()

        self.w["snap_split"].toggled.connect(self._update_enabled)
        self.w["mode"].currentIndexChanged.connect(self._update_enabled)
        self.reload_presets()
        self.set_cfg(default_card(kind))

    # ---- 构建 ----
    def _group(self, title):
        box = QGroupBox(title)
        form = QFormLayout(box)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.vbox.addWidget(box)
        return form

    def _add(self, form, key, typ, label, **opt):
        if typ == "check":
            wd = QCheckBox(label)
            wd.toggled.connect(self._emit)
            form.addRow("", wd)
        else:
            if typ == "spin":
                wd = QSpinBox()
                wd.setRange(*opt.get("rng", (0, 100)))
                wd.setSingleStep(opt.get("step", 1))
                wd.valueChanged.connect(self._emit)
            elif typ == "dspin":
                wd = QDoubleSpinBox()
                wd.setRange(*opt.get("rng", (0, 100)))
                wd.setSingleStep(opt.get("step", 0.1))
                wd.setDecimals(1)
                wd.valueChanged.connect(self._emit)
            elif typ == "color":
                wd = ColorButton()
                wd.colorChanged.connect(self._emit)
            elif typ == "line":
                wd = QLineEdit()
                wd.setPlaceholderText(opt.get("placeholder", ""))
                wd.textChanged.connect(self._emit)
            elif typ == "combo":
                wd = QComboBox()
                for val, txt in opt["items"]:
                    wd.addItem(txt, val)
                wd.currentIndexChanged.connect(self._emit)
            elif typ == "font":
                wd = QFontComboBox()
                wd.currentFontChanged.connect(self._on_font_combo)
            elif typ == "file":
                wd = QWidget()
                h = QHBoxLayout(wd)
                h.setContentsMargins(0, 0, 0, 0)
                le = QLineEdit()
                le.textChanged.connect(self._emit)
                b = QPushButton("选择…")
                b.clicked.connect(lambda: self._pick_image(le))
                h.addWidget(le)
                h.addWidget(b)
                wd.line = le
            lbl_w = QLabel(label)
            lbl_w.setWordWrap(True)
            form.addRow(lbl_w, wd)
        self.w[key] = wd
        wd._typ = typ

    # ---- 事件 ----
    def _emit(self, *a):
        if not self._loading:
            # Synchronize bold checkbox and weight combobox
            sender = self.sender()
            if sender and "bold" in self.w and "weight" in self.w:
                if sender == self.w["bold"]:
                    is_bold = self.w["bold"].isChecked()
                    # if bold is checked and weight is regular, change to bold
                    if is_bold and self.w["weight"].currentData() < 600:
                        idx = self.w["weight"].findData(700)
                        if idx >= 0: self.w["weight"].setCurrentIndex(idx)
                    # if bold is unchecked and weight is bold/black, change to regular
                    elif not is_bold and self.w["weight"].currentData() >= 600:
                        idx = self.w["weight"].findData(400)
                        if idx >= 0: self.w["weight"].setCurrentIndex(idx)
                elif sender == self.w["weight"]:
                    is_bold = self.w["weight"].currentData() >= 600
                    if self.w["bold"].isChecked() != is_bold:
                        self.w["bold"].blockSignals(True)
                        self.w["bold"].setChecked(is_bold)
                        self.w["bold"].blockSignals(False)

            self.changed.emit()

    def _on_font_combo(self, f):
        if self._font_file and load_font_file(self._font_file) != f.family():
            self._font_file = ""
            self.lbl_font_file.setText("")
        self._emit()

    def _upload_font(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择字体文件", "", "字体文件 (*.ttf *.otf *.ttc)")
        if not path:
            return
        fam = load_font_file(path)
        if not fam:
            QMessageBox.warning(self, "字体加载失败", "无法读取该字体文件。")
            return
        self._font_file = path
        self._loading = True
        self.w["font_family"].setCurrentFont(QFont(fam))
        self._loading = False
        self.lbl_font_file.setText(f"已加载：{os.path.basename(path)}")
        self._emit()

    def _open_font_lib(self):
        dlg = FontLibraryDialog(self.w["font_family"].currentFont().family(), self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.selected_family():
            self.w["font_family"].setCurrentFont(QFont(dlg.selected_family()))

    def _pick_image(self, le):
        path, _ = QFileDialog.getOpenFileName(self, "选择图片", "", "图片 (*.png *.jpg *.jpeg *.webp *.bmp)")
        if path:
            le.setText(path)
            # 选择图片后自动切换为「图片卡片」，否则仍显示文字卡片
            self.w["mode"].setCurrentIndex(max(0, self.w["mode"].findData("image")))

    def _update_enabled(self, *a):
        snap = self.w["snap_split"].isChecked()
        self.w["pos_x"].setEnabled(not snap)
        self.w["pos_y"].setEnabled(not snap)

    # ---- 读写 ----
    def get_cfg(self):
        cfg = default_card(self.kind)
        for k, wd in self.w.items():
            t = wd._typ
            if t == "check":
                cfg[k] = wd.isChecked()
            elif t in ("spin", "dspin"):
                cfg[k] = wd.value()
            elif t == "color":
                cfg[k] = wd.color()
            elif t == "line":
                cfg[k] = wd.text()
            elif t == "combo":
                cfg[k] = wd.currentData()
            elif t == "font":
                cfg[k] = wd.currentFont().family()
            elif t == "file":
                cfg[k] = wd.line.text()
        cfg["font_file"] = self._font_file
        return cfg

    def set_cfg(self, cfg):
        base = default_card(self.kind)
        base.update(cfg or {})
        self._loading = True
        self._font_file = base.get("font_file", "")
        if self._font_file:
            fam = load_font_file(self._font_file)
            if fam:
                base["font_family"] = fam
                self.lbl_font_file.setText(f"已加载：{os.path.basename(self._font_file)}")
            else:
                self._font_file = ""
        else:
            self.lbl_font_file.setText("")
        for k, wd in self.w.items():
            v = base.get(k)
            t = wd._typ
            try:
                if t == "check":
                    wd.setChecked(bool(v))
                elif t == "spin":
                    wd.setValue(int(v))
                elif t == "dspin":
                    wd.setValue(float(v))
                elif t == "color":
                    wd.set_color(v)
                elif t == "line":
                    wd.setText(str(v))
                elif t == "combo":
                    i = wd.findData(v)
                    wd.setCurrentIndex(max(0, i))
                elif t == "font":
                    wd.setCurrentFont(QFont(v))
                elif t == "file":
                    wd.line.setText(str(v))
            except Exception:
                pass
        self._loading = False
        self._update_enabled()
        self.changed.emit()

    # ---- 预设（卡片库） ----
    def reload_presets(self):
        presets = _get_all_presets()
        self.cmb_preset.blockSignals(True)
        self.cmb_preset.clear()
        self.cmb_preset.addItem("— 选择预设 —", None)
        
        user_presets = []
        default_presets = []
        
        for name, cfg in presets.items():
            is_user = cfg.get("_is_user")
            
            if is_user is None:
                if name.startswith("热门 -") or name in [
                    '黄金强光贴纸 (El Resplandor Dorado)', '霓虹青空发光体 (Cielo Neón)', '街头冲击 (Impacto Urbano)', 
                    '纯净极简 (Minimalismo Puro)', '复古报纸 (Titular de Prensa)', '警戒红幕 (Alerta Roja)', 
                    '深海权威 (Autoridad Profunda)', '复古羊皮纸 (Pergamino Clásico)', '活力柑橘 (Cítrico Vibrante)', 
                    '极简白盒 (Caja Blanca Minimalista)', '暗流暗盒 (Caja Oscura)', '紫水晶滤镜 (Filtro Amatista)', 
                    '毛玻璃翠绿 (Verde Esmerilado)', '赛博深灰 (Gris Cibernético)', '柔和米黄带 (Cinta Beige Suave)', 
                    '官方生态分层 (Ecosistema WhatsApp)', '专业深海拼图 (Azul Profesional)', '极简黑白交界 (Frontera Monocromática)', 
                    '牧师呼召紫带 (Llamado Pastoral)', '黄金金融分割 (División Financiera)', '磨砂白玉胶囊 (Vidrio Esmerilado)', 
                    '暗夜流金 (Noche Dorada)', '翠绿信任盾牌 (Escudo Verde)', '极简半透黑盒 (Caja Translúcida)', 
                    '纯白云朵悬浮 (Nube Blanca)', '红色下划线警告 (Subrayado Urgente)', '警戒黄黑封条 (Cinta de Precaución)', 
                    '荧光焦点框 (Marco de Enfoque Neón)', '优惠警报红底 (Alerta de Oferta)', '科技蓝图指示牌 (Plano Tecnológico)'
                ]:
                    is_user = False
                else:
                    is_user = True
                    
            kind = cfg.get("_kind")
            if kind is None:
                kind = "phone" if "电话" in name else "title"
            if kind == self.kind:
                if is_user:
                    user_presets.append(name)
                else:
                    default_presets.append(name)
                
        user_presets.reverse()
        
        if user_presets:
            self.cmb_preset.addItem("—— 我的预设 ——", None)
            item_model = self.cmb_preset.model()
            item_model.item(self.cmb_preset.count()-1).setEnabled(False)
            
            for name in user_presets:
                self.cmb_preset.addItem(name, name)
                
        if default_presets:
            self.cmb_preset.addItem("—— 默认预设 ——", None)
            item_model = self.cmb_preset.model()
            item_model.item(self.cmb_preset.count()-1).setEnabled(False)
            
            for name in default_presets:
                self.cmb_preset.addItem(name, name)

        self.cmb_preset.blockSignals(False)

    def _apply_preset(self, idx):
        name = self.cmb_preset.itemData(idx)
        if not name:
            return
        presets = _get_all_presets()
        if name in presets:
            cfg = dict(presets[name])
            cfg["time"] = self.w["time"].value()   # 时间线不随预设改变
            self.set_cfg(cfg)

    def _get_preset_cfg_to_save(self):
        cfg = self.get_cfg()
        cfg["_kind"] = self.kind
        cfg["_is_user"] = True
        try:
            if cfg.get("image_path"):
                cfg["image_path"] = _persist_file(cfg["image_path"])
                self.w["image_path"].line.setText(cfg["image_path"])
            if cfg.get("font_file"):
                cfg["font_file"] = _persist_file(cfg["font_file"])
                self._font_file = cfg["font_file"]
                load_font_file(self._font_file)
        except Exception as e:
            QMessageBox.warning(self, "复制失败", f"无法把文件保存到卡片库：{e}")
        return cfg

    def _save_preset(self):
        name, ok = QInputDialog.getText(self, "另存为预设", "新预设名称:")
        if not ok or not name.strip():
            return
        presets = _load_json("card_presets.json", {})
        presets[name.strip()] = self._get_preset_cfg_to_save()
        _save_json("card_presets.json", presets)
        self.reload_presets()
        self.cmb_preset.setCurrentIndex(self.cmb_preset.findData(name.strip()))

    def _update_preset(self):
        name = self.cmb_preset.currentData()
        if not name:
            return
        presets = _load_json("card_presets.json", {})
        if name not in presets or presets.get(name, {}).get("_is_user") is False:
            QMessageBox.warning(self, "提示", "这是内置默认预设，无法更新。请使用【另存为】创建新预设。")
            return
        presets[name] = self._get_preset_cfg_to_save()
        _save_json("card_presets.json", presets)
        QMessageBox.information(self, "成功", f"预设 '{name}' 已更新！")

    def _rename_preset(self):
        old_name = self.cmb_preset.currentData()
        if not old_name:
            return
        presets = _load_json("card_presets.json", {})
        if old_name not in presets or presets.get(old_name, {}).get("_is_user") is False:
            QMessageBox.warning(self, "提示", "这是内置默认预设，无法重命名。")
            return
        new_name, ok = QInputDialog.getText(self, "重命名预设", "新名称:", text=old_name)
        if not ok or not new_name.strip() or new_name.strip() == old_name:
            return
        new_name = new_name.strip()
        if new_name in presets:
            QMessageBox.warning(self, "提示", "该名称已存在！")
            return
        presets[new_name] = presets.pop(old_name)
        _save_json("card_presets.json", presets)
        self.reload_presets()
        self.cmb_preset.setCurrentIndex(self.cmb_preset.findData(new_name))

    def _del_preset(self):
        name = self.cmb_preset.currentData()
        if not name:
            return
        presets = _load_json("card_presets.json", {})
        if name not in presets or presets.get(name, {}).get("_is_user") is False:
            QMessageBox.warning(self, "提示", "这是内置默认预设，无法删除。")
            return
        reply = QMessageBox.question(self, "确认删除", f"确定要删除预设 '{name}' 吗？",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            presets.pop(name, None)
            _save_json("card_presets.json", presets)
            self.reload_presets()

    def _export_preset(self):
        import json
        from PyQt6.QtWidgets import QFileDialog
        
        # 导出所有的预设（包括默认和用户自定义的）
        presets = _get_all_presets()
        if not presets:
            QMessageBox.warning(self, "提示", "当前没有任何预设可导出。")
            return
            
        save_path, _ = QFileDialog.getSaveFileName(self, "导出所有预设", "全部预设备份.json", "JSON Files (*.json)")
        if not save_path:
            return
            
        try:
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(presets, f, ensure_ascii=False, indent=4)
            QMessageBox.information(self, "成功", f"成功导出了 {len(presets)} 个预设！\n（包含内置预设及自定义预设）")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"导出失败: {e}")

    def _import_preset(self):
        import json
        from PyQt6.QtWidgets import QFileDialog
        
        open_paths, _ = QFileDialog.getOpenFileNames(self, "导入预设", "", "JSON Files (*.json)")
        if not open_paths:
            return
            
        presets = _load_json("card_presets.json", {})
        imported_count = 0
        
        for p in open_paths:
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                # 检查是单个预设字典还是包含了多个预设的字典
                if "_kind" in data:  # 这是一个裸的预设数据，没有外层名称，用文件名当名称
                    name = os.path.splitext(os.path.basename(p))[0]
                    data["_is_user"] = True
                    presets[name] = data
                    imported_count += 1
                else: # 这是一个包含多个预设的字典
                    for k, v in data.items():
                        if isinstance(v, dict):
                            v["_is_user"] = True
                            presets[k] = v
                            imported_count += 1
            except Exception as e:
                QMessageBox.warning(self, "错误", f"读取文件 {os.path.basename(p)} 失败: {e}")
                
        if imported_count > 0:
            _save_json("card_presets.json", presets)
            self.reload_presets()
            QMessageBox.information(self, "成功", f"成功导入了 {imported_count} 个预设！")


# ══════════════════════════════════════════════════════════════════════════════
#  主界面
# ══════════════════════════════════════════════════════════════════════════════



class WatermarkItemWidget(QFrame):
    changed = pyqtSignal()
    deleteRequested = pyqtSignal(QWidget)

    def __init__(self, cfg=None, parent=None):
        super().__init__(parent)
        self.setProperty("class", "Card")
        self.setStyleSheet("QFrame.Card { border: 1px solid #4A5568; border-radius: 8px; margin-bottom: 10px; padding: 10px; background-color: #2D3748; }")
        
        from image_worker.duet_render import default_watermark
        self.cfg = default_watermark()
        if cfg:
            self.cfg.update(cfg)

        self.vbox = QVBoxLayout(self)
        self.vbox.setContentsMargins(10, 10, 10, 10)
        
        # Header: Enabled, Type, Delete
        top_lay = QHBoxLayout()
        self.chk_enabled = QCheckBox("启用")
        self.chk_enabled.setChecked(self.cfg.get("enabled", True))
        self.chk_enabled.toggled.connect(self._on_change)
        top_lay.addWidget(self.chk_enabled)
        
        top_lay.addWidget(QLabel("类型:"))
        self.cmb_type = QComboBox()
        self.cmb_type.addItem("文字", "text")
        self.cmb_type.addItem("图片", "image")
        self.cmb_type.setCurrentIndex(max(0, self.cmb_type.findData(self.cfg.get("type", "text"))))
        self.cmb_type.currentIndexChanged.connect(self._on_type_change)
        top_lay.addWidget(self.cmb_type)
        
        top_lay.addStretch()
        self.btn_del = QPushButton("删除")
        self.btn_del.setStyleSheet("color: red; font-weight: bold;")
        self.btn_del.setFixedWidth(50)
        self.btn_del.clicked.connect(lambda: self.deleteRequested.emit(self))
        top_lay.addWidget(self.btn_del)
        self.vbox.addLayout(top_lay)
        
        # Stacked widget for type-specific fields
        self.stack = QStackedWidget()
        self.vbox.addWidget(self.stack)
        
        # Text Page
        self.page_text = QWidget()
        form_text = QFormLayout(self.page_text)
        form_text.setContentsMargins(0, 5, 0, 0)
        
        self.txt_text = QPlainTextEdit()
        self.txt_text.setFixedHeight(50)
        self.txt_text.setPlainText(self.cfg.get("text", ""))
        self.txt_text.textChanged.connect(self._on_change)
        form_text.addRow("文本内容:", self.txt_text)
        
        self.cmb_font = QFontComboBox()
        self.cmb_font.setCurrentFont(QFont(self.cfg.get("font_family", "Microsoft YaHei")))
        self.cmb_font.currentFontChanged.connect(self._on_change)
        form_text.addRow("字体:", self.cmb_font)
        
        row_fs = QHBoxLayout()
        self.spin_fs = QSpinBox()
        self.spin_fs.setRange(6, 400)
        self.spin_fs.setValue(int(self.cfg.get("font_size", 32)))
        self.spin_fs.valueChanged.connect(self._on_change)
        row_fs.addWidget(self.spin_fs)
        
        self.btn_color = ColorButton(self.cfg.get("color", "#FFFFFF"))
        self.btn_color.colorChanged.connect(self._on_change)
        row_fs.addWidget(QLabel("颜色:"))
        row_fs.addWidget(self.btn_color)
        
        self.spin_t_alpha = QSpinBox()
        self.spin_t_alpha.setRange(0, 100)
        self.spin_t_alpha.setValue(int(self.cfg.get("text_opacity", 100)))
        self.spin_t_alpha.valueChanged.connect(self._on_change)
        row_fs.addWidget(QLabel("透明%: "))
        row_fs.addWidget(self.spin_t_alpha)
        form_text.addRow("字号颜色:", row_fs)
        
        row_bg = QHBoxLayout()
        self.btn_bg = ColorButton(self.cfg.get("bg_color", "#000000"))
        self.btn_bg.colorChanged.connect(self._on_change)
        row_bg.addWidget(self.btn_bg)
        
        self.spin_b_alpha = QSpinBox()
        self.spin_b_alpha.setRange(0, 100)
        self.spin_b_alpha.setValue(int(self.cfg.get("bg_opacity", 50)))
        self.spin_b_alpha.valueChanged.connect(self._on_change)
        row_bg.addWidget(QLabel("底透明%: "))
        row_bg.addWidget(self.spin_b_alpha)
        row_bg.addStretch()
        form_text.addRow("底色:", row_bg)
        
        self.stack.addWidget(self.page_text)
        
        # Image Page
        self.page_img = QWidget()
        form_img = QFormLayout(self.page_img)
        form_img.setContentsMargins(0, 5, 0, 0)
        
        row_file = QHBoxLayout()
        self.txt_file = QLineEdit(self.cfg.get("image_path", ""))
        self.txt_file.textChanged.connect(self._on_change)
        btn_pick = QPushButton("选择...")
        btn_pick.clicked.connect(self._pick_file)
        row_file.addWidget(self.txt_file)
        row_file.addWidget(btn_pick)
        form_img.addRow("图片文件:", row_file)
        
        self.spin_scale = QSpinBox()
        self.spin_scale.setRange(1, 1000)
        self.spin_scale.setValue(int(self.cfg.get("scale", 30)))
        self.spin_scale.valueChanged.connect(self._on_change)
        form_img.addRow("缩放(%):", self.spin_scale)
        
        self.spin_i_alpha = QSpinBox()
        self.spin_i_alpha.setRange(0, 100)
        self.spin_i_alpha.setValue(int(self.cfg.get("opacity", 100)))
        self.spin_i_alpha.valueChanged.connect(self._on_change)
        form_img.addRow("透明度(%):", self.spin_i_alpha)
        
        row_flip = QHBoxLayout()
        self.chk_fh = QCheckBox("左右翻转")
        self.chk_fh.setChecked(self.cfg.get("flip_h", False))
        self.chk_fh.toggled.connect(self._on_change)
        row_flip.addWidget(self.chk_fh)
        
        self.chk_fv = QCheckBox("上下翻转")
        self.chk_fv.setChecked(self.cfg.get("flip_v", False))
        self.chk_fv.toggled.connect(self._on_change)
        row_flip.addWidget(self.chk_fv)
        row_flip.addStretch()
        form_img.addRow("翻转:", row_flip)
        
        self.stack.addWidget(self.page_img)
        
        # Common Position
        form_pos = QFormLayout()
        
        self.cmb_pos = QComboBox()
        for v, t in [("tl", "左上"), ("tr", "右上"), ("bl", "左下"), ("br", "右下"), ("bc", "居中")]:
            self.cmb_pos.addItem(t, v)
        self.cmb_pos.setCurrentIndex(max(0, self.cmb_pos.findData(self.cfg.get("position", "br"))))
        self.cmb_pos.currentIndexChanged.connect(self._on_change)
        form_pos.addRow("位置:", self.cmb_pos)
        
        row_xy = QHBoxLayout()
        self.spin_ox = QSpinBox()
        self.spin_ox.setRange(-2000, 2000)
        self.spin_ox.setValue(int(self.cfg.get("ox", 0)))
        self.spin_ox.valueChanged.connect(self._on_change)
        row_xy.addWidget(QLabel("X:"))
        row_xy.addWidget(self.spin_ox)
        
        self.spin_oy = QSpinBox()
        self.spin_oy.setRange(-2000, 2000)
        self.spin_oy.setValue(int(self.cfg.get("oy", 0)))
        self.spin_oy.valueChanged.connect(self._on_change)
        row_xy.addWidget(QLabel("Y:"))
        row_xy.addWidget(self.spin_oy)
        row_xy.addStretch()
        form_pos.addRow("偏移:", row_xy)
        
        self.vbox.addLayout(form_pos)
        
        self._sync_type()
        self._updating = False

    def _sync_type(self):
        t = self.cmb_type.currentData()
        self.stack.setCurrentWidget(self.page_text if t == "text" else self.page_img)

    def _on_type_change(self):
        self._sync_type()
        self._on_change()

    def _pick_file(self):
        p, _ = QFileDialog.getOpenFileName(self, "选择图片", "", "图片 (*.png *.jpg *.jpeg *.webp *.bmp)")
        if p:
            self.txt_file.setText(p)

    def _on_change(self, *a):
        if getattr(self, "_updating", False):
            return
        self.cfg["enabled"] = self.chk_enabled.isChecked()
        self.cfg["type"] = self.cmb_type.currentData()
        self.cfg["position"] = self.cmb_pos.currentData()
        self.cfg["ox"] = self.spin_ox.value()
        self.cfg["oy"] = self.spin_oy.value()
        
        if self.cfg["type"] == "text":
            self.cfg["text"] = self.txt_text.toPlainText()
            self.cfg["font_family"] = self.cmb_font.currentFont().family()
            self.cfg["font_size"] = self.spin_fs.value()
            self.cfg["color"] = self.btn_color.color()
            self.cfg["text_opacity"] = self.spin_t_alpha.value()
            self.cfg["bg_color"] = self.btn_bg.color()
            self.cfg["bg_opacity"] = self.spin_b_alpha.value()
        else:
            self.cfg["image_path"] = self.txt_file.text()
            self.cfg["scale"] = self.spin_scale.value()
            self.cfg["opacity"] = self.spin_i_alpha.value()
            self.cfg["flip_h"] = self.chk_fh.isChecked()
            self.cfg["flip_v"] = self.chk_fv.isChecked()
            
        self.changed.emit()
        
    def get_cfg(self):
        return self.cfg


class WatermarkEditor(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = []
        
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.container = QWidget()
        self.vbox = QVBoxLayout(self.container)
        self.vbox.setContentsMargins(5, 5, 5, 5)
        self.vbox.setSpacing(10)
        self.vbox.addStretch()
        
        self.scroll.setWidget(self.container)
        outer.addWidget(self.scroll, 1)
        
        btn_add = QPushButton("➕ 添加水印")
        btn_add.setMinimumHeight(36)
        btn_add.setProperty("class", "ActionBtn")
        btn_add.clicked.connect(self.add_item)
        outer.addWidget(btn_add)

    def add_item(self, cfg=None):
        w = WatermarkItemWidget(cfg, self.container)
        w.changed.connect(self.changed.emit)
        w.deleteRequested.connect(self.remove_item)
        self.items.append(w)
        self.vbox.insertWidget(self.vbox.count() - 1, w)
        if not cfg:
            self.changed.emit()

    def remove_item(self, w):
        if w in self.items:
            self.items.remove(w)
            self.vbox.removeWidget(w)
            w.deleteLater()
            self.changed.emit()

    def get_cfg(self):
        return [w.get_cfg() for w in self.items]

    def set_cfg(self, cfgs):
        while self.items:
            self.remove_item(self.items[0])
        for c in (cfgs or []):
            self.add_item(c)


class DuetVideoUI(QWidget):
    def __init__(self):
        super().__init__()
        self.tasks = []
        self.aligned = False
        self._threads = []
        self._frame_cache = {}
        self._frame_req = 0
        self._tpl_frames = {}
        self._align_thread = None
        self._render_thread = None
        self.cur_task = 0

        user_saved = _load_json("templates.json", None)
        if user_saved is None:
            from UI.default_templates import DEFAULT_TEMPLATES
            import copy
            self.templates = copy.deepcopy(DEFAULT_TEMPLATES)
        else:
            self.templates = user_saved
        if not self.templates:
            self.templates = [default_template()]
            _save_json("templates.json", self.templates)
        self.settings = _load_json("settings.json", {})
        if not self.settings.get("layout_presets_v1"):
            # 第一次升级：把多格 / 画中画版式加入模板库
            names = {t["name"] for t in self.templates}
            for tab, name, cells in LAYOUT_PRESETS:
                nm = f"{tab}·{name}"
                if nm not in names:
                    self.templates.append(template_from_cells(nm, cells))
            _save_json("templates.json", self.templates)
            self.settings["layout_presets_v1"] = True
        set_cache_root(self.settings.get("cache_root", ""))
        self.task_dir = ""
        self.active_tpl_name = self.settings.get("active_tpl", self.templates[0]["name"])
        if not self._tpl_by_name(self.active_tpl_name):
            self.active_tpl_name = self.templates[0]["name"]
        self.edit_tpl = dict(self._tpl_by_name(self.active_tpl_name))

        self.init_ui()
        self._load_settings()
        self.refresh_tpl_combos()
        self.refresh_tpl_library(select=self.active_tpl_name)
        self.update_align_status()
        self.redraw_tpl_canvas()
        self.redraw_preview()

    # ── 模板工具 ───────────────────────────────────────────────────────────
    def _tpl_by_name(self, name):
        for t in self.templates:
            if t["name"] == name:
                return t
        return None

    def active_tpl(self):
        return self._tpl_by_name(self.active_tpl_name) or self.templates[0]

    # ── 总体布局 ───────────────────────────────────────────────────────────
    def init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        title = QLabel("✨ 合拍视频批量合成")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #3182CE;")
        root.addWidget(title)

        nav = QHBoxLayout()
        self.step_btns = []
        for i, txt in enumerate(["1. 素材与时间线", "2. 画面排版模板", "3. 字幕卡片微调", "4. 全局导出设置"]):
            b = QPushButton(txt)
            b.setCheckable(True)
            b.setStyleSheet("""
                QPushButton { background: transparent; color: #718096; font-weight: bold;
                              border: 1px solid #CBD5E0; padding: 7px 16px; border-radius: 6px; }
                QPushButton:hover { border-color: #3182CE; color: #3182CE; }
                QPushButton:checked { background-color: #3182CE; color: white; border-color: #3182CE; }
            """)
            b.clicked.connect(lambda _, x=i: self.switch_step(x))
            nav.addWidget(b)
            self.step_btns.append(b)
        nav.addStretch()
        root.addLayout(nav)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_page_material())
        self.stack.addWidget(self._build_page_template())
        self.stack.addWidget(self._build_page_cards())
        self.stack.addWidget(self._build_page_export())
        root.addWidget(self.stack, 1)

        bottom = QHBoxLayout()
        bottom.addStretch()
        self.btn_prev = QPushButton("⬅️ 上一步")
        self.btn_prev.setProperty("class", "ActionBtn")
        self.btn_next = QPushButton("下一步 ➡️")
        self.btn_next.setProperty("class", "ActionBtn")
        self.btn_prev.clicked.connect(self.go_prev)
        self.btn_next.clicked.connect(self.go_next)
        bottom.addWidget(self.btn_prev)
        bottom.addWidget(self.btn_next)
        root.addLayout(bottom)

        # 每 30 秒自动保存一次全部设置（防崩溃丢失）
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(30_000)
        self._autosave_timer.timeout.connect(self._autosave)
        self._autosave_timer.start()

        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(220)
        self._preview_timer.timeout.connect(self.request_preview_frames)

        self.switch_step(0)

    # ══════════════════════════════════════════════════════════════════════
    #  第一板块：素材与时间线
    # ══════════════════════════════════════════════════════════════════════
    def _build_page_material(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)

        # 模板选择
        tpl_row = QHBoxLayout()
        tpl_row.addWidget(QLabel("🧩 画面模板:"))
        self.cmb_tpl_material = QComboBox()
        self.cmb_tpl_material.setMinimumWidth(220)
        self.cmb_tpl_material.setIconSize(QSize(18, 32))
        self.cmb_tpl_material.currentIndexChanged.connect(
            lambda: self._on_tpl_combo(self.cmb_tpl_material))
        tpl_row.addWidget(self.cmb_tpl_material)
        b_edit = QPushButton("✏️ 打开模板库编辑")
        b_edit.clicked.connect(lambda: self.switch_step(1))
        tpl_row.addWidget(b_edit)
        tpl_row.addStretch()
        lay.addLayout(tpl_row)

        lists = QHBoxLayout()
        self.list_person, p_card = self._video_list_card("👤 人物视频1（较短，将被循环）", "person")
        self.list_viral, v_card = self._video_list_card("🎬 主视频（时长基准）", "viral")
        lists.addWidget(v_card)     # 主视频是时长基准，放在最前面
        lists.addWidget(p_card)
        # 多格 / 画中画模板需要的额外人物视频列（按当前模板自动显示）
        self.extra_lists, self.extra_cards = {}, {}
        for src in ("person2", "person3", "person4"):
            lw, card = self._video_list_card(f"👥 {SRC_LABELS[src]}", src)
            card.setVisible(False)
            lists.addWidget(card)
            self.extra_lists[src] = lw
            self.extra_cards[src] = card
        lay.addLayout(lists, 1)

        # 对齐区
        align_card = _card()
        al = QVBoxLayout(align_card)
        row = QHBoxLayout()
        self.lbl_status1 = QLabel("")
        self.lbl_status1.setWordWrap(True)
        row.addWidget(self.lbl_status1, 1)
        
        self.cmb_align_mode = QComboBox()
        self.cmb_align_mode.addItem("默认: 按照左右列表当前顺序对齐", "default")
        self.cmb_align_mode.addItem("匹配: 按文件名开头的数字配对", "number")
        self.cmb_align_mode.addItem("匹配: 按文件名相似度自动配对", "fuzzy")
        row.addWidget(self.cmb_align_mode)
        
        self.btn_align = QPushButton("⏱ 开始对齐")
        self.btn_align.setProperty("class", "ActionBtn")
        self.btn_align.clicked.connect(lambda: self.start_align(False))
        row.addWidget(self.btn_align)
        
        self.btn_skip_align = QPushButton("⏭️ 不对齐直接下一步")
        self.btn_skip_align.setProperty("class", "ActionBtn")
        self.btn_skip_align.setStyleSheet("background-color: #718096;")
        self.btn_skip_align.clicked.connect(lambda: self.start_align(True))
        row.addWidget(self.btn_skip_align)

        self.btn_open_proj = QPushButton("📂 打开已对齐工程")
        self.btn_open_proj.setProperty("class", "ActionBtn")
        self.btn_open_proj.setStyleSheet("background-color: #38A169;")
        self.btn_open_proj.setToolTip("选择以前对齐过的文件夹，直接恢复那次任务的全部参数（文字、卡片样式、导出设置……）")
        self.btn_open_proj.clicked.connect(self._open_project)
        row.addWidget(self.btn_open_proj)
        
        al.addLayout(row)
        self.align_progress = QProgressBar()
        self.align_progress.setValue(0)
        self.align_progress.setFormat("等待对齐")
        al.addWidget(self.align_progress)
        cr = QHBoxLayout()
        cr.addWidget(QLabel("📁 缓存目录:"))
        self.txt_cache_root = QLineEdit(get_cache_dir())
        self.txt_cache_root.setReadOnly(True)
        self.txt_cache_root.setToolTip("每次对齐会在这里新建「日期_合拍视频批量合成」文件夹，同一天多次任务依次为 _02、_03 ……")
        cr.addWidget(self.txt_cache_root, 1)
        b_cr = QPushButton("更改…")
        b_cr.clicked.connect(self._choose_cache_root)
        b_co = QPushButton("打开")
        b_co.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(get_cache_dir())))
        cr.addWidget(b_cr)
        cr.addWidget(b_co)
        al.addLayout(cr)
        lay.addWidget(align_card)

        for lw in (self.list_person, self.list_viral, *self.extra_lists.values()):
            lw.model().rowsInserted.connect(self._mark_dirty)
            lw.model().rowsRemoved.connect(self._mark_dirty)
        return page

    def _video_list_card(self, title, kind):
        card = _card()
        v = QVBoxLayout(card)
        v.addWidget(_card_title(title))
        lw = VideoListWidget()
        lw.setToolTip("可直接把视频文件或文件夹拖到这里")
        v.addWidget(lw, 1)

        opt = QHBoxLayout()
        chk = QCheckBox("取消原视频声音（静音）")
        if kind not in ("person", "viral"):
            chk.setVisible(False)
        if kind == "person":
            chk.setChecked(True)
            self.chk_mute_person = chk
            chk.toggled.connect(self._mark_dirty)
            opt.addWidget(chk)
            opt.addStretch()
            opt.addWidget(QLabel("播放倍速:"))
            self.spin_person_speed = QDoubleSpinBox()
            self.spin_person_speed.setRange(0.25, 4.0)
            self.spin_person_speed.setSingleStep(0.05)
            self.spin_person_speed.setValue(1.0)
            self.spin_person_speed.setToolTip("所有人物视频对齐时的播放倍速")
            self.spin_person_speed.valueChanged.connect(self._mark_dirty)
            opt.addWidget(self.spin_person_speed)
        elif kind != "viral":
            opt.addWidget(QLabel("静音/倍速 与「人物视频1」相同"))
            opt.addStretch()
        else:
            chk.setChecked(False)
            self.chk_mute_viral = chk
            opt.addWidget(chk)
            opt.addStretch()
        v.addLayout(opt)

        btns = QHBoxLayout()
        icon_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "theme_icons")
        def _ib(icon, tip, text=""):
            b = QPushButton(text)
            b.setIcon(QIcon(os.path.join(icon_dir, icon)))
            b.setIconSize(QSize(16, 16))
            b.setToolTip(tip)
            if not text:
                b.setFixedWidth(36)
            else:
                b.setMinimumWidth(72)
            return b
        b_imp = _ib("add_video.svg", "导入视频（也可以直接拖拽文件/文件夹到列表）", "导入")
        b_imp.clicked.connect(lambda: self._import_videos(lw))
        b_up = _ib("arrow_up.svg", "上移选中的视频")
        b_up.clicked.connect(lambda: lw.move_selected(-1))
        b_dn = _ib("arrow_down.svg", "下移选中的视频")
        b_dn.clicked.connect(lambda: lw.move_selected(1))
        b_rm = _ib("remove.svg", "移除选中的视频")
        b_rm.clicked.connect(lw.remove_selected)
        b_clr = _ib("clear.svg", "清空整个列表")
        b_clr.clicked.connect(lw.clear)
        for b in (b_imp, b_up, b_dn, b_rm, b_clr):
            btns.addWidget(b)
        v.addLayout(btns)
        return lw, card

    def _import_videos(self, lw):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择视频", "", "视频文件 (" + " ".join(f"*.{e}" for e in VIDEO_EXTS) + ")")
        if files:
            lw.add_files(files)

    def _mark_dirty(self, *a):
        if self.aligned:
            self.aligned = False
        self._tpl_frames = {}
        self.update_align_status()

    def _src_list(self, src):
        if src == "viral":
            return self.list_viral
        if src == "person":
            return self.list_person
        return getattr(self, "extra_lists", {}).get(src)

    def _needed_person_srcs(self):
        """当前模板需要的人物视频列（至少需要人物视频1）。"""
        used = sources_used(self.active_tpl())
        srcs = [s for s in ("person", "person2", "person3", "person4") if s in used]
        return srcs or ["person"]

    def _sync_source_lists(self):
        need = set(self._needed_person_srcs())
        for src, card in getattr(self, "extra_cards", {}).items():
            card.setVisible(src in need or self.extra_lists[src].count() > 0)
        self.update_align_status()

    def update_align_status(self):
        cv = self.list_viral.count()
        counts = {s: self._src_list(s).count() for s in self._needed_person_srcs()}
        if self.aligned:
            self.lbl_status1.setText(f"✅ 时间线已对齐，共 {len(self.tasks)} 组任务（缓存：{os.path.basename(self.task_dir)}）。"
                                     f"可点击「下一步」进入字幕卡片微调。")
            self.lbl_status1.setStyleSheet("color: #38A169; font-weight: bold;")
        elif cv == 0 and not any(counts.values()):
            names = "、".join(SRC_LABELS[s] for s in counts)
            self.lbl_status1.setText(f"请导入「主视频」与「{names}」（可拖拽文件或文件夹），然后点击「开始对齐」。")
            self.lbl_status1.setStyleSheet("color: #718096;")
        elif any(n != cv for n in counts.values()):
            detail = "，".join(f"{SRC_LABELS[s]} {n} 个" for s, n in counts.items())
            self.lbl_status1.setText(f"⚠️ 数量不匹配：主视频 {cv} 个，{detail}，必须一一对应！")
            self.lbl_status1.setStyleSheet("color: #E53E3E; font-weight: bold;")
        else:
            extra = "（素材或设置已变更，需要重新对齐）" if self.tasks else ""
            self.lbl_status1.setText(f"已配对 {cv} 组，请点击「⏱ 开始对齐」生成对齐缓存。{extra}")
            self.lbl_status1.setStyleSheet("color: #DD6B20; font-weight: bold;")

    def start_align(self, skip=False):
        if self._align_thread and self._align_thread.isRunning():
            self._align_thread.stop()
            return
        srcs = self._needed_person_srcs()
        cv = self.list_viral.count()
        counts = {s: self._src_list(s).count() for s in srcs}
        if cv == 0 or any(n != cv for n in counts.values()):
            detail = "\n".join(f"{SRC_LABELS[s]}：{n} 个" for s, n in counts.items())
            QMessageBox.warning(self, "数量不匹配",
                                f"当前模板「{self.active_tpl_name}」需要以下几列视频，数量必须大于 0 且与主视频完全一致！\n\n"
                                f"主视频：{cv} 个\n{detail}")
            return

        v_paths = self.list_viral.paths()
        p_lists = {s: self._src_list(s).paths() for s in srcs}
        mode = self.cmb_align_mode.currentData()

        if mode == "number":
            import re
            def get_num(pth):
                m = re.search(r'^(\d+)', os.path.basename(pth))
                return int(m.group(1)) if m else -1
            v_paths = sorted(v_paths, key=get_num)
            for s in srcs:
                p_lists[s] = sorted(p_lists[s], key=get_num)
        elif mode == "fuzzy":
            import difflib
            for s in srcs:
                pool = list(p_lists[s])
                new = []
                for vp in v_paths:
                    vn = os.path.basename(vp)
                    best = max(pool, key=lambda x: difflib.SequenceMatcher(None, vn, os.path.basename(x)).ratio())
                    new.append(best)
                    pool.remove(best)
                p_lists[s] = new
        if mode in ("number", "fuzzy"):
            self.list_viral.clear()
            self.list_viral.add_files(v_paths)
            for s in srcs:
                self._src_list(s).clear()
                self._src_list(s).add_files(p_lists[s])

        items = [(v_paths[i], [p_lists[s][i] for s in srcs]) for i in range(cv)]
        task_dir = new_task_cache_dir()
        self._align_thread = AlignThread(items, self.chk_mute_person.isChecked(),
                                         self.spin_person_speed.value(), task_dir, skip_align=skip, parent=self)
        self._align_thread.progress.connect(self._on_align_progress)
        self._align_thread.done.connect(self._on_align_done)
        self._align_thread.failed.connect(self._on_align_failed)
        self.btn_align.setText("⏹ 取消")
        self._align_thread.start()

    def _on_align_progress(self, i, n, msg):
        self.align_progress.setMaximum(max(1, n))
        self.align_progress.setValue(i)
        self.align_progress.setFormat(f"{msg}  (%p%)")

    def _on_align_done(self, results):
        old = self.tasks
        import copy
        for i, r in enumerate(results):
            prev = old[i] if i < len(old) else {}
            # If the videos are the same, inherit. Otherwise default to new task independent!
            if prev and prev.get("person") == r.get("person") and prev.get("viral") == r.get("viral"):
                r["title_text"] = prev.get("title_text", "")
                r["phone_text"] = prev.get("phone_text", "")
                r["out_name"] = prev.get("out_name", "")
                r["adj"] = prev.get("adj", {"person": {"dx": 0, "dy": 0, "scale": 100},
                                            "viral": {"dx": 0, "dy": 0, "scale": 100}})
                if "title_cfg" in prev: r["title_cfg"] = prev["title_cfg"]
                if "phone_cfg" in prev: r["phone_cfg"] = prev["phone_cfg"]
            else:
                r["title_text"] = ""
                r["phone_text"] = ""
                r["out_name"] = ""
                r["adj"] = {"person": {"dx": 0, "dy": 0, "scale": 100},
                            "viral": {"dx": 0, "dy": 0, "scale": 100}}
                r["title_cfg"] = copy.deepcopy(getattr(self, "global_title_cfg"))
                r["phone_cfg"] = copy.deepcopy(getattr(self, "global_phone_cfg"))
                
        self.tasks = results
        self.task_dir = results[0]["task_dir"] if results else ""
        self.aligned = True
        self._frame_cache.clear()
        self.cur_task = 0
        self.btn_align.setText("⏱ 对齐时间线")
        self.align_progress.setFormat("✅ 对齐完成 (%p%)")
        self.update_align_status()
        self.refresh_task_list()
        self.save_settings()   # 新工程立即写入它自己的对齐文件夹

    def _on_align_failed(self, msg):
        self.btn_align.setText("⏱ 对齐时间线")
        self.align_progress.setFormat("对齐中断")
        QMessageBox.critical(self, "对齐失败", msg)

    # ══════════════════════════════════════════════════════════════════════
    #  第二板块：画面排版模板（随时可编辑）
    # ══════════════════════════════════════════════════════════════════════
    def _build_page_template(self):
        page = QWidget()
        lay = QHBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)

        # 左：模板库
        lib = _card()
        lib.setFixedWidth(230)
        lv = QVBoxLayout(lib)
        lv.addWidget(_card_title("📚 模板库"))
        self.tpl_list = QListWidget()
        self.tpl_list.setIconSize(QSize(36, 64))
        self.tpl_list.setSpacing(3)
        self.tpl_list.currentRowChanged.connect(self._on_tpl_lib_select)
        lv.addWidget(self.tpl_list, 1)
        g = QHBoxLayout()
        b_new = QPushButton("➕ 新建")
        b_new.clicked.connect(self._tpl_new)
        b_ren = QPushButton("✏️ 重命名")
        b_ren.clicked.connect(self._tpl_rename)
        g.addWidget(b_new)
        g.addWidget(b_ren)
        lv.addLayout(g)
        g2 = QHBoxLayout()
        b_dup = QPushButton("📄 另存为")
        b_dup.clicked.connect(self._tpl_save_as)
        b_del = QPushButton("🗑 删除")
        b_del.clicked.connect(self._tpl_delete)
        g2.addWidget(b_dup)
        g2.addWidget(b_del)
        lv.addLayout(g2)
        lay.addWidget(lib)

        # 中：画布预览
        mid = _card()
        mv = QVBoxLayout(mid)
        t = _card_title("👁 模板预览（拖动黄线调整格子边界；画中画小窗可拖动，拖右下角缩放）")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mv.addWidget(t)
        self.tpl_canvas = CanvasView(draggable=True)
        self.tpl_canvas.cellsChanged.connect(self._on_cells_dragged)
        self.tpl_canvas.cellSelected.connect(self._on_canvas_cell_selected)
        mv.addWidget(self.tpl_canvas, 1)
        self.lbl_tpl_hint = QLabel("浅粉 = 主视频，浅蓝/浅绿/浅橙/浅紫 = 人物视频1/2/3/4。导入素材后会显示第一组视频的真实画面。")
        self.lbl_tpl_hint.setWordWrap(True)
        self.lbl_tpl_hint.setStyleSheet("color:#718096;")
        mv.addWidget(self.lbl_tpl_hint)
        lay.addWidget(mid, 1)

        # 右：参数
        right = _card()
        right.setFixedWidth(320)
        rv = QVBoxLayout(right)
        rv.addWidget(_card_title("⚙️ 排版参数"))
        self.lbl_tpl_name = QLabel("")
        self.lbl_tpl_name.setStyleSheet("color:#3182CE; font-weight:bold;")
        rv.addWidget(self.lbl_tpl_name)
        form = QFormLayout()
        self.cmb_cell = QComboBox()
        self.cmb_cell.currentIndexChanged.connect(self._on_cell_pick)
        form.addRow("选择格子:", self.cmb_cell)
        rv.addLayout(form)

        gb = QGroupBox("🔲 当前格子")
        f = QFormLayout(gb)
        self.cmb_cell_src = QComboBox()
        for s in SOURCES:
            self.cmb_cell_src.addItem(SRC_LABELS[s], s)
        self.cmb_cell_src.currentIndexChanged.connect(self._on_tpl_param)
        f.addRow("放哪个视频:", self.cmb_cell_src)
        self.cmb_cell_fill = QComboBox()
        for k, lbl in FILL_MODES:
            self.cmb_cell_fill.addItem(lbl, k)
        self.cmb_cell_fill.currentIndexChanged.connect(self._on_tpl_param)
        f.addRow("填充规则:", self.cmb_cell_fill)
        self.cell_spins = {}
        for key, lbl, rng, step in (("ox", "画面偏移 X", (-2000, 2000), 10), ("oy", "画面偏移 Y", (-2000, 2000), 10),
                                    ("px", "格子位置 X", (0, CANVAS_W), 10), ("py", "格子位置 Y", (0, CANVAS_H), 10),
                                    ("pw", "格子宽度", (20, CANVAS_W), 10), ("ph", "格子高度", (20, CANVAS_H), 10),
                                    ("border", "白色边框", (0, 60), 1)):
            sp = QSpinBox()
            sp.setRange(*rng)
            sp.setSingleStep(step)
            sp.setSuffix(" px")
            sp.valueChanged.connect(self._on_tpl_param)
            f.addRow(lbl + ":", sp)
            self.cell_spins[key] = sp
        self.chk_cell_pip = QCheckBox("画中画小窗（浮在其它格子上面，可自由拖动）")
        self.chk_cell_pip.toggled.connect(self._on_tpl_param)
        f.addRow("", self.chk_cell_pip)
        rv.addWidget(gb)
        rv.addStretch()
        b_save = QPushButton("💾 保存模板")
        b_save.setProperty("class", "ActionBtn")
        b_save.clicked.connect(self._tpl_save)
        rv.addWidget(b_save)
        b_use = QPushButton("✅ 保存并设为当前使用模板")
        b_use.clicked.connect(self._tpl_save_and_use)
        rv.addWidget(b_use)
        lay.addWidget(right)
        return page

    def refresh_tpl_library(self, select=None):
        self.tpl_list.blockSignals(True)
        self.tpl_list.clear()
        for t in self.templates:
            mark = "  ★ 当前使用" if t["name"] == self.active_tpl_name else ""
            it = QListWidgetItem(template_icon(t), t["name"] + mark)
            it.setData(Qt.ItemDataRole.UserRole, t["name"])
            self.tpl_list.addItem(it)
        self.tpl_list.blockSignals(False)
        names = [t["name"] for t in self.templates]
        sel = select if select in names else (self.edit_tpl.get("name") if self.edit_tpl.get("name") in names else names[0])
        self.tpl_list.setCurrentRow(names.index(sel))
        self._on_tpl_lib_select(names.index(sel))

    def _on_tpl_lib_select(self, row):
        if row < 0 or row >= len(self.templates):
            return
        t = json.loads(json.dumps(self.templates[row]))
        # 旧版上下分屏模板统一转换为格子格式编辑（渲染结果不变）
        self.edit_tpl = {"name": t["name"], "cells": json.loads(json.dumps(tpl_cells(t)))}
        self._sel_cell = 0
        self._load_tpl_editor()

    def _tpl_editor_widgets(self):
        return [self.cmb_cell, self.cmb_cell_src, self.cmb_cell_fill, self.chk_cell_pip, *self.cell_spins.values()]

    def _load_tpl_editor(self):
        t = self.edit_tpl
        cells = t["cells"]
        self._sel_cell = max(0, min(getattr(self, "_sel_cell", 0), len(cells) - 1))
        for w in self._tpl_editor_widgets():
            w.blockSignals(True)
        self.lbl_tpl_name.setText(f"正在编辑：{t['name']}（{len(cells)} 个格子）")
        self.cmb_cell.clear()
        for i, cl in enumerate(cells):
            kind = "小窗" if cl.get("pip") else "格子"
            self.cmb_cell.addItem(f"{kind} {i + 1}：{SRC_LABELS.get(cl.get('src'), cl.get('src'))}", i)
        self.cmb_cell.setCurrentIndex(self._sel_cell)
        cl = cells[self._sel_cell]
        self.cmb_cell_src.setCurrentIndex(max(0, self.cmb_cell_src.findData(cl.get("src"))))
        self.cmb_cell_fill.setCurrentIndex(max(0, self.cmb_cell_fill.findData(cl.get("fill", "cover"))))
        x, y, w, h = cell_rect_px(cl)
        vals = {"ox": cl.get("ox", 0), "oy": cl.get("oy", 0), "px": x, "py": y, "pw": w, "ph": h,
                "border": cl.get("border", 0)}
        for k, sp in self.cell_spins.items():
            sp.setValue(int(vals[k]))
        self.chk_cell_pip.setChecked(bool(cl.get("pip")))
        for w in self._tpl_editor_widgets():
            w.blockSignals(False)
        self.redraw_tpl_canvas()

    def _read_tpl_editor(self):
        cells = self.edit_tpl.get("cells")
        if not cells:
            return
        cl = cells[self._sel_cell]
        cl["src"] = self.cmb_cell_src.currentData()
        cl["fill"] = self.cmb_cell_fill.currentData()
        cl["ox"] = self.cell_spins["ox"].value()
        cl["oy"] = self.cell_spins["oy"].value()
        cl["border"] = self.cell_spins["border"].value()
        cl["pip"] = self.chk_cell_pip.isChecked()
        x, y, w, h = cell_rect_px(cl)
        sp = self.cell_spins
        if (sp["px"].value(), sp["py"].value(), sp["pw"].value(), sp["ph"].value()) != (x, y, w, h):
            cl["x"] = sp["px"].value() / CANVAS_W
            cl["y"] = sp["py"].value() / CANVAS_H
            cl["w"] = min(sp["pw"].value(), CANVAS_W - sp["px"].value()) / CANVAS_W
            cl["h"] = min(sp["ph"].value(), CANVAS_H - sp["py"].value()) / CANVAS_H

    def _on_tpl_param(self, *a):
        self._read_tpl_editor()
        self._load_tpl_editor()

    def _on_cell_pick(self, idx):
        if idx < 0:
            return
        self._sel_cell = idx
        self._load_tpl_editor()

    def _on_canvas_cell_selected(self, idx):
        if idx != getattr(self, "_sel_cell", 0):
            self._sel_cell = idx
            self._load_tpl_editor()

    def _on_cells_dragged(self, cells):
        self.edit_tpl["cells"] = cells
        # 只更新数值框，不重建画布格子（避免打断拖动）
        cl = cells[self._sel_cell]
        x, y, w, h = cell_rect_px(cl)
        for k, v in (("px", x), ("py", y), ("pw", w), ("ph", h)):
            self.cell_spins[k].blockSignals(True)
            self.cell_spins[k].setValue(v)
            self.cell_spins[k].blockSignals(False)
        self.redraw_tpl_canvas(update_cells=False)

    def _on_split_dragged(self, ratio):
        pass

    def redraw_tpl_canvas(self, update_cells=True):
        if not hasattr(self, "tpl_canvas"):
            return
        img = compose_preview(self.edit_tpl, self._tpl_frames or {}, show_split=False,
                              selected=getattr(self, "_sel_cell", -1))
        self.tpl_canvas.set_image(img)
        if update_cells:
            self.tpl_canvas.set_cells(self.edit_tpl.get("cells"))

    def refresh_tpl_frames(self):
        """取每列素材的第一个视频，用于模板预览（没有素材则显示色块）。"""
        paths = {}
        for s in SOURCES:
            lw = self._src_list(s)
            if lw is not None and lw.count():
                paths[s] = lw.paths()[0]
        if not paths:
            self._tpl_frames = {}
            self.redraw_tpl_canvas()
            return
        if self._tpl_frames:
            return
        self._start_frame_thread("tpl", paths, 1.0)

    def _unique_name(self, base):
        names = {t["name"] for t in self.templates}
        if base not in names:
            return base
        i = 2
        while f"{base} {i}" in names:
            i += 1
        return f"{base} {i}"

    def _tpl_new(self):
        dlg = LayoutPickerDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.result_cells:
            return
        name, ok = QInputDialog.getText(self, "新建模板", "模板名称:", text=self._unique_name(dlg.result_name))
        if not ok or not name.strip():
            return
        name = self._unique_name(name.strip())
        self.templates.append(template_from_cells(name, dlg.result_cells))
        _save_json("templates.json", self.templates)
        self.refresh_tpl_library(select=name)
        self.refresh_tpl_combos()

    def _tpl_save(self):
        self._read_tpl_editor()
        name = self.edit_tpl["name"]
        for i, t in enumerate(self.templates):
            if t["name"] == name:
                self.templates[i] = json.loads(json.dumps(self.edit_tpl))
                break
        else:
            self.templates.append(json.loads(json.dumps(self.edit_tpl)))
        _save_json("templates.json", self.templates)
        self.refresh_tpl_library(select=name)
        self.refresh_tpl_combos()
        self._sync_source_lists()
        self._refresh_adj_sources()
        self.redraw_preview()
        QMessageBox.information(self, "已保存", f"模板「{name}」已保存到模板库。")

    def _tpl_save_and_use(self):
        self._read_tpl_editor()
        self.active_tpl_name = self.edit_tpl["name"]
        self._tpl_save()

    def _tpl_save_as(self):
        self._read_tpl_editor()
        name, ok = QInputDialog.getText(self, "另存为新模板", "新模板名称:",
                                        text=self._unique_name(self.edit_tpl["name"] + " 副本"))
        if not ok or not name.strip():
            return
        name = self._unique_name(name.strip())
        t = json.loads(json.dumps(self.edit_tpl))
        t["name"] = name
        self.templates.append(t)
        _save_json("templates.json", self.templates)
        self.refresh_tpl_library(select=name)
        self.refresh_tpl_combos()

    def _tpl_rename(self):
        old = self.edit_tpl["name"]
        name, ok = QInputDialog.getText(self, "重命名模板", "新名称:", text=old)
        if not ok or not name.strip() or name.strip() == old:
            return
        name = name.strip()
        if self._tpl_by_name(name):
            QMessageBox.warning(self, "名称重复", "已存在同名模板。")
            return
        for t in self.templates:
            if t["name"] == old:
                t["name"] = name
        self.edit_tpl["name"] = name
        if self.active_tpl_name == old:
            self.active_tpl_name = name
        _save_json("templates.json", self.templates)
        self.refresh_tpl_library(select=name)
        self.refresh_tpl_combos()

    def _tpl_delete(self):
        if len(self.templates) <= 1:
            QMessageBox.information(self, "无法删除", "模板库中至少需要保留一个模板。")
            return
        name = self.edit_tpl["name"]
        if QMessageBox.question(self, "删除模板", f"确定删除模板「{name}」吗？") != QMessageBox.StandardButton.Yes:
            return
        self.templates = [t for t in self.templates if t["name"] != name]
        if self.active_tpl_name == name:
            self.active_tpl_name = self.templates[0]["name"]
        _save_json("templates.json", self.templates)
        self.refresh_tpl_library(select=self.templates[0]["name"])
        self.refresh_tpl_combos()
        self.redraw_preview()

    def refresh_tpl_combos(self):
        for cmb in (self.cmb_tpl_material, self.cmb_tpl_cards):
            cmb.blockSignals(True)
            cmb.clear()
            for t in self.templates:
                cmb.addItem(template_icon(t, 18, 32), t["name"], t["name"])
            cmb.setCurrentIndex(max(0, cmb.findData(self.active_tpl_name)))
            cmb.blockSignals(False)

    def _on_tpl_combo(self, cmb):
        name = cmb.currentData()
        if not name:
            return
        self.active_tpl_name = name
        for other in (self.cmb_tpl_material, self.cmb_tpl_cards):
            if other is not cmb:
                other.blockSignals(True)
                other.setCurrentIndex(max(0, other.findData(name)))
                other.blockSignals(False)
        self.refresh_tpl_library(select=self.edit_tpl.get("name"))
        self._sync_source_lists()
        self._refresh_adj_sources()
        self._tpl_frames = {}
        self.redraw_preview()

    # ══════════════════════════════════════════════════════════════════════
    #  第三板块：字幕卡片微调
    # ══════════════════════════════════════════════════════════════════════

    def _wrap_editor(self, kind, editor):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(5,5,5,5)
        lay.addWidget(editor, 1)
        
        def on_editor_changed():
            cfg = editor.get_cfg()
            if hasattr(self, "rb_global") and self.rb_global.isChecked():
                setattr(self, f"global_{kind}_cfg", cfg)
            else:
                if getattr(self, "tasks", None) and getattr(self, "cur_task", -1) >= 0:
                    self.tasks[self.cur_task][f"{kind}_cfg"] = cfg
            self.redraw_preview()
            
        editor.changed.connect(on_editor_changed)
        return w

    def _build_page_cards(self):
        from image_worker.duet_render import default_card
        self.global_title_cfg = default_card("title")
        self.global_phone_cfg = default_card("phone")
        page = QWidget()
        main_lay = QHBoxLayout(page)
        main_lay.setContentsMargins(0, 0, 0, 0)
        self.cards_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_lay.addWidget(self.cards_splitter)

        # 左：任务列表
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setMinimumWidth(150)
        left_scroll.setMaximumWidth(450)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left = _card()
        left_scroll.setWidget(left)
        lv = QVBoxLayout(left)
        lv.addWidget(_card_title("📋 任务列表"))
        self.task_list = QListWidget()
        self.task_list.setMinimumHeight(300)
        self.task_list.currentRowChanged.connect(self._on_task_select)
        lv.addWidget(self.task_list, 1)
        self.cards_splitter.addWidget(left_scroll)

        # 中：预览
        mid = _card()
        mv = QVBoxLayout(mid)
        top = QHBoxLayout()
        top.addWidget(QLabel("模板:"))
        self.cmb_tpl_cards = QComboBox()
        self.cmb_tpl_cards.setIconSize(QSize(18, 32))
        self.cmb_tpl_cards.currentIndexChanged.connect(lambda: self._on_tpl_combo(self.cmb_tpl_cards))
        top.addWidget(self.cmb_tpl_cards, 1)
        mv.addLayout(top)
        self.preview_canvas = CanvasView(draggable=False)
        mv.addWidget(self.preview_canvas, 1)
        self.time_slider = QSlider(Qt.Orientation.Horizontal)
        self.time_slider.setRange(0, 100)
        self.time_slider.valueChanged.connect(self._on_time_change)
        mv.addWidget(self.time_slider)
        tr = QHBoxLayout()
        self.lbl_time = QLabel("0.0s / 0.0s")
        tr.addWidget(self.lbl_time, 1)
        self.btn_preview_title = QPushButton("看标题卡片")
        self.btn_preview_title.clicked.connect(lambda: self._jump_card("title"))
        self.btn_preview_phone = QPushButton("看电话卡片")
        self.btn_preview_phone.clicked.connect(lambda: self._jump_card("phone"))
        tr.addWidget(self.btn_preview_title)
        tr.addWidget(self.btn_preview_phone)
        mv.addLayout(tr)
        self.lbl_preview_tip = QLabel("")
        self.lbl_preview_tip.setStyleSheet("color:#718096;")
        self.lbl_preview_tip.setWordWrap(True)
        mv.addWidget(self.lbl_preview_tip)
        self.cards_splitter.addWidget(mid)

        # 右：卡片参数
        right_panel = QWidget()
        rv = QVBoxLayout(right_panel)
        rv.setContentsMargins(0, 0, 0, 0)
        
        scope_lay = QHBoxLayout()
        scope_lay.addWidget(QLabel("应用范围:"))
        self.rb_global = QRadioButton("全局默认")
        self.rb_task = QRadioButton("仅当前任务(独立设置)")
        self.rb_task.setChecked(True)
        scope_lay.addWidget(self.rb_global)
        scope_lay.addWidget(self.rb_task)
        scope_lay.addStretch()
        rv.addLayout(scope_lay)
        
        self.rb_global.toggled.connect(self._on_scope_toggled)

        self.card_tabs = QTabWidget()
        self.card_tabs.setMinimumWidth(380)
        self.card_tabs.currentChanged.connect(self._on_card_tab_changed)
        rv.addWidget(self.card_tabs, 1)
        
        self.title_editor = CardEditor("title")
        self.phone_editor = CardEditor("phone")
        self.card_tabs.addTab(self._wrap_editor("title", self.title_editor), "🅰 标题卡片")
        self.card_tabs.addTab(self._wrap_editor("phone", self.phone_editor), "📞 电话卡片")
        self.wm_editor = WatermarkEditor(self)
        self.wm_editor.changed.connect(self.redraw_preview)
        self.card_tabs.addTab(self.wm_editor, "© 水印")

        # 增加一个文案和微调 tab
        tab_text_adj = QWidget()
        tab_text_scroll = QScrollArea()
        tab_text_scroll.setWidgetResizable(True)
        tab_text_scroll.setWidget(tab_text_adj)
        tv = QVBoxLayout(tab_text_adj)
        
        tv.addWidget(QLabel("标题卡片文本（当前任务）:"))
        self.txt_title = QPlainTextEdit()
        self.txt_title.setFixedHeight(64)
        self.txt_title.textChanged.connect(self._on_task_text)
        tv.addWidget(self.txt_title)
        tv.addWidget(QLabel("电话卡片文本（当前任务）:"))
        self.txt_phone = QPlainTextEdit()
        self.txt_phone.setFixedHeight(52)
        self.txt_phone.textChanged.connect(self._on_task_text)
        tv.addWidget(self.txt_phone)
        
        btn_lay = QHBoxLayout()
        b1 = QPushButton("📋 批量粘贴标题文本")
        b1.clicked.connect(lambda: self._batch_paste("title_text", "批量导入标题文本"))
        b2 = QPushButton("📋 批量粘贴电话文本")
        b2.clicked.connect(lambda: self._batch_paste("phone_text", "批量导入电话文本"))
        btn_lay.addWidget(b1)
        btn_lay.addWidget(b2)
        tv.addLayout(btn_lay)

        gb = QGroupBox("🎯 画面单项微调（当前任务）")
        f = QFormLayout(gb)
        self.cmb_adj_src = QComboBox()
        self.cmb_adj_src.currentIndexChanged.connect(self._load_adj_widgets)
        f.addRow("调整哪个视频:", self.cmb_adj_src)
        self.adj_sp = {}
        for k, lbl, rng in (("dx", "X 移动", (-2000, 2000)), ("dy", "Y 移动", (-2000, 2000)),
                            ("scale", "缩放 %", (10, 500))):
            sp = QSpinBox()
            sp.setRange(*rng)
            sp.setSingleStep(1 if k == "scale" else 10)
            sp.setValue(100 if k == "scale" else 0)
            sp.valueChanged.connect(self._on_adj_change)
            f.addRow(f"{lbl}:", sp)
            self.adj_sp[k] = sp
        b_reset = QPushButton("↺ 重置微调")
        b_reset.clicked.connect(self._reset_adj)
        f.addRow("", b_reset)
        tv.addWidget(gb)
        tv.addStretch()

        self.card_tabs.addTab(tab_text_scroll, "📝 文案和微调")
        
        self.cards_splitter.addWidget(right_panel)
        self.cards_splitter.setStretchFactor(0, 0)
        self.cards_splitter.setStretchFactor(1, 1)
        self.cards_splitter.setStretchFactor(2, 0)
        return page

    def _on_scope_toggled(self):
        if not getattr(self, "tasks", None): return
        t = self.tasks[self.cur_task]
        is_global = self.rb_global.isChecked()
        
        for kind, editor in [("title", self.title_editor), ("phone", self.phone_editor)]:
            editor.blockSignals(True)
            if is_global:
                t.pop(f"{kind}_cfg", None)
                editor.set_cfg(getattr(self, f"global_{kind}_cfg"))
            else:
                if f"{kind}_cfg" not in t:
                    import copy
                    t[f"{kind}_cfg"] = copy.deepcopy(getattr(self, f"global_{kind}_cfg"))
                editor.set_cfg(t[f"{kind}_cfg"])
            editor.blockSignals(False)
        self.redraw_preview()

    def _on_card_tab_changed(self, index):
        title = self.card_tabs.tabText(index)
        if "标题" in title:
            self._jump_card("title")
        elif "电话" in title:
            self._jump_card("phone")

    def refresh_task_list(self):
        self.task_list.blockSignals(True)
        self.task_list.clear()
        for i, t in enumerate(self.tasks):
            it = QListWidgetItem(f"{i + 1:02d}. {os.path.basename(t['viral'])}")
            it.setToolTip(f"人物：{t['person']}\n主视频：{t['viral']}\n时长：{t['duration']:.1f}s")
            self.task_list.addItem(it)
        self.task_list.blockSignals(False)
        if self.tasks:
            self.cur_task = min(self.cur_task, len(self.tasks) - 1)
            if self.time_slider.value() == 0:
                self.time_slider.blockSignals(True)
                self.time_slider.setRange(0, max(1, int(self.tasks[self.cur_task]["duration"] * 10)))
                self.time_slider.setValue(min(10, self.time_slider.maximum()))
                self.time_slider.blockSignals(False)
            self.task_list.setCurrentRow(self.cur_task)
            self._on_task_select(self.cur_task)

    def _on_task_select(self, row):
        if row < 0 or row >= len(self.tasks):
            return
        self.cur_task = row
        t = self.tasks[row]
        for w in (self.txt_title, self.txt_phone):
            w.blockSignals(True)
        self.txt_title.setPlainText(t.get("title_text", ""))
        self.txt_phone.setPlainText(t.get("phone_text", ""))
        for w in (self.txt_title, self.txt_phone):
            w.blockSignals(False)
        self._refresh_adj_sources()
        
        # Update Scope Radio
        has_task_cfg = "title_cfg" in t or "phone_cfg" in t
        self.rb_global.blockSignals(True)
        self.rb_task.blockSignals(True)
        if has_task_cfg:
            self.rb_task.setChecked(True)
        else:
            self.rb_global.setChecked(True)
        self.rb_global.blockSignals(False)
        self.rb_task.blockSignals(False)
        
        for kind, editor in [("title", self.title_editor), ("phone", self.phone_editor)]:
            editor.blockSignals(True)
            if f"{kind}_cfg" in t:
                editor.set_cfg(t[f"{kind}_cfg"])
            else:
                editor.set_cfg(getattr(self, f"global_{kind}_cfg"))
            editor.blockSignals(False)
            
        self.time_slider.blockSignals(True)
        self.time_slider.setRange(0, max(1, int(t["duration"] * 10)))
        if self.time_slider.value() > self.time_slider.maximum():
            self.time_slider.setValue(10)
        self.time_slider.blockSignals(False)
        self._update_time_label()
        self.redraw_preview()
        self._preview_timer.start()

    def _on_task_text(self):
        if not self.tasks:
            return
        t = self.tasks[self.cur_task]
        t["title_text"] = self.txt_title.toPlainText()
        t["phone_text"] = self.txt_phone.toPlainText()
        self.redraw_preview()

    def _refresh_adj_sources(self):
        if not hasattr(self, "cmb_adj_src"):
            return
        cur = self.cmb_adj_src.currentData()
        self.cmb_adj_src.blockSignals(True)
        self.cmb_adj_src.clear()
        for s in sources_used(self.active_tpl()):
            self.cmb_adj_src.addItem(SRC_LABELS[s], s)
        self.cmb_adj_src.setCurrentIndex(max(0, self.cmb_adj_src.findData(cur)))
        self.cmb_adj_src.blockSignals(False)
        self._load_adj_widgets()

    def _load_adj_widgets(self, *a):
        src = self.cmb_adj_src.currentData()
        vals = {}
        if self.tasks and src:
            vals = self.tasks[self.cur_task].setdefault("adj", {}).get(src, {})
        for k, sp in self.adj_sp.items():
            sp.blockSignals(True)
            sp.setValue(int(vals.get(k, 100 if k == "scale" else 0)))
            sp.blockSignals(False)

    def _on_adj_change(self, *a):
        src = self.cmb_adj_src.currentData()
        if not self.tasks or not src:
            return
        t = self.tasks[self.cur_task]
        d = t.setdefault("adj", {}).setdefault(src, {})
        for k, sp in self.adj_sp.items():
            d[k] = sp.value()
        self.redraw_preview()

    def _reset_adj(self):
        if not self.tasks:
            return
        self.tasks[self.cur_task]["adj"] = {}
        self._load_adj_widgets()
        self.redraw_preview()

    def _batch_paste(self, key, title):
        if not self.tasks:
            return
        dlg = PasteDialog(title, f"从 Excel 复制一列内容后粘贴到下方。共 {len(self.tasks)} 个任务；"
                                 f"粘贴几行就替换前几个任务，其余保持不变，多出的行自动忽略。", self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        for i, line in enumerate(dlg.rows()[:len(self.tasks)]):
            self.tasks[i][key] = line
        self._on_task_select(self.cur_task)

    def cur_time(self):
        return self.time_slider.value() / 10.0

    def _update_time_label(self):
        dur = self.tasks[self.cur_task]["duration"] if self.tasks else 0
        self.lbl_time.setText(f"{self.cur_time():.1f}s / {dur:.1f}s")

    def _on_time_change(self, *a):
        self._update_time_label()
        self.redraw_preview()
        self._preview_timer.start()

    def _jump_card(self, which):
        if not self.tasks:
            return
        dur = self.tasks[self.cur_task]["duration"]
        if which == "title":
            t = min(1.0, self.title_editor.get_cfg()["time"] / 2)
            self.btn_preview_title.setStyleSheet("background-color: #3182CE; color: white;")
            self.btn_preview_phone.setStyleSheet("")
        else:
            t = self.phone_editor.get_cfg()["time"] + 0.5
            if t >= dur:
                QMessageBox.information(self, "提示", f"电话卡片开始时间超过了当前视频时长（{dur:.1f}s），该卡片在此任务中不会出现。")
                return
            self.btn_preview_phone.setStyleSheet("background-color: #3182CE; color: white;")
            self.btn_preview_title.setStyleSheet("")
        self.time_slider.setValue(int(t * 10))

    def _task_paths(self, t):
        out = {}
        for s in sources_used(self.active_tpl()):
            info = task_source(t, s)
            if info and info[0]:
                out[s] = info[0]
        return out

    def request_preview_frames(self):
        if not self.tasks or self.stack.currentIndex() != 2:
            return
        t = self.tasks[self.cur_task]
        tm = round(self.cur_time(), 1)
        paths = self._task_paths(t)
        if all((pth, tm) in self._frame_cache for pth in paths.values()):
            self.redraw_preview()
            return
        self._start_frame_thread("preview", paths, tm)

    def _start_frame_thread(self, tag, paths, tm):
        self._frame_req += 1
        th = FrameThread(tag, paths, tm, self._frame_req, self)
        th.done.connect(self._on_frames)
        th.finished.connect(lambda: self._threads.remove(th) if th in self._threads else None)
        self._threads.append(th)
        th.start()

    def _on_frames(self, tag, data, tm, req):
        imgs = {k: (QImage.fromData(b) if b else None) for k, b in data.items()}
        if tag == "tpl":
            self._tpl_frames = {k: v for k, v in imgs.items() if v is not None}
            self.redraw_tpl_canvas(update_cells=False)
            return
        th = self.sender()
        if th is not None:
            for k, img in imgs.items():
                if img is not None and th.paths.get(k):
                    self._frame_cache[(th.paths[k], tm)] = img
        if len(self._frame_cache) > 300:
            self._frame_cache.clear()
        self.redraw_preview()

    def redraw_preview(self, *a):
        if not hasattr(self, "preview_canvas"):
            return
        tpl = self.active_tpl()
        split_y = box_layout(tpl)["split_y"]
        
        has_task = bool(self.tasks)
        tm = round(self.cur_time(), 1) if has_task else 0.0
        
        frames = {}
        if has_task:
            task = self.tasks[self.cur_task]
            for s, pth in self._task_paths(task).items():
                frames[s] = self._frame_cache.get((pth, tm))
        else:
            task = {}
            
        overlays = []
        tc = task.get("title_cfg") or getattr(self, "global_title_cfg", self.title_editor.get_cfg()) if has_task else getattr(self, "global_title_cfg", self.title_editor.get_cfg())
        pc = task.get("phone_cfg") or getattr(self, "global_phone_cfg", self.phone_editor.get_cfg()) if has_task else getattr(self, "global_phone_cfg", self.phone_editor.get_cfg())
        tips = []
        if not has_task:
            tips.append("尚未对齐时间线，正以空背景预览卡片效果")
            
        if tm <= tc["time"]:
            txt = task.get("title_text") or ""
            if not txt.strip() and tc["mode"] == "text":
                txt = SAMPLE_TITLE
                if has_task: tips.append("标题为空显示示例文字")
            overlays.append(render_card_layer(tc, txt, split_y, self.cur_task if has_task else 0, draw_guides=True))
            
        if tm >= pc["time"]:
            txt = task.get("phone_text") or ""
            if not txt.strip() and pc["mode"] == "text":
                txt = SAMPLE_PHONE
                if has_task: tips.append("电话为空显示示例文字")
            overlays.append(render_card_layer(pc, txt, split_y, self.cur_task if has_task else 0, draw_guides=True))

        wm_cfg = getattr(self, "wm_editor", None) and self.wm_editor.get_cfg()
        if wm_cfg:
            overlays.append(render_watermark_layer(wm_cfg))
            
        if has_task and any(v is None for v in frames.values()):
            tips.insert(0, "正在读取视频画面…")
        missing = [SRC_LABELS[s] for s in sources_used(tpl) if has_task and s not in frames]
        if missing:
            tips.insert(0, f"当前模板需要「{'、'.join(missing)}」，本组任务没有，请回到素材页导入后重新对齐")

        img = compose_preview(tpl, frames, None, task.get("adj"), overlays, show_split=True)
        self.preview_canvas.set_image(img)
        self.lbl_preview_tip.setText("；".join(tips))

    # ══════════════════════════════════════════════════════════════════════
    #  第四板块：全局导出
    # ══════════════════════════════════════════════════════════════════════
    def _build_page_export(self):
        page = QWidget()
        lay = QHBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)

        left = _card()
        lv = QVBoxLayout(left)
        lv.addWidget(_card_title("📝 导出任务与文件名"))
        btn_row = QHBoxLayout()
        btn_sel_all = QPushButton("☑ 全选")
        btn_sel_none = QPushButton("☐ 取消全选")
        btn_sel_all.clicked.connect(lambda: self._select_all_tasks(True))
        btn_sel_none.clicked.connect(lambda: self._select_all_tasks(False))
        btn_row.addWidget(btn_sel_all)
        btn_row.addWidget(btn_sel_none)
        btn_row.addStretch()
        lv.addLayout(btn_row)
        
        self.tbl_names = QTableWidget(0, 3)
        self.tbl_names.setHorizontalHeaderLabels(["导出", "输出文件名（可直接编辑）", "进度"])
        self.tbl_names.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.tbl_names.setColumnWidth(0, 70)
        self.tbl_names.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tbl_names.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.tbl_names.setColumnWidth(2, 110)
        self.tbl_names.itemChanged.connect(self._on_name_edited)
        lv.addWidget(self.tbl_names, 1)
        b = QPushButton("📋 批量粘贴文件名")
        b.clicked.connect(self._batch_names)
        lv.addWidget(b)
        lay.addWidget(left, 1)

        right = _card()
        right.setFixedWidth(400)
        rv = QVBoxLayout(right)
        rv.addWidget(_card_title("⚙️ 导出参数"))
        form = QFormLayout()
        pr = QHBoxLayout()
        self.txt_export_dir = QLineEdit(os.path.join(os.path.expanduser("~"), "Desktop", "合拍视频输出"))
        bb = QPushButton("浏览…")
        bb.clicked.connect(self._browse_export)
        pr.addWidget(self.txt_export_dir)
        pr.addWidget(bb)
        form.addRow("导出文件夹:", pr)
        self.cmb_res = QComboBox()
        self.cmb_res.addItem("1080 x 1920（推荐）", (1080, 1920))
        self.cmb_res.addItem("720 x 1280", (720, 1280))
        self.cmb_res.addItem("1440 x 2560", (1440, 2560))
        self.cmb_res.addItem("2160 x 3840（4K）", (2160, 3840))
        form.addRow("分辨率:", self.cmb_res)
        self.cmb_quality = QComboBox()
        self.cmb_quality.addItem("高画质", 18)
        self.cmb_quality.addItem("标准", 23)
        self.cmb_quality.addItem("小体积", 28)
        self.cmb_quality.setCurrentIndex(1)
        form.addRow("画面质量:", self.cmb_quality)
        
        row_speed = QHBoxLayout()
        self.spin_speed = QDoubleSpinBox()
        self.spin_speed.setRange(0.1, 10.0)
        self.spin_speed.setSingleStep(0.1)
        self.spin_speed.setValue(1.0)
        row_speed.addWidget(self.spin_speed)
        row_speed.addWidget(QLabel("倍"))
        form.addRow("全局速度倍数:", row_speed)
        
        self.chk_max_3min = QCheckBox("总时长不超过三分钟 (超出自动加速)")
        self.chk_max_3min.setChecked(False)
        form.addRow("", self.chk_max_3min)
        vr = QHBoxLayout()
        self.slider_volume = QSlider(Qt.Orientation.Horizontal)
        self.slider_volume.setRange(0, 200)
        self.slider_volume.setValue(100)
        self.lbl_volume = QLabel("100%")
        self.slider_volume.valueChanged.connect(lambda v: self.lbl_volume.setText(f"{v}%"))
        vr.addWidget(self.slider_volume)
        vr.addWidget(self.lbl_volume)
        form.addRow("总音量:", vr)
        self.cmb_enc = QComboBox()
        self.cmb_enc.addItem("CPU（兼容性最好）", "cpu")
        self.cmb_enc.addItem("NVIDIA 显卡 (NVENC)", "nvenc")
        self.cmb_enc.addItem("AMD 显卡 (AMF)", "amf")
        self.cmb_enc.addItem("Intel 核显 (QSV)", "qsv")
        form.addRow("硬件加速:", self.cmb_enc)
        self.spin_workers = QSpinBox()
        self.spin_workers.setRange(1, 4)
        self.spin_workers.setValue(2)
        form.addRow("同时导出进程:", self.spin_workers)
        rv.addLayout(form)

        self.btn_render = QPushButton("🚀 开始批量合成")
        self.btn_render.setProperty("class", "ActionBtn")
        self.btn_render.setMinimumHeight(40)
        self.btn_render.clicked.connect(self.start_render)
        rv.addWidget(self.btn_render)
        self.render_progress = QProgressBar()
        self.render_progress.setFormat("等待开始")
        rv.addWidget(self.render_progress)
        self.txt_log = QPlainTextEdit()
        self.txt_log.setReadOnly(True)
        rv.addWidget(self.txt_log, 1)
        row = QHBoxLayout()
        b_open = QPushButton("📂 打开输出文件夹")
        b_open.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.txt_export_dir.text())))
        b_cache = QPushButton("🧹 清理临时缓存")
        b_cache.setStyleSheet("color: #E53E3E;")
        b_cache.clicked.connect(self.clear_cache)
        row.addWidget(b_open)
        row.addWidget(b_cache)
        rv.addLayout(row)
        row2 = QHBoxLayout()
        b_restore = QPushButton("♻️ 恢复本工程历史")
        b_restore.setToolTip("当前工程每 30 秒自动保存到它的对齐文件夹，并在 backups 里保留最近 30 份历史快照。")
        b_restore.clicked.connect(self._restore_backup)
        b_data = QPushButton("🗂 打开工程文件夹")
        b_data.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(
            self.task_dir if self.task_dir and os.path.isdir(self.task_dir) else get_cache_dir())))
        row2.addWidget(b_restore)
        row2.addWidget(b_data)
        rv.addLayout(row2)
        lay.addWidget(right)
        return page

    def _default_out_name(self, t):
        return os.path.splitext(os.path.basename(t["viral"]))[0] + "合成"

    def refresh_export_table(self):
        self.tbl_names.blockSignals(True)
        self.tbl_names.setRowCount(len(self.tasks))
        for i, t in enumerate(self.tasks):
            a = QTableWidgetItem(f"{i + 1:02d}. {os.path.basename(t['viral'])}")
            a.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            a.setCheckState(Qt.CheckState.Unchecked if t.get("skip_export") else Qt.CheckState.Checked)
            a.setToolTip(t["viral"])
            self.tbl_names.setItem(i, 0, a)
            self.tbl_names.setItem(i, 1, QTableWidgetItem(t.get("out_name") or self._default_out_name(t)))
            pb = QProgressBar()
            pb.setRange(0, 100)
            pb.setValue(0)
            pb.setFormat("%p%")
            pb.setTextVisible(True)
            self.tbl_names.setCellWidget(i, 2, pb)
        self.tbl_names.blockSignals(False)

    def _select_all_tasks(self, check):
        self.tbl_names.blockSignals(True)
        for i in range(self.tbl_names.rowCount()):
            it = self.tbl_names.item(i, 0)
            if it: it.setCheckState(Qt.CheckState.Checked if check else Qt.CheckState.Unchecked)
            if i < len(self.tasks):
                self.tasks[i]["skip_export"] = not check
        self.tbl_names.blockSignals(False)

    def _on_name_edited(self, item):
        if item.row() >= len(self.tasks):
            return
        if item.column() == 1:
            self.tasks[item.row()]["out_name"] = item.text().strip()
        elif item.column() == 0:
            self.tasks[item.row()]["skip_export"] = item.checkState() != Qt.CheckState.Checked

    def _batch_names(self):
        if not self.tasks:
            return
        dlg = PasteDialog("批量导入文件名", f"共 {len(self.tasks)} 个任务。粘贴几行就替换前几个任务的文件名，"
                                         f"其余保持默认，多出的行自动忽略。", self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        for i, line in enumerate(dlg.rows()[:len(self.tasks)]):
            if line.strip():
                self.tasks[i]["out_name"] = line.strip()
        self.refresh_export_table()

    def _browse_export(self):
        d = QFileDialog.getExistingDirectory(self, "选择导出文件夹", self.txt_export_dir.text())
        if d:
            self.txt_export_dir.setText(d)

    @staticmethod
    def _safe_name(name):
        for ch in '\\/:*?"<>|\n\r\t':
            name = name.replace(ch, "_")
        return name.strip() or "output"

    def _card_visible(self, cfg, text):
        if not cfg.get("enabled", True):
            return False
        if cfg.get("mode") == "image":
            return bool(cfg.get("image_path")) and os.path.isfile(cfg["image_path"])
        return bool((text or "").strip())

    def start_render(self):
        if self._render_thread and self._render_thread.isRunning():
            return
        if not self.aligned or not self.tasks:
            QMessageBox.warning(self, "无法导出", "请先完成「对齐时间线」。")
            return
        out_dir = self.txt_export_dir.text().strip()
        if not out_dir:
            QMessageBox.warning(self, "无法导出", "请选择导出文件夹。")
            return
        need = sources_used(self.active_tpl())
        lack = [i + 1 for i, t in enumerate(self.tasks) if any(task_source(t, s) is None for s in need)]
        if lack:
            QMessageBox.warning(self, "无法导出",
                                f"当前模板「{self.active_tpl_name}」需要："
                                f"{'、'.join(SRC_LABELS[s] for s in need)}。\n"
                                f"第 {', '.join(map(str, lack[:10]))}{' 等' if len(lack) > 10 else ''} 组任务缺少其中的视频。\n\n"
                                f"请回到素材页导入对应的人物视频列，然后重新「开始对齐」。")
            return
        selected = [i for i in range(len(self.tasks))
                    if self.tbl_names.item(i, 0) is None
                    or self.tbl_names.item(i, 0).checkState() == Qt.CheckState.Checked]
        if not selected:
            QMessageBox.warning(self, "无法导出", "没有勾选任何任务，请至少勾选一个。")
            return
        if QMessageBox.question(self, "确认批量导出",
                                f"即将导出 {len(selected)} / {len(self.tasks)} 个任务到：\n{out_dir}\n\n确定开始吗？",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                                ) != QMessageBox.StandardButton.Yes:
            return
        self.save_settings()   # 导出前先把当前所有设置落盘，防止中途崩溃丢失
        os.makedirs(out_dir, exist_ok=True)
        if not self.task_dir or not os.path.isdir(self.task_dir):
            self.task_dir = new_task_cache_dir()
        card_dir = os.path.join(self.task_dir, "cards")
        os.makedirs(card_dir, exist_ok=True)

        tpl = json.loads(json.dumps(self.active_tpl()))
        split_y = box_layout(tpl)["split_y"]
        ow, oh = self.cmb_res.currentData()
        self.txt_log.clear()
        jobs = []
        used = set()
        wm_cfg = getattr(self, "wm_editor", None) and self.wm_editor.get_cfg()
        for i, t in enumerate(self.tasks):
            if i not in selected:
                continue
            title_png = phone_png = ""
            tc = t.get("title_cfg") or getattr(self, "global_title_cfg", self.title_editor.get_cfg())
            pc = t.get("phone_cfg") or getattr(self, "global_phone_cfg", self.phone_editor.get_cfg())
            if self._card_visible(tc, t.get("title_text")):
                title_png = os.path.join(card_dir, f"{i + 1:03d}_title.png")
                render_card_layer(tc, t.get("title_text", ""), split_y, i).save(title_png)
            if self._card_visible(pc, t.get("phone_text")):
                if pc["time"] < t["duration"]:
                    phone_png = os.path.join(card_dir, f"{i + 1:03d}_phone.png")
                    render_card_layer(pc, t.get("phone_text", ""), split_y, i).save(phone_png)
                else:
                    self.txt_log.appendPlainText(f"⚠️ 任务 {i + 1}：电话卡片开始时间超过视频时长，已跳过该卡片。")
            
            wm_png = ""
            if wm_cfg:
                wm_png = os.path.join(card_dir, f"{i + 1:03d}_wm.png")
                render_watermark_layer(wm_cfg).save(wm_png)
                
            name = self._safe_name(t.get("out_name") or self._default_out_name(t))
            base, k = name, 2
            while name.lower() in used:
                name = f"{base}_{k}"
                k += 1
            used.add(name.lower())
            out = os.path.join(out_dir, name + ".mp4")
            jobs.append({
                "index": i,
                "task": t, "tpl": tpl, "out": out,
                "kw": dict(title_png=title_png, title_end=min(tc["time"], t["duration"]),
                           phone_png=phone_png, phone_start=pc["time"],
                           wm_png=wm_png,
                           global_speed=self.spin_speed.value(),
                           max_3min=self.chk_max_3min.isChecked(),
                           mute_viral=self.chk_mute_viral.isChecked(),
                           volume=self.slider_volume.value() / 100.0,
                           out_w=ow, out_h=oh, quality=self.cmb_quality.currentData()),
            })
        self.render_progress.setMaximum(len(jobs))
        self.render_progress.setValue(0)
        self.render_progress.setFormat("合成中 %v / %m")
        self.btn_render.setEnabled(False)
        self._render_thread = RenderThread(jobs, self.spin_workers.value(), self.cmb_enc.currentData(), self)
        self._render_thread.progress.connect(lambda d, n: self.render_progress.setValue(d))
        self._render_thread.task_progress.connect(self._on_task_progress)
        for i in selected:
            pb = self.tbl_names.cellWidget(i, 2)
            if pb:
                pb.setValue(0)
        self._render_thread.log.connect(self.txt_log.appendPlainText)
        self._render_thread.finished_all.connect(self._on_render_done)
        self._render_thread.start()

    def _on_task_progress(self, index, pct):
        pb = self.tbl_names.cellWidget(index, 2)
        if pb:
            pb.setValue(int(pct))

    def _on_render_done(self, ok, n):
        self.btn_render.setEnabled(True)
        self.render_progress.setFormat(f"完成 {ok} / {n}")
        QMessageBox.information(self, "批量合成完成", f"成功 {ok} 个，失败 {n - ok} 个。\n输出目录：{self.txt_export_dir.text()}")

    def _choose_cache_root(self):
        d = QFileDialog.getExistingDirectory(self, "选择缓存存储位置", get_cache_dir())
        if d:
            set_cache_root(d)
            self.txt_cache_root.setText(get_cache_dir())
            self.save_settings()

    def clear_cache(self):
        if (self._align_thread and self._align_thread.isRunning()) or \
           (self._render_thread and self._render_thread.isRunning()):
            QMessageBox.warning(self, "请稍候", "正在处理任务，暂时不能清理缓存。")
            return
        dirs = list_task_cache_dirs()
        if not dirs:
            QMessageBox.information(self, "清理临时缓存", "当前缓存目录下没有可清理的任务缓存。")
            return
        size = 0
        for d in dirs:
            for r, _, fs in os.walk(d):
                for fn in fs:
                    try:
                        size += os.path.getsize(os.path.join(r, fn))
                    except Exception:
                        pass
        names = "\n".join(os.path.basename(d) for d in dirs[:12]) + ("\n……" if len(dirs) > 12 else "")
        if QMessageBox.question(self, "清理临时缓存",
                                f"缓存目录：{get_cache_dir()}\n将删除 {len(dirs)} 个任务缓存文件夹，"
                                f"约 {size / 1024 / 1024:.1f} MB：\n{names}\n\n"
                                f"（只删除本工具创建的「日期_合拍视频批量合成」文件夹）\n"
                                f"清理后需要重新「对齐时间线」。确定清理吗？") != QMessageBox.StandardButton.Yes:
            return
        for d in dirs:
            shutil.rmtree(d, ignore_errors=True)
        if self.task_dir and not os.path.isdir(self.task_dir):
            self.aligned = False
            self.task_dir = ""
        self._frame_cache.clear()
        self.update_align_status()
        QMessageBox.information(self, "已清理", "临时缓存已清理。")

    # ══════════════════════════════════════════════════════════════════════
    #  导航
    # ══════════════════════════════════════════════════════════════════════
    def switch_step(self, idx):
        if idx in (2, 3) and not self.aligned:
            QMessageBox.warning(self, "尚未对齐时间线",
                                "您尚未完成时间线对齐，将以无视频背景进行效果预览。\n"
                                "（如果仅为了编辑模板，可忽略此提示）")
        for i, b in enumerate(self.step_btns):
            b.setChecked(i == idx)
        self.stack.setCurrentIndex(idx)
        if idx == 1:
            self.refresh_tpl_library(select=self.edit_tpl.get("name"))
            self.refresh_tpl_frames()
        elif idx == 2:
            self.redraw_preview()
            self._preview_timer.start()
        elif idx == 3:
            self.refresh_export_table()

        texts = {
            0: (None, "下一步：字幕卡片 ➡️"),
            1: ("⬅️ 返回素材", "前往字幕卡片 ➡️"),
            2: ("⬅️ 返回素材", "下一步：导出设置 ➡️"),
            3: ("⬅️ 返回字幕卡片", None),
        }
        p, n = texts[idx]
        self.btn_prev.setVisible(p is not None)
        self.btn_next.setVisible(n is not None)
        if p:
            self.btn_prev.setText(p)
        if n:
            self.btn_next.setText(n)

    def go_prev(self):
        idx = self.stack.currentIndex()
        self.switch_step({1: 0, 2: 0, 3: 2}.get(idx, 0))

    def go_next(self):
        idx = self.stack.currentIndex()
        self.switch_step({0: 2, 1: 2, 2: 3}.get(idx, 3))

    # ══════════════════════════════════════════════════════════════════════
    #  设置保存
    # ══════════════════════════════════════════════════════════════════════
    # 全局 settings.json 只放软件偏好；每次任务的全部参数放在它自己的对齐文件夹 project.json
    _PREF_KEYS = ("export_dir", "res_idx", "quality_idx", "enc_idx", "workers", "volume",
                  "global_speed", "max_3min", "mute_person", "mute_viral")

    def _load_settings(self):
        s = self.settings
        state = None
        proj = s.get("last_project", "")
        if proj and os.path.isfile(os.path.join(proj, PROJECT_FILE)):
            try:
                state = load_project(proj)
                self.task_dir = proj
            except Exception as e:
                print("load project failed:", e)
        if state is None:
            # 旧版本把任务直接存在 settings.json 里：迁移过来
            if s.get("tasks"):
                state = dict(s)
                td = s["tasks"][0].get("task_dir", "")
                self.task_dir = td if td and os.path.isdir(td) else ""
            else:
                state = s.get("draft") or {}
        merged = {k: s[k] for k in self._PREF_KEYS if k in s}
        merged.update(state)
        self._apply_state(merged)

    def _apply_state(self, s):
        """把一份工程数据应用到界面（会先清空当前任务）。"""
        self.list_person.clear()
        self.list_viral.clear()
        self.tasks = []
        self.aligned = False
        if "title_cfg" in s:
            self.global_title_cfg = s["title_cfg"]
            self.title_editor.set_cfg(s["title_cfg"])
        if "phone_cfg" in s:
            self.global_phone_cfg = s["phone_cfg"]
            self.phone_editor.set_cfg(s["phone_cfg"])
        if "wm_cfg" in s:
            self.wm_editor.set_cfg(s["wm_cfg"])
        if s.get("person_videos"):
            self.list_person.add_files(s["person_videos"])
        if s.get("viral_videos"):
            self.list_viral.add_files(s["viral_videos"])
        for src, lw in self.extra_lists.items():
            lw.clear()
            if (s.get("extra_videos") or {}).get(src):
                lw.add_files(s["extra_videos"][src])
        self.spin_person_speed.setValue(float(s.get("person_speed", 1.0)))
        if s.get("tasks"):
            self.tasks = s["tasks"]
            self.aligned = s.get("aligned", False)
        self._frame_cache.clear()
        self._tpl_frames = {}
        self.cur_task = 0
        self.chk_mute_person.setChecked(s.get("mute_person", True))
        self.chk_mute_viral.setChecked(s.get("mute_viral", False))
        self.spin_speed.setValue(s.get("global_speed", s.get("speed", 1.0)))
        self.chk_max_3min.setChecked(s.get("max_3min", False))
        if s.get("export_dir"):
            self.txt_export_dir.setText(s["export_dir"])
        self.cmb_res.setCurrentIndex(s.get("res_idx", 0))
        self.cmb_quality.setCurrentIndex(s.get("quality_idx", 1))
        self.cmb_enc.setCurrentIndex(s.get("enc_idx", 0))
        self.spin_workers.setValue(s.get("workers", 2))
        self.slider_volume.setValue(s.get("volume", 100))
        if s.get("active_tpl") and self._tpl_by_name(s["active_tpl"]):
            self.active_tpl_name = s["active_tpl"]
            self.edit_tpl = dict(self._tpl_by_name(self.active_tpl_name))
        self._sync_source_lists()
        self.refresh_task_list()
        self.refresh_export_table()
        self.update_align_status()

    def _project_state(self):
        """当前这次任务的全部参数。"""
        return {
            "version": 1,
            "active_tpl": self.active_tpl_name,
            "person_videos": self.list_person.paths(),
            "viral_videos": self.list_viral.paths(),
            "extra_videos": {s: lw.paths() for s, lw in self.extra_lists.items()},
            "person_speed": self.spin_person_speed.value(),
            "tasks": getattr(self, "tasks", []),
            "aligned": getattr(self, "aligned", False),
            "title_cfg": getattr(self, "global_title_cfg", self.title_editor.get_cfg()),
            "phone_cfg": getattr(self, "global_phone_cfg", self.phone_editor.get_cfg()),
            "wm_cfg": self.wm_editor.get_cfg(),
            "mute_person": self.chk_mute_person.isChecked(),
            "mute_viral": self.chk_mute_viral.isChecked(),
            "export_dir": self.txt_export_dir.text(),
            "global_speed": self.spin_speed.value(),
            "max_3min": self.chk_max_3min.isChecked(),
            "res_idx": self.cmb_res.currentIndex(),
            "quality_idx": self.cmb_quality.currentIndex(),
            "enc_idx": self.cmb_enc.currentIndex(),
            "workers": self.spin_workers.value(),
            "volume": self.slider_volume.value(),
        }

    def _autosave(self):
        try:
            self.save_settings()
        except Exception as e:
            print("autosave failed:", e)

    def save_settings(self):
        state = self._project_state()
        has_proj = bool(self.task_dir and os.path.isdir(self.task_dir))
        if has_proj:
            save_project(self.task_dir, state)
        prefs = {
            "active_tpl": self.active_tpl_name,
            "cache_root": self.txt_cache_root.text() if hasattr(self, "txt_cache_root") else "",
            "last_project": self.task_dir if has_proj else "",
            "layout_presets_v1": True,
        }
        prefs.update({k: state[k] for k in self._PREF_KEYS})
        if not has_proj:
            # 还没对齐（没有工程文件夹）时，只临时记住导入的素材和卡片样式
            prefs["draft"] = {k: state[k] for k in
                              ("person_videos", "viral_videos", "extra_videos", "person_speed", "tasks", "aligned",
                               "title_cfg", "phone_cfg", "wm_cfg")}
        _save_json("settings.json", prefs)

    def _list_projects(self):
        root = get_cache_dir()
        out = []
        try:
            for n in os.listdir(root):
                d = os.path.join(root, n)
                f = os.path.join(d, PROJECT_FILE)
                if os.path.isfile(f):
                    out.append((os.path.getmtime(f), d))
        except Exception:
            pass
        return [d for _, d in sorted(out, reverse=True)]

    def _open_project(self):
        import time
        projs = self._list_projects()
        items = []
        for d in projs:
            try:
                with open(os.path.join(d, PROJECT_FILE), "r", encoding="utf-8") as fh:
                    n = len(json.load(fh).get("tasks") or [])
            except Exception:
                n = "?"
            t = time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(os.path.join(d, PROJECT_FILE))))
            mark = "  ← 当前" if self.task_dir and os.path.normcase(d) == os.path.normcase(self.task_dir) else ""
            items.append(f"{os.path.basename(d)}    （{n} 组任务，{t}）{mark}")
        browse = "📁 浏览其他位置的文件夹…"
        items.append(browse)
        sel, ok = QInputDialog.getItem(self, "打开已对齐工程",
                                       f"缓存目录：{get_cache_dir()}\n选择要打开的工程：", items, 0, False)
        if not ok:
            return
        if sel == browse:
            d = QFileDialog.getExistingDirectory(self, "选择以前对齐的文件夹", get_cache_dir())
            if not d:
                return
        else:
            d = projs[items.index(sel)]
        if not os.path.isfile(os.path.join(d, PROJECT_FILE)):
            QMessageBox.warning(self, "无法打开",
                                "这个文件夹里没有工程文件（project.json）。\n"
                                "可能是旧版本对齐的文件夹，当时还不会保存任务参数。")
            return
        try:
            data = load_project(d)
        except Exception as e:
            QMessageBox.critical(self, "打开失败", f"工程文件读取失败：{e}")
            return
        self.save_settings()          # 先保存当前工程
        self.task_dir = d
        self._apply_state(data)
        self.refresh_tpl_combos()
        self.redraw_preview()
        self.save_settings()
        missing = sum(1 for t in self.tasks if t.get("cache") and not os.path.isfile(t["cache"]))
        msg = f"已打开工程：{os.path.basename(d)}\n共 {len(self.tasks)} 组任务。"
        if missing:
            msg += f"\n\n⚠️ 有 {missing} 个对齐视频找不到了，请重新点击「开始对齐」（文字和卡片参数会保留）。"
            self.aligned = False
            self.update_align_status()
        QMessageBox.information(self, "打开工程", msg)

    def _restore_backup(self):
        import glob, time
        if not self.task_dir or not os.path.isdir(self.task_dir):
            QMessageBox.information(self, "恢复本工程历史", "当前还没有工程（请先对齐，或打开已对齐工程）。")
            return
        files = sorted(glob.glob(os.path.join(project_backup_dir(self.task_dir), "project_*.json")), reverse=True)
        if not files:
            QMessageBox.information(self, "恢复本工程历史", "这个工程还没有历史快照。\n软件运行后会自动保存。")
            return
        items = []
        for f in files:
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    n = len(json.load(fh).get("tasks") or [])
            except Exception:
                n = "?"
            t = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(f)))
            items.append(f"{t}    （{n} 组任务）")
        sel, ok = QInputDialog.getItem(self, "恢复本工程历史",
                                       f"工程：{os.path.basename(self.task_dir)}\n选择要恢复的时间点：", items, 0, False)
        if not ok:
            return
        try:
            with open(files[items.index(sel)], "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception as e:
            QMessageBox.critical(self, "恢复失败", f"快照文件损坏：{e}")
            return
        # 先把当前状态单独存一份，便于反悔
        try:
            with open(os.path.join(project_backup_dir(self.task_dir),
                                   f"project_{time.strftime('%Y%m%d_%H%M%S')}_before_restore.json"),
                      "w", encoding="utf-8") as fh:
                json.dump(self._project_state(), fh, ensure_ascii=False, indent=2)
        except Exception:
            pass
        self._apply_state(data)
        self.refresh_tpl_combos()
        self.redraw_preview()
        self.save_settings()
        QMessageBox.information(self, "恢复完成", f"已恢复到：{sel}")
