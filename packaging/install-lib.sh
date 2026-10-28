# Horyzont — wspólne funkcje instalatora (install.sh) i aktualizatora (update.sh).
# Plik jest wczytywany przez „source”, nie uruchamiaj go bezpośrednio.

say()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m ✓\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m !!\033[0m %s\n' "$*"; }
err()  { printf '\033[1;31m xx\033[0m %s\n' "$*" >&2; }

# Pakiety wymagane (bez nich Horyzont nie wystartuje)
# qt6-qtwayland: bez niego programy Qt działają przez XWayland (gorsze skalowanie, problemy z fokusem okien)
REQUIRED_PKGS="labwc python3-pyside6 qt6-qtwayland python3-psutil python3-pefile wlr-randr xdg-user-dirs polkit"
# Pakiety zalecane: nazwa:opis
RECOMMENDED_PKGS="
wine-tahoma-fonts:czcionka interfejsu Tahoma (z projektu Wine)
fedora-logos:logo Fedory na przycisku Start
grim:zrzuty ekranu (Print Screen)
swayidle:wygaszacz ekranu po bezczynności
swaylock:blokada ekranu
NetworkManager:połączenia sieciowe i Wi-Fi
bluez:obsługa Bluetooth
bluez-obexd:wysyłanie plików przez Bluetooth
pulseaudio-utils:Regulacja głośności (pactl)
xdg-utils:otwieranie plików i adresów
xdg-desktop-portal-gtk:okna wyboru plików i „Pokaż w folderze” dla aplikacji Flatpak
xdg-desktop-portal-wlr:udostępnianie ekranu (wideorozmowy, nagrywanie)
gnome-keyring:przechowywanie haseł (przeglądarki, poczta, Wi-Fi)
glib2:dyski sieciowe i Kosz (gio)
udisks2:montowanie obrazów płyt (.iso) jako stacji CD i nośników USB
7zip:archiwa 7z, ZIP z szyfrowaniem AES i inne
unar:archiwa RAR (także z hasłem)
flatpak:aplikacje Flatpak
PackageKit:sprawdzanie aktualizacji bez hasła (pkcon)
cups:drukowanie
lxpolkit:zapasowy agent uwierzytelniania dla innych programów
qt6-qtmultimedia:Odtwarzacz multimediów i Rejestrator dźwięku
pipewire-utils:nagrywanie dźwięku (pw-record)
pipewire-pulseaudio:dźwięk dla starszych programów (pactl)
gstreamer1-plugins-good:odtwarzanie popularnych formatów audio i wideo
pciutils:nazwy urządzeń w Menedżerze urządzeń (lspci)
usbutils:nazwy urządzeń USB (lsusb)
hwdata:baza nazw sprzętu
dejavu-sans-fonts:czcionki zapasowe
dejavu-sans-mono-fonts:czcionka Wiersza polecenia
google-noto-color-emoji-fonts:emoji w Mapie znaków i programach
"

INSTALLED_OK=""
SKIPPED=""

detect_dnf() {
    DNF="$(command -v dnf5 || command -v dnf || true)"
    DNF_SKIP=""
    if [ -n "$DNF" ]; then
        if "$DNF" --version 2>/dev/null | grep -qi "dnf5\|^5\."; then
            DNF_SKIP="--skip-unavailable"
        else
            DNF_SKIP="--setopt=strict=0"
        fi
    fi
}

pkg_installed() { rpm -q "$1" >/dev/null 2>&1; }

pkg_available() {
    "$DNF" -q list --available "$1" >/dev/null 2>&1 || "$DNF" -q repoquery "$1" 2>/dev/null | grep -q .
}

install_required() {
    [ -n "$DNF" ] || { warn "Brak dnf — pomijam instalację pakietów."; return 0; }
    local missing=""
    for p in $REQUIRED_PKGS; do pkg_installed "$p" || missing="$missing $p"; done
    if [ -z "$missing" ]; then ok "Wymagane pakiety są już zainstalowane."; return 0; fi
    say "Instalowanie wymaganych pakietów:$missing"
    if ! $SUDO "$DNF" install -y $DNF_SKIP $missing; then
        err "Nie udało się zainstalować wymaganych pakietów:$missing"
        return 1
    fi
    for p in $missing; do
        pkg_installed "$p" || { err "Pakiet $p jest niedostępny w repozytoriach — Horyzont może nie działać."; }
    done
}

install_recommended() {
    [ -n "$DNF" ] || return 0
    say "Pakiety zalecane (każdy sprawdzany osobno, brakujące w repozytoriach są pomijane)..."
    local todo=""
    while IFS=: read -r p desc; do
        [ -z "$p" ] && continue
        if pkg_installed "$p"; then INSTALLED_OK="$INSTALLED_OK\n   $p — $desc (już zainstalowany)"; continue; fi
        todo="$todo $p"
    done <<EOF
$RECOMMENDED_PKGS
EOF
    # profil zasilania: w Fedorze 41+ jest tuned-ppd, który wyklucza power-profiles-daemon
    if ! pkg_installed tuned-ppd && ! pkg_installed power-profiles-daemon; then
        todo="$todo tuned-ppd"
    fi
    if [ -n "$todo" ]; then
        $SUDO "$DNF" install -y $DNF_SKIP $todo >/tmp/horyzont-install-dnf.log 2>&1 || true
    fi
    for p in $todo; do
        desc="$(printf '%s\n' "$RECOMMENDED_PKGS" | sed -n "s/^$p://p")"
        if pkg_installed "$p"; then
            INSTALLED_OK="$INSTALLED_OK\n   $p — ${desc:-profil zasilania}"
        else
            SKIPPED="$SKIPPED\n   $p — ${desc:-profil zasilania} (niedostępny w włączonych repozytoriach)"
        fi
    done
}

# Sprawdzenie, czy po instalacji naprawdę jest wszystko, bez czego sesja nie wystartuje
verify_required() {
    local bad=0
    if ! command -v labwc >/dev/null 2>&1; then
        err "Brak kompozytora labwc. Zainstaluj go poleceniem:  sudo dnf install labwc"
        bad=1
    fi
    for mod in PySide6 PySide6.QtSvg psutil; do
        if ! python3 -c "import $mod" 2>/dev/null; then
            err "Brak modułu Pythona $mod (pakiet python3-pyside6 / python3-psutil)."
            bad=1
        fi
    done
    if ! python3 - <<'PY' 2>/dev/null
import os, sys
from PySide6.QtCore import QLibraryInfo
d = os.path.join(QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath), "platforms")
sys.exit(0 if any(f.startswith("libqwayland") for f in os.listdir(d)) else 1)
PY
    then
        err "Brak wtyczki Wayland dla Qt (pakiet qt6-qtwayland) — programy Horyzontu działałyby przez XWayland."
        bad=1
    fi
    command -v wlr-randr >/dev/null 2>&1 || warn "Brak wlr-randr — zmiana rozdzielczości w Panelu sterowania nie zadziała."
    command -v pkexec >/dev/null 2>&1 || warn "Brak pkexec (polkit) — zadania administracyjne nie zadziałają."
    python3 -c "import PySide6.QtMultimedia" 2>/dev/null || warn "Brak QtMultimedia — Odtwarzacz multimediów i Rejestrator dźwięku będą ograniczone."
    [ $bad = 0 ] && ok "Wszystkie wymagane składniki są obecne (labwc $(labwc --version 2>/dev/null | awk '{print $2}'), PySide6)."
    return $bad
}

