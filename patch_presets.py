import codecs

path = r"d:\Antigravity\VideoTools\UI\ui_duet_video.py"
with codecs.open(path, 'r', 'utf-8') as f:
    code = f.read()

old_reload = """    def reload_presets(self):
        presets = _load_json("card_presets.json", {})
        self.cmb_preset.blockSignals(True)
        self.cmb_preset.clear()
        self.cmb_preset.addItem("— 选择预设 —", None)
        for name in presets:
            self.cmb_preset.addItem(name, name)
        self.cmb_preset.blockSignals(False)"""

new_reload = """    def reload_presets(self):
        presets = _load_json("card_presets.json", {})
        self.cmb_preset.blockSignals(True)
        self.cmb_preset.clear()
        self.cmb_preset.addItem("— 选择预设 —", None)
        
        user_presets = []
        default_presets = []
        
        for name, cfg in presets.items():
            is_user = cfg.get("_is_user")
            
            if is_user is None:
                if name.startswith("热门 -") or name in [
                    '黄金强光贴纸 (El Resplandor Dorado)', '霓虹青空发光体 (Cielo Neón)', '街头冲击 (Impacto Urbano)', 
                    '纯净极简 (Minimalismo Puro)', '复古报纸 (Titular de Prensa)', '警戒红幕 (Alerta Roja)', 
                    '深海权威 (Autoridad Profunda)', '复古羊皮纸 (Pergamino Clásico)', '活力柑橘 (Cítrico Vibrante)', 
                    '极简白盒 (Caja Blanca Minimalista)', '暗流暗盒 (Caja Oscura)', '紫水晶滤镜 (Filtro Amatista)', 
                    '毛玻璃翠绿 (Verde Esmerilado)', '赛博深灰 (Gris Cibernético)', '柔和米黄带 (Cinta Beige Suave)', 
                    '官方生态分层 (Ecosistema WhatsApp)', '专业深海拼图 (Azul Profesional)', '极简黑白交界 (Frontera Monocromática)', 
                    '牧师呼召紫带 (Llamado Pastoral)', '黄金金融分割 (División Financiera)', '磨砂白玉胶囊 (Vidrio Esmerilado)', 
                    '暗夜流金 (Noche Dorada)', '翠绿信任盾牌 (Escudo Verde)', '极简半透黑盒 (Caja Translúcida)', 
                    '纯白云朵悬浮 (Nube Blanca)', '红色下划线警告 (Subrayado Urgente)', '警戒黄黑封条 (Cinta de Precaución)', 
                    '荧光焦点框 (Marco de Enfoque Neón)', '优惠警报红底 (Alerta de Oferta)', '科技蓝图指示牌 (Plano Tecnológico)'
                ]:
                    is_user = False
                else:
                    is_user = True
                    
            if is_user:
                kind = cfg.get("_kind")
                if kind is None:
                    kind = "phone" if "电话" in name else "title"
                if kind == self.kind:
                    user_presets.append(name)
            else:
                default_presets.append(name)
                
        user_presets.reverse()
        
        if user_presets:
            self.cmb_preset.addItem("—— 我的预设 ——", None)
            item_model = self.cmb_preset.model()
            item_model.item(self.cmb_preset.count()-1).setEnabled(False)
            
            for name in user_presets:
                self.cmb_preset.addItem(name, name)
                
        if default_presets:
            self.cmb_preset.addItem("—— 默认预设 ——", None)
            item_model = self.cmb_preset.model()
            item_model.item(self.cmb_preset.count()-1).setEnabled(False)
            
            for name in default_presets:
                self.cmb_preset.addItem(name, name)

        self.cmb_preset.blockSignals(False)"""

old_save = """    def _save_preset(self):
        name, ok = QInputDialog.getText(self, "保存卡片预设", "预设名称（含文字样式 / 图片缩放与位置）:")
        if not ok or not name.strip():
            return
        presets = _load_json("card_presets.json", {})
        cfg = self.get_cfg()"""

new_save = """    def _save_preset(self):
        name, ok = QInputDialog.getText(self, "保存卡片预设", "预设名称（含文字样式 / 图片缩放与位置）:")
        if not ok or not name.strip():
            return
        presets = _load_json("card_presets.json", {})
        cfg = self.get_cfg()
        cfg["_kind"] = self.kind
        cfg["_is_user"] = True"""

old_del = """    def _del_preset(self):
        name = self.cmb_preset.currentData()
        if not name:
            return
        presets = _load_json("card_presets.json", {})"""

new_del = """    def _del_preset(self):
        name = self.cmb_preset.currentData()
        if not name:
            return
        # 不能删除默认预设
        presets = _load_json("card_presets.json", {})
        if presets.get(name, {}).get("_is_user") is False or name.startswith("热门 -"):
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "提示", "无法删除默认预设。")
            return"""

if old_reload in code and old_save in code and old_del in code:
    code = code.replace(old_reload, new_reload)
    code = code.replace(old_save, new_save)
    code = code.replace(old_del, new_del)
    with codecs.open(path, 'w', 'utf-8') as f:
        f.write(code)
    print("Patched presets successfully.")
else:
    print("Old block not found!")
    if old_reload not in code: print("old_reload failed")
    if old_save not in code: print("old_save failed")
    if old_del not in code: print("old_del failed")
