"""Pomoc i obsługa techniczna."""
from PySide6.QtCore import QRect, Qt, QUrl
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QSplitter,
                               QTextBrowser, QVBoxLayout, QWidget)

from ...common import launcher
from ...common.taskpane import TaskPane
from ...common.window import HWindow
from ...i18n import lang_code, plain
from ...theme import iconcache
from ...theme.base import hgrad, vgrad
from ...theme.manager import current

TOPICS_PL = [
    ("start", "Witamy w Horyzoncie", """
<h2>Witamy w środowisku Horyzont</h2>
<p>Horyzont to klasyczne środowisko pulpitu dla Fedory: pasek zadań na dole ekranu, menu Start,
pulpit z ikonami, Eksplorator z panelem zadań, Panel sterowania i Menedżer zadań.</p>
<ul>
<li>Kliknij przycisk <b>Start</b>, aby otworzyć programy, dokumenty i ustawienia.</li>
<li>Dwukrotnie kliknij <b>Mój komputer</b>, aby zobaczyć dyski i foldery.</li>
<li>Kliknij pulpit prawym przyciskiem myszy i wybierz <b>Właściwości</b>, aby zmienić tapetę i kompozycję.</li>
</ul>"""),
    ("desktop", "Pulpit i menu Start", """
<h2>Pulpit i menu Start</h2>
<p>Lewa kolumna menu Start zawiera przypięte programy (przeglądarka i poczta) oraz najczęściej używane.
Prawa kolumna prowadzi do folderów i ustawień. <b>Wszystkie programy</b> pokazuje aplikacje zainstalowane w systemie,
pogrupowane w foldery.</p>
<p>Programy można przypinać prawym przyciskiem myszy. Ikony na pulpicie przeciąga się myszą; menu kontekstowe
pulpitu pozwala je rozmieścić według nazwy, rozmiaru, typu lub daty.</p>"""),
    ("files", "Praca z plikami i folderami", """
<h2>Praca z plikami i folderami</h2>
<p>Panel zadań po lewej stronie okna Eksploratora pokazuje czynności dostępne dla zaznaczonych elementów:
zmianę nazwy, kopiowanie, przenoszenie i usuwanie. Usunięte pliki trafiają do <b>Kosza</b>, skąd można je przywrócić.</p>
<p>Przycisk <b>Widoki</b> przełącza między miniaturami, kafelkami, ikonami, listą i szczegółami.
Przycisk <b>Foldery</b> pokazuje drzewo folderów.</p>"""),
    ("looks", "Wygląd i kompozycje", """
<h2>Wygląd i kompozycje</h2>
<p>Otwórz <b>Panel sterowania → Wygląd i kompozycje → Ekran</b>. Na karcie <b>Wygląd</b> wybierasz styl okien
(Horyzont lub Klasyczny), schemat kolorów i rozmiar czcionki. Na karcie <b>Pulpit</b> — tapetę.</p>
<p><b>Style wizualne .msstyles</b>: jeśli masz własne pliki stylów (np. z posiadanej kopii innego systemu),
wybierz <b>Przeglądaj...</b> na karcie Kompozycje. Horyzont odczyta grafiki stylu i użyje ich do rysowania
okien, przycisków, paska zadań i menu Start.</p>"""),
    ("keys", "Skróty klawiaturowe", """
<h2>Skróty klawiaturowe</h2>
<table cellpadding="3">
<tr><td><b>Super</b></td><td>menu Start</td></tr>
<tr><td><b>Super+E</b></td><td>Mój komputer</td></tr>
<tr><td><b>Super+R</b></td><td>Uruchamianie</td></tr>
<tr><td><b>Super+D</b></td><td>pokaż pulpit</td></tr>
<tr><td><b>Super+L</b></td><td>zablokuj komputer</td></tr>
<tr><td><b>Ctrl+Shift+Esc</b>, <b>Ctrl+Alt+Del</b></td><td>Menedżer zadań</td></tr>
<tr><td><b>Alt+Tab</b></td><td>przełączanie okien</td></tr>
<tr><td><b>Alt+F4</b></td><td>zamknij okno</td></tr>
<tr><td><b>F2</b></td><td>zmień nazwę</td></tr>
<tr><td><b>Shift+Delete</b></td><td>usuń bez przenoszenia do Kosza</td></tr>
</table>"""),
    ("software", "Instalowanie programów", """
<h2>Instalowanie programów</h2>
<p>Programy instaluje się w <b>Panelu sterowania → Dodaj lub usuń programy</b> albo z wiersza polecenia:</p>
<pre>sudo dnf install nazwa-pakietu
flatpak install flathub nazwa.aplikacji</pre>
<p>Strona <b>Aplikacje Flatpak</b> w oknie Dodaj lub usuń programy wyszukuje i instaluje aplikacje z Flathuba
(także „tylko dla mnie”, bez hasła administratora).</p>"""),
    ("updates", "Horyzont Updates", """
<h2>Horyzont Updates</h2>
<p><b>Start → Wszystkie programy → Horyzont Updates</b> sprawdza aktualizacje systemu Fedora (dnf), aplikacji Flatpak
i samego Horyzontu (wydania na GitHubie). Wybierz <b>Ekspresowa</b>, aby zainstalować wszystko, albo
<b>Niestandardowa</b>, aby wybrać aktualizacje.</p>
<p>W <b>Zmień ustawienia</b> ustawisz aktualizacje automatyczne (instalowanie, tylko pobieranie, tylko powiadamianie)
i częstotliwość sprawdzania. Opcja <b>Horyzont zarządza aktualizacjami</b> wyłącza automatyczne aktualizacje Fedory,
żeby nic nie było instalowane dwa razy. Gdy są aktualizacje, w obszarze powiadomień pojawia się żółta tarcza.</p>"""),
    ("calc", "Kalkulator", """
<h2>Kalkulator</h2>
<p><b>Start → Wszystkie programy → Akcesoria → Kalkulator</b>. W menu <b>Widok</b> wybierzesz widok
<b>Standardowy</b> (działania liczone po kolei) albo <b>Naukowy</b> (kolejność działań, nawiasy, funkcje
trygonometryczne, logarytmy, silnia, systemy szesnastkowy/ósemkowy/dwójkowy, operacje bitowe i statystyka).</p>
<ul><li>Cyfry i działania można wpisywać z klawiatury: <b>Enter</b> — wynik, <b>Esc</b> — C, <b>Del</b> — CE,
<b>F9</b> — zmiana znaku, <b>@</b> — pierwiastek, <b>r</b> — odwrotność.</li>
<li>Pamięć: <b>MS</b> zapisz, <b>MR</b> przywołaj, <b>M+</b> dodaj, <b>MC</b> wyczyść (Ctrl+M, Ctrl+R, Ctrl+P, Ctrl+L).</li>
<li><b>Edycja → Kopiuj/Wklej</b> — wynik do schowka lub wklejenie liczby albo całego wyrażenia.</li></ul>"""),
    ("charmap", "Mapa znaków", """
<h2>Mapa znaków</h2>
<p>Pokazuje wszystkie znaki wybranej czcionki. Kliknij i przytrzymaj znak, aby go powiększyć; dwukrotne kliknięcie
(albo <b>Wybierz</b>) dodaje go do pola <b>Znaki do skopiowania</b>, a <b>Kopiuj</b> umieszcza je w schowku.</p>
<p><b>Widok zaawansowany</b> pozwala grupować znaki według podzakresów Unicode, wyszukiwać je po nazwie
(np. <i>ogonek</i>, <i>arrow</i>, <i>euro</i>) i przejść do kodu, np. <code>U+0105</code>.</p>"""),
    ("paint", "Paint", """
<h2>Paint</h2>
<p>Edytor obrazów z narzędziami: zaznaczanie (prostokąt i dowolny kształt), gumka, wypełnianie kolorem, pipeta,
lupa, ołówek, pędzel, aerograf, tekst, linia, krzywa, prostokąt, wielokąt, elipsa i zaokrąglony prostokąt.</p>
<ul><li>Lewy przycisk myszy rysuje kolorem pierwszoplanowym, prawy — kolorem tła. Kolory wybierasz w polu kolorów
na dole (dwukrotne kliknięcie zmienia kolor w palecie).</li>
<li>Pod narzędziami jest pole opcji: grubość linii, kształt pędzla, styl wypełnienia, rozmiar gumki.</li>
<li>Klawisz <b>Shift</b> rysuje kwadraty, koła i linie pod kątem 45°. Wielokąt zamykasz dwukrotnym kliknięciem.</li>
<li>Zaznaczenie przeciągnięte z <b>Ctrl</b> zostawia kopię, z <b>Shift</b> — „stempluje”.</li>
<li><b>Obraz</b> — przerzucanie, obracanie, rozciąganie, pochylanie, odwracanie kolorów i rozmiar (Atrybuty).
Rozmiar obrazu zmienisz też uchwytami przy jego krawędziach.</li>
<li>Zapis do BMP, PNG, JPEG, GIF, TIFF, WebP i ICO. <b>Plik → Ustaw jako tło pulpitu</b>.</li></ul>"""),
    ("wordpad", "WordPad", """
<h2>WordPad</h2>
<p>Edytor dokumentów z formatowaniem: czcionki, rozmiary, pogrubienie, kursywa, podkreślenie, kolory, wyrównanie,
punktory, wcięcia (także przeciąganiem znaczników na linijce), tabulatory, obrazy.</p>
<p>Otwiera i zapisuje pliki <b>RTF</b>, <b>DOCX</b> (Word), <b>ODT</b> (LibreOffice), <b>TXT</b> i <b>HTML</b>.
Stare pliki <b>DOC</b> otwiera, jeśli zainstalowany jest LibreOffice (konwersja w tle).</p>
<p>Skróty: Ctrl+B/I/U — pogrubienie/kursywa/podkreślenie, Ctrl+L/E/R/J — wyrównanie, Ctrl+F — znajdź, Ctrl+H — zamień.</p>"""),
    ("viewer", "Przeglądarka obrazów i faksów", """
<h2>Przeglądarka obrazów i faksów</h2>
<p>Otwiera się po dwukrotnym kliknięciu zdjęcia. Strzałki (albo kółko myszy) przechodzą do poprzedniego/następnego
obrazu w folderze, <b>+</b>/<b>−</b> lub Ctrl+kółko powiększają, <b>Ctrl+K</b>/<b>Ctrl+L</b> obracają (przy zmianie
obrazu program zapyta o zapisanie obrotu), <b>F11</b> uruchamia pokaz slajdów, <b>Del</b> przenosi plik do Kosza,
<b>Ctrl+E</b> otwiera obraz w programie Paint.</p>"""),
    ("media", "Odtwarzacz multimediów i Rejestrator dźwięku", """
<h2>Odtwarzacz multimediów</h2>
<p>Odtwarza muzykę i filmy, ma listę odtwarzania (dodawanie plików, folderów, adresów URL, zapis do M3U),
odtwarzanie losowe i w pętli, pełny ekran (Alt+Enter albo dwukrotne kliknięcie obrazu) i wizualizację dźwięku.</p>
<p>Formaty zależą od zainstalowanych kodeków. Fedora ze względów licencyjnych dostarcza okrojony zestaw — pełną obsługę
MP3, AAC i H.264 zapewnia pakiet <code>ffmpeg</code> z repozytorium RPM Fusion.</p>
<h2>Rejestrator dźwięku</h2>
<p>Nagrywa z mikrofonu (przycisk z czerwonym kółkiem), odtwarza i zapisuje pliki WAV (a z zainstalowanym ffmpeg także
OGG, MP3 i FLAC). Menu <b>Efekty</b>: głośniej/ciszej, szybciej/wolniej, echo, odwrócenie. Menu <b>Edycja</b>:
wstawianie i miksowanie z innym plikiem, usuwanie przed/po bieżącym położeniu.</p>"""),
    ("games", "Gry: Saper i Pasjans", """
<h2>Saper</h2>
<p>Odkryj wszystkie pola bez min. Liczba na polu mówi, ile min jest wokół. Prawy przycisk stawia flagę (i znak
zapytania, jeśli włączony), kliknięcie obu przycisków (albo środkowego) na liczbie odkrywa sąsiednie pola, gdy flag jest
tyle, ile wskazuje liczba. Pierwsze kliknięcie nigdy nie trafia na minę. <b>F2</b> — nowa gra.</p>
<h2>Pasjans</h2>
<p>Ułóż wszystkie karty na czterech stosach w prawym górnym rogu, kolorami od asa do króla. W kolumnach karty
układa się malejąco, na przemian czerwone i czarne; na puste pole można położyć tylko króla.</p>
<ul><li>Kliknięcie talii odkrywa kartę (lub trzy — <b>Gra → Opcje</b>).</li>
<li>Dwukrotne kliknięcie karty przenosi ją na stos końcowy, prawy przycisk — przenosi wszystkie możliwe.</li>
<li>Punktacja standardowa, Vegas lub bez punktów; <b>Gra → Talia</b> zmienia wzór koszulek.</li></ul>"""),
    ("tray", "Obszar powiadomień i dymki", """
<h2>Obszar powiadomień</h2>
<p>Prawa część paska zadań, obok zegara. Są tu ikony systemowe (sieć, Bluetooth, głośność, bateria, aktualizacje)
oraz ikony programów, które działają w tle lub „chowają się do zasobnika” — np. Discord, Steam, Telegram, Nextcloud.</p>
<ul><li><b>Kliknij</b> ikonę programu, aby otworzyć jego okno.</li>
<li><b>Kliknij prawym przyciskiem</b>, aby wyświetlić menu programu (np. <i>Zakończ</i>).</li>
<li><b>Środkowy przycisk</b> i <b>kółko myszy</b> działają, jeśli program je obsługuje.</li></ul>
<h2>Dymki powiadomień</h2>
<p>Powiadomienia programów i systemu pojawiają się w żółtych dymkach nad obszarem powiadomień. Kliknij dymek, aby
przejść do programu, albo <b>✕</b>, aby go zamknąć. Dymki znikają same po kilku sekundach (pilne — dopiero po kliknięciu).</p>
<p>Ikony programów i dymki włączysz lub wyłączysz w <b>Panelu sterowania → Pasek zadań i menu Start</b>.</p>
<p>Programy z folderu <b>Autostart</b> (<code>~/.config/autostart</code>) uruchamiają się po zalogowaniu.</p>"""),
    ("cmd", "Wiersz polecenia", """
<h2>Wiersz polecenia</h2>
<p><b>Start → Wszystkie programy → Akcesoria → Wiersz polecenia</b> (albo <b>Uruchom → cmd</b>) otwiera konsolę z powłoką bash.</p>
<ul><li>Zaznacz tekst myszą — prawy przycisk kopiuje; prawy przycisk bez zaznaczenia wkleja (tryb szybkiej edycji).</li>
<li><b>Ctrl+Shift+C</b> / <b>Ctrl+Shift+V</b> — kopiuj i wklej, <b>Shift+PageUp</b> — przewijanie historii.</li>
<li>Kliknij ikonę w lewym górnym rogu okna, aby zmienić czcionkę, kolory i rozmiar (<b>Właściwości</b>).</li>
<li>Działają polecenia <code>cls</code>, <code>dir</code>, <code>copy</code>, <code>move</code>, <code>del</code>, <code>md</code>, <code>rd</code>.</li></ul>"""),
    ("archives", "Foldery skompresowane (ZIP, RAR, 7z)", """
<h2>Foldery skompresowane</h2>
<p>Archiwa ZIP, RAR, 7z, TAR i inne otwierają się w Eksploratorze jak foldery. Pliki można z nich otwierać,
a <b>Wyodrębnij wszystkie pliki</b> uruchamia kreatora rozpakowywania. Jeśli archiwum jest chronione hasłem,
pojawi się okno hasła.</p>
<p>Aby spakować pliki, zaznacz je i wybierz <b>Wyślij do → Folder skompresowany (zip)</b> albo <b>Dodaj do archiwum...</b>
(z możliwością ustawienia hasła). Do archiwów RAR potrzebny jest pakiet <code>unar</code>, do 7z — <code>7zip</code>.</p>"""),
    ("icons", "Zestawy ikon .msicon", """
<h2>Zestawy ikon .msicon</h2>
<p><b>Panel sterowania → Ekran → Ikony</b>: wybór zestawu ikon, instalacja plików .msicon i eksport szablonu.
Plik .msicon to archiwum ZIP z plikiem <code>manifest.ini</code> i folderem <code>icons/</code>; nazwy plików
odpowiadają nazwom ikon (lista: przycisk <b>Jak przygotować własny zestaw ikon?</b>). Spakujesz go poleceniem
<code>horyzont-msicon folder</code>.</p>"""),
    ("trouble", "Rozwiązywanie problemów", """
<h2>Rozwiązywanie problemów</h2>
<ul>
<li>Jeśli pasek zadań zniknie, naciśnij <b>Ctrl+Alt+Del</b>, wybierz <b>Plik → Nowe zadanie</b> i wpisz
<code>horyzont-shell --replace</code>.</li>
<li>Dziennik powłoki znajduje się w <code>~/.cache/horyzont/shell.log</code>.</li>
<li>Ustawienia są w pliku <code>~/.config/horyzont/settings.json</code> — usunięcie go przywraca ustawienia domyślne.</li>
</ul>"""),
]

