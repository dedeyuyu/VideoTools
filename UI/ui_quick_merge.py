# -*- coding: utf-8 -*-
"""
ui_quick_merge.py — 快速合并界面

功能特点：
1. 支持选择 1 ~ 5 个视频板块：
   - 1 个板块（单板块模式）：将所有视频一股脑拖入同一个板块，按名称相似度（可设阈值 %）
     或文件名开头数字自动归类成组，同组视频合并到一起，未匹配的单独输出。
   - 2 ~ 5 个板块（多板块模式）：跨板块按相似度、开头数字或列表顺序配对合并。
2. 支持选择合并顺序：「按顺序合并」或「随机顺序合并」。
3. 支持设置「输出数量」（每组输出几份）：
   - 设为 1 时正常输出 1 轮；
   - 设为 2（或更多）时，第一组合并完后会对多段匹配组再进行第二组（及更多组）合并；
     若选择了「随机顺序合并」，每一轮合并都会重新随机打乱顺序，确保每组顺序不同。
4. 支持保留原声 / 去除声音（含单板块独立静音）、播放倍速、转场效果与转场时长、
   多种画面尺寸比例（9:16、16:9、3:4、4:3、4:5、1:1、19:6）。
5. 输出文件名自动保留主视频的原始命名（多轮输出自动追加 _2、_3 防止覆盖）。
"""
import os
import sys
import json
from PyQt6.QtCore import Qt, QSize, QSettings, QUrl, pyqtSignal
from PyQt6.QtGui import QIcon, QColor, QDesktopServices, QShortcut, QKeySequence
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFrame, QLabel,
    QPushButton, QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox,
    QSlider, QListWidget, QListWidgetItem, QFileDialog, QMessageBox,
    QProgressBar, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QScrollArea, QLineEdit, QButtonGroup, QRadioButton,
)

from image_worker.quick_merge_worker import (
    TRANSITION_OPTIONS,
    ASPECT_OPTIONS,
    FIT_OPTIONS,
    match_video_groups,
    QuickMergeWorker,
)
from UI.ui_ffmpeg_downloader_mgr import get_ffmpeg_status, FFmpegDownloaderDialog

VIDEO_EXTS = ("mp4", "mov", "mkv", "avi", "webm", "flv", "m4v", "ts")


def _theme_icon(name: str) -> str:
    if hasattr(sys, "_MEIPASS"):
        p = os.path.join(sys._MEIPASS, "theme_icons", name)
        if os.path.isfile(p):
            return p
    if getattr(sys, "frozen", False):
        p = os.path.join(os.path.dirname(sys.executable), "theme_icons", name)
        if os.path.isfile(p):
            return p
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "theme_icons", name)


class VideoSlotListWidget(QListWidget):
    """支持拖拽文件/文件夹导入、内部拖拽排序的视频列表控件。"""
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setMinimumHeight(185)
        self.model().rowsMoved.connect(lambda *a: self._on_structure_changed())

        del_sc = QShortcut(QKeySequence(Qt.Key.Key_Delete), self)
        del_sc.setContext(Qt.ShortcutContext.WidgetShortcut)
        del_sc.activated.connect(self.remove_selected)

    def _on_structure_changed(self):
        self._renumber()
        self.changed.emit()

    def add_files(self, paths):
        existing = set(os.path.normcase(p) for p in self.paths())
        added = False
        for p in paths:
            if not p or not os.path.isfile(p):
                continue
            ext = os.path.splitext(p)[1].lower().lstrip(".")
            if ext in VIDEO_EXTS:
                norm = os.path.normcase(p)
                if norm not in existing:
                    existing.add(norm)
                    it = QListWidgetItem(os.path.basename(p))
                    it.setData(Qt.ItemDataRole.UserRole, p)
                    it.setToolTip(p)
                    self.addItem(it)
                    added = True
        if added:
            self._renumber()
            self.changed.emit()

    def _renumber(self):
        for i in range(self.count()):
            it = self.item(i)
            p = it.data(Qt.ItemDataRole.UserRole)
            it.setText(f"{i + 1:02d}.  {os.path.basename(p)}")

    def paths(self) -> list[str]:
        return [self.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.count())]

    def move_selected(self, delta: int):
        row = self.currentRow()
        new_row = row + delta
        if row < 0 or new_row < 0 or new_row >= self.count():
            return
        it = self.takeItem(row)
        self.insertItem(new_row, it)
        self.setCurrentRow(new_row)
        self._renumber()
        self.changed.emit()

    def remove_selected(self):
        items = self.selectedItems()
        if not items:
            return
        for it in items:
            self.takeItem(self.row(it))
        self._renumber()
        self.changed.emit()

    def clear_all(self):
        if self.count() == 0:
            return
        self.clear()
        self.changed.emit()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() or e.source() == self:
            e.accept()
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls() or e.source() == self:
            e.accept()
        else:
            e.ignore()

    def dropEvent(self, e):
        if e.source() == self:
            super().dropEvent(e)
            self._renumber()
            self.changed.emit()
            return
        if e.mimeData().hasUrls():
            collected = []
            for url in e.mimeData().urls():
                local = url.toLocalFile()
                if os.path.isdir(local):
                    for fn in sorted(os.listdir(local)):
                        collected.append(os.path.join(local, fn))
                elif os.path.isfile(local):
                    collected.append(local)
            self.add_files(collected)
            e.accept()


