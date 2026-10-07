import codecs

path = r"d:\Antigravity\VideoTools\UI\ui_duet_video.py"
with codecs.open(path, 'r', 'utf-8') as f:
    code = f.read()

old_block = """    def _build_page_cards(self):
        from image_worker.duet_render import default_card
        self.global_title_cfg = default_card("title")
        self.global_phone_cfg = default_card("phone")
        page = QWidget()
        main_lay = QHBoxLayout(page)
        main_lay.setContentsMargins(0, 0, 0, 0)
        self.cards_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_lay.addWidget(self.cards_splitter)

        # 左：任务与文本（可滚动）
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFixedWidth(270)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left = _card()
        left_scroll.setWidget(left)
        lv = QVBoxLayout(left)
        lv.addWidget(_card_title("📋 任务列表"))
        self.task_list = QListWidget()
        self.task_list.setMinimumHeight(130)
        self.task_list.currentRowChanged.connect(self._on_task_select)
        lv.addWidget(self.task_list, 1)

        lv.addWidget(QLabel("标题卡片文本（当前任务）:"))
        self.txt_title = QPlainTextEdit()
        self.txt_title.setFixedHeight(64)
        self.txt_title.textChanged.connect(self._on_task_text)
        lv.addWidget(self.txt_title)
        lv.addWidget(QLabel("电话卡片文本（当前任务）:"))
        self.txt_phone = QPlainTextEdit()
        self.txt_phone.setFixedHeight(52)
        self.txt_phone.textChanged.connect(self._on_task_text)
        lv.addWidget(self.txt_phone)
        b1 = QPushButton("📋 批量粘贴标题文本")
        b1.clicked.connect(lambda: self._batch_paste("title_text", "批量导入标题文本"))
        b2 = QPushButton("📋 批量粘贴电话文本")
        b2.clicked.connect(lambda: self._batch_paste("phone_text", "批量导入电话文本"))
        lv.addWidget(b1)
        lv.addWidget(b2)

        gb = QGroupBox("🎯 画面单项微调（当前任务）")
        f = QFormLayout(gb)
        self.adj_w = {}
        for who, nm in (("person", "人物"), ("viral", "爆款")):
            for k, lbl, rng in (("dx", "X 移动", (-2000, 2000)), ("dy", "Y 移动", (-2000, 2000)),
                                ("scale", "缩放 %", (10, 500))):
                sp = QSpinBox()
                sp.setRange(*rng)
                sp.setSingleStep(1 if k == "scale" else 10)
                sp.setValue(100 if k == "scale" else 0)
                sp.valueChanged.connect(self._on_adj_change)
                f.addRow(f"{nm} {lbl}:", sp)
                self.adj_w[(who, k)] = sp
        b_reset = QPushButton("↺ 重置微调")
        b_reset.clicked.connect(self._reset_adj)
        f.addRow("", b_reset)
        lv.addWidget(gb)
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
        self.card_tabs = QTabWidget()
        self.card_tabs.setMinimumWidth(380)
        
        self.title_editor = CardEditor("title")
        self.phone_editor = CardEditor("phone")
        self.card_tabs.addTab(self._wrap_editor("title", self.title_editor), "🅰 标题卡片")
        self.card_tabs.addTab(self._wrap_editor("phone", self.phone_editor), "📞 电话卡片")
        self.wm_editor = WatermarkEditor(self)
        self.wm_editor.changed.connect(self.redraw_preview)
        self.card_tabs.addTab(self.wm_editor, "© 水印")
        self.cards_splitter.addWidget(self.card_tabs)
        self.cards_splitter.setStretchFactor(1, 1)
        return page"""

new_block = """    def _build_page_cards(self):
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
        left_scroll.setFixedWidth(240)
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
        self.card_tabs = QTabWidget()
        self.card_tabs.setMinimumWidth(380)
        
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
        self.adj_w = {}
        for who, nm in (("person", "人物"), ("viral", "爆款")):
            for k, lbl, rng in (("dx", "X 移动", (-2000, 2000)), ("dy", "Y 移动", (-2000, 2000)),
                                ("scale", "缩放 %", (10, 500))):
                sp = QSpinBox()
                sp.setRange(*rng)
                sp.setSingleStep(1 if k == "scale" else 10)
                sp.setValue(100 if k == "scale" else 0)
                sp.valueChanged.connect(self._on_adj_change)
                f.addRow(f"{nm} {lbl}:", sp)
                self.adj_w[(who, k)] = sp
        b_reset = QPushButton("↺ 重置微调")
        b_reset.clicked.connect(self._reset_adj)
        f.addRow("", b_reset)
        tv.addWidget(gb)
        tv.addStretch()

        self.card_tabs.addTab(tab_text_scroll, "📝 文案和微调")
        
        self.cards_splitter.addWidget(self.card_tabs)
        self.cards_splitter.setStretchFactor(1, 1)
        return page"""

if old_block in code:
    code = code.replace(old_block, new_block)
    with codecs.open(path, 'w', 'utf-8') as f:
        f.write(code)
    print("Patched layout successfully.")
else:
    print("Old block not found!")
