import re
import codecs

path = r"d:\Antigravity\VideoTools\UI\ui_duet_video.py"
with codecs.open(path, 'r', 'utf-8') as f:
    code = f.read()

# 1. Fix save_settings
old_save = """            "active_tpl": self.active_tpl_name,
            "cache_root": self.txt_cache_root.text() if hasattr(self, "txt_cache_root") else "",
            "title_cfg": self.title_editor.get_cfg(),"""
new_save = """            "active_tpl": self.active_tpl_name,
            "cache_root": self.txt_cache_root.text() if hasattr(self, "txt_cache_root") else "",
            "person_videos": self.list_person.paths(),
            "viral_videos": self.list_viral.paths(),
            "tasks": getattr(self, "tasks", []),
            "aligned": getattr(self, "aligned", False),
            "title_cfg": self.title_editor.get_cfg(),"""
code = code.replace(old_save, new_save)

# 2. Fix Watermark Delete Button
code = code.replace('self.btn_del = QPushButton("❌")', 'self.btn_del = QPushButton("删除")\n        self.btn_del.setStyleSheet("color: red; font-weight: bold;")')
code = code.replace('self.btn_del.setFixedWidth(30)', 'self.btn_del.setFixedWidth(50)')

# 3. Add Export Speed Controls
# Find: form.addRow("画面质量:", self.cmb_quality)
old_quality = '        form.addRow("画面质量:", self.cmb_quality)'
new_quality = """        form.addRow("画面质量:", self.cmb_quality)
        
        row_speed = QHBoxLayout()
        self.spin_speed = QDoubleSpinBox()
        self.spin_speed.setRange(0.1, 10.0)
        self.spin_speed.setSingleStep(0.1)
        self.spin_speed.setValue(1.0)
        row_speed.addWidget(self.spin_speed)
        row_speed.addWidget(QLabel("倍"))
        form.addRow("全局速度倍数:", row_speed)
        
        self.chk_max_3min = QCheckBox("总时长不超过三分钟 (超出自动加速)")
        self.chk_max_3min.setChecked(False)
        form.addRow("", self.chk_max_3min)"""
code = code.replace(old_quality, new_quality)

# Also ensure it is passed to start_render
# Find: out_w=ow, out_h=oh, quality=self.cmb_quality.currentData()),
old_args = """                           out_w=ow, out_h=oh, quality=self.cmb_quality.currentData()),"""
new_args = """                           global_speed=self.spin_speed.value(),
                           max_3min=self.chk_max_3min.isChecked(),
                           out_w=ow, out_h=oh, quality=self.cmb_quality.currentData()),"""
code = code.replace(old_args, new_args)


with codecs.open(path, 'w', 'utf-8') as f:
    f.write(code)

print("Patched ui_duet_video.py fixes")
