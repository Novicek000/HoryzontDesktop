"""Ustawienia monitorów (rozdzielczość, odświeżanie, skala) przez wlr-randr i ich przywracanie przy logowaniu."""
import shutil
import subprocess

from .. import config


def _mode_args(cfg):
    args = []
    mode = cfg.get("mode")
    if mode:
        res, _, rate = mode.partition("@")
        if cfg.get("custom"):
            args += ["--custom-mode", f"{res}@{float(rate or 60):.3f}Hz" if rate else res]
        else:
            args += ["--mode", f"{res}@{float(rate):.3f}Hz" if rate else res]
    if cfg.get("scale"):
        args += ["--scale", str(cfg["scale"])]
    return args


def apply_output(name, cfg):
    """Zwraca (ok, komunikat błędu)."""
    if not shutil.which("wlr-randr"):
        return False, "wlr-randr"
    args = ["wlr-randr", "--output", name] + _mode_args(cfg)
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=10)
    except Exception as e:
        return False, str(e)
    if r.returncode != 0 and not cfg.get("custom") and "--mode" in args:
        # niektóre sterowniki podają częstotliwość nieco inaczej — próbujemy samej rozdzielczości
        i = args.index("--mode")
        args[i + 1] = args[i + 1].split("@")[0]
        r = subprocess.run(args, capture_output=True, text=True, timeout=10)
    return r.returncode == 0, (r.stderr or r.stdout).strip()


def save_output(name, cfg):
    outs = dict(config.get("display_outputs", {}))
    outs[name] = cfg
    config.set("display_outputs", outs)


def apply_saved():
    """Wywoływane przy starcie powłoki: przywraca zapisane tryby monitorów."""
    for name, cfg in (config.get("display_outputs", {}) or {}).items():
        try:
            apply_output(name, cfg)
        except Exception:
            pass


def notify_shell():
    """Powłoka ponownie układa pulpit i pasek zadań po zmianie trybu ekranu."""
    try:
        from .single import forward_fast
        forward_fast("shell", ["relayout"])
    except Exception:
        pass
