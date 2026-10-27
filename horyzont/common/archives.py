"""Archiwa: ZIP, RAR, 7z, TAR (gz/bz2/xz/zst), ISO, CAB i inne — przeglądanie, rozpakowywanie
(także z hasłem) i tworzenie archiwów ZIP.

ZIP i TAR obsługuje sam Python. Pozostałe formaty — zainstalowane narzędzia:
7z (pakiet 7zip), unar/lsar (pakiet unar — m.in. RAR5 z hasłem), unrar, bsdtar.
"""
import bz2
import datetime as _dt
import gzip
import json
import lzma
import os
import re
import shutil
import stat
import subprocess
import tarfile
import zipfile

TAR_EXT = (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz", ".tbz2", ".tar.xz", ".txz", ".tar.zst", ".tzst",
           ".tar.lz", ".tar.lzma", ".tar.z")
ZIP_EXT = (".zip", ".jar", ".xpi", ".apk", ".epub", ".cbz", ".odt", ".ods", ".odp", ".docx", ".xlsx", ".pptx",
           ".whl", ".nupkg")
OTHER_EXT = (".rar", ".cbr", ".7z", ".cb7", ".iso", ".cab", ".arj", ".lzh", ".lha", ".cpio", ".rpm", ".deb",
             ".xar", ".wim", ".dmg", ".msi", ".z01", ".001")
SINGLE_EXT = {".gz": "gzip", ".bz2": "bzip2", ".xz": "xz", ".lzma": "xz", ".zst": "zstd"}
# typy otwierane jak folder skompresowany (dokumenty biurowe .docx itp. otwieramy normalnie)
BROWSABLE = (".zip", ".rar", ".7z", ".cbz", ".cbr", ".cb7", ".iso", ".cab", ".arj", ".lzh", ".lha", ".cpio",
             ".jar", ".xpi", ".apk") + TAR_EXT + tuple(SINGLE_EXT)


class ArchiveError(Exception):
    pass


class NeedPassword(ArchiveError):
    pass


class WrongPassword(ArchiveError):
    pass


class Entry:
    __slots__ = ("name", "is_dir", "size", "packed", "mtime", "encrypted")

    def __init__(self, name, is_dir=False, size=0, packed=0, mtime=0, encrypted=False):
        name = name.replace("\\", "/")
        while name.startswith("./"):
            name = name[2:]
        self.name = name.strip("/")
        self.is_dir = is_dir
        self.size = size
        self.packed = packed
        self.mtime = mtime
        self.encrypted = encrypted


def lower_ext(path):
    p = path.lower()
    for e in sorted(TAR_EXT, key=len, reverse=True):
        if p.endswith(e):
            return e
    return os.path.splitext(p)[1]


def kind(path):
    e = lower_ext(path)
    if e in TAR_EXT:
        return "tar"
    if e in ZIP_EXT:
        return "zip"
    if e in (".rar", ".cbr"):
        return "rar"
    if e in (".7z", ".cb7"):
        return "7z"
    if e in SINGLE_EXT:
        return "single"
    if e in OTHER_EXT:
        return "other"
    # rozpoznanie po zawartości
    try:
        with open(path, "rb") as f:
            head = f.read(8)
    except OSError:
        return None
    if head[:4] == b"PK\x03\x04":
        return "zip"
    if head[:6] == b"Rar!\x1a\x07":
        return "rar"
    if head[:6] == b"7z\xbc\xaf\x27\x1c":
        return "7z"
    return None


def is_archive(path, browsable_only=True):
    if not os.path.isfile(path):
        return False
    if browsable_only:
        return lower_ext(path) in BROWSABLE or (lower_ext(path) not in ZIP_EXT and kind(path) in ("zip", "rar", "7z"))
    return kind(path) is not None


def tool(name):
    for n in {"7z": ("7z", "7zz", "7za", "7zr"), "unar": ("unar",), "lsar": ("lsar",), "unrar": ("unrar",),
              "bsdtar": ("bsdtar",), "tar": ("tar",)}.get(name, (name,)):
        p = shutil.which(n)
        if p:
            return p
    return None


def _decode_zip_name(info):
    if info.flag_bits & 0x800:
        return info.filename
    try:
        raw = info.filename.encode("cp437")
    except UnicodeEncodeError:
        return info.filename
    for enc in ("utf-8", "cp852", "cp1250"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return info.filename


def _run(args, timeout=600, input_text=None):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL
                           if input_text is None else None, input=input_text, errors="replace")
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    except OSError as e:
        return 127, "", str(e)


