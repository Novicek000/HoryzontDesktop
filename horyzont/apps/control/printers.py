"""Drukarki i faksy (CUPS)."""
import shutil
import subprocess

from ...common import dialogs, launcher
from ...i18n import plain, tr
from .common import run
from .folderwin import FolderWindow, entry, header


def printers():
    out = []
    if not shutil.which("lpstat"):
        return out, None
    rc, txt = run(["lpstat", "-p"])
    rc2, d = run(["lpstat", "-d"])
    default = d.split(":", 1)[1].strip() if ":" in d else None
    for line in txt.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] in ("printer", "drukarka"):
            name = parts[1]
            status = "idle" if "idle" in line or "bezczynn" in line else "disabled" if "disabled" in line or "wyłącz" in line else "busy"
            out.append((name, status))
    return out, default


class PrintersWindow(FolderWindow):
    title_key = "printers"
    icon = "printer"

    def load_items(self):
        lst, default = printers()
        items = []
        if not lst:
            items.append(header(plain("pr_none")))
        for name, status in lst:
            rc, jobs = run(["lpstat", "-o", name])
            n = len([l for l in jobs.splitlines() if l.strip()])
            st = plain("pr_ready") if status == "idle" else plain("pr_offline") if status == "disabled" else plain("pr_printing")
            info = (plain("pr_default") + " — " if name == default else "") + tr("pr_jobs", n)
            items.append(entry(name, "printer", st, info, key=name, default=name == default, details=[info]))
        return items

    def fill_tasks(self, pane, sel):
        s = pane.add_section(plain("pr_tasks"), special=True)
        s.add_link("printer", plain("pr_add"), self.add_printer)
        if sel:
            name = sel[0].path
            s.add_link("star", plain("pr_set_default"), lambda: self.set_default(name))
            s.add_link("delete", plain("pr_cancel_all"), lambda: self.cancel_all(name))
            s.add_link("properties", plain("pr_properties"), self.add_printer)
        self.other_places(pane)
        self.details(pane, sel)

    def activate(self, it):
        rc, jobs = run(["lpstat", "-o", it.path])
        dialogs.message(self, it.label, jobs.strip() or plain("pr_no_jobs"), "printer")

    def item_menu(self, m, it):
        m.addAction(tr("open"), lambda: self.activate(it))
        m.addAction(plain("pr_set_default"), lambda: self.set_default(it.path))
        m.addAction(plain("pr_cancel_all"), lambda: self.cancel_all(it.path))
        m.addSeparator()
        m.addAction(tr("properties"), self.add_printer)

    def set_default(self, name):
        subprocess.run(["lpoptions", "-d", name], capture_output=True)
        self.refresh()

    def cancel_all(self, name):
        subprocess.run(["cancel", "-a", name], capture_output=True)
        self.refresh()

    def add_printer(self):
        for c in (["system-config-printer"], ["gnome-control-center", "printers"]):
            if shutil.which(c[0]):
                launcher._spawn(c)
                return
        launcher.xdg_open("http://localhost:631/admin")


def open_printers(page=None, parent=None):
    w = PrintersWindow()
    if page == "add":
        w.add_printer()
    return w
