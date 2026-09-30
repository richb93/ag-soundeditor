"""Parameter editor dialogs, laid out from the original DLOG/DITL resources.

Item numbers below refer to the original DITL items; the byte offsets were
taken from the PGpr resources and the dialog code in CODE 3.
"""
import tkinter as tk
from tkinter import ttk

from . import program as P
from . import resources
from . import widgets as W

# DITL item types
BTN, CHK, RADIO, CTL, STAT, EDIT, ICON, PICT, USER = 4, 5, 6, 7, 8, 16, 32, 64, 0


def double(prog):
    return prog.osc2_active


# ----------------------------------------------------------------- bindings
class Bind:
    """Connects DITL item(s) to program bytes."""
    offsets = ()

    def __init__(self, enabled=None):
        self.enabled_fn = enabled

    def enabled(self, prog):
        return self.enabled_fn(prog) if self.enabled_fn else True


class Num(Bind):
    """Scroll-bar slider (item) with its value text (item + 1)."""

    def __init__(self, item, off, fmt=None, enabled=None):
        super().__init__(enabled)
        self.item, self.off, self.stat = item, off, item + 1
        self.fmt = fmt or (lambda v: str(v))
        self.offsets = (off,)

    def get(self, prog):
        return prog.get(self.off)

    def set(self, prog, v):
        prog.set(self.off, v)

    def limits(self, prog, cntl):
        return cntl['min'], cntl['max']


class Key(Num):
    def __init__(self, item, off, enabled=None):
        super().__init__(item, off, fmt=P.note_name, enabled=enabled)

    def get(self, prog):
        return prog.data[self.off] & 0x7F


class MS(Num):
    """Multisound / drum-kit selector (vertical arrows) with its name text."""

    def __init__(self, item, osc, enabled=None):
        super().__init__(item, (P.OSC1_MS, P.OSC2_MS)[osc], enabled=enabled)
        self.osc = osc
        self.offsets = ((P.OSC1_MS, P.OSC2_MS)[osc],)

    def get(self, prog):
        return prog.ms_index(self.osc)

    def set(self, prog, v):
        prog.set_ms_index(self.osc, v)

    def limits(self, prog, cntl):
        return 0, prog.ms_max(self.osc)


class Group(Bind):
    """Radio-button group; items[i] selects values[i]."""

    def __init__(self, items, off, mask=0xFF, shift=0, values=None, signed=False, enabled=None):
        super().__init__(enabled)
        self.items = items
        self.off, self.mask, self.shift, self.signed = off, mask, shift, signed
        self.values = values if values is not None else list(range(len(items)))
        self.offsets = (off,)

    def get(self, prog):
        if self.signed:
            return prog.get(self.off)
        return prog.get_bits(self.off, self.mask, self.shift)

    def set(self, prog, v):
        if self.signed:
            prog.set(self.off, v)
        else:
            prog.set_bits(self.off, self.mask, self.shift, v)


class Flag(Group):
    def __init__(self, item, off, mask, shift, enabled=None):
        super().__init__([item], off, mask, shift, [1], enabled=enabled)


class Tri(Bind):
    def __init__(self, item, off, seg, enabled=None):
        super().__init__(enabled)
        self.item, self.off, self.seg = item, off, seg
        self.offsets = (off,)


class EG(Bind):
    def __init__(self, item, kind, base=0):
        super().__init__()
        self.item, self.kind, self.base = item, kind, base


def eg_points(prog, kind, base=0):
    g = prog.get
    hold = 25
    if kind == 'pitch':
        sl, at, al, dt, rt, rl = (g(P.PEG_SL), g(P.PEG_AT), g(P.PEG_AL), g(P.PEG_DT), g(P.PEG_RT),
                                  g(P.PEG_RL))
        seq = [(0, sl), (at, al), (dt, 0), (hold, 0), (rt, rl)]
    elif kind == 'vdf':
        at, al, dt, bp, st, sl, rt, rl = (g(base + P.O_VDF_EG + i) for i in range(8))
        seq = [(0, 0), (at, al), (dt, bp), (st, sl), (hold, sl), (rt, rl)]
    else:
        at, al, dt, bp, st, sl, rt = (g(base + P.O_VDA_EG + i) for i in range(7))
        seq = [(0, 0), (at, al), (dt, bp), (st, sl), (hold, sl), (rt, 0)]
    x = 0
    pts = [(0, seq[0][1])]
    for dx, y in seq[1:]:
        x += max(0, dx) + 1   # +1 keeps zero-length segments visible
        pts.append((x, y))
    return pts