def _is_pw_error(text):
    t = text.lower()
    return any(s in t for s in ("wrong password", "incorrect password", "bad password", "password is incorrect",
                                "nieprawidłowe hasło", "błędne hasło", "can not open encrypted archive",
                                "data error in encrypted file", "crc failed in encrypted", "checksum error in the encrypted",
                                "invalid password"))


def _needs_pw(text):
    t = text.lower()
    return "enter password" in t or "password is required" in t or "this archive requires a password" in t or \
        "encrypted" in t and "password" in t


# ------------------------------------------------------------------ listowanie
def list_entries(path, password=None):
    return [e for e in _list_entries(path, password) if e.name and e.name != "."]


def _list_entries(path, password=None):
    k = kind(path)
    if k is None:
        raise ArchiveError("nieznany format archiwum")
    if k == "zip":
        try:
            return _list_zip(path)
        except (zipfile.BadZipFile, NotImplementedError):
            pass
    if k == "tar":
        try:
            return _list_tar(path)
        except (tarfile.TarError, OSError, ValueError, ImportError):
            pass
    if k == "single":
        name = os.path.basename(path)
        inner = name[: -len(lower_ext(path))] or "dane"
        return [Entry(inner, False, 0, os.path.getsize(path), os.path.getmtime(path))]
    order = {"rar": ("unar", "7z", "unrar", "bsdtar"), "7z": ("7z", "unar", "bsdtar")}.get(k, ("7z", "bsdtar", "unar"))
    last = ArchiveError("brak programu do obsługi tego archiwum (zainstaluj 7zip lub unar)")
    for t in order:
        if not tool("lsar" if t == "unar" else t):
            continue
        try:
            return {"7z": _list_7z, "unar": _list_lsar, "unrar": _list_unrar, "bsdtar": _list_bsdtar}[t](path, password)
        except (NeedPassword, WrongPassword):
            raise
        except ArchiveError as e:
            last = e
    raise last


def _list_zip(path):
    out = []
    with zipfile.ZipFile(path) as z:
        for i in z.infolist():
            try:
                mt = _dt.datetime(*i.date_time).timestamp()
            except ValueError:
                mt = 0
            out.append(Entry(_decode_zip_name(i), i.is_dir(), i.file_size, i.compress_size, mt, bool(i.flag_bits & 1)))
    return out


def _tar_open(path):
    e = lower_ext(path)
    if e in (".tar.zst", ".tzst"):
        return tarfile.open(path, "r:zst")   # Python 3.14+
    return tarfile.open(path, "r:*")


def _list_tar(path):
    out = []
    with _tar_open(path) as t:
        for m in t.getmembers():
            out.append(Entry(m.name, m.isdir(), m.size, 0, m.mtime))
    return out


def _list_7z(path, password):
    rc, out, err = _run([tool("7z"), "l", "-slt", "-ba", f"-p{password or ''}", "--", path], 120)
    text = out + err
    if rc != 0:
        if _is_pw_error(text):
            raise (WrongPassword if password else NeedPassword)(text.strip()[-300:])
        if "unsupported" in text.lower() or "can not open the file as archive" in text.lower():
            raise ArchiveError(text.strip()[-300:])
        raise ArchiveError(text.strip()[-300:] or f"7z: kod {rc}")
    entries, cur = [], {}
    for line in out.splitlines() + [""]:
        if not line.strip():
            if "Path" in cur:
                mt = 0
                try:
                    mt = _dt.datetime.strptime(cur.get("Modified", "")[:19], "%Y-%m-%d %H:%M:%S").timestamp()
                except ValueError:
                    pass
                entries.append(Entry(cur["Path"].replace("\\", "/"), cur.get("Folder") == "+" or "D" in cur.get("Attributes", "")[:1],
                                     int(cur.get("Size") or 0), int(cur.get("Packed Size") or 0), mt,
                                     cur.get("Encrypted") == "+"))
            cur = {}
            continue
        if " = " in line:
            k, v = line.split(" = ", 1)
            cur[k.strip()] = v
    return entries


