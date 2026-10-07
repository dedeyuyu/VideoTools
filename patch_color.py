import codecs

path = r"d:\Antigravity\VideoTools\UI\ui_duet_video.py"
with codecs.open(path, 'r', 'utf-8') as f:
    code = f.read()

old_pick = """    def _pick(self):
        # QColorDialog 自带「Pick Screen Color」吸色器
        c = QColorDialog.getColor(QColor(self._color), self, "选择颜色")"""

new_pick = """    def _pick(self):
        # 使用 Qt 内置取色器，它支持 拾色器(吸管) 和 Hue/Sat 面板
        c = QColorDialog.getColor(QColor(self._color), self, "选择颜色", options=QColorDialog.ColorDialogOption.DontUseNativeDialog)"""

code = code.replace(old_pick, new_pick)

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(code)

print("Patched ColorPicker to use Qt built-in dialog")
