import os
import sys
import random
from datetime import datetime
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
                             QPushButton, QLabel, QSpinBox, QComboBox,
                             QCheckBox, QDoubleSpinBox, QFileDialog, QListWidget,
                             QListWidgetItem, QProgressBar, QMessageBox, QFrame,
                             QSlider, QAbstractSpinBox, QDialog, QScrollArea,
                             QSizePolicy, QInputDialog)
from PyQt6.QtCore import Qt, QEvent, QSettings

from Video.video_manager import VideoManager
from image_worker.ffmpeg_worker import FFmpegWorker
from image_worker.audio_library import AudioLibrary, SUPPORTED_AUDIO_EXT
from UI.ui_image_merger import AudioSelectDialog, ClickableFrame, IrregularSegmentsDialog, LoopModeDialog

class VideoMergerUI(QWidget):
    def __init__(self):
        super().__init__()
        self.video_manager = VideoManager()
        self.audio_library = AudioLibrary()
        self.selected_audios: list[str] = []   # ordered list of selected audio paths
        self.irregular_segments: list[int] = []  # 不规则合并片段列表
        self.loop_counts: list[int] = []           # 循环模式：每个视频的循环次数
        self.playlists: dict = {}              # 歌单：{name: [audio_path, ...]}
        self.worker = None
        self.base_dir = "" # 保存用户选择的基础目录
        self.output_dir = ""
        self.settings = QSettings("MyCompany", "VideoToolbox") # 初始化设置引擎
        
        self.setup_ui()
        self.bind_events()
        self.load_settings() # 界面加载完毕后，立刻恢复之前的参数

    def load_settings(self):
        """从注册表读取上次保存的设置"""
        self.spin_merge_count.setValue(self.settings.value("v_merge_count", 2, type=int))
        self.spin_output_count.setValue(self.settings.value("v_output_count", 1, type=int))
        self.combo_aspect_ratio.setCurrentText(self.settings.value("v_aspect_ratio", "9:16 (竖屏/抖音)"))
        self.combo_resolution.setCurrentText(self.settings.value("v_resolution", "1080P (1K/推荐)"))
        self.combo_order.setCurrentText(self.settings.value("v_order", "随机合并"))
        self.combo_transition.setCurrentText(self.settings.value("v_transition", "溶解"))
        self.spin_speed.setValue(self.settings.value("v_speed", 1.0, type=float))
        self.check_mute.setChecked(self.settings.value("v_mute", True, type=bool))
        self.check_add_music.setChecked(self.settings.value("v_add_music", False, type=bool))
        self.combo_audio_mode.setCurrentText(self.settings.value("v_audio_mode", "随机分配"))
        self.check_audio_loop.setChecked(self.settings.value("v_audio_loop", True, type=bool))
        self.spin_audio_volume.setValue(self.settings.value("v_audio_volume", 100, type=int))

        saved_dir = self.settings.value("v_base_dir", "")
        if saved_dir and os.path.exists(saved_dir):
            self.base_dir = saved_dir
            self.lbl_out_path.setText(f"已选择: {self.base_dir}")

        self._refresh_audio_library_list()

        # 恢复上次选择的背景音乐（过滤掉已从库中删除的条目）
        saved_selected = self.settings.value("v_selected_audios", [], type=list)
        library_paths = {e['path'] for e in self.audio_library.get_all()}
        self.selected_audios = [p for p in saved_selected if p in library_paths]
        self._update_audio_select_bar()

        # 恢复歌单
        import json as _json
        try:
            raw_pl = self.settings.value("v_playlists", "{}")
            loaded = _json.loads(raw_pl) if raw_pl else {}
            self.playlists = {
                name: [p for p in paths if p in library_paths]
                for name, paths in loaded.items()
                if isinstance(name, str) and isinstance(paths, list)
            }
        except Exception:
            self.playlists = {}
        self._refresh_playlist_combo()

        # 恢复不规则合并设置
        import json
        try:
            raw = self.settings.value("v_irregular_segments", "[]")
            self.irregular_segments = json.loads(raw) if raw else []
        except Exception:
            self.irregular_segments = []
        irr_on = self.settings.value("v_irregular_on", False, type=bool)
        self.check_irregular.setChecked(irr_on)
        self._toggle_irregular_mode()
        self._update_irregular_label()

        # 恢复循环模式设置
        try:
            raw_loop = self.settings.value("v_loop_counts", "[]")
            self.loop_counts = json.loads(raw_loop) if raw_loop else []
        except Exception:
            self.loop_counts = []
        loop_on = self.settings.value("v_loop_on", False, type=bool)
        self.check_loop_mode.setChecked(loop_on)
        self._toggle_loop_mode()
        self._update_loop_label()

    def save_settings(self):
        """保存当前界面的所有参数配置"""
        self.settings.setValue("v_merge_count", self.spin_merge_count.value())
        self.settings.setValue("v_output_count", self.spin_output_count.value())
        self.settings.setValue("v_aspect_ratio", self.combo_aspect_ratio.currentText())
        self.settings.setValue("v_resolution", self.combo_resolution.currentText())
        self.settings.setValue("v_order", self.combo_order.currentText())
        self.settings.setValue("v_transition", self.combo_transition.currentText())
        self.settings.setValue("v_speed", self.spin_speed.value())
        self.settings.setValue("v_mute", self.check_mute.isChecked())
        self.settings.setValue("v_add_music", self.check_add_music.isChecked())
        self.settings.setValue("v_audio_mode", self.combo_audio_mode.currentText())
        self.settings.setValue("v_audio_loop", self.check_audio_loop.isChecked())
        self.settings.setValue("v_audio_volume", self.spin_audio_volume.value())
        self.settings.setValue("v_base_dir", self.base_dir)
        self.settings.setValue("v_selected_audios", self.selected_audios)
        import json
        self.settings.setValue("v_irregular_segments", json.dumps(self.irregular_segments))
        self.settings.setValue("v_irregular_on", self.check_irregular.isChecked())
        self.settings.setValue("v_loop_counts", json.dumps(self.loop_counts))
        self.settings.setValue("v_loop_on", self.check_loop_mode.isChecked())
        self.settings.setValue("v_playlists", json.dumps(self.playlists, ensure_ascii=False))

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

        card_upload, layout_upload = self.create_card("📁 输入视频文件")
        self.file_list = QListWidget()
        self.file_list.setFixedHeight(140)
        self.file_list.setAcceptDrops(True)
        self.file_list.setDragDropMode(QListWidget.DragDropMode.DropOnly)
        self.file_list.installEventFilter(self)
        layout_upload.addWidget(self.file_list)

        btn_layout = QHBoxLayout()
        self.btn_add_files = QPushButton("添加文件")
        self.btn_add_folder = QPushButton("添加文件夹")
        self.btn_clear = QPushButton("清空列表")
        btn_layout.addWidget(self.btn_add_files)
        btn_layout.addWidget(self.btn_add_folder)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_clear)
        layout_upload.addLayout(btn_layout)
        main_layout.addWidget(card_upload)

        card_params, layout_params = self.create_card("⚙️ 合并与参数设置")
        grid = QGridLayout()
        grid.setVerticalSpacing(15)
        grid.setHorizontalSpacing(20)
        # 标签列固定，输入框列均等拉伸，与图片合并完全一致
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 0)
        grid.setColumnStretch(3, 1)
        _INPUT_MAX_W = 260   # 与图片合并一致：对独占列的控件限宽

        # Row 0
        grid.addWidget(QLabel("合并数量(每个视频几段):"), 0, 0)
        self.spin_merge_count = QSpinBox()
        self.spin_merge_count.setRange(2, 100)
        self.spin_merge_count.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_merge_count.setMaximumWidth(_INPUT_MAX_W)
        grid.addWidget(self.spin_merge_count, 0, 1)

        grid.addWidget(QLabel("最终输出视频数量:"), 0, 2)
        self.spin_output_count = QSpinBox()
        self.spin_output_count.setRange(1, 1000)
        self.spin_output_count.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_output_count.setMaximumWidth(_INPUT_MAX_W)
        grid.addWidget(self.spin_output_count, 0, 3)

        # Row 1
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

        # Row 2
        grid.addWidget(QLabel("合并顺序:"), 2, 0)
        self.combo_order = QComboBox()
        self.combo_order.addItems(["随机合并", "按顺序合并"])
        self.combo_order.setMaximumWidth(_INPUT_MAX_W)
        grid.addWidget(self.combo_order, 2, 1)

        grid.addWidget(QLabel("转场特效:"), 2, 2)
        self.combo_transition = QComboBox()
        self.combo_transition.addItems(["溶解", "滑动", "颜色擦去", "直线擦去", "对比并移动", "流动", "堆叠", "叠加", "无转场"])
        self.combo_transition.setMaximumWidth(_INPUT_MAX_W)
        grid.addWidget(self.combo_transition, 2, 3)

        # Row 3 左半：速度标签 + 滑条 + 数值框，跨 col0+col1
        # 与图片合并的 trans_layout / eff_layout 跨列写法完全一致
        speed_layout = QHBoxLayout()
        speed_layout.setContentsMargins(0, 0, 0, 0)
        speed_layout.setSpacing(10)
        speed_layout.addWidget(QLabel("视频速度 (滑动或输入):"))
        self.slider_speed = QSlider(Qt.Orientation.Horizontal)
        self.slider_speed.setRange(10, 200)
        self.spin_speed = QDoubleSpinBox()
        self.spin_speed.setRange(0.1, 2.0)
        self.spin_speed.setSingleStep(0.1)
        self.spin_speed.setFixedWidth(60)
        self.spin_speed.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.slider_speed.valueChanged.connect(lambda v: self.spin_speed.setValue(v / 100.0))
        self.spin_speed.valueChanged.connect(lambda v: self.slider_speed.setValue(int(v * 100)))
        speed_layout.addWidget(self.slider_speed, 1)
        speed_layout.addWidget(self.spin_speed)
        grid.addLayout(speed_layout, 3, 0, 1, 2)    # colspan=2，跨左半边，与图片合并 Row3 左侧一致

        # Row 3 右半：去掉声音勾选，跨 col2+col3
        mute_layout = QHBoxLayout()
        mute_layout.setContentsMargins(0, 0, 0, 0)
        self.check_mute = QCheckBox("去掉声音 (防合并崩溃推荐)")
        mute_layout.addWidget(self.check_mute)
        mute_layout.addStretch()
        grid.addLayout(mute_layout, 3, 2, 1, 2)     # colspan=2，跨右半边

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

        # ── 循环模式行 ─────────────────────────────────────────────────────────
        loop_row = QHBoxLayout()
        loop_row.setSpacing(10)
        self.check_loop_mode = QCheckBox("🔁 循环模式")
        self.check_loop_mode.setToolTip(
            "开启后，每行指定对应视频素材的循环次数，\n"
            "每个输出视频仅包含单一素材循环合并。\n"
            "与不规则模式互斥，开启循环模式将自动关闭不规则模式。"
        )
        loop_row.addWidget(self.check_loop_mode)
        self.btn_loop_config = QPushButton("📋 点击配置循环")
        self.btn_loop_config.setEnabled(False)
        loop_row.addWidget(self.btn_loop_config)
        self.lbl_loop_summary = QLabel("（未配置）")
        self.lbl_loop_summary.setStyleSheet("color: #4b5563; font-size: 9pt;")
        loop_row.addWidget(self.lbl_loop_summary, 1)
        layout_params.addLayout(loop_row)

        # ── 按文件名合并模式行 ────────────────────────────────────
        fname_row = QHBoxLayout()
        fname_row.setSpacing(10)
        self.check_filename_mode = QCheckBox("🗂 按文件名合并")
        self.check_filename_mode.setToolTip(
            "开启后，根据视频文件名自动分组并按编号顺序合并。\n"
            "命名格式：「识别码-数字编号」，例如 A-1、A-2、邓-1、AB-3\n"
            "相同识别码的视频会合并为一个，按数字升序排列。\n"
            "合并数量、输出数量、合并顺序将失效，尺寸/分辨率/转场仍有效。"
        )
        fname_row.addWidget(self.check_filename_mode)
        self.lbl_filename_summary = QLabel("（未开启）")
        self.lbl_filename_summary.setStyleSheet("color: #4b5563; font-size: 9pt;")
        fname_row.addWidget(self.lbl_filename_summary, 1)
        layout_params.addLayout(fname_row)

        main_layout.addWidget(card_params)

        # ── 音频背景音乐卡 (仅当勾选去掉声音时显示) ─────────────────────────
        self.card_audio, layout_audio = self.create_card("🎵 添加背景音乐")

        # 开关行
        music_toggle_row = QHBoxLayout()
        self.check_add_music = QCheckBox("添加背景音乐")
        self.check_add_music.setChecked(False)
        self.check_add_music.setToolTip(
            "勾选后将把所选背景音乐混入输出视频。\n"
            "• 若同时勾选了「去掉声音」，则去掉原声后替换为背景音乐；\n"
            "• 若未勾选「去掉声音」，则保留原声并与背景音乐叠加混音。"
        )
        music_toggle_row.addWidget(self.check_add_music)
        music_toggle_row.addStretch()
        layout_audio.addLayout(music_toggle_row)

        # 音频库列表
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

        # 已选音乐展示条
        select_title = QLabel("🎼  当前任务的背景音乐（点击下方选择）")
        select_title.setProperty("class", "CardTitle")
        layout_audio.addWidget(select_title)

        self.audio_select_bar = ClickableFrame()
        self.audio_select_bar.setObjectName("VAudioSelectBar")
        self.audio_select_bar.setMinimumHeight(44)
        self.audio_select_bar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.audio_select_bar.setStyleSheet("""
            QFrame#VAudioSelectBar {
                background-color: #0f1117;
                border: 1px dashed #374151;
                border-radius: 8px;
            }
            QFrame#VAudioSelectBar:hover {
                border-color: #f43f5e;
            }
        """)
        bar_layout = QHBoxLayout(self.audio_select_bar)
        bar_layout.setContentsMargins(14, 6, 14, 6)
        self.audio_select_label = QLabel("未选择背景音乐 — 点击此处打开选择器")
        self.audio_select_label.setStyleSheet("color: #4b5563; font-size: 10pt;")
        bar_layout.addWidget(self.audio_select_label)
        bar_layout.addStretch()
        hint_lbl2 = QLabel("单击选择  →")
        hint_lbl2.setStyleSheet("color: #374151; font-size: 9pt;")
        bar_layout.addWidget(hint_lbl2)
        layout_audio.addWidget(self.audio_select_bar)

        # 音频分配模式 + 循环 + 音量
        audio_params_grid = QGridLayout()
        audio_params_grid.setHorizontalSpacing(20)
        audio_params_grid.setVerticalSpacing(10)

        audio_params_grid.addWidget(QLabel("🎵 音频分配模式:"), 0, 0)
        self.combo_audio_mode = QComboBox()
        self.combo_audio_mode.addItems(["随机分配", "按顺序补全", "按顺序不补全"])
        self.combo_audio_mode.setToolTip(
            "随机分配：随机为每个视频分配一首背景音乐\n"
            "按顺序补全：按选择顺序依次分配，不足时循环补全\n"
            "按顺序不补全：按选择顺序依次分配，不足时剩余视频无音频"
        )
        audio_params_grid.addWidget(self.combo_audio_mode, 0, 1)

        self.check_audio_loop = QCheckBox("音频自动循环（时长不足时）")
        self.check_audio_loop.setChecked(True)
        self.check_audio_loop.setToolTip("若开启，当音频时长短于视频时，自动循环播放补全；若关闭，音频结束后静音")
        audio_params_grid.addWidget(self.check_audio_loop, 0, 2, 1, 2)

        audio_params_grid.addWidget(QLabel("🔊 音量:"), 1, 0)
        vol_row = QHBoxLayout()
        self.slider_audio_volume = QSlider(Qt.Orientation.Horizontal)
        self.slider_audio_volume.setRange(0, 200)
        self.slider_audio_volume.setValue(100)
        self.slider_audio_volume.setFixedWidth(110)
        self.slider_audio_volume.setToolTip("0% = 静音 / 100% = 原始音量 / 200% = 双倍音量")
        self.spin_audio_volume = QSpinBox()
        self.spin_audio_volume.setRange(0, 200)
        self.spin_audio_volume.setValue(100)
        self.spin_audio_volume.setSuffix(" %")
        self.spin_audio_volume.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_audio_volume.setFixedWidth(70)
        self.slider_audio_volume.valueChanged.connect(self.spin_audio_volume.setValue)
        self.spin_audio_volume.valueChanged.connect(self.slider_audio_volume.setValue)
        vol_row.addWidget(self.slider_audio_volume)
        vol_row.addWidget(self.spin_audio_volume)
        vol_hint = QLabel("ℹ 跳过开头 / 渐入时长：在音频库中选中音频后点击 [🎧 编辑参数] 进行设置")
        vol_hint.setStyleSheet("color: #4b5563; font-size: 9pt;")
        vol_row.addSpacing(14)
        vol_row.addWidget(vol_hint)
        vol_row.addStretch()
        vol_layout_widget = QFrame()
        vol_layout_widget.setLayout(vol_row)
        audio_params_grid.addWidget(vol_layout_widget, 1, 1, 1, 3)

        layout_audio.addLayout(audio_params_grid)

        # ── 歌单管理区域 ────────────────────────────────────
        playlist_sep = QFrame()
        playlist_sep.setFrameShape(QFrame.Shape.HLine)
        playlist_sep.setStyleSheet("color: #2d3748; margin: 4px 0;")
        layout_audio.addWidget(playlist_sep)

        playlist_title = QLabel("🎶  歌单管理")
        playlist_title.setProperty("class", "CardTitle")
        layout_audio.addWidget(playlist_title)

        playlist_row1 = QHBoxLayout()
        playlist_row1.setSpacing(8)
        playlist_row1.addWidget(QLabel("当前歌单:"))
        self.combo_playlist = QComboBox()
        self.combo_playlist.setMinimumWidth(160)
        self.combo_playlist.setToolTip("切换歌单后，当前选中的背景音乐将自动替换为该歌单的曲目")
        playlist_row1.addWidget(self.combo_playlist, 1)
        self.btn_playlist_new = QPushButton("＋ 新建歌单")
        self.btn_playlist_new.setToolTip("将当前选中的背景音乐保存为新歌单")
        playlist_row1.addWidget(self.btn_playlist_new)
        self.btn_playlist_save = QPushButton("💾 保存到歌单")
        self.btn_playlist_save.setToolTip("将当前选中的背景音乐覆盖保存到所选歌单")
        playlist_row1.addWidget(self.btn_playlist_save)
        self.btn_playlist_delete = QPushButton("🗑 删除歌单")
        self.btn_playlist_delete.setToolTip("删除当前所选歌单（不影响音频库）")
        playlist_row1.addWidget(self.btn_playlist_delete)
        layout_audio.addLayout(playlist_row1)

        self.lbl_playlist_hint = QLabel("「新建歌单」可将当前选中的音乐保存为歌单，下次直接切换加载")
        self.lbl_playlist_hint.setStyleSheet("color: #4b5563; font-size: 9pt;")
        layout_audio.addWidget(self.lbl_playlist_hint)

        main_layout.addWidget(self.card_audio)

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
        self.btn_start = QPushButton("🚀 开始生成视频")
        self.btn_start.setObjectName("PrimaryBtn")
        self.btn_start.setFixedHeight(45)
        self.btn_stop = QPushButton("🛑 停止")
        self.btn_stop.setEnabled(False)
        self.btn_stop.setFixedHeight(45)

        action_btn_layout.addWidget(self.btn_start, stretch=3)
        action_btn_layout.addWidget(self.btn_stop, stretch=1)
        layout_action.addLayout(action_btn_layout)

        main_layout.addWidget(card_action)
        main_layout.addStretch()


    def bind_events(self):
        self.btn_add_files.clicked.connect(self.add_files)
        self.btn_add_folder.clicked.connect(self.add_folder)
        self.btn_clear.clicked.connect(self.file_list.clear)
        self.btn_out_path.clicked.connect(self.select_output_dir)
        self.btn_start.clicked.connect(self.start_merge)
        self.btn_stop.clicked.connect(self.stop_merge)
        # 不规则合并模式
        self.check_irregular.stateChanged.connect(lambda _: self._toggle_irregular_mode())
        self.btn_irregular_config.clicked.connect(self._open_irregular_dialog)
        # 循环模式
        self.check_loop_mode.stateChanged.connect(lambda _: self._toggle_loop_mode())
        self.btn_loop_config.clicked.connect(self._open_loop_dialog)
        # 按文件名合并模式
        self.check_filename_mode.stateChanged.connect(lambda _: self._toggle_filename_mode())
        # 音频库管理
        self.btn_add_audio.clicked.connect(self._add_audio_files)
        self.btn_add_audio_folder.clicked.connect(self._add_audio_folder)
        self.btn_remove_audio.clicked.connect(self._remove_selected_audio)
        self.btn_clear_audio.clicked.connect(self._clear_audio_library)
        self.audio_select_bar.clicked.connect(self._open_audio_select_dialog)
        # 歌单管理
        self.combo_playlist.currentIndexChanged.connect(self._switch_playlist)
        self.btn_playlist_new.clicked.connect(self._new_playlist)
        self.btn_playlist_save.clicked.connect(self._save_to_playlist)
        self.btn_playlist_delete.clicked.connect(self._delete_playlist)

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "选择视频", "", "Video Files (*.mp4 *.avi *.mov *.mkv)")
        for f in files: self.file_list.addItem(f)

    def add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if folder:
            for root, _, files in os.walk(folder):
                for file in files:
                    if file.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
                        self.file_list.addItem(os.path.join(root, file))

    def select_output_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "选择基础输出文件夹")
        if dir_path:
            self.base_dir = dir_path
            self.lbl_out_path.setText(f"已选择: {self.base_dir}")
            self.settings.setValue("v_base_dir", self.base_dir)  # 立即持久化，重启后自动恢复

    # ── 音乐面板显示控制 ───────────────────────────────────────────────────

    def _toggle_music_panel(self):
        """背景音乐面板现在常驻显示，与“去掉声音”解耦；保留此方法以兼容旧调用。"""
        self.card_audio.setVisible(True)

    # ── 不规则合并模式 ────────────────────────────────────────────────────

    def _toggle_irregular_mode(self):
        is_irr = self.check_irregular.isChecked()
        # 与循环模式互斥
        if is_irr and self.check_loop_mode.isChecked():
            self.check_loop_mode.blockSignals(True)
            self.check_loop_mode.setChecked(False)
            self.check_loop_mode.blockSignals(False)
            self._toggle_loop_mode()
        # 与按文件名模式互斥
        if is_irr and self.check_filename_mode.isChecked():
            self.check_filename_mode.blockSignals(True)
            self.check_filename_mode.setChecked(False)
            self.check_filename_mode.blockSignals(False)
            self._update_filename_summary()
        is_any = is_irr or self.check_loop_mode.isChecked() or self.check_filename_mode.isChecked()
        self.spin_merge_count.setEnabled(not is_any)
        self.spin_output_count.setEnabled(not is_any)
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

    # ── 循环模式 ──────────────────────────────────────────────────────────

    def _toggle_loop_mode(self):
        is_loop = self.check_loop_mode.isChecked()
        # 与不规则模式互斥
        if is_loop and self.check_irregular.isChecked():
            self.check_irregular.blockSignals(True)
            self.check_irregular.setChecked(False)
            self.check_irregular.blockSignals(False)
            self.btn_irregular_config.setEnabled(False)
        # 与按文件名模式互斥
        if is_loop and self.check_filename_mode.isChecked():
            self.check_filename_mode.blockSignals(True)
            self.check_filename_mode.setChecked(False)
            self.check_filename_mode.blockSignals(False)
            self._update_filename_summary()
        is_any = is_loop or self.check_irregular.isChecked() or self.check_filename_mode.isChecked()
        self.spin_merge_count.setEnabled(not is_any)
        self.spin_output_count.setEnabled(not is_any)
        self.combo_order.setEnabled(not is_loop and not self.check_filename_mode.isChecked())
        self.btn_loop_config.setEnabled(is_loop)

    def _open_loop_dialog(self):
        dlg = LoopModeDialog(self.loop_counts, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.loop_counts = dlg.get_loops()
            self._update_loop_label()

    def _update_loop_label(self):
        if self.loop_counts:
            preview = ", ".join(str(n) for n in self.loop_counts[:8])
            if len(self.loop_counts) > 8:
                preview += "..."
            self.lbl_loop_summary.setText(
                f"共{len(self.loop_counts)}个视频 · 循环次数：{preview}")
            self.lbl_loop_summary.setStyleSheet(
                "color: #f43f5e; font-size: 9pt; font-weight: bold;")
        else:
            self.lbl_loop_summary.setText("（未配置）")
            self.lbl_loop_summary.setStyleSheet("color: #4b5563; font-size: 9pt;")

    # ── 按文件名合并模式 ─────────────────────────────────────────────────

    def _toggle_filename_mode(self):
        is_fn = self.check_filename_mode.isChecked()
        if is_fn and self.check_irregular.isChecked():
            self.check_irregular.blockSignals(True)
            self.check_irregular.setChecked(False)
            self.check_irregular.blockSignals(False)
            self.btn_irregular_config.setEnabled(False)
        if is_fn and self.check_loop_mode.isChecked():
            self.check_loop_mode.blockSignals(True)
            self.check_loop_mode.setChecked(False)
            self.check_loop_mode.blockSignals(False)
            self.btn_loop_config.setEnabled(False)
        is_any = is_fn or self.check_irregular.isChecked() or self.check_loop_mode.isChecked()
        self.spin_merge_count.setEnabled(not is_any)
        self.spin_output_count.setEnabled(not is_any)
        self.combo_order.setEnabled(not is_fn and not self.check_loop_mode.isChecked())
        self._update_filename_summary()

    def _update_filename_summary(self):
        if not self.check_filename_mode.isChecked():
            self.lbl_filename_summary.setText("（未开启）")
            self.lbl_filename_summary.setStyleSheet("color: #4b5563; font-size: 9pt;")
            return
        all_videos = [self.file_list.item(i).text() for i in range(self.file_list.count())]
        groups = self._parse_filename_groups(all_videos)
        if groups:
            self.lbl_filename_summary.setText(
                f"共识别出 {len(groups)} 组，将生成 {len(groups)} 个视频"
            )
            self.lbl_filename_summary.setStyleSheet(
                "color: #f43f5e; font-size: 9pt; font-weight: bold;"
            )
        else:
            self.lbl_filename_summary.setText("未识别到有效分组，请检查文件名格式（识别码-编号）")
            self.lbl_filename_summary.setStyleSheet("color: #f59e0b; font-size: 9pt;")

    def _parse_filename_groups(self, video_paths: list) -> dict:
        """
        解析视频文件列表，按「识别码-数字编号」格式分组并排序。
        返回: {identifier: [path_sorted_by_number, ...]} 按识别码字典序排序
        """
        import re
        groups: dict = {}
        pattern = re.compile(r'^(.+)-(\d+)$')
        for path in video_paths:
            stem = os.path.splitext(os.path.basename(path))[0]
            m = pattern.match(stem)
            if m:
                identifier = m.group(1)
                number = int(m.group(2))
                if identifier not in groups:
                    groups[identifier] = []
                groups[identifier].append((number, path))
        sorted_groups = dict(sorted(groups.items()))
        result = {k: [p for _, p in sorted(v)] for k, v in sorted_groups.items()}
        return result

    # ── 音频库管理 ─────────────────────────────────────────────────────────

    def _add_audio_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择音频文件", "", "Audio Files (*.mp3 *.wav *.aac *.ogg)")
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
        self.audio_lib_list.clear()
        for entry in self.audio_library.get_all():
            item = QListWidgetItem(f"🎵  {entry['name']}   |   {entry['path']}")
            item.setData(Qt.ItemDataRole.UserRole, entry['path'])
            self.audio_lib_list.addItem(item)

    def _open_audio_select_dialog(self):
        if not self.audio_library.get_all():
            QMessageBox.information(self, "音频库为空", "请先在上方区域添加音频文件。")
            return
        dlg = AudioSelectDialog(self.audio_library, self.selected_audios, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.selected_audios = dlg.get_selected_paths()
            self._update_audio_select_bar()

    def _update_audio_select_bar(self):
        if not self.selected_audios:
            self.audio_select_label.setText("未选择背景音乐 — 点击此处打开选择器")
            self.audio_select_label.setStyleSheet("color: #4b5563; font-size: 10pt;")
        else:
            n = len(self.selected_audios)
            text = f"🎵  已选 {n} 首背景音乐 — 点击修改"
            self.audio_select_label.setText(text)
            self.audio_select_label.setStyleSheet("color: #f43f5e; font-size: 10pt; font-weight: bold;")

    # ── 歌单管理 ──────────────────────────────────────────────────────────

    def _refresh_playlist_combo(self):
        """重新填充歌单下拉框，保持当前选中项（若存在）。"""
        current = self.combo_playlist.currentText()
        self.combo_playlist.blockSignals(True)
        self.combo_playlist.clear()
        self.combo_playlist.addItem("（未选择歌单）")
        for name in self.playlists:
            self.combo_playlist.addItem(name)
        idx = self.combo_playlist.findText(current)
        self.combo_playlist.setCurrentIndex(max(0, idx))
        self.combo_playlist.blockSignals(False)
        has_pl = bool(self.playlists)
        self.btn_playlist_save.setEnabled(has_pl)
        self.btn_playlist_delete.setEnabled(has_pl)

    def _switch_playlist(self, index: int):
        """切换到所选歌单，将 selected_audios 替换为该歌单的曲目并刷新界面。"""
        if index <= 0:
            return
        name = self.combo_playlist.currentText()
        if name not in self.playlists:
            return
        library_paths = {e['path'] for e in self.audio_library.get_all()}
        valid = [p for p in self.playlists[name] if p in library_paths]
        self.selected_audios = valid
        self._update_audio_select_bar()
        self.lbl_playlist_hint.setText(
            f"已切换到歌单「{name}」，共 {len(valid)} 首"
        )

    def _new_playlist(self):
        """将当前选中的背景音乐保存为新歌单。"""
        if not self.selected_audios:
            QMessageBox.information(self, "提示", "请先在下方选择器中选择背景音乐，再创建歌单。")
            return
        name, ok = QInputDialog.getText(self, "新建歌单", "请输入歌单名称：")
        if not ok or not name.strip():
            return
        name = name.strip()
        if name in self.playlists:
            reply = QMessageBox.question(
                self, "歌单已存在",
                f"歌单「{name}」已存在，是否覆盖保存？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self.playlists[name] = list(self.selected_audios)
        self.save_settings()
        self._refresh_playlist_combo()
        idx = self.combo_playlist.findText(name)
        if idx >= 0:
            self.combo_playlist.blockSignals(True)
            self.combo_playlist.setCurrentIndex(idx)
            self.combo_playlist.blockSignals(False)
        self.lbl_playlist_hint.setText(
            f"歌单「{name}」已保存，共 {len(self.selected_audios)} 首"
        )

    def _save_to_playlist(self):
        """将当前选中的背景音乐覆盖保存到当前所选歌单。"""
        name = self.combo_playlist.currentText()
        if not name or name == "（未选择歌单）":
            QMessageBox.information(self, "提示", "请先在下拉框中选择一个歌单。")
            return
        if not self.selected_audios:
            QMessageBox.information(self, "提示", "当前没有选中任何背景音乐。")
            return
        self.playlists[name] = list(self.selected_audios)
        self.save_settings()
        self.lbl_playlist_hint.setText(
            f"已将当前选中的 {len(self.selected_audios)} 首音乐保存到歌单「{name}」"
        )

    def _delete_playlist(self):
        """删除当前所选歌单。"""
        name = self.combo_playlist.currentText()
        if not name or name == "（未选择歌单）":
            QMessageBox.information(self, "提示", "请先在下拉框中选择要删除的歌单。")
            return
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除歌单「{name}」吗？（不影响音频库）",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.playlists.pop(name, None)
        self.save_settings()
        self._refresh_playlist_combo()
        self.lbl_playlist_hint.setText(f"歌单「{name}」已删除")

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

    def start_merge(self):
        if self.file_list.count() == 0 or not self.base_dir:
            QMessageBox.warning(self, "警告", "请先上传视频并选择输出路径！")
            return
            
        # 根据保存的基础路径，每次动态创建带有当天日期的文件夹
        prefix = datetime.now().strftime("%Y%m%d")
        self.output_dir = os.path.join(self.base_dir, prefix)

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
        ffprobe_exe = os.path.join(_root, "ffmpeg", "ffprobe.exe")
        if not os.path.exists(ffmpeg_exe) or not os.path.exists(ffprobe_exe):
            QMessageBox.critical(self, "错误", f"找不到 ffmpeg.exe 或 ffprobe.exe！\n期望路径：{_root}\\ffmpeg\\")
            return

        all_videos = [self.file_list.item(i).text() for i in range(self.file_list.count())]
        self.video_manager.clear()
        self.video_manager.add_videos(all_videos)

        merge_count = self.spin_merge_count.value()
        output_count = self.spin_output_count.value()
        merge_mode = self.combo_order.currentText()

        # ── 确定任务列表 ──────────────────────────────────────────────────
        # 按文件名合并模式：直接解析分组并启动
        if self.check_filename_mode.isChecked():
            groups = self._parse_filename_groups(all_videos)
            if not groups:
                QMessageBox.warning(self, "警告",
                    "按文件名合并模式已开启，但未识别出有效分组。\n"
                    "请确保视频文件名格式为：「识别码-数字编号」，例如 A-1、张三-2")
                return
            tasks = []
            current_seq = 1
            for identifier, sorted_paths in groups.items():
                while True:
                    raw_path = os.path.join(self.output_dir, f"{identifier}_{current_seq:03d}.mp4")
                    output_file = os.path.normpath(raw_path)
                    if not os.path.exists(output_file): break
                    current_seq += 1
                tasks.append({"videos": sorted_paths, "output_file": output_file})
                current_seq += 1
            use_music = self.check_add_music.isChecked()
            audio_assignments = self._get_audio_for_tasks(len(tasks)) if use_music and self.selected_audios else [None] * len(tasks)
            for task, ap in zip(tasks, audio_assignments):
                task["audio_path"] = ap
                if ap:
                    params = self.audio_library.get_params_for_path(ap)
                    task["audio_skip_start"] = params["skip_start"]
                    task["audio_fade_in"]    = params["fade_in"]
                else:
                    task["audio_skip_start"] = 0.0
                    task["audio_fade_in"]    = 0.0
            self.btn_start.setEnabled(False)
            self.btn_stop.setEnabled(True)
            self.progress_bar.setValue(0)
            self.worker = FFmpegWorker(
                tasks=tasks,
                transition=self.combo_transition.currentText(),
                aspect_ratio=self.combo_aspect_ratio.currentText().split(" ")[0],
                resolution=self.combo_resolution.currentText().split(" ")[0],
                speed=self.spin_speed.value(),
                mute=self.check_mute.isChecked(),
                ffmpeg_path=ffmpeg_exe,
                ffprobe_path=ffprobe_exe,
                audio_loop=self.check_audio_loop.isChecked(),
                audio_volume=self.spin_audio_volume.value(),
            )
            self.worker.progress.connect(self.update_progress)
            self.worker.finished.connect(self.task_finished)
            self.worker.start()
            return

        # 不规则模式：使用自定义片段数列表
        if self.check_irregular.isChecked():
            if not self.irregular_segments:
                QMessageBox.warning(self, "警告",
                    "不规则模式已开启，但未配置片段列表，请先点击「点击配置列表」输入数据。")
                return
            segment_list = self.irregular_segments
        elif self.check_loop_mode.isChecked():
            # 循环模式：按顺序强制
            merge_mode = "按顺序合并"
            if not self.loop_counts:
                QMessageBox.warning(self, "警告",
                    "循环模式已开启，但未配置循环次数，请先点击「点击配置循环」输入数据。")
                return
            segment_list = None   # 循环模式单独处理
        else:
            segment_list = [merge_count] * output_count


        tasks = []
        current_seq = 1

        if self.check_loop_mode.isChecked():
            # ── 循环模式：第 i 行 → 第 i 个文件，重复 loop_counts[i] 次 ──
            all_videos = [self.file_list.item(j).text() for j in range(self.file_list.count())]
            # 以文件数量为上限
            effective = min(len(self.loop_counts), len(all_videos))
            for idx in range(effective):
                video_path = all_videos[idx]
                loop_n = self.loop_counts[idx]
                # 该视频重复 loop_n 次组成 task_videos
                task_videos = [video_path] * loop_n

                while True:
                    raw_path = os.path.join(self.output_dir, f"{prefix}_{current_seq:03d}.mp4")
                    output_file = os.path.normpath(raw_path)
                    if not os.path.exists(output_file): break
                    current_seq += 1

                tasks.append({"videos": task_videos, "output_file": output_file})
                current_seq += 1
        else:
            for count in segment_list:
                task_videos = self.video_manager.get_videos_for_merge(count, mode=merge_mode)
                if not task_videos: break

                while True:
                    raw_path = os.path.join(self.output_dir, f"{prefix}_{current_seq:03d}.mp4")
                    output_file = os.path.normpath(raw_path)
                    if not os.path.exists(output_file): break
                    current_seq += 1

                tasks.append({"videos": task_videos, "output_file": output_file})
                current_seq += 1

        if not tasks: return

        # 分配背景音乐（勾选添加音乐即可，不再要求去掉原声）
        use_music = self.check_add_music.isChecked()
        if use_music and self.selected_audios:
            audio_assignments = self._get_audio_for_tasks(len(tasks))
        else:
            audio_assignments = [None] * len(tasks)

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

        self.worker = FFmpegWorker(
            tasks=tasks, 
            transition=self.combo_transition.currentText(),
            aspect_ratio=self.combo_aspect_ratio.currentText().split(" ")[0],
            resolution=self.combo_resolution.currentText().split(" ")[0],
            speed=self.spin_speed.value(), 
            mute=self.check_mute.isChecked(),
            ffmpeg_path=ffmpeg_exe, 
            ffprobe_path=ffprobe_exe,
            audio_loop=self.check_audio_loop.isChecked(),
            audio_volume=self.spin_audio_volume.value(),
        )
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.task_finished)
        self.worker.start()

    def stop_merge(self):
        if self.worker: self.worker.stop()

    def update_progress(self, percent, text):
        self.progress_bar.setValue(percent)
        self.lbl_status.setText(text)

    def task_finished(self, success, message):
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        if success: QMessageBox.information(self, "完成", message)
        else: QMessageBox.critical(self, "错误或中断", message)

    def eventFilter(self, source, event):
        if source is self.file_list:
            if event.type() in (QEvent.Type.DragEnter, QEvent.Type.DragMove):
                if event.mimeData().hasUrls():
                    event.accept()
                    return True
            elif event.type() == QEvent.Type.Drop:
                for url in event.mimeData().urls():
                    path = url.toLocalFile()
                    if path.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
                        self.file_list.addItem(path)
                event.accept()
                return True

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

        res = super().eventFilter(source, event)
        return bool(res)