# Horyzont — klasyczne środowisko pulpitu dla Fedory

Horyzont to środowisko pulpitu w układzie i stylu pracy znanym z systemów biurkowych
z początku lat 2000: pasek zadań na dole, dwukolumnowe menu Start, ikony na pulpicie,
Eksplorator z panelem zadań, Panel sterowania z kategoriami, Menedżer zadań, Horyzont Updates
i komplet akcesoriów: Notatnik, WordPad, Paint, Kalkulator, Mapa znaków, Wiersz polecenia, Przeglądarka obrazów
i faksów, Odtwarzacz multimediów, Rejestrator dźwięku oraz gry Saper i Pasjans.

Działa na kompozytorze **labwc** (Wayland, wlroots), a powłoka i programy są napisane
w **Pythonie + Qt (PySide6)**. Cała grafika (ikony, tapety, wskaźniki myszy, styl okien, logo,
dźwięki) jest oryginalna i rysowana w kodzie. Wygląd można zmienić na **własny plik `.msstyles`**,
ikony — na **zestaw `.msicon`**, a wskaźniki — na własny schemat (także z plików `.cur`/`.ani`).

## Co nowego w wersji 0.3

| Program | Co potrafi |
|---|---|
| **Kalkulator** | widok standardowy i naukowy: kolejność działań, nawiasy, trygonometria (stopnie/radiany/gradusy), logarytmy, silnia, systemy HEX/DEC/OCT/BIN z rozmiarem słowa, operacje bitowe, statystyka, pamięć, grupowanie cyfr, kopiuj/wklej, obsługa klawiatury; dokładna arytmetyka dziesiętna (0,1 + 0,2 = 0,3) |
| **Mapa znaków** | wszystkie znaki czcionki, powiększenie po kliknięciu, kopiowanie, grupy Unicode, wyszukiwanie po nazwie, skok do kodu U+, kody Alt |
| **Paint** | 16 narzędzi (zaznaczenia, gumka, wypełnianie, pipeta, lupa, ołówek, pędzel, aerograf, tekst, linia, krzywa, prostokąt, wielokąt, elipsa, zaokrąglony prostokąt), paleta 28 kolorów, powiększenie i siatka, przerzucanie/obracanie/rozciąganie/pochylanie, odwracanie kolorów, zmiana rozmiaru uchwytami, cofanie, schowek, zapis BMP/PNG/JPEG/GIF/TIFF/WebP/ICO, tło pulpitu |
| **WordPad** | czcionki, kolory, wyrównanie, punktory, akapity, tabulatory, linijka z przeciąganymi wcięciami, obrazy, znajdź/zamień, podgląd wydruku; pliki **RTF, DOCX, ODT**, TXT, HTML (stare DOC przez LibreOffice) |
| **Saper** | trzy poziomy i pole niestandardowe, flagi i znaki zapytania, „akord” obu przycisków, najlepsze wyniki, opcjonalny dźwięk |
| **Pasjans** | Klondike: dobieranie po 1/3, punktacja standardowa i Vegas (także łączna), gra na czas, cofanie, 8 wzorów talii, autouzupełnianie prawym przyciskiem, klasyczna animacja wygranej |
| **Przeglądarka obrazów i faksów** | przeglądanie folderu, dopasowanie i rzeczywisty rozmiar, powiększanie, obracanie, pokaz slajdów, animowane GIF, usuwanie do Kosza, drukowanie, „Edytuj w Paint” |
| **Odtwarzacz multimediów** | muzyka i filmy, lista odtwarzania (M3U/PLS, foldery, adresy URL), losowo/w pętli, pełny ekran, okładki i tagi, wizualizacja liczona z prawdziwego dźwięku |
| **Rejestrator dźwięku** | nagrywanie z mikrofonu, odtwarzanie, efekty (głośność, szybkość, echo, odwrócenie), wstawianie i miksowanie plików, zapis WAV (oraz OGG/MP3/FLAC z ffmpeg) |

