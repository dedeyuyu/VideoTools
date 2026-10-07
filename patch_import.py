import re
import codecs

path = r"d:\Antigravity\VideoTools\UI\ui_duet_video.py"
with codecs.open(path, 'r', 'utf-8') as f:
    code = f.read()

code = code.replace("QSlider, QFormLayout, QLineEdit, QFileDialog, QMessageBox, QProgressBar,", 
                    "QSlider, QFormLayout, QLineEdit, QFileDialog, QMessageBox, QProgressBar, QSplitter,")

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(code)

print("Added QSplitter to imports")
