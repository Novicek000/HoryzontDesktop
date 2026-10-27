#!/bin/bash
# Buduje paczkę wydania Horyzontu: dist/horyzont-<wersja>.tar.gz oraz dist/SHA256SUMS.
# Użycie: tools/make-release.sh   (z katalogu głównego repozytorium)
set -e
cd "$(dirname "$0")/.."
VER="$(python3 -c 'from horyzont import config; print(config.VERSION)')"
NAME="horyzont-$VER"
OUT="dist"
mkdir -p "$OUT"
TMP="$(mktemp -d)"
mkdir "$TMP/$NAME"
tar --exclude=__pycache__ --exclude='*.pyc' --exclude=.git --exclude=dist --exclude=tests -cf - . | tar -xf - -C "$TMP/$NAME"
cp packaging/horyzont.spec "$TMP/$NAME/horyzont.spec"
rm -f "$TMP/$NAME/packaging/horyzont.spec"
tar czf "$OUT/$NAME.tar.gz" --owner=0 --group=0 -C "$TMP" "$NAME"
(cd "$OUT" && sha256sum "$NAME.tar.gz" > SHA256SUMS)
rm -rf "$TMP"
echo "Gotowe: $OUT/$NAME.tar.gz"
echo "Utwórz wydanie: gh release create v$VER $OUT/$NAME.tar.gz $OUT/SHA256SUMS --title \"Horyzont $VER\""
