import os
import sys
import random
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QSpinBox, QDoubleSpinBox, QComboBox,
    QCheckBox, QFileDialog, QListWidget, QListWidgetItem,
    QProgressBar, QMessageBox, QFrame, QAbstractSpinBox,
    QDialog, QLineEdit, QInputDialog, QSizePolicy, QSlider, QScrollArea,
    QPlainTextEdit
)
from PyQt6.QtCore import Qt, QEvent, QSettings, pyqtSignal, QSize
from PyQt6.QtGui import QColor, QFont

# ── Optional multimedia (graceful degradation if unavailable) ─────────────────
try:
    from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
    from PyQt6.QtCore import QUrl
    _HAS_MULTIMEDIA = True
except ImportError:
    _HAS_MULTIMEDIA = False

from image_worker.image_merge_worker import ImageMergeWorker
from image_worker.audio_library import AudioLibrary, SUPPORTED_AUDIO_EXT


# ══════════════════════════════════════════════════════════════════════════════
#  ClickableFrame — emits a signal on single/double click
# ══════════════════════════════════════════════════════════════════════════════

class ClickableFrame(QFrame):
    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)


# ══════════════════════════════════════════════════════════════════════════════
#  AudioSelectDialog — beautiful music selection popup
# ══════════════════════════════════════════════════════════════════════════════

