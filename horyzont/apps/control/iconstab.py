"""Karta „Ikony” we Właściwościach ekranu — zestawy ikon .msicon."""
import os

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QComboBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QPushButton)

from ... import config
from ...common import dialogs
from ...i18n import lang_code, plain, tr
from ...theme import iconcache, iconpacks

SAMPLE = ["computer", "documents", "network", "recycle_empty", "recycle_full", "folder", "folder_open",
          "folder_zip", "drive_system", "drive_cd", "file_text", "file_image", "notepad", "control_panel",
          "taskmgr", "cmd", "help", "search", "logo", "shutdown"]


def build(dlg):
    w, lay = dlg.add_tab(plain("dp_icons"))
    g = QGroupBox(plain("ip_pack"))
    gl = QGridLayout(g)
    dlg.ip_combo = QComboBox()
    gl.addWidget(dlg.ip_combo, 0, 0, 1, 3)
    dlg.ip_info = QLabel()
    dlg.ip_info.setWordWrap(True)
    gl.addWidget(dlg.ip_info, 1, 0, 1, 3)
    inst = QPushButton(plain("ip_install"))
    rem = QPushButton(plain("delete").replace("&", ""))
    exp = QPushButton(plain("ip_export"))
    gl.addWidget(inst, 2, 0)
    gl.addWidget(rem, 2, 1)
    gl.addWidget(exp, 2, 2)
    lay.addWidget(g)
    lay.addWidget(QLabel(plain("ip_preview")))
    dlg.ip_list = QListWidget()
    dlg.ip_list.setViewMode(QListWidget.IconMode)
    dlg.ip_list.setIconSize(QSize(32, 32))
    dlg.ip_list.setGridSize(QSize(64, 56))
    dlg.ip_list.setMovement(QListWidget.Static)
    dlg.ip_list.setResizeMode(QListWidget.Adjust)
    lay.addWidget(dlg.ip_list, 1)
    howto = QLabel(f'<a href="#">{plain("ip_howto")}</a>')
    howto.linkActivated.connect(lambda *_: show_howto(dlg))
    lay.addWidget(howto)
    dlg.pending.setdefault("icon_pack", config.get("icon_pack", ""))

    def fill(select=None):
        dlg.ip_combo.blockSignals(True)
        dlg.ip_combo.clear()
        dlg.ip_combo.addItem(iconcache.icon("logo"), plain("ip_builtin"), "")
        for key, meta, n in iconpacks.installed():
            dlg.ip_combo.addItem(iconcache.icon("icon_pack"), meta["name"], key)
        cur = dlg.pending.get("icon_pack", "") if select is None else select
        dlg.ip_combo.setCurrentIndex(max(0, dlg.ip_combo.findData(cur)))
        dlg.ip_combo.blockSignals(False)
        changed_pack()

    def changed_pack(*_):
        key = dlg.ip_combo.currentData() or ""
        dlg.pending["icon_pack"] = key
        rem.setEnabled(bool(key))
        if key:
            meta = next((m for k, m, n in iconpacks.installed() if k == key), {})
            n = next((n for k, m, n in iconpacks.installed() if k == key), 0)
            parts = [tr("ip_icons_n", n)]
            if meta.get("author"):
                parts.append(tr("ip_author", meta["author"]))
            if meta.get("version"):
                parts.append(tr("ip_version", meta["version"]))
            if meta.get("description"):
                parts.append(meta["description"])
            dlg.ip_info.setText(" · ".join(parts))
        else:
            dlg.ip_info.setText(plain("ip_builtin_desc"))
        # podgląd wybranego zestawu (bez zapisywania ustawień)
        old = config.get("icon_pack", "")
        config.load()["icon_pack"] = key
        iconcache.reset()
        dlg.ip_list.clear()
        for name in SAMPLE:
            it = QListWidgetItem(QIcon_for(name), "")
            it.setToolTip(name)
            dlg.ip_list.addItem(it)
        config.load()["icon_pack"] = old
        iconcache.reset()

    def QIcon_for(name):
        from PySide6.QtGui import QIcon
        return QIcon(iconcache.pixmap(name, 32))

    def do_install():
        fn = dialogs.open_file(dlg, plain("ip_install"), os.path.expanduser("~/Downloads"),
                               plain("ip_filter") + " (*.msicon *.zip)")
        if fn:
            install_file(dlg, fn, fill)

    def do_remove():
        key = dlg.ip_combo.currentData()
        if not key:
            return
        if dialogs.message(dlg, plain("display_props"), tr("ip_remove_q", dlg.ip_combo.currentText()), "question",
                           ("yes", "no")) != "yes":
            return
        iconpacks.remove(key)
        if config.get("icon_pack", "") == key:
            config.set("icon_pack", "")
        dlg.pending["icon_pack"] = ""
        fill("")

    def do_export():
        d = dialogs.choose_dir(dlg, plain("ip_export"), config.user_dir("DOCUMENTS"))
        if not d:
            return
        target = os.path.join(d, "szablon-ikon-horyzont")
        iconpacks.export_template(target, lang_code())
        dialogs.message(dlg, plain("display_props"), tr("ip_exported", target), "info")
        QDesktopServices.openUrl(QUrl.fromLocalFile(target))

    dlg.ip_combo.currentIndexChanged.connect(lambda *_: (changed_pack(), dlg.changed()))
    inst.clicked.connect(do_install)
    rem.clicked.connect(do_remove)
    exp.clicked.connect(do_export)
    dlg._ip_fill = fill
    fill()
    return w


