"""Classic Macintosh controls drawn on a Tk Canvas.

All geometry is in original QuickDraw pixels (t, l, b, r); the Surface
multiplies by an integer scale so the 1-bit artwork stays crisp.
"""
import math
import tkinter as tk
import tkinter.font as tkfont

from . import resources

BLACK, WHITE, GRAY = '#000000', '#FFFFFF', '#808080'
_images = {}
_fonts = {}

SYSTEM_FAMILIES = ('Chicago', 'ChicagoFLF', 'Charcoal', 'Geneva', 'Lucida Grande', 'Segoe UI',
                   'Tahoma', 'DejaVu Sans', 'Helvetica', 'Arial')
SMALL_FAMILIES = ('Geneva', 'Verdana', 'Tahoma', 'DejaVu Sans', 'Helvetica', 'Arial')


def font(kind, scale):
    """kind: 'system' (Chicago 12 stand-in) or 'small' (Geneva 9 stand-in)."""
    key = (kind, scale)
    if key not in _fonts:
        fams = set(tkfont.families())
        prefs = SYSTEM_FAMILIES if kind == 'system' else SMALL_FAMILIES
        fam = next((f for f in prefs if f in fams), 'TkDefaultFont')
        px = {'system': 12, 'small': 10, 'bold': 10}[kind]
        weight = 'bold' if kind == 'bold' else 'normal'
        _fonts[key] = tkfont.Font(family=fam, size=-px * scale, weight=weight)
    return _fonts[key]


def pict(pict_id, scale):
    key = (pict_id, scale)
    if key not in _images:
        img = tk.PhotoImage(file=resources.pict_path(pict_id))
        if scale != 1:
            img = img.zoom(scale)
        _images[key] = img
    return _images[key]


def checker(w, h, scale):
    """50% gray pattern image (Tk stipples do not work on macOS)."""
    key = ('checker', w, h, scale)
    if key not in _images:
        img = tk.PhotoImage(width=w * scale, height=h * scale)
        rows = []
        for y in range(h):
            row = ' '.join((BLACK if (x + y) % 2 else WHITE) for x in range(w) for _ in range(scale))
            rows.extend(['{' + row + '}'] * scale)
        img.put(' '.join(rows))
        _images[key] = img
    return _images[key]


class Surface(tk.Canvas):
    def __init__(self, master, width, height, scale):
        super().__init__(master, width=width * scale, height=height * scale, bg=WHITE,
                         highlightthickness=0, bd=0)
        self.S = scale
        self.widgets = []
        self.capture = None
        self.bind('<ButtonPress-1>', self._press)
        self.bind('<B1-Motion>', self._drag)
        self.bind('<ButtonRelease-1>', self._release)

    def add(self, w):
        w.surface = self
        w.tag = f'w{id(w)}'
        self.widgets.append(w)
        w.redraw()
        return w

    def pt(self, ev):
        return ev.x / self.S, ev.y / self.S

    def _press(self, ev):
        x, y = self.pt(ev)
        for w in reversed(self.widgets):
            if w.interactive and w.enabled and w.visible and w.hit(x, y):
                self.capture = w
                w.press(x, y)
                return

    def _drag(self, ev):
        if self.capture:
            self.capture.drag(*self.pt(ev))

    def _release(self, ev):
        w, self.capture = self.capture, None
        if w:
            w.release(*self.pt(ev))

    # ---------------------------------------------------------- primitives
    def fill(self, l, t, r, b, color, tag):
        S = self.S
        if r > l and b > t:
            self.create_rectangle(l * S, t * S, r * S, b * S, fill=color, outline='', tags=tag)

    def frame(self, l, t, r, b, color, tag, pen=1):
        self.fill(l, t, r, t + pen, color, tag)
        self.fill(l, b - pen, r, b, color, tag)
        self.fill(l, t, l + pen, b, color, tag)
        self.fill(r - pen, t, r, b, color, tag)

    def text(self, x, y, s, tag, kind='system', color=BLACK, anchor='nw', **kw):
        return self.create_text(x * self.S, y * self.S, text=s, anchor=anchor, fill=color,
                                font=font(kind, self.S), tags=tag, **kw)

    def image(self, x, y, pict_id, tag):
        return self.create_image(x * self.S, y * self.S, image=pict(pict_id, self.S), anchor='nw',
                                 tags=tag)