def _list_lsar(path, password):
    args = [tool("lsar"), "-j"]
    if password:
        args += ["-p", password]
    rc, out, err = _run(args + ["--", path], 120)
    try:
        data = json.loads(out)
    except ValueError:
        text = out + err
        if _is_pw_error(text) or "password" in text.lower():
            raise (WrongPassword if password else NeedPassword)(text.strip()[-300:])
        raise ArchiveError(text.strip()[-300:] or "lsar")
    if data.get("lsarError"):
        msg = str(data.get("lsarError"))
        if "password" in msg.lower() or data.get("lsarFormatName") and data.get("lsarEncrypted"):
            raise (WrongPassword if password else NeedPassword)(msg)
    entries = []
    for e in data.get("lsarContents", []):
        name = e.get("XADFileName", "")
        mt = 0
        d = e.get("XADLastModificationDate", "")
        try:
            mt = _dt.datetime.strptime(d[:19], "%Y-%m-%d %H:%M:%S").timestamp()
        except ValueError:
            pass
        entries.append(Entry(name, bool(e.get("XADIsDirectory")), int(e.get("XADFileSize") or 0),
                             int(e.get("XADCompressedSize") or 0), mt, bool(e.get("XADIsEncrypted"))))
    if data.get("lsarEncrypted") and not entries:
        raise (WrongPassword if password else NeedPassword)("archiwum zaszyfrowane")
    return entries


def _list_unrar(path, password):
    rc, out, err = _run([tool("unrar"), "vt", f"-p{password or '-'}", "--", path], 120)
    if rc != 0:
        text = out + err
        if "password" in text.lower():
            raise (WrongPassword if password else NeedPassword)(text.strip()[-300:])
        raise ArchiveError(text.strip()[-300:])
    entries, cur = [], {}
    for line in out.splitlines() + [""]:
        line = line.strip()
        if not line:
            if "Name" in cur:
                entries.append(Entry(cur["Name"], cur.get("Type") == "Directory", int(cur.get("Size", "0") or 0), 0, 0,
                                     "*" in cur.get("Flags", "")))
            cur = {}
            continue
        if ": " in line:
            k, v = line.split(": ", 1)
            cur[k.strip()] = v.strip()
    return entries


def _list_bsdtar(path, password):
    args = [tool("bsdtar"), "-tvf", path]
    if password:
        args += ["--passphrase", password]
    rc, out, err = _run(args, 120)
    if rc != 0:
        if "passphrase" in err.lower() or "encrypted" in err.lower():
            raise (WrongPassword if password else NeedPassword)(err.strip()[-300:])
        raise ArchiveError(err.strip()[-300:] or "bsdtar")
    entries = []
    for line in out.splitlines():
        parts = line.split(None, 8)
        if len(parts) < 9:
            continue
        name = parts[8]
        try:
            size = int(parts[4])
        except ValueError:
            size = 0
        entries.append(Entry(name, parts[0].startswith("d"), size))
    return entries


# ------------------------------------------------------------------ rozpakowywanie
def _safe_target(dest, name):
    target = os.path.normpath(os.path.join(dest, name))
    if not (target == os.path.normpath(dest) or target.startswith(os.path.normpath(dest) + os.sep)):
        raise ArchiveError(f"niebezpieczna ścieżka w archiwum: {name}")
    return target


def extract(path, dest, members=None, password=None, progress=None, cancelled=lambda: False):
    """Rozpakowuje archiwum (lub wybrane elementy — ścieżki wewnątrz archiwum, także foldery) do dest.

    progress(procent, nazwa) — wywoływane w trakcie (z wątku roboczego).
    """
    os.makedirs(dest, exist_ok=True)
    k = kind(path)
    if k == "zip":
        try:
            return _extract_zip(path, dest, members, password, progress, cancelled)
        except NotImplementedError:
            pass     # np. ZIP z szyfrowaniem AES — narzędzie zewnętrzne
    if k == "tar":
        try:
            return _extract_tar(path, dest, members, progress, cancelled)
        except (tarfile.CompressionError, ImportError, ValueError):
            pass
    if k == "single":
        return _extract_single(path, dest, progress)
    order = {"rar": ("unar", "7z", "unrar", "bsdtar"), "7z": ("7z", "unar", "bsdtar")}.get(k, ("7z", "bsdtar", "unar"))
    last = ArchiveError("brak programu do rozpakowania tego archiwum (zainstaluj 7zip lub unar)")
    for t in order:
        if not tool(t):
            continue
        try:
            return {"7z": _extract_7z, "unar": _extract_unar, "unrar": _extract_unrar,
                    "bsdtar": _extract_bsdtar}[t](path, dest, members, password, progress, cancelled)
        except (NeedPassword, WrongPassword):
            raise
        except ArchiveError as e:
            last = e
    raise last


