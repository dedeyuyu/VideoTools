"""
ui_landscape_to_portrait.py
横屏转竖屏 — 将 16:9 视频转换为 9:16 竖屏格式
"""
import os
import sys

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QFileDialog, QProgressBar,
    QSpinBox, QComboBox, QLineEdit, QPlainTextEdit, QCheckBox,
    QRadioButton, QButtonGroup, QFrame, QScrollArea, QSizePolicy,
    QColorDialog, QMessageBox, QAbstractItemView,
)
from PyQt6.QtCore import Qt, QSettings, QMimeData
from PyQt6.QtGui import QColor, QFont, QDragEnterEvent, QDropEvent

from image_worker.landscape_portrait_worker import LandscapePortraitWorker, RESOLUTION_MAP


# ── 辅助：颜色预览按钮 ───────────────────────────────────────────────────────

class ColorButton(QPushButton):
    """带颜色预览色块的按钮，点击弹出颜色选择器。"""
    def __init__(self, color: str = "#000000", parent=None):
        super().__init__(parent)
        self._color = color
        self._refresh_style()
        self.clicked.connect(self._pick_color)

    def _refresh_style(self):
        self.setText(f"  {self._color}")
        self.setStyleSheet(
            f"QPushButton {{ background-color: {self._color}; color: {'#ffffff' if self._is_dark() else '#000000'};"
            f" border: 2px solid #555; border-radius: 6px; padding: 4px 10px; font-family: monospace; }}"
        )

    def _is_dark(self):
        c = QColor(self._color)
        return (c.red() * 299 + c.green() * 587 + c.blue() * 114) / 1000 < 128

    def _pick_color(self):
        c = QColorDialog.getColor(QColor(self._color), self, "选择颜色")
        if c.isValid():
            self._color = c.name()
            self._refresh_style()

    def color(self) -> str:
        return self._color

    def set_color(self, hex_str: str):
        self._color = hex_str
        self._refresh_style()


# ── 可拖拽视频列表 ────────────────────────────────────────────────────────────

class DropListWidget(QListWidget):
    """支持拖拽文件/文件夹导入的列表控件。"""

    VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm", ".ts", ".m4v"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        paths = []
        for url in event.mimeData().urls():
            p = url.toLocalFile()
            if os.path.isdir(p):
                for f in sorted(os.listdir(p)):
                    if os.path.splitext(f)[1].lower() in self.VIDEO_EXTS:
                        paths.append(os.path.join(p, f))
            elif os.path.isfile(p) and os.path.splitext(p)[1].lower() in self.VIDEO_EXTS:
                paths.append(p)
        self._add_paths(paths)
        event.acceptProposedAction()

    def _add_paths(self, paths: list):
        existing = {self.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.count())}
        for p in paths:
            if p not in existing:
                item = QListWidgetItem(os.path.basename(p))
                item.setData(Qt.ItemDataRole.UserRole, p)
                item.setToolTip(p)
                self.addItem(item)
                existing.add(p)


# ══════════════════════════════════════════════════════════════════════════════
#  LandscapeToPortraitUI
# ══════════════════════════════════════════════════════════════════════════════

