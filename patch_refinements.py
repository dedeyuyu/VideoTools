import codecs

path = r"d:\Antigravity\VideoTools\UI\ui_duet_video.py"
with codecs.open(path, 'r', 'utf-8') as f:
    code = f.read()

# 1. Patch reload_presets
old_reload = """            if is_user:
                kind = cfg.get("_kind")
                if kind is None:
                    kind = "phone" if "电话" in name else "title"
                if kind == self.kind:
                    user_presets.append(name)
            else:
                default_presets.append(name)"""

new_reload = """            kind = cfg.get("_kind")
            if kind is None:
                kind = "phone" if "电话" in name else "title"
            if kind == self.kind:
                if is_user:
                    user_presets.append(name)
                else:
                    default_presets.append(name)"""
if old_reload in code:
    code = code.replace(old_reload, new_reload)

# 2. Patch _add for WordWrap
old_add = """            form.addRow(label, wd)
        self.w[key] = wd"""

new_add = """            lbl_w = QLabel(label)
            lbl_w.setWordWrap(True)
            form.addRow(lbl_w, wd)
        self.w[key] = wd"""
if old_add in code:
    code = code.replace(old_add, new_add)

# 3. Patch _wrap_editor to remove radio buttons
old_wrap = """    def _wrap_editor(self, kind, editor):
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
        return w"""

new_wrap = """    def _wrap_editor(self, kind, editor):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(5,5,5,5)
        lay.addWidget(editor, 1)
        
        def on_editor_changed():
            cfg = editor.get_cfg()
            if hasattr(self, "rb_global") and self.rb_global.isChecked():
                setattr(self, f"global_{kind}_cfg", cfg)
            else:
                if getattr(self, "tasks", None) and getattr(self, "cur_task", -1) >= 0:
                    self.tasks[self.cur_task][f"{kind}_cfg"] = cfg
            self.redraw_preview()
            
        editor.changed.connect(on_editor_changed)
        return w"""
if old_wrap in code:
    code = code.replace(old_wrap, new_wrap)

# 4. Patch _build_page_cards to add global radio, set widths, and connect tabs
old_page_cards_1 = """        # 左：任务列表
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFixedWidth(240)"""

new_page_cards_1 = """        # 左：任务列表
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setMinimumWidth(150)
        left_scroll.setMaximumWidth(450)"""
if old_page_cards_1 in code:
    code = code.replace(old_page_cards_1, new_page_cards_1)

old_page_cards_2 = """        # 右：卡片参数
        self.card_tabs = QTabWidget()
        self.card_tabs.setMinimumWidth(380)"""

new_page_cards_2 = """        # 右：卡片参数
        right_panel = QWidget()
        rv = QVBoxLayout(right_panel)
        rv.setContentsMargins(0, 0, 0, 0)
        
        scope_lay = QHBoxLayout()
        scope_lay.addWidget(QLabel("应用范围:"))
        self.rb_global = QRadioButton("全局默认")
        self.rb_task = QRadioButton("仅当前任务(独立设置)")
        self.rb_task.setChecked(True)
        scope_lay.addWidget(self.rb_global)
        scope_lay.addWidget(self.rb_task)
        scope_lay.addStretch()
        rv.addLayout(scope_lay)
        
        self.rb_global.toggled.connect(self._on_scope_toggled)

        self.card_tabs = QTabWidget()
        self.card_tabs.setMinimumWidth(380)
        self.card_tabs.currentChanged.connect(self._on_card_tab_changed)
        rv.addWidget(self.card_tabs, 1)"""
if old_page_cards_2 in code:
    code = code.replace(old_page_cards_2, new_page_cards_2)

old_page_cards_3 = """        self.cards_splitter.addWidget(self.card_tabs)
        self.cards_splitter.setStretchFactor(1, 1)
        return page"""

