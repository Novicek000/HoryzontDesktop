"""Styl Qt (QProxyStyle) rysujący kontrolki za pomocą bieżącego motywu."""
import time

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPalette, QPen, QFontMetrics
from PySide6.QtWidgets import (QAbstractButton, QAbstractScrollArea, QComboBox,
                               QHeaderView, QLineEdit, QMenu, QProxyStyle,
                               QScrollBar, QSlider, QSpinBox, QAbstractSpinBox,
                               QStyle, QStyleFactory, QStyleOption, QStyleOptionTab,
                               QStyleOptionButton, QStyleOptionMenuItem,
                               QTabBar, QToolButton, QWidget)

from .base import CHECKED, DISABLED, HOVER, NORMAL, PRESSED, draw_arrow

S = QStyle


def _signed(v):
    v &= 0xFFFFFFFF
    return v - (1 << 32) if v >= (1 << 31) else v


def _state(opt, checkable=False):
    st = opt.state
    if not (st & S.State_Enabled):
        return DISABLED
    if st & S.State_Sunken:
        return PRESSED
    if checkable and st & S.State_On:
        return CHECKED
    if st & S.State_MouseOver:
        return HOVER
    return NORMAL


class HoryzontStyle(QProxyStyle):
    def __init__(self, theme):
        super().__init__(QStyleFactory.create("Windows"))
        self.theme = theme

    # ------------------------------------------------------------------ polerowanie
    def polish(self, arg):
        if isinstance(arg, QWidget):
            if isinstance(arg, (QAbstractButton, QComboBox, QScrollBar, QTabBar, QHeaderView, QSlider,
                                QAbstractSpinBox, QToolButton)):
                arg.setAttribute(Qt.WA_Hover, True)
            return super().polish(arg)
        return super().polish(arg)

    # ------------------------------------------------------------------ metryki
    _PM = None

    def pixelMetric(self, metric, opt=None, widget=None):
        m = HoryzontStyle._PM
        if m is None:
            m = HoryzontStyle._PM = {
            S.PM_ScrollBarExtent: 17,
            S.PM_ScrollBarSliderMin: 12,
            S.PM_IndicatorWidth: 13,
            S.PM_IndicatorHeight: 13,
            S.PM_ExclusiveIndicatorWidth: 13,
            S.PM_ExclusiveIndicatorHeight: 13,
            S.PM_CheckBoxLabelSpacing: 5,
            S.PM_RadioButtonLabelSpacing: 5,
            S.PM_MenuPanelWidth: 1,
            S.PM_MenuHMargin: 2,
            S.PM_MenuVMargin: 2,
            S.PM_MenuBarPanelWidth: 0,
            S.PM_MenuBarItemSpacing: 0,
            S.PM_MenuBarVMargin: 1,
            S.PM_MenuBarHMargin: 0,
            S.PM_SmallIconSize: 16,
            S.PM_ToolBarIconSize: 24,
            S.PM_ToolBarItemSpacing: 1,
            S.PM_ToolBarFrameWidth: 1,
            S.PM_SliderLength: 11,
            S.PM_SliderThickness: 24,
            S.PM_SliderControlThickness: 21,
            S.PM_SliderTickmarkOffset: 4,
            S.PM_ButtonMargin: 8,
            S.PM_ButtonShiftHorizontal: 0,
            S.PM_ButtonShiftVertical: 0,
            S.PM_DefaultFrameWidth: 1,
            S.PM_ComboBoxFrameWidth: 1,
            S.PM_SpinBoxFrameWidth: 1,
            S.PM_TabBarTabHSpace: 14,
            S.PM_TabBarTabVSpace: 8,
            S.PM_TabBarBaseOverlap: 1,
            S.PM_TabBarTabShiftVertical: 2,
            S.PM_TabBarTabOverlap: 0,
            S.PM_HeaderMargin: 5,
            S.PM_SplitterWidth: 4,
            S.PM_ToolTipLabelFrameWidth: 2,
            S.PM_ProgressBarChunkWidth: 8,
            S.PM_ListViewIconSize: 16,
            S.PM_IconViewIconSize: 32,
            S.PM_TreeViewIndentation: 19,
        }
        if metric in m:
            return m[metric]
        return super().pixelMetric(metric, opt, widget)

    _HINTS = None

    def styleHint(self, hint, opt=None, widget=None, ret=None):
        if hint == S.SH_GroupBox_TextLabelColor:
            return _signed(self.theme.color("group_title").rgb())
        hints = HoryzontStyle._HINTS
        if hints is None:
            hints = HoryzontStyle._HINTS = {
                S.SH_EtchDisabledText: 0,
                S.SH_DitherDisabledText: 0,
                S.SH_Menu_MouseTracking: 1,
                S.SH_MenuBar_MouseTracking: 1,
                S.SH_Menu_SubMenuPopupDelay: 300,
                S.SH_ComboBox_Popup: 0,
                S.SH_ComboBox_ListMouseTracking: 1,
                S.SH_UnderlineShortcut: 1,
                S.SH_Widget_Animate: 0,
                S.SH_ScrollBar_LeftClickAbsolutePosition: 0,
                S.SH_ScrollBar_MiddleClickAbsolutePosition: 1,
                S.SH_DialogButtonBox_ButtonsHaveIcons: 0,
                S.SH_ItemView_ShowDecorationSelected: 1,
                S.SH_TabBar_SelectMouseType: 2,
                S.SH_Slider_StopMouseOverSlider: 1,
                S.SH_ToolTipLabel_Opacity: 255,
                S.SH_Menu_FlashTriggeredItem: 0,
                S.SH_Menu_FadeOutOnHide: 0,
                S.SH_DialogButtonLayout: 0,  # układ "Windows": OK, Anuluj
                S.SH_MessageBox_CenterButtons: 1,
                S.SH_ItemView_ActivateItemOnSingleClick: 0,
            }
        v = hints.get(hint)
        if v is not None:
            return v
        return super().styleHint(hint, opt, widget, ret)

    # ------------------------------------------------------------------ prymitywy
    def drawPrimitive(self, pe, opt, p, widget=None):
        t = self.theme
        if pe in (S.PE_PanelButtonCommand, S.PE_PanelButtonBevel):
            default = bool(getattr(opt, "features", 0) & QStyleOptionButton.DefaultButton) if hasattr(opt, "features") else False
            t.draw_button(p, opt.rect, _state(opt, True) if _state(opt) != PRESSED and opt.state & S.State_On else _state(opt),
                          default=default, focus=bool(opt.state & S.State_HasFocus))
            return
        if pe == S.PE_FrameDefaultButton:
            return
        if pe == S.PE_FrameFocusRect:
            if isinstance(widget, (QAbstractButton,)) or (widget and widget.inherits("QAbstractItemView")):
                p.save()
                pen = QPen(QColor("#000000"), 1, Qt.DotLine)
                p.setPen(pen)
                p.setBrush(Qt.NoBrush)
                p.drawRect(QRect(opt.rect).adjusted(0, 0, -1, -1))
                p.restore()
            return
        if pe == S.PE_IndicatorCheckBox:
            st = _state(opt)
            t.draw_checkbox(p, opt.rect, bool(opt.state & S.State_On), st, bool(opt.state & S.State_NoChange))
            return
        if pe == S.PE_IndicatorRadioButton:
            t.draw_radio(p, opt.rect, bool(opt.state & S.State_On), _state(opt))
            return
        if pe == S.PE_FrameGroupBox:
            t.draw_groupbox(p, opt.rect)
            return
        if pe == S.PE_PanelLineEdit:
            if not (isinstance(widget, QLineEdit) and widget.parent() and isinstance(widget.parent(), (QComboBox, QAbstractSpinBox))):
                p.fillRect(opt.rect, opt.palette.brush(QPalette.Base))
                if getattr(opt, "lineWidth", 1) > 0:
                    t.draw_edit_frame(p, opt.rect, bool(opt.state & S.State_HasFocus), not (opt.state & S.State_Enabled))
            return
        if pe == S.PE_FrameLineEdit:
            t.draw_edit_frame(p, opt.rect, bool(opt.state & S.State_HasFocus), not (opt.state & S.State_Enabled))
            return
        if pe == S.PE_Frame:
            t.draw_edit_frame(p, opt.rect, False, not (opt.state & S.State_Enabled))
            return
        if pe == S.PE_FrameTabWidget:
            t.draw_tab_pane(p, opt.rect)
            return
        if pe == S.PE_FrameTabBarBase:
            return
        if pe in (S.PE_FrameMenu,):
            t.draw_menu_frame(p, opt.rect)
            return
        if pe == S.PE_PanelMenu:
            p.fillRect(opt.rect, t.color("menu"))
            t.draw_menu_frame(p, opt.rect)
            return
        if pe == S.PE_PanelMenuBar:
            p.fillRect(opt.rect, t.color("menubar"))
            return
        if pe == S.PE_PanelButtonTool:
            if isinstance(widget, QToolButton) and widget.autoRaise() or not (opt.state & S.State_Raised) and not (opt.state & S.State_Sunken):
                t.draw_toolbar_button(p, opt.rect, _state(opt, True))
            else:
                t.draw_button(p, opt.rect, _state(opt, True))
            return
        if pe in (S.PE_IndicatorArrowDown, S.PE_IndicatorArrowUp, S.PE_IndicatorArrowLeft, S.PE_IndicatorArrowRight):
            d = {S.PE_IndicatorArrowDown: "down", S.PE_IndicatorArrowUp: "up",
                 S.PE_IndicatorArrowLeft: "left", S.PE_IndicatorArrowRight: "right"}[pe]
            col = opt.palette.color(QPalette.Disabled if not (opt.state & S.State_Enabled) else QPalette.Active, QPalette.ButtonText)
            draw_arrow(p, opt.rect, d, col, 3.2)
            return
        if pe == S.PE_PanelTipLabel:
            t.draw_tooltip(p, opt.rect)
            return
        if pe == S.PE_IndicatorProgressChunk:
            t.draw_progress_chunk(p, opt.rect)
            return
        if pe == S.PE_FrameStatusBarItem:
            return
        if pe == S.PE_IndicatorHeaderArrow:
            up = getattr(opt, "sortIndicator", 0) == 1
            draw_arrow(p, opt.rect, "up" if up else "down", QColor("#7a8a8c"), 3)
            return
        if pe == S.PE_PanelItemViewItem:
            if not (opt.state & S.State_Selected) and opt.state & S.State_MouseOver and widget is not None \
                    and widget.property("hotTrack"):
                h = t.color("highlight")
                h.setAlpha(35)
                p.fillRect(opt.rect, h)
                return
            return super().drawPrimitive(pe, opt, p, widget)
        super().drawPrimitive(pe, opt, p, widget)

    # ------------------------------------------------------------------ kontrolki
    def drawControl(self, ce, opt, p, widget=None):
        t = self.theme
        if ce == S.CE_PushButtonBevel:
            st = _state(opt)
            if st == NORMAL and opt.state & S.State_On:
                st = PRESSED
            default = bool(opt.features & QStyleOptionButton.DefaultButton) if hasattr(opt, "features") else False
            t.draw_button(p, opt.rect, st, default=default and (opt.state & S.State_Enabled),
                          focus=bool(opt.state & S.State_HasFocus))
            if hasattr(opt, "features") and opt.features & QStyleOptionButton.HasMenu:
                r = QRect(opt.rect.right() - 16, opt.rect.top(), 12, opt.rect.height())
                draw_arrow(p, r, "down", opt.palette.color(QPalette.ButtonText), 3)
            return
        if ce in (S.CE_ScrollBarAddLine, S.CE_ScrollBarSubLine):
            horiz = opt.orientation == Qt.Horizontal
            if ce == S.CE_ScrollBarAddLine:
                d = "right" if horiz else "down"
            else:
                d = "left" if horiz else "up"
            st = _state(opt)
            if opt.minimum == opt.maximum:
                st = DISABLED
            t.draw_sb_arrow(p, opt.rect, d, st)
            return
        if ce in (S.CE_ScrollBarAddPage, S.CE_ScrollBarSubPage):
            t.draw_sb_track(p, opt.rect, opt.orientation == Qt.Horizontal, bool(opt.state & S.State_Sunken))
            return
        if ce == S.CE_ScrollBarSlider:
            if opt.minimum == opt.maximum:
                t.draw_sb_track(p, opt.rect, opt.orientation == Qt.Horizontal)
                return
            t.draw_sb_thumb(p, opt.rect, opt.orientation == Qt.Horizontal, _state(opt))
            return
        if ce in (S.CE_ScrollBarFirst, S.CE_ScrollBarLast):
            return
        if ce == S.CE_ProgressBarGroove:
            t.draw_progress_track(p, opt.rect)
            return
        if ce == S.CE_ProgressBarContents:
            self._draw_progress(p, opt)
            return
        if ce == S.CE_ProgressBarLabel:
            return
        if ce == S.CE_TabBarTabShape:
            selected = bool(opt.state & S.State_Selected)
            r = QRect(opt.rect)
            if not selected:
                r.adjust(0, 2, 0, 0)
            else:
                first = opt.position in (QStyleOptionTab.Beginning, QStyleOptionTab.OnlyOneTab)
                r.adjust(0 if first else -1, 0, 1, 1)
            t.draw_tab(p, r, selected, _state(opt))
            return
        if ce == S.CE_HeaderSection:
            st = PRESSED if opt.state & S.State_Sunken else HOVER if opt.state & S.State_MouseOver else NORMAL
            t.draw_header_section(p, opt.rect, st)
            return
        if ce == S.CE_HeaderEmptyArea:
            t.draw_header_section(p, opt.rect, NORMAL)
            return
        if ce == S.CE_MenuBarItem:
            self._draw_menubar_item(p, opt, widget)
            return
        if ce == S.CE_MenuBarEmptyArea:
            p.fillRect(opt.rect, t.color("menubar"))
            return
        if ce == S.CE_MenuItem:
            self._draw_menu_item(p, opt, widget)
            return
        if ce in (S.CE_MenuEmptyArea, S.CE_MenuTearoff, S.CE_MenuScroller):
            p.fillRect(opt.rect, t.color("menu"))
            return
        if ce == S.CE_ComboBoxLabel:
            if (opt.state & S.State_HasFocus) and not opt.editable and opt.state & S.State_Enabled:
                o2 = type(opt)(opt)
                o2.palette.setColor(QPalette.ButtonText, t.color("highlight_text"))
                o2.palette.setColor(QPalette.Text, t.color("highlight_text"))
                return super().drawControl(ce, o2, p, widget)
            return super().drawControl(ce, opt, p, widget)
        if ce == S.CE_Splitter:
            p.fillRect(opt.rect, t.color("window"))
            return
        if ce == S.CE_SizeGrip:
            self._draw_size_grip(p, opt.rect)
            return
        if ce == S.CE_ToolBar:
            p.fillRect(opt.rect, t.color("window"))
            return
        super().drawControl(ce, opt, p, widget)

    def _draw_size_grip(self, p, r):
        p.save()
        for i in range(3):
            for j in range(i + 1):
                x = r.right() - 3 - (i - j) * 4
                y = r.bottom() - 3 - j * 4
                p.fillRect(QRect(x - 1, y - 1, 2, 2), QColor("#ffffff"))
                p.fillRect(QRect(x - 2, y - 2, 2, 2), QColor("#a7b3b1"))
        p.restore()

    def _draw_progress(self, p, opt):
        t = self.theme
        r = QRect(opt.rect).adjusted(3, 3, -3, -3)
        if opt.maximum == opt.minimum:  # tryb nieokreślony — wędrujący blok
            span = r.width()
            pos = int((time.monotonic() * 120) % (span + 40)) - 40
            x = r.left() + pos
            for i in range(3):
                cr = QRect(x + i * 10, r.top(), 8, r.height()).intersected(r)
                if cr.width() > 0:
                    t.draw_progress_chunk(p, cr)
            return
        frac = (opt.progress - opt.minimum) / float(opt.maximum - opt.minimum)
        frac = max(0.0, min(1.0, frac))
        horiz = getattr(opt, "orientation", Qt.Horizontal) == Qt.Horizontal
        if horiz:
            w = int(r.width() * frac)
            x = r.left()
            while x < r.left() + w:
                cw = min(8, r.left() + w - x)
                t.draw_progress_chunk(p, QRect(x, r.top(), cw, r.height()))
                x += 10
        else:
            h = int(r.height() * frac)
            y = r.bottom()
            while y > r.bottom() - h:
                t.draw_progress_chunk(p, QRect(r.left(), y - 8, r.width(), 8))
                y -= 10

    def _draw_menubar_item(self, p, opt, widget):
        t = self.theme
        p.fillRect(opt.rect, t.color("menubar"))
        selected = (opt.state & S.State_Selected) and (opt.state & S.State_Enabled)
        if selected:
            t.draw_menu_highlight(p, opt.rect, True)
        col = t.color("highlight_text") if selected else (opt.palette.color(QPalette.ButtonText)
                                                          if opt.state & S.State_Enabled else t.color("gray_text"))
        p.setPen(col)
        flags = Qt.AlignCenter | Qt.TextShowMnemonic | Qt.TextSingleLine
        p.setFont(t.font("menu"))
        p.drawText(opt.rect, flags, opt.text)

    def _draw_menu_item(self, p, opt, widget):
        t = self.theme
        r = QRect(opt.rect)
        p.fillRect(r, t.color("menu"))
        if opt.menuItemType == QStyleOptionMenuItem.Separator:
            y = r.center().y()
            p.setPen(QColor("#c5cfcf"))
            p.drawLine(r.left() + 1, y, r.right() - 1, y)
            p.setPen(QColor("#ffffff"))
            p.drawLine(r.left() + 1, y + 1, r.right() - 1, y + 1)
            return
        enabled = bool(opt.state & S.State_Enabled)
        selected = bool(opt.state & S.State_Selected) and enabled
        if opt.state & S.State_Selected:
            if enabled:
                t.draw_menu_highlight(p, r, False)
        text_col = t.color("highlight_text") if selected else (t.color("menu_text") if enabled else t.color("gray_text"))
        check_w = 22
        # znacznik/ikona
        icon_rect = QRect(r.left() + 2, r.top(), check_w - 2, r.height())
        if opt.checkType != QStyleOptionMenuItem.NotCheckable and opt.checked:
            p.save()
            p.setRenderHint(QPainter.Antialiasing, True)
            c = icon_rect.center()
            if opt.checkType == QStyleOptionMenuItem.Exclusive:
                p.setBrush(text_col)
                p.setPen(Qt.NoPen)
                p.drawEllipse(QPointF(c), 3.0, 3.0)
            else:
                p.setPen(QPen(text_col, 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                p.drawPolyline([QPointF(c.x() - 4, c.y()), QPointF(c.x() - 1, c.y() + 3), QPointF(c.x() + 4, c.y() - 3)])
            p.restore()
        elif not opt.icon.isNull():
            mode = 1 if not enabled else 0  # QIcon.Disabled = 1
            from PySide6.QtGui import QIcon
            pm = opt.icon.pixmap(16, 16, QIcon.Disabled if not enabled else QIcon.Normal)
            p.drawPixmap(icon_rect.left() + (icon_rect.width() - 16) // 2, r.top() + (r.height() - 16) // 2, pm)
        # tekst
        text = opt.text
        shortcut = ""
        if "\t" in text:
            text, shortcut = text.split("\t", 1)
        f = t.font("menu")
        if opt.menuItemType == QStyleOptionMenuItem.DefaultItem or opt.font.bold():
            f.setBold(True)
        p.setFont(f)
        p.setPen(text_col)
        tr = QRect(r.left() + check_w + 4, r.top(), r.width() - check_w - 24, r.height())
        flags = Qt.AlignVCenter | Qt.AlignLeft | Qt.TextShowMnemonic | Qt.TextSingleLine
        if not (self.styleHint(S.SH_UnderlineShortcut, opt, widget)):
            flags |= Qt.TextHideMnemonic
        p.drawText(tr, flags, text)
        if shortcut:
            p.drawText(tr.adjusted(0, 0, -4, 0), Qt.AlignVCenter | Qt.AlignRight | Qt.TextSingleLine, shortcut)
        if opt.menuItemType == QStyleOptionMenuItem.SubMenu:
            ar = QRect(r.right() - 16, r.top(), 12, r.height())
            draw_arrow(p, ar, "right", text_col, 3.2)

    # ------------------------------------------------------------------ złożone
    def drawComplexControl(self, cc, opt, p, widget=None):
        t = self.theme
        if cc == S.CC_ComboBox:
            r = QRect(opt.rect)
            enabled = bool(opt.state & S.State_Enabled)
            p.fillRect(r.adjusted(1, 1, -1, -1), opt.palette.brush(QPalette.Base) if enabled else t.color("window").lighter(104))
            t.draw_edit_frame(p, r, bool(opt.state & S.State_HasFocus) and opt.editable, not enabled)
            ar = self.subControlRect(cc, opt, S.SC_ComboBoxArrow, widget)
            st = DISABLED if not enabled else PRESSED if (opt.state & S.State_Sunken and opt.activeSubControls & S.SC_ComboBoxArrow) \
                else HOVER if opt.state & S.State_MouseOver else NORMAL
            t.draw_combo_button(p, ar, st)
            if (opt.state & S.State_HasFocus) and not opt.editable and enabled:
                er = self.subControlRect(cc, opt, S.SC_ComboBoxEditField, widget)
                p.fillRect(er.adjusted(0, 1, 0, -1), t.color("highlight"))
            return
        if cc == S.CC_SpinBox:
            r = QRect(opt.rect)
            enabled = bool(opt.state & S.State_Enabled)
            p.fillRect(r.adjusted(1, 1, -1, -1), opt.palette.brush(QPalette.Base) if enabled else t.color("window").lighter(104))
            t.draw_edit_frame(p, r, bool(opt.state & S.State_HasFocus), not enabled)
            for sc, d in ((S.SC_SpinBoxUp, "up"), (S.SC_SpinBoxDown, "down")):
                br = self.subControlRect(cc, opt, sc, widget)
                st = DISABLED if not enabled else PRESSED if (opt.activeSubControls & sc and opt.state & S.State_Sunken) \
                    else HOVER if (opt.activeSubControls & sc and opt.state & S.State_MouseOver) else NORMAL
                t.draw_combo_button(p, br, st, d)
            return
        if cc == S.CC_Slider:
            horiz = opt.orientation == Qt.Horizontal
            groove = self.subControlRect(cc, opt, S.SC_SliderGroove, widget)
            handle = self.subControlRect(cc, opt, S.SC_SliderHandle, widget)
            t.draw_slider_groove(p, groove, horiz)
            if opt.subControls & S.SC_SliderTickmarks and opt.tickPosition:
                self._draw_ticks(p, opt, groove, handle, horiz)
            st = DISABLED if not (opt.state & S.State_Enabled) else PRESSED if (opt.activeSubControls & S.SC_SliderHandle and opt.state & S.State_Sunken) \
                else HOVER if (opt.activeSubControls & S.SC_SliderHandle and opt.state & S.State_MouseOver) else NORMAL
            t.draw_slider_handle(p, handle, horiz, st)
            return
        super().drawComplexControl(cc, opt, p, widget)

    def _draw_ticks(self, p, opt, groove, handle, horiz):
        span = (opt.maximum - opt.minimum) or 1
        interval = opt.tickInterval or opt.pageStep or 1
        p.save()
        p.setPen(QColor("#7a8a8c"))
        hl = self.pixelMetric(S.PM_SliderLength, opt)
        v = opt.minimum
        while v <= opt.maximum:
            pos = S.sliderPositionFromValue(opt.minimum, opt.maximum, v,
                                            (groove.width() if horiz else groove.height()) - hl, opt.upsideDown)
            if horiz:
                x = groove.left() + pos + hl // 2
                p.drawLine(x, opt.rect.bottom() - 4, x, opt.rect.bottom() - 1)
            else:
                y = groove.top() + pos + hl // 2
                p.drawLine(opt.rect.right() - 4, y, opt.rect.right() - 1, y)
            v += interval
        p.restore()

    def subControlRect(self, cc, opt, sc, widget=None):
        if cc == S.CC_ComboBox:
            r = QRect(opt.rect)
            if sc == S.SC_ComboBoxArrow:
                return QRect(r.right() - 17, r.top() + 1, 17, r.height() - 2)
            if sc == S.SC_ComboBoxEditField:
                return QRect(r.left() + 3, r.top() + 2, r.width() - 23, r.height() - 4)
            if sc == S.SC_ComboBoxFrame:
                return r
        if cc == S.CC_SpinBox:
            r = QRect(opt.rect)
            bw = 16
            h = (r.height() - 2) // 2
            if sc == S.SC_SpinBoxUp:
                return QRect(r.right() - bw, r.top() + 1, bw, h)
            if sc == S.SC_SpinBoxDown:
                return QRect(r.right() - bw, r.top() + 1 + h, bw, r.height() - 2 - h)
            if sc == S.SC_SpinBoxEditField:
                return QRect(r.left() + 3, r.top() + 2, r.width() - bw - 6, r.height() - 4)
            if sc == S.SC_SpinBoxFrame:
                return r
        if cc == S.CC_Slider:
            r = QRect(opt.rect)
            horiz = opt.orientation == Qt.Horizontal
            hl = self.pixelMetric(S.PM_SliderLength, opt, widget)
            th = 20
            if sc == S.SC_SliderGroove:
                if horiz:
                    return QRect(r.left(), r.top(), r.width(), th)
                return QRect(r.left(), r.top(), th, r.height())
            if sc == S.SC_SliderHandle:
                length = (r.width() if horiz else r.height()) - hl
                pos = S.sliderPositionFromValue(opt.minimum, opt.maximum, opt.sliderPosition, length, opt.upsideDown)
                if horiz:
                    return QRect(r.left() + pos, r.top() + 1, hl, th - 1)
                return QRect(r.left() + 1, r.top() + pos, th - 1, hl)
        return super().subControlRect(cc, opt, sc, widget)

    def sizeFromContents(self, ct, opt, size, widget=None):
        if ct == S.CT_MenuItem:
            if opt.menuItemType == QStyleOptionMenuItem.Separator:
                return QSize(10, 9)
            mf = self.theme.font("menu")
            if opt.font.bold():
                mf.setBold(True)
            fm = QFontMetrics(mf)
            text = opt.text
            shortcut = ""
            if "\t" in text:
                text, shortcut = text.split("\t", 1)
            w = 22 + 4 + fm.horizontalAdvance(text.replace("&", "")) + 24
            if shortcut:
                w += fm.horizontalAdvance(shortcut) + 28
            return QSize(max(w, 120), max(self.theme.metrics["menu_item_h"] - 2, fm.height() + 6))
        if ct == S.CT_MenuBarItem:
            fm = QFontMetrics(self.theme.font("menu"))
            return QSize(fm.horizontalAdvance(opt.text.replace("&", "")) + 14, fm.height() + 6)
        if ct == S.CT_PushButton:
            s = super().sizeFromContents(ct, opt, size, widget)
            if opt.text:
                return QSize(max(75, s.width()), max(23, s.height()))
            return QSize(max(23, s.width()), max(23, s.height()))
        if ct == S.CT_ComboBox:
            s = super().sizeFromContents(ct, opt, size, widget)
            return QSize(s.width() + 6, max(21, s.height()))
        if ct == S.CT_LineEdit:
            s = super().sizeFromContents(ct, opt, size, widget)
            return QSize(s.width(), max(21, s.height()))
        if ct == S.CT_SpinBox:
            s = super().sizeFromContents(ct, opt, size, widget)
            return QSize(s.width() + 4, max(21, s.height()))
        if ct == S.CT_TabBarTab:
            s = super().sizeFromContents(ct, opt, size, widget)
            return QSize(s.width(), max(21, s.height()))
        return super().sizeFromContents(ct, opt, size, widget)

    def subElementRect(self, se, opt, widget=None):
        r = super().subElementRect(se, opt, widget)
        if se == S.SE_TabWidgetTabBar:
            # zakładki zaczynają się 2 px od krawędzi karty — wybrana (szersza) zakładka nie jest ucinana
            r = QRect(r)
            r.translate(2, 0)
        return r
