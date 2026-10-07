import re
import codecs

path = r"d:\Antigravity\VideoTools\UI\ui_duet_video.py"
with codecs.open(path, 'r', 'utf-8') as f:
    code = f.read()

# 1. UI Resizability: change QHBoxLayout(page) to QSplitter
old_layout = """    def _build_page_cards(self):
        page = QWidget()
        lay = QHBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)

        # 左：任务与文本（可滚动）
        left_scroll = QScrollArea()"""

new_layout = """    def _build_page_cards(self):
        page = QWidget()
        main_lay = QHBoxLayout(page)
        main_lay.setContentsMargins(0, 0, 0, 0)
        self.cards_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_lay.addWidget(self.cards_splitter)

        # 左：任务与文本（可滚动）
        left_scroll = QScrollArea()"""
code = code.replace(old_layout, new_layout)

# Replace lay.addWidget(...) with self.cards_splitter.addWidget(...)
# Only inside _build_page_cards!
def replace_lay_addWidget(m):
    block = m.group(0)
    block = block.replace("lay.addWidget(left_scroll)", "self.cards_splitter.addWidget(left_scroll)")
    block = block.replace("lay.addWidget(mid, 1)", "self.cards_splitter.addWidget(mid)")
    block = block.replace("lay.addWidget(self.card_tabs)", "self.cards_splitter.addWidget(self.card_tabs)\n        self.cards_splitter.setStretchFactor(1, 1)")
    return block

# Find the body of _build_page_cards and replace
pattern_body = r'(def _build_page_cards.*?)(def _build_page_export)'
code = re.sub(pattern_body, replace_lay_addWidget, code, flags=re.DOTALL)

# Remove the maximum width limit on card_tabs so it can be resized freely
code = code.replace("self.card_tabs.setMaximumWidth(500)", "")

# 2. Add speed controls to _build_page_export
old_export_ui = """        self.cmb_quality.addItem("低画质（体积小）", 28)
        form.addRow("画质:", self.cmb_quality)
        self.chk_mute_viral = QCheckBox("抹除爆款视频原声")"""

new_export_ui = """        self.cmb_quality.addItem("低画质（体积小）", 28)
        form.addRow("画质:", self.cmb_quality)
        
        row_speed = QHBoxLayout()
        self.spin_speed = QDoubleSpinBox()
        self.spin_speed.setRange(0.1, 10.0)
        self.spin_speed.setSingleStep(0.1)
        self.spin_speed.setValue(1.0)
        row_speed.addWidget(self.spin_speed)
        row_speed.addWidget(QLabel("倍"))
        form.addRow("全局速度倍数:", row_speed)
        
        self.chk_max_3min = QCheckBox("视频总时长强制不超过三分钟 (超出自动加速)")
        self.chk_max_3min.setChecked(False)
        form.addRow("", self.chk_max_3min)
        
        self.chk_mute_viral = QCheckBox("抹除爆款视频原声")"""
code = code.replace(old_export_ui, new_export_ui)

# 3. Add to settings save & load
old_save_settings = """            "export_dir": self.txt_export_dir.text(),"""
new_save_settings = """            "export_dir": self.txt_export_dir.text(),
            "global_speed": self.spin_speed.value(),
            "max_3min": self.chk_max_3min.isChecked(),"""
code = code.replace(old_save_settings, new_save_settings)

old_load_settings = """        if "export_dir" in s:
            self.txt_export_dir.setText(s["export_dir"])"""
new_load_settings = """        if "export_dir" in s:
            self.txt_export_dir.setText(s["export_dir"])
        if "global_speed" in s:
            self.spin_speed.setValue(s["global_speed"])
        if "max_3min" in s:
            self.chk_max_3min.setChecked(s["max_3min"])"""
code = code.replace(old_load_settings, new_load_settings)


# 4. Pass arguments to start_render
old_job_args = """                           wm_png=wm_png,
                           mute_viral=self.chk_mute_viral.isChecked(),
                           volume=self.slider_volume.value() / 100.0,
                           out_w=ow, out_h=oh, quality=self.cmb_quality.currentData()),"""

new_job_args = """                           wm_png=wm_png,
                           global_speed=self.spin_speed.value(),
                           max_3min=self.chk_max_3min.isChecked(),
                           mute_viral=self.chk_mute_viral.isChecked(),
                           volume=self.slider_volume.value() / 100.0,
                           out_w=ow, out_h=oh, quality=self.cmb_quality.currentData()),"""
code = code.replace(old_job_args, new_job_args)

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(code)

print("Patched ui_duet_video.py for resizer and export settings")
