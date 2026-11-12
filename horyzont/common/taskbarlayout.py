"""Geometria paska niezależna od protokołu okien i motywu."""
from PySide6.QtCore import QRect, QPoint
from .. import config


def edge():
    value = config.get("taskbar_edge", "bottom")
    return value if value in ("bottom", "top", "left", "right") else "bottom"


def vertical():
    return edge() in ("left", "right")


def geometry(screen, base):
    rows = max(1, min(6, int(config.get("taskbar_rows", 1))))
    thickness = min(max(80, int(config.get("taskbar_width", 160))), screen.width() // 2) if vertical() else min(base * rows, screen.height() // 2)
    if edge() == "left":
        return QRect(screen.left(), screen.top(), thickness, screen.height())
    if edge() == "right":
        return QRect(screen.right() + 1 - thickness, screen.top(), thickness, screen.height())
    return QRect(screen.left(), screen.top() if edge() == "top" else screen.bottom() + 1 - thickness, screen.width(), thickness)


def popup_position(bar, size, screen, anchor=None):
    """Po zewnętrznej stronie paska, z ograniczeniem do bieżącego monitora."""
    anchor = anchor or bar.topLeft()
    if edge() == "top":
        x, y = anchor.x(), bar.bottom() + 1
    elif edge() == "left":
        x, y = bar.right() + 1, anchor.y()
    elif edge() == "right":
        x, y = bar.left() - size.width(), anchor.y()
    else:
        x, y = anchor.x(), bar.top() - size.height()
    return QPoint(max(screen.left(), min(screen.right() + 1 - size.width(), x)),
                  max(screen.top(), min(screen.bottom() + 1 - size.height(), y)))
