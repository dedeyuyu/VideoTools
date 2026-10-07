import codecs

path = r"d:\Antigravity\VideoTools\UI\ui_duet_video.py"
with codecs.open(path, 'r', 'utf-8') as f:
    code = f.read()

old_block = """        tpl = json.loads(json.dumps(self.active_tpl()))
        split_y = box_layout(tpl)["split_y"]
        tc = self.title_editor.get_cfg()
        pc = self.phone_editor.get_cfg()
        ow, oh = self.cmb_res.currentData()
        self.txt_log.clear()
        jobs = []
        used = set()
        wm_cfg = self.wm_editor.get_cfg()
        for i, t in enumerate(self.tasks):
            title_png = phone_png = ""
            if self._card_visible(tc, t.get("title_text")):"""

new_block = """        tpl = json.loads(json.dumps(self.active_tpl()))
        split_y = box_layout(tpl)["split_y"]
        ow, oh = self.cmb_res.currentData()
        self.txt_log.clear()
        jobs = []
        used = set()
        wm_cfg = getattr(self, "wm_editor", None) and self.wm_editor.get_cfg()
        for i, t in enumerate(self.tasks):
            title_png = phone_png = ""
            tc = t.get("title_cfg") or getattr(self, "global_title_cfg", self.title_editor.get_cfg())
            pc = t.get("phone_cfg") or getattr(self, "global_phone_cfg", self.phone_editor.get_cfg())
            if self._card_visible(tc, t.get("title_text")):"""

code = code.replace(old_block, new_block)

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(code)

print("Patched start_render to use per-task configs")
