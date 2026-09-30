"""Test keyboard window (DLOG 1000), using the KBDT key maps and keyboard PICTs."""
from . import program as P
from . import resources
from . import widgets as W
from .dialogs import DialogWindow

BLACK_KEYS = {1, 3, 6, 8, 10}
# computer keyboard -> semitone offset from the middle C of the visible page
QWERTY = {c: i for i, c in enumerate('awsedftgyhujkolp;')}


class Keys(W.Widget):
    """The 5-octave keyboard (user item 2)."""
    interactive = True

    def __init__(self, rect, win):
        super().__init__(rect)
        self.win = win
        d = resources.data()
        self.octaves, self.octave_w, _ = d['kbdg']
        self.maps = d['kbdt']
        self.down = set()
        self.mouse_note = None

    def last_is_partial(self):
        return self.win.base + 12 * self.octaves > 127

    def entries(self):
        """Yield (key rect entry, x offset, note)."""
        for k in range(self.octaves):
            partial = k == self.octaves - 1 and self.last_is_partial()
            for e in self.maps[1 if partial else 0]:
                note = self.win.base + 12 * k + e['key']
                if note <= 127:
                    yield e, k * self.octave_w, note

    def draw(self):
        s = self.surface
        t, l, b, r = self.rect
        s.image(l, t, 1001 if self.last_is_partial() else 1000, self.tag)
        for e, dx, note in self.entries():
            if note in self.down:
                it, il, ib, ir = e['invert']
                color = W.WHITE if e['key'] in BLACK_KEYS else W.BLACK
                s.fill(l + dx + il, t + it, l + dx + ir, t + ib, color, self.tag)

    def note_at(self, x, y):
        t, l, b, r = self.rect
        px, py = x - l, y - t
        for e, dx, note in self.entries():
            at, al, ab, ar = e['area']
            if al + dx <= px < ar + dx and at <= py < ab:
                return note
        return None

    def press(self, x, y):
        n = self.note_at(x, y)
        if n is not None:
            self.mouse_note = n
            self.win.note_on(n)

    def drag(self, x, y):
        n = self.note_at(x, y)
        if n != self.mouse_note:
            if self.mouse_note is not None:
                self.win.note_off(self.mouse_note)
            self.mouse_note = n
            if n is not None:
                self.win.note_on(n)

    def release(self, x, y):
        if self.mouse_note is not None:
            self.win.note_off(self.mouse_note)
            self.mouse_note = None


class MiniKeys(W.Widget):
    """Full-range keyboard (user item 3): shows and selects the visible page."""
    interactive = True

    def __init__(self, rect, win):
        super().__init__(rect)
        self.win = win

    def draw(self):
        s = self.surface
        t, l, b, r = self.rect
        s.image(l, t, 1002, self.tag)
        w = resources.data()['kbdg'][2]
        o = self.win.octave
        x0 = l + o * w
        x1 = min(r, x0 + 5 * w + 1)
        s.frame(x0, t, x1, b, W.BLACK, self.tag, 2)

    def press(self, x, y):
        w = resources.data()['kbdg'][2]
        t, l, b, r = self.rect
        self.win.set_octave(int((x - l) // w) - 2)


class KeyboardWindow(DialogWindow):
    def __init__(self, app):
        super().__init__(app, 1000, 'Keyboard')
        self.octave = 3
        s = self.surface
        it = self.items
        self.keys = s.add(Keys(it[2]['rect'], self))
        self.mini = s.add(MiniKeys(it[3]['rect'], self))
        self.oct_bar = s.add(W.ScrollBar(it[4]['rect'], 0, 6, self.octave, self.set_octave, page=1))
        self.labels = [s.add(W.Text(it[n]['rect'], '', align=a))
                       for n, a in ((5, 'left'), (10, 'center'), (6, 'right'))]
        st = self.add_static(skip=(5, 6, 8, 10, 12, 15, 18))
        del st
        self.values = {}
        state = app.kbd_state
        for ctl, stat, key, lo in ((7, 8, 'velocity', 1), (11, 12, 'reverb', 0), (14, 15, 'chorus', 0),
                                   (17, 18, 'surround', 0)):
            txt = s.add(W.Text(it[stat]['rect'], str(state[key])))
            s.add(W.ScrollBar(it[ctl]['rect'], lo, 127, state[key],
                              lambda v, key=key, txt=txt: self.set_value(key, v, txt)))
        self.add_buttons()
        self.set_octave(self.octave)
        self.top.bind('<KeyPress>', self.key_down)
        self.top.bind('<KeyRelease>', self.key_up)
        self.top.bind('<Return>', lambda e: None)
        self._pending_up = {}

    @property
    def base(self):
        return self.octave * 12

    def set_octave(self, o):
        o = max(0, min(6, o))
        self.octave = o
        self.oct_bar.set_value(o)
        self.labels[0].set(P.note_name(self.base))
        self.labels[1].set(P.note_name(self.base + 24))
        self.labels[2].set(P.note_name(min(127, self.base + 59)))
        self.keys.redraw()
        self.mini.redraw()

    def set_value(self, key, v, txt):
        self.app.kbd_state[key] = v
        txt.set(str(v))
        midi = self.app.midi
        if key == 'reverb':
            midi.reverb(v)
        elif key == 'chorus':
            midi.chorus(v)
        elif key == 'surround':
            midi.surround(v)

    def note_on(self, n):
        self.keys.down.add(n)
        self.app.midi.note(n, self.app.kbd_state['velocity'])
        self.keys.redraw()

    def note_off(self, n):
        self.keys.down.discard(n)
        self.app.midi.note(n, 0)
        self.keys.redraw()

    # computer keyboard; key auto-repeat produces release/press pairs, so
    # releases are deferred briefly and cancelled by an immediate re-press
    def key_down(self, ev):
        ch = ev.char.lower()
        if ch == 'z':
            self.set_octave(self.octave - 1)
        elif ch == 'x':
            self.set_octave(self.octave + 1)
        if ch not in QWERTY:
            return
        n = self.base + 24 + QWERTY[ch]
        job = self._pending_up.pop(ch, None)
        if job:
            self.top.after_cancel(job)
            return
        if n <= 127 and n not in self.keys.down:
            self.note_on(n)

    def key_up(self, ev):
        ch = ev.char.lower()
        if ch in QWERTY:
            n = self.base + 24 + QWERTY[ch]
            self._pending_up[ch] = self.top.after(30, lambda: self._release(ch, n))

    def _release(self, ch, n):
        self._pending_up.pop(ch, None)
        if n in self.keys.down:
            self.note_off(n)

    def close(self):
        for n in list(self.keys.down):
            self.note_off(n)
        self.app.keyboard = None
        super().close()