def vdf_binds(b):
    return ([Num(3, b + P.O_VDF_CUTOFF), Num(5, b + P.O_VDF_EG_INT), Num(7, b + P.O_VDF_EGI_VS),
             Num(9, b + P.O_VDF_EGT_VS), Key(11, b + P.O_VDF_KEY), Num(13, b + P.O_VDF_KBD),
             Num(15, b + P.O_VDF_EGT_KBD)]
            + [Num(17 + 2 * i, b + P.O_VDF_EG + i) for i in range(8)]
            + [Tri(33 + j, b + P.O_VDF_VS_BITS, j) for j in range(4)]
            + [Tri(37 + j, b + P.O_VDF_KBD_BITS, j) for j in range(4)]
            + [Group([41, 42, 43, 44], b + P.O_KBD_MODE, 0x03, 0), EG(47, 'vdf', b)])


def vda_binds(b):
    return ([Num(3, b + P.O_VDA_VS), Num(5, b + P.O_VDA_EGT_VS), Key(7, b + P.O_VDA_KEY),
             Num(9, b + P.O_VDA_KBD), Num(11, b + P.O_VDA_EGT_KBD)]
            + [Num(13 + 2 * i, b + P.O_VDA_EG + i) for i in range(7)]
            + [Tri(27 + j, b + P.O_VDA_VS_BITS, j) for j in range(4)]
            + [Tri(31 + j, b + P.O_VDA_KBD_BITS, j) for j in range(4)]
            + [Group([35, 36, 37, 38], b + P.O_KBD_MODE, 0x0C, 2), EG(41, 'vda', b)])


def pmg_binds(b):
    return [Group([3, 4, 5, 6, 7], b + P.O_PMG_WAVE, 0x07, 0),
            Num(8, b + P.O_PMG_FREQ), Num(10, b + P.O_PMG_INT), Num(12, b + P.O_PMG_DELAY),
            Num(14, b + P.O_PMG_FADE), Num(16, b + P.O_PMG_FREQ_KBD), Num(18, b + P.O_PMG_ATMOD1_FREQ),
            Num(20, b + P.O_PMG_AT_INT), Num(22, b + P.O_PMG_MOD1_INT),
            Group([24, 25], b + P.O_PMG_WAVE, 0x80, 7)]


SPECS = {
    # key: (DLOG id, window title, bindings factory(osc base))
    'osc': (601, 'OSC Basic', lambda b: [
        Group([3, 4, 5], P.OSC_MODE, 0x03, 0), Flag(6, P.OSC_MODE, 0x08, 3),
        MS(7, 0), Num(9, P.OSC_BASE[0] + P.O_VDA_LEVEL),
        Group([11, 12, 13, 14], P.OSC1_OCT, values=[-2, -1, 0, 1], signed=True),
        MS(15, 1, enabled=double), Num(17, P.OSC_BASE[1] + P.O_VDA_LEVEL, enabled=double),
        Group([19, 20, 21, 22], P.OSC2_OCT, values=[-2, -1, 0, 1], signed=True, enabled=double),
        Num(23, P.INTERVAL, enabled=double), Num(25, P.DETUNE, enabled=double),
        Num(27, P.DELAY_START, enabled=double)]),
    'color': (602, 'Color', lambda b: [
        Num(3, P.OSC_BASE[0] + P.O_COLOR_INT), Num(5, P.OSC_BASE[0] + P.O_COLOR_VS),
        Num(7, P.OSC_BASE[1] + P.O_COLOR_INT, enabled=double),
        Num(9, P.OSC_BASE[1] + P.O_COLOR_VS, enabled=double)]),
    'vdfmg': (603, 'VDF MG', lambda b: [
        Num(3, P.VDF_MG_FREQ), Num(5, P.VDF_MG_DELAY), Num(7, P.VDF_MG_INT),
        Group([9, 10, 11, 12, 13], P.VDF_MG_WAVE, 0x07, 0),
        Group([14, 15, 16, 17], P.VDF_MG_WAVE, 0x60, 5)]),
    'vdf': (604, 'VDF', vdf_binds),
    'vda': (606, 'VDA', vda_binds),
    'aftertouch': (607, 'After Touch', lambda b: [
        Num(3, P.AT_BEND), Num(5, P.AT_VDF_CUTOFF), Num(7, P.AT_VDF_MG), Num(9, P.AT_VDA_AMP)]),
    'joystick': (609, 'Joy Stick', lambda b: [Num(3, P.JS_VDF_SWEEP), Num(5, P.MOD2_VDF_MG)]),
    'pitchmg': (611, 'Pitch MG', pmg_binds),
    'pitcheg': (612, 'Pitch EG', lambda b: [
        Num(3, P.PEG_SL), Num(5, P.PEG_AT), Num(7, P.PEG_AL), Num(9, P.PEG_DT), Num(11, P.PEG_RT),
        Num(13, P.PEG_RL), Num(15, P.OSC_BASE[0] + P.O_PEG_INT),
        Num(17, P.OSC_BASE[1] + P.O_PEG_INT, enabled=double),
        Num(19, P.PEG_LEVEL_VS), Num(21, P.PEG_TIME_VS), EG(24, 'pitch')]),
}


