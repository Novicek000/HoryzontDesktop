# Zestawy ikon .msicon — nazwy plików

Plik .msicon to archiwum ZIP z plikiem `manifest.ini` i folderem `icons/`.
Każdy plik w `icons/` nazywa się tak jak ikona poniżej (rozszerzenie: .svg, .png lub .ico).
Opcjonalnie można dodać osobne rozmiary: `nazwa@16.png`, `nazwa@32.png`, `nazwa@48.png`, `nazwa@256.png`.
Ikony pominięte w zestawie są brane z wbudowanego zestawu Horyzont.

## manifest.ini

```ini
[Icon Pack]
Name=Mój zestaw
Author=Jan Kowalski
Version=1.0
Description=Krótki opis
```

## Pakowanie

```bash
tools/make-msicon.sh moj-zestaw/        # tworzy Moj-zestaw.msicon
```

Szablon ze wszystkimi ikonami (SVG) zapiszesz w: Panel sterowania → Ekran → Ikony → **Eksportuj szablon...**

## Nazwy ikon

### Pulpit i foldery specjalne

| Plik | Ikona |
|---|---|
| `computer.svg` | Mój komputer |
| `desktop_folder.svg` | Pulpit (folder) |
| `documents.svg` | Moje dokumenty |
| `downloads.svg` | Pobrane |
| `folder.svg` | Folder zamknięty |
| `folder_open.svg` | Folder otwarty / Eksplorator |
| `folder_zip.svg` | Folder skompresowany (ZIP, RAR, 7z) |
| `fonts.svg` | Folder Czcionki |
| `home.svg` | Folder domowy |
| `music.svg` | Moja muzyka |
| `network.svg` | Moje miejsca sieciowe |
| `new_folder.svg` | Nowy folder |
| `pictures.svg` | Moje obrazy |
| `recent.svg` | Moje bieżące dokumenty |
| `recycle_empty.svg` | Kosz (pusty) |
| `recycle_full.svg` | Kosz (pełny) |
| `shortcut_overlay.svg` | Strzałka skrótu (nakładka, przezroczyste tło) |
| `videos.svg` | Moje wideo |

### Napędy

| Plik | Ikona |
|---|---|
| `drive_cd.svg` | Napęd CD/DVD |
| `drive_floppy.svg` | Stacja dyskietek |
| `drive_hdd.svg` | Dysk twardy |
| `drive_network.svg` | Dysk sieciowy |
| `drive_system.svg` | Dysk systemowy |
| `drive_usb.svg` | Dysk wymienny (USB) |

### Typy plików

| Plik | Ikona |
|---|---|
| `file.svg` | Plik nieznanego typu |
| `file_archive.svg` | Archiwum |
| `file_audio.svg` | Plik dźwiękowy |
| `file_code.svg` | Kod źródłowy / skrypt |
| `file_doc.svg` | Dokument edytora tekstu |
| `file_exe.svg` | Program (plik wykonywalny) |
| `file_font.svg` | Plik czcionki |
| `file_html.svg` | Strona HTML |
| `file_image.svg` | Obraz |
| `file_pdf.svg` | Dokument PDF |
| `file_sheet.svg` | Arkusz kalkulacyjny |
| `file_text.svg` | Dokument tekstowy |
| `file_video.svg` | Plik wideo |

### Programy i aplety

