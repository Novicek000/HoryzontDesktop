"""Horyzont Updates — sprawdzanie i instalowanie aktualizacji:

* system Fedora (dnf; bez uprawnień administratora sprawdzamy przez PackageKit/pkcon albo dnf),
* aplikacje Flatpak,
* sam Horyzont (wydania na GitHubie: archiwum .tar.gz ze skryptem update.sh).
"""
import datetime as _dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request

from .. import config

SYSTEM_CONFIG = "/etc/horyzont/updates.json"
SYSTEM_STATUS = "/var/lib/horyzont/updates-status.json"
USER_STATUS = os.path.join(config.CACHE_DIR, "updates-status.json")
HISTORY = os.path.join(config.DATA_DIR, "updates-history.json")

DEFAULT_SETTINGS = {
    "mode": "notify",            # auto / download / notify / off
    "frequency": "daily",        # hourly / every6h / daily / weekly
    "time": "03:00",             # godzina dla daily/weekly
    "weekday": "Sun",
    "include_horyzont": True,
    "include_flatpak": True,
    "takeover": True,            # Horyzont przejmuje aktualizacje (wyłącza dnf-automatic i automatyczne pobieranie GNOME Software)
    "github_repo": "",           # właściciel/nazwa, np. jan/horyzont
}


def settings():
    s = dict(DEFAULT_SETTINGS)
    s.update(config.get("updates", {}) or {})
    try:
        with open(SYSTEM_CONFIG, encoding="utf-8") as f:
            sysconf = json.load(f)
        # ustawienia systemowe (zapisane przez administratora) mają pierwszeństwo dla trybu i harmonogramu
        for k in ("mode", "frequency", "time", "weekday", "takeover"):
            if k in sysconf:
                s[k] = sysconf[k]
    except (OSError, ValueError):
        pass
    if not s.get("github_repo"):
        s["github_repo"] = default_repo()
    return s


def default_repo():
    """Repozytorium zapisane przy instalacji (plik REPO obok kodu), np. przez update.sh."""
    for p in (os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "REPO"), "/etc/horyzont/repo"):
        try:
            with open(p, encoding="utf-8") as f:
                v = f.read().strip()
                if re.fullmatch(r"[\w.-]+/[\w.-]+", v):
                    return v
        except OSError:
            continue
    return ""


def parse_version(v):
    v = (v or "").strip().lstrip("vV")
    parts = re.findall(r"\d+", v.split("-")[0])
    return tuple(int(x) for x in parts[:4]) or (0,)


class Update:
    __slots__ = ("source", "id", "name", "old", "new", "size", "security", "description", "extra")

    def __init__(self, source, id_, name, old="", new="", size=0, security=False, description="", extra=None):
        self.source, self.id, self.name = source, id_, name
        self.old, self.new, self.size = old, new, size
        self.security = security
        self.description = description
        self.extra = extra or {}

    def to_dict(self):
        return {k: getattr(self, k) for k in self.__slots__}


def _run(args, timeout=900):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL,
                           env=dict(os.environ, LC_ALL="C"))
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    except OSError as e:
        return 127, "", str(e)


# ------------------------------------------------------------------ system (dnf / PackageKit)
PKG_LINE = re.compile(r"^(\S+?)\.(\w+)\s+(\S+)\s+(\S+)\s*$")


def check_system(refresh=True):
    """Lista aktualizacji pakietów systemu. Nie wymaga uprawnień administratora."""
    if shutil.which("pkcon"):
        ups = _check_pkcon(refresh)
        if ups is not None:
            return ups
    dnf = shutil.which("dnf") or shutil.which("dnf5")
    if not dnf:
        return []
    args = [dnf, "check-upgrade", "-q"]
    if refresh:
        args.append("--refresh")
    rc, out, err = _run(args)
    if rc not in (0, 100):
        rc, out, err = _run([dnf, "check-update", "-q"] + (["--refresh"] if refresh else []))
        if rc not in (0, 100):
            raise RuntimeError((err or out).strip()[-400:] or "dnf")
    ups = []
    sec = _security_ids(dnf)
    for line in out.splitlines():
        if line.lower().startswith(("obsoleting", "security:", "last metadata", "updating", "repositories")):
            continue
        m = PKG_LINE.match(line.strip())
        if m:
            name, arch, ver, repo = m.groups()
            ups.append(Update("dnf", f"{name}.{arch}", name, "", ver, 0, name in sec, repo))
    return ups


