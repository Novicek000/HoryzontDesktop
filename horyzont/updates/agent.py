"""Agent aktualizacji uruchamiany jako root (przez timer systemd albo pkexec z Panelu sterowania).

    horyzont update-agent --run                 # wg /etc/horyzont/updates.json (timer)
    horyzont update-agent --configure PLIK.json # zapis ustawień, harmonogramu i przejęcia aktualizacji
    horyzont update-agent --install-horyzont KATALOG  # instalacja pobranej wersji (update.sh) Horyzontu
                                                      # albo dodatku (np. ekranu powitalnego)
"""
import json
import os
import shutil
import subprocess
import sys

from . import core

UNIT_DIR = "/etc/systemd/system"
TIMER = "horyzont-updates.timer"
FEDORA_TIMERS = ["dnf-automatic.timer", "dnf-automatic-install.timer", "dnf-automatic-download.timer",
                 "dnf-automatic-notifyonly.timer", "dnf5-automatic.timer"]
VALID = {"mode": {"auto", "download", "notify", "off"}, "frequency": {"hourly", "every6h", "daily", "weekly"},
         "weekday": {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"}}


def log(*a):
    print("horyzont-updates:", *a, flush=True)


def _sh(args, timeout=3600):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout + r.stderr
    except Exception as e:
        return 1, str(e)


def load_sysconf():
    try:
        with open(core.SYSTEM_CONFIG, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def configure(path):
    with open(path, encoding="utf-8") as f:
        new = json.load(f)
    s = {}
    for k in ("mode", "frequency", "weekday"):
        v = new.get(k)
        if v in VALID[k]:
            s[k] = v
    t = str(new.get("time", "03:00"))
    if len(t) == 5 and t[2] == ":" and t[:2].isdigit() and t[3:].isdigit() and int(t[:2]) < 24 and int(t[3:]) < 60:
        s["time"] = t
    s["takeover"] = bool(new.get("takeover", True))
    s["include_flatpak"] = bool(new.get("include_flatpak", True))
    s["include_horyzont"] = bool(new.get("include_horyzont", True))
    repo = str(new.get("github_repo", ""))
    if repo and all(c.isalnum() or c in "-_./" for c in repo) and repo.count("/") == 1:
        s["github_repo"] = repo
    s.setdefault("mode", "notify")
    old = load_sysconf()
    os.makedirs(os.path.dirname(core.SYSTEM_CONFIG), exist_ok=True)
    # przejęcie aktualizacji: zapamiętujemy, które timery Fedory były włączone
    if s["takeover"] and not old.get("takeover_done"):
        enabled = []
        for t_ in FEDORA_TIMERS:
            rc, out = _sh(["systemctl", "is-enabled", t_])
            if rc == 0 and out.strip().startswith("enabled"):
                enabled.append(t_)
        for t_ in enabled:
            _sh(["systemctl", "disable", "--now", t_])
        s["takeover_done"] = True
        s["restored_timers"] = enabled
        log("wyłączono automatyczne aktualizacje Fedory:", ", ".join(enabled) or "(żadne nie były włączone)")
    elif not s["takeover"] and old.get("takeover_done"):
        for t_ in old.get("restored_timers", []):
            _sh(["systemctl", "enable", "--now", t_])
        s["takeover_done"] = False
        log("przywrócono automatyczne aktualizacje Fedory")
    else:
        s["takeover_done"] = old.get("takeover_done", False)
        s["restored_timers"] = old.get("restored_timers", [])
    with open(core.SYSTEM_CONFIG, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=1)
    os.chmod(core.SYSTEM_CONFIG, 0o644)
    # harmonogram
    dropdir = os.path.join(UNIT_DIR, TIMER + ".d")
    os.makedirs(dropdir, exist_ok=True)
    with open(os.path.join(dropdir, "schedule.conf"), "w", encoding="utf-8") as f:
        f.write(f"# Horyzont Updates — harmonogram (wygenerowany)\n[Timer]\nOnCalendar=\nOnCalendar={core.on_calendar(s)}\n")
    _sh(["systemctl", "daemon-reload"])
    if s["mode"] in ("auto", "download", "notify") and os.path.exists(os.path.join(UNIT_DIR, "horyzont-updates.service")):
        _sh(["systemctl", "enable", "--now", TIMER])
    else:
        _sh(["systemctl", "disable", "--now", TIMER])
    log("zapisano ustawienia:", s)
    return 0


def run():
    s = dict(core.DEFAULT_SETTINGS)
    s.update(load_sysconf())
    mode = s.get("mode", "notify")
    if mode == "off":
        return 0
    dnf = shutil.which("dnf") or shutil.which("dnf5") or "dnf"
    msg = None
    installed = []
    if mode == "auto":
        rc, out = _sh([dnf, "upgrade", "-y", "--refresh"])
        log(out[-2000:])
        if rc == 0 and "Nothing to do" not in out and "Nic do zrobienia" not in out:
            msg = "Aktualizacje systemu zostały zainstalowane automatycznie."
            installed.append(("System Fedora", "", True, "dnf"))
        if s.get("include_flatpak", True) and shutil.which("flatpak"):
            rc2, out2 = _sh(["flatpak", "update", "-y", "--noninteractive", "--system"])
            log(out2[-1000:])
        if s.get("include_horyzont", True):
            try:
                u = core.check_horyzont(s.get("github_repo") or core.default_repo())
                if u:
                    d = core.download_horyzont(u)
                    rc3, out3 = _sh(["bash", os.path.join(d, "update.sh"), "--yes"])
                    log(out3[-2000:])
                    if rc3 == 0:
                        msg = f"Horyzont został zaktualizowany do wersji {u.new}. Wyloguj się, aby zakończyć."
            except Exception as e:
                log("aktualizacja Horyzontu:", e)
            # dodatki (np. ekran powitalny) z /etc/horyzont/components.d
            cups, cerrs = core.check_components()
            for e in cerrs:
                log("dodatek:", e)
            for cu in cups:
                try:
                    d = core.download_horyzont(cu)
                    rc4, out4 = _sh(["bash", os.path.join(d, "update.sh"), "--yes"])
                    log(out4[-2000:])
                    installed.append((cu.name, cu.new, rc4 == 0, "horyzont"))
                except Exception as e:
                    log(f"aktualizacja {cu.name}:", e)
    elif mode == "download":
        rc, out = _sh([dnf, "upgrade", "-y", "--refresh", "--downloadonly"])
        log(out[-2000:])
    # po każdym przebiegu zapisujemy listę oczekujących aktualizacji (dla ikony w zasobniku)
    try:
        ups, errors = core.check_all(s.get("include_flatpak", True), s.get("include_horyzont", True), refresh=mode == "notify")
        core.write_status(ups, core.SYSTEM_STATUS, msg, "; ".join(errors) or None)
    except Exception as e:
        log("błąd sprawdzania:", e)
    return 0


def install_horyzont(directory):
    script = os.path.join(directory, "update.sh")
    if not os.path.isfile(script):
        log("brak update.sh w", directory)
        return 2
    os.chdir(directory)
    os.execvp("bash", ["bash", script, "--yes"])


def main(argv):
    if os.geteuid() != 0:
        print("horyzont update-agent: wymaga uprawnień administratora", file=sys.stderr)
        return 1
    if not argv or argv[0] == "--run":
        return run()
    if argv[0] == "--configure" and len(argv) > 1:
        return configure(argv[1])
    if argv[0] == "--install-horyzont" and len(argv) > 1:
        return install_horyzont(argv[1])
    print(__doc__)
    return 2