class Widget:
    interactive = False

    def __init__(self, rect):
        self.rect = list(rect)
        self.enabled = True
        self.visible = True
        self.surface = None
        self.tag = None

    def hit(self, x, y):
        t, l, b, r = self.rect
        return l <= x < r and t <= y < b

    def redraw(self):
        if not self.surface:
            return
        self.surface.delete(self.tag)
        if self.visible:
            self.draw()

    def draw(self):
        pass

    def set_enabled(self, on):
        if on != self.enabled:
            self.enabled = on
            self.redraw()

    def press(self, x, y):
        pass

    def drag(self, x, y):
        pass

    def release(self, x, y):
        pass


class Picture(Widget):
    def __init__(self, rect, pict_id, command=None):
        super().__init__(rect)
        self.pict_id = pict_id
        self.command = command
        self.interactive = command is not None

    def draw(self):
        t, l, b, r = self.rect
        self.surface.image(l, t, self.pict_id, self.tag)

    def release(self, x, y):
        if self.hit(x, y) and self.command:
            self.command()


class Text(Widget):
    def __init__(self, rect, text='', kind='system', align='left', command=None):
        super().__init__(rect)
        self.text, self.kind, self.align = text, kind, align
        self.command = command
        self.interactive = command is not None

    def set(self, text):
        if text != self.text:
            self.text = text
            self.redraw()

    def draw(self):
        t, l, b, r = self.rect
        color = BLACK if self.enabled else GRAY
        if self.align == 'right':
            self.surface.text(r, t, self.text, self.tag, self.kind, color, anchor='ne')
        elif self.align == 'center':
            self.surface.text((l + r) / 2, t, self.text, self.tag, self.kind, color, anchor='n')
        else:
            self.surface.text(l, t, self.text, self.tag, self.kind, color)

    def release(self, x, y):
        if self.hit(x, y) and self.command:
            self.command()


