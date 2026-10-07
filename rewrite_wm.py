import re
import codecs

path = r"d:\Antigravity\VideoTools\UI\ui_duet_video.py"
with codecs.open(path, 'r', 'utf-8') as f:
    code = f.read()

watermark_class = """
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
        self.btn_del = QPushButton("❌")
        self.btn_del.setFixedWidth(30)
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
        
        row_font = QHBoxLayout()
        self.cmb_font = QFontComboBox()
        self.cmb_font.setCurrentFont(QFont(self.cfg.get("font_family", "Microsoft YaHei")))
        self.cmb_font.currentFontChanged.connect(self._on_change)
        row_font.addWidget(self.cmb_font, 1)
        
        self.spin_fs = QSpinBox()
        self.spin_fs.setRange(6, 400)
        self.spin_fs.setValue(int(self.cfg.get("font_size", 32)))
        self.spin_fs.valueChanged.connect(self._on_change)
        row_font.addWidget(QLabel("字号:"))
        row_font.addWidget(self.spin_fs)
        
        self.btn_color = ColorButton(self.cfg.get("color", "#FFFFFF"))
        self.btn_color.colorChanged.connect(self._on_change)
        row_font.addWidget(QLabel("颜色:"))
        row_font.addWidget(self.btn_color)
        form_text.addRow("字体设置:", row_font)
        
        row_alpha = QHBoxLayout()
        self.spin_t_alpha = QSpinBox()
        self.spin_t_alpha.setRange(0, 100)
        self.spin_t_alpha.setValue(int(self.cfg.get("text_opacity", 100)))
        self.spin_t_alpha.valueChanged.connect(self._on_change)
        row_alpha.addWidget(QLabel("字透明度:"))
        row_alpha.addWidget(self.spin_t_alpha)
        row_alpha.addWidget(QLabel("%"))
        
        self.btn_bg = ColorButton(self.cfg.get("bg_color", "#000000"))
        self.btn_bg.colorChanged.connect(self._on_change)
        row_alpha.addWidget(QLabel("底色:"))
        row_alpha.addWidget(self.btn_bg)
        
        self.spin_b_alpha = QSpinBox()
        self.spin_b_alpha.setRange(0, 100)
        self.spin_b_alpha.setValue(int(self.cfg.get("bg_opacity", 50)))
        self.spin_b_alpha.valueChanged.connect(self._on_change)
        row_alpha.addWidget(QLabel("底透明度:"))
        row_alpha.addWidget(self.spin_b_alpha)
        row_alpha.addWidget(QLabel("%"))
        row_alpha.addStretch()
        form_text.addRow("颜色透明:", row_alpha)
        
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
        
        row_img_opt = QHBoxLayout()
        self.spin_scale = QSpinBox()
        self.spin_scale.setRange(1, 1000)
        self.spin_scale.setValue(int(self.cfg.get("scale", 30)))
        self.spin_scale.valueChanged.connect(self._on_change)
        row_img_opt.addWidget(QLabel("缩放:"))
        row_img_opt.addWidget(self.spin_scale)
        row_img_opt.addWidget(QLabel("%"))
        
        self.spin_i_alpha = QSpinBox()
        self.spin_i_alpha.setRange(0, 100)
        self.spin_i_alpha.setValue(int(self.cfg.get("opacity", 100)))
        self.spin_i_alpha.valueChanged.connect(self._on_change)
        row_img_opt.addWidget(QLabel("透明度:"))
        row_img_opt.addWidget(self.spin_i_alpha)
        row_img_opt.addWidget(QLabel("%"))
        
        self.chk_fh = QCheckBox("左右翻转")
        self.chk_fh.setChecked(self.cfg.get("flip_h", False))
        self.chk_fh.toggled.connect(self._on_change)
        row_img_opt.addWidget(self.chk_fh)
        
        self.chk_fv = QCheckBox("上下翻转")
        self.chk_fv.setChecked(self.cfg.get("flip_v", False))
        self.chk_fv.toggled.connect(self._on_change)
        row_img_opt.addWidget(self.chk_fv)
        row_img_opt.addStretch()
        form_img.addRow("图片设置:", row_img_opt)
        
        self.stack.addWidget(self.page_img)
        
        # Common Position
        row_pos = QHBoxLayout()
        self.cmb_pos = QComboBox()
        for v, t in [("tl", "左上"), ("tr", "右上"), ("bl", "左下"), ("br", "右下"), ("bc", "居中")]:
            self.cmb_pos.addItem(t, v)
        self.cmb_pos.setCurrentIndex(max(0, self.cmb_pos.findData(self.cfg.get("position", "br"))))
        self.cmb_pos.currentIndexChanged.connect(self._on_change)
        row_pos.addWidget(QLabel("位置:"))
        row_pos.addWidget(self.cmb_pos)
        
        self.spin_ox = QSpinBox()
        self.spin_ox.setRange(-2000, 2000)
        self.spin_ox.setValue(int(self.cfg.get("ox", 0)))
        self.spin_ox.valueChanged.connect(self._on_change)
        row_pos.addWidget(QLabel("偏移X:"))
        row_pos.addWidget(self.spin_ox)
        
        self.spin_oy = QSpinBox()
        self.spin_oy.setRange(-2000, 2000)
        self.spin_oy.setValue(int(self.cfg.get("oy", 0)))
        self.spin_oy.valueChanged.connect(self._on_change)
        row_pos.addWidget(QLabel("Y:"))
        row_pos.addWidget(self.spin_oy)
        row_pos.addStretch()
        
        self.vbox.addLayout(row_pos)
        
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
"""

pattern = r"class WatermarkEditor\(QWidget\):.*?class DuetVideoUI\(QWidget\):"
code = re.sub(pattern, watermark_class + "\n\nclass DuetVideoUI(QWidget):", code, flags=re.DOTALL)

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(code)

print("Replaced WatermarkEditor")