# ------------------------------------------------------------ base window
class DialogWindow:
    def __init__(self, app, dlog_id, title):
        self.app = app
        self.prog = app.prog
        S = app.scale
        dl = resources.dlog(dlog_id)
        self.items = resources.ditl(dl['ditl'])
        t, l, b, r = dl['rect']
        self.top = tk.Toplevel(app.root)
        self.top.title(title)
        self.top.resizable(False, False)
        self.top.transient(app.root)
        self.top.protocol('WM_DELETE_WINDOW', self.cancel)
        self.surface = W.Surface(self.top, r - l, b - t, S)
        self.surface.pack()
        rx, ry = app.root.winfo_rootx(), app.root.winfo_rooty()
        self.top.geometry(f'+{rx + max(0, l - 6) * S}+{ry + max(0, t - 42) * S}')
        self.top.bind('<Return>', lambda e: self.ok())
        self.top.bind('<Escape>', lambda e: self.cancel())

    def add_pictures(self):
        for it in self.items.values():
            if it['type'] == PICT:
                self.surface.add(W.Picture(it['rect'], it['id']))

    def add_buttons(self):
        for it in self.items.values():
            if it['type'] == BTN and it['rect'][3] - it['rect'][1] > 4:
                cmd = {'OK': self.ok, 'Cancel': self.cancel, 'Done': self.ok,
                       'KBD': self.app.show_keyboard}.get(it['text'], self.ok)
                self.surface.add(W.Button(it['rect'], it['text'], cmd))

    def add_static(self, skip=(), subst=''):
        out = {}
        for n, it in self.items.items():
            if it['type'] == STAT and n not in skip and it['rect'][0] > -100:
                out[n] = self.surface.add(W.Text(it['rect'], it['text'].replace('^0', subst)))
        return out

    def ok(self):
        self.close()

    def cancel(self):
        self.close()

    def close(self):
        self.top.destroy()


