# -*- coding: utf-8 -*-
"""
ui_video_transcoder.py
视频批量转码 — 解决视频在其他软件中无法导入/无法导出、编码不兼容、可变帧率音画不同步等问题。
支持批量拖入视频或文件夹，选择输出文件夹后按原视频文件名命名输出。
"""
import os
import sys

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QFileDialog, QProgressBar, QComboBox,
    QPlainTextEdit, QCheckBox, QFrame, QScrollArea, QSizePolicy,
    QMessageBox, QAbstractItemView,
)
from PyQt6.QtCore import Qt, QSettings, pyqtSignal
from PyQt6.QtGui import QFont, QDragEnterEvent, QDropEvent

from image_worker.transcode_worker import TranscodeWorker, VIDEO_EXTS


class TranscodeDropListWidget(QListWidget):
    """支持拖拽多个视频文件或文件夹导入的列表控件。"""
    count_changed = pyqtSignal(int)

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
                for root_dir, _, files in os.walk(p):
                    for f in sorted(files):
                        if os.path.splitext(f)[1].lower() in VIDEO_EXTS:
                            paths.append(os.path.join(root_dir, f))
            elif os.path.isfile(p) and os.path.splitext(p)[1].lower() in VIDEO_EXTS:
                paths.append(p)
        self.add_video_paths(paths)
        event.acceptProposedAction()

    def add_video_paths(self, paths: list[str]):
        existing = {self.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.count())}
        added = False
        for p in paths:
            norm_p = os.path.normpath(p)
            if norm_p not in existing and os.path.isfile(norm_p):
                item = QListWidgetItem(os.path.basename(norm_p))
                item.setData(Qt.ItemDataRole.UserRole, norm_p)
                item.setToolTip(norm_p)
                self.addItem(item)
                existing.add(norm_p)
                added = True
        if added:
            self.count_changed.emit(self.count())


