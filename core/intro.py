"""
Intro de abertura: a malha de linhas do JARVIS constrói, um de cada vez,
um cartão, um checkout, a palavra RASTRACKING e o Pixel da Meta; o pixel
"absorve" os dados, solta dinheiro, e no fim as mesmas linhas giram e se
encaixam no rosto do JARVIS, que então faz a saudação normal.

Tudo é desenhado com QPainter dentro do HudCanvas (ui.py). O rosto final é o
próprio HoloAvatar: os segmentos-alvo da última fase são as arestas reais da
malha projetada, e o avatar verdadeiro aparece em crossfade por cima.

Quando toca: na primeira abertura em cada PC (marca `intro_shown` em
config/api_keys.json). Para tocar em toda abertura, coloque
"intro_always": true no api_keys.json. Para nunca tocar, "intro_shown": true.
"""
from __future__ import annotations

import math
import random
import time

import numpy as np
from PyQt6.QtCore import QLineF, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen

from memory.config_manager import load_api_keys, _save_flag

HALF = 420          # segmentos por metade da malha (A e B)
_FLAG = "intro_shown"

# Linha do tempo (segundos)
T = dict(card=1.0, chk=2.4, fly=3.2, data=4.4, gone=5.8, ok=5.9, chkOut=6.8, rastr=6.8,
         pulse=8.2, rastrOut=9.4, pixel=9.4, absorb=11.0, money=12.4, spin=14.4,
         face=16.6, end=18.0)

_PACKETS = ["pedido", "valor", "utm", "cliente", "device", "origem"]


# ── configuração ─────────────────────────────────────────────────────────────
def is_pending() -> bool:
    cfg = load_api_keys()
    if cfg.get("intro_always", False):
        return True
    return not bool(cfg.get(_FLAG, False))


def mark_shown() -> None:
    try:
        _save_flag(_FLAG, True)
    except Exception as e:
        print(f"[Intro] could not save flag: {e}")


# ── utilidades ───────────────────────────────────────────────────────────────
def _clamp(v, a, b):
    return max(a, min(b, v))


def _ease(t):
    return 2 * t * t if t < 0.5 else -1 + (4 - 2 * t) * t


def _seg(t, a, b):
    return _clamp((t - a) / (b - a), 0.0, 1.0)


def _lerp(a, b, t):
    return a + (b - a) * t


def _rnd(a, b):
    return a + random.random() * (b - a)


# ── geradores de forma: cada um devolve np.ndarray (n, 4) = x0,y0,x1,y1 ──────
def _path_segs(pts, closed, step, jit):
    out = []
    n = len(pts)
    m = n if closed else n - 1
    for i in range(m):
        ax, ay = pts[i]
        bx, by = pts[(i + 1) % n]
        ln = math.hypot(bx - ax, by - ay)
        k = max(1, round(ln / step))
        for q in range(k):
            if random.random() < 0.12:          # falhas = fragmentos
                continue
            t0, t1 = q / k, (q + 1) / k
            out.append((_lerp(ax, bx, t0) + _rnd(-jit, jit), _lerp(ay, by, t0) + _rnd(-jit, jit),
                        _lerp(ax, bx, t1) + _rnd(-jit, jit), _lerp(ay, by, t1) + _rnd(-jit, jit)))
    return out


def _rrect_pts(x, y, w, h, r):
    p = []
    corners = [(x + w / 2 - r, y - h / 2 + r, -math.pi / 2, 0.0),
               (x + w / 2 - r, y + h / 2 - r, 0.0, math.pi / 2),
               (x - w / 2 + r, y + h / 2 - r, math.pi / 2, math.pi),
               (x - w / 2 + r, y - h / 2 + r, math.pi, math.pi * 1.5)]
    for cx, cy, a0, a1 in corners:
        for i in range(7):
            a = _lerp(a0, a1, i / 6)
            p.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return p


def _fragments(cx, cy, rx, ry, n, size):
    out = []
    for _ in range(n):
        a = _rnd(0, math.tau)
        r = math.sqrt(random.random())
        px, py = cx + math.cos(a) * r * rx, cy + math.sin(a) * r * ry
        p = [(px + _rnd(-size, size), py + _rnd(-size, size)) for _ in range(3)]
        for i, j in ((0, 1), (1, 2), (2, 0)):
            if random.random() < 0.7:
                out.append((p[i][0], p[i][1], p[j][0], p[j][1]))
    return out


