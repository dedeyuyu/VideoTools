import codecs

path = r"d:\Antigravity\VideoTools\UI\ui_duet_video.py"
with codecs.open(path, 'r', 'utf-8') as f:
    code = f.read()

code = code.replace("QProgressBar, QSplitter,", "QProgressBar, QSplitter, QRadioButton,")

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(code)

print("Added QRadioButton to imports")
