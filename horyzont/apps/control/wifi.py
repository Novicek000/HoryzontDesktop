"""Okno „Połączenie sieci bezprzewodowej” — wybór sieci Wi-Fi i łączenie (nmcli)."""
from PySide6.QtCore import QProcess, QRect, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import (QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QProgressBar,
                               QPushButton, QSplitter, QStyledItemDelegate, QVBoxLayout,
                               QWidget)

from ...common import dialogs, launcher, netman
from ...common.taskpane import TaskPane
from ...common.window import HDialog, HWindow
from ...i18n import plain, tr
from ...theme import iconcache
from ...theme.manager import current

NetRole = Qt.UserRole + 1


class NetDelegate(QStyledItemDelegate):
    def sizeHint(self, opt, idx):
        n = idx.data(NetRole)
        return QSize(300, 76 if n and n.get("_expanded") else 56)

    def paint(self, p, opt, idx):
        from PySide6.QtWidgets import QStyle
        n = idx.data(NetRole)
        if n is None:
            return
        p.save()
        r = opt.rect
        selected = bool(opt.state & QStyle.State_Selected)
        t = current()
        if selected:
            p.fillRect(r.adjusted(1, 1, -1, -1), t.color("highlight").lighter(175))
            p.setPen(t.color("highlight"))
            p.drawRect(r.adjusted(1, 1, -2, -2))
        p.drawPixmap(r.left() + 8, r.top() + 10, iconcache.pixmap("network_wireless", 32))
        f = QFont(t.font("normal"))
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("#000000"))
        p.drawText(QRect(r.left() + 50, r.top() + 6, r.width() - 200, 18), Qt.AlignLeft | Qt.AlignVCenter,
                   QFontMetrics(f).elidedText(n["ssid"], Qt.ElideRight, r.width() - 200))
        p.setFont(t.font("normal"))
        sec_txt = netman.describe_security(n["security"])
        if n["security"]:
            p.drawPixmap(r.left() + 50, r.top() + 27, iconcache.pixmap("lock", 16))
        avail = r.width() - 70 - 200
        p.drawText(QRect(r.left() + 70, r.top() + 26, avail, 18), Qt.AlignLeft | Qt.AlignVCenter,
                   QFontMetrics(p.font()).elidedText(sec_txt, Qt.ElideRight, avail))
        if n.get("active"):
            p.setFont(f)
            p.setPen(QColor("#1d6b28"))
            p.drawText(QRect(r.right() - 150, r.top() + 6, 110, 18), Qt.AlignRight | Qt.AlignVCenter, plain("wifi_connected"))
            p.drawPixmap(r.right() - 36, r.top() + 6, iconcache.pixmap("star", 16))
        elif n.get("saved"):
            p.setPen(QColor("#555555"))
            p.drawText(QRect(r.right() - 150, r.top() + 6, 140, 18), Qt.AlignRight | Qt.AlignVCenter, plain("wifi_saved"))
        # siła sygnału — 5 słupków
        p.setPen(QColor("#555555"))
        p.setFont(t.font("normal"))
        p.drawText(QRect(r.right() - 186, r.top() + 26, 98, 18), Qt.AlignRight | Qt.AlignVCenter, plain("wifi_signal"))
        bars = max(1, round(n["signal"] / 20)) if n["signal"] > 0 else 0
        for i in range(5):
            h = 4 + i * 3
            br = QRect(r.right() - 80 + i * 8, r.top() + 42 - h, 6, h)
            p.fillRect(br, QColor("#3ab54a") if i < bars else QColor("#d0d6d9"))
            p.setPen(QColor("#1d6b28") if i < bars else QColor("#a8b0b4"))
            p.drawRect(br.adjusted(0, 0, -1, -1))
        if n.get("_expanded"):
            p.setPen(QColor("#333333"))
            txt = plain("wifi_hint_secured") if n["security"] else plain("wifi_hint_open")
            p.drawText(QRect(r.left() + 50, r.top() + 46, r.width() - 70, 28), Qt.AlignLeft | Qt.TextWordWrap, txt)
        p.restore()