def install_file(dlg, fn, fill=None):
    try:
        key, count, unknown = iconpacks.install(fn)
    except Exception as e:
        dialogs.message(dlg, plain("display_props"), tr("ip_install_failed", os.path.basename(fn)) + f"\n\n{e}", "error")
        return None
    msg = tr("ip_installed", count)
    if unknown:
        msg += "\n\n" + tr("ip_unknown", ", ".join(unknown[:15]) + ("…" if len(unknown) > 15 else ""))
    dialogs.message(dlg, plain("display_props"), msg, "info" if not unknown else "warning")
    if fill:
        fill(key)
        dlg.changed()
    return key


def show_howto(parent):
    from ...common.window import HDialog
    from PySide6.QtWidgets import QTextBrowser, QVBoxLayout
    d = HDialog(plain("ip_howto"), "icon_pack", parent)
    lay = QVBoxLayout(d.body())
    lay.setContentsMargins(8, 8, 8, 8)
    tb = QTextBrowser()
    tb.setOpenExternalLinks(True)
    pl = lang_code() == "pl"
    intro = ("<h3>Jak przygotować zestaw ikon (.msicon)</h3>"
             "<ol><li>Kliknij <b>Eksportuj szablon...</b> — powstanie folder ze wszystkimi ikonami Horyzontu (SVG), "
             "plikiem <code>manifest.ini</code> i listą nazw.</li>"
             "<li>Podmień pliki w folderze <code>icons/</code> na własne. Nazwa pliku = nazwa ikony z listy poniżej. "
             "Możesz użyć SVG, PNG (najlepiej 48×48 lub 256×256) albo ICO. Osobne rozmiary: <code>nazwa@16.png</code>, "
             "<code>nazwa@32.png</code>, <code>nazwa@48.png</code>. Ikon, których nie podmienisz, możesz po prostu usunąć — "
             "zostaną wzięte z zestawu wbudowanego.</li>"
             "<li>Uzupełnij <code>manifest.ini</code> (nazwa, autor, wersja).</li>"
             "<li>Spakuj folder poleceniem <code>horyzont-msicon nazwa-folderu</code> (skrypt w pakiecie: "
             "<code>tools/make-msicon.sh</code>). .msicon to zwykły ZIP ze zmienionym rozszerzeniem.</li>"
             "<li>Kliknij <b>Instaluj...</b> albo dwukrotnie kliknij plik .msicon w Eksploratorze.</li></ol>"
             "<h3>Nazwy ikon</h3>") if pl else (
             "<h3>How to make an icon pack (.msicon)</h3><ol><li>Click <b>Export template...</b>.</li>"
             "<li>Replace files in <code>icons/</code> — the file name is the icon name below (SVG, PNG or ICO; "
             "optional sizes <code>name@16.png</code>…).</li><li>Fill in <code>manifest.ini</code>.</li>"
             "<li>Pack it with <code>tools/make-msicon.sh folder</code> (a ZIP with a different extension).</li>"
             "<li>Click <b>Install...</b>.</li></ol><h3>Icon names</h3>")
    import html
    table = "<pre>" + html.escape(iconpacks.names_table(lang_code())) + "</pre>"
    tb.setHtml(intro + table)
    lay.addWidget(tb)
    d.resize(620, 560)
    d.exec()