Wszystkie grafiki programów (ikony narzędzi, karty, miny, przyciski) są oryginalne i rysowane w kodzie.
Pliki obrazów, dokumentów i multimediów otwierają się wbudowanymi programami, chyba że w systemie ustawiono inny
domyślny program. W Eksploratorze w menu kontekstowym są polecenia **Podgląd**, **Edytuj** i **Odtwórz**.

Instalator sam instaluje wszystkie potrzebne pakiety (labwc, PySide6, psutil, polkit…), sprawdza po instalacji, czy
niczego nie brakuje, a gdy w systemie nie ma żadnego ekranu logowania — instaluje SDDM.

## Co nowego w wersji 0.2.1

* **Ikony programów w zasobniku** — programy, które chowają się do zasobnika (Discord, Steam, Telegram, Nextcloud,
  KeePassXC, OBS, programy Qt/Electron/AppIndicator), pokazują ikonę w prawym dolnym rogu paska zadań obok zegara.
  Lewy przycisk — otwiera program, prawy — jego menu, środkowy — akcja dodatkowa, kółko — przewijanie.
* **Powiadomienia jako dymki** — Horyzont jest serwerem powiadomień (org.freedesktop.Notifications): powiadomienia
  z `notify-send`, przeglądarek, komunikatorów itp. pojawiają się jako żółte dymki nad zasobnikiem, po jednym,
  z ogonkiem wskazującym ikonę programu; obsługa akcji (odnośniki w dymku), pilnych powiadomień i dźwięku.
  Mako i nm-applet nie są już potrzebne.
* **Autostart** — programy z `~/.config/autostart` i `/etc/xdg/autostart` uruchamiają się po zalogowaniu.
* Panel sterowania → Pasek zadań i menu Start → „Obszar powiadomień”: włączanie ikon programów i dymków,
  przycisk „Testuj dymek”.

## Co nowego w wersji 0.2

| Obszar | Zmiany |
|---|---|
| **Pasek zadań** | lista okien bez modułu pywayland (własny klient protokołu Wayland), logo dystrybucji (Fedora) na przycisku Start — do wyboru w Panelu sterowania (logo systemu / Horyzont / brak / własny obraz), ikony Wi-Fi i Bluetooth, tarcza aktualizacji, dymki powiadomień, stan zbierany w tle (bez przycięć) |
| **Menu Start** | otwiera się natychmiast (budowane zawczasu), zawsze w lewym dolnym rogu — także po klawiszu Windows; obsługa strzałek i Enter; okno Uruchamianie w lewym dolnym rogu |
| **Okna** | ramka pozostaje aktywna podczas przeciągania; kursor zmiany rozmiaru nie „zostaje” po zjechaniu z krawędzi; szybsze rysowanie stylów .msstyles |
| **Wiersz polecenia** | własny emulator terminala (xterm-256color): bash, vim, htop, mc; tryb szybkiej edycji, właściwości (czcionka, kolory, układ), klasyczny monit `~/Dokumenty>` |
| **Eksplorator** | archiwa ZIP, RAR, 7z, TAR, ISO… jako foldery skompresowane, hasła, Kreator wyodrębniania, „Wyślij do → Folder skompresowany (zip)”, „Dodaj do archiwum…” z hasłem AES; menu kontekstowe w „Inne miejsca” |
| **Uprawnienia** | własne okno hasła administratora (agent polkit w stylu Horyzontu) — koniec z błędem „Error creating textual authentication agent” |
| **Panel sterowania** | Horyzont Updates i Aktualizacje automatyczne, Aplikacje Flatpak (Flathub), Urządzenia Bluetooth z kreatorem, Sieci bezprzewodowe, Kreator nowego połączenia i właściwości TCP/IP (bez zewnętrznych programów), pełne zarządzanie kontami (tworzenie, hasła, typ konta, grupy, usuwanie z zachowaniem plików), schematy dźwiękowe, schematy wskaźników myszy, zestawy ikon .msicon |

