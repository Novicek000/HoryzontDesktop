# HoryzontDesktop — aktualizacje środowiska

Gdy użytkownik zleca aktualizację środowiska, wynikiem ma być wersja dostępna przez
Horyzont Updates. Sam otwarty PR nie kończy takiego zadania, chyba że użytkownik
wyraźnie prosi tylko o przygotowanie PR-a lub zmian do przeglądu.

Przy publikacji aktualizacji:

1. Podnieś `VERSION` w `horyzont/config.py`, zsynchronizuj `Version` i zależności
   w `packaging/horyzont.spec` oraz opisz zmiany w README.
2. Przeprowadź sprawdzenia odpowiednie do zmian. W ramach zleconej publikacji
   doprowadź poprawki do głównej gałęzi repozytorium.
3. Sprawdź `_latest` w `horyzont/updates/core.py`: aktualizator preferuje wydanie,
   potem tag, a dopiero przy ich braku czyta VERSION z głównej gałęzi. Istniejące
   starsze wydanie lub tag mogą wymagać opublikowania nowego wydania/tagu.
4. Zweryfikuj wykrywanie z numerem poprzednio zainstalowanej wersji oraz pobranie
   archiwum przez `check_horyzont` i `download_horyzont`. Archiwum musi zawierać
   właściwą wersję, poprawki i `update.sh`.
5. Informuj o dostępności aktualizacji dopiero po weryfikacji. Gdy publikacja lub
   weryfikacja jest zablokowana, wyraźnie wskaż, czego nie udało się potwierdzić.
