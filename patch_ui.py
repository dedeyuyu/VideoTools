import re
import codecs

path = r"d:\Antigravity\VideoTools\UI\ui_duet_video.py"
with codecs.open(path, 'r', 'utf-8') as f:
    code = f.read()

# 1. Add render_watermark_layer to image_worker.duet_render imports
code = re.sub(
    r'(from image_worker\.duet_render import \(\n?.*?,?)',
    r'\1 render_watermark_layer,',
    code, count=1
)

# 2. Add WatermarkEditor class right after CardEditor ends
watermark_class = """
class WatermarkEditor(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = []
        self._sel = -1
        self.w = {}

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        # Left list
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.lst = QListWidget()
        self.lst.currentRowChanged.connect(self._on_select)
        ll.addWidget(self.lst, 1)
        btn_lay = QHBoxLayout()
        btn_add = QPushButton("➕ 添加水印")
        btn_add.clicked.connect(self._add_wm)
        btn_del = QPushButton("🗑 删除")
        btn_del.clicked.connect(self._del_wm)
        btn_lay.addWidget(btn_add)
        btn_lay.addWidget(btn_del)
        ll.addLayout(btn_lay)
        lay.addWidget(left)

        # Right editor
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        right = QWidget()
        self.vbox = QFormLayout(right)
        scroll.setWidget(right)
        lay.addWidget(scroll, 1)

        self._add("enabled", "check", "启用该水印")
        self._add("type", "combo", "水印类型", items=[("text", "文字水印"), ("image", "图片水印")])
        self._add("text", "line", "文本内容")
        self._add("image_path", "file", "图片路径")
        self._add("position", "combo", "位置", items=[("tl", "左上角"), ("tr", "右上角"), ("bl", "左下角"), ("br", "右下角"), ("bc", "底部居中")])
        self._add("ox", "spin", "X 偏移", rng=(-2000, 2000))
        self._add("oy", "spin", "Y 偏移", rng=(-2000, 2000))
        self._add("scale", "spin", "缩放/大小", rng=(1, 500))
        self._add("opacity", "spin", "整体透明度", rng=(0, 100))
        self._add("flip_h", "check", "水平翻转 (图片)")
        self._add("font_family", "font", "字体 (文字)")
        self._add("font_size", "spin", "字号 (文字)", rng=(6, 400))
        self._add("color", "color", "字体颜色 (文字)")
        self._add("bg_color", "color", "背景颜色 (文字)")
        self._add("bg_opacity", "spin", "背景透明度 (文字)", rng=(0, 100))

        right.setEnabled(False)
        self.right_panel = right

    def _add(self, key, typ, label, **opt):
        if typ == "check":
            wd = QCheckBox()
            wd.toggled.connect(self._emit)
        elif typ == "spin":
            wd = QSpinBox()
            wd.setRange(*opt.get("rng", (0, 100)))
            wd.valueChanged.connect(self._emit)
        elif typ == "combo":
            wd = QComboBox()
            for val, txt in opt["items"]:
                wd.addItem(txt, val)
            wd.currentIndexChanged.connect(self._emit)
        elif typ == "line":
            wd = QLineEdit()
            wd.textChanged.connect(self._emit)
        elif typ == "font":
            wd = QFontComboBox()
            wd.currentFontChanged.connect(self._emit)
        elif typ == "color":
            wd = ColorButton()
            wd.colorChanged.connect(self._emit)
        elif typ == "file":
            wd = QWidget()
            h = QHBoxLayout(wd)
            h.setContentsMargins(0, 0, 0, 0)
            le = QLineEdit()
            le.textChanged.connect(self._emit)
            b = QPushButton("选择…")
            def pick(l=le):
                p, _ = QFileDialog.getOpenFileName(self, "选择图片", "", "图片 (*.png *.jpg *.jpeg *.webp *.bmp)")
                if p: l.setText(p)
            b.clicked.connect(pick)
            h.addWidget(le)
            h.addWidget(b)
            wd.line = le

        self.vbox.addRow(label, wd)
        self.w[key] = wd
        wd._typ = typ

    def _emit(self, *a):
        if self._sel >= 0 and self._sel < len(self.items):
            cfg = self.items[self._sel]
            for k, wd in self.w.items():
                t = wd._typ
                if t == "check": cfg[k] = wd.isChecked()
                elif t == "spin": cfg[k] = wd.value()
                elif t == "combo": cfg[k] = wd.currentData()
                elif t == "line": cfg[k] = wd.text()
                elif t == "font": cfg[k] = wd.currentFont().family()
                elif t == "color": cfg[k] = wd.color()
                elif t == "file": cfg[k] = wd.line.text()
            name = cfg.get("text") if cfg.get("type") == "text" else os.path.basename(cfg.get("image_path", "图片"))
            if not name: name = "未命名水印"
            self.lst.item(self._sel).setText(name)
            self.changed.emit()

    def _add_wm(self):
        from image_worker.duet_render import default_watermark
        wm = default_watermark()
        wm["text"] = f"Watermark {len(self.items)+1}"
        self.items.append(wm)
        self.lst.addItem(wm["text"])
        self.lst.setCurrentRow(len(self.items)-1)
        self.changed.emit()

    def _del_wm(self):
        if self._sel >= 0:
            self.items.pop(self._sel)
            self.lst.takeItem(self._sel)
            self.changed.emit()

    def _on_select(self, row):
        self._sel = row
        if row < 0 or row >= len(self.items):
            self.right_panel.setEnabled(False)
            return
        self.right_panel.setEnabled(True)
        cfg = self.items[row]
        for k, wd in self.w.items():
            wd.blockSignals(True)
            v = cfg.get(k)
            t = wd._typ
            try:
                if t == "check": wd.setChecked(bool(v))
                elif t == "spin": wd.setValue(int(v))
                elif t == "combo": wd.setCurrentIndex(max(0, wd.findData(v)))
                elif t == "line": wd.setText(str(v or ""))
                elif t == "font": wd.setCurrentFont(QFont(v))
                elif t == "color": wd.set_color(v or "#FFFFFF")
                elif t == "file": wd.line.setText(str(v or ""))
            except Exception: pass
            wd.blockSignals(False)

    def get_cfg(self):
        return self.items

    def set_cfg(self, items):
        self.items = items or []
        self.lst.blockSignals(True)
        self.lst.clear()
        for cfg in self.items:
            name = cfg.get("text") if cfg.get("type") == "text" else os.path.basename(cfg.get("image_path", "图片"))
            if not name: name = "未命名水印"
            self.lst.addItem(name)
        self.lst.blockSignals(False)
        if self.items:
            self.lst.setCurrentRow(0)
        else:
            self._sel = -1
            self.right_panel.setEnabled(False)

"""

