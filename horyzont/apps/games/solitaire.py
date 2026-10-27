"""Pasjans (Klondike) — dobieranie po 1 lub 3 kartach, punktacja standardowa i Vegas, cofanie, animacja wygranej."""
import copy
import random
import sys

from PySide6.QtCore import QPointF, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QDialog, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                               QMenuBar, QPushButton, QRadioButton, QStatusBar, QVBoxLayout, QWidget)

from ... import config
from ...common import dialogs
from ...common.appkit import T, act, help_menu, run_app
from ...common.window import HDialog, HWindow
from . import cards

FELT = QColor("#007f0e")


def new_deck():
    d = [(r, s) for s in cards.SUITS for r in range(13)]
    random.shuffle(d)
    return d


def red(card):
    return cards.is_red(card[1])


class Game:
    def __init__(self, draw=1, scoring="standard", timed=True, carry=0):
        self.draw = draw
        self.scoring = scoring
        self.timed = timed
        deck = new_deck()
        self.tableau = []
        for i in range(7):
            pile = []
            for j in range(i + 1):
                pile.append([deck.pop(), j == i])
            self.tableau.append(pile)
        self.stock = deck
        self.waste = []
        self.found = [[] for _ in range(4)]
        self.passes = 0
        self.score = (carry - 52) if scoring == "vegas" else 0
        self.time = 0
        self.started = False
        self.won = False

    def snapshot(self):
        return copy.deepcopy({k: getattr(self, k) for k in ("tableau", "stock", "waste", "found", "passes", "score")})

    def restore(self, snap):
        for k, v in snap.items():
            setattr(self, k, v)

    def add_score(self, n):
        if self.scoring == "standard":
            self.score = max(0, self.score + n)

    def max_passes(self):
        if self.scoring != "vegas":
            return None
        return 1 if self.draw == 1 else 3

    def can_recycle(self):
        mp = self.max_passes()
        return mp is None or self.passes < mp - 1

    def deal(self):
        if self.stock:
            n = min(self.draw, len(self.stock))
            for _ in range(n):
                self.waste.append(self.stock.pop())
            return True
        if self.waste and self.can_recycle():
            self.stock = list(reversed(self.waste))
            self.waste = []
            self.passes += 1
            if self.scoring == "standard":
                self.add_score(-100 if self.draw == 1 else -20)
            return True
        return False

    # ---- reguły
    @staticmethod
    def fits_tableau(card, pile):
        if not pile:
            return card[0] == 12
        top, up = pile[-1]
        return up and top[0] == card[0] + 1 and red(top) != red(card)

    def foundation_for(self, card):
        for i, f in enumerate(self.found):
            if (not f and card[0] == 0) or (f and f[-1][1] == card[1] and f[-1][0] == card[0] - 1):
                return i
        return None

    def fits_foundation(self, card, i):
        f = self.found[i]
        return (not f and card[0] == 0) or (f and f[-1][1] == card[1] and f[-1][0] == card[0] - 1)

    def check_win(self):
        if all(len(f) == 13 for f in self.found):
            self.won = True
        return self.won