def _wanted(name, members):
    if not members:
        return True
    while name.startswith("./"):
        name = name[2:]
    name = name.strip("/")
    return any(name == m or name.startswith(m.rstrip("/") + "/") for m in members)


def _extract_zip(path, dest, members, password, progress, cancelled):
    pwd = password.encode("utf-8") if password else None
    with zipfile.ZipFile(path) as z:
        infos = [i for i in z.infolist() if _wanted(_decode_zip_name(i), members)]
        total = sum(i.file_size for i in infos) or 1
        done = 0
        for i in infos:
            if cancelled():
                raise ArchiveError("anulowano")
            name = _decode_zip_name(i)
            target = _safe_target(dest, name)
            if i.is_dir():
                os.makedirs(target, exist_ok=True)
                continue
            if i.compress_type == 99:
                raise NotImplementedError("AES")
            if i.flag_bits & 1 and not pwd:
                raise NeedPassword(name)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            try:
                with z.open(i, pwd=pwd) as src, open(target, "wb") as out:
                    while True:
                        if cancelled():
                            raise ArchiveError("anulowano")
                        buf = src.read(1 << 20)
                        if not buf:
                            break
                        out.write(buf)
                        done += len(buf)
                        if progress:
                            progress(int(done * 100 / total), name)
            except RuntimeError as e:
                try:
                    os.remove(target)
                except OSError:
                    pass
                if "password" in str(e).lower():
                    raise WrongPassword(name) if pwd else NeedPassword(name)
                raise ArchiveError(str(e))
            except zipfile.BadZipFile as e:
                if pwd:
                    raise WrongPassword(name)
                raise ArchiveError(str(e))
            mt = _dt.datetime(*i.date_time).timestamp() if i.date_time[0] >= 1980 else None
            if mt:
                os.utime(target, (mt, mt))
            perm = (i.external_attr >> 16) & 0o777
            if perm & 0o100:
                os.chmod(target, os.stat(target).st_mode | stat.S_IXUSR)
    return True


def _extract_tar(path, dest, members, progress, cancelled):
    with _tar_open(path) as t:
        ms = [m for m in t.getmembers() if _wanted(m.name, members)]
        total = len(ms) or 1
        for n, m in enumerate(ms):
            if cancelled():
                raise ArchiveError("anulowano")
            _safe_target(dest, m.name)
            try:
                t.extract(m, dest, filter="data")
            except TypeError:
                t.extract(m, dest)
            except tarfile.FilterError as e:
                raise ArchiveError(str(e))
            if progress:
                progress(int((n + 1) * 100 / total), m.name)
    return True


def _extract_single(path, dest, progress):
    e = lower_ext(path)
    name = os.path.basename(path)[: -len(e)] or "dane"
    opener = {".gz": gzip.open, ".bz2": bz2.open, ".xz": lzma.open, ".lzma": lzma.open}.get(e)
    target = os.path.join(dest, name)
    if opener is None:
        if tool("zstd") or shutil.which("zstd"):
            rc, out, err = _run(["zstd", "-d", "-f", "-o", target, path])
            if rc != 0:
                raise ArchiveError(err.strip())
            return True
        raise ArchiveError("brak programu zstd")
    with opener(path, "rb") as src, open(target, "wb") as out:
        shutil.copyfileobj(src, out, 1 << 20)
    if progress:
        progress(100, name)
    return True


def _popen_progress(args, progress, cancelled, pct_re=re.compile(r"(\d{1,3})%")):
    p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                         text=True, errors="replace", bufsize=1)
    out = []
    buf = ""
    while True:
        ch = p.stdout.read(1)
        if not ch:
            break
        if cancelled():
            p.kill()
            raise ArchiveError("anulowano")
        if ch in "\r\n\b":
            line = buf.strip()
            buf = ""
            if line:
                out.append(line)
                m = pct_re.search(line)
                if m and progress:
                    progress(min(100, int(m.group(1))), line.split("-", 1)[-1].strip() if "-" in line else "")
            continue
        buf += ch
    p.wait()
    if buf.strip():
        out.append(buf.strip())
    return p.returncode, "\n".join(out[-60:])