code = code.replace("class DuetVideoUI(QWidget):", watermark_class + "\n\nclass DuetVideoUI(QWidget):")

# 3. Update _build_page_cards to store buttons and add WatermarkEditor tab
code = code.replace('bt = QPushButton("看标题卡片")', 'self.btn_preview_title = QPushButton("看标题卡片")')
code = code.replace('bp = QPushButton("看电话卡片")', 'self.btn_preview_phone = QPushButton("看电话卡片")')
code = code.replace('bt.clicked.connect', 'self.btn_preview_title.clicked.connect')
code = code.replace('bp.clicked.connect', 'self.btn_preview_phone.clicked.connect')
code = code.replace('tr.addWidget(bt)', 'tr.addWidget(self.btn_preview_title)')
code = code.replace('tr.addWidget(bp)', 'tr.addWidget(self.btn_preview_phone)')

code = code.replace('self.card_tabs.addTab(self.phone_editor, "📞 电话卡片")',
                    'self.card_tabs.addTab(self.phone_editor, "📞 电话卡片")\n        '
                    'self.wm_editor = WatermarkEditor(self)\n        '
                    'self.wm_editor.changed.connect(self.redraw_preview)\n        '
                    'self.card_tabs.addTab(self.wm_editor, "© 水印")')

# 4. Update _jump_card to highlight button
jump_card_code_new = """
    def _jump_card(self, which):
        if not self.tasks:
            return
        dur = self.tasks[self.cur_task]["duration"]
        if which == "title":
            t = min(1.0, self.title_editor.get_cfg()["time"] / 2)
            self.btn_preview_title.setStyleSheet("background-color: #3182CE; color: white;")
            self.btn_preview_phone.setStyleSheet("")
        else:
            t = self.phone_editor.get_cfg()["time"] + 0.5
            if t >= dur:
                QMessageBox.information(self, "提示", f"电话卡片开始时间超过了当前视频时长（{dur:.1f}s），该卡片在此任务中不会出现。")
                return
            self.btn_preview_phone.setStyleSheet("background-color: #3182CE; color: white;")
            self.btn_preview_title.setStyleSheet("")
        self.time_slider.setValue(int(t * 10))
"""
code = re.sub(r'    def _jump_card\(self, which\):.*?        self\.time_slider\.setValue\(int\(t \* 10\)\)', jump_card_code_new.strip('\n'), code, flags=re.DOTALL)