# ---------------------------------------------------------- param editor
class ParamDialog(DialogWindow):
    def __init__(self, app, key, osc=0):
        dlog_id, title, factory = SPECS[key]
        base = P.OSC_BASE[osc]
        if key in ('vdf', 'vda', 'pitchmg'):
            title = f'{title} {osc + 1}'
        super().__init__(app, dlog_id, title)
        self.key, self.osc = key, osc
        self.binds = factory(base)
        self.snapshot = self.prog.snapshot()
        s = self.surface
        self.add_pictures()
        value_items = {b.stat for b in self.binds if isinstance(b, Num)}
        self.statics = self.add_static(skip=value_items, subst=str(osc + 1))
        self.controls = []  # (bind, widget-or-list)
        for b in self.binds:
            if isinstance(b, Num):
                it = self.items[b.item]
                cntl = resources.cntl(it['id'])
                lo, hi = b.limits(self.prog, cntl)
                bar = W.ScrollBar(it['rect'], lo, hi, b.get(self.prog),
                                  lambda v, b=b: self.edit(b, v))
                stat_rect = self.items[b.stat]['rect']
                if isinstance(b, MS):
                    stat_rect = [stat_rect[0], stat_rect[1] + 4, stat_rect[2], stat_rect[3] + 40]
                    text = W.Text(stat_rect, '', command=lambda b=b: self.pick_ms(b))
                else:
                    text = W.Text(stat_rect, '')
                s.add(bar)
                s.add(text)
                self.controls.append((b, (bar, text, cntl)))
            elif isinstance(b, Group):
                radios = []
                for item, val in zip(b.items, b.values):
                    it = self.items[item]
                    cls = W.Check if it['type'] == CHK else W.Radio
                    w = s.add(cls(it['rect'], it.get('text', ''),
                                  lambda b=b, val=val, cls=cls: self.pick(b, val, cls)))
                    radios.append((w, val))
                self.controls.append((b, radios))
            elif isinstance(b, Tri):
                it = self.items[b.item]
                w = s.add(W.TriState(it['rect'], lambda v, b=b: self.edit_tri(b, v)))
                self.controls.append((b, w))
            elif isinstance(b, EG):
                it = self.items[b.item]
                g = s.add(W.Graph(it['rect'], lambda b=b: eg_points(self.prog, b.kind, b.base),
                                  bipolar=b.kind != 'vda'))
                self.controls.append((b, g))
        self.add_buttons()
        self.prog.listeners.append(self.refresh)
        self.refresh()

    # -- editing
    def edit(self, b, v):
        b.set(self.prog, v)

    def edit_tri(self, b, v):
        self.prog.set_tri(b.off, b.seg, v)

    def pick(self, b, val, cls):
        if cls is W.Check:
            val = 0 if b.get(self.prog) else 1
        b.set(self.prog, val)

    def pick_ms(self, b):
        if not b.enabled(self.prog):
            return
        menu = tk.Menu(self.top, tearoff=0)
        d = resources.data()
        if b.osc == 0 and self.prog.mode == P.MODE_DRUMS:
            names = d['drumkit_names'][:self.prog.ms_max(0) + 1]
        else:
            names = [f'{i:03d}: {n}' for i, n in enumerate(d['multisound_names'])]
        cur = b.get(self.prog)
        for i, n in enumerate(names):
            menu.add_radiobutton(label=n, value=i, variable=tk.IntVar(value=cur),
                                 command=lambda i=i: b.set(self.prog, i),
                                 columnbreak=1 if i and i % 29 == 0 else 0)
        menu.tk_popup(self.top.winfo_pointerx(), self.top.winfo_pointery())

    # -- sync from program
    def refresh(self):
        if not self.top.winfo_exists():
            return
        prog = self.prog
        for b, w in self.controls:
            en = b.enabled(prog)
            if isinstance(b, Num):
                bar, text, cntl = w
                lo, hi = b.limits(prog, cntl)
                if (bar.min, bar.max) != (lo, hi):
                    bar.set_range(lo, hi)
                bar.set_value(b.get(prog))
                bar.set_enabled(en)
                text.set(prog.ms_name(b.osc) if isinstance(b, MS) else b.fmt(b.get(prog)))
                text.set_enabled(en)
            elif isinstance(b, Group):
                cur = b.get(prog)
                for r, val in w:
                    r.set(cur == val if not isinstance(r, W.Check) else bool(cur))
                    r.set_enabled(en)
            elif isinstance(b, Tri):
                w.set(prog.tri(b.off, b.seg))
                w.set_enabled(en)
            elif isinstance(b, EG):
                w.redraw()

    def offsets(self):
        offs = set()
        for b in self.binds:
            offs.update(b.offsets)
        return offs

    def cancel(self):
        for off in self.offsets():
            self.prog.data[off] = self.snapshot[off]
        self.prog.changed()
        self.close()

    def close(self):
        if self.refresh in self.prog.listeners:
            self.prog.listeners.remove(self.refresh)
        self.app.dialog_closed(self)
        super().close()


# ------------------------------------------------------- utility dialogs
class ChoiceDialog(DialogWindow):
    """Copy EG / Copy OSC: pick one radio, OK performs the action."""

    def __init__(self, app, dlog_id, title, actions):
        super().__init__(app, dlog_id, title)
        self.actions = actions
        self.choice = 0
        self.add_pictures()
        self.add_static()
        self.radios = []
        for i, item in enumerate(sorted(actions)):
            it = self.items[item]
            self.radios.append(self.surface.add(W.Radio(it['rect'], it['text'],
                                                        lambda i=i: self.select(i))))
        self.select(0)
        self.add_buttons()

    def select(self, i):
        self.choice = i
        for k, r in enumerate(self.radios):
            r.set(k == i)

    def ok(self):
        self.actions[sorted(self.actions)[self.choice]]()
        self.close()