def _check_pkcon(refresh):
    if refresh:
        _run(["pkcon", "refresh", "--noninteractive"], 600)
    rc, out, err = _run(["pkcon", "get-updates", "--plain", "--noninteractive"], 600)
    if rc not in (0, 5):        # 5 = brak aktualizacji
        return None
    ups = []
    for line in out.splitlines():
        line = line.strip()
        m = re.match(r"^(Security|Bug ?fix|Enhancement|Normal|Low|Important|Blocked)\s+(\S+)", line, re.I)
        if not m:
            continue
        kind, pid = m.group(1), m.group(2)
        # nazwa-wersja-wydanie.arch
        mm = re.match(r"^(.+?)-(\d[^-]*-[^-]+)\.(\w+)$", pid)
        if mm:
            name, ver, arch = mm.groups()
        else:
            name, ver, arch = pid, "", ""
        ups.append(Update("dnf", f"{name}.{arch}" if arch else name, name, "", ver, 0, kind.lower() == "security",
                          kind))
    return ups


def _security_ids(dnf):
    rc, out, err = _run([dnf, "updateinfo", "list", "--security", "--updates", "-q"], 120)
    names = set()
    if rc == 0:
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 3:
                pkg = parts[-1]
                mm = re.match(r"^(.+?)-\d", pkg)
                if mm:
                    names.add(mm.group(1))
    return names


def installed_versions(names):
    if not names or not shutil.which("rpm"):
        return {}
    rc, out, err = _run(["rpm", "-q", "--qf", "%{NAME} %{VERSION}-%{RELEASE}\n"] + list(names), 60)
    res = {}
    for line in out.splitlines():
        p = line.split()
        if len(p) == 2:
            res[p[0]] = p[1]
    return res


# ------------------------------------------------------------------ Flatpak
def check_flatpak():
    if not shutil.which("flatpak"):
        return []
    ups = []
    for scope in ("--system", "--user"):
        rc, out, err = _run(["flatpak", "remote-ls", "--updates", scope, "--columns=application,name,version,branch"], 300)
        if rc != 0:
            continue
        for line in out.splitlines():
            p = line.split("\t")
            if len(p) >= 2 and "." in p[0]:
                ups.append(Update("flatpak", p[0], p[1] or p[0], "", p[2] if len(p) > 2 else "", 0, False, "",
                                  {"scope": scope}))
    return ups


# ------------------------------------------------------------------ Horyzont (GitHub)
def check_horyzont(repo=None):
    """Najnowsze wydanie z GitHuba. Zwraca Update albo None (brak nowszej wersji)."""
    repo = repo or settings().get("github_repo")
    if not repo:
        return None
    data = _github(f"https://api.github.com/repos/{repo}/releases/latest")
    if not data:
        tags = _github(f"https://api.github.com/repos/{repo}/tags")
        if tags:
            tag = tags[0]["name"]
            data = {"tag_name": tag, "body": "", "assets": [],
                    "tarball_url": f"https://api.github.com/repos/{repo}/tarball/{tag}", "name": tag}
        else:
            data = _branch_version(repo)
            if not data:
                return None
    tag = data.get("tag_name", "")
    if parse_version(tag) <= parse_version(config.VERSION):
        return None
    url, size, sums = None, 0, None
    for a in data.get("assets", []):
        n = a.get("name", "")
        if n.endswith((".tar.gz", ".tgz")) and "horyzont" in n.lower():
            url, size = a.get("browser_download_url"), a.get("size", 0)
        elif n.upper().startswith("SHA256SUM"):
            sums = a.get("browser_download_url")
    if url is None:
        for a in data.get("assets", []):
            if a.get("name", "").endswith((".tar.gz", ".tgz")):
                url, size = a.get("browser_download_url"), a.get("size", 0)
                break
    url = url or data.get("tarball_url")
    return Update("horyzont", "horyzont", "Horyzont", config.VERSION, tag.lstrip("vV"), size, False,
                  data.get("body") or "", {"url": url, "sums": sums, "repo": repo, "title": data.get("name") or tag})


def _branch_version(repo):
    """Brak wydań i tagów: wersja z pliku horyzont/config.py w głównej gałęzi repozytorium."""
    info = _github(f"https://api.github.com/repos/{repo}") or {}
    branches = [info.get("default_branch")] if info.get("default_branch") else ["main", "master"]
    for br in branches:
        try:
            req = urllib.request.Request(f"https://raw.githubusercontent.com/{repo}/{br}/horyzont/config.py",
                                         headers={"User-Agent": f"Horyzont/{config.VERSION}"})
            with urllib.request.urlopen(req, timeout=20) as r:
                text = r.read().decode("utf-8", "replace")
        except Exception:
            continue
        m = re.search(r'^VERSION\s*=\s*["\']([^"\']+)["\']', text, re.M)
        if not m:
            continue
        body = ""
        commit = _github(f"https://api.github.com/repos/{repo}/commits/{br}")
        if commit:
            body = (commit.get("commit") or {}).get("message", "")
        return {"tag_name": m.group(1), "body": body, "assets": [], "name": f"Horyzont {m.group(1)} ({br})",
                "tarball_url": f"https://github.com/{repo}/archive/refs/heads/{br}.tar.gz"}
    return None


