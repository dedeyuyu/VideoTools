import re
import codecs

path = r"d:\Antigravity\VideoTools\image_worker\duet_render.py"
with codecs.open(path, 'r', 'utf-8') as f:
    code = f.read()

# 1. Change bg_fit default
code = code.replace('"bg": False, "bg_fit": True,', '"bg": False, "bg_fit": False,')

# 2. Add ribbon, wave, bow shapes to _shape_path
old_shape_code = """        path.addPolygon(QPolygonF(pts))
        path.closeSubpath()
    else:   # rounded / outline"""

new_shape_code = """        path.addPolygon(QPolygonF(pts))
        path.closeSubpath()
    elif shape == "ribbon":
        c = min(rect.height() * 0.4, 40.0)
        path.addPolygon(QPolygonF([
            QPointF(rect.left(), rect.top()), 
            QPointF(rect.right(), rect.top()),
            QPointF(rect.right() - c, rect.top() + rect.height()/2),
            QPointF(rect.right(), rect.bottom()),
            QPointF(rect.left(), rect.bottom()), 
            QPointF(rect.left() + c, rect.top() + rect.height()/2),
        ]))
        path.closeSubpath()
    elif shape == "bow":
        c = min(rect.height() * 0.2, 20.0)
        path.addPolygon(QPolygonF([
            QPointF(rect.left(), rect.top()), 
            QPointF(rect.right(), rect.top()),
            QPointF(rect.right() - c, rect.top() + rect.height()/2),
            QPointF(rect.right(), rect.bottom()),
            QPointF(rect.left(), rect.bottom()), 
            QPointF(rect.left() + c, rect.top() + rect.height()/2),
        ]))
        path.closeSubpath()
    elif shape == "wave":
        c = min(rect.height() * 0.2, 20.0)
        path.moveTo(rect.topLeft())
        path.lineTo(rect.topRight())
        path.lineTo(rect.bottomRight() - QPointF(0, c))
        path.quadTo(rect.center().x() + rect.width()*0.25, rect.bottom(),
                    rect.center().x(), rect.bottom() - c/2)
        path.quadTo(rect.center().x() - rect.width()*0.25, rect.bottom() - c,
                    rect.bottomLeft() - QPointF(0, c))
        path.closeSubpath()
    else:   # rounded / outline"""

code = code.replace(old_shape_code, new_shape_code)

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(code)

print("Patched duet_render.py")
