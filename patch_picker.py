import codecs
import re

path = r"d:\Antigravity\VideoTools\UI\ui_duet_video.py"
with codecs.open(path, 'r', 'utf-8') as f:
    code = f.read()

old_block = """class ColorButton(QPushButton):
    colorChanged = pyqtSignal()

    def __init__(self, color="#FFFFFF", parent=None):
        super().__init__(parent)
        self._color = color
        self.setFixedHeight(30)
        self.clicked.connect(self._pick)
        self._refresh()

    def color(self):
        return self._color

    def set_color(self, c):
        self._color = c
        self._refresh()

    def _refresh(self):
        txt = "#000000" if QColor(self._color).lightness() > 140 else "#FFFFFF"
        self.setText(self._color.upper())
        self.setStyleSheet(f"background-color: {self._color}; color: {txt}; "
                           f"border: 1px solid #A0AEC0; border-radius: 6px;")

    def _pick(self):
        # 使用 Qt 内置取色器，它支持 拾色器(吸管) 和 Hue/Sat 面板
        c = QColorDialog.getColor(QColor(self._color), self, "选择颜色", options=QColorDialog.ColorDialogOption.DontUseNativeDialog)
        if c.isValid():
            self.set_color(c.name())
            self.colorChanged.emit()"""

new_block = """class ScreenPicker(QWidget):
    colorPicked = pyqtSignal(QColor)
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setGeometry(QApplication.primaryScreen().virtualGeometry())

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 1))

    def mousePressEvent(self, event):
        self.hide()
        QApplication.processEvents()
        import time
        time.sleep(0.05)
        pos = event.globalPosition().toPoint()
        sc = QApplication.screenAt(pos) or QApplication.primaryScreen()
        px = sc.grabWindow(0, pos.x() - sc.geometry().x(), pos.y() - sc.geometry().y(), 1, 1)
        self.colorPicked.emit(px.toImage().pixelColor(0, 0))
        self.close()

    def keyPressEvent(self, event):
        self.close()


class ColorButton(QWidget):
    colorChanged = pyqtSignal()

    def __init__(self, color="#FFFFFF", parent=None):
        super().__init__(parent)
        self._color = color
        self.setFixedHeight(30)
        
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        
        self.btn_color = QPushButton()
        self.btn_color.setFixedHeight(30)
        self.btn_color.clicked.connect(self._pick)
        
        self.btn_drop = QPushButton("🖌")
        self.btn_drop.setFixedSize(30, 30)
        self.btn_drop.setToolTip("屏幕吸管：点击后，再点击屏幕任意位置吸取颜色")
        self.btn_drop.clicked.connect(self._start_eyedropper)
        
        lay.addWidget(self.btn_color, 1)
        lay.addWidget(self.btn_drop)
        
        self._refresh()

    def color(self):
        return self._color

    def set_color(self, c):
        self._color = c
        self._refresh()

    def _refresh(self):
        txt = "#000000" if QColor(self._color).lightness() > 140 else "#FFFFFF"
        self.btn_color.setText(self._color.upper())
        self.btn_color.setStyleSheet(f"background-color: {self._color}; color: {txt}; "
                                     f"border: 1px solid #A0AEC0; border-radius: 6px;")

    def _pick(self):
        c = QColorDialog.getColor(QColor(self._color), self, "选择颜色", options=QColorDialog.ColorDialogOption.DontUseNativeDialog)
        if c.isValid():
            self.set_color(c.name())
            self.colorChanged.emit()

    def _start_eyedropper(self):
        self.picker = ScreenPicker()
        self.picker.colorPicked.connect(self._on_picked)
        self.picker.show()
        
    def _on_picked(self, c):
        self.set_color(c.name())
        self.colorChanged.emit()"""

code = code.replace(old_block, new_block)

# Ensure QApplication and QPainter are imported
if "QApplication," not in code and "import QApplication" not in code:
    code = code.replace("from PyQt6.QtWidgets import (", "from PyQt6.QtWidgets import (QApplication, ")
if "QPainter," not in code and "import QPainter" not in code:
    code = code.replace("from PyQt6.QtGui import (", "from PyQt6.QtGui import (QPainter, ")

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(code)

print("Patched ColorButton with ScreenPicker")