class AudioSelectDialog(QDialog):
    """Full-screen music selector with multi-select, order badges, and preview."""

    _BADGES = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩"]

    def __init__(self, library: AudioLibrary, current_selected: list, parent=None):
        super().__init__(parent)
        self.library = library
        self._selected_order: list[str] = list(current_selected)  # ordered path list

        # Media player setup
        self._player = None
        self._audio_out = None
        if _HAS_MULTIMEDIA:
            self._player = QMediaPlayer()
            self._audio_out = QAudioOutput()
            self._player.setAudioOutput(self._audio_out)
            self._audio_out.setVolume(0.8)
            self._player.playbackStateChanged.connect(self._on_playback_state_changed)

        self.setWindowTitle("选择背景音乐")
        self.setMinimumSize(780, 580)
        self.resize(840, 620)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint)

        self._apply_style()
        self._setup_ui()
        self._load_library()

    # ── Stylesheet ─────────────────────────────────────────────────────────

    def _apply_style(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #1a1d27;
                color: #d1d5db;
                font-family: "Microsoft YaHei", "Segoe UI";
            }
            QFrame#TitleBar {
                background-color: #16192a;
                border-bottom: 2px solid #f43f5e;
            }
            QLabel#DialogTitle {
                font-size: 16pt;
                font-weight: bold;
                color: #ffffff;
                letter-spacing: 1px;
            }
            QLabel#CountBadge {
                font-size: 11pt;
                font-weight: bold;
                color: #f43f5e;
                background-color: #2d1520;
                border-radius: 10px;
                padding: 2px 10px;
            }
            QFrame#BodyFrame {
                background-color: #1a1d27;
            }
            QLineEdit#SearchBar {
                background-color: #0f1117;
                border: 1px solid #2b303b;
                border-radius: 8px;
                padding: 9px 14px;
                color: #e5e7eb;
                font-size: 11pt;
            }
            QLineEdit#SearchBar:focus {
                border: 1px solid #f43f5e;
            }
            QListWidget#AudioList {
                background-color: #0f1117;
                border: 1px solid #1f2937;
                border-radius: 10px;
                padding: 6px;
                outline: none;
                font-size: 11pt;
            }
            QListWidget#AudioList::item {
                border-radius: 7px;
                padding: 0px 8px;
                margin: 2px 0px;
                color: #d1d5db;
            }
            QListWidget#AudioList::item:hover {
                background-color: #1e2535;
            }
            QListWidget#AudioList::item:selected {
                background-color: #1e2535;
                color: #ffffff;
            }
            QFrame#PlaybackBar {
                background-color: #16192a;
                border-top: 1px solid #2b303b;
            }
            QPushButton#BtnPlay {
                background-color: #f43f5e;
                color: white;
                border: none;
                border-radius: 20px;
                font-size: 14pt;
                font-weight: bold;
            }
            QPushButton#BtnPlay:hover { background-color: #e11d48; }
            QPushButton#BtnPlay:disabled { background-color: #4b5563; }
            QPushButton#BtnStop {
                background-color: #374151;
                color: #d1d5db;
                border: none;
                border-radius: 20px;
                font-size: 12pt;
            }
            QPushButton#BtnStop:hover { background-color: #4b5563; }
            QPushButton#BtnConfirm {
                background-color: #f43f5e;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 28px;
                font-size: 11pt;
                font-weight: bold;
            }
            QPushButton#BtnConfirm:hover { background-color: #e11d48; }
            QPushButton#BtnCancel {
                background-color: #1f2937;
                color: #9ca3af;
                border: 1px solid #374151;
                border-radius: 8px;
                padding: 10px 24px;
                font-size: 11pt;
            }
            QPushButton#BtnCancel:hover { background-color: #374151; color: #ffffff; }
            QPushButton#BtnRename {
                background-color: transparent;
                color: #9ca3af;
                border: 1px solid #374151;
                border-radius: 6px;
                padding: 5px 14px;
                font-size: 10pt;
            }
            QPushButton#BtnRename:hover { background-color: #1f2937; color: #ffffff; border-color: #f43f5e; }
            QLabel#NowPlaying {
                color: #9ca3af;
                font-size: 10pt;
                font-style: italic;
            }
            QLabel#HintLabel {
                color: #4b5563;
                font-size: 10pt;
            }
        """)

    # ── UI construction ────────────────────────────────────────────────────

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Title bar ────────────────────────────────────────────────────
        title_bar = QFrame()
        title_bar.setObjectName("TitleBar")
        title_bar.setFixedHeight(64)
        tl = QHBoxLayout(title_bar)
        tl.setContentsMargins(24, 0, 24, 0)
        tl.setSpacing(12)

        title_icon = QLabel("🎵")
        title_icon.setFont(QFont("Segoe UI Emoji", 18))
        tl.addWidget(title_icon)

        title_lbl = QLabel("选择背景音乐")
        title_lbl.setObjectName("DialogTitle")
        tl.addWidget(title_lbl)
        tl.addStretch()

        self.lbl_count = QLabel("已选 0 首")
        self.lbl_count.setObjectName("CountBadge")
        tl.addWidget(self.lbl_count)

        main_layout.addWidget(title_bar)

        # ── Body ──────────────────────────────────────────────────────────
        body = QFrame()
        body.setObjectName("BodyFrame")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(20, 16, 20, 10)
        bl.setSpacing(12)

        # Search row
        search_row = QHBoxLayout()
        search_icon = QLabel("🔍")
        search_icon.setFont(QFont("Segoe UI Emoji", 12))
        self.search_bar = QLineEdit()
        self.search_bar.setObjectName("SearchBar")
        self.search_bar.setPlaceholderText("搜索音频名称...")
        self.search_bar.textChanged.connect(self._filter_list)
        search_row.addWidget(search_icon)
        search_row.addWidget(self.search_bar)
        bl.addLayout(search_row)

        # Hint
        hint = QLabel("💡  点击列表中的音频可选择 / 取消选择，支持多选（显示播放顺序序号）")
        hint.setObjectName("HintLabel")
        bl.addWidget(hint)

        # List
        self.list_widget = QListWidget()
        self.list_widget.setObjectName("AudioList")
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        self.list_widget.currentItemChanged.connect(self._on_current_changed)
        fnt = QFont("Microsoft YaHei", 11)
        self.list_widget.setFont(fnt)
        bl.addWidget(self.list_widget, 1)

        # Rename + Edit-params row
        rename_row = QHBoxLayout()
        rename_row.addStretch()
        self.btn_edit_params = QPushButton("🎧  编辑参数")
        self.btn_edit_params.setObjectName("BtnRename")
        self.btn_edit_params.setToolTip("设置该音频的跳过开头时长和渐入时长")
        self.btn_edit_params.clicked.connect(self._edit_params_current)
        rename_row.addWidget(self.btn_edit_params)
        self.btn_rename = QPushButton("✏  重命名")
        self.btn_rename.setObjectName("BtnRename")
        self.btn_rename.clicked.connect(self._rename_current)
        rename_row.addWidget(self.btn_rename)
        bl.addLayout(rename_row)

        main_layout.addWidget(body, 1)

        # ── Playback bar ──────────────────────────────────────────────────
        pb_frame = QFrame()
        pb_frame.setObjectName("PlaybackBar")
        pb_frame.setFixedHeight(70)
        pb_layout = QHBoxLayout(pb_frame)
        pb_layout.setContentsMargins(24, 0, 24, 0)
        pb_layout.setSpacing(14)

        self.btn_play = QPushButton("▶")
        self.btn_play.setObjectName("BtnPlay")
        self.btn_play.setFixedSize(40, 40)
        self.btn_play.setToolTip("试听选中的音频")
        self.btn_play.clicked.connect(self._toggle_play)
        pb_layout.addWidget(self.btn_play)

        self.btn_stop = QPushButton("⏹")
        self.btn_stop.setObjectName("BtnStop")
        self.btn_stop.setFixedSize(40, 40)
        self.btn_stop.setToolTip("停止播放")
        self.btn_stop.clicked.connect(self._stop_play)
        pb_layout.addWidget(self.btn_stop)

        self.lbl_now_playing = QLabel("← 从列表选中一首，点击 ▶ 试听")
        self.lbl_now_playing.setObjectName("NowPlaying")
        pb_layout.addWidget(self.lbl_now_playing, 1)

        pb_layout.addStretch()

        btn_cancel = QPushButton("取 消")
        btn_cancel.setObjectName("BtnCancel")
        btn_cancel.clicked.connect(self.reject)

        btn_confirm = QPushButton("✓  确认选择")
        btn_confirm.setObjectName("BtnConfirm")
        btn_confirm.clicked.connect(self.accept)

        pb_layout.addWidget(btn_cancel)
        pb_layout.addWidget(btn_confirm)

        main_layout.addWidget(pb_frame)

    # ── Library loading ────────────────────────────────────────────────────

    def _load_library(self):
        self.list_widget.clear()
        for entry in self.library.get_all():
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole,     entry['path'])
            item.setData(Qt.ItemDataRole.UserRole + 1, entry['name'])
            item.setSizeHint(QSize(0, 52))
            self.list_widget.addItem(item)
        self._refresh_display()

    def _filter_list(self, text: str):
        text = text.lower()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            name: str = item.data(Qt.ItemDataRole.UserRole + 1)
            item.setHidden(bool(text) and text not in name.lower())

    # ── Selection logic ────────────────────────────────────────────────────

    def _on_item_clicked(self, item: QListWidgetItem):
        path: str = item.data(Qt.ItemDataRole.UserRole)
        if path in self._selected_order:
            self._selected_order.remove(path)
        else:
            self._selected_order.append(path)
        self._refresh_display()

    def _on_current_changed(self, current, _prev):
        if current:
            name: str = current.data(Qt.ItemDataRole.UserRole + 1)
            path: str = current.data(Qt.ItemDataRole.UserRole)
            self.lbl_now_playing.setText(f"🎵  {name}   |   {path}")

    def _refresh_display(self):
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            path: str = item.data(Qt.ItemDataRole.UserRole)
            name: str = item.data(Qt.ItemDataRole.UserRole + 1)

            if path in self._selected_order:
                idx = self._selected_order.index(path)
                badge = self._BADGES[idx] if idx < len(self._BADGES) else f"[{idx + 1}]"
                item.setText(f"  {badge}   🎵  {name}")
                item.setForeground(QColor("#f43f5e"))
                item.setBackground(QColor("#2d1520"))
            else:
                item.setText(f"       🎵  {name}")
                item.setForeground(QColor("#9ca3af"))
                item.setBackground(QColor("transparent"))

        n = len(self._selected_order)
        self.lbl_count.setText(f"已选 {n} 首")

    # ── Playback ───────────────────────────────────────────────────────────

    def _toggle_play(self):
        if not _HAS_MULTIMEDIA or self._player is None:
            QMessageBox.information(self, "提示", "当前环境暂不支持试听。\n请确认已安装 PyQt6 多媒体组件。")
            return
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
            self.btn_play.setText("▶")
        else:
            current = self.list_widget.currentItem()
            if not current:
                QMessageBox.information(self, "提示", "请先在列表中选中一首音频。")
                return
            path: str = current.data(Qt.ItemDataRole.UserRole)
            self._player.setSource(QUrl.fromLocalFile(path))
            self._player.play()
            self.btn_play.setText("⏸")

    def _stop_play(self):
        if _HAS_MULTIMEDIA and self._player:
            self._player.stop()
            self.btn_play.setText("▶")

    def _on_playback_state_changed(self, state):
        if state == QMediaPlayer.PlaybackState.StoppedState:
            self.btn_play.setText("▶")

    # ── Rename ─────────────────────────────────────────────────────────────

    def _edit_params_current(self):
        item = self.list_widget.currentItem()
        if not item:
            QMessageBox.information(self, "提示", "请先在列表中选中一条音频。")
            return
        path: str = item.data(Qt.ItemDataRole.UserRole)
        name: str = item.data(Qt.ItemDataRole.UserRole + 1)
        dlg = AudioEditDialog(self.library, path, name, parent=self)
        dlg.exec()   # result is auto-saved inside the dialog

    def _rename_current(self):
        item = self.list_widget.currentItem()
        if not item:
            QMessageBox.information(self, "提示", "请先在列表中选中一条音频。")
            return
        path: str = item.data(Qt.ItemDataRole.UserRole)
        current_name: str = item.data(Qt.ItemDataRole.UserRole + 1)
        new_name, ok = QInputDialog.getText(self, "重命名", "输入新的显示名称：", text=current_name)
        if ok and new_name.strip():
            self.library.rename(path, new_name.strip())
            item.setData(Qt.ItemDataRole.UserRole + 1, new_name.strip())
            self._refresh_display()

    # ── Cleanup & result ───────────────────────────────────────────────────

    def closeEvent(self, event):
        self._stop_play()
        super().closeEvent(event)

    def get_selected_paths(self) -> list[str]:
        """Return selected audio paths in user-defined order."""
        return list(self._selected_order)


# ══════════════════════════════════════════════════════════════════════════════
#  AudioEditDialog — per-audio skip_start + fade_in editor
# ══════════════════════════════════════════════════════════════════════════════

class AudioEditDialog(QDialog):
    """Edit skip_start and fade_in for a single audio entry in the library."""

    def __init__(self, library: 'AudioLibrary', path: str, name: str, parent=None):
        super().__init__(parent)
        self.library = library
        self.path    = path
        self.name    = name

        params = library.get_params_for_path(path)
        self._skip_start: float = params['skip_start']
        self._fade_in:    float = params['fade_in']

        # Player
        self._player    = None
        self._audio_out = None
        if _HAS_MULTIMEDIA:
            self._player    = QMediaPlayer()
            self._audio_out = QAudioOutput()
            self._player.setAudioOutput(self._audio_out)
            self._audio_out.setVolume(0.8)
            self._player.playbackStateChanged.connect(self._on_state_changed)

        self.setWindowTitle("编辑音频参数")
        self.setFixedSize(520, 400)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint)
        self._apply_style()
        self._setup_ui()

    # ── Stylesheet ──────────────────────────────────────────────────────────

    def _apply_style(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #1a1d27;
                color: #d1d5db;
                font-family: "Microsoft YaHei", "Segoe UI";
            }
            QFrame#EditTitleBar {
                background-color: #16192a;
                border-bottom: 2px solid #f43f5e;
            }
            QLabel#EditTitle {
                font-size: 14pt;
                font-weight: bold;
                color: #ffffff;
            }
            QFrame#ParamCard {
                background-color: #1e2535;
                border-radius: 10px;
                border: 1px solid #2b303b;
            }
            QLabel#CardTitle {
                font-size: 11pt;
                font-weight: bold;
                color: #f43f5e;
            }
            QLabel#HintText {
                color: #6b7280;
                font-size: 9pt;
            }
            QDoubleSpinBox {
                background-color: #0f1117;
                border: 1px solid #374151;
                border-radius: 5px;
                padding: 5px 8px;
                color: #ffffff;
                font-size: 11pt;
            }
            QDoubleSpinBox:focus { border-color: #f43f5e; }
            QSlider::groove:horizontal {
                border-radius: 3px; height: 6px;
                background: #374151;
            }
            QSlider::handle:horizontal {
                background: #f43f5e; width: 16px;
                margin: -5px 0; border-radius: 8px;
            }
            QSlider::sub-page:horizontal {
                background: #f43f5e; border-radius: 3px;
            }
            QPushButton#BtnPreview {
                background-color: #f43f5e; color: white;
                border: none; border-radius: 7px;
                padding: 8px 18px; font-size: 11pt;
            }
            QPushButton#BtnPreview:hover { background-color: #e11d48; }
            QPushButton#BtnSave {
                background-color: #f43f5e; color: white;
                border: none; border-radius: 8px;
                padding: 10px 28px; font-size: 11pt; font-weight: bold;
            }
            QPushButton#BtnSave:hover { background-color: #e11d48; }
            QPushButton#BtnEditCancel {
                background-color: #1f2937; color: #9ca3af;
                border: 1px solid #374151; border-radius: 8px;
                padding: 10px 24px; font-size: 11pt;
            }
            QPushButton#BtnEditCancel:hover { background-color: #374151; color: white; }
        """)

    # ── UI construction ────────────────────────────────────────────────────

    def _setup_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── Title bar ────────────────────────────────────────────────────
        title_bar = QFrame(); title_bar.setObjectName("EditTitleBar")
        title_bar.setFixedHeight(56)
        tl = QHBoxLayout(title_bar); tl.setContentsMargins(22, 0, 22, 0)
        lbl = QLabel(f"🎵  编辑参数：{self.name}"); lbl.setObjectName("EditTitle")
        tl.addWidget(lbl)
        root_layout.addWidget(title_bar)

        # ── Body ──────────────────────────────────────────────────────────
        body = QVBoxLayout()
        body.setContentsMargins(22, 16, 22, 16)
        body.setSpacing(14)

        # File path hint
        path_lbl = QLabel(f"📂  {self.path}")
        path_lbl.setObjectName("HintText")
        path_lbl.setWordWrap(True)
        body.addWidget(path_lbl)

        # ── Card 1: skip_start ────────────────────────────────────────────
        body.addWidget(self._make_card(
            "✂  跳过开头",
            "从音频第 X 秒处开始播放，将开头的安静 / 无声部分跳过",
            is_skip=True
        ))

        # ── Card 2: fade_in ───────────────────────────────────────────────
        body.addWidget(self._make_card(
            "〜  音频渐入",
            "跳过开头后，音量从 0 渐入至正常音量所需的秒数",
            is_skip=False
        ))

        # ── Preview row ───────────────────────────────────────────────────
        prev_row = QHBoxLayout()
        self.btn_preview = QPushButton("▶  试听效果")
        self.btn_preview.setObjectName("BtnPreview")
        self.btn_preview.clicked.connect(self._toggle_preview)
        prev_row.addWidget(self.btn_preview)
        hint = QLabel("试听将从跳过点开始播放（渐入效果在生成视频时应用）")
        hint.setObjectName("HintText")
        prev_row.addWidget(hint, 1)
        body.addLayout(prev_row)

        body.addStretch()

        # ── Bottom buttons ─────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = QPushButton("取 消"); btn_cancel.setObjectName("BtnEditCancel")
        btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("✓  保 存"); btn_save.setObjectName("BtnSave")
        btn_save.clicked.connect(self._save)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_save)
        body.addLayout(btn_row)

        wrapper = QFrame()
        wrapper.setLayout(body)
        wrapper.setStyleSheet("background-color: #1a1d27;")
        root_layout.addWidget(wrapper, 1)

    def _make_card(self, title: str, hint: str, is_skip: bool) -> QFrame:
        card = QFrame(); card.setObjectName("ParamCard")
        lo = QVBoxLayout(card)
        lo.setContentsMargins(16, 10, 16, 12)
        lo.setSpacing(8)

        title_lbl = QLabel(title); title_lbl.setObjectName("CardTitle")
        lo.addWidget(title_lbl)
        hint_lbl = QLabel(hint); hint_lbl.setObjectName("HintText")
        lo.addWidget(hint_lbl)

        row = QHBoxLayout(); row.setSpacing(12)

        slider = QSlider(Qt.Orientation.Horizontal)
        spin   = QDoubleSpinBox()
        spin.setSingleStep(0.1); spin.setDecimals(1)
        spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        spin.setFixedWidth(90)

        if is_skip:
            slider.setRange(0, 300)          # 0.0 – 30.0 s
            slider.setValue(int(self._skip_start * 10))
            spin.setRange(0.0, 30.0); spin.setValue(self._skip_start); spin.setSuffix(" 秒")
            slider.valueChanged.connect(lambda v, s=spin:  s.setValue(v / 10.0))
            spin.valueChanged.connect(lambda v, sl=slider: sl.setValue(int(v * 10)))
            spin.valueChanged.connect(lambda v: setattr(self, '_skip_start', v))
            self.spin_skip = spin
        else:
            slider.setRange(0, 100)          # 0.0 – 10.0 s
            slider.setValue(int(self._fade_in * 10))
            spin.setRange(0.0, 10.0); spin.setValue(self._fade_in); spin.setSuffix(" 秒")
            slider.valueChanged.connect(lambda v, s=spin:  s.setValue(v / 10.0))
            spin.valueChanged.connect(lambda v, sl=slider: sl.setValue(int(v * 10)))
            spin.valueChanged.connect(lambda v: setattr(self, '_fade_in', v))
            self.spin_fade = spin

        row.addWidget(slider, 1)
        row.addWidget(spin)
        lo.addLayout(row)
        return card

    # ── Preview ────────────────────────────────────────────────────────────

    def _toggle_preview(self):
        if not _HAS_MULTIMEDIA or self._player is None:
            QMessageBox.information(self, "提示", "当前环境不支持试听。")
            return
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.stop()
        else:
            from PyQt6.QtCore import QUrl
            self._seeking = False          # reset guard each time we start
            self._player.setSource(QUrl.fromLocalFile(self.path))
            # positionChanged fires quickly and repeatedly — _seek_once guards itself
            self._player.positionChanged.connect(self._seek_once)
            self._player.play()

    def _seek_once(self, _pos):
        """Seek to skip_start exactly once, then disconnect.
        positionChanged fires many times in rapid succession; the _seeking flag
        prevents re-entrant seeks, and the try/except prevents crashes if the
        slot is somehow invoked after already being disconnected."""
        if self._seeking:
            return
        self._seeking = True
        if self._player:
            target_ms = int(self._skip_start * 1000)
            self._player.setPosition(target_ms)
        try:
            self._player.positionChanged.disconnect(self._seek_once)
        except (RuntimeError, TypeError):
            pass   # already disconnected — safe to ignore


    def _on_state_changed(self, state):
        is_playing = (state == QMediaPlayer.PlaybackState.PlayingState)
        self.btn_preview.setText("⏹  停止试听" if is_playing else "▶  试听效果")

    # ── Save ───────────────────────────────────────────────────────────────

    def _save(self):
        self.library.set_audio_params(self.path, self._skip_start, self._fade_in)
        self.accept()

    def closeEvent(self, event):
        if _HAS_MULTIMEDIA and self._player:
            self._player.stop()
        super().closeEvent(event)


