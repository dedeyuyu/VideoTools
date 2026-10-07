import sys
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter, QColor

class SP(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setGeometry(QApplication.primaryScreen().virtualGeometry())
    def paintEvent(self, e):
        p=QPainter(self)
        p.fillRect(self.rect(), QColor(0,0,0,1))
    def mousePressEvent(self, e):
        self.hide()
        QApplication.processEvents()
        import time
        time.sleep(0.05)
        pos=e.globalPosition().toPoint()
        sc=QApplication.screenAt(pos) or QApplication.primaryScreen()
        px=sc.grabWindow(0, pos.x()-sc.geometry().x(), pos.y()-sc.geometry().y(), 1, 1)
        print('Picked:', px.toImage().pixelColor(0,0).name())
        self.close()
        sys.exit(0)
    def keyPressEvent(self, e):
        self.close()
        sys.exit(0)

app=QApplication(sys.argv)
w=SP()
w.show()
sys.exit(app.exec())
