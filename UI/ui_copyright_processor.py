# ui_copyright_processor.py
"""
「🎨 处理版权图片」标签页 UI
模式一：人物遮脸 — 检测人脸 → 遮脸图 + 大头图
模式二：左右裁剪 — 检测人脸中心 X 轴 → 左/右两张
"""

import os
from pathlib import Path

from PyQt6.QtCore import Qt, QSettings, pyqtSignal, QRect, QPoint
from PyQt6.QtGui import QFont, QColor, QPainter, QPen, QPixmap, QCursor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QListWidget, QListWidgetItem, QFileDialog,
    QProgressBar, QPlainTextEdit, QAbstractSpinBox,
    QScrollArea, QSizePolicy, QMessageBox, QComboBox,
    QStackedWidget, QColorDialog, QSlider, QDialog,
    QDialogButtonBox, QRubberBand,
)

from image_worker.copyright_worker import CopyrightWorker, SUPPORTED_IMAGE_EXT


COVER_STYLES = {
    "🔲 马赛克":    "mosaic",
    "🌫️ 模糊":    "blur",
    "⬛ 黑色方块":  "black_box",
    "⭕ 彩色圆形":  "colored_circle",
    "⭐ 金色星形":  "star",
    "😊 黄色笑脸":  "smiley",
}


# ─────────────────────────────────────────────────────────────────────────────
# 手动标记画布：支持鼠标拖拽选取矩形区域
# ─────────────────────────────────────────────────────────────────────────────