new_page_cards_3 = """        self.cards_splitter.addWidget(right_panel)
        self.cards_splitter.setStretchFactor(0, 0)
        self.cards_splitter.setStretchFactor(1, 1)
        self.cards_splitter.setStretchFactor(2, 0)
        return page

    def _on_scope_toggled(self):
        if not getattr(self, "tasks", None): return
        t = self.tasks[self.cur_task]
        is_global = self.rb_global.isChecked()
        
        for kind, editor in [("title", self.title_editor), ("phone", self.phone_editor)]:
            editor.blockSignals(True)
            if is_global:
                t.pop(f"{kind}_cfg", None)
                editor.set_cfg(getattr(self, f"global_{kind}_cfg"))
            else:
                if f"{kind}_cfg" not in t:
                    import copy
                    t[f"{kind}_cfg"] = copy.deepcopy(getattr(self, f"global_{kind}_cfg"))
                editor.set_cfg(t[f"{kind}_cfg"])
            editor.blockSignals(False)
        self.redraw_preview()

    def _on_card_tab_changed(self, index):
        title = self.card_tabs.tabText(index)
        if "标题" in title:
            self._jump_card("title")
        elif "电话" in title:
            self._jump_card("phone")"""
if old_page_cards_3 in code:
    code = code.replace(old_page_cards_3, new_page_cards_3)

# 5. Patch _on_task_select to update single radio button
old_task_sel = """        # Update Scope Radios
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
            editor.blockSignals(False)"""

new_task_sel = """        # Update Scope Radio
        has_task_cfg = "title_cfg" in t or "phone_cfg" in t
        self.rb_global.blockSignals(True)
        self.rb_task.blockSignals(True)
        if has_task_cfg:
            self.rb_task.setChecked(True)
        else:
            self.rb_global.setChecked(True)
        self.rb_global.blockSignals(False)
        self.rb_task.blockSignals(False)
        
        for kind, editor in [("title", self.title_editor), ("phone", self.phone_editor)]:
            editor.blockSignals(True)
            if f"{kind}_cfg" in t:
                editor.set_cfg(t[f"{kind}_cfg"])
            else:
                editor.set_cfg(getattr(self, f"global_{kind}_cfg"))
            editor.blockSignals(False)"""
if old_task_sel in code:
    code = code.replace(old_task_sel, new_task_sel)

# 6. Patch _on_align_done for cache resetting
old_align_done = """        old = self.tasks
        for i, r in enumerate(results):
            prev = old[i] if i < len(old) else {}
            r["title_text"] = prev.get("title_text", "")
            r["phone_text"] = prev.get("phone_text", "")
            r["out_name"] = prev.get("out_name", "")
            r["adj"] = prev.get("adj", {"person": {"dx": 0, "dy": 0, "scale": 100},
                                        "viral": {"dx": 0, "dy": 0, "scale": 100}})
        self.tasks = results"""

new_align_done = """        old = self.tasks
        import copy
        for i, r in enumerate(results):
            prev = old[i] if i < len(old) else {}
            # If the videos are the same, inherit. Otherwise default to new task independent!
            if prev and prev.get("person") == r.get("person") and prev.get("viral") == r.get("viral"):
                r["title_text"] = prev.get("title_text", "")
                r["phone_text"] = prev.get("phone_text", "")
                r["out_name"] = prev.get("out_name", "")
                r["adj"] = prev.get("adj", {"person": {"dx": 0, "dy": 0, "scale": 100},
                                            "viral": {"dx": 0, "dy": 0, "scale": 100}})
                if "title_cfg" in prev: r["title_cfg"] = prev["title_cfg"]
                if "phone_cfg" in prev: r["phone_cfg"] = prev["phone_cfg"]
            else:
                r["title_text"] = ""
                r["phone_text"] = ""
                r["out_name"] = ""
                r["adj"] = {"person": {"dx": 0, "dy": 0, "scale": 100},
                            "viral": {"dx": 0, "dy": 0, "scale": 100}}
                r["title_cfg"] = copy.deepcopy(getattr(self, "global_title_cfg"))
                r["phone_cfg"] = copy.deepcopy(getattr(self, "global_phone_cfg"))
                
        self.tasks = results"""
if old_align_done in code:
    code = code.replace(old_align_done, new_align_done)

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(code)

print("Patch generated.")