## Wymagania

* Fedora 41 lub nowsza (labwc **0.8.2+** — starsze wersje wymuszają wysokość okna ≥ 60 px, co psuje pasek zadań)
* wymagane pakiety: `labwc python3-pyside6 python3-psutil python3-pefile wlr-randr xdg-user-dirs polkit`
* zalecane: `wine-tahoma-fonts fedora-logos grim swayidle swaylock NetworkManager bluez pavucontrol
  xdg-utils glib2 7zip unar flatpak PackageKit cups lxpolkit qt6-qtmultimedia pipewire-utils
  gstreamer1-plugins-good` i czcionki (instalator sprawdza każdy osobno i pomija te, których nie ma
  w repozytoriach — na końcu wypisuje podsumowanie)
* **wszystko to instaluje `install.sh`** — wystarczy go uruchomić
* kodeki MP3/AAC/H.264 dla Odtwarzacza multimediów: pakiet `ffmpeg` z [RPM Fusion](https://rpmfusion.org)
  (Fedora nie dostarcza ich ze względów licencyjnych)

## Instalacja

```bash
tar xzf horyzont-0.3.0.tar.gz
cd horyzont-0.3.0
./install.sh
```

albo prosto z GitHuba:

```bash
git clone https://github.com/Novicek000/HoryzontDesktop.git
cd HoryzontDesktop
./install.sh
```

Horyzont Updates sprawdza nowe wersje w repozytorium **Novicek000/HoryzontDesktop** (inne repozytorium:
`HORYZONT_REPO=uzytkownik/repo ./install.sh`).

Następnie wyloguj się i na ekranie logowania (GDM/SDDM) wybierz sesję **Horyzont**.

Usuwanie: `./uninstall.sh` (ustawienia zostają w `~/.config/horyzont`).

## Aktualizacja

* **Z Horyzont Updates** (Start → Wszystkie programy → Horyzont Updates) — sprawdza dnf, Flatpak i nowe wersje
  Horyzontu z GitHuba, instaluje je i pyta o ponowne uruchomienie powłoki.
* **Ręcznie z nowej paczki**: rozpakuj nową wersję i uruchom `./update.sh` (ustawienia użytkowników zostają).
* **Prosto z GitHuba**: `./update.sh --github Novicek000/HoryzontDesktop`.

### Publikowanie nowej wersji na GitHubie

1. Zmień `VERSION` w `horyzont/config.py` (np. `0.4.0`) i wyślij zmiany (`git push`).
2. Utwórz tag `v0.4.0` (`git tag v0.4.0 && git push --tags`) — to wystarczy: Horyzont Updates pobierze
   archiwum kodu z tego tagu.
3. Lepiej: utwórz na GitHubie wydanie (Release) z tagiem `v0.4.0` i dołącz paczkę `horyzont-0.4.0.tar.gz`
   (oraz opcjonalnie `SHA256SUMS` — Horyzont sprawdzi sumę). Opis wydania (Markdown) pokazuje się w oknie
   Horyzont Updates jako lista zmian. Paczkę zbudujesz skryptem `tools/make-release.sh`.

## Aktualizacje automatyczne

Panel sterowania → Centrum zabezpieczeń → **Aktualizacje automatyczne** (albo Horyzont Updates → Zmień ustawienia):

* tryby: *automatycznie* (pobieranie i instalacja w tle), *tylko pobieranie*, *tylko powiadamianie*, *wyłączone*;
* częstotliwość: co godzinę, co 6 godzin, codziennie lub co tydzień o wybranej godzinie (timer systemd
  `horyzont-updates.timer`, uruchamiany jako root);
* **Horyzont zarządza aktualizacjami** — wyłącza `dnf-automatic*.timer` i automatyczne pobieranie w GNOME Software,
  by aktualizacje nie były instalowane dwa razy (odznaczenie przywraca ustawienia Fedory).

## Style `.msstyles` i zestawy ikon `.msicon`

Panel sterowania → Wygląd i kompozycje → **Ekran**:

* karta **Kompozycje** → **Przeglądaj…** — plik `.msstyles` lub `.theme` (kopiowany do `~/.local/share/horyzont/themes/`);
* karta **Ikony** — zestaw ikon `.msicon` (ZIP z `manifest.ini` i folderem `icons/`). Opis formatu i wszystkie
  nazwy ikon: [docs/IKONY.md](docs/IKONY.md), skrypt pakujący: `tools/make-msicon.sh` (po instalacji: `horyzont-msicon`).

Horyzont nie dołącza żadnych cudzych stylów ani ikon — korzystasz z plików, do których masz prawa.

## Skróty klawiaturowe

| Klawisze | Działanie |
|---|---|
| Super | menu Start |
| Super+E | Mój komputer |
| Super+R | Uruchamianie |
| Super+D / Super+M | pokaż pulpit |
| Super+F | wyszukiwanie |
| Super+L | blokada ekranu |
| Super+Pause | Właściwości systemu |
| Ctrl+Shift+Esc, Ctrl+Alt+Del | Menedżer zadań |
| Alt+Tab, Alt+F4, Alt+Spacja | przełączanie / zamykanie / menu okna |
| Print Screen | zrzut ekranu do `~/Pictures` |

## Pliki i katalogi

* `~/.config/horyzont/settings.json` — ustawienia (usunięcie = ustawienia domyślne)
* `~/.config/horyzont/labwc/` — generowana konfiguracja kompozytora
* `~/.cache/horyzont/shell.log` — dziennik powłoki
* `~/.local/share/horyzont/themes/`, `.../iconpacks/` — wczytane style i zestawy ikon
* `~/.icons/Horyzont` — oryginalny motyw wskaźników (tworzony przy pierwszym logowaniu)
* `/etc/horyzont/updates.json`, `/var/lib/horyzont/` — ustawienia i stan aktualizacji automatycznych

## Budowa kodu

```
horyzont/
  __main__.py          punkt wejścia: python3 -m horyzont <program>
  theme/               silnik motywów, ikony (icons*.py), zestawy .msicon, wskaźniki (cursors.py)
  shell/               powłoka: pulpit, pasek zadań, zasobnik (traystatus.py, sni.py), dymki i powiadomienia
                       (balloon.py, notifications.py), autostart, menu Start, okna sesji
  wm/                  lista okien: własny klient Wayland (wlclient.py) + wlr-foreign-toplevel-management
  session/             konfiguracja labwc i start sesji
  common/              klient D-Bus (dbus.py), okna z ramką, uprawnienia (privileged.py), archiwa, sieć (netman.py), kursory (xcursor.py)
  updates/             Horyzont Updates: sprawdzanie, agent systemowy
  apps/explorer/       Eksplorator, archiwa, wyszukiwanie, Pomoc
  apps/terminal/       Wiersz polecenia (emulator VT)
  apps/calc.py, charmap.py, paint.py, wordpad.py, imageviewer.py, mediaplayer.py, soundrec.py
  apps/games/          Saper, Pasjans, karty (cards.py)
  common/richtext.py   RTF/DOCX/ODT dla WordPada
  apps/control/        Panel sterowania i aplety
packaging/install-lib.sh  wspólne funkcje install.sh / update.sh
tools/make-msicon.sh   pakowanie zestawu ikon
tools/make-release.sh  budowa paczki .tar.gz i SHA256SUMS do wydania na GitHubie
```

## Plan kolejnych etapów

Ekran powitalny, ukrywanie nieaktywnych ikon zasobnika, autoukrywanie paska zadań, klasyczne menu Start,
kolejne gry (Kier, FreeCell, Pająk).