class QuickMergeUI(QWidget):
    """⚡ 快速合并 主界面"""

    MAX_SLOTS = 5

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = QSettings("MyCompany", "VideoToolbox")
        self.slot_lists: list[VideoSlotListWidget] = []
        self.slot_cards: list[QFrame] = []
        self.slot_title_labels: list[QLabel] = []
        self.slot_mute_checks: list[QCheckBox] = []
        self.matched_groups: list[dict] = []
        self._worker: QuickMergeWorker | None = None
        self._loading = False

        self._init_ui()
        self._load_settings()
        self._refresh_slot_visibility()
        self._recompute_matches()

    def _make_card(self, title: str = ""):
        card = QFrame()
        card.setProperty("class", "Card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)
        lbl = None
        if title:
            lbl = QLabel(title)
            lbl.setProperty("class", "CardTitle")
            lay.addWidget(lbl)
        return card, lay, lbl

    def _init_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.viewport().setAutoFillBackground(False)
        outer.addWidget(scroll)

        container = QWidget()
        container.setAutoFillBackground(False)
        scroll.setWidget(container)
        root = QVBoxLayout(container)
        root.setContentsMargins(6, 4, 10, 12)
        root.setSpacing(10)

        # ── 顶部标题栏 ────────────────────────────────────────────────────
        header_row = QHBoxLayout()
        title_lbl = QLabel("⚡ 快速合并")
        title_lbl.setStyleSheet("font-size: 20px; font-weight: bold; color: #3182CE;")
        header_row.addWidget(title_lbl)
        header_row.addSpacing(12)
        sub_lbl = QLabel("支持单板块自动归类合并或 2~5 板块配对合并，可选顺序/随机合并与多组循环输出")
        sub_lbl.setStyleSheet("color: #718096; font-size: 9.5pt;")
        header_row.addWidget(sub_lbl, 1)
        root.addLayout(header_row)

        # ── 卡片 1：板块模式、匹配规则与视频列表 ──────────────────────────
        top_card, top_lay, _ = self._make_card()

        # 第一行：板块数量 + 匹配方式 + 相似度阈值
        ctrl_row1 = QHBoxLayout()
        ctrl_row1.setSpacing(10)
        ctrl_row1.addWidget(QLabel("🧩 视频板块数量:"))
        self.cmb_slot_count = QComboBox()
        self.cmb_slot_count.addItem("1 个板块（单板块自动归类合并）", 1)
        for n in (2, 3, 4, 5):
            self.cmb_slot_count.addItem(f"{n} 个板块（视频1 ~ 视频{n}）", n)
        self.cmb_slot_count.setMinimumWidth(210)
        self.cmb_slot_count.currentIndexChanged.connect(self._on_slot_count_changed)
        ctrl_row1.addWidget(self.cmb_slot_count)

        ctrl_row1.addSpacing(8)
        ctrl_row1.addWidget(QLabel("🔗 匹配方式:"))
        self.cmb_match_mode = QComboBox()
        self.cmb_match_mode.addItem("按名称相似度匹配", "similarity")
        self.cmb_match_mode.addItem("按文件名开头数字匹配", "number")
        self.cmb_match_mode.addItem("按列表顺序依次匹配", "order")
        self.cmb_match_mode.setMinimumWidth(165)
        self.cmb_match_mode.currentIndexChanged.connect(self._on_match_mode_changed)
        ctrl_row1.addWidget(self.cmb_match_mode)

        # 相似度阈值控件组（仅在“按名称相似度匹配”时显示）
        self.sim_widget = QWidget()
        sim_lay = QHBoxLayout(self.sim_widget)
        sim_lay.setContentsMargins(4, 0, 4, 0)
        sim_lay.setSpacing(6)
        sim_lay.addWidget(QLabel("相似度阈值 ≥"))
        self.slider_sim = QSlider(Qt.Orientation.Horizontal)
        self.slider_sim.setRange(10, 100)
        self.slider_sim.setValue(60)
        self.slider_sim.setFixedWidth(105)
        self.spin_sim = QSpinBox()
        self.spin_sim.setRange(10, 100)
        self.spin_sim.setValue(60)
        self.spin_sim.setSuffix(" %")
        self.spin_sim.setFixedWidth(70)
        self.slider_sim.valueChanged.connect(self.spin_sim.setValue)
        self.spin_sim.valueChanged.connect(self.slider_sim.setValue)
        self.spin_sim.valueChanged.connect(self._on_params_changed)
        sim_lay.addWidget(self.slider_sim)
        sim_lay.addWidget(self.spin_sim)
        ctrl_row1.addWidget(self.sim_widget)

        ctrl_row1.addStretch()
        btn_clear_all = QPushButton("🗑️ 清空全部板块")
        btn_clear_all.clicked.connect(self._clear_all_slots)
        ctrl_row1.addWidget(btn_clear_all)
        top_lay.addLayout(ctrl_row1)

        # 第二行：合并顺序（按顺序 / 随机） + 输出数量（每组输出几轮） + 未匹配策略
        ctrl_row2 = QHBoxLayout()
        ctrl_row2.setSpacing(10)
        ctrl_row2.addWidget(QLabel("🔀 合并顺序:"))
        self.cmb_merge_order = QComboBox()
        self.cmb_merge_order.addItem("按顺序合并", "sequential")
        self.cmb_merge_order.addItem("随机顺序合并", "random")
        self.cmb_merge_order.setMinimumWidth(140)
        self.cmb_merge_order.setToolTip(
            "按顺序合并：同一组匹配到的视频按列表先后顺序依次拼接\n"
            "随机顺序合并：同一组匹配到的视频在合并时随机打乱顺序拼接"
        )
        self.cmb_merge_order.currentIndexChanged.connect(self._on_merge_order_changed)
        ctrl_row2.addWidget(self.cmb_merge_order)

        self.btn_reshuffle = QPushButton("🎲 重新随机排序")
        self.btn_reshuffle.setToolTip("重新随机生成每组视频的拼接顺序")
        self.btn_reshuffle.clicked.connect(self._recompute_matches)
        self.btn_reshuffle.setVisible(False)
        ctrl_row2.addWidget(self.btn_reshuffle)

        ctrl_row2.addSpacing(12)
        ctrl_row2.addWidget(QLabel("🔢 输出数量:"))
        self.spin_output_count = QSpinBox()
        self.spin_output_count.setRange(1, 50)
        self.spin_output_count.setValue(1)
        self.spin_output_count.setSuffix(" 组")
        self.spin_output_count.setFixedWidth(80)
        self.spin_output_count.setToolTip(
            "设置每组匹配视频输出几个成品：\n"
            "• 设为 1：正常输出 1 轮（包括多段合并组与未匹配单段视频）\n"
            "• 设为 2 或更多：第一组合并完后，所有多段匹配组会继续进行第二组（及更多组）合并；\n"
            "  若选择了「随机顺序合并」，第二组会重新随机打乱顺序后再合并！"
        )
        self.spin_output_count.valueChanged.connect(self._on_params_changed)
        ctrl_row2.addWidget(self.spin_output_count)

        self.lbl_output_count_hint = QLabel("（设为 2+ 时，匹配组完成第 1 轮后会自动重新随机/顺序合并第 2 轮）")
        self.lbl_output_count_hint.setStyleSheet("color: #718096; font-size: 9pt;")
        ctrl_row2.addWidget(self.lbl_output_count_hint)

        self.chk_other_unmatched = QCheckBox("其他板块未匹配视频也单独输出")
        self.chk_other_unmatched.setToolTip(
            "默认以「视频 1」为基准输出（视频 1 中未匹配到的视频会单独输出）。\n"
            "勾选后，视频 2~5 中未被匹配到的多余视频也会各自单独输出。"
        )
        self.chk_other_unmatched.toggled.connect(self._on_params_changed)
        ctrl_row2.addWidget(self.chk_other_unmatched)

        ctrl_row2.addStretch()
        top_lay.addLayout(ctrl_row2)

        # 1 ~ 5 个视频板块横向并排
        slots_row = QHBoxLayout()
        slots_row.setSpacing(10)
        for idx in range(self.MAX_SLOTS):
            lw, card, lbl_title, chk_mute = self._build_slot_card(idx)
            self.slot_lists.append(lw)
            self.slot_cards.append(card)
            self.slot_title_labels.append(lbl_title)
            self.slot_mute_checks.append(chk_mute)
            slots_row.addWidget(card, 1)
        top_lay.addLayout(slots_row)
        root.addWidget(top_card)

        # ── 卡片 2：匹配结果实时预览表 ────────────────────────────────────
        preview_card, preview_lay, _ = self._make_card()
        prev_hdr = QHBoxLayout()
        lbl_prev_title = QLabel("📋 匹配与拼接顺序预览")
        lbl_prev_title.setProperty("class", "CardTitle")
        prev_hdr.addWidget(lbl_prev_title)
        self.lbl_match_summary = QLabel("")
        self.lbl_match_summary.setStyleSheet("color: #38A169; font-weight: bold;")
        prev_hdr.addWidget(self.lbl_match_summary, 1)
        preview_lay.addLayout(prev_hdr)

        self.table_preview = QTableWidget(0, 5)
        self.table_preview.setHorizontalHeaderLabels([
            "#", "匹配依据", "拼接顺序（播放完前一段紧接着播放下一段）", "输出文件名（保留原命名）", "状态"
        ])
        hdr = self.table_preview.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.table_preview.setColumnWidth(0, 44)
        self.table_preview.setColumnWidth(4, 90)
        self.table_preview.setMinimumHeight(145)
        self.table_preview.setMaximumHeight(210)
        self.table_preview.setAlternatingRowColors(True)
        self.table_preview.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_preview.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_preview.verticalHeader().setVisible(False)
        preview_lay.addWidget(self.table_preview)
        root.addWidget(preview_card)

        # ── 卡片 3：合成参数设置（声音 / 倍速 / 转场 / 尺寸）──────────────
        param_card, param_lay, _ = self._make_card("⚙️ 合并参数设置")
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(12)
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 0)
        grid.setColumnStretch(3, 1)

        # Row 0: 声音设置 & 画面尺寸
        grid.addWidget(QLabel("🔊 原视频声音:"), 0, 0)
        audio_box = QHBoxLayout()
        audio_box.setContentsMargins(0, 0, 0, 0)
        self.rb_keep_audio = QRadioButton("保留原视频声音")
        self.rb_mute_audio = QRadioButton("去掉声音（全部静音）")
        self.rb_keep_audio.setChecked(True)
        self.audio_btn_group = QButtonGroup(self)
        self.audio_btn_group.addButton(self.rb_keep_audio, 0)
        self.audio_btn_group.addButton(self.rb_mute_audio, 1)
        self.rb_keep_audio.toggled.connect(self._on_params_changed)
        audio_box.addWidget(self.rb_keep_audio)
        audio_box.addWidget(self.rb_mute_audio)
        audio_box.addStretch()
        grid.addLayout(audio_box, 0, 1)

        grid.addWidget(QLabel("📐 视频尺寸比例:"), 0, 2)
        size_box = QHBoxLayout()
        size_box.setContentsMargins(0, 0, 0, 0)
        self.cmb_aspect = QComboBox()
        for label, val in ASPECT_OPTIONS:
            self.cmb_aspect.addItem(label, val)
        self.cmb_aspect.setMinimumWidth(180)
        self.cmb_aspect.currentIndexChanged.connect(self._on_params_changed)
        size_box.addWidget(self.cmb_aspect)

        size_box.addSpacing(8)
        size_box.addWidget(QLabel("填充:"))
        self.cmb_fit = QComboBox()
        for label, val in FIT_OPTIONS:
            self.cmb_fit.addItem(label, val)
        self.cmb_fit.currentIndexChanged.connect(self._on_params_changed)
        size_box.addWidget(self.cmb_fit, 1)
        grid.addLayout(size_box, 0, 3)

        # Row 1: 播放倍速 & 转场设置
        grid.addWidget(QLabel("⏩ 播放倍速:"), 1, 0)
        speed_box = QHBoxLayout()
        speed_box.setContentsMargins(0, 0, 0, 0)
        speed_box.setSpacing(6)
        self.slider_speed = QSlider(Qt.Orientation.Horizontal)
        self.slider_speed.setRange(25, 300)
        self.slider_speed.setValue(100)
        self.spin_speed = QDoubleSpinBox()
        self.spin_speed.setRange(0.25, 4.0)
        self.spin_speed.setSingleStep(0.05)
        self.spin_speed.setDecimals(2)
        self.spin_speed.setValue(1.00)
        self.spin_speed.setSuffix(" x")
        self.spin_speed.setFixedWidth(82)
        self.slider_speed.valueChanged.connect(lambda v: self.spin_speed.setValue(round(v / 100.0, 2)))
        self.spin_speed.valueChanged.connect(lambda v: self.slider_speed.setValue(int(round(v * 100))))
        self.spin_speed.valueChanged.connect(self._on_params_changed)
        speed_box.addWidget(self.slider_speed, 1)
        speed_box.addWidget(self.spin_speed)
        for spd in (1.0, 1.25, 1.5, 2.0):
            b_spd = QPushButton(f"{spd:g}x")
            b_spd.setFixedWidth(44)
            b_spd.clicked.connect(lambda _, s=spd: self.spin_speed.setValue(s))
            speed_box.addWidget(b_spd)
        grid.addLayout(speed_box, 1, 1)

        grid.addWidget(QLabel("✨ 转场效果:"), 1, 2)
        trans_box = QHBoxLayout()
        trans_box.setContentsMargins(0, 0, 0, 0)
        trans_box.setSpacing(8)
        self.cmb_transition = QComboBox()
        for label, val in TRANSITION_OPTIONS:
            self.cmb_transition.addItem(label, val)
        self.cmb_transition.setMinimumWidth(180)
        self.cmb_transition.currentIndexChanged.connect(self._on_transition_changed)
        trans_box.addWidget(self.cmb_transition, 1)

        self.lbl_trans_dur = QLabel("时长:")
        trans_box.addWidget(self.lbl_trans_dur)
        self.spin_trans_dur = QDoubleSpinBox()
        self.spin_trans_dur.setRange(0.2, 3.0)
        self.spin_trans_dur.setSingleStep(0.1)
        self.spin_trans_dur.setDecimals(1)
        self.spin_trans_dur.setValue(0.6)
        self.spin_trans_dur.setSuffix(" 秒")
        self.spin_trans_dur.setFixedWidth(78)
        self.spin_trans_dur.valueChanged.connect(self._on_params_changed)
        trans_box.addWidget(self.spin_trans_dur)
        grid.addLayout(trans_box, 1, 3)

        param_lay.addLayout(grid)
        root.addWidget(param_card)

        # ── 卡片 4：输出位置与开始合并 ────────────────────────────────────
        out_card, out_lay, _ = self._make_card("📂 输出与执行")
        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("输出目录:"))
        default_out = os.path.join(os.path.expanduser("~"), "Desktop", "快速合并输出")
        self.txt_output_dir = QLineEdit(default_out)
        out_row.addWidget(self.txt_output_dir, 1)

        btn_pick_out = QPushButton("📁 选择文件夹")
        btn_pick_out.clicked.connect(self._choose_output_dir)
        out_row.addWidget(btn_pick_out)

        btn_open_out = QPushButton("📂 打开输出目录")
        btn_open_out.clicked.connect(self._open_output_dir)
        out_row.addWidget(btn_open_out)
        out_lay.addLayout(out_row)

        run_row = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("准备就绪")
        self.progress_bar.setMinimumHeight(32)
        run_row.addWidget(self.progress_bar, 1)

        self.btn_start = QPushButton("🚀 开始快速合并")
        self.btn_start.setProperty("class", "PrimaryBtn")
        self.btn_start.setMinimumWidth(170)
        self.btn_start.setMinimumHeight(38)
        self.btn_start.clicked.connect(self._start_or_stop_merge)
        run_row.addWidget(self.btn_start)
        out_lay.addLayout(run_row)
        root.addWidget(out_card)

    def _build_slot_card(self, idx: int):
        card = QFrame()
        card.setProperty("class", "Card")
        v = QVBoxLayout(card)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(6)

        title_text = f"🎬 视频 {idx + 1}" + ("（主命名基准）" if idx == 0 else "")
        lbl_title = QLabel(title_text)
        lbl_title.setProperty("class", "CardTitle")
        v.addWidget(lbl_title)

        lw = VideoSlotListWidget()
        lw.setToolTip(f"可直接把视频文件或文件夹拖入「视频 {idx + 1}」列表，或上下拖动调整顺序")
        lw.changed.connect(self._on_slots_modified)
        v.addWidget(lw, 1)

        opt_row = QHBoxLayout()
        chk_mute = QCheckBox("静音此板块")
        chk_mute.setToolTip(f"单独将「视频 {idx + 1}」静音（不影响其他板块）")
        chk_mute.toggled.connect(self._on_params_changed)
        opt_row.addWidget(chk_mute)
        opt_row.addStretch()
        v.addLayout(opt_row)

        btns = QHBoxLayout()
        btns.setSpacing(4)

        def _ib(icon_name: str, tip: str, text: str = ""):
            b = QPushButton(text)
            ic_path = _theme_icon(icon_name)
            if os.path.isfile(ic_path):
                b.setIcon(QIcon(ic_path))
                b.setIconSize(QSize(15, 15))
            b.setToolTip(tip)
            if not text:
                b.setFixedWidth(32)
            return b

        b_add = _ib("add_video.svg", "导入视频文件", "导入")
        b_add.clicked.connect(lambda _, w=lw: self._import_files(w))
        b_dir = QPushButton("📁")
        b_dir.setFixedWidth(32)
        b_dir.setToolTip("导入整个文件夹中的视频")
        b_dir.clicked.connect(lambda _, w=lw: self._import_folder(w))
        b_up = _ib("arrow_up.svg", "上移选中视频")
        b_up.clicked.connect(lambda _, w=lw: w.move_selected(-1))
        b_dn = _ib("arrow_down.svg", "下移选中视频")
        b_dn.clicked.connect(lambda _, w=lw: w.move_selected(1))
        b_rm = _ib("remove.svg", "移除选中视频")
        b_rm.clicked.connect(lw.remove_selected)
        b_clr = _ib("clear.svg", "清空当前板块")
        b_clr.clicked.connect(lw.clear_all)

        for b in (b_add, b_dir, b_up, b_dn, b_rm, b_clr):
            btns.addWidget(b)
        v.addLayout(btns)
        return lw, card, lbl_title, chk_mute

    # ── 事件与状态更新 ────────────────────────────────────────────────────

    def _import_files(self, lw: VideoSlotListWidget):
        exts = " ".join(f"*.{e}" for e in VIDEO_EXTS)
        files, _ = QFileDialog.getOpenFileNames(self, "选择视频文件", "", f"视频文件 ({exts})")
        if files:
            lw.add_files(files)

    def _import_folder(self, lw: VideoSlotListWidget):
        folder = QFileDialog.getExistingDirectory(self, "选择包含视频的文件夹", "")
        if folder and os.path.isdir(folder):
            paths = [os.path.join(folder, fn) for fn in sorted(os.listdir(folder))]
            lw.add_files(paths)

    def _clear_all_slots(self):
        for lw in self.slot_lists:
            lw.clear()
        self._on_slots_modified()

    def _active_slot_count(self) -> int:
        return int(self.cmb_slot_count.currentData() or 2)

    def _on_slot_count_changed(self):
        cnt = self._active_slot_count()
        if cnt == 1 and self.cmb_match_mode.currentData() == "order":
            self.cmb_match_mode.setCurrentIndex(0)
        self._refresh_slot_visibility()
        self._recompute_matches()
        self.save_settings()

    def _on_match_mode_changed(self):
        mode = self.cmb_match_mode.currentData()
        if self._active_slot_count() == 1 and mode == "order":
            self.cmb_match_mode.blockSignals(True)
            self.cmb_match_mode.setCurrentIndex(0)
            self.cmb_match_mode.blockSignals(False)
            mode = "similarity"
        self.sim_widget.setVisible(mode == "similarity")
        self._recompute_matches()
        self.save_settings()

    def _on_merge_order_changed(self):
        is_rand = (self.cmb_merge_order.currentData() == "random")
        self.btn_reshuffle.setVisible(is_rand)
        self._recompute_matches()
        self.save_settings()

    def _on_transition_changed(self):
        trans = self.cmb_transition.currentData()
        has_trans = trans != "none"
        self.lbl_trans_dur.setEnabled(has_trans)
        self.spin_trans_dur.setEnabled(has_trans)
        self._on_params_changed()

    def _on_slots_modified(self):
        self._update_slot_headers()
        self._recompute_matches()
        self.save_settings()

    def _on_params_changed(self, *args):
        if self._loading:
            return
        self._recompute_matches()
        self.save_settings()

    def _refresh_slot_visibility(self):
        cnt = self._active_slot_count()
        for i, card in enumerate(self.slot_cards):
            card.setVisible(i < cnt)
        self.chk_other_unmatched.setVisible(cnt > 1)
        self._update_slot_headers()

    def _update_slot_headers(self):
        cnt = self._active_slot_count()
        for i, lbl in enumerate(self.slot_title_labels):
            n = self.slot_lists[i].count()
            if cnt == 1 and i == 0:
                lbl.setText(f"🎬 全部视频列表（可直接拖入所有视频，自动按相似度/开头数字归类合并）  [{n} 个]")
            else:
                suffix = "（主命名基准）" if i == 0 else ""
                lbl.setText(f"🎬 视频 {i + 1}{suffix}  [{n} 个]")

    def _recompute_matches(self):
        if self._loading:
            return
        cnt = self._active_slot_count()
        active_lists = [self.slot_lists[i].paths() for i in range(cnt)]
        mode = self.cmb_match_mode.currentData() or "similarity"
        sim_thresh = self.spin_sim.value() / 100.0
        inc_other = self.chk_other_unmatched.isChecked()
        merge_order = self.cmb_merge_order.currentData() or "sequential"
        out_count = self.spin_output_count.value()

        self.matched_groups = match_video_groups(
            active_lists,
            match_mode=mode,
            similarity_threshold=sim_thresh,
            include_other_unmatched=inc_other,
            merge_order=merge_order,
            output_count=out_count,
        )

        self.table_preview.setRowCount(len(self.matched_groups))
        multi_cnt = 0
        single_cnt = 0
        for r, g in enumerate(self.matched_groups):
            if g["is_single"]:
                single_cnt += 1
            else:
                multi_cnt += 1
            if cnt == 1:
                chain_str = "  ➔  ".join(os.path.basename(p) for _, p in g["clips"])
            else:
                chain_str = "  ➔  ".join(
                    f"[视频{s + 1}] {os.path.basename(p)}" for s, p in g["clips"]
                )
            it_idx = QTableWidgetItem(str(r + 1))
            it_idx.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_info = QTableWidgetItem(g["match_info"])
            it_chain = QTableWidgetItem(chain_str)
            it_chain.setToolTip("\n".join(f"{idx + 1}. {p}" for idx, (_, p) in enumerate(g["clips"])))
            it_out = QTableWidgetItem(g["output_name"])
            it_status = QTableWidgetItem("待处理")
            it_status.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            if g["is_single"]:
                it_info.setForeground(QColor("#DD6B20"))
            else:
                it_info.setForeground(QColor("#38A169"))

            self.table_preview.setItem(r, 0, it_idx)
            self.table_preview.setItem(r, 1, it_info)
            self.table_preview.setItem(r, 2, it_chain)
            self.table_preview.setItem(r, 3, it_out)
            self.table_preview.setItem(r, 4, it_status)

        total = len(self.matched_groups)
        if total == 0:
            self.lbl_match_summary.setText("请将视频拖入上方视频板块")
            self.lbl_match_summary.setStyleSheet("color: #718096;")
        else:
            order_tag = "随机顺序" if merge_order == "random" else "按顺序"
            self.lbl_match_summary.setText(
                f"📊 共 {total} 个输出任务（{multi_cnt} 组多段{order_tag}合并，{single_cnt} 个未匹配单段输出）"
            )
            self.lbl_match_summary.setStyleSheet("color: #38A169; font-weight: bold;")

    def _choose_output_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录", self.txt_output_dir.text())
        if d:
            self.txt_output_dir.setText(d)
            self.save_settings()

    def _open_output_dir(self):
        d = self.txt_output_dir.text().strip()
        if d:
            os.makedirs(d, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(d))

    # ── 开始 / 停止合成 ───────────────────────────────────────────────────

    def _start_or_stop_merge(self):
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self.btn_start.setEnabled(False)
            self.btn_start.setText("正在停止...")
            return

        if not self.matched_groups:
            self._recompute_matches()
        if not self.matched_groups:
            QMessageBox.warning(self, "没有可合并的视频", "请先在视频板块中导入视频文件！")
            return

        ff_status = get_ffmpeg_status()
        if not ff_status["installed"]:
            reply = QMessageBox.question(
                self,
                "未检测到 FFmpeg",
                "快速合并需要 FFmpeg 组件，是否立即打开「下载必要组件」进行安装？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                dlg = FFmpegDownloaderDialog(self)
                dlg.exec()
            return

        out_dir = self.txt_output_dir.text().strip()
        if not out_dir:
            QMessageBox.warning(self, "未设置输出目录", "请先选择一个输出文件夹！")
            return

        cnt = self._active_slot_count()
        slot_mutes = {i: self.slot_mute_checks[i].isChecked() for i in range(cnt)}

        self._worker = QuickMergeWorker(
            groups=self.matched_groups,
            output_dir=out_dir,
            ffmpeg_path=ff_status["ffmpeg"],
            ffprobe_path=ff_status["ffprobe"],
            aspect_ratio=self.cmb_aspect.currentData() or "9:16",
            fit_mode=self.cmb_fit.currentData() or "pad",
            speed=self.spin_speed.value(),
            mute_global=self.rb_mute_audio.isChecked(),
            slot_mutes=slot_mutes,
            transition=self.cmb_transition.currentData() or "none",
            transition_dur=self.spin_trans_dur.value(),
            parent=self,
        )
        self._worker.progress.connect(self._on_worker_progress)
        self._worker.task_status.connect(self._on_worker_task_status)
        self._worker.finished.connect(self._on_worker_finished)

        self.btn_start.setText("⏹ 停止合并")
        self.progress_bar.setValue(0)
        self._worker.start()

    def _on_worker_progress(self, pct: int, msg: str):
        self.progress_bar.setValue(pct)
        self.progress_bar.setFormat(f"{msg} (%p%)")

    def _on_worker_task_status(self, row: int, status_text: str):
        if 0 <= row < self.table_preview.rowCount():
            it = self.table_preview.item(row, 4)
            if it:
                it.setText(status_text)

    def _on_worker_finished(self, ok: bool, msg: str):
        self.btn_start.setEnabled(True)
        self.btn_start.setText("🚀 开始快速合并")
        if ok:
            self.progress_bar.setValue(100)
            self.progress_bar.setFormat("✅ 全部合并完成")
            QMessageBox.information(self, "合并完成", msg)
        else:
            self.progress_bar.setFormat("⚠️ 已中断")
            QMessageBox.warning(self, "合并未完成", msg)

    # ── 设置持久化 ────────────────────────────────────────────────────────

    def _load_settings(self):
        self._loading = True
        try:
            slot_cnt = self.settings.value("qm_slot_count", 1, type=int)
            idx_cnt = self.cmb_slot_count.findData(slot_cnt)
            if idx_cnt >= 0:
                self.cmb_slot_count.setCurrentIndex(idx_cnt)

            mode = self.settings.value("qm_match_mode", "similarity")
            idx_mode = self.cmb_match_mode.findData(mode)
            if idx_mode >= 0:
                self.cmb_match_mode.setCurrentIndex(idx_mode)
            self.sim_widget.setVisible((self.cmb_match_mode.currentData() or "similarity") == "similarity")

            sim_val = self.settings.value("qm_sim_threshold", 60, type=int)
            self.spin_sim.setValue(sim_val)
            self.slider_sim.setValue(sim_val)

            merge_order = self.settings.value("qm_merge_order", "sequential")
            idx_ord = self.cmb_merge_order.findData(merge_order)
            if idx_ord >= 0:
                self.cmb_merge_order.setCurrentIndex(idx_ord)
            self.btn_reshuffle.setVisible(merge_order == "random")

            out_cnt = self.settings.value("qm_output_count", 1, type=int)
            self.spin_output_count.setValue(max(1, out_cnt))

            self.chk_other_unmatched.setChecked(
                self.settings.value("qm_other_unmatched", False, type=bool)
            )

            mute_all = self.settings.value("qm_mute_global", False, type=bool)
            self.rb_mute_audio.setChecked(mute_all)
            self.rb_keep_audio.setChecked(not mute_all)

            aspect = self.settings.value("qm_aspect_ratio", "9:16")
            idx_asp = self.cmb_aspect.findData(aspect)
            if idx_asp >= 0:
                self.cmb_aspect.setCurrentIndex(idx_asp)

            fit = self.settings.value("qm_fit_mode", "pad")
            idx_fit = self.cmb_fit.findData(fit)
            if idx_fit >= 0:
                self.cmb_fit.setCurrentIndex(idx_fit)

            spd = self.settings.value("qm_speed", 1.0, type=float)
            self.spin_speed.setValue(spd)
            self.slider_speed.setValue(int(round(spd * 100)))

            trans = self.settings.value("qm_transition", "none")
            idx_tr = self.cmb_transition.findData(trans)
            if idx_tr >= 0:
                self.cmb_transition.setCurrentIndex(idx_tr)
            has_trans = (self.cmb_transition.currentData() or "none") != "none"
            self.lbl_trans_dur.setEnabled(has_trans)
            self.spin_trans_dur.setEnabled(has_trans)

            trans_dur = self.settings.value("qm_transition_dur", 0.6, type=float)
            self.spin_trans_dur.setValue(trans_dur)

            saved_out = self.settings.value("qm_output_dir", "")
            if saved_out:
                self.txt_output_dir.setText(saved_out)

            raw_slots = self.settings.value("qm_slot_files", "[]")
            slot_files = json.loads(raw_slots) if raw_slots else []
            for i in range(min(len(slot_files), self.MAX_SLOTS)):
                valid = [p for p in (slot_files[i] or []) if os.path.isfile(p)]
                self.slot_lists[i].add_files(valid)

            raw_mutes = self.settings.value("qm_slot_mutes", "[]")
            slot_mutes = json.loads(raw_mutes) if raw_mutes else []
            for i in range(min(len(slot_mutes), self.MAX_SLOTS)):
                self.slot_mute_checks[i].setChecked(bool(slot_mutes[i]))
        except Exception:
            pass
        finally:
            self._loading = False

    def save_settings(self):
        if self._loading:
            return
        self.settings.setValue("qm_slot_count", self._active_slot_count())
        self.settings.setValue("qm_match_mode", self.cmb_match_mode.currentData())
        self.settings.setValue("qm_sim_threshold", self.spin_sim.value())
        self.settings.setValue("qm_merge_order", self.cmb_merge_order.currentData())
        self.settings.setValue("qm_output_count", self.spin_output_count.value())
        self.settings.setValue("qm_other_unmatched", self.chk_other_unmatched.isChecked())
        self.settings.setValue("qm_mute_global", self.rb_mute_audio.isChecked())
        self.settings.setValue("qm_aspect_ratio", self.cmb_aspect.currentData())
        self.settings.setValue("qm_fit_mode", self.cmb_fit.currentData())
        self.settings.setValue("qm_speed", self.spin_speed.value())
        self.settings.setValue("qm_transition", self.cmb_transition.currentData())
        self.settings.setValue("qm_transition_dur", self.spin_trans_dur.value())
        self.settings.setValue("qm_output_dir", self.txt_output_dir.text().strip())
        self.settings.setValue(
            "qm_slot_files",
            json.dumps([lw.paths() for lw in self.slot_lists], ensure_ascii=False),
        )
        self.settings.setValue(
            "qm_slot_mutes",
            json.dumps([chk.isChecked() for chk in self.slot_mute_checks]),
        )