class KeyDialog(HDialog):
    def __init__(self, ssid, parent=None, hidden=False):
        super().__init__(plain("wifi_conn_title"), "network_wireless", parent, help_button=False)
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)
        g = QGridLayout()
        row = 0
        self.ssid = None
        if hidden:
            lay.addWidget(_wrap(plain("wifi_hidden_desc")))
            g.addWidget(QLabel(plain("wifi_ssid")), row, 0)
            self.ssid = QLineEdit()
            g.addWidget(self.ssid, row, 1)
            row += 1
            g.addWidget(QLabel(plain("wifi_security")), row, 0)
            self.sec = QComboBox()
            self.sec.addItem(plain("wifi_sec_wpa"), "wpa-psk")
            self.sec.addItem(plain("wifi_sec_none"), "none")
            g.addWidget(self.sec, row, 1)
            row += 1
        else:
            lay.addWidget(_wrap(tr("wifi_key_desc", ssid)))
        g.addWidget(QLabel(plain("wifi_key")), row, 0)
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.Password)
        g.addWidget(self.key, row, 1)
        row += 1
        g.addWidget(QLabel(plain("wifi_key_confirm")), row, 0)
        self.key2 = QLineEdit()
        self.key2.setEchoMode(QLineEdit.Password)
        g.addWidget(self.key2, row, 1)
        row += 1
        lay.addLayout(g)
        show = QCheckBox(plain("wifi_show_chars"))
        show.toggled.connect(lambda on: [e.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password)
                                         for e in (self.key, self.key2)])
        lay.addWidget(show)
        btns = QHBoxLayout()
        btns.addStretch(1)
        ok = QPushButton(plain("wifi_connect"))
        ok.setDefault(True)
        ok.clicked.connect(self._ok)
        ca = QPushButton(plain("cancel"))
        ca.clicked.connect(self.reject)
        btns.addWidget(ok)
        btns.addWidget(ca)
        lay.addLayout(btns)
        self.setFixedWidth(420)
        (self.ssid or self.key).setFocus()

    def _ok(self):
        if self.ssid is not None and not self.ssid.text().strip():
            return
        need_key = self.ssid is None or self.sec.currentData() != "none"
        if need_key and self.key.text() != self.key2.text():
            dialogs.message(self, plain("wifi_conn_title"), plain("wifi_key_mismatch"), "warning")
            return
        if need_key and len(self.key.text()) < 8:
            dialogs.message(self, plain("wifi_conn_title"), plain("wifi_key_short"), "warning")
            return
        self.accept()


def _wrap(t):
    l = QLabel(t)
    l.setWordWrap(True)
    return l


class ConnectProgress(HDialog):
    """Okienko „Trwa łączenie…” — nmcli działa asynchronicznie."""

    def __init__(self, ssid, args, parent=None):
        super().__init__(plain("wifi_conn_title"), "network_wireless", parent, help_button=False)
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(14, 14, 14, 12)
        row = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(iconcache.pixmap("network_wireless", 32))
        row.addWidget(ic)
        self.lbl = _wrap(tr("wifi_connecting", ssid))
        row.addWidget(self.lbl, 1)
        lay.addLayout(row)
        bar = QProgressBar()
        bar.setRange(0, 0)
        bar.setTextVisible(False)
        lay.addWidget(bar)
        b = QHBoxLayout()
        b.addStretch(1)
        ca = QPushButton(plain("cancel"))
        ca.clicked.connect(self._cancel)
        b.addWidget(ca)
        lay.addLayout(b)
        self.setFixedWidth(360)
        self.ok = False
        self.err = ""
        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.MergedChannels)
        self.proc.finished.connect(self._done)
        QTimer.singleShot(0, lambda: self.proc.start("nmcli", args))

    def _cancel(self):
        self.proc.kill()
        self.reject()

    def _done(self, code, status):
        out = bytes(self.proc.readAll()).decode("utf-8", "replace").strip()
        self.ok = code == 0
        self.err = out
        self.accept()


def connect_network(parent, net, ifname=None):
    """Łączy z siecią (zapisaną albo nową). Zwraca True po sukcesie."""
    ssid = net["ssid"]
    saved = netman.saved_wifi()
    if ssid in saved:
        args = ["connection", "up", saved[ssid]["uuid"]]
    elif net["security"]:
        d = KeyDialog(ssid, parent)
        if not d.exec():
            return False
        args = ["device", "wifi", "connect", ssid, "password", d.key.text()]
    else:
        args = ["device", "wifi", "connect", ssid]
    if ifname:
        args += ["ifname", ifname]
    pr = ConnectProgress(ssid, args, parent)
    pr.exec()
    if pr.ok:
        return True
    if pr.err:
        low = pr.err.lower()
        if "secrets were required" in low or "802.1x" in low or "password" in low:
            msg = plain("wifi_wrong_key")
            if ssid not in saved:
                # nieudana nowa konfiguracja — nie zostawiamy jej w ustawieniach
                netman.con_delete(ssid)
        else:
            msg = pr.err
        dialogs.message(parent, plain("wifi_conn_title"), tr("wifi_failed", ssid) + "\n\n" + msg, "warning")
    return False


