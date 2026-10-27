"""NetworkManager przez nmcli: urządzenia, połączenia, sieci Wi-Fi, ustawienia IP."""
import shutil
import subprocess


def available():
    return shutil.which("nmcli") is not None


def split_terse(line):
    """Dzieli linię trybu -t nmcli (':' rozdziela, '\\:' to dwukropek w wartości)."""
    out, cur, i = [], [], 0
    while i < len(line):
        c = line[i]
        if c == "\\" and i + 1 < len(line):
            cur.append(line[i + 1])
            i += 2
            continue
        if c == ":":
            out.append("".join(cur))
            cur = []
        else:
            cur.append(c)
        i += 1
    out.append("".join(cur))
    return out


def nmcli(args, timeout=15):
    if not available():
        return 127, "", "nmcli"
    try:
        r = subprocess.run(["nmcli"] + args, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    except OSError as e:
        return 1, "", str(e)


def devices():
    """[{device, type, state, connection}] bez urządzeń wirtualnych."""
    rc, out, _ = nmcli(["-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device"])
    res = []
    for line in out.splitlines():
        p = split_terse(line)
        if len(p) < 4 or p[1] in ("loopback", "bridge", "tun", "wifi-p2p", "dummy", "veth"):
            continue
        res.append({"device": p[0], "type": p[1], "state": p[2], "connection": p[3]})
    return res


def connections():
    rc, out, _ = nmcli(["-t", "-f", "NAME,UUID,TYPE,DEVICE,AUTOCONNECT,ACTIVE", "connection", "show"])
    res = []
    for line in out.splitlines():
        p = split_terse(line)
        if len(p) < 6 or p[2] in ("loopback", "bridge", "tun"):
            continue
        res.append({"name": p[0], "uuid": p[1], "type": p[2], "device": p[3], "autoconnect": p[4] == "yes",
                    "active": p[5] == "yes"})
    return res


def device_ip(dev):
    rc, out, _ = nmcli(["-t", "-f", "IP4.ADDRESS,IP4.GATEWAY,IP4.DNS,GENERAL.HWADDR", "device", "show", dev])
    info = {}
    for line in out.splitlines():
        k, _, v = line.partition(":")
        k = k.split("[")[0]
        if v and k not in info:
            info[k] = v
        elif v and k == "IP4.DNS":
            info[k] += ", " + v
    return info


def wifi_devices():
    return [d for d in devices() if d["type"] == "wifi"]


def wifi_enabled():
    rc, out, _ = nmcli(["radio", "wifi"])
    return out.strip() == "enabled"


def set_wifi_enabled(on):
    return nmcli(["radio", "wifi", "on" if on else "off"])[0] == 0


def wifi_list(rescan="auto"):
    """Sieci posortowane: najpierw połączona, potem wg siły sygnału. Duplikaty SSID scalone."""
    rc, out, _ = nmcli(["-t", "-f", "IN-USE,SSID,BSSID,SIGNAL,SECURITY,CHAN", "device", "wifi", "list",
                        "--rescan", rescan], timeout=30)
    nets = {}
    for line in out.splitlines():
        p = split_terse(line)
        if len(p) < 6:
            continue
        inuse, ssid, bssid, sig, sec, chan = p[:6]
        if not ssid:
            continue
        try:
            sig = int(sig)
        except ValueError:
            sig = 0
        n = nets.get(ssid)
        if n is None or sig > n["signal"] or inuse == "*":
            nets[ssid] = {"ssid": ssid, "bssid": bssid, "signal": sig if n is None else max(sig, n["signal"]),
                          "security": "" if sec in ("", "--") else sec, "channel": chan,
                          "active": inuse == "*" or (n is not None and n["active"])}
    return sorted(nets.values(), key=lambda n: (not n["active"], -n["signal"]))


def saved_wifi():
    return {c["name"]: c for c in connections() if c["type"] in ("802-11-wireless", "wifi")}


def signal_level(sig):
    """0..4 kresek sygnału."""
    if sig <= 0:
        return 0
    return 1 if sig < 25 else 2 if sig < 50 else 3 if sig < 75 else 4


def con_settings(uuid, fields):
    rc, out, _ = nmcli(["-s", "-t", "-f", ",".join(fields), "connection", "show", uuid])
    res = {}
    for line in out.splitlines():
        k, _, v = line.partition(":")
        if k in fields:
            res[k] = v
    return res


def con_modify(uuid, settings):
    args = ["connection", "modify", uuid]
    for k, v in settings.items():
        args += [k, v]
    return nmcli(args, timeout=30)


def con_up(uuid_or_name, ifname=None):
    args = ["connection", "up", uuid_or_name]
    if ifname:
        args += ["ifname", ifname]
    return nmcli(args, timeout=60)


def con_down(uuid_or_name):
    return nmcli(["connection", "down", uuid_or_name], timeout=30)


def con_delete(uuid_or_name):
    return nmcli(["connection", "delete", uuid_or_name], timeout=30)


def con_rename(uuid, name):
    return nmcli(["connection", "modify", uuid, "connection.id", name])


def describe_security(sec):
    from ..i18n import plain
    if not sec:
        return plain("wifi_unsecured")
    s = sec.replace("802.1X", "802.1X ")
    return plain("wifi_secured") + f" ({s.strip()})"