TOPICS_EN = [
    ("start", "Welcome to Horyzont", """<h2>Welcome to Horyzont</h2><p>Horyzont is a classic desktop for Fedora:
a taskbar, a Start menu, desktop icons, Explorer with a task pane, Control Panel and Task Manager.</p>"""),
    ("looks", "Appearance and themes", """<h2>Appearance and themes</h2><p>Open <b>Control Panel → Display</b>.
Use the <b>Appearance</b> tab for window style and colors and <b>Themes → Browse...</b> to load your own .msstyles files.</p>"""),
    ("keys", "Keyboard shortcuts", """<h2>Keyboard shortcuts</h2><p>Super — Start menu, Super+E — My Computer,
Super+R — Run, Super+D — show desktop, Ctrl+Shift+Esc — Task Manager, Alt+Tab — switch windows.</p>"""),
]


class Header(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(64)

    def paintEvent(self, e):
        p = QPainter(self)
        t = current()
        sc = getattr(t, "sc", {"accent_darker": "#0b4a52", "accent": "#1f8591", "accent_light": "#5cc6d0"})
        r = self.rect()
        p.fillRect(r, hgrad(r, [(0, sc["accent_darker"]), (0.6, sc["accent"]), (1, sc["accent_light"])]))
        p.drawPixmap(14, 12, iconcache.pixmap("help", 40))
        f = t.font("title_big")
        p.setFont(f)
        p.setPen(QColor("#ffffff"))
        p.drawText(QRect(66, 0, r.width() - 80, r.height()), Qt.AlignVCenter | Qt.AlignLeft, plain("help_center"))


class HelpWindow(HWindow):
    def __init__(self):
        super().__init__(plain("help_center"), "help")
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(Header())
        split = QSplitter(Qt.Horizontal)
        self.pane = TaskPane()
        topics = TOPICS_PL if lang_code() == "pl" else TOPICS_EN
        sec = self.pane.add_section(plain("help_topics").replace("&", ""), special=True)
        for key, title, html in topics:
            sec.add_link("help", title, lambda h=html: self.show_html(h))
        more = self.pane.add_section(plain("help_more"))
        more.add_link("browser", "docs.fedoraproject.org", lambda: launcher.xdg_open("https://docs.fedoraproject.org/pl/"))
        more.add_link("browser", "labwc.github.io", lambda: launcher.xdg_open("https://labwc.github.io/"))
        split.addWidget(self.pane)
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.document().setDefaultStyleSheet(
            "h2 { color: #1f6f78; } body { font-size: 11px; } pre { background: #f0f3f2; }")
        split.addWidget(self.browser)
        split.setSizes([220, 560])
        lay.addWidget(split, 1)
        self.show_html(topics[0][2])
        self.resize(820, 560)

    def show_topic(self, key):
        topics = TOPICS_PL if lang_code() == "pl" else TOPICS_EN
        for k, _title, html in topics:
            if k == key:
                self.show_html(html)
                return True
        return False

    def show_html(self, html):
        self.browser.setHtml(f"<body style='margin:14px'>{html}</body>")
