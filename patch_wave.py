import codecs

path = r"d:\Antigravity\VideoTools\image_worker\duet_render.py"
with codecs.open(path, 'r', 'utf-8') as f:
    code = f.read()

old_wave = """    elif shape == "wave":
        c = min(rect.height() * 0.2, 20.0)
        path.moveTo(rect.topLeft())
        path.lineTo(rect.topRight())
        path.lineTo(rect.bottomRight() - QPointF(0, c))
        path.quadTo(rect.center().x() + rect.width()*0.25, rect.bottom(),
                    rect.center().x(), rect.bottom() - c/2)
        path.quadTo(rect.center().x() - rect.width()*0.25, rect.bottom() - c,
                    rect.bottomLeft() - QPointF(0, c))
        path.closeSubpath()"""

new_wave = """    elif shape == "wave":
        c = min(rect.height() * 0.2, 20.0)
        path.moveTo(rect.topLeft())
        path.lineTo(rect.topRight())
        path.lineTo(rect.bottomRight() - QPointF(0, c))
        path.quadTo(QPointF(rect.center().x() + rect.width()*0.25, rect.bottom()),
                    QPointF(rect.center().x(), rect.bottom() - c/2))
        path.quadTo(QPointF(rect.center().x() - rect.width()*0.25, rect.bottom() - c),
                    rect.bottomLeft() - QPointF(0, c))
        path.closeSubpath()"""

code = code.replace(old_wave, new_wave)

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(code)

print("Patched duet_render.py for wave shape")
