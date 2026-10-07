import re
import codecs

path = r"d:\Antigravity\VideoTools\UI\ui_duet_video.py"
with codecs.open(path, 'r', 'utf-8') as f:
    code = f.read()

# 1. Add global config initialization in init_ui or __init__
# We can just put it at the start of _build_page_cards
old_build_page_cards = "    def _build_page_cards(self):"
new_build_page_cards = """    def _build_page_cards(self):
        from image_worker.duet_render import default_card
        self.global_title_cfg = default_card("title")
        self.global_phone_cfg = default_card("phone")"""
code = code.replace(old_build_page_cards, new_build_page_cards)

# 2. Add Scope UI wrapper
wrapper_code = """
    def _wrap_editor(self, kind, editor):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(5,5,5,5)
        
        scope_lay = QHBoxLayout()
        scope_lay.addWidget(QLabel("应用范围:"))
        rb_global = QRadioButton("全局默认")
        rb_task = QRadioButton("仅当前任务(独立设置)")
        rb_global.setChecked(True)
        scope_lay.addWidget(rb_global)
        scope_lay.addWidget(rb_task)
        scope_lay.addStretch()
        lay.addLayout(scope_lay)
        lay.addWidget(editor, 1)
        
        # Connect signals
        def on_toggle():
            if not getattr(self, "tasks", None): return
            t = self.tasks[self.cur_task]
            is_global = rb_global.isChecked()
            
            editor.blockSignals(True)
            if is_global:
                # Switching to global: we can optionally delete task cfg, or just keep it but not use it.
                # Let's delete it so it truly reverts to global.
                t.pop(f"{kind}_cfg", None)
                editor.set_cfg(getattr(self, f"global_{kind}_cfg"))
            else:
                # Switching to task: create a copy of global if it doesn't have one
                if f"{kind}_cfg" not in t:
                    import copy
                    t[f"{kind}_cfg"] = copy.deepcopy(getattr(self, f"global_{kind}_cfg"))
                editor.set_cfg(t[f"{kind}_cfg"])
            editor.blockSignals(False)
            self.redraw_preview()
            
        rb_global.toggled.connect(on_toggle)
        
        def on_editor_changed():
            # Save the new config to the respective scope
            cfg = editor.get_cfg()
            if rb_global.isChecked():
                setattr(self, f"global_{kind}_cfg", cfg)
            else:
                if getattr(self, "tasks", None):
                    self.tasks[self.cur_task][f"{kind}_cfg"] = cfg
            self.redraw_preview()
            
        editor.changed.connect(on_editor_changed)
        
        setattr(self, f"rb_global_{kind}", rb_global)
        setattr(self, f"rb_task_{kind}", rb_task)
        return w

"""

old_add_tab = """        self.title_editor.changed.connect(self.redraw_preview)
        self.phone_editor.changed.connect(self.redraw_preview)
        self.card_tabs.addTab(self.title_editor, "🅰 标题卡片")
        self.card_tabs.addTab(self.phone_editor, "📞 电话卡片")"""

new_add_tab = """        self.card_tabs.addTab(self._wrap_editor("title", self.title_editor), "🅰 标题卡片")
        self.card_tabs.addTab(self._wrap_editor("phone", self.phone_editor), "📞 电话卡片")"""

# Inject wrapper_code before _build_page_cards
code = code.replace("    def _build_page_cards(self):", wrapper_code + "    def _build_page_cards(self):")
code = code.replace(old_add_tab, new_add_tab)

# 3. Handle task selection updating the radio buttons
old_task_select = """        self.time_slider.blockSignals(True)"""
new_task_select = """        
        # Update Scope Radios
        for kind, editor, rb_global, rb_task in [
            ("title", self.title_editor, self.rb_global_title, self.rb_task_title),
            ("phone", self.phone_editor, self.rb_global_phone, self.rb_task_phone)
        ]:
            rb_global.blockSignals(True)
            rb_task.blockSignals(True)
            editor.blockSignals(True)
            
            if f"{kind}_cfg" in t:
                rb_task.setChecked(True)
                editor.set_cfg(t[f"{kind}_cfg"])
            else:
                rb_global.setChecked(True)
                editor.set_cfg(getattr(self, f"global_{kind}_cfg"))
                
            rb_global.blockSignals(False)
            rb_task.blockSignals(False)
            editor.blockSignals(False)
            
        self.time_slider.blockSignals(True)"""