def _fit(segs, n, cx, cy, rx, ry, s):
    segs = list(segs)
    while len(segs) < n:
        segs.extend(_fragments(cx, cy, rx, ry, 4, 10 * s))
    random.shuffle(segs)
    return np.array(segs[:n], dtype=np.float32)


def _scatter(n, x0, x1, H):
    out = []
    for _ in range(n):
        x, y = _rnd(x0, x1), _rnd(-50, H + 50)
        out.append((x, y, x + _rnd(-14, 14), y + _rnd(-14, 14)))
    return np.array(out, dtype=np.float32)


def _shape_card(cx, cy, s):
    w, h = 300 * s, 185 * s
    o = []
    o += _path_segs(_rrect_pts(cx, cy, w, h, 14 * s), True, 14 * s, 1.5)
    o += _path_segs(_rrect_pts(cx - w / 2 + 55 * s, cy - h / 2 + 70 * s, 50 * s, 38 * s, 4 * s), True, 10 * s, 1)
    for i in range(4):
        x = cx - w / 2 + 30 * s + i * ((w - 60 * s) / 4)
        o += _path_segs([(x, cy + h / 2 - 60 * s), (x + (w - 60 * s) / 4 - 14 * s, cy + h / 2 - 60 * s)], False, 12 * s, 1)
    o += _path_segs([(cx - w / 2 + 30 * s, cy + h / 2 - 28 * s), (cx - w / 2 + 30 * s + w * 0.5, cy + h / 2 - 28 * s)], False, 12 * s, 1)
    o += _fragments(cx, cy, w * 0.45, h * 0.4, 14, 9 * s)
    return _fit(o, HALF, cx, cy, w * 0.75, h * 0.75, s)


def _shape_checkout(cx, cy, s):
    w, h = 300 * s, 230 * s
    o = []
    o += _path_segs(_rrect_pts(cx, cy, w, h, 10 * s), True, 14 * s, 1.5)
    o += _path_segs([(cx - w / 2, cy - h / 2 + 36 * s), (cx + w / 2, cy - h / 2 + 36 * s)], False, 12 * s, 1)
    o += _path_segs(_rrect_pts(cx, cy, w - 48 * s, 60 * s, 4 * s), True, 10 * s, 1)
    o += _fragments(cx, cy, w * 0.45, h * 0.42, 16, 9 * s)
    return _fit(o, HALF, cx, cy, w * 0.5, h * 0.5, s)


def _text_font(px: float) -> QFont:
    f = QFont("Arial Black", max(8, int(px)))
    f.setWeight(QFont.Weight.Black)
    f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 106)
    return f