class LandscapeToPortraitUI(QWidget):

    def __init__(self):
        super().__init__()
        self.settings = QSettings("MyCompany", "VideoToolbox")
        self._worker: LandscapePortraitWorker | None = None
        self._ffmpeg_dir = self._detect_ffmpeg()
        self.setup_ui()
        self.bind_events()
        self.load_settings()

    # ── FFmpeg 路径探测 ──────────────────────────────────────────────────────

    def _detect_ffmpeg(self) -> str:
        """优先使用项目 ffmpeg/ 目录，否则回退系统 PATH。"""
        if getattr(sys, "frozen", False):
            base = os.path.dirname(sys.executable)
        else:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        local = os.path.join(base, "ffmpeg")
        if os.path.isfile(os.path.join(local, "ffmpeg.exe")):
            return local
        return ""

    # ── 构建 UI ──────────────────────────────────────────────────────────────

    def setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)
        scroll.setWidget(inner)
        root.addWidget(scroll)

        # ── 标题 ─────────────────────────────────────────────────────────
        title = QLabel("🔃 横屏转竖屏")
        title.setObjectName("CardTitle")
        title.setFont(QFont("Microsoft YaHei", 13, QFont.Weight.Bold))
        layout.addWidget(title)

        # ── 文件列表区 ───────────────────────────────────────────────────
        list_card = self._make_card()
        list_layout = QVBoxLayout(list_card)

        lbl_drop = QLabel("📂 视频文件列表（拖拽视频/文件夹到此处）")
        lbl_drop.setObjectName("CardTitle")
        list_layout.addWidget(lbl_drop)

        self.list_widget = DropListWidget()
        self.list_widget.setMinimumHeight(180)
        list_layout.addWidget(self.list_widget)

        btn_row = QHBoxLayout()
        self.btn_add_files  = QPushButton("➕ 添加视频")
        self.btn_add_folder = QPushButton("📁 导入文件夹")
        self.btn_clear      = QPushButton("🗑️ 清空列表")
        self.btn_remove_sel = QPushButton("❌ 删除选中")
        for b in (self.btn_add_files, self.btn_add_folder, self.btn_remove_sel, self.btn_clear):
            btn_row.addWidget(b)
        btn_row.addStretch()
        list_layout.addLayout(btn_row)
        layout.addWidget(list_card)

        # ── 参数面板 ─────────────────────────────────────────────────────
        param_card = self._make_card()
        param_layout = QVBoxLayout(param_card)
        param_layout.setSpacing(10)

        param_title = QLabel("⚙️ 转换参数")
        param_title.setObjectName("CardTitle")
        param_layout.addWidget(param_title)

        # 分辨率
        row_res = QHBoxLayout()
        row_res.addWidget(QLabel("输出分辨率："))
        self.combo_resolution = QComboBox()
        for key in RESOLUTION_MAP:
            self.combo_resolution.addItem(key)
        self.combo_resolution.setCurrentText("1K (默认)")
        self.combo_resolution.setMinimumWidth(160)
        row_res.addWidget(self.combo_resolution)
        row_res.addStretch()
        param_layout.addLayout(row_res)

        # Y 轴偏移
        row_y = QHBoxLayout()
        row_y.addWidget(QLabel("视频 Y 轴偏移（像素）："))
        self.spin_y = QSpinBox()
        self.spin_y.setRange(-656, 656)
        self.spin_y.setValue(0)
        self.spin_y.setSuffix(" px")
        self.spin_y.setToolTip("正值向上，负值向下，0 为居中。范围 ±656px（基于 1K 分辨率）")
        self.spin_y.setMinimumWidth(120)
        row_y.addWidget(self.spin_y)
        row_y.addWidget(QLabel("（正数↑上移，负数↓下移，0=居中）"))
        row_y.addStretch()
        param_layout.addLayout(row_y)

        # 背景颜色
        sep_bg = QFrame()
        sep_bg.setFrameShape(QFrame.Shape.HLine)
        sep_bg.setFrameShadow(QFrame.Shadow.Sunken)
        param_layout.addWidget(sep_bg)

        row_bg1 = QHBoxLayout()
        row_bg1.addWidget(QLabel("背景颜色："))
        self.btn_color1 = ColorButton("#000000")
        self.btn_color1.setFixedWidth(160)
        row_bg1.addWidget(self.btn_color1)
        row_bg1.addStretch()
        param_layout.addLayout(row_bg1)

        row_grad = QHBoxLayout()
        self.chk_gradient = QCheckBox("使用渐变背景（由上色到下色）")
        row_grad.addWidget(self.chk_gradient)
        row_grad.addStretch()
        param_layout.addLayout(row_grad)

        row_bg2 = QHBoxLayout()
        self.lbl_color2 = QLabel("渐变终止颜色：")
        self.btn_color2 = ColorButton("#333333")
        self.btn_color2.setFixedWidth(160)
        row_bg2.addWidget(self.lbl_color2)
        row_bg2.addWidget(self.btn_color2)
        row_bg2.addStretch()
        param_layout.addLayout(row_bg2)
        # 默认隐藏渐变第二颜色
        self.lbl_color2.setVisible(False)
        self.btn_color2.setVisible(False)

        layout.addWidget(param_card)

        # ── 命名方式 ─────────────────────────────────────────────────────
        name_card = self._make_card()
        name_layout = QVBoxLayout(name_card)
        name_layout.setSpacing(8)
        name_title = QLabel("✏️ 导出命名方式")
        name_title.setObjectName("CardTitle")
        name_layout.addWidget(name_title)

        self.radio_default  = QRadioButton("原文件名 + \"-横转竖\"（默认）")
        self.radio_original = QRadioButton("以原本名称导出")
        self.radio_custom   = QRadioButton("自定义名称（一行一个，按视频顺序）")
        self.radio_default.setChecked(True)
        self._name_group = QButtonGroup(self)
        for r in (self.radio_default, self.radio_original, self.radio_custom):
            self._name_group.addButton(r)
            name_layout.addWidget(r)

        self.txt_custom_names = QPlainTextEdit()
        self.txt_custom_names.setPlaceholderText("请在此输入自定义名称，每行对应一个视频（不含扩展名）")
        self.txt_custom_names.setFixedHeight(90)
        self.txt_custom_names.setVisible(False)
        name_layout.addWidget(self.txt_custom_names)
        layout.addWidget(name_card)

        # ── 导出目录 ─────────────────────────────────────────────────────
        out_card = self._make_card()
        out_layout = QVBoxLayout(out_card)
        out_lbl = QLabel("📤 导出目录")
        out_lbl.setObjectName("CardTitle")
        out_layout.addWidget(out_lbl)

        row_out = QHBoxLayout()
        self.lbl_output_dir = QLabel("未选择导出目录")
        self.lbl_output_dir.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.lbl_output_dir.setWordWrap(True)
        self.btn_choose_output = QPushButton("📂 选择目录")
        self.btn_choose_output.setFixedWidth(120)
        row_out.addWidget(self.lbl_output_dir, 1)
        row_out.addWidget(self.btn_choose_output)
        out_layout.addLayout(row_out)
        layout.addWidget(out_card)

        # ── 进度区域 ─────────────────────────────────────────────────────
        prog_card = self._make_card()
        prog_layout = QVBoxLayout(prog_card)
        self.lbl_status = QLabel("就绪")
        prog_layout.addWidget(self.lbl_status)
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        prog_layout.addWidget(self.progress_bar)

        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFixedHeight(120)
        self.log_box.setFont(QFont("Consolas", 9))
        prog_layout.addWidget(self.log_box)
        layout.addWidget(prog_card)

        # ── 操作按钮 ─────────────────────────────────────────────────────
        btn_main_row = QHBoxLayout()
        self.btn_start = QPushButton("🚀 开始转换")
        self.btn_start.setObjectName("PrimaryBtn")
        self.btn_start.setFixedHeight(50)
        self.btn_stop  = QPushButton("⏹️ 停止")
        self.btn_stop.setEnabled(False)
        self.btn_stop.setFixedHeight(50)
        self.btn_stop.setFixedWidth(120)
        btn_main_row.addWidget(self.btn_start, 1)
        btn_main_row.addWidget(self.btn_stop)
        layout.addLayout(btn_main_row)
        layout.addStretch()

    # ── 辅助：创建卡片容器 ────────────────────────────────────────────────────

    def _make_card(self) -> QFrame:
        f = QFrame()
        f.setProperty("class", "Card")
        return f

    # ── 事件绑定 ─────────────────────────────────────────────────────────────

    def bind_events(self):
        self.btn_add_files.clicked.connect(self._add_files)
        self.btn_add_folder.clicked.connect(self._add_folder)
        self.btn_clear.clicked.connect(self.list_widget.clear)
        self.btn_remove_sel.clicked.connect(self._remove_selected)
        self.btn_choose_output.clicked.connect(self._choose_output)
        self.btn_start.clicked.connect(self._start)
        self.btn_stop.clicked.connect(self._stop)
        self.chk_gradient.toggled.connect(self._on_gradient_toggled)
        self.radio_custom.toggled.connect(self._on_custom_name_toggled)

    # ── UI 事件处理 ──────────────────────────────────────────────────────────

    def _on_gradient_toggled(self, checked: bool):
        self.lbl_color2.setVisible(checked)
        self.btn_color2.setVisible(checked)

    def _on_custom_name_toggled(self, checked: bool):
        self.txt_custom_names.setVisible(checked)

    def _add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择视频文件", "",
            "视频文件 (*.mp4 *.mov *.avi *.mkv *.wmv *.flv *.webm *.ts *.m4v)"
        )
        if files:
            self.list_widget._add_paths(files)

    def _add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if folder:
            exts = DropListWidget.VIDEO_EXTS
            paths = [
                os.path.join(folder, f)
                for f in sorted(os.listdir(folder))
                if os.path.splitext(f)[1].lower() in exts
            ]
            if paths:
                self.list_widget._add_paths(paths)
            else:
                QMessageBox.information(self, "提示", "所选文件夹中没有找到视频文件。")

    def _remove_selected(self):
        for item in self.list_widget.selectedItems():
            self.list_widget.takeItem(self.list_widget.row(item))

    def _choose_output(self):
        folder = QFileDialog.getExistingDirectory(
            self, "选择导出目录",
            self.settings.value("l2p_output_dir", "")
        )
        if folder:
            self._output_dir = folder
            self.lbl_output_dir.setText(folder)
            self.settings.setValue("l2p_output_dir", folder)

    # ── 收集输出名称列表 ─────────────────────────────────────────────────────

    def _collect_output_names(self, input_files: list) -> list:
        if self.radio_original.isChecked():
            return [os.path.splitext(os.path.basename(p))[0] for p in input_files]
        elif self.radio_custom.isChecked():
            lines = [l.strip() for l in self.txt_custom_names.toPlainText().splitlines() if l.strip()]
            names = []
            for i, p in enumerate(input_files):
                if i < len(lines):
                    names.append(lines[i])
                else:
                    names.append(os.path.splitext(os.path.basename(p))[0] + "-横转竖")
            return names
        else:  # 默认
            return [os.path.splitext(os.path.basename(p))[0] + "-横转竖" for p in input_files]

    # ── 开始 / 停止 ───────────────────────────────────────────────────────────

    def _start(self):
        # 验证文件列表
        input_files = [
            self.list_widget.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.list_widget.count())
        ]
        if not input_files:
            QMessageBox.warning(self, "提示", "请先添加要转换的视频文件。")
            return

        output_dir = getattr(self, "_output_dir", "")
        if not output_dir:
            QMessageBox.warning(self, "提示", "请先选择导出目录。")
            return

        output_names = self._collect_output_names(input_files)

        self.log_box.clear()
        self.progress_bar.setValue(0)
        self.lbl_status.setText("处理中...")
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)

        self._worker = LandscapePortraitWorker(
            input_files  = input_files,
            output_dir   = output_dir,
            output_names = output_names,
            resolution   = self.combo_resolution.currentText(),
            y_offset     = self.spin_y.value(),
            bg_color1    = self.btn_color1.color(),
            use_gradient = self.chk_gradient.isChecked(),
            bg_color2    = self.btn_color2.color(),
            ffmpeg_dir   = self._ffmpeg_dir,
        )
        self._worker.log_signal.connect(self._on_log)
        self._worker.progress_signal.connect(self._on_progress)
        self._worker.file_done_signal.connect(self._on_file_done)
        self._worker.finished_signal.connect(self._on_finished)
        self._worker.start()

    def _stop(self):
        if self._worker:
            self._worker.stop()
        self.btn_stop.setEnabled(False)

    # ── Worker 信号处理 ──────────────────────────────────────────────────────

    def _on_log(self, msg: str):
        self.log_box.appendPlainText(msg)
        self.log_box.verticalScrollBar().setValue(self.log_box.verticalScrollBar().maximum())

    def _on_progress(self, idx: int, pct: int, text: str):
        total = self.list_widget.count()
        # 整体进度 = 已完成文件 * 100 + 当前文件进度，再除以总数
        overall = int((idx * 100 + pct) / max(total, 1))
        self.progress_bar.setValue(overall)
        self.lbl_status.setText(f"[{idx+1}/{total}] {text}")

    def _on_file_done(self, idx: int, ok: bool, msg: str):
        item = self.list_widget.item(idx)
        if item:
            orig = item.text().split("  ")[0]  # 去掉旧状态
            item.setText(f"{orig}  {msg}")

    def _on_finished(self, ok: bool, summary: str):
        self.progress_bar.setValue(100 if ok else self.progress_bar.value())
        self.lbl_status.setText(summary)
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        if ok:
            QMessageBox.information(self, "完成", summary)
        else:
            QMessageBox.warning(self, "完成（含失败）", summary)

    # ── Settings ─────────────────────────────────────────────────────────────

    def load_settings(self):
        self.combo_resolution.setCurrentText(
            self.settings.value("l2p_resolution", "1K (默认)"))
        self.spin_y.setValue(
            self.settings.value("l2p_y_offset", 0, type=int))
        self.btn_color1.set_color(
            self.settings.value("l2p_color1", "#000000"))
        self.btn_color2.set_color(
            self.settings.value("l2p_color2", "#333333"))
        self.chk_gradient.setChecked(
            self.settings.value("l2p_gradient", False, type=bool))

        saved_dir = self.settings.value("l2p_output_dir", "")
        if saved_dir and os.path.isdir(saved_dir):
            self._output_dir = saved_dir
            self.lbl_output_dir.setText(saved_dir)
        else:
            self._output_dir = ""

        name_mode = self.settings.value("l2p_name_mode", "default")
        if name_mode == "original":
            self.radio_original.setChecked(True)
        elif name_mode == "custom":
            self.radio_custom.setChecked(True)
        else:
            self.radio_default.setChecked(True)

    def save_settings(self):
        self.settings.setValue("l2p_resolution",   self.combo_resolution.currentText())
        self.settings.setValue("l2p_y_offset",     self.spin_y.value())
        self.settings.setValue("l2p_color1",       self.btn_color1.color())
        self.settings.setValue("l2p_color2",       self.btn_color2.color())
        self.settings.setValue("l2p_gradient",     self.chk_gradient.isChecked())

        if self.radio_original.isChecked():
            mode = "original"
        elif self.radio_custom.isChecked():
            mode = "custom"
        else:
            mode = "default"
        self.settings.setValue("l2p_name_mode", mode)