# 5. Update redraw_preview to draw watermark layer
redraw_new = """
        if tm >= pc["time"]:
            txt = task.get("phone_text") or ""
            if not txt.strip() and pc["mode"] == "text":
                txt = SAMPLE_PHONE
                tips.append("电话文本为空，预览显示示例文字（导出时不会出现）")
            overlays.append(render_card_layer(pc, txt, split_y, self.cur_task, draw_guides=True))

        wm_cfg = self.wm_editor.get_cfg()
        if wm_cfg:
            overlays.append(render_watermark_layer(wm_cfg))
"""
code = code.replace('        if tm >= pc["time"]:\n            txt = task.get("phone_text") or ""\n            if not txt.strip() and pc["mode"] == "text":\n                txt = SAMPLE_PHONE\n                tips.append("电话文本为空，预览显示示例文字（导出时不会出现）")\n            overlays.append(render_card_layer(pc, txt, split_y, self.cur_task, draw_guides=True))', redraw_new.strip('\n'))

# 6. Update start_render to export watermark layer
# In start_render, we specifically replace the block inside `for i, t in enumerate(self.tasks):` safely
start_render_old = """        for i, t in enumerate(self.tasks):
            title_png = phone_png = ""
            if self._card_visible(tc, t.get("title_text")):
                title_png = os.path.join(card_dir, f"{i + 1:03d}_title.png")
                render_card_layer(tc, t.get("title_text", ""), split_y, i).save(title_png)
            if self._card_visible(pc, t.get("phone_text")):
                if pc["time"] < t["duration"]:
                    phone_png = os.path.join(card_dir, f"{i + 1:03d}_phone.png")
                    render_card_layer(pc, t.get("phone_text", ""), split_y, i).save(phone_png)
                else:
                    self.txt_log.appendPlainText(f"⚠️ 任务 {i + 1}：电话卡片开始时间超过视频时长，已跳过该卡片。")
            name = self._safe_name(t.get("out_name") or self._default_out_name(t))
            base, k = name, 2
            while name.lower() in used:
                name = f"{base}_{k}"
                k += 1
            used.add(name.lower())
            out = os.path.join(out_dir, name + ".mp4")
            jobs.append({
                "task": t, "tpl": tpl, "out": out,
                "kw": dict(title_png=title_png, title_end=min(tc["time"], t["duration"]),
                           phone_png=phone_png, phone_start=pc["time"],
                           mute_viral=self.chk_mute_viral.isChecked(),
                           volume=self.slider_volume.value() / 100.0,
                           out_w=ow, out_h=oh, quality=self.cmb_quality.currentData()),
            })"""

start_render_new = """        wm_cfg = self.wm_editor.get_cfg()
        for i, t in enumerate(self.tasks):
            title_png = phone_png = ""
            if self._card_visible(tc, t.get("title_text")):
                title_png = os.path.join(card_dir, f"{i + 1:03d}_title.png")
                render_card_layer(tc, t.get("title_text", ""), split_y, i).save(title_png)
            if self._card_visible(pc, t.get("phone_text")):
                if pc["time"] < t["duration"]:
                    phone_png = os.path.join(card_dir, f"{i + 1:03d}_phone.png")
                    render_card_layer(pc, t.get("phone_text", ""), split_y, i).save(phone_png)
                else:
                    self.txt_log.appendPlainText(f"⚠️ 任务 {i + 1}：电话卡片开始时间超过视频时长，已跳过该卡片。")
            
            wm_png = ""
            if wm_cfg:
                wm_png = os.path.join(card_dir, f"{i + 1:03d}_wm.png")
                render_watermark_layer(wm_cfg).save(wm_png)
                
            name = self._safe_name(t.get("out_name") or self._default_out_name(t))
            base, k = name, 2
            while name.lower() in used:
                name = f"{base}_{k}"
                k += 1
            used.add(name.lower())
            out = os.path.join(out_dir, name + ".mp4")
            jobs.append({
                "task": t, "tpl": tpl, "out": out,
                "kw": dict(title_png=title_png, title_end=min(tc["time"], t["duration"]),
                           phone_png=phone_png, phone_start=pc["time"],
                           wm_png=wm_png,
                           mute_viral=self.chk_mute_viral.isChecked(),
                           volume=self.slider_volume.value() / 100.0,
                           out_w=ow, out_h=oh, quality=self.cmb_quality.currentData()),
            })"""

code = code.replace(start_render_old, start_render_new)

# 7. Update settings load/save
code = code.replace('        if "phone_cfg" in s:\n            self.phone_editor.set_cfg(s["phone_cfg"])',
                    '        if "phone_cfg" in s:\n            self.phone_editor.set_cfg(s["phone_cfg"])\n        if "wm_cfg" in s:\n            self.wm_editor.set_cfg(s["wm_cfg"])')
code = code.replace('            "phone_cfg": self.phone_editor.get_cfg(),',
                    '            "phone_cfg": self.phone_editor.get_cfg(),\n            "wm_cfg": self.wm_editor.get_cfg(),')

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(code)

print("Patched ui_duet_video.py")