class Button(Widget):
    interactive = True

    def __init__(self, rect, title, command):
        super().__init__(rect)
        self.title, self.command = title, command
        self.down = False

    def draw(self):
        s = self.surface
        S = s.S
        t, l, b, r = self.rect
        rad = min(8, (b - t) // 2)
        fill = BLACK if self.down else WHITE
        pts = []
        for (cx, cy, a0) in ((r - rad, t + rad, 0), (l + rad, t + rad, 90), (l + rad, b - rad, 180),
                             (r - rad, b - rad, 270)):
            for k in range(7):
                a = math.radians(a0 + k * 15)
                pts += [(cx + rad * math.cos(a)) * S, (cy - rad * math.sin(a)) * S]
        s.create_polygon(pts, fill=fill, outline=BLACK if self.enabled else GRAY, width=S,
                         tags=self.tag)
        s.text((l + r) / 2, (t + b) / 2, self.title, self.tag, 'system',
               WHITE if self.down else (BLACK if self.enabled else GRAY), anchor='center')

    def press(self, x, y):
        self.down = True
        self.redraw()

    def drag(self, x, y):
        d = self.hit(x, y)
        if d != self.down:
            self.down = d
            self.redraw()

    def release(self, x, y):
        was = self.down
        self.down = False
        self.redraw()
        if was and self.hit(x, y):
            self.command()


class Radio(Widget):
    interactive = True

    def __init__(self, rect, title, command):
        super().__init__(rect)
        self.title, self.command = title, command
        self.value = False
        self.down = False

    def set(self, on):
        if on != self.value:
            self.value = on
            self.redraw()

    def mark(self, s, x, y, S, color):
        s.create_oval(x * S, y * S, (x + 12) * S, (y + 12) * S, outline=color,
                      width=S * (2 if self.down else 1), fill=WHITE, tags=self.tag)
        if self.value:
            s.create_oval((x + 3) * S, (y + 3) * S, (x + 9) * S, (y + 9) * S, fill=color, outline='',
                          tags=self.tag)

    def draw(self):
        s = self.surface
        t, l, b, r = self.rect
        color = BLACK if self.enabled else GRAY
        y = (t + b) // 2 - 6
        self.mark(s, l + 2, y, s.S, color)
        if self.title:
            s.text(l + 18, (t + b) / 2, self.title, self.tag, 'system', color, anchor='w')

    def press(self, x, y):
        self.down = True
        self.redraw()

    def drag(self, x, y):
        d = self.hit(x, y)
        if d != self.down:
            self.down = d
            self.redraw()

    def release(self, x, y):
        was = self.down
        self.down = False
        self.redraw()
        if was and self.hit(x, y):
            self.command()


class Check(Radio):
    def mark(self, s, x, y, S, color):
        s.fill(x, y, x + 12, y + 12, WHITE, self.tag)
        s.frame(x, y, x + 12, y + 12, color, self.tag, 2 if self.down else 1)
        if self.value:
            s.create_line(x * S, y * S, (x + 12) * S, (y + 12) * S, fill=color, width=S, tags=self.tag)
            s.create_line((x + 12) * S, y * S, x * S, (y + 12) * S, fill=color, width=S, tags=self.tag)


class TriState(Widget):
    """CDEF 256: EG time switch box showing blank / + / -."""
    interactive = True

    def __init__(self, rect, command):
        super().__init__(rect)
        self.value = 0
        self.command = command
        self.down = False

    def set(self, v):
        if v != self.value:
            self.value = v
            self.redraw()

    def draw(self):
        s = self.surface
        t, l, b, r = self.rect
        mid = (t + b) // 2
        x0, y0 = l + 2, mid - 6
        color = BLACK if self.enabled else GRAY
        s.fill(x0, y0, x0 + 12, y0 + 12, WHITE, self.tag)
        s.frame(x0, y0, x0 + 12, y0 + 12, color, self.tag, 2 if self.down else 1)
        if self.value > 0:
            s.fill(x0 + 5, y0 + 2, x0 + 7, y0 + 10, color, self.tag)
        if self.value:
            s.fill(x0 + 2, y0 + 5, x0 + 10, y0 + 7, color, self.tag)

    def hit(self, x, y):
        t, l, b, r = self.rect
        mid = (t + b) // 2
        return l <= x < l + 16 and mid - 8 <= y < mid + 8

    def press(self, x, y):
        self.down = True
        self.redraw()

    def release(self, x, y):
        self.down = False
        if self.hit(x, y):
            self.value = {0: 1, 1: -1, -1: 0}[self.value]
            self.command(self.value)
        self.redraw()


ARROW = [(8, 2), (14, 8), (10, 8), (10, 13), (6, 13), (6, 8), (2, 8)]  # pointing up, in a 16x16 box


class ScrollBar(Widget):
    """Standard CDEF 1 scroll bar used by the editor as a value slider."""
    interactive = True
    REPEAT_DELAY, REPEAT_RATE = 350, 60

    def __init__(self, rect, vmin, vmax, value, command, page=10):
        super().__init__(rect)
        self.min, self.max, self.value = vmin, vmax, value
        self.command = command
        self.page = page
        self.part = None
        self.grab = 0
        self._job = None
        t, l, b, r = rect
        self.horizontal = (r - l) >= (b - t)

    # geometry helpers along the main axis
    def _axis(self):
        t, l, b, r = self.rect
        return (l, r) if self.horizontal else (t, b)

    def _thumb_pos(self):
        a0, a1 = self._axis()
        span = a1 - a0 - 48
        if span <= 0 or self.max <= self.min:
            return None
        return a0 + 16 + round((self.value - self.min) * span / (self.max - self.min))

    def set_value(self, v):
        v = max(self.min, min(self.max, v))
        if v != self.value:
            self.value = v
            self.redraw()

    def set_range(self, vmin, vmax):
        self.min, self.max = vmin, vmax
        self.value = max(vmin, min(vmax, self.value))
        self.redraw()

    def draw(self):
        s = self.surface
        S = s.S
        t, l, b, r = self.rect
        active = self.enabled and self.max > self.min
        s.fill(l, t, r, b, WHITE, self.tag)
        s.frame(l, t, r, b, BLACK, self.tag)
        a0, a1 = self._axis()
        boxes = [(a0, -1), (a1 - 16, 1)]
        for pos, direction in boxes:
            if self.horizontal:
                bl, bt = pos, t
                s.frame(bl, t, bl + 16, b, BLACK, self.tag)
                pts = [(bl + (y if direction < 0 else 16 - y), bt + x) for x, y in ARROW]
            else:
                bl, bt = l, pos
                s.frame(l, bt, r, bt + 16, BLACK, self.tag)
                pts = [(bl + x, bt + (y if direction < 0 else 16 - y)) for x, y in ARROW]
            if active:
                pressed = self.part == ('down' if direction < 0 else 'up')
                flat = [c * S for p in pts for c in p]
                s.create_polygon(flat, fill=BLACK if pressed else WHITE, outline=BLACK, width=S,
                                 tags=self.tag)
        tp = self._thumb_pos()
        if active and tp is not None:
            if self.horizontal:
                s.create_image((a0 + 16) * S, (t + 1) * S, anchor='nw', tags=self.tag,
                               image=checker(a1 - a0 - 32, b - t - 2, S))
                s.fill(tp, t, tp + 16, b, WHITE, self.tag)
                s.frame(tp, t, tp + 16, b, BLACK, self.tag)
            else:
                s.create_image((l + 1) * S, (a0 + 16) * S, anchor='nw', tags=self.tag,
                               image=checker(r - l - 2, a1 - a0 - 32, S))
                s.fill(l, tp, r, tp + 16, WHITE, self.tag)
                s.frame(l, tp, r, tp + 16, BLACK, self.tag)

    def _part_at(self, x, y):
        a0, a1 = self._axis()
        p = x if self.horizontal else y
        if p < a0 + 16:
            return 'down'
        if p >= a1 - 16:
            return 'up'
        tp = self._thumb_pos()
        if tp is None:
            return None
        if tp <= p < tp + 16:
            return 'thumb'
        return 'pagedown' if p < tp else 'pageup'

    def _step(self):
        delta = {'down': -1, 'up': 1, 'pagedown': -self.page, 'pageup': self.page}.get(self.part, 0)
        if self.part in ('pagedown', 'pageup'):
            # stop paging once the thumb reaches the pointer
            tp = self._thumb_pos()
            p = self._last[0] if self.horizontal else self._last[1]
            if tp is not None and tp <= p < tp + 16:
                return
        self._apply(self.value + delta)

    def _apply(self, v):
        v = max(self.min, min(self.max, int(v)))
        if v != self.value:
            self.value = v
            self.redraw()
            self.command(v)

    def _repeat(self):
        if self.part and self.part != 'thumb':
            self._step()
            self._job = self.surface.after(self.REPEAT_RATE, self._repeat)

    def press(self, x, y):
        if self.max <= self.min:
            return
        self._last = (x, y)
        self.part = self._part_at(x, y)
        if self.part == 'thumb':
            p = x if self.horizontal else y
            self.grab = p - self._thumb_pos()
        elif self.part:
            self._step()
            self._job = self.surface.after(self.REPEAT_DELAY, self._repeat)
        self.redraw()

    def drag(self, x, y):
        self._last = (x, y)
        if self.part == 'thumb':
            a0, a1 = self._axis()
            span = a1 - a0 - 48
            p = (x if self.horizontal else y) - self.grab - (a0 + 16)
            self._apply(self.min + round(p * (self.max - self.min) / span))

    def release(self, x, y):
        if self._job:
            self.surface.after_cancel(self._job)
            self._job = None
        self.part = None
        self.redraw()


class Graph(Widget):
    """EG shape display (pitch, VDF or VDA envelope)."""

    def __init__(self, rect, points_fn, bipolar=True, inset=2):
        super().__init__(rect)
        self.points_fn = points_fn
        self.bipolar = bipolar
        self.inset = inset

    def draw(self):
        s = self.surface
        S = s.S
        t, l, b, r = self.rect
        i = self.inset
        t, l, b, r = t + i, l + i, b - i, r - i
        pts = self.points_fn()
        if not pts:
            return
        total = max(1e-6, pts[-1][0])
        coords = []
        for x, y in pts:
            px = l + (r - l - 1) * x / total
            if self.bipolar:
                py = (t + b - 1) / 2 - y / 99 * ((b - t - 1) / 2)
            else:
                py = (b - 1) - y / 99 * (b - t - 1)
            coords += [(px + 0.5) * S, (py + 0.5) * S]
        s.create_line(coords, fill=BLACK if self.enabled else GRAY, width=S, tags=self.tag)
