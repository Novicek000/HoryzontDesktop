"""Operacje na plikach: kosz (specyfikacja freedesktop), kopiowanie, schowek."""
import datetime
import os
import shutil
import subprocess
import urllib.parse

from ..i18n import lang_code, plain, tr

TRASH_HOME = os.path.join(os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")), "Trash")


# ------------------------------------------------------------------ nazwy
def unique_name(directory, name, copy_style=False):
    """Zwraca nazwę, która nie istnieje jeszcze w katalogu."""
    if not os.path.exists(os.path.join(directory, name)):
        return name
    base, ext = os.path.splitext(name)
    if os.path.isdir(os.path.join(directory, name)):
        base, ext = name, ""
    i = 1 if copy_style else 2
    while True:
        if copy_style:
            if lang_code() == "pl":
                cand = f"Kopia {base}{ext}" if i == 1 else f"Kopia ({i}) {base}{ext}"
            else:
                cand = f"Copy of {base}{ext}" if i == 1 else f"Copy ({i}) of {base}{ext}"
        else:
            cand = f"{base} ({i}){ext}"
        if not os.path.exists(os.path.join(directory, cand)):
            return cand
        i += 1


def new_folder(directory):
    name = unique_name(directory, plain("new_folder_name"))
    path = os.path.join(directory, name)
    os.makedirs(path)
    return path


def new_text_document(directory):
    name = unique_name(directory, plain("new_text_name"))
    path = os.path.join(directory, name)
    open(path, "w").close()
    return path


def new_shortcut(directory, target, name=None):
    """Skrót jako plik .desktop (typ Link lub Application)."""
    name = name or os.path.basename(target.rstrip("/")) or target
    fn = unique_name(directory, name + ".desktop")
    path = os.path.join(directory, fn)
    with open(path, "w", encoding="utf-8") as f:
        f.write("[Desktop Entry]\nType=Link\n")
        f.write(f"Name={name}\nURL=file://{urllib.parse.quote(os.path.abspath(target))}\n")
        f.write("Icon=folder\n" if os.path.isdir(target) else "")
    os.chmod(path, 0o755)
    return path


# ------------------------------------------------------------------ kosz
def _home_dev():
    try:
        os.makedirs(TRASH_HOME, exist_ok=True)
        return os.stat(TRASH_HOME).st_dev
    except OSError:
        return None


def trash_paths(paths):
    """Przenosi pliki do Kosza. Zwraca listę błędów (ścieżka, komunikat)."""
    errors = []
    hd = _home_dev()
    files_dir = os.path.join(TRASH_HOME, "files")
    info_dir = os.path.join(TRASH_HOME, "info")
    os.makedirs(files_dir, exist_ok=True)
    os.makedirs(info_dir, exist_ok=True)
    for p in paths:
        p = os.path.abspath(p)
        try:
            same = os.lstat(p).st_dev == hd
        except OSError as e:
            errors.append((p, str(e)))
            continue
        if not same:
            # inny system plików — korzystamy z gio, który zna lokalne kosze
            if shutil.which("gio"):
                r = subprocess.run(["gio", "trash", p], capture_output=True, text=True)
                if r.returncode != 0:
                    errors.append((p, r.stderr.strip()))
            else:
                errors.append((p, "brak kosza na tym dysku"))
            continue
        name = os.path.basename(p)
        base = name
        i = 1
        while os.path.exists(os.path.join(files_dir, name)) or os.path.exists(os.path.join(info_dir, name + ".trashinfo")):
            i += 1
            b, ext = os.path.splitext(base)
            name = f"{b}.{i}{ext}"
        info = os.path.join(info_dir, name + ".trashinfo")
        try:
            fd = os.open(info, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write("[Trash Info]\n")
                f.write("Path=" + urllib.parse.quote(p) + "\n")
                f.write("DeletionDate=" + datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S") + "\n")
            os.rename(p, os.path.join(files_dir, name))
        except OSError as e:
            try:
                os.remove(info)
            except OSError:
                pass
            errors.append((p, str(e)))
    return errors


class TrashItem:
    __slots__ = ("name", "orig", "date", "file", "info", "is_dir", "size")


def trash_list():
    out = []
    files_dir = os.path.join(TRASH_HOME, "files")
    info_dir = os.path.join(TRASH_HOME, "info")
    if not os.path.isdir(info_dir):
        return out
    for fn in os.listdir(info_dir):
        if not fn.endswith(".trashinfo"):
            continue
        name = fn[:-10]
        f = os.path.join(files_dir, name)
        if not os.path.lexists(f):
            continue
        it = TrashItem()
        it.name = name
        it.file = f
        it.info = os.path.join(info_dir, fn)
        it.orig = ""
        it.date = ""
        try:
            with open(it.info, encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith("Path="):
                        it.orig = urllib.parse.unquote(line[5:].strip())
                    elif line.startswith("DeletionDate="):
                        it.date = line[13:].strip()
        except OSError:
            pass
        it.is_dir = os.path.isdir(f) and not os.path.islink(f)
        try:
            it.size = dir_size(f) if it.is_dir else os.lstat(f).st_size
        except OSError:
            it.size = 0
        out.append(it)
    return out


def trash_count():
    info_dir = os.path.join(TRASH_HOME, "info")
    try:
        return sum(1 for f in os.listdir(info_dir) if f.endswith(".trashinfo"))
    except OSError:
        return 0


def trash_restore(item):
    dest = item.orig
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.exists(dest):
        dest = os.path.join(os.path.dirname(dest), unique_name(os.path.dirname(dest), os.path.basename(dest)))
    os.rename(item.file, dest)
    os.remove(item.info)
    return dest


def trash_delete(item):
    if item.is_dir:
        shutil.rmtree(item.file, ignore_errors=True)
    else:
        os.remove(item.file)
    try:
        os.remove(item.info)
    except OSError:
        pass


def trash_empty():
    for it in trash_list():
        try:
            trash_delete(it)
        except OSError:
            pass
    # porządki w pozostałościach
    for sub in ("files", "info", "expunged"):
        d = os.path.join(TRASH_HOME, sub)
        if os.path.isdir(d):
            for fn in os.listdir(d):
                p = os.path.join(d, fn)
                try:
                    shutil.rmtree(p) if os.path.isdir(p) and not os.path.islink(p) else os.remove(p)
                except OSError:
                    pass


def dir_size(path, limit=200000):
    total = 0
    n = 0
    for root, dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.lstat(os.path.join(root, f)).st_size
            except OSError:
                pass
            n += 1
            if n > limit:
                return total
    return total


def count_contents(path, limit=200000):
    nfiles = nfolders = 0
    total = 0
    for root, dirs, files in os.walk(path):
        nfolders += len(dirs)
        nfiles += len(files)
        for f in files:
            try:
                total += os.lstat(os.path.join(root, f)).st_size
            except OSError:
                pass
        if nfiles > limit:
            break
    return nfiles, nfolders, total


# ------------------------------------------------------------------ kopiowanie
def copy_into(srcs, dest_dir, move=False, conflict=None, progress=None):
    """Kopiuje lub przenosi pliki do katalogu. ``conflict(name)`` -> 'replace'/'skip'/'rename'.

    Wkopiowanie do tego samego katalogu tworzy "Kopia ..." (jak w klasycznych systemach).
    Zwraca (lista nowych ścieżek, lista błędów).
    """
    created, errors = [], []
    for i, src in enumerate(srcs):
        src = os.path.abspath(src)
        name = os.path.basename(src.rstrip("/"))
        if progress:
            if progress(i, len(srcs), name) is False:
                break
        same_dir = os.path.dirname(src) == os.path.abspath(dest_dir)
        if same_dir and move:
            continue
        dest = os.path.join(dest_dir, name)
        if same_dir:
            dest = os.path.join(dest_dir, unique_name(dest_dir, name, copy_style=True))
        elif os.path.lexists(dest):
            act = conflict(name) if conflict else "rename"
            if act == "skip":
                continue
            if act == "rename":
                dest = os.path.join(dest_dir, unique_name(dest_dir, name))
            elif act == "replace":
                try:
                    if os.path.isdir(dest) and not os.path.islink(dest):
                        shutil.rmtree(dest)
                    else:
                        os.remove(dest)
                except OSError as e:
                    errors.append((src, str(e)))
                    continue
        if os.path.isdir(src) and (os.path.abspath(dest) + os.sep).startswith(src + os.sep):
            errors.append((src, tr("error")))
            continue
        try:
            if move:
                shutil.move(src, dest)
            elif os.path.isdir(src) and not os.path.islink(src):
                shutil.copytree(src, dest, symlinks=True)
            else:
                shutil.copy2(src, dest, follow_symlinks=False)
            created.append(dest)
        except (OSError, shutil.Error) as e:
            errors.append((src, str(e)))
    return created, errors


def delete_permanently(paths):
    errors = []
    for p in paths:
        try:
            if os.path.isdir(p) and not os.path.islink(p):
                shutil.rmtree(p)
            else:
                os.remove(p)
        except OSError as e:
            errors.append((p, str(e)))
    return errors


# ------------------------------------------------------------------ schowek
def set_clipboard(paths, cut=False):
    from PySide6.QtCore import QMimeData, QUrl
    from PySide6.QtWidgets import QApplication
    md = QMimeData()
    urls = [QUrl.fromLocalFile(os.path.abspath(p)) for p in paths]
    md.setUrls(urls)
    gnome = ("cut" if cut else "copy") + "\n" + "\n".join(u.toString() for u in urls)
    md.setData("x-special/gnome-copied-files", gnome.encode("utf-8"))
    md.setData("application/x-kde-cutselection", b"1" if cut else b"0")
    md.setText("\n".join(os.path.abspath(p) for p in paths))
    QApplication.clipboard().setMimeData(md)


def get_clipboard():
    """Zwraca (lista ścieżek, czy wycięte)."""
    from PySide6.QtWidgets import QApplication
    md = QApplication.clipboard().mimeData()
    if md is None:
        return [], False
    cut = False
    if md.hasFormat("x-special/gnome-copied-files"):
        data = bytes(md.data("x-special/gnome-copied-files")).decode("utf-8", "replace").splitlines()
        if data:
            cut = data[0].strip() == "cut"
    elif md.hasFormat("application/x-kde-cutselection"):
        cut = bytes(md.data("application/x-kde-cutselection")).strip() == b"1"
    paths = [u.toLocalFile() for u in md.urls() if u.isLocalFile()]
    return paths, cut


def clipboard_has_files():
    return bool(get_clipboard()[0])
