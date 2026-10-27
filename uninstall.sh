#!/bin/bash
# Usuwa Horyzont zainstalowany przez install.sh (ustawienia użytkownika pozostają w ~/.config/horyzont).
PREFIX="${PREFIX:-/usr/local}"
SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"
$SUDO systemctl disable --now horyzont-updates.timer 2>/dev/null
# przywrócenie automatycznych aktualizacji Fedory, jeśli Horyzont je przejął
if [ -f /etc/horyzont/updates.json ]; then
    for t in $(python3 -c 'import json; print(" ".join(json.load(open("/etc/horyzont/updates.json")).get("restored_timers", [])))' 2>/dev/null); do
        $SUDO systemctl enable --now "$t" 2>/dev/null
    done
fi
# układ przycisków na paskach tytułu GTK (Firefox, GNOME) sprzed Horyzontu
[ -x "$PREFIX/bin/horyzont" ] && "$PREFIX/bin/horyzont" gtk-buttons --restore >/dev/null 2>&1
$SUDO rm -rf "$PREFIX/share/horyzont" "$PREFIX/libexec/horyzont"
$SUDO rm -f "$PREFIX"/bin/horyzont "$PREFIX"/bin/horyzont-* "$PREFIX"/share/applications/horyzont-*.desktop "$PREFIX"/share/applications/horyzont-mimeapps.list
$SUDO rm -f /usr/share/wayland-sessions/horyzont.desktop /usr/share/polkit-1/actions/org.horyzont.update-agent.policy /usr/share/xdg-desktop-portal/horyzont-portals.conf
$SUDO rm -rf /etc/systemd/system/horyzont-updates.service /etc/systemd/system/horyzont-updates.timer \
    /etc/systemd/system/horyzont-updates.timer.d /etc/horyzont /var/lib/horyzont
$SUDO systemctl daemon-reload 2>/dev/null
echo "Horyzont został usunięty."