# ══════════════════════════════════════════════════════════════════════════════
#  IrregularSegmentsDialog — 不规则片段合并配置
# ══════════════════════════════════════════════════════════════════════════════

class IrregularSegmentsDialog(QDialog):
    """Let the user paste a per-line list of integers defining how many clips
    each output video should contain."""

    def __init__(self, current_segments: list = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("不规则片段合并 — 配置列表")
        self.setMinimumSize(420, 480)
        self.resize(460, 520)
        self._segments: list[int] = []
        self._setup_ui(current_segments or [])
        self._parse()

    def _setup_ui(self, current_segments: list):
        self.setStyleSheet("""
            QDialog { background-color: #1a1d27; color: #d1d5db;
                      font-family: "Microsoft YaHei", "Segoe UI"; }
            QLabel   { color: #d1d5db; }
            QLabel#Hint { color: #6b7280; font-size: 9pt; }
            QLabel#Summary { font-size: 10pt; padding: 6px 10px;
                             border-radius: 6px; background: #1e2535; }
            QPlainTextEdit { background: #0f1117; border: 1px solid #374151;
                             border-radius: 6px; color: #e5e7eb;
                             font-size: 11pt; padding: 8px; }
            QPlainTextEdit:focus { border-color: #f43f5e; }
            QPushButton#BtnOK { background: #f43f5e; color: white; border: none;
                                border-radius: 7px; padding: 9px 24px;
                                font-size: 11pt; font-weight: bold; }
            QPushButton#BtnOK:hover { background: #e11d48; }
            QPushButton#BtnCancelD { background: #1f2937; color: #9ca3af;
                                    border: 1px solid #374151; border-radius: 7px;
                                    padding: 9px 20px; font-size: 11pt; }
            QPushButton#BtnCancelD:hover { background: #374151; color: white; }
        """)
        lo = QVBoxLayout(self)
        lo.setContentsMargins(20, 20, 20, 20)
        lo.setSpacing(12)

        title = QLabel("🔀  不规则片段合并")
        title.setStyleSheet("font-size: 14pt; font-weight: bold; color: #ffffff;")
        lo.addWidget(title)

        hint = QLabel(
            "每行输入一个数字，代表该视频合并的片段数。\n"
            "支持直接从 Excel / WPS 表格复制粘贴（每格一行）。"
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        lo.addWidget(hint)

        self.text_edit = QPlainTextEdit()
        self.text_edit.setPlaceholderText(
            "例如:\n8\n4\n6\n\n→ 输出 3 个视频，分别合并 8、4、6 个片段"
        )
        if current_segments:
            self.text_edit.setPlainText("\n".join(str(s) for s in current_segments))
        self.text_edit.textChanged.connect(self._parse)
        lo.addWidget(self.text_edit, 1)

        self.lbl_summary = QLabel("📊 暂未输入")
        self.lbl_summary.setObjectName("Summary")
        self.lbl_summary.setWordWrap(True)
        lo.addWidget(self.lbl_summary)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = QPushButton("取 消")
        btn_cancel.setObjectName("BtnCancelD")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("✓  确 认")
        btn_ok.setObjectName("BtnOK")
        btn_ok.clicked.connect(self._accept)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        lo.addLayout(btn_row)

    def _parse(self):
        segments, errors = [], []
        for i, raw in enumerate(self.text_edit.toPlainText().splitlines(), 1):
            line = raw.strip()
            if not line:
                continue
            try:
                n = int(line)
                if n < 1:
                    errors.append(f"第{i}行: 必须 ≥ 1")
                else:
                    segments.append(n)
            except ValueError:
                errors.append(f"第{i}行: 非数字 ‘{line}’")
        if errors:
            self.lbl_summary.setText("⚠ 错误: " + "  |  ".join(errors[:3]))
            self.lbl_summary.setStyleSheet("color: #f43f5e; background: #2d1520;")
            self._segments = []
        elif segments:
            total = sum(segments)
            preview = ", ".join(str(s) for s in segments[:10])
            if len(segments) > 10:
                preview += "..."
            self.lbl_summary.setText(
                f"✅  共 {len(segments)} 个视频，片段总数 {total}    [{preview}]"
            )
            self.lbl_summary.setStyleSheet("color: #10b981; background: #0d2a1f;")
            self._segments = segments
        else:
            self.lbl_summary.setText("📊 暂未输入")
            self.lbl_summary.setStyleSheet("")
            self._segments = []

    def _accept(self):
        self._parse()
        if not self._segments:
            QMessageBox.warning(self, "提示", "请至少输入一个有效的片段数。")
            return
        self.accept()

    def get_segments(self) -> list[int]:
        return list(self._segments)


# ══════════════════════════════════════════════════════════════════════════════
#  LoopModeDialog — 循环模式配置
# ══════════════════════════════════════════════════════════════════════════════

class LoopModeDialog(QDialog):
    """Let the user specify how many times each video (in order) should loop.
    Each line maps to one input video by position. If there are more lines than
    files the excess lines are silently ignored; if there are fewer lines the
    remaining files are skipped."""

    def __init__(self, current_loops: list = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("循环模式 — 配置每个视频的循环次数")
        self.setMinimumSize(440, 500)
        self.resize(480, 540)
        self._loops: list[int] = []
        self._setup_ui(current_loops or [])
        self._parse()

    def _setup_ui(self, current_loops: list):
        self.setStyleSheet("""
            QDialog { background-color: #1a1d27; color: #d1d5db;
                      font-family: \"Microsoft YaHei\", \"Segoe UI\"; }
            QLabel   { color: #d1d5db; }
            QLabel#Hint { color: #6b7280; font-size: 9pt; }
            QLabel#Summary { font-size: 10pt; padding: 6px 10px;
                             border-radius: 6px; background: #1e2535; }
            QPlainTextEdit { background: #0f1117; border: 1px solid #374151;
                             border-radius: 6px; color: #e5e7eb;
                             font-size: 11pt; padding: 8px; }
            QPlainTextEdit:focus { border-color: #f43f5e; }
            QPushButton#BtnOK { background: #f43f5e; color: white; border: none;
                                border-radius: 7px; padding: 9px 24px;
                                font-size: 11pt; font-weight: bold; }
            QPushButton#BtnOK:hover { background: #e11d48; }
            QPushButton#BtnCancelD { background: #1f2937; color: #9ca3af;
                                    border: 1px solid #374151; border-radius: 7px;
                                    padding: 9px 20px; font-size: 11pt; }
            QPushButton#BtnCancelD:hover { background: #374151; color: white; }
        """)
        lo = QVBoxLayout(self)
        lo.setContentsMargins(20, 20, 20, 20)
        lo.setSpacing(12)

        title = QLabel("🔁  循环模式")
        title.setStyleSheet("font-size: 14pt; font-weight: bold; color: #ffffff;")
        lo.addWidget(title)

        hint = QLabel(
            "每行输入一个数字，代表对应顺序的视频素材循环几次。\n"
            "第 1 行 → 第 1 个文件，第 2 行 → 第 2 个文件，依此类推。\n"
            "若行数超过文件数，多余行自动忽略；若行数少于文件数，多余文件跳过。\n"
            "支持直接从 Excel / WPS 表格复制粘贴（每格一行）。"
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        lo.addWidget(hint)

        self.text_edit = QPlainTextEdit()
        self.text_edit.setPlaceholderText(
            "例如：\n3\n5\n2\n\n"
            "→ 第1个视频循环3次、第2个循环5次、第3个循环2次\n"
            "   合计输出 3 个独立视频（每个视频是单素材的多次循环合并）"
        )
        if current_loops:
            self.text_edit.setPlainText("\n".join(str(n) for n in current_loops))
        self.text_edit.textChanged.connect(self._parse)
        lo.addWidget(self.text_edit, 1)

        self.lbl_summary = QLabel("📊 暂未输入")
        self.lbl_summary.setObjectName("Summary")
        self.lbl_summary.setWordWrap(True)
        lo.addWidget(self.lbl_summary)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = QPushButton("取 消")
        btn_cancel.setObjectName("BtnCancelD")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("✓  确 认")
        btn_ok.setObjectName("BtnOK")
        btn_ok.clicked.connect(self._accept)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        lo.addLayout(btn_row)

    def _parse(self):
        loops, errors = [], []
        for i, raw in enumerate(self.text_edit.toPlainText().splitlines(), 1):
            line = raw.strip()
            if not line:
                continue
            try:
                n = int(line)
                if n < 1:
                    errors.append(f"第{i}行: 必须 ≥ 1")
                else:
                    loops.append(n)
            except ValueError:
                errors.append(f"第{i}行: 非数字 '{line}'")
        if errors:
            self.lbl_summary.setText("⚠ 错误: " + "  |  ".join(errors[:3]))
            self.lbl_summary.setStyleSheet("color: #f43f5e; background: #2d1520;")
            self._loops = []
        elif loops:
            total_clips = sum(loops)
            preview = ", ".join(str(n) for n in loops[:10])
            if len(loops) > 10:
                preview += "..."
            self.lbl_summary.setText(
                f"✅  共 {len(loops)} 个视频，总片段数 {total_clips}    [{preview}]"
            )
            self.lbl_summary.setStyleSheet("color: #10b981; background: #0d2a1f;")
            self._loops = loops
        else:
            self.lbl_summary.setText("📊 暂未输入")
            self.lbl_summary.setStyleSheet("")
            self._loops = []

    def _accept(self):
        self._parse()
        if not self._loops:
            QMessageBox.warning(self, "提示", "请至少输入一个有效的循环次数。")
            return
        self.accept()

    def get_loops(self) -> list[int]:
        """Return loop counts per video in order."""
        return list(self._loops)


# ══════════════════════════════════════════════════════════════════════════════

class ImageManager:
    def __init__(self):
        self.pool = {}
        self.original_order = []

    def add_items(self, items):
        for item in items:
            if item not in self.pool:
                self.pool[item] = 0
                self.original_order.append(item)

    def clear(self):
        self.pool.clear()
        self.original_order.clear()

    def get_items_for_merge(self, count, mode="随机合并"):
        if not self.pool:
            return []
        selected = []
        for _ in range(count):
            min_usage = min(self.pool.values())
            candidates = [k for k in self.original_order if self.pool[k] == min_usage]
            if not candidates:
                break
            chosen = random.choice(candidates) if mode == "随机合并" else candidates[0]
            selected.append(chosen)
            self.pool[chosen] += 1
        return selected


# ══════════════════════════════════════════════════════════════════════════════
#  ImageMergerUI
# ══════════════════════════════════════════════════════════════════════════════

class ImageMergerUI(QWidget):
    def __init__(self):
        super().__init__()
        self.image_manager = ImageManager()
        self.audio_library = AudioLibrary()
        self.selected_audios: list[str] = []   # ordered list of selected audio paths
        self.irregular_segments: list[int] = []  # 不规则合并片段列表
        self.worker = None
        self.base_dir = ""
        self.output_dir = ""
        self.settings = QSettings("MyCompany", "VideoToolbox")

        self.setup_ui()
        self.bind_events()
        self.load_settings()

    # ── Settings ───────────────────────────────────────────────────────────

    def load_settings(self):
        self.spin_merge_count.setValue(self.settings.value("i_merge_count", 3, type=int))
        self.spin_output_count.setValue(self.settings.value("i_output_count", 1, type=int))
        self.combo_aspect_ratio.setCurrentText(self.settings.value("i_aspect_ratio", "9:16 (竖屏/抖音)"))
        self.combo_resolution.setCurrentText(self.settings.value("i_resolution", "1080P (1K/推荐)"))
        self.combo_order.setCurrentText(self.settings.value("i_order", "随机合并"))
        self.spin_duration.setValue(self.settings.value("i_duration", 5, type=int))
        saved_trans = self.settings.value("i_transition", "淡入淡出 (fade)")
        if self.combo_transition.findText(saved_trans) >= 0:
            self.combo_transition.setCurrentText(saved_trans)
        self.check_effect.setChecked(self.settings.value("i_chk_effect", True, type=bool))
        self.combo_audio_mode.setCurrentText(self.settings.value("i_audio_mode", "随机分配"))
        self.check_audio_loop.setChecked(self.settings.value("i_audio_loop", True, type=bool))
        self.spin_audio_volume.setValue(self.settings.value("i_audio_volume", 100, type=int))

        saved_effect = self.settings.value("i_effect", "中心缓慢放大 (Zoom Center)")
        if self.combo_effect.findText(saved_effect) >= 0:
            self.combo_effect.setCurrentText(saved_effect)

        saved_dir = self.settings.value("i_base_dir", "")
        if saved_dir and os.path.exists(saved_dir):
            self.base_dir = saved_dir
            self.lbl_out_path.setText(f"已选择: {self.base_dir}")

        self._refresh_audio_library_list()

        # 恢复上次选择的背景音乐（过滤掉已从库中删除的条目）
        saved_selected = self.settings.value("i_selected_audios", [], type=list)
        library_paths = {e['path'] for e in self.audio_library.get_all()}
        self.selected_audios = [p for p in saved_selected if p in library_paths]
        self._update_audio_select_bar()

        # 恢复不规则合并设置
        import json
        try:
            raw = self.settings.value("i_irregular_segments", "[]")
            self.irregular_segments = json.loads(raw) if raw else []
        except Exception:
            self.irregular_segments = []
        irr_on = self.settings.value("i_irregular_on", False, type=bool)
        self.check_irregular.setChecked(irr_on)
        self._toggle_irregular_mode()
        self._update_irregular_label()

    def save_settings(self):
        self.settings.setValue("i_merge_count", self.spin_merge_count.value())
        self.settings.setValue("i_output_count", self.spin_output_count.value())
        self.settings.setValue("i_aspect_ratio", self.combo_aspect_ratio.currentText())
        self.settings.setValue("i_resolution", self.combo_resolution.currentText())
        self.settings.setValue("i_order", self.combo_order.currentText())
        self.settings.setValue("i_duration", self.spin_duration.value())
        self.settings.setValue("i_transition", self.combo_transition.currentText())
        self.settings.setValue("i_chk_effect", self.check_effect.isChecked())
        self.settings.setValue("i_effect", self.combo_effect.currentText())
        self.settings.setValue("i_audio_mode", self.combo_audio_mode.currentText())
        self.settings.setValue("i_audio_loop", self.check_audio_loop.isChecked())
        self.settings.setValue("i_audio_volume", self.spin_audio_volume.value())
        self.settings.setValue("i_base_dir", self.base_dir)
        self.settings.setValue("i_selected_audios", self.selected_audios)
        import json
        self.settings.setValue("i_irregular_segments", json.dumps(self.irregular_segments))
        self.settings.setValue("i_irregular_on", self.check_irregular.isChecked())

    # ── UI construction ────────────────────────────────────────────────────

    def create_card(self, title):
        card = QFrame()
        card.setProperty("class", "Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        lbl_title = QLabel(title)
        lbl_title.setProperty("class", "CardTitle")
        layout.addWidget(lbl_title)
        return card, layout

    def setup_ui(self):
        # ── 外层：用 QScrollArea 包裹，实现垂直滚动 ───────────────────────
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.viewport().setAutoFillBackground(False)
        outer_layout.addWidget(scroll_area)

        # ── 内容容器 ────────────────────────────────────────────────────────
        inner_widget = QWidget()
        inner_widget.setAutoFillBackground(False)
        scroll_area.setWidget(inner_widget)
        main_layout = QVBoxLayout(inner_widget)
        main_layout.setContentsMargins(0, 0, 1, 0)
        main_layout.setSpacing(2)

        # ── 1. Image upload card ──────────────────────────────────────────
        card_upload, layout_upload = self.create_card("🖼️ 输入图片素材")
        self.file_list = QListWidget()
        self.file_list.setFixedHeight(140)
        self.file_list.setAcceptDrops(True)
        self.file_list.setDragDropMode(QListWidget.DragDropMode.DropOnly)
        self.file_list.installEventFilter(self)
        layout_upload.addWidget(self.file_list)

        btn_layout = QHBoxLayout()
        self.btn_add_files = QPushButton("添加图片")
        self.btn_add_folder = QPushButton("添加文件夹")
        self.btn_clear = QPushButton("清空列表")
        btn_layout.addWidget(self.btn_add_files)
        btn_layout.addWidget(self.btn_add_folder)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_clear)
        layout_upload.addLayout(btn_layout)
        main_layout.addWidget(card_upload)

        # ── 2. Audio library card ─────────────────────────────────────────
        card_audio, layout_audio = self.create_card("📻 音频素材入库")

        self.audio_lib_list = QListWidget()
        self.audio_lib_list.setFixedHeight(130)
        self.audio_lib_list.setAcceptDrops(True)
        self.audio_lib_list.setDragDropMode(QListWidget.DragDropMode.DropOnly)
        self.audio_lib_list.installEventFilter(self)
        self.audio_lib_list.setToolTip("将 MP3 / WAV / AAC / OGG 文件拖拽至此，可永久保存入库")
        layout_audio.addWidget(self.audio_lib_list)

        audio_btn_layout = QHBoxLayout()
        self.btn_add_audio = QPushButton("添加音频")
        self.btn_add_audio_folder = QPushButton("添加文件夹")
        self.btn_remove_audio = QPushButton("删除选中")
        self.btn_clear_audio = QPushButton("清空音频库")
        audio_btn_layout.addWidget(self.btn_add_audio)
        audio_btn_layout.addWidget(self.btn_add_audio_folder)
        audio_btn_layout.addStretch()
        audio_btn_layout.addWidget(self.btn_remove_audio)
        audio_btn_layout.addWidget(self.btn_clear_audio)
        layout_audio.addLayout(audio_btn_layout)

        # Separator label
        select_title = QLabel("🎼  当前任务的背景音乐（点击下方选择）")
        select_title.setProperty("class", "CardTitle")
        layout_audio.addWidget(select_title)

        # Clickable selected-audio bar
        self.audio_select_bar = ClickableFrame()
        self.audio_select_bar.setObjectName("AudioSelectBar")
        self.audio_select_bar.setMinimumHeight(44)
        self.audio_select_bar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.audio_select_bar.setStyleSheet("""
            QFrame#AudioSelectBar {
                background-color: #0f1117;
                border: 1px dashed #374151;
                border-radius: 8px;
            }
            QFrame#AudioSelectBar:hover {
                border-color: #f43f5e;
            }
        """)
        bar_layout = QHBoxLayout(self.audio_select_bar)
        bar_layout.setContentsMargins(14, 6, 14, 6)
        self.audio_select_label = QLabel("未选择背景音乐 — 点击此处打开选择器")
        self.audio_select_label.setStyleSheet("color: #4b5563; font-size: 10pt;")
        bar_layout.addWidget(self.audio_select_label)
        bar_layout.addStretch()
        hint_lbl = QLabel("双击 / 单击选择  →")
        hint_lbl.setStyleSheet("color: #374151; font-size: 9pt;")
        bar_layout.addWidget(hint_lbl)
        layout_audio.addWidget(self.audio_select_bar)

        main_layout.addWidget(card_audio)

        # ── 3. Params card ────────────────────────────────────────────────
        card_params, layout_params = self.create_card("✨ 图片合并参数配置")
        grid = QGridLayout()
        grid.setVerticalSpacing(15)
        grid.setHorizontalSpacing(20)
        # 标签列不拉伸，输入框列等比拉伸但有最大宽度限制
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 0)
        grid.setColumnStretch(3, 1)
        _INPUT_MAX_W = 260

        grid.addWidget(QLabel("每个视频合并几张图:"), 0, 0)
        self.spin_merge_count = QSpinBox()
        self.spin_merge_count.setRange(2, 200)
        self.spin_merge_count.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_merge_count.setMaximumWidth(_INPUT_MAX_W)
        grid.addWidget(self.spin_merge_count, 0, 1)

        grid.addWidget(QLabel("输出几个视频:"), 0, 2)
        self.spin_output_count = QSpinBox()
        self.spin_output_count.setRange(1, 1000)
        self.spin_output_count.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_output_count.setMaximumWidth(_INPUT_MAX_W)
        grid.addWidget(self.spin_output_count, 0, 3)

        grid.addWidget(QLabel("生成的视频画幅(尺寸):"), 1, 0)
        self.combo_aspect_ratio = QComboBox()
        self.combo_aspect_ratio.addItems(["9:16 (竖屏/抖音)", "16:9 (横屏/西瓜)", "3:4 (小红书)", "4:5 (Ins)", "1:1 (正方形)"])
        self.combo_aspect_ratio.setMaximumWidth(_INPUT_MAX_W)
        grid.addWidget(self.combo_aspect_ratio, 1, 1)

        grid.addWidget(QLabel("输出分辨率:"), 1, 2)
        self.combo_resolution = QComboBox()
        self.combo_resolution.addItems(["1080P (1K/推荐)", "720P (标清)", "2K (超清)", "4K (极清)"])
        self.combo_resolution.setMaximumWidth(_INPUT_MAX_W)
        grid.addWidget(self.combo_resolution, 1, 3)

        grid.addWidget(QLabel("合并顺序:"), 2, 0)
        self.combo_order = QComboBox()
        self.combo_order.addItems(["随机合并", "按顺序合并"])
        self.combo_order.setMaximumWidth(_INPUT_MAX_W)
        grid.addWidget(self.combo_order, 2, 1)

        grid.addWidget(QLabel("每张图片展示时长(秒):"), 2, 2)
        self.spin_duration = QSpinBox()
        self.spin_duration.setRange(2, 60)
        self.spin_duration.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_duration.setMaximumWidth(_INPUT_MAX_W)
        grid.addWidget(self.spin_duration, 2, 3)

        trans_layout = QHBoxLayout()
        trans_layout.addWidget(QLabel("转场特效:"))
        self.combo_transition = QComboBox()
        self.combo_transition.addItems([
            "无转场（直接拼接）",
            "淡入淡出 (fade)", "向左滑动 (slideleft)", "向右滑动 (slideright)",
            "向上滑动 (slideup)", "向下滑动 (slidedown)", "平滑向左 (smoothleft)",
            "直线擦除 (wipeleft)", "对角擦除 (wiperv)", "圆形展开 (circlecrop)",
            "矩形展开 (rectcrop)", "雷达扫描 (radial)", "马赛克 (pixelize)",
            "溶解 (dissolve)", "距离形变 (distance)", "黑场过渡 (fadeblack)"
        ])
        self.combo_transition.setToolTip("选择'无转场（直接拼接）'时图片之间直接切换，无过渡效果")
        trans_layout.addWidget(self.combo_transition)
        grid.addLayout(trans_layout, 3, 0, 1, 2)

        eff_layout = QHBoxLayout()
        self.check_effect = QCheckBox("动态特效")
        eff_layout.addWidget(self.check_effect)
        self.combo_effect = QComboBox()
        self.combo_effect.addItems([
            "中心缓慢放大 (Zoom Center)",
            "左上缓慢放大 (Zoom Top-Left)",
            "右上缓慢放大 (Zoom Top-Right)",
            "左下缓慢放大 (Zoom Bottom-Left)",
            "右下缓慢放大 (Zoom Bottom-Right)",
            "放大后拉远缩小 (Zoom Out)",
            "放大后缓缓上移 (Pan Up)",
            "黑白老照片 (B&W)",
            "色彩增强 (EQ)"
        ])
        eff_layout.addWidget(self.combo_effect)
        grid.addLayout(eff_layout, 3, 2, 1, 2)

        # ── Row 4: Audio distribution & loop ─────────────────────────────
        audio_param_layout = QHBoxLayout()
        audio_param_layout.setSpacing(12)
        audio_param_layout.addWidget(QLabel("🎵 音频分配模式:"))
        self.combo_audio_mode = QComboBox()
        self.combo_audio_mode.addItems(["随机分配", "按顺序补全", "按顺序不补全"])
        self.combo_audio_mode.setToolTip(
            "随机分配：随机为每个视频分配一首背景音乐\n"
            "按顺序补全：按选择顺序依次分配，不足时循环补全\n"
            "按顺序不补全：按选择顺序依次分配，不足时剩余视频无音频"
        )
        audio_param_layout.addWidget(self.combo_audio_mode)
        audio_param_layout.addSpacing(20)
        self.check_audio_loop = QCheckBox("音频自动循环（时长不足时）")
        self.check_audio_loop.setChecked(True)
        self.check_audio_loop.setToolTip("若开启，当音频时长短于视频时，自动循环播放补全；若关闭，音频结束后静音")
        audio_param_layout.addWidget(self.check_audio_loop)
        audio_param_layout.addStretch()
        grid.addLayout(audio_param_layout, 4, 0, 1, 4)

        # ── Row 5: Volume (per-audio skip/fade now lives in the audio library) ──
        audio_ext_layout = QHBoxLayout()
        audio_ext_layout.setSpacing(10)
        audio_ext_layout.addWidget(QLabel("\U0001f50a \u97f3\u91cf:"))
        self.slider_audio_volume = QSlider(Qt.Orientation.Horizontal)
        self.slider_audio_volume.setRange(0, 200)
        self.slider_audio_volume.setValue(100)
        self.slider_audio_volume.setFixedWidth(110)
        self.slider_audio_volume.setToolTip("0% = \u9759\u97f3 / 100% = \u539f\u59cb\u97f3\u91cf / 200% = \u53cc\u500d\u97f3\u91cf")
        self.spin_audio_volume = QSpinBox()
        self.spin_audio_volume.setRange(0, 200)
        self.spin_audio_volume.setValue(100)
        self.spin_audio_volume.setSuffix(" %")
        self.spin_audio_volume.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_audio_volume.setFixedWidth(70)
        self.spin_audio_volume.setToolTip("\u97f3\u9891\u97f3\u91cf\u767e\u5206\u6bd4\uff08100% = \u539f\u59cb\u97f3\u91cf\uff09")
        self.slider_audio_volume.valueChanged.connect(self.spin_audio_volume.setValue)
        self.spin_audio_volume.valueChanged.connect(self.slider_audio_volume.setValue)
        audio_ext_layout.addWidget(self.slider_audio_volume)
        audio_ext_layout.addWidget(self.spin_audio_volume)
        vol_hint = QLabel("\u2139 \u8df3\u8fc7\u5f00\u5934 / \u6e10\u5165\u65f6\u957f\uff1a\u5728\u97f3\u9891\u5e93\u4e2d\u9009\u4e2d\u97f3\u9891\u540e\u70b9\u51fb [\ud83c\udfa7 \u7f16\u8f91\u53c2\u6570] \u8fdb\u884c\u8bbe\u7f6e")
        vol_hint.setStyleSheet("color: #4b5563; font-size: 9pt;")
        audio_ext_layout.addSpacing(16)
        audio_ext_layout.addWidget(vol_hint)
        audio_ext_layout.addStretch()
        grid.addLayout(audio_ext_layout, 5, 0, 1, 4)

        layout_params.addLayout(grid)

        # ── 不规则合并模式行 ───────────────────────────────────────────────────
        irr_row = QHBoxLayout()
        irr_row.setSpacing(10)
        self.check_irregular = QCheckBox("🔀 不规则片段合并")
        self.check_irregular.setToolTip("开启后，合并数量和输出数量由自定义列表决定")
        irr_row.addWidget(self.check_irregular)
        self.btn_irregular_config = QPushButton("📋 点击配置列表")
        self.btn_irregular_config.setEnabled(False)
        irr_row.addWidget(self.btn_irregular_config)
        self.lbl_irregular_summary = QLabel("（未配置）")
        self.lbl_irregular_summary.setStyleSheet("color: #4b5563; font-size: 9pt;")
        irr_row.addWidget(self.lbl_irregular_summary, 1)
        layout_params.addLayout(irr_row)

        main_layout.addWidget(card_params)

        # ── 4. Output & action card ───────────────────────────────────────
        card_action, layout_action = self.create_card("💾 输出与执行")
        path_layout = QHBoxLayout()
        self.btn_out_path = QPushButton("选择输出目录")
        self.lbl_out_path = QLabel("默认: 未选择")
        self.lbl_out_path.setStyleSheet("color: #888;")
        path_layout.addWidget(self.btn_out_path)
        path_layout.addWidget(self.lbl_out_path)
        path_layout.addStretch()
        layout_action.addLayout(path_layout)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout_action.addWidget(self.progress_bar)

        self.lbl_status = QLabel("准备就绪...")
        layout_action.addWidget(self.lbl_status)

        action_btn_layout = QHBoxLayout()
        self.btn_start = QPushButton("🚀 批量生成视频")
        self.btn_start.setObjectName("PrimaryBtn")
        self.btn_stop = QPushButton("🛑 停止")
        self.btn_stop.setEnabled(False)
        self.btn_stop.setMinimumHeight(45)
        action_btn_layout.addWidget(self.btn_start, stretch=3)
        action_btn_layout.addWidget(self.btn_stop, stretch=1)
        layout_action.addLayout(action_btn_layout)

        main_layout.addWidget(card_action)
        main_layout.addStretch()


    # ── Event binding ──────────────────────────────────────────────────────

    def bind_events(self):
        # Image
        self.btn_add_files.clicked.connect(self.add_files)
        self.btn_add_folder.clicked.connect(self.add_folder)
        self.btn_clear.clicked.connect(self.file_list.clear)
        # Audio library
        self.btn_add_audio.clicked.connect(self._add_audio_files)
        self.btn_add_audio_folder.clicked.connect(self._add_audio_folder)
        self.btn_remove_audio.clicked.connect(self._remove_selected_audio)
        self.btn_clear_audio.clicked.connect(self._clear_audio_library)
        # Audio select bar
        self.audio_select_bar.clicked.connect(self._open_audio_select_dialog)
        # Params & action
        self.btn_out_path.clicked.connect(self.select_output_dir)
        self.btn_start.clicked.connect(self.start_merge)
        self.btn_stop.clicked.connect(self.stop_merge)
        self.check_effect.stateChanged.connect(
            lambda state: self.combo_effect.setEnabled(state == 2))
        self.check_irregular.stateChanged.connect(lambda _: self._toggle_irregular_mode())
        self.btn_irregular_config.clicked.connect(self._open_irregular_dialog)

    # ── 不规则合并模式 ────────────────────────────────────────────────────

    def _toggle_irregular_mode(self):
        is_irr = self.check_irregular.isChecked()
        self.spin_merge_count.setEnabled(not is_irr)
        self.spin_output_count.setEnabled(not is_irr)
        self.btn_irregular_config.setEnabled(is_irr)

    def _open_irregular_dialog(self):
        dlg = IrregularSegmentsDialog(self.irregular_segments, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.irregular_segments = dlg.get_segments()
            self._update_irregular_label()

    def _update_irregular_label(self):
        if self.irregular_segments:
            preview = ", ".join(str(s) for s in self.irregular_segments[:8])
            if len(self.irregular_segments) > 8:
                preview += "..."
            self.lbl_irregular_summary.setText(
                f"共{len(self.irregular_segments)}个视频 · {preview}")
            self.lbl_irregular_summary.setStyleSheet(
                "color: #f43f5e; font-size: 9pt; font-weight: bold;")
        else:
            self.lbl_irregular_summary.setText("（未配置）")
            self.lbl_irregular_summary.setStyleSheet("color: #4b5563; font-size: 9pt;")

    # ── Image file handling ────────────────────────────────────────────────

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "选择图片", "", "Images (*.png *.jpg *.jpeg *.webp)")
        for f in files:
            self.file_list.addItem(f)

    def add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if folder:
            for root, _, files in os.walk(folder):
                for file in files:
                    if file.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                        self.file_list.addItem(os.path.join(root, file))

    # ── Audio library management ───────────────────────────────────────────

    def _add_audio_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择音频文件", "",
            "Audio Files (*.mp3 *.wav *.aac *.ogg)")
        added = 0
        for f in files:
            if self.audio_library.add(f):
                added += 1
        if added > 0:
            self._refresh_audio_library_list()
            self.lbl_status.setText(f"已添加 {added} 个音频到音频库。")

    def _add_audio_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if not folder:
            return
        added = 0
        for root, _, files in os.walk(folder):
            for file in files:
                if file.lower().endswith(SUPPORTED_AUDIO_EXT):
                    if self.audio_library.add(os.path.join(root, file)):
                        added += 1
        if added > 0:
            self._refresh_audio_library_list()
            self.lbl_status.setText(f"已从文件夹添加 {added} 个音频到音频库。")

    def _remove_selected_audio(self):
        selected_items = self.audio_lib_list.selectedItems()
        if not selected_items:
            return
        for item in selected_items:
            path = item.data(Qt.ItemDataRole.UserRole)
            self.audio_library.remove(path)
            # Also remove from selected_audios if present
            if path in self.selected_audios:
                self.selected_audios.remove(path)
        self._refresh_audio_library_list()
        self._update_audio_select_bar()

    def _clear_audio_library(self):
        reply = QMessageBox.question(
            self, "确认清空",
            "确定要清空整个音频库吗？\n（已选择的音频也会被取消）",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.audio_library.clear()
            self.selected_audios.clear()
            self._refresh_audio_library_list()
            self._update_audio_select_bar()

    def _refresh_audio_library_list(self):
        """Rebuild the audio library QListWidget from the library data."""
        self.audio_lib_list.clear()
        for entry in self.audio_library.get_all():
            item = QListWidgetItem(f"🎵  {entry['name']}   |   {entry['path']}")
            item.setData(Qt.ItemDataRole.UserRole, entry['path'])
            self.audio_lib_list.addItem(item)

    # ── Audio selection dialog ─────────────────────────────────────────────

    def _open_audio_select_dialog(self):
        if not self.audio_library.get_all():
            QMessageBox.information(self, "音频库为空", "请先在「音频素材入库」区域添加音频文件。")
            return
        dlg = AudioSelectDialog(self.audio_library, self.selected_audios, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.selected_audios = dlg.get_selected_paths()
            self._update_audio_select_bar()

    def _update_audio_select_bar(self):
        """Refresh the compact selected-audio display bar."""
        if not self.selected_audios:
            self.audio_select_label.setText("未选择背景音乐 — 点击此处打开选择器")
            self.audio_select_label.setStyleSheet("color: #4b5563; font-size: 10pt;")
        else:
            n = len(self.selected_audios)
            text = f"🎵  已选 {n} 首背景音乐 — 点击修改"
            self.audio_select_label.setText(text)
            self.audio_select_label.setStyleSheet("color: #f43f5e; font-size: 10pt; font-weight: bold;")

    # ── Audio-per-task distribution ────────────────────────────────────────

    def _get_audio_for_tasks(self, num_tasks: int) -> list:
        """Return a list of audio_path (or None) for each output video."""
        audios = self.selected_audios
        mode = self.combo_audio_mode.currentText()

        if not audios:
            return [None] * num_tasks

        result = []
        n = len(audios)
        for i in range(num_tasks):
            if mode == "随机分配":
                result.append(random.choice(audios))
            elif mode == "按顺序补全":
                result.append(audios[i % n])
            elif mode == "按顺序不补全":
                result.append(audios[i] if i < n else None)
            else:
                result.append(random.choice(audios))
        return result

    # ── Output directory ───────────────────────────────────────────────────

    def select_output_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "选择基础输出文件夹")
        if dir_path:
            self.base_dir = dir_path
            self.lbl_out_path.setText(f"已选择: {self.base_dir}")

    # ── Main merge logic ───────────────────────────────────────────────────

    def start_merge(self):
        try:
            self._start_merge_impl()
        except Exception as exc:
            import traceback
            QMessageBox.critical(self, "錯误",
                f"开始生成时发生错误，请拍照以下错误内容反馈：\n\n{traceback.format_exc()}")

    def _start_merge_impl(self):
        if self.file_list.count() == 0 or not self.base_dir:
            QMessageBox.warning(self, "警告", "请先上传图片并选择输出路径！")
            return

        prefix = datetime.now().strftime("%Y%m%d")
        self.output_dir = os.path.join(self.base_dir, f"图片合成视频_{prefix}")

        try:
            os.makedirs(self.output_dir, exist_ok=True)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法创建输出文件夹，请检查是否被拦截！\n{str(e)}")
            return

        # Resolve ffmpeg: frozen → next to .exe; dev → project root via __file__
        if getattr(sys, 'frozen', False):
            _root = os.path.dirname(sys.executable)
        else:
            _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ffmpeg_exe = os.path.join(_root, "ffmpeg", "ffmpeg.exe")
        if not os.path.exists(ffmpeg_exe):
            QMessageBox.critical(self, "错误", f"找不到 ffmpeg.exe！\n期望路径：{ffmpeg_exe}")
            return

        all_images = [self.file_list.item(i).text() for i in range(self.file_list.count())]
        self.image_manager.clear()
        self.image_manager.add_items(all_images)

        merge_count = self.spin_merge_count.value()
        output_count = self.spin_output_count.value()
        merge_mode = self.combo_order.currentText()

        # \u4e0d\u89c4\u5219\u6a21\u5f0f\uff1a\u4f7f\u7528\u81ea\u5b9a\u4e49\u7247\u6bb5\u6570\u5217\u8868
        if self.check_irregular.isChecked():
            if not self.irregular_segments:
                QMessageBox.warning(self, "\u8b66\u544a", "\u4e0d\u89c4\u5219\u6a21\u5f0f\u5df2\u5f00\u542f\uff0c\u4f46\u672a\u914d\u7f6e\u7247\u6bb5\u5217\u8868\uff0c\u8bf7\u5148\u70b9\u51fb\u300c\u70b9\u51fb\u914d\u7f6e\u5217\u8868\u300d\u8f93\u5165\u6570\u636e\u3002")
                return
            segment_list = self.irregular_segments
        else:
            segment_list = [merge_count] * output_count

        tasks = []
        current_seq = 1
        for count in segment_list:
            task_images = self.image_manager.get_items_for_merge(count, mode=merge_mode)
            if not task_images:
                break
            while True:
                raw_path = os.path.join(self.output_dir, f"{prefix}_{current_seq:03d}.mp4")
                output_file = os.path.normpath(raw_path)
                if not os.path.exists(output_file):
                    break
                current_seq += 1
            tasks.append({"images": task_images, "output_file": output_file})
            current_seq += 1

        if not tasks:
            return

        # Assign audio + per-audio params to each task
        audio_assignments = self._get_audio_for_tasks(len(tasks))
        for task, audio_path in zip(tasks, audio_assignments):
            task["audio_path"] = audio_path
            if audio_path:
                params = self.audio_library.get_params_for_path(audio_path)
                task["audio_skip_start"] = params["skip_start"]
                task["audio_fade_in"]    = params["fade_in"]
            else:
                task["audio_skip_start"] = 0.0
                task["audio_fade_in"]    = 0.0

        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.progress_bar.setValue(0)

        selected_trans = self.combo_transition.currentText()
        enable_trans = selected_trans != "无转场（直接拼接）"
        # 从括号中提取 ffmpeg 转场名称，如 "淡入淡出 (fade)" → "fade"
        if enable_trans and "(" in selected_trans:
            trans_code = selected_trans.split("(")[-1].strip(")")
        else:
            trans_code = "fade"   # 无转场时该值不会被使用
        eff_code = self.combo_effect.currentText().split("(")[-1].strip(")")
        aspect_ratio = self.combo_aspect_ratio.currentText().split(" ")[0]
        resolution = self.combo_resolution.currentText().split(" ")[0]

        self.worker = ImageMergeWorker(
            tasks=tasks,
            duration=self.spin_duration.value(),
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            enable_trans=enable_trans,
            trans_name=trans_code,
            enable_eff=self.check_effect.isChecked(),
            eff_name=eff_code,
            ffmpeg_path=ffmpeg_exe,
            audio_loop=self.check_audio_loop.isChecked(),
            audio_volume=self.spin_audio_volume.value(),
        )
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.task_finished)
        self.worker.start()

    def stop_merge(self):
        if self.worker:
            self.worker.stop()

    def update_progress(self, percent, text):
        self.progress_bar.setValue(percent)
        self.lbl_status.setText(text)

    def task_finished(self, success, message):
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        if success:
            QMessageBox.information(self, "完成", message)
        else:
            QMessageBox.critical(self, "错误", message)

    # ── Drag-drop event filter ─────────────────────────────────────────────

    def eventFilter(self, source, event):
        # ── Image list ────────────────────────────────────────────────────
        if source is self.file_list:
            if event.type() in (QEvent.Type.DragEnter, QEvent.Type.DragMove):
                if event.mimeData().hasUrls():
                    event.accept()
                    return True
            elif event.type() == QEvent.Type.Drop:
                for url in event.mimeData().urls():
                    path = url.toLocalFile()
                    if path.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tif', '.tiff')):
                        self.file_list.addItem(path)
                event.accept()
                return True

        # ── Audio library list ────────────────────────────────────────────
        elif source is self.audio_lib_list:
            if event.type() in (QEvent.Type.DragEnter, QEvent.Type.DragMove):
                if event.mimeData().hasUrls():
                    event.accept()
                    return True
            elif event.type() == QEvent.Type.Drop:
                added = 0
                for url in event.mimeData().urls():
                    path = url.toLocalFile()
                    if os.path.isdir(path):
                        for root, _, files in os.walk(path):
                            for f in files:
                                if f.lower().endswith(SUPPORTED_AUDIO_EXT):
                                    if self.audio_library.add(os.path.join(root, f)):
                                        added += 1
                    elif path.lower().endswith(SUPPORTED_AUDIO_EXT):
                        if self.audio_library.add(path):
                            added += 1
                if added > 0:
                    self._refresh_audio_library_list()
                    self.lbl_status.setText(f"已添加 {added} 个音频到音频库。")
                event.accept()
                return True

        return bool(super().eventFilter(source, event))