class AnnotationCanvas(QLabel):
    """
    显示图片并允许用户用鼠标拖拽框选人脸区域。
    - 绿色实线框：已确认的区域
    - 橙色虚线框：正在拖拽的新选区
    - 坐标系统：emit 的 region_changed 信号使用原始图片像素坐标
    """
    region_changed = pyqtSignal(tuple)   # (x, y, w, h) 原始图片坐标

    def __init__(self, parent=None):
        super().__init__(parent)
        self._orig_pixmap: QPixmap | None = None
        self._scale   = 1.0
        self._off_x   = 0
        self._off_y   = 0
        self._drag_start: QPoint | None = None
        self._drag_cur:   QPoint | None = None
        self._region: tuple | None = None   # (x, y, w, h) 原始坐标
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(500, 420)
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
        self.setMouseTracking(True)

    def load_image(self, path: str):
        self._orig_pixmap = QPixmap(path)
        self._region = None
        self._drag_start = None
        self._drag_cur   = None
        self._repaint()

    def set_region(self, rect: tuple | None):
        """设置已有标注区域（原始像素坐标）。"""
        self._region = rect
        self._repaint()

    def get_region(self) -> tuple | None:
        return self._region

    def clear_region(self):
        self._region = None
        self._drag_start = None
        self._drag_cur   = None
        self._repaint()

    # ── 坐标转换 ──────────────────────────────────────────────────────────────

    def _compute_layout(self):
        """计算当前 widget 尺寸下图片的缩放比例和偏移量。"""
        if not self._orig_pixmap:
            return
        lw, lh = self.width(), self.height()
        ow, oh  = self._orig_pixmap.width(), self._orig_pixmap.height()
        if ow == 0 or oh == 0:
            return
        s = min(lw / ow, lh / oh)
        self._scale = s
        dw = int(ow * s)
        dh = int(oh * s)
        self._off_x = (lw - dw) // 2
        self._off_y = (lh - dh) // 2

    def _widget_to_orig(self, pt: QPoint) -> tuple[int, int]:
        """Widget 坐标 → 原始图片坐标（钳位在图片范围内）。"""
        if not self._orig_pixmap or self._scale == 0:
            return 0, 0
        rx = (pt.x() - self._off_x) / self._scale
        ry = (pt.y() - self._off_y) / self._scale
        rx = max(0, min(rx, self._orig_pixmap.width()))
        ry = max(0, min(ry, self._orig_pixmap.height()))
        return int(rx), int(ry)

    def _orig_rect_to_widget(self, x, y, w, h) -> tuple[int, int, int, int]:
        """原始坐标矩形 → widget 坐标矩形。"""
        wx = self._off_x + int(x * self._scale)
        wy = self._off_y + int(y * self._scale)
        ww = int(w * self._scale)
        wh = int(h * self._scale)
        return wx, wy, ww, wh

    # ── 绘制 ──────────────────────────────────────────────────────────────────

    def _repaint(self):
        if not self._orig_pixmap:
            return
        self._compute_layout()
        ow, oh = self._orig_pixmap.width(), self._orig_pixmap.height()
        dw = int(ow * self._scale)
        dh = int(oh * self._scale)

        canvas = QPixmap(self.width(), self.height())
        canvas.fill(QColor(30, 30, 30))

        p = QPainter(canvas)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        scaled = self._orig_pixmap.scaled(
            dw, dh,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        p.drawPixmap(self._off_x, self._off_y, scaled)

        # 已确认区域 — 绿色实线框 + 半透明填充
        if self._region:
            x, y, w, h = self._region
            wx, wy, ww, wh = self._orig_rect_to_widget(x, y, w, h)
            p.setPen(QPen(QColor(50, 220, 100), 2, Qt.PenStyle.SolidLine))
            p.drawRect(wx, wy, ww, wh)
            p.fillRect(wx, wy, ww, wh, QColor(50, 220, 100, 45))

        # 拖拽中的选区 — 橙色虚线框
        if self._drag_start and self._drag_cur:
            x1 = min(self._drag_start.x(), self._drag_cur.x())
            y1 = min(self._drag_start.y(), self._drag_cur.y())
            x2 = max(self._drag_start.x(), self._drag_cur.x())
            y2 = max(self._drag_start.y(), self._drag_cur.y())
            pen = QPen(QColor(255, 130, 0), 2, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawRect(x1, y1, x2 - x1, y2 - y1)
            p.fillRect(x1, y1, x2 - x1, y2 - y1, QColor(255, 130, 0, 40))

        p.end()
        self.setPixmap(canvas)

    # ── 鼠标事件 ──────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.position().toPoint()
            self._drag_cur   = event.position().toPoint()

    def mouseMoveEvent(self, event):
        if self._drag_start:
            self._drag_cur = event.position().toPoint()
            self._repaint()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._drag_start:
            self._drag_cur = event.position().toPoint()
            x1, y1 = self._widget_to_orig(self._drag_start)
            x2, y2 = self._widget_to_orig(self._drag_cur)
            rw, rh = abs(x2 - x1), abs(y2 - y1)
            if rw > 10 and rh > 10:
                self._region = (min(x1, x2), min(y1, y2), rw, rh)
                self.region_changed.emit(self._region)
            self._drag_start = None
            self._drag_cur   = None
            self._repaint()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._repaint()


# ─────────────────────────────────────────────────────────────────────────────
# 手动标记对话框
# ─────────────────────────────────────────────────────────────────────────────

class FaceRegionEditor(QDialog):
    """
    让用户在图片上手动框选人脸区域。
    框选区域将同时用于：
      • 打马赛克 / 遮脸（使用框选区域）
      • 大头图裁剪（使用框选区域，不做自动扩展）
    """

    def __init__(self, image_path: str, existing_rect: tuple | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"🎯 手动标记区域 — {Path(image_path).name}")
        self.setMinimumSize(780, 640)
        self._result: tuple | None = None

        lay = QVBoxLayout(self)
        lay.setSpacing(8)

        # 说明文字
        hint = QLabel(
            "📌 <b>在图片上拖拽鼠标</b>框选人脸区域（绿框 = 已确认，橙框 = 拖拽中）。\n"
            "  框选区域将同时用于打马赛克/遮挡 和 大头图裁剪。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #94a3b8; font-size: 9pt; padding: 4px 0;")
        lay.addWidget(hint)

        # 画布
        self.canvas = AnnotationCanvas()
        self.canvas.load_image(image_path)
        if existing_rect:
            self.canvas.set_region(existing_rect)
        lay.addWidget(self.canvas, 1)

        # 状态标签
        self.lbl_status = QLabel("尚未框选区域，请拖拽鼠标选取人脸区域。")
        self.lbl_status.setStyleSheet("color: #64748b; font-size: 9pt;")
        lay.addWidget(self.lbl_status)
        if existing_rect:
            x, y, w, h = existing_rect
            self.lbl_status.setText(f"当前标记：x={x}, y={y}, 宽={w}, 高={h}（可重新拖拽覆盖）")
        self.canvas.region_changed.connect(self._on_region_changed)

        # 按钮行
        btn_row = QHBoxLayout()
        self.btn_clear = QPushButton("🗑 清除选区")
        self.btn_clear.setToolTip("清除当前框选区域，恢复自动检测")
        self.btn_clear.clicked.connect(self._clear)

        self.btn_ok = QPushButton("✅ 确认使用此区域")
        self.btn_ok.setDefault(True)
        self.btn_ok.setEnabled(existing_rect is not None)
        self.btn_ok.clicked.connect(self._confirm)

        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)

        btn_row.addWidget(self.btn_clear)
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(self.btn_ok)
        lay.addLayout(btn_row)

    def _on_region_changed(self, rect: tuple):
        x, y, w, h = rect
        self.lbl_status.setText(f"已框选：x={x}, y={y}, 宽={w}px, 高={h}px — 点击「确认」保存")
        self.btn_ok.setEnabled(True)

    def _clear(self):
        self.canvas.clear_region()
        self.lbl_status.setText("选区已清除。处理时将恢复自动检测。")
        self.btn_ok.setEnabled(True)   # 允许「确认清除」

    def _confirm(self):
        self._result = self.canvas.get_region()   # None = 清除
        self.accept()

    def get_result(self) -> tuple | None:
        """返回 (x, y, w, h) 或 None（用户清除了标记）。"""
        return self._result


class CopyrightProcessorUI(QWidget):

    """版权图片处理主页面"""

    def __init__(self):
        super().__init__()
        self.worker: CopyrightWorker | None = None
        self.output_dir = ""
        self.circle_color = (255, 80, 80)      # 彩色圆形默认颜色（RGB）
        self.settings = QSettings("MyCompany", "VideoToolbox")
        self.manual_annotations: dict[str, tuple | None] = {}  # path → (x,y,w,h) 或 None

        self._setup_ui()
        self._bind_events()
        self.load_settings()


    # ── 持久化 ────────────────────────────────────────────────────────────────

    def load_settings(self):
        mode = self.settings.value("cp_mode", "face_cover")
        if mode == "face_cover":
            self.btn_mode_face.setChecked(True)
            self.btn_mode_split.setChecked(False)
            self.stack_params.setCurrentIndex(0)
        else:
            self.btn_mode_split.setChecked(True)
            self.btn_mode_face.setChecked(False)
            self.stack_params.setCurrentIndex(1)

        style_label = self.settings.value("cp_cover_style_label", "🔲 马赛克")
        idx = self.combo_cover.findText(style_label)
        if idx >= 0:
            self.combo_cover.setCurrentIndex(idx)

        r = self.settings.value("cp_circle_r", 255, type=int)
        g = self.settings.value("cp_circle_g", 80,  type=int)
        b = self.settings.value("cp_circle_b", 80,  type=int)
        self.circle_color = (r, g, b)
        self._update_color_btn()

        saved_dir = self.settings.value("cp_output_dir", "")
        if saved_dir and os.path.isdir(saved_dir):
            self.output_dir = saved_dir
            self.lbl_out_path.setText(f"已选择: {saved_dir}")

    def save_settings(self):
        mode = "face_cover" if self.btn_mode_face.isChecked() else "lr_split"
        self.settings.setValue("cp_mode",              mode)
        self.settings.setValue("cp_cover_style_label", self.combo_cover.currentText())
        self.settings.setValue("cp_circle_r",          self.circle_color[0])
        self.settings.setValue("cp_circle_g",          self.circle_color[1])
        self.settings.setValue("cp_circle_b",          self.circle_color[2])
        self.settings.setValue("cp_output_dir",        self.output_dir)

    # ── UI 构建 ───────────────────────────────────────────────────────────────

    def _create_card(self, title: str):
        card = QFrame()
        card.setProperty("class", "Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(10)
        lbl = QLabel(title)
        lbl.setProperty("class", "CardTitle")
        layout.addWidget(lbl)
        return card, layout

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.viewport().setAutoFillBackground(False)
        outer.addWidget(scroll)

        inner = QWidget()
        inner.setAutoFillBackground(False)
        scroll.setWidget(inner)
        main = QVBoxLayout(inner)
        main.setContentsMargins(0, 0, 1, 0)
        main.setSpacing(10)

        # ═══════════════════════════════════════════════════════════════════
        # 板块一：模式选择
        # ═══════════════════════════════════════════════════════════════════
        card1, lay1 = self._create_card("🎭 板块一 · 选择处理模式")

        hint_mode = QLabel(
            "根据需要选择处理模式。两种模式均支持批量上传图片，自动检测人物面部位置。"
        )
        hint_mode.setStyleSheet("color: #6b7280; font-size: 9pt;")
        hint_mode.setWordWrap(True)
        lay1.addWidget(hint_mode)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(12)

        self.btn_mode_face = QPushButton("🎭  人物遮脸模式")
        self.btn_mode_face.setCheckable(True)
        self.btn_mode_face.setChecked(True)
        self.btn_mode_face.setFixedHeight(44)
        self.btn_mode_face.setToolTip(
            "检测人物面部 → 生成遮脸图（遮挡人脸）和大头图（裁剪人脸区域）"
        )

        self.btn_mode_split = QPushButton("✂️  左右裁剪模式")
        self.btn_mode_split.setCheckable(True)
        self.btn_mode_split.setChecked(False)
        self.btn_mode_split.setFixedHeight(44)
        self.btn_mode_split.setToolTip(
            "以人物的 X 轴中心为基准，将图片拆分为左右两张"
        )

        for btn in (self.btn_mode_face, self.btn_mode_split):
            btn.setProperty("class", "NavBtn")
            mode_row.addWidget(btn)
        mode_row.addStretch()
        lay1.addLayout(mode_row)

        main.addWidget(card1)

        # ═══════════════════════════════════════════════════════════════════
        # 板块二：图片输入
        # ═══════════════════════════════════════════════════════════════════
        card2, lay2 = self._create_card("🖼️ 板块二 · 图片输入")

        hint_img = QLabel(
            f"支持格式：{', '.join(sorted(SUPPORTED_IMAGE_EXT))}  ·  可拖拽文件或点击按钮批量添加"
        )
        hint_img.setStyleSheet("color: #6b7280; font-size: 9pt;")
        lay2.addWidget(hint_img)

        img_btn_row = QHBoxLayout()
        img_btn_row.setSpacing(10)
        self.btn_add_files  = QPushButton("➕ 添加图片")
        self.btn_add_folder = QPushButton("📁 添加文件夹")
        self.btn_clear_list = QPushButton("🗑 清空列表")
        for btn in (self.btn_add_files, self.btn_add_folder, self.btn_clear_list):
            btn.setFixedHeight(34)
            img_btn_row.addWidget(btn)
        img_btn_row.addStretch()
        lay2.addLayout(img_btn_row)

        self.img_list = QListWidget()
        self.img_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.img_list.setMinimumHeight(140)
        self.img_list.setMaximumHeight(220)
        self.img_list.setAcceptDrops(True)
        self.img_list.setToolTip("支持拖拽图片文件到此处")
        lay2.addWidget(self.img_list)

        # 「手动标记」按钮行
        annotate_row = QHBoxLayout()
        annotate_row.setSpacing(10)
        self.btn_annotate = QPushButton("🎯 手动标记选中图片")
        self.btn_annotate.setFixedHeight(34)
        self.btn_annotate.setEnabled(False)
        self.btn_annotate.setToolTip(
            "为选中的图片手动框选人脸/遮脸区域。\n"
            "框选后该图片将跳过自动检测，直接使用你框选的区域。"
        )
        annotate_row.addWidget(self.btn_annotate)
        self.lbl_annotate_hint = QLabel("选中列表中的图片后可手动标记人脸区域")
        self.lbl_annotate_hint.setStyleSheet("color: #6b7280; font-size: 9pt;")
        annotate_row.addWidget(self.lbl_annotate_hint)
        annotate_row.addStretch()
        lay2.addLayout(annotate_row)

        self.lbl_img_count = QLabel("尚未添加图片")
        self.lbl_img_count.setStyleSheet("color: #6b7280; font-size: 9pt;")
        lay2.addWidget(self.lbl_img_count)


        main.addWidget(card2)

        # ═══════════════════════════════════════════════════════════════════
        # 板块三：参数设置（根据模式动态切换）
        # ═══════════════════════════════════════════════════════════════════
        card3, lay3 = self._create_card("⚙️ 板块三 · 参数设置")

        self.stack_params = QStackedWidget()

        # ── 遮脸模式参数面板 ──────────────────────────────────────────────
        face_panel = QWidget()
        face_layout = QVBoxLayout(face_panel)
        face_layout.setContentsMargins(0, 0, 0, 0)
        face_layout.setSpacing(12)

        style_row = QHBoxLayout()
        style_row.setSpacing(12)
        style_row.addWidget(QLabel("遮脸图形："))
        self.combo_cover = QComboBox()
        for label in COVER_STYLES:
            self.combo_cover.addItem(label)
        self.combo_cover.setMinimumWidth(200)
        self.combo_cover.setToolTip("选择在人脸上方绘制的遮挡图形样式")
        style_row.addWidget(self.combo_cover)

        self.btn_color = QPushButton("  自定义颜色")
        self.btn_color.setFixedWidth(140)
        self.btn_color.setToolTip("点击选择「彩色圆形」使用的颜色")
        style_row.addWidget(self.btn_color)
        style_row.addStretch()
        face_layout.addLayout(style_row)

        # ── 检测灵敏度 ────────────────────────────────────────────────────
        sens_row = QHBoxLayout()
        sens_row.setSpacing(10)
        sens_row.addWidget(QLabel("检测灵敏度："))
        self.slider_confidence = QSlider(Qt.Orientation.Horizontal)
        self.slider_confidence.setRange(1, 5)    # 1=极高灵敏度(0.05), 5=低灵敏度(0.45)
        self.slider_confidence.setValue(3)       # 默认中等
        self.slider_confidence.setFixedWidth(160)
        self.slider_confidence.setToolTip(
            "灵敏度越高，能检测到更多/更难识别的人脸，但可能误判\n"
            "灵敏度越低，只检测非常明显的正面人脸"
        )
        self.lbl_confidence = QLabel("中")
        self.lbl_confidence.setFixedWidth(60)
        self.lbl_confidence.setStyleSheet("color: #60a5fa; font-weight: bold;")
        self.slider_confidence.valueChanged.connect(self._on_confidence_changed)
        sens_row.addWidget(self.slider_confidence)
        sens_row.addWidget(self.lbl_confidence)
        sens_row.addStretch()
        face_layout.addLayout(sens_row)

        # ── 检测失败时的处理方式 ──────────────────────────────────────────
        fallback_row = QHBoxLayout()
        fallback_row.setSpacing(10)
        fallback_row.addWidget(QLabel("未检测到人脸时："))
        self.combo_fallback = QComboBox()
        self.combo_fallback.addItem("跳过该图片", "skip")
        self.combo_fallback.addItem("使用图片顶部区域（适合正面肖像）", "use_top")
        self.combo_fallback.setToolTip(
            "跳过：未检测到人脸时忽略该图片（默认）\n"
            "使用顶部区域：将图片顶部35%宽60%范围作为人脸区域处理（适合检测失败的正面肖像）"
        )
        fallback_row.addWidget(self.combo_fallback)
        fallback_row.addStretch()
        face_layout.addLayout(fallback_row)

        face_hint = QLabel(
            "软件将自动检测图片中面积最大的人脸，生成：\n"
            "  ① 原图名_遮脸.jpg — 用所选图形遮挡人脸\n"
            "  ② 原图名_大头图.jpg — 裁剪出人脸区域（紧贴五官，无留白）"
        )
        face_hint.setStyleSheet("color: #6b7280; font-size: 9pt;")
        face_hint.setWordWrap(True)
        face_layout.addWidget(face_hint)

        self.stack_params.addWidget(face_panel)


        # ── 左右裁剪模式参数面板 ──────────────────────────────────────────
        split_panel = QWidget()
        split_layout = QVBoxLayout(split_panel)
        split_layout.setContentsMargins(0, 0, 0, 0)
        split_layout.setSpacing(8)

        split_hint = QLabel(
            "软件将检测图片中的主要人物位置，以人物的面部中心 X 轴为分割线，\n"
            "将图片拆分为左右两张，生成：\n"
            "  ① 原图名_左.jpg — 分割线左侧部分\n"
            "  ② 原图名_右.jpg — 分割线右侧部分\n\n"
            "⚠️ 分割点自动约束在图片宽度的 20%~80% 范围内，避免人物被完整截入一侧。\n"
            "⚠️ 若未检测到人脸，将从图片水平中心分割。"
        )
        split_hint.setStyleSheet("color: #6b7280; font-size: 9pt;")
        split_hint.setWordWrap(True)
        split_layout.addWidget(split_hint)
        split_layout.addStretch()

        self.stack_params.addWidget(split_panel)

        lay3.addWidget(self.stack_params)
        main.addWidget(card3)

        # ═══════════════════════════════════════════════════════════════════
        # 板块四：输出目录
        # ═══════════════════════════════════════════════════════════════════
        card4, lay4 = self._create_card("📁 板块四 · 输出目录")

        out_row = QHBoxLayout()
        out_row.setSpacing(10)
        self.btn_out_path = QPushButton("📁 选择输出目录")
        self.btn_out_path.setFixedWidth(150)
        self.lbl_out_path = QLabel("尚未选择输出目录")
        self.lbl_out_path.setStyleSheet("color: #6b7280;")
        out_row.addWidget(self.btn_out_path)
        out_row.addWidget(self.lbl_out_path, 1)
        lay4.addLayout(out_row)

        out_note = QLabel("处理结果将保存到此目录，文件名格式见板块三说明。")
        out_note.setStyleSheet("color: #6b7280; font-size: 9pt;")
        lay4.addWidget(out_note)

        main.addWidget(card4)

        # ═══════════════════════════════════════════════════════════════════
        # 板块五：进度与日志
        # ═══════════════════════════════════════════════════════════════════
        card5, lay5 = self._create_card("📊 板块五 · 进度与日志")

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(18)
        self.progress_bar.setTextVisible(True)
        lay5.addWidget(self.progress_bar)

        self.lbl_status = QLabel("就绪 — 请添加图片并点击「开始处理」")
        self.lbl_status.setStyleSheet("color: #6b7280; font-size: 9pt;")
        lay5.addWidget(self.lbl_status)

        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(200)
        self.log_text.setFont(QFont("Consolas", 9))
        self.log_text.setPlaceholderText("运行日志将在此处实时显示...")
        lay5.addWidget(self.log_text)

        btn_row = QHBoxLayout()
        self.btn_clear_log = QPushButton("🗑 清空日志")
        self.btn_clear_log.setFixedWidth(110)
        btn_row.addWidget(self.btn_clear_log)
        btn_row.addStretch()

        self.btn_start = QPushButton("🚀 开始处理")
        self.btn_start.setObjectName("PrimaryBtn")
        self.btn_start.setFixedHeight(46)
        self.btn_stop  = QPushButton("🛑 停止")
        self.btn_stop.setEnabled(False)
        self.btn_stop.setFixedHeight(46)

        btn_row.addWidget(self.btn_start, stretch=3)
        btn_row.addWidget(self.btn_stop,  stretch=1)
        lay5.addLayout(btn_row)

        main.addWidget(card5)
        main.addStretch()

    # ── 事件绑定 ──────────────────────────────────────────────────────────────

    def _bind_events(self):
        self.btn_mode_face.clicked.connect(lambda: self._switch_mode("face_cover"))
        self.btn_mode_split.clicked.connect(lambda: self._switch_mode("lr_split"))
        self.btn_add_files.clicked.connect(self._add_files)
        self.btn_add_folder.clicked.connect(self._add_folder)
        self.btn_clear_list.clicked.connect(self._clear_list)
        self.btn_annotate.clicked.connect(self._manual_annotate)
        self.btn_color.clicked.connect(self._pick_color)
        self.btn_out_path.clicked.connect(self._select_output_dir)
        self.btn_clear_log.clicked.connect(self.log_text.clear)
        self.btn_start.clicked.connect(self._start_task)
        self.btn_stop.clicked.connect(self._stop_task)
        self.combo_cover.currentTextChanged.connect(self._on_style_changed)
        self.img_list.itemSelectionChanged.connect(self._on_list_selection_changed)
        # 拖拽支持
        self.img_list.installEventFilter(self)

    # ── 模式切换 ──────────────────────────────────────────────────────────────

    def _switch_mode(self, mode: str):
        if mode == "face_cover":
            self.btn_mode_face.setChecked(True)
            self.btn_mode_split.setChecked(False)
            self.stack_params.setCurrentIndex(0)
        else:
            self.btn_mode_split.setChecked(True)
            self.btn_mode_face.setChecked(False)
            self.stack_params.setCurrentIndex(1)

    def _on_style_changed(self, text: str):
        """显示/隐藏自定义颜色按钮（仅彩色圆形时显示）。"""
        self.btn_color.setVisible("彩色圆形" in text)

    def _on_confidence_changed(self, value: int):
        """滑块值 1~5 对应灵敏度标签和置信度阈值。"""
        labels = {1: "极高", 2: "高", 3: "中", 4: "低", 5: "精准"}
        self.lbl_confidence.setText(labels.get(value, "中"))

    def _get_min_confidence(self) -> float:
        """将滑块值（1~5）转换为 mediapipe 的最低检测置信度。"""
        # 1→0.05（最灵敏），5→0.45（最精准）
        mapping = {1: 0.05, 2: 0.1, 3: 0.15, 4: 0.25, 5: 0.45}
        return mapping.get(self.slider_confidence.value(), 0.15)

    # ── 图片列表操作 ──────────────────────────────────────────────────────────

    def _get_current_paths(self) -> set:
        paths = set()
        for i in range(self.img_list.count()):
            paths.add(self.img_list.item(i).data(Qt.ItemDataRole.UserRole))
        return paths

    def _add_paths(self, paths: list):
        existing = self._get_current_paths()
        added = 0
        for p in paths:
            if p not in existing and Path(p).suffix.lower() in SUPPORTED_IMAGE_EXT:
                item = QListWidgetItem(Path(p).name)
                item.setData(Qt.ItemDataRole.UserRole, p)
                item.setToolTip(p)
                self.img_list.addItem(item)
                added += 1
        self._update_count_label()
        return added

    def _add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择图片文件", "",
            "图片文件 (*.jpg *.jpeg *.png *.webp *.bmp *.tiff *.tif)"
        )
        if files:
            added = self._add_paths(files)
            self._append_log(f"已添加 {added} 张图片。")

    def _add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择图片文件夹")
        if not folder:
            return
        paths = []
        for root, _, fnames in os.walk(folder):
            for fname in fnames:
                if Path(fname).suffix.lower() in SUPPORTED_IMAGE_EXT:
                    paths.append(os.path.join(root, fname))
        added = self._add_paths(paths)
        self._append_log(f"已从文件夹添加 {added} 张图片。")

    def _clear_list(self):
        self.img_list.clear()
        self.manual_annotations.clear()
        self._update_count_label()

    def _update_count_label(self):
        n = self.img_list.count()
        ann_n = sum(1 for v in self.manual_annotations.values() if v is not None)
        if n == 0:
            self.lbl_img_count.setText("尚未添加图片")
        elif ann_n > 0:
            self.lbl_img_count.setText(f"共 {n} 张图片（其中 {ann_n} 张已手动标记 🎯）")
        else:
            self.lbl_img_count.setText(f"共 {n} 张图片")

    # ── 手动标记 ──────────────────────────────────────────────────────────────

    def _on_list_selection_changed(self):
        """根据列表选中状态启用/禁用手动标记按钮。"""
        selected = self.img_list.selectedItems()
        has_one  = len(selected) == 1
        self.btn_annotate.setEnabled(has_one)
        if has_one:
            path = selected[0].data(Qt.ItemDataRole.UserRole)
            has_ann = path in self.manual_annotations and self.manual_annotations[path] is not None
            self.lbl_annotate_hint.setText(
                "🎯 已手动标记" if has_ann else "点击按钮为选中图片手动框选人脸区域"
            )
        else:
            self.lbl_annotate_hint.setText("选中列表中的图片后可手动标记人脸区域")

    def _manual_annotate(self):
        """打开手动标记对话框，为选中的图片框选人脸区域。"""
        selected = self.img_list.selectedItems()
        if len(selected) != 1:
            return
        item = selected[0]
        path = item.data(Qt.ItemDataRole.UserRole)
        existing = self.manual_annotations.get(path)

        dlg = FaceRegionEditor(path, existing, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        result = dlg.get_result()
        name   = Path(path).name

        if result:
            self.manual_annotations[path] = result
            item.setText(f"🎯 {name}")
            item.setToolTip(f"[手动标记] {path}")
        else:
            # 用户点「清除选区」后确认 → 取消手动标记
            self.manual_annotations.pop(path, None)
            item.setText(name)
            item.setToolTip(path)

        self._update_count_label()
        self._on_list_selection_changed()



    def _get_image_paths(self) -> list:
        return [
            self.img_list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.img_list.count())
        ]

    # ── 颜色选择 ──────────────────────────────────────────────────────────────

    def _pick_color(self):
        init = QColor(*self.circle_color)
        color = QColorDialog.getColor(init, self, "选择圆形填充颜色")
        if color.isValid():
            self.circle_color = (color.red(), color.green(), color.blue())
            self._update_color_btn()

    def _update_color_btn(self):
        r, g, b = self.circle_color
        text_color = "#ffffff" if (r * 299 + g * 587 + b * 114) / 1000 < 128 else "#000000"
        self.btn_color.setStyleSheet(
            f"background-color: rgb({r},{g},{b}); color: {text_color}; "
            f"border-radius: 6px; padding: 6px 12px;"
        )

    # ── 输出目录 ──────────────────────────────────────────────────────────────

    def _select_output_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if d:
            self.output_dir = d
            self.lbl_out_path.setText(f"已选择: {d}")
            self.lbl_out_path.setStyleSheet("")

    # ── 日志 ─────────────────────────────────────────────────────────────────

    def _append_log(self, msg: str):
        self.log_text.appendPlainText(msg)
        sb = self.log_text.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ── 任务控制 ──────────────────────────────────────────────────────────────

    def _start_task(self):
        paths = self._get_image_paths()
        if not paths:
            QMessageBox.warning(self, "提示", "请先添加至少一张图片！")
            return
        if not self.output_dir:
            QMessageBox.warning(self, "提示", "请先选择输出目录！")
            return

        mode = "face_cover" if self.btn_mode_face.isChecked() else "lr_split"
        cover_style = COVER_STYLES.get(self.combo_cover.currentText(), "mosaic")

        self.log_text.clear()
        self.progress_bar.setValue(0)
        mode_name = "人物遮脸" if mode == "face_cover" else "左右裁剪"
        self.lbl_status.setText(f"准备以「{mode_name}」模式处理 {len(paths)} 张图片...")
        self._set_running(True)

        self.worker = CopyrightWorker(
            image_paths        = paths,
            mode               = mode,
            cover_style        = cover_style,
            circle_color       = self.circle_color,
            output_dir         = self.output_dir,
            min_confidence     = self._get_min_confidence(),
            face_fallback      = self.combo_fallback.currentData(),
            manual_annotations = dict(self.manual_annotations),   # 传副本
        )
        self.worker.log_signal.connect(self._append_log)
        self.worker.progress_signal.connect(self._on_progress)
        self.worker.finished_signal.connect(self._on_finished)
        self.worker.start()

    def _stop_task(self):
        if self.worker:
            self.worker.stop()
            self.lbl_status.setText("正在停止，请稍候...")
            self.btn_stop.setEnabled(False)

    def _set_running(self, running: bool):
        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        self.btn_add_files.setEnabled(not running)
        self.btn_add_folder.setEnabled(not running)
        self.btn_clear_list.setEnabled(not running)

    # ── Worker 信号 ───────────────────────────────────────────────────────────

    def _on_progress(self, pct: int, text: str):
        self.progress_bar.setValue(pct)
        self.lbl_status.setText(text)

    def _on_finished(self, success: bool, message: str):
        self._set_running(False)
        self.progress_bar.setValue(100 if success else self.progress_bar.value())
        self.lbl_status.setText(message)
        if success:
            QMessageBox.information(self, "完成", message)
        else:
            QMessageBox.warning(self, "任务结束", message)

    # ── 拖拽支持 ──────────────────────────────────────────────────────────────

    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent
        if obj is self.img_list:
            if event.type() == QEvent.Type.DragEnter:
                if event.mimeData().hasUrls():
                    event.acceptProposedAction()
                    return True
            elif event.type() == QEvent.Type.Drop:
                urls = event.mimeData().urls()
                paths = [u.toLocalFile() for u in urls]
                added = self._add_paths(paths)
                self._append_log(f"拖拽添加 {added} 张图片。")
                return True
        return super().eventFilter(obj, event)
