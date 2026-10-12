# -*- coding: utf-8 -*-
"""软件设置对话框：界面语言、主题，以及常用文件夹入口。以后新增的常规设置也放在这里。"""
import os
import sys

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
                             QComboBox, QLabel, QPushButton, QMessageBox)
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices

from UI import i18n


def _install_root():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class SettingsDialog(QDialog):
    """返回值：exec() 之后读取 self.restart_requested 判断是否需要重启。"""

    def __init__(self, parent=None, is_dark_mode=True, version=""):
        super().__init__(parent)
        self.setWindowTitle("软件设置")
        self.setMinimumWidth(460)
        self.restart_requested = False
        self.theme_changed = False
        self._orig_lang = i18n.get_language()
        self._orig_dark = bool(is_dark_mode)

        root = QVBoxLayout(self)
        root.setSpacing(12)

        # ── 常规 ──
        g = QGroupBox("常规")
        form = QFormLayout(g)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.cmb_lang = QComboBox()
        for code, name in i18n.LANGUAGES:
            self.cmb_lang.addItem(name, code)       # 语言名称本身不翻译
        idx = self.cmb_lang.findData(self._orig_lang)
        self.cmb_lang.setCurrentIndex(max(0, idx))
        form.addRow("界面语言:", self.cmb_lang)

        self.cmb_theme = QComboBox()
        self.cmb_theme.addItem("暗色", True)
        self.cmb_theme.addItem("亮色", False)
        self.cmb_theme.setCurrentIndex(0 if self._orig_dark else 1)
        form.addRow("界面主题:", self.cmb_theme)

        hint = QLabel("切换语言后需要重启软件才能生效。")
        hint.setStyleSheet("color: #A0AEC0;")
        form.addRow("", hint)
        root.addWidget(g)

        # ── 数据与日志 ──
        g2 = QGroupBox("数据与日志")
        h = QHBoxLayout(g2)
        b_data = QPushButton("📁 打开数据文件夹")
        b_data.clicked.connect(lambda: self._open_dir(os.path.join(_install_root(), "duet_data")))
        b_logs = QPushButton("🧾 打开崩溃日志文件夹")
        b_logs.clicked.connect(lambda: self._open_dir(os.path.join(_install_root(), "crash_logs")))
        h.addWidget(b_data)
        h.addWidget(b_logs)
        root.addWidget(g2)

        if version:
            v = QLabel(f"版本: {version}")
            v.setStyleSheet("color: #A0AEC0;")
            root.addWidget(v)

        # ── 按钮 ──
        btns = QHBoxLayout()
        btns.addStretch()
        b_cancel = QPushButton("取消")
        b_cancel.clicked.connect(self.reject)
        b_ok = QPushButton("保存")
        b_ok.setProperty("class", "ActionBtn")
        b_ok.setDefault(True)
        b_ok.clicked.connect(self._save)
        btns.addWidget(b_cancel)
        btns.addWidget(b_ok)
        root.addLayout(btns)

    # 读取用户选择
    def selected_dark_mode(self):
        return bool(self.cmb_theme.currentData())

    def _open_dir(self, path):
        os.makedirs(path, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _save(self):
        lang = self.cmb_lang.currentData()
        self.theme_changed = self.selected_dark_mode() != self._orig_dark
        if lang != self._orig_lang:
            i18n.set_language(lang)
            # 提示用目标语言显示，方便看不懂当前语言的用户
            if lang == "en":
                title, text = "Language changed", "Language changed. Restart now?\n(Your current work will be saved automatically.)"
            else:
                title, text = "语言已切换", "语言已切换，是否立即重启软件？\n（未保存的内容会自动保存）"
            i18n.LANG = "zh"          # 提示已是目标语言，显示时不要再翻译
            r = QMessageBox.question(self, title, text,
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            i18n.LANG = self._orig_lang
            self.restart_requested = (r == QMessageBox.StandardButton.Yes)
        self.accept()