| Plik | Ikona |
|---|---|
| `accessibility.svg` | Opcje ułatwień dostępu |
| `accessories.svg` | Akcesoria |
| `addremove.svg` | Dodaj lub usuń programy |
| `admin.svg` | Narzędzia administracyjne |
| `app.svg` | Program ogólny |
| `auto_updates.svg` | Aktualizacje automatyczne |
| `bluetooth.svg` | Urządzenia Bluetooth |
| `browser.svg` | Przeglądarka internetowa |
| `calculator.svg` | Kalkulator |
| `cards.svg` | Pasjans |
| `charmap.svg` | Tablica znaków |
| `cmd.svg` | Wiersz polecenia |
| `control_panel.svg` | Panel sterowania |
| `cursor.svg` | Wskaźniki myszy |
| `datetime.svg` | Data i godzina |
| `disk_cleanup.svg` | Oczyszczanie dysku |
| `display.svg` | Ekran |
| `email.svg` | Poczta e-mail |
| `flatpak.svg` | Aplikacje Flatpak |
| `folder_options.svg` | Opcje folderów |
| `games.svg` | Gry |
| `icon_pack.svg` | Zestaw ikon |
| `image_viewer.svg` | Przeglądarka obrazów |
| `key.svg` | Uwierzytelnianie (hasło) |
| `keyboard.svg` | Klawiatura |
| `media_player.svg` | Odtwarzacz multimediów |
| `mines.svg` | Saper |
| `mouse.svg` | Mysz |
| `network_conn.svg` | Połączenia sieciowe |
| `network_wireless.svg` | Połączenie sieci bezprzewodowej |
| `notepad.svg` | Notatnik |
| `package.svg` | Pakiet oprogramowania |
| `paint.svg` | Paint |
| `power.svg` | Opcje zasilania |
| `printer.svg` | Drukarki i faksy |
| `programs.svg` | Folder grupy programów |
| `recorder.svg` | Rejestrator dźwięku |
| `regional.svg` | Opcje regionalne i językowe |
| `scheduled.svg` | Zaplanowane zadania |
| `security.svg` | Centrum zabezpieczeń |
| `sound.svg` | Dźwięki i urządzenia audio |
| `sound_scheme.svg` | Schemat dźwiękowy |
| `sysinfo.svg` | Informacje o systemie |
| `system.svg` | System |
| `taskbar_props.svg` | Pasek zadań i menu Start |
| `taskmgr.svg` | Menedżer zadań |
| `terminal.svg` | Terminal |
| `updates.svg` | Horyzont Updates |
| `user.svg` | Konto użytkownika |
| `user_add.svg` | Nowe konto |
| `users.svg` | Konta użytkowników |
| `wifi.svg` | Sieci bezprzewodowe (aplet) |
| `wizard.svg` | Kreator |
| `wordpad.svg` | WordPad / dokument RTF |

### Polecenia i paski narzędzi

| Plik | Ikona |
|---|---|
| `back.svg` | Wstecz |
| `chevron_down.svg` | Strzałka rozwijania |
| `copy.svg` | Kopiuj |
| `cut.svg` | Wytnij |
| `delete.svg` | Usuń |
| `extract.svg` | Wyodrębnij pliki |
| `folders_tree.svg` | Foldery (drzewo) |
| `forward.svg` | Dalej |
| `go.svg` | Przejdź |
| `paste.svg` | Wklej |
| `properties.svg` | Właściwości |
| `refresh.svg` | Odśwież |
| `search.svg` | Wyszukaj |
| `show_desktop.svg` | Pokaż pulpit |
| `signal_bars.svg` | Siła sygnału |
| `star.svg` | Gwiazdka (ulubione, połączono) |
| `undo.svg` | Cofnij |
| `up.svg` | W górę |
| `views.svg` | Widoki |

### Menu Start i sesja

| Plik | Ikona |
|---|---|
| `help.svg` | Pomoc i obsługa techniczna |
| `lock.svg` | Zablokuj komputer |
| `logo.svg` | Logo Horyzont (przycisk Start, okno Informacje) |
| `logoff.svg` | Wyloguj |
| `restart.svg` | Uruchom ponownie |
| `run.svg` | Uruchom... |
| `shutdown.svg` | Wyłącz komputer |
| `standby.svg` | Stan wstrzymania |
| `switch_user.svg` | Przełącz użytkownika |

### Komunikaty

| Plik | Ikona |
|---|---|
| `error.svg` | Błąd |
| `info.svg` | Informacja |
| `question.svg` | Pytanie |
| `warning.svg` | Ostrzeżenie |

### Obszar powiadomień (16x16)

| Plik | Ikona |
|---|---|
| `tray_battery.svg` | Bateria |
| `tray_bluetooth.svg` | Bluetooth włączony |
| `tray_bluetooth_off.svg` | Bluetooth wyłączony |
| `tray_network.svg` | Sieć przewodowa — połączono |
| `tray_network_off.svg` | Sieć przewodowa — kabel odłączony |
| `tray_updates.svg` | Dostępne aktualizacje |
| `tray_wifi_0.svg` | Wi-Fi — brak sygnału |
| `tray_wifi_1.svg` | Wi-Fi — sygnał słaby |
| `tray_wifi_2.svg` | Wi-Fi — sygnał średni |
| `tray_wifi_3.svg` | Wi-Fi — sygnał dobry |
| `tray_wifi_4.svg` | Wi-Fi — sygnał doskonały |
| `tray_wifi_off.svg` | Wi-Fi — niepołączono / wyłączone |
| `volume.svg` | Głośność |
| `volume_muted.svg` | Głośność wyciszona |

### Obrazy kont użytkowników

| Plik | Ikona |
|---|---|
| `avatar_boat.svg` | Obraz konta: łódka |
| `avatar_cat.svg` | Obraz konta: kot |
| `avatar_flower.svg` | Obraz konta: kwiat |
| `avatar_guitar.svg` | Obraz konta: gitara |
| `avatar_kite.svg` | Obraz konta: latawiec |
| `avatar_planet.svg` | Obraz konta: planeta |
