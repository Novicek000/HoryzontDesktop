#!/bin/bash
# Horyzont — pakowanie zestawu ikon do pliku .msicon (to zwykły ZIP ze zmienionym rozszerzeniem).
#
# Użycie:  ./make-msicon.sh <folder-zestawu> [plik-wyjściowy.msicon]
#
# Folder zestawu:
#   manifest.ini        [Icon Pack]  Name=  Author=  Version=  Description=
#   icons/<nazwa>.svg   (albo .png / .ico; opcjonalnie <nazwa>@16.png, @32, @48, @256)
#
# Listę nazw ikon znajdziesz w pliku LISTA-IKON.txt w szablonie
# (Panel sterowania → Ekran → Ikony → Eksportuj szablon...) albo w docs/IKONY.md.
set -e
SRC="${1:?Podaj folder zestawu ikon}"
SRC="${SRC%/}"
[ -d "$SRC/icons" ] || { echo "Brak podfolderu icons/ w $SRC" >&2; exit 1; }
NAME="$(sed -n 's/^Name=//p' "$SRC/manifest.ini" 2>/dev/null | head -1)"
[ -n "$NAME" ] || NAME="$(basename "$SRC")"
OUT="${2:-$(pwd)/$(echo "$NAME" | tr ' /' '--').msicon}"
case "$OUT" in /*) ;; *) OUT="$(pwd)/$OUT";; esac

# sprawdzenie nazw plików (ostrzeżenie o literówkach)
LIST="$(dirname "$0")/../docs/lista-ikon.txt"
if [ -f "$LIST" ]; then
    for f in "$SRC"/icons/*; do
        b="$(basename "$f")"; n="${b%.*}"; n="${n%@*}"
        grep -qx "$n" "$LIST" || echo "!! nieznana nazwa ikony: $b (zostanie pominięta przez Horyzont)" >&2
    done
fi

rm -f "$OUT"
if command -v zip >/dev/null 2>&1; then
    (cd "$SRC" && zip -q -r -X "$OUT" manifest.ini icons $( [ -f README.txt ] && echo README.txt ) )
else
    python3 - "$SRC" "$OUT" <<'PY'
import os, sys, zipfile
src, out = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for root, dirs, files in os.walk(src):
        for f in files:
            p = os.path.join(root, f)
            rel = os.path.relpath(p, src)
            if rel == "manifest.ini" or rel.startswith("icons" + os.sep) or rel == "README.txt":
                z.write(p, rel)
PY
fi
echo "Gotowe: $OUT ($(unzip -l "$OUT" 2>/dev/null | tail -1 | awk '{print $2}') plików)"