# Ekran logowania: bez niego nie da się wybrać sesji Horyzont. Instalujemy SDDM tylko, gdy nie ma żadnego.
ensure_display_manager() {
    [ -n "$DNF" ] || return 0
    for dm in gdm sddm lightdm lxdm greetd; do
        if pkg_installed "$dm"; then ok "Ekran logowania: $dm"; return 0; fi
    done
    if [ "${HORYZONT_NO_DM:-0}" = 1 ]; then
        warn "Brak ekranu logowania — Horyzont uruchomisz z konsoli poleceniem: horyzont-session"
        return 0
    fi
    say "Brak ekranu logowania — instaluję SDDM (wyłączysz to zmienną HORYZONT_NO_DM=1)."
    if $SUDO "$DNF" install -y sddm >/tmp/horyzont-install-dnf.log 2>&1; then
        $SUDO systemctl enable sddm >/dev/null 2>&1 || true
        $SUDO systemctl set-default graphical.target >/dev/null 2>&1 || true
        INSTALLED_OK="$INSTALLED_OK\n   sddm — ekran logowania (uruchomi się po restarcie)"
    else
        warn "Nie udało się zainstalować SDDM — Horyzont uruchomisz z konsoli poleceniem: horyzont-session"
    fi
}

python_fallbacks() {
    for mod in PySide6:PySide6 psutil:psutil pefile:pefile; do
        name="${mod%%:*}"; pipname="${mod##*:}"
        if ! python3 -c "import $name" 2>/dev/null; then
            warn "Brak modułu Pythona $name — instaluję z PyPI dla użytkownika (pip --user)"
            python3 -m pip install --user "$pipname" || err "Nie udało się zainstalować $pipname"
        fi
    done
}