class VideoTranscoderUI(QWidget):

    def __init__(self):
        super().__init__()
        self.settings = QSettings("MyCompany", "VideoToolbox")
        self._worker: TranscodeWorker | None = None
        self._output_dir = ""
        self._ffmpeg_dir = self._detect_ffmpeg()
        self.setup_ui()
        self.load_settings()

    def _detect_ffmpeg(self) -> str:
        if getattr(sys, "frozen", False):
            base = os.path.dirname(sys.executable)
        else:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        local = os.path.join(base, "ffmpeg")
        return local if os.path.isfile(os.path.join(local, "ffmpeg.exe")) else ""

    @staticmethod
    def _card() -> QFrame:
        f = QFrame()
        f.setProperty("class", "Card")
        return f

    def setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)
        scroll.setWidget(inner)
        root.addWidget(scroll)

        # 标题与说明
        header_row = QHBoxLayout()
        title = QLabel("🔄 视频批量转码")
        title.setObjectName("CardTitle")
        title.setFont(QFont("Microsoft YaHei", 13, QFont.Weight.Bold))
        header_row.addWidget(title)
        sub_tip = QLabel("将视频转换为标准兼容格式（H.264 + AAC + 恒定帧率），解决在其他软件中无法导入或无法导出的问题，输出按原文件名命名")
        sub_tip.setStyleSheet("color: #A0AEC0; font-size: 9.5pt;")
        sub_tip.setWordWrap(True)
        header_row.addWidget(sub_tip, 1)
        layout.addLayout(header_row)

        # 1. 视频文件列表
        lc = self._card()
        ll = QVBoxLayout(lc)
        self.lbl_list_title = QLabel("📂 待转码视频列表（直接拖拽视频或文件夹到下方列表）  [0 个]")
        self.lbl_list_title.setProperty("class", "CardTitle")
        ll.addWidget(self.lbl_list_title)

        self.list_widget = TranscodeDropListWidget()
        self.list_widget.setMinimumHeight(200)
        ll.addWidget(self.list_widget)

        row = QHBoxLayout()
        self.btn_add = QPushButton("➕ 添加视频")
        self.btn_folder = QPushButton("📁 导入文件夹")
        self.btn_rm = QPushButton("❌ 删除选中")
        self.btn_clear = QPushButton("🗑️ 清空列表")
        for b in (self.btn_add, self.btn_folder, self.btn_rm, self.btn_clear):
            row.addWidget(b)
        row.addStretch()
        ll.addLayout(row)
        layout.addWidget(lc)

        # 2. 转码参数设置
        pc = self._card()
        pl = QVBoxLayout(pc)
        pt = QLabel("⚙️ 转码参数设置（默认已设为最佳兼容模式，可直接点击开始转码）")
        pt.setProperty("class", "CardTitle")
        pl.addWidget(pt)

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(10)

        # 转码模式
        grid.addWidget(QLabel("转码模式:"), 0, 0)
        self.combo_mode = QComboBox()
        self.combo_mode.addItem("🛠️ 标准兼容修复（推荐 · H.264 + AAC + 恒定帧率，解决无法导入/导出）", "compat")
        self.combo_mode.addItem("💎 高清无损画质（H.264 高码率 CRF 15，适合二次剪辑）", "hq")
        self.combo_mode.addItem("📦 轻量压缩（H.264 CRF 24，减小文件体积同时保持兼容）", "compress")
        self.combo_mode.addItem("⚡ 极速重封装（已兼容视频直接秒级修复容器，不兼容视频自动转码）", "remux")
        grid.addWidget(self.combo_mode, 0, 1, 1, 3)

        # 输出格式
        grid.addWidget(QLabel("输出格式:"), 1, 0)
        self.combo_ext = QComboBox()
        self.combo_ext.addItem("MP4 (.mp4 · 全平台通用推荐)", ".mp4")
        self.combo_ext.addItem("MOV (.mov)", ".mov")
        self.combo_ext.addItem("MKV (.mkv)", ".mkv")
        grid.addWidget(self.combo_ext, 1, 1)

        # 编码方式
        grid.addWidget(QLabel("编码方式:"), 1, 2)
        self.combo_encoder = QComboBox()
        self.combo_encoder.addItem("🖥️ CPU 标准编码 (libx264 · 兼容性最佳)", False)
        self.combo_encoder.addItem("🚀 GPU 硬件加速（自动检测显卡，失败回退 CPU）", True)
        grid.addWidget(self.combo_encoder, 1, 3)

        # 分辨率
        grid.addWidget(QLabel("输出分辨率:"), 2, 0)
        self.combo_res = QComboBox()
        self.combo_res.addItem("保持原分辨率（自动修正奇数宽高）", 0)
        self.combo_res.addItem("1080P (长边最多 1920)", 1920)
        self.combo_res.addItem("720P (长边最多 1280)", 1280)
        self.combo_res.addItem("2K (长边最多 2560)", 2560)
        self.combo_res.addItem("4K (长边最多 3840)", 3840)
        grid.addWidget(self.combo_res, 2, 1)

        # 帧率
        grid.addWidget(QLabel("输出帧率:"), 2, 2)
        self.combo_fps = QComboBox()
        self.combo_fps.addItem("保持原帧率（转为恒定帧率 CFR）", 0)
        self.combo_fps.addItem("30 fps（常用标准帧率）", 30)
        self.combo_fps.addItem("60 fps（高帧率流畅）", 60)
        self.combo_fps.addItem("25 fps", 25)
        self.combo_fps.addItem("24 fps", 24)
        grid.addWidget(self.combo_fps, 2, 3)

        # 音频处理
        grid.addWidget(QLabel("音频处理:"), 3, 0)
        self.combo_audio = QComboBox()
        self.combo_audio.addItem("转为标准 AAC 音频 (44.1kHz 双声道 · 推荐)", "aac")
        self.combo_audio.addItem("保留原音频流（若已是 AAC）", "copy")
        self.combo_audio.addItem("去除声音（输出静音视频）", "mute")
        grid.addWidget(self.combo_audio, 3, 1)

        self.chk_ensure_audio = QCheckBox("原视频无音轨时自动补充静音轨（防止部分软件因缺音轨无法导出）")
        self.chk_ensure_audio.setChecked(True)
        grid.addWidget(self.chk_ensure_audio, 3, 2, 1, 2)

        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        pl.addLayout(grid)
        layout.addWidget(pc)

        # 3. 导出目录
        oc = self._card()
        ol = QVBoxLayout(oc)
        ot = QLabel("📤 导出目录（导出文件名将自动保持原视频文件名）")
        ot.setProperty("class", "CardTitle")
        ol.addWidget(ot)
        orow = QHBoxLayout()
        self.lbl_out = QLabel("未选择导出目录")
        self.lbl_out.setWordWrap(True)
        self.lbl_out.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.btn_out = QPushButton("📂 选择目录")
        self.btn_out.setFixedWidth(120)
        self.btn_open_out = QPushButton("📁 打开目录")
        self.btn_open_out.setFixedWidth(120)
        orow.addWidget(self.lbl_out, 1)
        orow.addWidget(self.btn_out)
        orow.addWidget(self.btn_open_out)
        ol.addLayout(orow)
        layout.addWidget(oc)

        # 4. 进度与日志
        gc = self._card()
        gl = QVBoxLayout(gc)
        self.lbl_status = QLabel("就绪")
        gl.addWidget(self.lbl_status)
        self.progress = QProgressBar()
        gl.addWidget(self.progress)
        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFixedHeight(120)
        self.log_box.setFont(QFont("Consolas", 9))
        gl.addWidget(self.log_box)
        layout.addWidget(gc)

        # 5. 开始 / 停止按钮
        br = QHBoxLayout()
        self.btn_start = QPushButton("🚀 开始批量转码")
        self.btn_start.setProperty("class", "ActionBtn")
        self.btn_start.setFixedHeight(50)
        self.btn_stop = QPushButton("⏹️ 停止")
        self.btn_stop.setEnabled(False)
        self.btn_stop.setFixedHeight(50)
        self.btn_stop.setFixedWidth(120)
        br.addWidget(self.btn_start, 1)
        br.addWidget(self.btn_stop)
        layout.addLayout(br)
        layout.addStretch()

        # 绑定事件
        self.list_widget.count_changed.connect(self._update_list_title)
        self.btn_add.clicked.connect(self._add_files)
        self.btn_folder.clicked.connect(self._add_folder)
        self.btn_rm.clicked.connect(self._remove_selected)
        self.btn_clear.clicked.connect(self._clear_list)
        self.btn_out.clicked.connect(self._choose_output)
        self.btn_open_out.clicked.connect(self._open_output)
        self.btn_start.clicked.connect(self._start)
        self.btn_stop.clicked.connect(self._stop)

    def _update_list_title(self, count: int = 0):
        c = self.list_widget.count()
        self.lbl_list_title.setText(f"📂 待转码视频列表（直接拖拽视频或文件夹到下方列表）  [{c} 个]")

    def _add_files(self):
        ext_filter = " ".join(f"*{e}" for e in sorted(VIDEO_EXTS))
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择需要转码的视频文件", "",
            f"视频文件 ({ext_filter});;所有文件 (*.*)"
        )
        if files:
            self.list_widget.add_video_paths(files)
            self._update_list_title()

    def _add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择包含视频的文件夹")
        if folder:
            paths = []
            for root_dir, _, files in os.walk(folder):
                for f in sorted(files):
                    if os.path.splitext(f)[1].lower() in VIDEO_EXTS:
                        paths.append(os.path.join(root_dir, f))
            if paths:
                self.list_widget.add_video_paths(paths)
                self._update_list_title()
            else:
                QMessageBox.information(self, "提示", "所选文件夹中没有找到支持的视频文件。")

    def _remove_selected(self):
        for it in self.list_widget.selectedItems():
            self.list_widget.takeItem(self.list_widget.row(it))
        self._update_list_title()

    def _clear_list(self):
        self.list_widget.clear()
        self._update_list_title()

    def _choose_output(self):
        folder = QFileDialog.getExistingDirectory(
            self, "选择转码导出目录", self.settings.value("transcode_output_dir", "")
        )
        if folder:
            self._output_dir = folder
            self.lbl_out.setText(folder)
            self.settings.setValue("transcode_output_dir", folder)

    def _open_output(self):
        if self._output_dir and os.path.isdir(self._output_dir):
            os.startfile(self._output_dir)
        else:
            QMessageBox.information(self, "提示", "请先选择有效的导出目录。")

    def _start(self):
        files = [
            self.list_widget.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.list_widget.count())
        ]
        if not files:
            QMessageBox.warning(self, "提示", "请先拖入或添加需要转码的视频文件。")
            return
        if not self._output_dir:
            QMessageBox.warning(self, "提示", "请先选择导出目录。")
            return

        # 重置列表项文字为原文件名
        for i, p in enumerate(files):
            it = self.list_widget.item(i)
            if it:
                it.setText(os.path.basename(p))

        options = {
            "mode": self.combo_mode.currentData() or "compat",
            "out_ext": self.combo_ext.currentData() or ".mp4",
            "use_gpu": bool(self.combo_encoder.currentData()),
            "target_res": int(self.combo_res.currentData() or 0),
            "target_fps": int(self.combo_fps.currentData() or 0),
            "audio_mode": self.combo_audio.currentData() or "aac",
            "ensure_audio": self.chk_ensure_audio.isChecked(),
        }
        self.save_settings()

        self.log_box.clear()
        self.progress.setValue(0)
        self.lbl_status.setText("正在准备转码...")
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)

        self._worker = TranscodeWorker(files, self._output_dir, options, self._ffmpeg_dir)
        self._worker.log_signal.connect(self._on_log)
        self._worker.progress_signal.connect(self._on_progress)
        self._worker.file_done_signal.connect(self._on_file_done)
        self._worker.finished_signal.connect(self._on_finished)
        self._worker.start()

    def _stop(self):
        if self._worker:
            self._worker.stop()
        self.btn_stop.setEnabled(False)

    def _on_log(self, msg: str):
        self.log_box.appendPlainText(msg)

    def _on_progress(self, idx: int, pct: int, text: str):
        total = max(1, self.list_widget.count())
        self.progress.setValue(int((idx * 100 + pct) / total))
        self.lbl_status.setText(f"[{idx + 1}/{total}] {text}")

    def _on_file_done(self, idx: int, ok: bool, msg: str):
        item = self.list_widget.item(idx)
        if item:
            orig_name = os.path.basename(item.data(Qt.ItemDataRole.UserRole) or item.text().split("  ")[0])
            item.setText(f"{orig_name}  {msg}")

    def _on_finished(self, ok: bool, summary: str):
        if ok:
            self.progress.setValue(100)
        self.lbl_status.setText(summary)
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "完成", summary)

    def load_settings(self):
        self.combo_mode.setCurrentIndex(self.settings.value("transcode_mode_idx", 0, type=int))
        self.combo_ext.setCurrentIndex(self.settings.value("transcode_ext_idx", 0, type=int))
        self.combo_encoder.setCurrentIndex(self.settings.value("transcode_enc_idx", 0, type=int))
        self.combo_res.setCurrentIndex(self.settings.value("transcode_res_idx", 0, type=int))
        self.combo_fps.setCurrentIndex(self.settings.value("transcode_fps_idx", 0, type=int))
        self.combo_audio.setCurrentIndex(self.settings.value("transcode_audio_idx", 0, type=int))
        self.chk_ensure_audio.setChecked(self.settings.value("transcode_ensure_audio", True, type=bool))
        d = self.settings.value("transcode_output_dir", "")
        if d and os.path.isdir(d):
            self._output_dir = d
            self.lbl_out.setText(d)

    def save_settings(self):
        self.settings.setValue("transcode_mode_idx", self.combo_mode.currentIndex())
        self.settings.setValue("transcode_ext_idx", self.combo_ext.currentIndex())
        self.settings.setValue("transcode_enc_idx", self.combo_encoder.currentIndex())
        self.settings.setValue("transcode_res_idx", self.combo_res.currentIndex())
        self.settings.setValue("transcode_fps_idx", self.combo_fps.currentIndex())
        self.settings.setValue("transcode_audio_idx", self.combo_audio.currentIndex())
        self.settings.setValue("transcode_ensure_audio", self.chk_ensure_audio.isChecked())
        if self._output_dir:
            self.settings.setValue("transcode_output_dir", self._output_dir)