def _github(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": f"Horyzont/{config.VERSION}",
                                               "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def download_horyzont(update, progress=None, cancelled=lambda: False):
    """Pobiera i rozpakowuje wydanie. Zwraca katalog ze skryptem update.sh."""
    url = update.extra["url"]
    work = tempfile.mkdtemp(prefix="horyzont-update-", dir=config.CACHE_DIR if os.path.isdir(config.CACHE_DIR) else None)
    path = os.path.join(work, "horyzont.tar.gz")
    req = urllib.request.Request(url, headers={"User-Agent": f"Horyzont/{config.VERSION}"})
    h = hashlib.sha256()
    with urllib.request.urlopen(req, timeout=60) as r, open(path, "wb") as f:
        total = int(r.headers.get("Content-Length") or update.size or 0)
        done = 0
        while True:
            if cancelled():
                raise RuntimeError("anulowano")
            b = r.read(65536)
            if not b:
                break
            f.write(b)
            h.update(b)
            done += len(b)
            if progress and total:
                progress(int(done * 100 / total))
    if update.extra.get("sums"):
        sums = urllib.request.urlopen(urllib.request.Request(update.extra["sums"], headers={"User-Agent": "Horyzont"}),
                                      timeout=30).read().decode("utf-8", "replace")
        name = os.path.basename(url)
        expected = [l.split()[0] for l in sums.splitlines() if l.strip().endswith(name)]
        if expected and expected[0].lower() != h.hexdigest():
            raise RuntimeError("suma kontrolna pobranego pliku się nie zgadza — aktualizacja przerwana")
    with tarfile.open(path) as t:
        try:
            t.extractall(work, filter="data")
        except TypeError:
            t.extractall(work)
    for root, dirs, files in os.walk(work):
        if "update.sh" in files and "horyzont" in dirs:
            return root
    raise RuntimeError("w pobranym archiwum nie ma skryptu update.sh")


# ------------------------------------------------------------------ stan i historia
def write_status(updates, path=USER_STATUS, message=None, error=None):
    data = {"count": len(updates), "checked": _dt.datetime.now().isoformat(timespec="seconds"),
            "items": [u.to_dict() for u in updates]}
    if message:
        data["message"] = message
    if error:
        data["error"] = error
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)
    return data


def read_status():
    """Najświeższy stan (użytkownika albo systemowego agenta)."""
    best = {}
    for p in (USER_STATUS, SYSTEM_STATUS):
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
            if d.get("checked", "") > best.get("checked", ""):
                best = d
        except (OSError, ValueError):
            continue
    return best


def add_history(entries):
    hist = history()
    now = _dt.datetime.now().isoformat(timespec="seconds")
    for name, version, ok, source in entries:
        hist.insert(0, {"date": now, "name": name, "version": version, "ok": ok, "source": source})
    os.makedirs(os.path.dirname(HISTORY), exist_ok=True)
    with open(HISTORY, "w", encoding="utf-8") as f:
        json.dump(hist[:500], f, ensure_ascii=False, indent=1)


def history():
    try:
        with open(HISTORY, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def check_all(include_flatpak=True, include_horyzont=True, refresh=True):
    """(lista aktualizacji, lista błędów)."""
    ups, errors = [], []
    try:
        ups += check_system(refresh)
    except Exception as e:
        errors.append(f"dnf: {e}")
    if include_flatpak:
        try:
            ups += check_flatpak()
        except Exception as e:
            errors.append(f"flatpak: {e}")
    if include_horyzont:
        try:
            u = check_horyzont()
            if u:
                ups.insert(0, u)
        except Exception as e:
            errors.append(f"Horyzont: {e}")
    return ups, errors


def interval_seconds(freq):
    return {"hourly": 3600, "every6h": 6 * 3600, "daily": 24 * 3600, "weekly": 7 * 24 * 3600}.get(freq, 24 * 3600)


def on_calendar(s):
    """Wyrażenie OnCalendar dla timera systemd."""
    t = s.get("time", "03:00")
    f = s.get("frequency", "daily")
    if f == "hourly":
        return "hourly"
    if f == "every6h":
        return "*-*-* 00/6:00:00"
    if f == "weekly":
        return f"{s.get('weekday', 'Sun')} *-*-* {t}:00"
    return f"*-*-* {t}:00"
