#!/bin/bash
# Horyzont — aktualizacja istniejącej instalacji.
#
#   ./update.sh                      instaluje wersję z tego katalogu (ustawienia użytkowników zostają)
#   ./update.sh --github wl/repo     pobiera najnowsze wydanie z GitHuba i je instaluje
#   ./update.sh --yes                bez pytań (używane przez Horyzont Updates)
set -e
SRC="$(cd "$(dirname "$0")" && pwd)"
YES=0; GITHUB=""
while [ $# -gt 0 ]; do
    case "$1" in
        --yes|-y) YES=1;;
        --github) GITHUB="$2"; shift;;
        *) echo "Nieznana opcja: $1"; exit 2;;
    esac
    shift
done
. "$SRC/packaging/install-lib.sh"

if [ -n "$GITHUB" ]; then
    say "Pobieranie najnowszego wydania z github.com/$GITHUB ..."
    TMP="$(mktemp -d)"
    URL="$(python3 - "$GITHUB" <<'PY'
import json, sys, urllib.request
repo = sys.argv[1]
req = urllib.request.Request(f"https://api.github.com/repos/{repo}/releases/latest", headers={"User-Agent": "Horyzont"})
try:
    d = json.load(urllib.request.urlopen(req, timeout=30))
    url = next((a["browser_download_url"] for a in d.get("assets", []) if a["name"].endswith((".tar.gz", ".tgz"))), d.get("tarball_url"))
except Exception:
    # brak wydań — bierzemy najnowszy tag, a w ostateczności gałąź main
    try:
        req = urllib.request.Request(f"https://api.github.com/repos/{repo}/tags", headers={"User-Agent": "Horyzont"})
        tags = json.load(urllib.request.urlopen(req, timeout=30))
        url = f"https://api.github.com/repos/{repo}/tarball/{tags[0]['name']}"
    except Exception:
        url = f"https://github.com/{repo}/archive/refs/heads/main.tar.gz"
print(url)
PY
)"
    [ -n "$URL" ] || { err "Nie znaleziono wydania."; exit 1; }
    curl -fsSL "$URL" -o "$TMP/h.tar.gz" || python3 -c "import urllib.request,sys; urllib.request.urlretrieve(sys.argv[1], sys.argv[2])" "$URL" "$TMP/h.tar.gz"
    tar xzf "$TMP/h.tar.gz" -C "$TMP"
    NEW="$(dirname "$(find "$TMP" -maxdepth 2 -name update.sh | head -1)")"
    [ -f "$NEW/update.sh" ] || { err "W archiwum nie ma update.sh"; exit 1; }
    echo "$GITHUB" > "$NEW/REPO"
    exec bash "$NEW/update.sh" $( [ $YES = 1 ] && echo --yes )
fi

# uprawnienia administratora
SUDO=""
if [ "$(id -u)" -ne 0 ]; then
    if command -v sudo >/dev/null 2>&1 && [ -t 0 ]; then SUDO="sudo"
    else exec pkexec bash "$SRC/update.sh" "$@"; fi
fi

# gdzie jest obecna instalacja
if [ -z "$PREFIX" ]; then
    for p in /usr/local /usr; do [ -d "$p/share/horyzont/horyzont" ] && PREFIX="$p" && break; done
fi
PREFIX="${PREFIX:-/usr/local}"
OLD="$(PYTHONPATH="$PREFIX/share/horyzont" python3 -c 'from horyzont import config; print(config.VERSION)' 2>/dev/null || echo '?')"
NEWV="$(PYTHONPATH="$SRC" python3 -c 'from horyzont import config; print(config.VERSION)' 2>/dev/null || echo '?')"
say "Aktualizacja Horyzontu: $OLD → $NEWV (katalog: $PREFIX)"
if [ $YES = 0 ] && [ -t 0 ]; then
    read -r -p "Kontynuować? [T/n] " a
    case "$a" in n|N) exit 0;; esac
fi
# zachowujemy repozytorium aktualizacji zapisane przy poprzedniej instalacji
if [ -z "$HORYZONT_REPO" ] && [ ! -f "$SRC/REPO" ] && [ -f "$PREFIX/share/horyzont/horyzont/REPO" ]; then
    HORYZONT_REPO="$(cat "$PREFIX/share/horyzont/horyzont/REPO")"
fi
detect_dnf
install_required || warn "Nie wszystkie wymagane pakiety udało się zainstalować."
install_recommended
copy_files "$SRC"
install_system_files "$SRC"
ok "Horyzont $NEWV zainstalowany. Wyloguj się i zaloguj ponownie, aby zakończyć aktualizację."
