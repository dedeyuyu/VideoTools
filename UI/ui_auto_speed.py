"""
ui_auto_speed.py
自动调速 — 给视频加速；可选“保持在3分钟以内”。
"""
import os
import sys

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
    QProgressBar, QDoubleSpinBox, QPlainTextEdit, QCheckBox, QFrame,
    QScrollArea, QSizePolicy, QMessageBox,
)
from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtGui import QFont

from UI.ui_landscape_to_portrait import DropListWidget
from image_worker.auto_speed_worker import AutoSpeedWorker


class AutoSpeedUI(QWidget):

    def __init__(self):
        super().__init__()
        self.settings = QSettings("MyCompany", "VideoToolbox")
        self._worker = None
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

        title = QLabel("⏩ 自动调速")
        title.setObjectName("CardTitle")
        title.setFont(QFont("Microsoft YaHei", 13, QFont.Weight.Bold))
        layout.addWidget(title)

        # 文件列表
        lc = self._card()
        ll = QVBoxLayout(lc)
        t = QLabel("📂 视频文件列表（拖拽视频/文件夹到此处）")
        t.setObjectName("CardTitle")
        ll.addWidget(t)
        self.list_widget = DropListWidget()
        self.list_widget.setMinimumHeight(180)
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

        # 参数
        pc = self._card()
        pl = QVBoxLayout(pc)
        pt = QLabel("⚙️ 调速参数")
        pt.setObjectName("CardTitle")
        pl.addWidget(pt)
        r = QHBoxLayout()
        r.addWidget(QLabel("播放倍速："))
        self.spin_speed = QDoubleSpinBox()
        self.spin_speed.setRange(0.1, 16.0)
        self.spin_speed.setSingleStep(0.1)
        self.spin_speed.setDecimals(2)
        self.spin_speed.setValue(1.5)
        self.spin_speed.setSuffix(" 倍")
        self.spin_speed.setMinimumWidth(120)
        r.addWidget(self.spin_speed)
        r.addStretch()
        pl.addLayout(r)
        self.chk_3min = QCheckBox("保持在 3 分钟以内（超过 3 分钟的视频自动加速到 2:59 以内；不超过的按上面的倍速输出）")
        self.chk_3min.setChecked(True)
        pl.addWidget(self.chk_3min)
        layout.addWidget(pc)

        # 导出目录
        oc = self._card()
        ol = QVBoxLayout(oc)
        ot = QLabel("📤 导出目录")
        ot.setObjectName("CardTitle")
        ol.addWidget(ot)
        orow = QHBoxLayout()
        self.lbl_out = QLabel("未选择导出目录")
        self.lbl_out.setWordWrap(True)
        self.lbl_out.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.btn_out = QPushButton("📂 选择目录")
        self.btn_out.setFixedWidth(120)
        orow.addWidget(self.lbl_out, 1)
        orow.addWidget(self.btn_out)
        ol.addLayout(orow)
        layout.addWidget(oc)

        # 进度
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

        br = QHBoxLayout()
        self.btn_start = QPushButton("🚀 开始调速")
        self.btn_start.setObjectName("PrimaryBtn")
        self.btn_start.setFixedHeight(50)
        self.btn_stop = QPushButton("⏹️ 停止")
        self.btn_stop.setEnabled(False)
        self.btn_stop.setFixedHeight(50)
        self.btn_stop.setFixedWidth(120)
        br.addWidget(self.btn_start, 1)
        br.addWidget(self.btn_stop)
        layout.addLayout(br)
        layout.addStretch()

        self.btn_add.clicked.connect(self._add_files)
        self.btn_folder.clicked.connect(self._add_folder)
        self.btn_rm.clicked.connect(self._remove_selected)
        self.btn_clear.clicked.connect(self.list_widget.clear)
        self.btn_out.clicked.connect(self._choose_output)
        self.btn_start.clicked.connect(self._start)
        self.btn_stop.clicked.connect(self._stop)

    def _add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择视频文件", "",
            "视频文件 (*.mp4 *.mov *.avi *.mkv *.wmv *.flv *.webm *.ts *.m4v)")
        if files:
            self.list_widget._add_paths(files)

    def _add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if folder:
            paths = [os.path.join(folder, f) for f in sorted(os.listdir(folder))
                     if os.path.splitext(f)[1].lower() in DropListWidget.VIDEO_EXTS]
            if paths:
                self.list_widget._add_paths(paths)
            else:
                QMessageBox.information(self, "提示", "所选文件夹中没有找到视频文件。")

    def _remove_selected(self):
        for it in self.list_widget.selectedItems():
            self.list_widget.takeItem(self.list_widget.row(it))

    def _choose_output(self):
        folder = QFileDialog.getExistingDirectory(
            self, "选择导出目录", self.settings.value("speed_output_dir", ""))
        if folder:
            self._output_dir = folder
            self.lbl_out.setText(folder)
            self.settings.setValue("speed_output_dir", folder)

    def _start(self):
        files = [self.list_widget.item(i).data(Qt.ItemDataRole.UserRole)
                 for i in range(self.list_widget.count())]
        if not files:
            QMessageBox.warning(self, "提示", "请先添加要调速的视频文件。")
            return
        if not self._output_dir:
            QMessageBox.warning(self, "提示", "请先选择导出目录。")
            return
        names = [os.path.splitext(os.path.basename(p))[0] + "-调速" for p in files]
        self.log_box.clear()
        self.progress.setValue(0)
        self.lbl_status.setText("处理中...")
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self._worker = AutoSpeedWorker(files, self._output_dir, names,
                                       self.spin_speed.value(),
                                       self.chk_3min.isChecked(), self._ffmpeg_dir)
        self._worker.log_signal.connect(self._on_log)
        self._worker.progress_signal.connect(self._on_progress)
        self._worker.file_done_signal.connect(self._on_file_done)
        self._worker.finished_signal.connect(self._on_finished)
        self._worker.start()

    def _stop(self):
        if self._worker:
            self._worker.stop()
        self.btn_stop.setEnabled(False)

    def _on_log(self, msg):
        self.log_box.appendPlainText(msg)

    def _on_progress(self, idx, pct, text):
        total = max(1, self.list_widget.count())
        self.progress.setValue(int((idx * 100 + pct) / total))
        self.lbl_status.setText(f"[{idx+1}/{total}] {text}")

    def _on_file_done(self, idx, ok, msg):
        item = self.list_widget.item(idx)
        if item:
            item.setText(f"{item.text().split('  ')[0]}  {msg}")

    def _on_finished(self, ok, summary):
        if ok:
            self.progress.setValue(100)
        self.lbl_status.setText(summary)
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "完成", summary)

    def load_settings(self):
        self.spin_speed.setValue(self.settings.value("speed_value", 1.5, type=float))
        self.chk_3min.setChecked(self.settings.value("speed_keep3", True, type=bool))
        d = self.settings.value("speed_output_dir", "")
        if d and os.path.isdir(d):
            self._output_dir = d
            self.lbl_out.setText(d)

    def save_settings(self):
        self.settings.setValue("speed_value", self.spin_speed.value())
        self.settings.setValue("speed_keep3", self.chk_3min.isChecked())