class AboutDialog(DialogWindow):
    def __init__(self, app):
        super().__init__(app, 256, 'About AG SoundEditor')
        self.add_pictures()
        st = self.add_static()
        st[3].set('1.1.1')
        self.surface.bind('<ButtonRelease-1>', lambda e: self.close())


class MidiSetupDialog(DialogWindow):
    """DLOG 512.  The Mac serial port choice becomes MIDI port menus."""

    def __init__(self, app):
        super().__init__(app, 512, 'MIDI Setup')
        s, S = self.surface, app.scale
        midi = app.midi
        self.add_pictures()
        self.add_static()
        self.device = app.prog.device
        self.targets = []
        for item, name in ((8, 'AG-3'), (9, 'AG-10')):
            self.targets.append((s.add(W.Radio(self.items[item]['rect'], name,
                                               lambda n=name: self.set_device(n))), name))
        self.set_device(self.device)
        # Port box (PICT 3000 at 39,24 .. 155,104): output and input menus
        outs = ['(none)'] + midi.output_names()
        ins = ['(none)'] + midi.input_names()
        self.out_var = tk.StringVar(value=midi.out_name or '(none)')
        self.in_var = tk.StringVar(value=midi.in_name or '(none)')
        for i, (label, var, names) in enumerate((('Out', self.out_var, outs), ('In', self.in_var, ins))):
            y = 62 + i * 44
            s.text(30, y, label, 'ports', 'small')
            cb = ttk.Combobox(self.top, textvariable=var, values=names, state='readonly',
                              width=max(8, 9 * S // 2), font=W.font('small', S))
            s.create_window(30 * S, (y + 13) * S, window=cb, anchor='nw', width=70 * S)
        if not midi.available:
            s.text(12, 160, midi.error or 'MIDI unavailable', 'err', 'small', color='#C00000')
        self.add_buttons()

    def set_device(self, name):
        self.device = name
        for r, n in self.targets:
            r.set(n == name)

    def ok(self):
        app = self.app
        app.prog.device = self.device
        try:
            out = self.out_var.get()
            app.midi.open_output(None if out == '(none)' else out)
            inp = self.in_var.get()
            app.midi.open_input(None if inp == '(none)' else inp)
        except Exception as e:  # port busy etc.
            from tkinter import messagebox
            messagebox.showerror('MIDI Setup', f'Could not open MIDI port:\n{e}', parent=self.top)
            return
        app.midi_settings_changed()
        self.close()


class SettingsDialog:
    """Settings window (macOS app menu > Settings...): GUI scale."""

    def __init__(self, app):
        from .app import SCALE_CHOICES
        self.app = app
        S = app.scale
        self.top = tk.Toplevel(app.root)
        self.top.title('Settings')
        self.top.resizable(False, False)
        self.top.transient(app.root)
        w, h = 220, 150
        s = self.surface = W.Surface(self.top, w, h, S)
        s.pack()
        s.text(14, 12, 'Window scale:', 'hdr')
        self.choice = app.scale_choice or 0
        self.radios = []
        for i, (value, label) in enumerate(SCALE_CHOICES):
            if value == 0:
                label = f'{label} ({app.auto_scale()}x)'
            y = 34 + i * 20
            r = s.add(W.Radio([y, 24, y + 18, 200], label, lambda v=value: self.select(v)))
            self.radios.append((r, value))
        self.select(self.choice)
        s.add(W.Button([118, 20, 138, 90], 'Cancel', self.top.destroy))
        s.add(W.Button([118, 130, 138, 200], 'OK', self.ok))
        self.top.bind('<Return>', lambda e: self.ok())
        self.top.bind('<Escape>', lambda e: self.top.destroy())
        rx, ry = app.root.winfo_rootx(), app.root.winfo_rooty()
        self.top.geometry(f'+{rx + 60 * S}+{ry + 40 * S}')

    def select(self, value):
        self.choice = value
        for r, v in self.radios:
            r.set(v == value)

    def ok(self):
        self.top.destroy()
        self.app.set_scale(self.choice or None)