code = code.replace(old_task_select, new_task_select)


# 4. _load_settings & save_settings
old_load = """        if "title_cfg" in s:
            self.title_editor.set_cfg(s["title_cfg"])
        if "phone_cfg" in s:
            self.phone_editor.set_cfg(s["phone_cfg"])"""
new_load = """        if "title_cfg" in s:
            self.global_title_cfg = s["title_cfg"]
            self.title_editor.set_cfg(s["title_cfg"])
        if "phone_cfg" in s:
            self.global_phone_cfg = s["phone_cfg"]
            self.phone_editor.set_cfg(s["phone_cfg"])"""
code = code.replace(old_load, new_load)

old_save = """            "title_cfg": self.title_editor.get_cfg(),
            "phone_cfg": self.phone_editor.get_cfg(),"""
new_save = """            "title_cfg": getattr(self, "global_title_cfg", self.title_editor.get_cfg()),
            "phone_cfg": getattr(self, "global_phone_cfg", self.phone_editor.get_cfg()),"""
code = code.replace(old_save, new_save)


# 5. start_render using t.get() or global
old_render = """        tc = self.title_editor.get_cfg()
        pc = self.phone_editor.get_cfg()
        wm_cfg = getattr(self, "wm_editor", None) and self.wm_editor.get_cfg()
        for i, t in enumerate(self.tasks):
            title_png = phone_png = ""
            if self._card_visible(tc, t.get("title_text")):
                title_png = os.path.join(card_dir, f"{i + 1:03d}_title.png")
                render_card_layer(tc, t.get("title_text", ""), split_y, i).save(title_png)
            if self._card_visible(pc, t.get("phone_text")):
                if pc["time"] < t["duration"]:
                    phone_png = os.path.join(card_dir, f"{i + 1:03d}_phone.png")
                    render_card_layer(pc, t.get("phone_text", ""), split_y, i).save(phone_png)"""

new_render = """        wm_cfg = getattr(self, "wm_editor", None) and self.wm_editor.get_cfg()
        for i, t in enumerate(self.tasks):
            tc = t.get("title_cfg") or self.global_title_cfg
            pc = t.get("phone_cfg") or self.global_phone_cfg
            title_png = phone_png = ""
            if self._card_visible(tc, t.get("title_text")):
                title_png = os.path.join(card_dir, f"{i + 1:03d}_title.png")
                render_card_layer(tc, t.get("title_text", ""), split_y, i).save(title_png)
            if self._card_visible(pc, t.get("phone_text")):
                if pc["time"] < t["duration"]:
                    phone_png = os.path.join(card_dir, f"{i + 1:03d}_phone.png")
                    render_card_layer(pc, t.get("phone_text", ""), split_y, i).save(phone_png)"""
code = code.replace(old_render, new_render)

# 6. redraw_preview using t.get() or global
old_redraw = """        overlays = []
        tc = self.title_editor.get_cfg()
        pc = self.phone_editor.get_cfg()
        tips = []"""

new_redraw = """        overlays = []
        tc = task.get("title_cfg") or getattr(self, "global_title_cfg", self.title_editor.get_cfg()) if has_task else getattr(self, "global_title_cfg", self.title_editor.get_cfg())
        pc = task.get("phone_cfg") or getattr(self, "global_phone_cfg", self.phone_editor.get_cfg()) if has_task else getattr(self, "global_phone_cfg", self.phone_editor.get_cfg())
        tips = []"""
code = code.replace(old_redraw, new_redraw)

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(code)

print("Patched UI for Global/Task Scope logic")