def _shape_text(txt, cx, cy, px, s):
    """Contorno real das letras (bordas do texto renderizado) vira malha."""
    pad = 24
    w, h = int(px * len(txt) * 0.95) + pad * 2, int(px * 1.4) + pad * 2
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(0)
    q = QPainter(img)
    q.setFont(_text_font(px))
    q.setPen(QColor(255, 255, 255))
    q.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, txt)
    q.end()
    ptr = img.constBits()
    ptr.setsize(img.sizeInBytes())
    arr = np.frombuffer(ptr, dtype=np.uint8).reshape(h, img.bytesPerLine() // 4, 4)[:, :w, 3]
    on = arr > 128
    edge = on.copy()
    edge[1:-1, 1:-1] &= ~(on[:-2, 1:-1] & on[2:, 1:-1] & on[1:-1, :-2] & on[1:-1, 2:])
    ys, xs = np.nonzero(edge)
    out = []
    if len(xs) > 10:
        pts = np.stack([xs, ys], axis=1).astype(np.float32)
        want = int(HALF * 0.92)
        idx = np.linspace(0, len(pts) - 1, min(want, len(pts))).astype(int)
        ox, oy = cx - w / 2, cy - h / 2
        for i in idx:
            p = pts[i]
            d = np.hypot(pts[:, 0] - p[0], pts[:, 1] - p[1])
            cand = np.nonzero((d >= 6) & (d <= 11))[0]
            if cand.size == 0:
                continue
            qd = pts[cand[np.argmin(d[cand])]]
            out.append((ox + p[0] + _rnd(-.6, .6), oy + p[1] + _rnd(-.6, .6),
                        ox + qd[0] + _rnd(-.6, .6), oy + qd[1] + _rnd(-.6, .6)))
    out += _fragments(cx, cy, w * 0.55, h * 0.9, 10, 8)
    return _fit(out, HALF, cx, cy, w * 0.5, h * 0.6, s)


def _shape_pixel(cx, cy, k, s):
    R = 40 * s * k
    inf = []
    for i in range(120):
        t = i / 120 * math.tau
        q = 1 + math.sin(t) ** 2
        inf.append((cx + R * 1.6 * math.cos(t) / q, cy + R * 1.6 * math.sin(t) * math.cos(t) / q))
    o = []
    # o "infinito" do pixel, três vezes com leve deslocamento, para ler forte
    for dx, dy in ((0, 0), (2, 2), (-2, 1)):
        o += [(a + dx, b + dy, c + dx, d + dy) for a, b, c, d in _path_segs(inf, True, 7 * s, 0.8)]

    def circ(r):
        return [(cx + r * math.cos(i / 72 * math.tau), cy + r * math.sin(i / 72 * math.tau)) for i in range(72)]
    o += _path_segs(circ(R * 2.2), True, 10 * s, 1.5)
    o += [sg for sg in _path_segs(circ(R * 2.6), True, 14 * s, 2) if random.random() < 0.5]
    o += _fragments(cx, cy, R * 2.4, R * 2.4, 10, 7 * s)
    return _fit(o, HALF, cx, cy, R * 2.6, R * 2.6, s)


def _shape_face(avatar, cx, cy, r, s):
    """Arestas reais do HoloAvatar projetadas como o HUD as desenha."""
    try:
        from core import avatar as _av
        cam = getattr(_av, "_CAM_D", 4.6)
        verts, norms = avatar._pose()
        w = np.maximum(cam - verts[:, 2], 0.35)
        k = (cam / w) * r
        xs = cx + verts[:, 0] * k
        ys = cy - verts[:, 1] * k
        e0, e1 = avatar._e0, avatar._e1
        front = (norms[e0, 2] > -0.05) & (norms[e1, 2] > -0.05)
        segs = np.stack([xs[e0], ys[e0], xs[e1], ys[e1]], axis=1)[front].astype(np.float32)
        n = HALF * 2
        if len(segs) >= n:
            pick = np.random.choice(len(segs), n, replace=False)
            segs = segs[pick]
        else:
            segs = _fit(segs.tolist(), n, cx, cy, r * 0.7, r, s)
        return segs
    except Exception as e:                      # avatar indisponível: elipse de malha
        print(f"[Intro] face mesh fallback: {e}")
        return _fit(_fragments(cx, cy, r * 0.7, r, 300, 12 * s), HALF * 2, cx, cy, r * 0.7, r, s)


def _move(a, dx, dy):
    return a + np.array([dx, dy, dx, dy], dtype=np.float32)


def _scale_about(a, cx, cy, k):
    c = np.array([cx, cy, cx, cy], dtype=np.float32)
    return c + (a - c) * k


# ── a animação ───────────────────────────────────────────────────────────────
class IntroAnimation:
    def __init__(self) -> None:
        self._t0: float | None = None
        self.done = False
        self._built_key = None
        self._KA = self._KB = None
        self._coins: list = []
        self._burst = False
        self._last_coin = 0.0
        self._last_now = 0.0

    def start(self, delay: float = 0.5) -> None:
        self._t0 = time.time() + delay
        self.done = False
        mark_shown()

    @property
    def active(self) -> bool:
        return self._t0 is not None and not self.done

    def skip(self) -> None:
        self.done = True

    # ── keyframes ───────────────────────────────────────────────────────────
    def _build(self, W, H, avatar, head_cx, head_cy, r_head):
        s = min(W, H) / 900.0
        cx, cy = W / 2.0, H / 2.0
        far_left, right = -700 * s, W + 500 * s
        self._s, self._cx, self._cy, self._far_left, self._right = s, cx, cy, far_left, right
        face = _shape_face(avatar, head_cx, head_cy, r_head, s) if avatar is not None else \
            _fit(_fragments(cx, cy, 160 * s, 230 * s, 300, 12 * s), HALF * 2, cx, cy, 160 * s, 230 * s, s)
        fA, fB = face[:HALF], face[HALF:HALF * 2]
        card_l = _shape_card(cx - 520 * s, cy, s)
        card_c = _move(card_l, 520 * s, -150 * s)
        rastr = _shape_text("RASTRACKING", cx, cy, 76 * s, s)
        rastr_big = _scale_about(rastr, cx, cy, 1.1)
        chk = _shape_checkout(cx, cy, s)
        pix = _shape_pixel(cx, cy, 1.0, s)
        pix_big = _shape_pixel(cx, cy, 1.9, s)
        self._KA = [(0, _scatter(HALF, -100, W * 0.45, H)), (T["card"] + 1.4, card_l), (T["fly"], card_l),
                    (T["data"], card_c), (T["gone"] - 0.2, card_c), (T["rastr"] + 1.0, rastr), (T["pulse"], rastr),
                    (T["pulse"] + 0.8, rastr_big), (T["rastrOut"], rastr_big),
                    (T["rastrOut"] + 1.2, _move(rastr_big, far_left - cx, 0)),
                    (T["spin"], _move(rastr_big, far_left - cx, 0)), (T["face"], fA)]
        self._KB = [(0, _scatter(HALF, W * 0.55, W + 100, H)), (T["chk"] + 0.9, chk), (T["chkOut"], chk),
                    (T["chkOut"] + 1.2, _move(chk, far_left - cx, 0)), (T["chkOut"] + 1.21, _move(pix, right - cx, 0)),
                    (T["pixel"], _move(pix, right - cx, 0)), (T["pixel"] + 1.2, pix), (T["absorb"], pix),
                    (T["money"], pix_big), (T["spin"], pix_big), (T["face"], fB)]

    def _sample(self, K, t, spin_from):
        i = 0
        while i < len(K) - 1 and K[i + 1][0] <= t:
            i += 1
        if i >= len(K) - 1:
            return K[-1][1]
        t0, A = K[i]
        t1, B = K[i + 1]
        e = _ease(_seg(t, t0, t1))
        out = A + (B - A) * e
        if t0 >= spin_from:                      # giro em espiral na montagem final
            ang = math.sin(e * math.pi) * math.pi * 0.9
            c, sn = math.cos(ang), math.sin(ang)
            cx, cy = self._cx, self._cy
            x0, y0, x1, y1 = out[:, 0] - cx, out[:, 1] - cy, out[:, 2] - cx, out[:, 3] - cy
            out = np.stack([cx + x0 * c - y0 * sn, cy + x0 * sn + y0 * c,
                            cx + x1 * c - y1 * sn, cy + x1 * sn + y1 * c], axis=1)
        return out

    # ── desenho ─────────────────────────────────────────────────────────────
    @staticmethod
    def _col(c: QColor, a: float) -> QColor:
        q = QColor(c)
        q.setAlphaF(_clamp(a, 0.0, 1.0))
        return q

    def _mesh(self, p, segs, alpha, glow, pri):
        if alpha <= 0.01:
            return
        lines = [QLineF(float(a), float(b), float(c), float(d)) for a, b, c, d in segs]
        if glow > 0:
            p.setPen(QPen(self._col(pri, 0.10 * alpha * min(1.0, glow / 6)), 2.5 + glow * 0.4))
            p.drawLines(lines)
        p.setPen(QPen(self._col(pri, 0.85 * alpha), 0.9))
        p.drawLines(lines)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._col(pri, 0.9 * alpha))
        for a, b, _, _ in segs[::5]:
            p.drawEllipse(QPointF(float(a), float(b)), 1.0, 1.0)
        p.setBrush(Qt.BrushStyle.NoBrush)

    def _label(self, p, txt, x, y, a, size, col):
        if a <= 0.01:
            return
        p.setPen(QPen(self._col(col, a), 1))
        f = QFont("Courier New", int(size))
        f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 120)
        p.setFont(f)
        p.drawText(QRectF(x - 400, y - 12, 800, 24), Qt.AlignmentFlag.AlignCenter, txt)

    def _packet(self, p, fx, fy, tx, ty, t, txt, arc, green):
        x = _lerp(fx, tx, t)
        y = _lerp(fy, ty, t) - math.sin(t * math.pi) * arc
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._col(green, 0.25))
        p.drawEllipse(QPointF(x, y), 9, 9)
        p.setBrush(green)
        p.drawEllipse(QPointF(x, y), 4, 4)
        p.setBrush(Qt.BrushStyle.NoBrush)
        if txt:
            self._label(p, txt, x, y - 14, 0.85, 8, green)

    def _rings(self, p, x, y, a, r0, r1, period, n, inward, pri, now):
        for i in range(n):
            ph = ((now / period) + i / n) % 1.0
            if inward:
                ph = 1 - ph
            al = a * (ph if inward else 1 - ph) * 0.7
            r = _lerp(r0, r1, ph)
            p.setPen(QPen(self._col(pri, al), 1.2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(x, y), r, r)

    def _glow_text(self, p, txt, x, y, px, a, pri):
        if a <= 0.01:
            return
        f = _text_font(px)
        path = QPainterPath()
        path.addText(0, 0, f, txt)
        br = path.boundingRect()
        path.translate(x - br.center().x(), y - br.center().y())
        p.setBrush(Qt.BrushStyle.NoBrush)
        for wdt, al in ((18, 0.05), (10, 0.08), (4, 0.16)):
            p.setPen(QPen(self._col(pri, a * al), wdt))
            p.drawPath(path)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._col(pri, a * 0.6))
        p.drawPath(path)
        p.setBrush(Qt.BrushStyle.NoBrush)

    def _burst_coins(self, x, y, n):
        for _ in range(n):
            a, v = _rnd(0, math.tau), _rnd(2, 7)
            self._coins.append([x, y, math.cos(a) * v, math.sin(a) * v - 2, 1.0, _rnd(7, 13)])

    def paint(self, p: QPainter, W: int, H: int, avatar, head_cx: float, head_cy: float, r_head: float,
              pri: QColor, green: QColor) -> float:
        """Desenha o quadro atual. Devolve a opacidade com que o chamador deve
        desenhar o avatar real por cima (0 = ainda não; 1 = intro terminou)."""
        if self._t0 is None:
            return 1.0
        now = time.time()
        t = now - self._t0
        key = (W, H, round(head_cx), round(head_cy), round(r_head))
        if self._built_key != key:
            self._build(W, H, avatar, head_cx, head_cy, r_head)
            self._built_key = key
        if t < 0:
            return 0.0
        if t >= T["end"]:
            self.done = True
            return 1.0
        s, cx, cy, far_left, right = self._s, self._cx, self._cy, self._far_left, self._right
        gold = QColor("#f3c969")

        A = self._sample(self._KA, t, T["spin"])
        B = self._sample(self._KB, t, T["spin"])
        r_power = _seg(t, T["pulse"], T["pulse"] + 0.8) * (1 - _seg(t, T["rastrOut"], T["rastrOut"] + 0.6))
        p_power = _seg(t, T["absorb"], T["money"])
        face_k = _seg(t, T["face"], T["face"] + 1.0)
        glow_a = (3 + r_power * 24) if t < T["spin"] else 3
        glow_b = (3 + p_power * 28) if t < T["spin"] else 3
        fade_a = 1 - _seg(t, T["gone"] - 0.2, T["gone"] + 0.3) if (T["gone"] - 0.2 <= t < T["rastr"] + 0.3) else 1.0
        mesh_alpha = 1.0 - face_k

        # posições que os textos seguem
        chk_draw = _seg(t, T["chk"], T["chk"] + 0.9)
        chk_slide = _ease(_seg(t, T["chkOut"], T["chkOut"] + 1.2))
        chk_x = _lerp(cx, far_left, chk_slide)
        chk_a = chk_draw * (1 - chk_slide)
        r_in = _seg(t, T["rastr"], T["rastr"] + 1.0)
        r_out = _ease(_seg(t, T["rastrOut"], T["rastrOut"] + 1.2))
        r_x = _lerp(cx, far_left, r_out)
        r_a = r_in * (1 - r_out)
        p_in = _seg(t, T["pixel"], T["pixel"] + 1.2)
        p_x = _lerp(right, cx, _ease(p_in))

        # a palavra acende por baixo da malha
        if r_a > 0.02 and t < T["spin"]:
            k = 0.22 + r_power * 0.5
            self._glow_text(p, "RASTRACKING", r_x, cy, 76 * s * (1 + 0.1 * _seg(t, T["pulse"], T["pulse"] + 0.8)),
                            r_a * k, pri)

        self._mesh(p, A, max(0.15, fade_a) * mesh_alpha, glow_a, pri)
        self._mesh(p, B, mesh_alpha, glow_b, pri)

        if t < T["spin"]:
            if chk_a > 0.02:
                self._label(p, "CHECKOUT", chk_x, cy - 115 * s + 18 * s, chk_a, 10, pri)
                ok = _seg(t, T["ok"], T["ok"] + 0.6)
                if ok > 0:
                    self._label(p, "PAGAMENTO APROVADO", chk_x, cy + 115 * s - 28 * s, chk_a * ok, 9, green)
                    p.setPen(QPen(self._col(green, chk_a * (1 - ok) * 0.8), 1))
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    rr = 40 + ok * 240
                    p.drawEllipse(QPointF(chk_x, cy), rr, rr)
                else:
                    self._label(p, "aguardando cartao...", chk_x, cy + 115 * s - 28 * s, chk_a * 0.6, 8, pri)
            fly = _ease(_seg(t, T["fly"], T["data"]))
            card_x, card_y = _lerp(cx - 520 * s, cx, fly), _lerp(cy, cy - 150 * s, fly)
            if T["data"] <= t < T["gone"] + 0.4:
                for i, txt in enumerate(_PACKETS[:4]):
                    tt = _seg(t, T["data"] + i * 0.25, T["data"] + i * 0.25 + 0.9)
                    if 0 < tt < 1:
                        self._packet(p, card_x, card_y, cx, cy, tt, txt, 20, green)
            if r_a > 0.02:
                self._label(p, "TRACKEAMENTO  ·  ATRIBUICAO  ·  ESCALA", r_x, cy + 72 * s, r_a * 0.8, 9, pri)
                if r_power > 0:
                    self._rings(p, r_x, cy, r_a * r_power, 60 * s, 300 * s, 1.2, 3, False, pri, now)
            if T["chkOut"] <= t < T["pulse"] + 0.6:
                for i, txt in enumerate(_PACKETS):
                    tt = _seg(t, T["chkOut"] + i * 0.2, T["chkOut"] + i * 0.2 + 1.0)
                    if 0 < tt < 1:
                        self._packet(p, chk_x, cy, cx, cy, tt, txt, 60, green)
            if p_in > 0.9:
                self._label(p, "PIXEL DA META", cx, cy + (130 + p_power * 100) * s, 1.0, 9, pri)
                if p_power > 0 and t < T["money"]:
                    self._rings(p, cx, cy, 1.0, 320 * s, 90 * s, 0.7, 4, True, pri, now)
            if T["rastrOut"] <= t < T["absorb"] + 0.8:
                for i in range(18):
                    tt = _seg(t, T["rastrOut"] + i * 0.08, T["rastrOut"] + i * 0.08 + 1.1)
                    if 0 < tt < 1:
                        txt = _PACKETS[(i // 3) % len(_PACKETS)] if i % 3 == 0 else ""
                        self._packet(p, r_x, cy + ((i % 3) - 1) * 60 * s, p_x, cy, tt, txt, ((i % 3) - 1) * 80, green)
            if t >= T["money"]:
                if not self._burst:
                    self._burst_coins(cx, cy, 90)
                    self._burst = True
                if now - self._last_coin > 0.045 and t < T["money"] + 1.6:
                    self._last_coin = now
                    self._burst_coins(cx + _rnd(-30, 30), cy + _rnd(-20, 20), 3)

        # dinheiro (tempo real, some antes do rosto)
        dt = min(0.05, now - (self._last_now or now))
        self._last_now = now
        f = dt * 60
        if t >= T["spin"] + 0.4:
            self._coins = []
        alive = []
        for c in self._coins:
            c[0] += c[2] * f
            c[1] += c[3] * f
            c[3] += 0.08 * f
            c[2] *= 0.99 ** f
            c[4] -= dt / 1.6
            if c[4] > 0:
                alive.append(c)
        self._coins = alive
        if alive:
            fnt = QFont("Courier New", 9)
            fnt.setBold(True)
            p.setFont(fnt)
            for x, y, _, _, life, rad in alive:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(self._col(gold, 0.25 * life))
                p.drawEllipse(QPointF(x, y), rad * 1.6, rad * 1.6)
                p.setBrush(self._col(gold, 0.95 * life))
                p.drawEllipse(QPointF(x, y), rad, rad)
                p.setPen(QPen(self._col(QColor("#3a2a00"), life), 1))
                p.drawText(QRectF(x - rad, y - rad, rad * 2, rad * 2), Qt.AlignmentFlag.AlignCenter, "$")
            p.setBrush(Qt.BrushStyle.NoBrush)

        return face_k