class Table(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setMinimumSize(560, 400)
        self.drag = None      # dict(src, cards, offset, pos)
        self.anim = None
        self.setMouseTracking(False)

    # ------------------------------------------------ geometria
    def metrics(self):
        w = self.width()
        scale = max(1.0, min(2.2, (w - 8 * 12) / (7 * cards.CARD_W)))
        scale = min(scale, max(1.0, (self.height() - 30) / (cards.CARD_H * 3.6)))
        cw, ch = round(cards.CARD_W * scale), round(cards.CARD_H * scale)
        gap = max(10, (w - 7 * cw) // 8)
        return scale, cw, ch, gap

    def pile_rect(self, kind, i=0):
        scale, cw, ch, gap = self.metrics()
        top = round(10 * scale)
        if kind == "stock":
            return QRect(gap, top, cw, ch)
        if kind == "waste":
            return QRect(gap * 2 + cw, top, cw, ch)
        if kind == "found":
            return QRect(gap + (3 + i) * (cw + gap), top, cw, ch)
        return QRect(gap + i * (cw + gap), top + ch + round(18 * scale), cw, ch)

    def tableau_offsets(self, pile):
        scale, cw, ch, gap = self.metrics()
        down, up = round(3 * scale), round(15 * scale)
        y0 = self.pile_rect("tab").top()
        avail = self.height() - y0 - ch - 6
        need = sum(down if not u else up for _, u in pile[:-1])
        if need > avail and need > 0:
            f = max(0.35, avail / need)
            down, up = max(2, round(down * f)), max(5, round(up * f))
        ys, y = [], 0
        for _, u in pile:
            ys.append(y)
            y += up if u else down
        return ys

    def card_rects_tab(self, i):
        base = self.pile_rect("tab", i)
        return [QRect(base.left(), base.top() + y, base.width(), base.height()) for y in self.tableau_offsets(self.win.game.tableau[i])]

    def waste_rects(self):
        g = self.win.game
        base = self.pile_rect("waste")
        scale = self.metrics()[0]
        n = len(g.waste)
        shown = min(3, n) if g.draw == 3 else min(1, n)
        rects = []
        for k in range(shown):
            rects.append(QRect(base.left() + k * round(12 * scale), base.top(), base.width(), base.height()))
        return rects

    # ------------------------------------------------ rysowanie
    def paintEvent(self, e):
        p = QPainter(self)
        if self.anim is not None:
            p.drawPixmap(0, 0, self.anim["canvas"])
            return
        p.fillRect(self.rect(), FELT)
        g = self.win.game
        scale = self.metrics()[0]
        back = cards.card_back(self.win.back, scale)
        dragging = self.drag["cards"] if self.drag else []
        # talia
        r = self.pile_rect("stock")
        if g.stock:
            n = len(g.stock)
            for k in range(min(3, (n + 9) // 10)):
                p.drawPixmap(r.left() + k * 2, r.top() + k, back)
        else:
            p.drawPixmap(r.topLeft(), cards.placeholder(scale, "recycle" if g.can_recycle() and g.waste else "stop"))
        # odkryte
        wr = self.waste_rects()
        visible = g.waste[-len(wr):] if wr else []
        if not visible:
            p.drawPixmap(self.pile_rect("waste").topLeft(), cards.placeholder(scale))
        for rr, card in zip(wr, visible):
            if self.drag and self.drag["src"] == ("waste",) and card is visible[-1]:
                continue
            p.drawPixmap(rr.topLeft(), cards.card_face(cards.RANKS[card[0]], card[1], scale))
        # stosy końcowe
        for i, f in enumerate(g.found):
            fr = self.pile_rect("found", i)
            show = f
            if self.drag and self.drag["src"] == ("found", i):
                show = f[:-1]
            if show:
                c = show[-1]
                p.drawPixmap(fr.topLeft(), cards.card_face(cards.RANKS[c[0]], c[1], scale))
            else:
                p.drawPixmap(fr.topLeft(), cards.placeholder(scale))
        # kolumny
        for i, pile in enumerate(g.tableau):
            rects = self.card_rects_tab(i)
            if not pile:
                p.drawPixmap(self.pile_rect("tab", i).topLeft(), cards.placeholder(scale))
            for k, ((card, up), rr) in enumerate(zip(pile, rects)):
                if self.drag and self.drag["src"] == ("tab", i) and k >= self.drag["index"]:
                    break
                p.drawPixmap(rr.topLeft(), cards.card_face(cards.RANKS[card[0]], card[1], scale) if up else back)
        # przeciągane
        if self.drag:
            pos = self.drag["pos"] - self.drag["offset"]
            up = round(15 * scale)
            for k, card in enumerate(dragging):
                p.drawPixmap(pos.x(), pos.y() + k * up, cards.card_face(cards.RANKS[card[0]], card[1], scale))

    # ------------------------------------------------ trafienia
    def hit(self, pos):
        g = self.win.game
        if self.pile_rect("stock").contains(pos):
            return ("stock",), None
        wr = self.waste_rects()
        if wr and wr[-1].contains(pos):
            return ("waste",), None
        for i in range(4):
            if self.pile_rect("found", i).contains(pos):
                return ("found", i), None
        for i in range(7):
            rects = self.card_rects_tab(i)
            for k in range(len(rects) - 1, -1, -1):
                if rects[k].contains(pos):
                    return ("tab", i), k
            if not g.tableau[i] and self.pile_rect("tab", i).contains(pos):
                return ("tab", i), None
        return None, None

    def mousePressEvent(self, e):
        if self.anim is not None:
            self.win.stop_animation()
            return
        g = self.win.game
        if g.won:
            return
        pos = e.position().toPoint()
        src, k = self.hit(pos)
        if src is None:
            return
        if e.button() == Qt.RightButton:
            self.win.autoplay()
            return
        if e.button() != Qt.LeftButton:
            return
        if src == ("stock",):
            self.win.do(lambda: g.deal())
            return
        if src == ("waste",) and g.waste:
            self._start_drag(src, [g.waste[-1]], self.waste_rects()[-1], pos, None)
        elif src[0] == "found" and g.found[src[1]]:
            self._start_drag(src, [g.found[src[1]][-1]], self.pile_rect("found", src[1]), pos, None)
        elif src[0] == "tab" and k is not None:
            pile = g.tableau[src[1]]
            card, up = pile[k]
            if not up:
                if k == len(pile) - 1:
                    def flip():
                        pile[k][1] = True
                        g.add_score(5)
                        return True
                    self.win.do(flip)
                return
            self._start_drag(src, [c for c, _ in pile[k:]], self.card_rects_tab(src[1])[k], pos, k)

    def _start_drag(self, src, cards_, rect, pos, index):
        self.drag = {"src": src, "cards": cards_, "offset": pos - rect.topLeft(), "pos": pos, "index": index,
                     "moved": False, "start": pos}

    def mouseMoveEvent(self, e):
        if self.drag:
            self.drag["pos"] = e.position().toPoint()
            if (self.drag["pos"] - self.drag["start"]).manhattanLength() > 3:
                self.drag["moved"] = True
            self.update()

    def mouseReleaseEvent(self, e):
        if not self.drag:
            return
        d = self.drag
        self.drag = None
        if not d["moved"]:
            self.update()
            return
        scale, cw, ch, gap = self.metrics()
        r = QRect(d["pos"] - d["offset"], self.pile_rect("stock").size())
        best, area = None, 0
        targets = [("found", i) for i in range(4)] + [("tab", i) for i in range(7)]
        for t in targets:
            if t == d["src"]:
                continue
            if t[0] == "found":
                tr = self.pile_rect("found", t[1])
            else:
                rects = self.card_rects_tab(t[1])
                tr = rects[-1] if rects else self.pile_rect("tab", t[1])
            inter = r.intersected(tr)
            a = inter.width() * inter.height()
            if a > area:
                best, area = t, a
        if best is not None:
            self.win.move_cards(d["src"], d["index"], best)
        self.update()

    def mouseDoubleClickEvent(self, e):
        g = self.win.game
        src, k = self.hit(e.position().toPoint())
        if src is None or src == ("stock",):
            if src == ("stock",):
                self.mousePressEvent(e)
            return
        if src == ("waste",) and g.waste:
            self.win.to_foundation(src, None)
        elif src[0] == "tab" and g.tableau[src[1]] and g.tableau[src[1]][-1][1]:
            self.win.to_foundation(src, len(g.tableau[src[1]]) - 1)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.anim is not None:
            self.win.stop_animation()


class DeckDialog(HDialog):
    def __init__(self, win, current):
        super().__init__(T("Wybierz tył talii", "Select Card Back"), "cards", win)
        self.choice = current
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(10, 10, 10, 10)
        grid = QGridLayout()
        self.buttons = QButtonGroup(self)
        for i, (key, pl, en) in enumerate(cards.BACKS):
            b = QPushButton()
            b.setCheckable(True)
            b.setIcon(cards.card_back(key, 1.0))
            b.setIconSize(cards.card_back(key, 1.0).size())
            b.setFixedSize(cards.CARD_W + 12, cards.CARD_H + 12)
            b.setToolTip(T(pl, en))
            b.setChecked(key == current)
            b.clicked.connect(lambda _=False, k=key: setattr(self, "choice", k))
            b.mouseDoubleClickEvent = lambda e, k=key: (setattr(self, "choice", k), self.accept())
            self.buttons.addButton(b)
            grid.addWidget(b, i // 4, i % 4)
        lay.addLayout(grid)
        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton(T("OK", "OK"))
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        ca = QPushButton(T("Anuluj", "Cancel"))
        ca.clicked.connect(self.reject)
        row.addWidget(ok)
        row.addWidget(ca)
        lay.addLayout(row)


class OptionsDialog(HDialog):
    def __init__(self, win):
        super().__init__(T("Opcje", "Options"), "cards", win)
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(10, 10, 10, 10)
        top = QHBoxLayout()
        dg = QGroupBox(T("Dobieranie", "Draw"))
        dl = QVBoxLayout(dg)
        self.d1 = QRadioButton(T("Dobieraj &jedną", "Draw &one"))
        self.d3 = QRadioButton(T("Dobieraj &trzy", "Draw t&hree"))
        (self.d1 if win.draw == 1 else self.d3).setChecked(True)
        dl.addWidget(self.d1)
        dl.addWidget(self.d3)
        top.addWidget(dg)
        sg = QGroupBox(T("Punktacja", "Scoring"))
        sl = QVBoxLayout(sg)
        self.s_std = QRadioButton(T("&Standardowa", "&Standard"))
        self.s_vegas = QRadioButton("&Vegas")
        self.s_none = QRadioButton(T("&Brak", "&None"))
        {"standard": self.s_std, "vegas": self.s_vegas}.get(win.scoring, self.s_none).setChecked(True)
        for w in (self.s_std, self.s_vegas, self.s_none):
            sl.addWidget(w)
        top.addWidget(sg)
        lay.addLayout(top)
        self.timed = QCheckBox(T("Gra na &czas", "&Timed game"))
        self.timed.setChecked(win.timed)
        self.status = QCheckBox(T("Pasek st&anu", "Status &bar"))
        self.status.setChecked(win.statusbar.isVisible())
        self.cumulative = QCheckBox(T("&Łączny wynik (Vegas)", "&Cumulative score (Vegas)"))
        self.cumulative.setChecked(win.cumulative)
        for w in (self.timed, self.status, self.cumulative):
            lay.addWidget(w)
        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton(T("OK", "OK"))
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        ca = QPushButton(T("Anuluj", "Cancel"))
        ca.clicked.connect(self.reject)
        row.addWidget(ok)
        row.addWidget(ca)
        lay.addLayout(row)


class SolitaireWindow(HWindow):
    def __init__(self):
        super().__init__(T("Pasjans", "Solitaire"), "cards")
        self.draw = int(config.get("sol_draw", 1))
        self.scoring = config.get("sol_scoring", "standard")
        self.timed = bool(config.get("sol_timed", True))
        self.cumulative = bool(config.get("sol_cumulative", False))
        self.back = config.get("sol_back", "lattice")
        self.vegas_bank = int(config.get("sol_vegas_bank", 0)) if self.cumulative else 0
        self.undo_snap = None
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.menubar = QMenuBar()
        lay.addWidget(self.menubar)
        self.table = Table(self)
        lay.addWidget(self.table, 1)
        self.statusbar = QStatusBar()
        self.score_label = QLabel()
        self.time_label = QLabel()
        self.statusbar.addPermanentWidget(self.score_label)
        self.statusbar.addPermanentWidget(self.time_label)
        lay.addWidget(self.statusbar)
        self.statusbar.setVisible(config.get("sol_status", True))
        self._build_menu()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._anim_step)
        self.resize(720, 560)
        self.new_game()

    def _build_menu(self):
        m = self.menubar.addMenu(T("&Gra", "&Game"))
        act(m, T("&Rozdaj", "&Deal"), self.new_game, "F2")
        m.addSeparator()
        self.a_undo = act(m, T("&Cofnij", "&Undo"), self.undo, "Ctrl+Z")
        act(m, T("&Talia…", "De&ck..."), self.choose_back)
        act(m, T("&Opcje…", "&Options..."), self.options)
        m.addSeparator()
        act(m, T("Za&kończ", "E&xit"), self.close)
        help_menu(self.menubar, self, T("Pasjans", "Solitaire"), "cards", "games")

    # ------------------------------------------------ gra
    def new_game(self):
        self.stop_animation(show_dialog=False)
        if self.scoring == "vegas" and self.cumulative and hasattr(self, "game"):
            self.vegas_bank = self.game.score
            config.set("sol_vegas_bank", self.vegas_bank)
        carry = self.vegas_bank if (self.scoring == "vegas" and self.cumulative) else 0
        self.game = Game(self.draw, self.scoring, self.timed, carry)
        self.undo_snap = None
        self.a_undo.setEnabled(False)
        self._update_status()
        self.table.update()

    def do(self, fn):
        """Wykonuje ruch z możliwością cofnięcia."""
        g = self.game
        snap = g.snapshot()
        if fn():
            self.undo_snap = snap
            self.a_undo.setEnabled(True)
            g.started = True
            self._after_move()
        self.table.update()

    def undo(self):
        if self.undo_snap is None:
            return
        self.game.restore(self.undo_snap)
        self.undo_snap = None
        self.a_undo.setEnabled(False)
        self._update_status()
        self.table.update()

    def move_cards(self, src, index, dst):
        g = self.game

        def mv():
            cards_ = self._take_preview(src, index)
            if not cards_:
                return False
            if dst[0] == "found":
                if len(cards_) != 1 or not g.fits_foundation(cards_[0], dst[1]):
                    return False
            elif not g.fits_tableau(cards_[0], g.tableau[dst[1]]):
                return False
            self._take(src, index)
            if dst[0] == "found":
                g.found[dst[1]].append(cards_[0])
                if g.scoring == "vegas":
                    g.score += 5
                elif src[0] != "found":
                    g.add_score(10)
            else:
                g.tableau[dst[1]].extend([c, True] for c in cards_)
                if src == ("waste",):
                    g.add_score(5)
                elif src[0] == "found":
                    if g.scoring == "vegas":
                        g.score -= 5
                    else:
                        g.add_score(-15)
            return True
        self.do(mv)

    def _take_preview(self, src, index):
        g = self.game
        if src == ("waste",):
            return g.waste[-1:] if g.waste else []
        if src[0] == "found":
            return g.found[src[1]][-1:]
        pile = g.tableau[src[1]]
        return [c for c, _ in pile[index:]] if index is not None else []

    def _take(self, src, index):
        g = self.game
        if src == ("waste",):
            g.waste.pop()
        elif src[0] == "found":
            g.found[src[1]].pop()
        else:
            del g.tableau[src[1]][index:]

    def to_foundation(self, src, index):
        g = self.game
        cs = self._take_preview(src, index)
        if len(cs) != 1:
            return False
        i = g.foundation_for(cs[0])
        if i is None:
            return False
        self.move_cards(src, index, ("found", i))
        return True

    def autoplay(self):
        """Prawy przycisk: przenosi na stosy końcowe wszystko, co się da."""
        g = self.game
        moved = True
        while moved and not g.won:
            moved = False
            if g.waste and g.foundation_for(g.waste[-1]) is not None:
                self.to_foundation(("waste",), None)
                moved = True
                continue
            for i, pile in enumerate(g.tableau):
                if pile and pile[-1][1] and g.foundation_for(pile[-1][0]) is not None:
                    self.to_foundation(("tab", i), len(pile) - 1)
                    moved = True
                    break

    def _after_move(self):
        g = self.game
        self._update_status()
        if g.check_win():
            if g.timed and g.scoring == "standard" and g.time > 30:
                g.score += 700000 // g.time
            if g.scoring == "vegas" and self.cumulative:
                self.vegas_bank = g.score
                config.set("sol_vegas_bank", g.score)
            self._update_status()
            QTimer.singleShot(150, self.start_animation)

    def _tick(self):
        g = self.game
        if g.started and not g.won and self.anim_timer.isActive() is False:
            g.time += 1
            if g.timed and g.scoring == "standard" and g.time % 10 == 0:
                g.add_score(-2)
            self._update_status()

    def _update_status(self):
        g = self.game
        if g.scoring == "vegas":
            self.score_label.setText(T("Wynik: ", "Score: ") + (f"-${-g.score}" if g.score < 0 else f"${g.score}"))
        elif g.scoring == "standard":
            self.score_label.setText(T("Wynik: ", "Score: ") + str(g.score))
        else:
            self.score_label.setText("")
        self.time_label.setText((T("Czas: ", "Time: ") + str(g.time)) if g.timed else "")

    # ------------------------------------------------ animacja wygranej
    def start_animation(self):
        t = self.table
        t.anim = None
        canvas = t.grab()
        order = []
        g = self.game
        for level in range(12, -1, -1):
            for i in range(4):
                if len(g.found[i]) > level:
                    order.append((i, g.found[i][level]))
        t.anim = {"canvas": canvas, "order": order, "cur": None}
        self.anim_timer.start(16)
        t.update()

    def _anim_step(self):
        t = self.table
        a = t.anim
        if a is None:
            self.anim_timer.stop()
            return
        scale, cw, ch, gap = t.metrics()
        p = QPainter(a["canvas"])
        for _ in range(2):
            cur = a["cur"]
            if cur is None:
                if not a["order"]:
                    p.end()
                    self.stop_animation()
                    return
                i, card = a["order"].pop(0)
                r = t.pile_rect("found", i)
                # „zdejmujemy” kartę ze stosu na płótnie
                p.fillRect(r, FELT)
                g = self.game
                below = g.found[i][:g.found[i].index(card)]
                if below:
                    c = below[-1]
                    p.drawPixmap(r.topLeft(), cards.card_face(cards.RANKS[c[0]], c[1], scale))
                else:
                    p.drawPixmap(r.topLeft(), cards.placeholder(scale))
                vx = random.choice([-1, 1]) * random.uniform(2.5, 7.5) * scale
                cur = a["cur"] = {"card": card, "x": float(r.left()), "y": float(r.top()), "vx": vx,
                                  "vy": -random.uniform(0, 6) * scale}
            cur["vy"] += 0.98 * scale
            cur["x"] += cur["vx"]
            cur["y"] += cur["vy"]
            floor = t.height() - ch
            if cur["y"] > floor:
                cur["y"] = floor
                cur["vy"] = -cur["vy"] * 0.75
            c = cur["card"]
            p.drawPixmap(QPointF(cur["x"], cur["y"]), cards.card_face(cards.RANKS[c[0]], c[1], scale))
            if cur["x"] < -cw or cur["x"] > t.width():
                a["cur"] = None
        p.end()
        t.update()

    def stop_animation(self, show_dialog=True):
        was = self.table.anim is not None
        self.anim_timer.stop()
        self.table.anim = None
        self.table.update()
        if was and show_dialog:
            QTimer.singleShot(50, self._ask_new)

    def _ask_new(self):
        ans = dialogs.message(self, T("Pasjans", "Solitaire"), T("Gratulacje, wygrałeś!\nCzy chcesz rozdać ponownie?",
                                                                 "Congratulations, you won!\nDeal again?"), "question", ("yes", "no"))
        if ans == "yes":
            self.new_game()

    # ------------------------------------------------ ustawienia
    def choose_back(self):
        d = DeckDialog(self, self.back)
        if d.exec() == QDialog.Accepted:
            self.back = d.choice
            config.set("sol_back", self.back)
            self.table.update()

    def options(self):
        d = OptionsDialog(self)
        if d.exec() != QDialog.Accepted:
            return
        draw = 1 if d.d1.isChecked() else 3
        scoring = "standard" if d.s_std.isChecked() else "vegas" if d.s_vegas.isChecked() else "none"
        timed = d.timed.isChecked()
        self.statusbar.setVisible(d.status.isChecked())
        config.set("sol_status", d.status.isChecked())
        self.cumulative = d.cumulative.isChecked()
        config.set("sol_cumulative", self.cumulative)
        changed = (draw, scoring, timed) != (self.draw, self.scoring, self.timed)
        self.draw, self.scoring, self.timed = draw, scoring, timed
        config.update({"sol_draw": draw, "sol_scoring": scoring, "sol_timed": timed})
        if changed:
            self.new_game()

    def keyPressEvent(self, e):
        if self.table.anim is not None:
            self.stop_animation()
            return
        super().keyPressEvent(e)


class SolitaireApp:
    def __init__(self):
        self.win = None

    def handle(self, args):
        if self.win is None:
            self.win = SolitaireWindow()
            self.win.move(90, 60)
        self.win.show()
        self.win.raise_()
        self.win.activateWindow()


def main(args):
    return run_app("solitaire", SolitaireApp().handle, args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