def _extract_7z(path, dest, members, password, progress, cancelled):
    args = [tool("7z"), "x", "-y", "-bsp1", "-bso1", "-bse1", f"-o{dest}", f"-p{password or ''}", "--", path]
    if members:
        args += list(members)
    rc, text = _popen_progress(args, progress, cancelled)
    if rc != 0:
        if _is_pw_error(text) or ("encrypted" in text.lower() and "headers" in text.lower()):
            raise (WrongPassword if password else NeedPassword)(text[-300:])
        raise ArchiveError(text[-400:] or f"7z: kod {rc}")
    return True


def _extract_unar(path, dest, members, password, progress, cancelled):
    args = [tool("unar"), "-q", "-f", "-D", "-o", dest]
    if password:
        args += ["-p", password]
    args += ["--", path] + list(members or [])
    if progress:
        progress(-1, "")
    rc, out, err = _run(args, 7200)
    if rc != 0:
        text = out + err
        if "password" in text.lower() or _is_pw_error(text):
            raise (WrongPassword if password else NeedPassword)(text.strip()[-300:])
        raise ArchiveError(text.strip()[-400:] or f"unar: kod {rc}")
    return True


def _extract_unrar(path, dest, members, password, progress, cancelled):
    args = [tool("unrar"), "x", "-o+", "-y", f"-p{password or '-'}", "--", path] + list(members or []) + [dest.rstrip("/") + "/"]
    rc, text = _popen_progress(args, progress, cancelled)
    if rc != 0:
        if "password" in text.lower():
            raise (WrongPassword if password else NeedPassword)(text[-300:])
        raise ArchiveError(text[-400:])
    return True


def _extract_bsdtar(path, dest, members, password, progress, cancelled):
    args = [tool("bsdtar"), "-xf", path, "-C", dest]
    if password:
        args += ["--passphrase", password]
    args += list(members or [])
    rc, out, err = _run(args, 7200)
    if rc != 0:
        if "passphrase" in err.lower() or "encrypted" in err.lower():
            raise (WrongPassword if password else NeedPassword)(err.strip()[-300:])
        raise ArchiveError(err.strip()[-400:])
    return True


# ------------------------------------------------------------------ tworzenie ZIP
def create_zip(paths, target, progress=None, cancelled=lambda: False, password=None):
    """Tworzy archiwum ZIP. Z hasłem — przez 7z (AES-256), bez hasła — wbudowany zipfile."""
    if password:
        if not tool("7z"):
            raise ArchiveError("do archiwów z hasłem potrzebny jest program 7z (pakiet 7zip)")
        args = [tool("7z"), "a", "-tzip", "-mem=AES256", f"-p{password}", "-bsp1", "-bso1", "-bse1", "-y", "--", target] + list(paths)
        rc, text = _popen_progress(args, progress, cancelled)
        if rc != 0:
            raise ArchiveError(text[-400:])
        return True
    files = []
    for p in paths:
        base = os.path.dirname(os.path.abspath(p))
        if os.path.isdir(p):
            for root, dirs, fs in os.walk(p):
                files.append((root, os.path.relpath(root, base) + "/"))
                for f in fs:
                    full = os.path.join(root, f)
                    files.append((full, os.path.relpath(full, base)))
        else:
            files.append((p, os.path.basename(p)))
    total = sum(os.path.getsize(f) for f, a in files if not a.endswith("/") and os.path.isfile(f)) or 1
    done = 0
    tmp = target + ".part"
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for full, arc in files:
                if cancelled():
                    raise ArchiveError("anulowano")
                if arc.endswith("/"):
                    z.writestr(zipfile.ZipInfo.from_file(full, arc), "")
                    continue
                if os.path.islink(full) or not os.path.isfile(full):
                    continue
                z.write(full, arc)
                done += os.path.getsize(full)
                if progress:
                    progress(int(done * 100 / total), arc)
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return True


def tools_summary():
    """Krótki opis dostępnych narzędzi (do okna informacji)."""
    have = [n for n in ("7z", "unar", "unrar", "bsdtar") if tool(n)]
    return have