class WifiWindow(HWindow):
    def __init__(self):
        super().__init__(plain("wifi_title"), "network_wireless")
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(0, 0, 0, 0)
        split = QSplitter(Qt.Horizontal)
        self.pane = TaskPane()
        split.addWidget(self.pane)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(14, 12, 14, 12)
        head = QLabel(plain("wifi_choose"))
        f = QFont(current().font("normal"))
        f.setPointSizeF((f.pointSizeF() if f.pointSizeF() > 0 else 9) * 1.5)
        f.setBold(True)
        head.setFont(f)
        head.setStyleSheet("color: #1f4f8a;")
        rl.addWidget(head)
        rl.addWidget(_wrap(plain("wifi_choose_desc")))
        self.list = QListWidget()
        self.list.setItemDelegate(NetDelegate(self.list))
        self.list.setUniformItemSizes(False)
        self.list.currentItemChanged.connect(self._sel)
        self.list.itemDoubleClicked.connect(lambda *_: self.connect_selected())
        rl.addWidget(self.list, 1)
        self.empty = _wrap("")
        self.empty.hide()
        rl.addWidget(self.empty)
        brow = QHBoxLayout()
        brow.addStretch(1)
        self.btn = QPushButton(plain("wifi_connect"))
        self.btn.clicked.connect(self.connect_selected)
        brow.addWidget(self.btn)
        rl.addLayout(brow)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        split.setSizes([210, 470])
        lay.addWidget(split)
        self.resize(720, 500)
        self.dev = None
        self._fill_pane()
        QTimer.singleShot(50, lambda: self.refresh("no"))
        QTimer.singleShot(400, lambda: self.refresh("auto"))

    def _fill_pane(self):
        p = self.pane
        p.clear()
        s = p.add_section(plain("wifi_tasks"), special=True)
        s.add_link("refresh", plain("wifi_refresh"), lambda: self.refresh("yes"))
        s.add_link("network_wireless", plain("wifi_hidden"), self.connect_hidden)
        on = netman.wifi_enabled()
        s.add_link("tray_wifi_off" if on else "network_wireless", plain("wifi_turn_off") if on else plain("wifi_turn_on"),
                   self.toggle_radio)
        r = p.add_section(plain("related_tasks"))
        r.add_link("network_conn", plain("ap_network"), lambda: launcher.start_builtin("control", ["network"]))
        r.add_link("properties", plain("wifi_forget_title"), self.forget_selected)

    def refresh(self, rescan="auto"):
        devs = netman.wifi_devices()
        self.dev = devs[0]["device"] if devs else None
        self.list.clear()
        if not netman.available():
            self._empty(plain("nc_no_nm"))
            return
        if not devs:
            self._empty(plain("wifi_no_adapter"))
            return
        if not netman.wifi_enabled():
            self._empty(plain("wifi_disabled"))
            return
        saved = netman.saved_wifi()
        nets = netman.wifi_list(rescan)
        for n in nets:
            n["saved"] = n["ssid"] in saved
            it = QListWidgetItem()
            it.setData(NetRole, n)
            self.list.addItem(it)
        self.empty.setVisible(not nets)
        self.empty.setText(plain("wifi_none_found"))
        self.list.setVisible(bool(nets))
        self._sel(self.list.currentItem(), None)

    def _empty(self, text):
        self.list.hide()
        self.empty.setText(text)
        self.empty.show()
        self.btn.setEnabled(False)

    def _sel(self, cur, prev):
        for it in (prev, cur):
            if it is not None:
                n = it.data(NetRole)
                n["_expanded"] = it is cur
                it.setData(NetRole, n)
                it.setSizeHint(QSize(300, 76 if it is cur else 56))
        n = cur.data(NetRole) if cur is not None else None
        self.btn.setEnabled(n is not None)
        self.btn.setText(plain("wifi_disconnect") if n and n.get("active") else plain("wifi_connect"))

    def connect_selected(self):
        it = self.list.currentItem()
        if it is None:
            return
        n = it.data(NetRole)
        if n.get("active"):
            if self.dev:
                netman.nmcli(["device", "disconnect", self.dev])
            QTimer.singleShot(500, lambda: self.refresh("no"))
            return
        if connect_network(self, n, self.dev):
            QTimer.singleShot(300, lambda: self.refresh("no"))

    def connect_hidden(self):
        d = KeyDialog("", self, hidden=True)
        if not d.exec():
            return
        ssid = d.ssid.text().strip()
        args = ["device", "wifi", "connect", ssid]
        if d.sec.currentData() != "none":
            args += ["password", d.key.text()]
        args += ["hidden", "yes"]
        pr = ConnectProgress(ssid, args, self)
        pr.exec()
        if not pr.ok and pr.err:
            dialogs.message(self, plain("wifi_conn_title"), tr("wifi_failed", ssid) + "\n\n" + pr.err, "warning")
        self.refresh("no")

    def toggle_radio(self):
        netman.set_wifi_enabled(not netman.wifi_enabled())
        QTimer.singleShot(1500, lambda: (self._fill_pane(), self.refresh("auto")))

    def forget_selected(self):
        it = self.list.currentItem()
        if it is None:
            dialogs.message(self, plain("wifi_title"), plain("wifi_select_first"), "info")
            return
        n = it.data(NetRole)
        if not n.get("saved"):
            dialogs.message(self, plain("wifi_title"), plain("wifi_not_saved"), "info")
            return
        if dialogs.message(self, plain("wifi_title"), tr("wifi_forget_q", n["ssid"]), "question", ("yes", "no")) == "yes":
            netman.con_delete(n["ssid"])
            self.refresh("no")


def open_wifi(page=None, parent=None):
    return WifiWindow()