check_labwc() {
    if command -v labwc >/dev/null 2>&1; then
        v="$(labwc --version 2>/dev/null | awk '{print $2}')"
        if [ -n "$v" ] && [ "$(printf '%s\n0.8.2\n' "$v" | sort -V | head -1)" != "0.8.2" ]; then
            warn "labwc $v jest starszy niż 0.8.2 — pasek zadań może mieć złą wysokość."
        fi
    fi
}

# kopiowanie plików Horyzontu do $PREFIX
copy_files() {
    local SRC="$1"
    PKGDIR="$PREFIX/share/horyzont"
    say "Kopiowanie plików do $PKGDIR ..."
    $SUDO mkdir -p "$PKGDIR" "$PREFIX/bin" "$PREFIX/share/applications" "$PREFIX/libexec/horyzont" /usr/share/wayland-sessions
    $SUDO rm -rf "$PKGDIR/horyzont.new"
    $SUDO cp -r "$SRC/horyzont" "$PKGDIR/horyzont.new"
    $SUDO find "$PKGDIR/horyzont.new" -name "__pycache__" -type d -prune -exec rm -rf {} +
    $SUDO rm -rf "$PKGDIR/horyzont.old"
    [ -d "$PKGDIR/horyzont" ] && $SUDO mv "$PKGDIR/horyzont" "$PKGDIR/horyzont.old"
    $SUDO mv "$PKGDIR/horyzont.new" "$PKGDIR/horyzont"
    $SUDO rm -rf "$PKGDIR/horyzont.old"
    for d in docs tools; do
        [ -d "$SRC/$d" ] && { $SUDO rm -rf "$PKGDIR/$d"; $SUDO cp -r "$SRC/$d" "$PKGDIR/$d"; }
    done
    $SUDO cp "$SRC/update.sh" "$SRC/uninstall.sh" "$PKGDIR/" 2>/dev/null || true
    $SUDO mkdir -p "$PKGDIR/packaging"
    $SUDO cp "$SRC/packaging/install-lib.sh" "$PKGDIR/packaging/"
    for f in "$SRC"/bin/*; do
        $SUDO sh -c "sed 's#@PKGDIR@#$PKGDIR#g' '$f' > '$PREFIX/bin/$(basename "$f")'"
        $SUDO chmod 755 "$PREFIX/bin/$(basename "$f")"
    done
    $SUDO ln -sf "$PKGDIR/tools/make-msicon.sh" "$PREFIX/bin/horyzont-msicon"
    $SUDO cp "$SRC"/share/applications/*.desktop "$PREFIX/share/applications/"
    # domyślne programy tylko dla sesji Horyzont (np. foldery → Eksplorator zamiast Nautilusa)
    $SUDO cp "$SRC/share/applications/horyzont-mimeapps.list" "$PREFIX/share/applications/"
    $SUDO mkdir -p /usr/share/xdg-desktop-portal
    $SUDO cp "$SRC/share/xdg-desktop-portal/horyzont-portals.conf" /usr/share/xdg-desktop-portal/
    command -v update-desktop-database >/dev/null && $SUDO update-desktop-database -q "$PREFIX/share/applications" 2>/dev/null || true
    $SUDO sh -c "sed 's#^Exec=horyzont-session#Exec=$PREFIX/bin/horyzont-session#; s#^TryExec=horyzont-session#TryExec=$PREFIX/bin/horyzont-session#' \
        '$SRC/share/wayland-sessions/horyzont.desktop' > /usr/share/wayland-sessions/horyzont.desktop"
    # agent aktualizacji (uruchamiany przez timer systemd i przez pkexec)
    $SUDO sh -c "cat > '$PREFIX/libexec/horyzont/update-agent'" <<EOF
#!/bin/sh
# Horyzont Updates — agent uruchamiany jako root
export PYTHONPATH="$PKGDIR"
exec /usr/bin/python3 -m horyzont update-agent "\$@"
EOF
    $SUDO chmod 755 "$PREFIX/libexec/horyzont/update-agent"
    [ -n "$HORYZONT_REPO" ] && echo "$HORYZONT_REPO" | $SUDO tee "$PKGDIR/horyzont/REPO" >/dev/null
    [ -f "$SRC/REPO" ] && $SUDO cp "$SRC/REPO" "$PKGDIR/horyzont/REPO"
    $SUDO python3 -m compileall -q "$PKGDIR/horyzont" >/dev/null 2>&1 || true
}

install_system_files() {
    local SRC="$1"
    # usługa i timer aktualizacji (timer włącza się dopiero po zapisaniu ustawień w Horyzont Updates)
    $SUDO sh -c "sed 's#@AGENT@#$PREFIX/libexec/horyzont/update-agent#g' '$SRC/share/systemd/horyzont-updates.service' > /etc/systemd/system/horyzont-updates.service"
    $SUDO cp "$SRC/share/systemd/horyzont-updates.timer" /etc/systemd/system/horyzont-updates.timer
    $SUDO mkdir -p /var/lib/horyzont /etc/horyzont
    # polityka polkit: czytelny opis w oknie hasła
    $SUDO mkdir -p /usr/share/polkit-1/actions
    $SUDO sh -c "sed 's#@AGENT@#$PREFIX/libexec/horyzont/update-agent#g' '$SRC/share/polkit/org.horyzont.update-agent.policy' > /usr/share/polkit-1/actions/org.horyzont.update-agent.policy"
    command -v systemctl >/dev/null && $SUDO systemctl daemon-reload 2>/dev/null || true
    # jeśli ustawienia już zapisano — timer pozostaje w swoim stanie; przy pierwszej instalacji włączamy tryb „powiadamiaj”
    if [ ! -f /etc/horyzont/updates.json ]; then
        echo '{"mode": "notify", "frequency": "daily", "time": "03:00", "takeover": false}' | $SUDO tee /etc/horyzont/updates.json >/dev/null
        $SUDO systemctl enable --now horyzont-updates.timer >/dev/null 2>&1 || true
    fi
}

print_summary() {
    echo
    say "Podsumowanie"
    [ -n "$INSTALLED_OK" ] && { echo "  Zainstalowane dodatki:"; printf "$INSTALLED_OK\n"; }
    if [ -n "$SKIPPED" ]; then
        echo "  Pominięte (Horyzont działa bez nich, ale część funkcji będzie niedostępna):"
        printf "$SKIPPED\n"
        echo "  Szczegóły: /tmp/horyzont-install-dnf.log"
    fi
}
