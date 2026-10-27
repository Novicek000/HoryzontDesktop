#!/bin/bash
# Instalator środowiska Horyzont dla Fedory.
# Użycie:  ./install.sh                  (instalacja do /usr/local, wymaga sudo)
#          PREFIX=/usr ./install.sh
#          HORYZONT_REPO=uzytkownik/horyzont ./install.sh   (inne repozytorium GitHub dla Horyzont Updates)
#          HORYZONT_NO_DM=1 ./install.sh           (nie instaluj ekranu logowania, gdy go nie ma)
#
# Instalator sam pobiera przez dnf wszystko, czego Horyzont potrzebuje: kompozytor labwc, PySide6 (Qt),
# psutil, wlr-randr, polkit, a także pakiety zalecane (sieć, Bluetooth, dźwięk, multimedia, archiwa, czcionki).
set -e
PREFIX="${PREFIX:-/usr/local}"
SRC="$(cd "$(dirname "$0")" && pwd)"
SUDO=""
[ "$(id -u)" -ne 0 ] && SUDO="sudo"
. "$SRC/packaging/install-lib.sh"

if ! grep -qi fedora /etc/os-release 2>/dev/null; then
    warn "To nie wygląda na Fedorę — instalacja zależności przez dnf może się nie udać."
fi
detect_dnf
install_required || { err "Przerwano. Sprawdź połączenie z Internetem i repozytoria dnf."; exit 1; }
install_recommended
python_fallbacks
verify_required || { err "Instalacja przerwana — brakuje składników wymienionych wyżej."; exit 1; }
check_labwc
ensure_display_manager
copy_files "$SRC"
install_system_files "$SRC"
print_summary
echo
ok "Gotowe. Wyloguj się i wybierz sesję \"Horyzont\" na ekranie logowania."
