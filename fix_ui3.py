import re
import codecs

path = r"d:\Antigravity\VideoTools\UI\ui_duet_video.py"
with codecs.open(path, 'r', 'utf-8') as f:
    code = f.read()

# 1. Fix card_tabs width
code = code.replace("self.card_tabs.setFixedWidth(380)", "self.card_tabs.setMinimumWidth(380)\n        self.card_tabs.setMaximumWidth(500)")

# 2. Add tasks & lists to settings
save_old = """            "phone_cfg": self.phone_editor.get_cfg(),
            "wm_cfg": self.wm_editor.get_cfg(),
            "cache_root": get_cache_dir(),"""
save_new = """            "phone_cfg": self.phone_editor.get_cfg(),
            "wm_cfg": self.wm_editor.get_cfg(),
            "cache_root": get_cache_dir(),
            "person_videos": self.list_person.paths(),
            "viral_videos": self.list_viral.paths(),
            "tasks": self.tasks,
            "aligned": getattr(self, "aligned", False),"""
code = code.replace(save_old, save_new)

load_old = """        if "wm_cfg" in s:
            self.wm_editor.set_cfg(s["wm_cfg"])"""
load_new = """        if "wm_cfg" in s:
            self.wm_editor.set_cfg(s["wm_cfg"])
        if s.get("person_videos"):
            self.list_person.add_files(s["person_videos"])
        if s.get("viral_videos"):
            self.list_viral.add_files(s["viral_videos"])
        if s.get("tasks"):
            self.tasks = s["tasks"]
            self.aligned = s.get("aligned", False)
            if self.tasks:
                self.task_dir = self.tasks[0].get("task_dir", "")
            self.refresh_task_list()
            self.update_align_status()"""
code = code.replace(load_old, load_new)

# 3. Allow bypassing align warning
step_old = """        if idx in (2, 3) and not self.aligned:
            QMessageBox.warning(self, "请先对齐时间线",
                                "请先在「1. 素材与时间线」中导入视频，并点击「⏱ 对齐时间线」。\\n"
                                "对齐完成后才能进入字幕卡片和导出步骤。\\n\\n"
                                "（「2. 画面排版模板」随时都可以打开编辑）")
            idx = self.stack.currentIndex()"""
step_new = """        if idx in (2, 3) and not self.aligned:
            QMessageBox.warning(self, "尚未对齐时间线",
                                "您尚未完成时间线对齐，将以无视频背景进行效果预览。\\n"
                                "（如果仅为了编辑模板，可忽略此提示）")"""
code = code.replace(step_old, step_new)

# 4. Graceful redraw_preview when no tasks
redraw_pattern = r'    def redraw_preview\(self, \*a\):.*?img = compose_preview\(tpl, pimg, vimg, task\.get\("adj"\), overlays, show_split=True\)'

new_redraw = """    def redraw_preview(self, *a):
        if not hasattr(self, "preview_canvas"):
            return
        tpl = self.active_tpl()
        split_y = box_layout(tpl)["split_y"]
        
        has_task = bool(self.tasks)
        tm = round(self.cur_time(), 1) if has_task else 0.0
        
        if has_task:
            task = self.tasks[self.cur_task]
            pimg = self._frame_cache.get((task["cache"], tm))
            vimg = self._frame_cache.get((task["viral"], tm))
        else:
            task = {}
            pimg = None
            vimg = None
            
        overlays = []
        tc = self.title_editor.get_cfg()
        pc = self.phone_editor.get_cfg()
        tips = []
        if not has_task:
            tips.append("尚未对齐时间线，正以空背景预览卡片效果")
            
        if tm <= tc["time"]:
            txt = task.get("title_text") or ""
            if not txt.strip() and tc["mode"] == "text":
                txt = SAMPLE_TITLE
                if has_task: tips.append("标题为空显示示例文字")
            overlays.append(render_card_layer(tc, txt, split_y, self.cur_task if has_task else 0, draw_guides=True))
            
        if tm >= pc["time"]:
            txt = task.get("phone_text") or ""
            if not txt.strip() and pc["mode"] == "text":
                txt = SAMPLE_PHONE
                if has_task: tips.append("电话为空显示示例文字")
            overlays.append(render_card_layer(pc, txt, split_y, self.cur_task if has_task else 0, draw_guides=True))

        wm_cfg = getattr(self, "wm_editor", None) and self.wm_editor.get_cfg()
        if wm_cfg:
            overlays.append(render_watermark_layer(wm_cfg))
            
        if has_task and (pimg is None or vimg is None):
            tips.insert(0, "正在读取视频画面…")
            
        img = compose_preview(tpl, pimg, vimg, task.get("adj"), overlays, show_split=True)"""

code = re.sub(redraw_pattern, new_redraw, code, flags=re.DOTALL)

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(code)

print("Applied fix_ui3.py")
