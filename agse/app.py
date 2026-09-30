"""AG SoundEditor main window (DLOG 768) and application logic."""
import json
import os
import queue
import sys
import time
import tkinter as tk
from tkinter import filedialog, messagebox

from . import dialogs
from . import program as P
from . import resources
from . import widgets as W
from .keyboard import KeyboardWindow
from .midi_io import Midi

SETTINGS = os.path.join(os.path.expanduser('~'), '.agse_settings.json')

SCALE_CHOICES = [(0, 'Automatic'), (1, '1x'), (2, '2x'), (3, '3x')]
MODES = ['Single', 'Double', 'Drums', '---']
OCTAVES = {-2: "32'", -1: "16'", 0: "8'", 1: "4'"}
OSC_SELECT = ['Off', 'OSC1', 'OSC2', 'Both']
KBD_MODES = ['Off', 'Low', 'High', 'All']

# overview panels: DITL 768 item -> (dialog key, osc)
PANELS = {1: ('osc', 0), 2: ('vdfmg', 0), 3: ('pitcheg', 0), 4: ('joystick', 0), 5: ('aftertouch', 0),
          6: ('color', 0), 7: ('vdf', 0), 8: ('vda', 0), 9: ('pitchmg', 0),
          10: ('vdf', 1), 11: ('vda', 1), 12: ('pitchmg', 1)}
OSC2_PICTS = {10: (144, 149), 11: (146, 150), 12: (148, 151)}   # (active, greyed)


class MiniTri(W.Widget):
    """+ / - mark inside one of the overview's 9x9 EG time boxes."""
    value = 0

    def draw(self):
        t, l, b, r = self.rect
        s = self.surface
        if self.value > 0:
            s.fill(l + 4, t + 2, l + 5, t + 7, W.BLACK, self.tag)
        if self.value:
            s.fill(l + 2, t + 4, l + 7, t + 5, W.BLACK, self.tag)


def enable_windows_dpi_awareness():
    """Stop Windows bitmap-stretching (blurring) the window on high-DPI displays;
    the app does its own crisp integer scaling instead."""
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass


class App:
    def __init__(self, scale=None, path=None):
        enable_windows_dpi_awareness()
        W.reset_caches()   # images/fonts belong to one Tk interpreter
        self.root = tk.Tk()
        self.root.withdraw()
        self.settings = self.load_settings()
        # --scale on the command line overrides the saved Settings choice for this run
        self.scale_choice = scale if scale else self.settings.get('scale')  # None = automatic
        self.scale = self.scale_choice or self.auto_scale()
        self.prog = P.Program()
        self.prog.device = self.settings.get('device', 'AG-10')
        self.midi = Midi()
        self.path = None
        self.dirty = False
        self.undo_stack = []
        self.clipboard = None
        self.dialogs = {}
        self.keyboard = None
        self.kbd_state = dict(velocity=64, reverb=0, chorus=0, surround=0)
        self._send_job = None
        self._last_send = 0.0
        self._receiving = False
        self.mod = 'Command' if sys.platform == 'darwin' else 'Control'

        self.build_menu()
        self.build_window()
        self.set_icon()
        self.prog.listeners.append(self.program_changed)
        self.open_saved_ports()
        if path:
            self.load_file(path)
        self.update_title()
        self.refresh()
        self.root.deiconify()
        self.root.after(50, self.poll_midi)

    # ------------------------------------------------------------ settings
    def load_settings(self):
        try:
            with open(SETTINGS) as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def save_settings(self):
        self.settings.update(out=self.midi.out_name, inp=self.midi.in_name, device=self.prog.device)
        try:
            with open(SETTINGS, 'w') as f:
                json.dump(self.settings, f, indent=1)
        except OSError:
            pass

    def open_saved_ports(self):
        try:
            if self.settings.get('out') in self.midi.output_names():
                self.midi.open_output(self.settings['out'])
            if self.settings.get('inp') in self.midi.input_names():
                self.midi.open_input(self.settings['inp'])
        except Exception:
            pass

    # ---------------------------------------------------------------- menu
    def build_menu(self):
        root, mod = self.root, self.mod
        acc = 'Cmd' if mod == 'Command' else 'Ctrl'
        mb = tk.Menu(root)
        d = resources.data()['menu']

        def add(menu, label, cmd, key=None):
            menu.add_command(label=label, command=cmd, accelerator=f'{acc}+{key}' if key else None)
            if key:
                root.bind_all(f'<{mod}-{key.lower()}>', lambda e: cmd())

        if sys.platform == 'darwin':
            apple = tk.Menu(mb, name='apple', tearoff=0)
            apple.add_command(label=d[1]['items'][0][0], command=self.about)
            mb.add_cascade(menu=apple)
            root.createcommand('tk::mac::Quit', self.quit)
            # Finder "Open With" / drag onto the Dock icon
            root.createcommand('::tk::mac::OpenDocument', self.open_documents)
            # defining this adds the standard Settings... (Cmd+,) item to the app menu
            root.createcommand('::tk::mac::ShowPreferences', self.settings_dialog)
        f = tk.Menu(mb, tearoff=0)
        add(f, 'New', self.new, 'N')
        add(f, 'Open...', self.open, 'O')
        add(f, 'Close', self.close_front, 'W')
        f.add_separator()
        add(f, 'Save', self.save, 'S')
        f.add_command(label='Save As...', command=self.save_as)
        f.add_separator()
        add(f, 'Quit' if sys.platform == 'darwin' else 'Exit', self.quit, 'Q')
        mb.add_cascade(label='File', menu=f)
        e = tk.Menu(mb, tearoff=0)
        add(e, 'Undo', self.undo, 'Z')
        e.add_separator()
        add(e, 'Cut', self.cut, 'X')
        add(e, 'Copy', self.copy, 'C')
        add(e, 'Paste', self.paste, 'V')
        add(e, 'Clear', self.clear, 'B')
        e.add_separator()
        e.add_command(label='Copy EG...', command=self.copy_eg)
        e.add_command(label='Copy OSC Parameters...', command=self.copy_osc)
        e.add_command(label='Swap OSC Parameters', command=self.swap_osc)
        mb.add_cascade(label='Edit', menu=e)
        m = tk.Menu(mb, tearoff=0)
        add(m, 'MIDI Setup...', self.midi_setup, 'M')
        m.add_separator()
        m.add_command(label='All Notes Off', command=self.midi.all_notes_off)
        m.add_command(label='Send Program', command=self.send_now)
        m.add_command(label='Keyboard...', command=self.show_keyboard)
        mb.add_cascade(label='MIDI', menu=m)
        if sys.platform != 'darwin':
            st = tk.Menu(mb, tearoff=0)
            scale_menu = tk.Menu(st, tearoff=0)
            self.scale_var = tk.IntVar(value=self.scale_choice or 0)
            for value, label in SCALE_CHOICES:
                scale_menu.add_radiobutton(label=label, value=value, variable=self.scale_var,
                                           command=lambda: self.set_scale(self.scale_var.get() or None))
            st.add_cascade(label='Scale', menu=scale_menu)
            mb.add_cascade(label='Settings', menu=st)
            h = tk.Menu(mb, tearoff=0)
            h.add_command(label=d[1]['items'][0][0], command=self.about)
            mb.add_cascade(label='Help', menu=h)
        root.config(menu=mb)

    def set_icon(self):
        self._icons = [tk.PhotoImage(file=os.path.join(resources.ASSETS, f'icon_app_{n}.png'))
                       for n in (32, 16)]
        if sys.platform != 'darwin':   # on macOS the .app bundle icon is used
            self.root.iconphoto(True, *self._icons)

    # ------------------------------------------------------------- scaling
    def auto_scale(self):
        h = self.root.winfo_screenheight()
        return 3 if h >= 2000 else 2 if h >= 900 else 1

    def settings_dialog(self):
        dialogs.SettingsDialog(self)

    def set_scale(self, choice):
        """choice: None for automatic, or 1/2/3.  Rebuilds the windows at the new zoom."""
        self.scale_choice = choice
        self.settings['scale'] = choice
        self.save_settings()
        if hasattr(self, 'scale_var'):
            self.scale_var.set(choice or 0)
        scale = choice or self.auto_scale()
        if scale == self.scale:
            return
        reopen_keyboard = self.keyboard is not None
        open_panels = list(self.dialogs)
        self.close_dialogs()
        if self.keyboard:
            self.keyboard.close()
        self.scale = scale
        self.surface.destroy()
        self.status.destroy()
        self.build_window()
        self.refresh()
        for key, osc in open_panels:
            self.open_panel(key, osc, 0)
        if reopen_keyboard:
            self.show_keyboard()

    def open_documents(self, *paths):
        if paths and self.confirm_discard('opening another file'):
            self.close_dialogs()
            self.load_file(paths[0])

    # -------------------------------------------------------- main window
    def build_window(self):
        root, S = self.root, self.scale
        root.resizable(False, False)
        root.protocol('WM_DELETE_WINDOW', self.quit)
        dl = resources.dlog(768)
        t, l, b, r = dl['rect']
        items = resources.ditl(768)
        s = self.surface = W.Surface(root, r - l, b - t, S)
        s.pack()
        self.status = tk.Label(root, anchor='w', font=W.font('small', S), bg=W.WHITE, bd=0,
                               padx=4 * S, pady=S)
        self.status.pack(fill='x')
        self.panels = {}
        for n, (key, osc) in PANELS.items():
            it = items[n]
            pid = it['id'] if n not in OSC2_PICTS else OSC2_PICTS[n][0]
            rect = it['rect']
            self.panels[n] = s.add(W.Picture(rect, pid, lambda k=key, o=osc, n=n: self.open_panel(k, o, n)))
        kb = items[15]
        s.add(W.Button(kb['rect'], kb['text'], self.show_keyboard))

        self.vals = []   # (Text widget, fn(prog) -> str, osc2-only)

        def val(panel_rect, x_right, row_top, fn, osc2=False, align='right', x_left=None):
            pt, pl = panel_rect[0], panel_rect[1]
            rect = [pt + row_top - 2, pl + (x_left if x_left is not None else 2), pt + row_top + 10,
                    pl + x_right]
            w = s.add(W.Text(rect, '', kind='small', align=align))
            self.vals.append((w, fn, osc2))

        g = lambda off: (lambda p: str(p.get(off)))  # noqa: E731
        R = {n: items[n]['rect'] for n in items}
        # OSC Basic (item 1)
        val(R[1], 79, 15, lambda p: MODES[p.mode])
        val(R[1], 79, 26, lambda p: 'On' if p.data[0] & 8 else 'Off')
        val(R[1], 80, 50, lambda p: p.ms_name(0), align='left', x_left=2)
        val(R[1], 79, 62, g(P.OSC_BASE[0] + P.O_VDA_LEVEL))
        val(R[1], 79, 73, lambda p: OCTAVES.get(p.get(P.OSC1_OCT), '?'))
        val(R[1], 80, 97, lambda p: p.ms_name(1), True, align='left', x_left=2)
        val(R[1], 79, 109, g(P.OSC_BASE[1] + P.O_VDA_LEVEL), True)
        val(R[1], 79, 120, lambda p: OCTAVES.get(p.get(P.OSC2_OCT), '?'), True)
        val(R[1], 79, 133, g(P.INTERVAL), True)
        val(R[1], 79, 144, g(P.DETUNE), True)
        val(R[1], 79, 155, g(P.DELAY_START), True)
        # Pitch EG (item 3)
        val(R[3], 79, 63, g(P.PEG_LEVEL_VS))
        val(R[3], 79, 74, g(P.PEG_TIME_VS))
        val(R[3], 79, 85, g(P.OSC_BASE[0] + P.O_PEG_INT))
        val(R[3], 79, 96, g(P.OSC_BASE[1] + P.O_PEG_INT), True)
        # VDF MG (item 2)
        val(R[2], 79, 26, g(P.VDF_MG_FREQ))
        val(R[2], 79, 37, g(P.VDF_MG_INT))
        val(R[2], 79, 48, g(P.VDF_MG_DELAY))
        val(R[2], 79, 59, lambda p: OSC_SELECT[p.get_bits(P.VDF_MG_WAVE, 0x60, 5)])
        # Color (item 6)
        val(R[6], 79, 15, g(P.OSC_BASE[0] + P.O_COLOR_INT))
        val(R[6], 79, 26, g(P.OSC_BASE[0] + P.O_COLOR_VS))
        val(R[6], 79, 37, g(P.OSC_BASE[1] + P.O_COLOR_INT), True)
        val(R[6], 79, 48, g(P.OSC_BASE[1] + P.O_COLOR_VS), True)
        # Modulation / After Touch (items 4, 5)
        val(R[4], 79, 15, g(P.JS_VDF_SWEEP))
        val(R[4], 79, 26, g(P.MOD2_VDF_MG))
        for i, off in enumerate((P.AT_BEND, P.AT_VDF_CUTOFF, P.AT_VDF_MG, P.AT_VDA_AMP)):
            val(R[5], 79, 15 + 11 * i, g(off))
        # per oscillator panels
        self.tris = []
        for osc, (vdf, vda, pmg) in enumerate(((7, 8, 9), (10, 11, 12))):
            b = P.OSC_BASE[osc]
            o2 = osc == 1
            for row, off in ((17, P.O_VDF_CUTOFF), (28, P.O_VDF_EG_INT), (63, None), (74, P.O_VDF_KBD),
                             (85, P.O_VDF_EGT_KBD)):
                fn = (lambda p, b=b: KBD_MODES[p.get_bits(b + P.O_KBD_MODE, 3, 0)]) if off is None \
                    else g(b + off)
                val(R[vdf], 80, row, fn, o2)
            val(R[vdf], 80, 52, lambda p, b=b: P.note_name(p.data[b + P.O_VDF_KEY] & 0x7F), o2)
            val(R[vdf], 161, 74, g(b + P.O_VDF_EGI_VS), o2)
            val(R[vdf], 161, 85, g(b + P.O_VDF_EGT_VS), o2)
            val(R[vda], 80, 30, lambda p, b=b: P.note_name(p.data[b + P.O_VDA_KEY] & 0x7F), o2)
            val(R[vda], 80, 41, lambda p, b=b: KBD_MODES[p.get_bits(b + P.O_KBD_MODE, 0x0C, 2)], o2)
            val(R[vda], 80, 52, g(b + P.O_VDA_KBD), o2)
            val(R[vda], 80, 63, g(b + P.O_VDA_EGT_KBD), o2)
            val(R[vda], 161, 52, g(b + P.O_VDA_VS), o2)
            val(R[vda], 161, 63, g(b + P.O_VDA_EGT_VS), o2)
            for row, off in ((26, P.O_PMG_FREQ), (37, P.O_PMG_INT), (48, P.O_PMG_DELAY), (59, P.O_PMG_FADE)):
                val(R[pmg], 80, row, g(b + off), o2)
            val(R[pmg], 161, 15, lambda p, b=b: 'On' if p.data[b + P.O_PMG_WAVE] & 0x80 else 'Off', o2)
            for row, off in ((26, P.O_PMG_FREQ_KBD), (37, P.O_PMG_ATMOD1_FREQ), (48, P.O_PMG_AT_INT),
                             (59, P.O_PMG_MOD1_INT)):
                val(R[pmg], 161, row, g(b + off), o2)
            # EG time switch boxes (kbd tracking left, velocity sense right)
            for panel, row, kbd_bits, vs_bits in ((vdf, 107, P.O_VDF_KBD_BITS, P.O_VDF_VS_BITS),
                                                  (vda, 85, P.O_VDA_KBD_BITS, P.O_VDA_VS_BITS)):
                pt, pl = R[panel][0], R[panel][1]
                for j, x in enumerate((8, 26, 44, 62)):
                    for dx, bits in ((0, kbd_bits), (83, vs_bits)):
                        box = s.add(MiniTri([pt + row, pl + x + dx, pt + row + 9, pl + x + dx + 9]))
                        self.tris.append((box, b + bits, j, o2))
        # EG graphs (user items 16-20) and waveform icons (21-24)
        self.graphs = []
        for n, kind, osc in ((16, 'pitch', 0), (17, 'vdf', 0), (18, 'vda', 0), (19, 'vdf', 1), (20, 'vda', 1)):
            gr = s.add(W.Graph(R[n], lambda k=kind, o=osc: dialogs.eg_points(self.prog, k, P.OSC_BASE[o]),
                               bipolar=kind != 'vda', inset=1))
            self.graphs.append((gr, osc == 1))
        self.icons = {n: s.add(W.Picture(R[n], 2000)) for n in (21, 22, 23, 24)}

    def refresh(self):
        p = self.prog
        dbl = p.osc2_active
        for n, (active, grey) in OSC2_PICTS.items():
            pic = self.panels[n]
            pid = active if dbl else grey
            if pic.pict_id != pid:
                pic.pict_id = pid
                pic.redraw()
        for w, fn, o2 in self.vals:
            w.visible = dbl or not o2
            w.set(fn(p))
            w.redraw()
        for box, off, j, o2 in self.tris:
            box.visible = dbl or not o2
            box.value = p.tri(off, j)
            box.redraw()
        for gr, o2 in self.graphs:
            gr.visible = dbl or not o2
            gr.redraw()
        ic = self.icons
        ic[21].visible = p.mode == P.MODE_DRUMS
        ic[21].pict_id = 2005
        ic[22].pict_id = 2000 + min(4, p.get_bits(P.VDF_MG_WAVE, 7, 0))
        ic[23].pict_id = 2000 + min(4, p.get_bits(P.OSC_BASE[0] + P.O_PMG_WAVE, 7, 0))
        ic[24].pict_id = 2000 + min(4, p.get_bits(P.OSC_BASE[1] + P.O_PMG_WAVE, 7, 0))
        ic[24].visible = dbl
        for w in ic.values():
            w.redraw()
        # the drum-kit badge sits over the start of the OSC1 name
        for w, fn, _ in self.vals[2:3]:
            w.rect[1] = ic[21].rect[1] + (36 if p.mode == P.MODE_DRUMS else 0) - 1
            w.redraw()
        midi = self.midi
        port = midi.out_name or 'no MIDI output (MIDI > MIDI Setup...)'
        extra = f'   In: {midi.in_name}' if midi.in_name else ''
        self.status.config(text=f'{p.device}   Out: {port}{extra}')

    # -------------------------------------------------------------- events
    def program_changed(self):
        self.dirty = True
        self.update_title()
        self.refresh()
        if not self._receiving:
            self.schedule_send()

    # A dump is 139 bytes, about 45 ms on a 31.25 kbaud MIDI cable, so sends are
    # limited to one per SEND_INTERVAL; the last change is always sent.
    SEND_INTERVAL = 0.1

    def schedule_send(self):
        if self._send_job is None:
            wait = self._last_send + self.SEND_INTERVAL - time.monotonic()
            self._send_job = self.root.after(max(1, int(wait * 1000)), self.send_now)

    def send_now(self):
        if self._send_job is not None:
            self.root.after_cancel(self._send_job)
            self._send_job = None
        self._last_send = time.monotonic()
        try:
            self.midi.send_program(self.prog)
        except Exception as e:
            self.status.config(text=f'MIDI error: {e}')

    def poll_midi(self):
        while True:
            try:
                msg = self.midi.incoming.get_nowait()
            except queue.Empty:
                break
            if msg.type != 'sysex':
                continue
            data = P.Program.parse_sysex(msg.data)
            # ignore our own dump echoed back (e.g. In and Out on the same bus)
            if data and data != self.prog.snapshot():
                self.push_undo()
                # the device already holds this program: load it without sending it back
                self._receiving = True
                try:
                    self.prog.load(data)
                finally:
                    self._receiving = False
                self.status.config(text='Program received from MIDI In')
        self.root.after(50, self.poll_midi)

    def open_panel(self, key, osc, n):
        if osc == 1 and not self.prog.osc2_active:
            self.root.bell()
            return
        dk = (key, osc)
        if dk in self.dialogs:
            self.dialogs[dk].top.lift()
            return
        self.push_undo()
        dlg = dialogs.ParamDialog(self, key, osc)
        self.dialogs[dk] = dlg

    def dialog_closed(self, dlg):
        self.dialogs.pop((dlg.key, dlg.osc), None)

    def close_front(self):
        focus = self.root.focus_get()
        top = focus.winfo_toplevel() if focus else None
        for dlg in list(self.dialogs.values()) + ([self.keyboard] if self.keyboard else []):
            if dlg.top == top:
                dlg.ok()
                return

    def show_keyboard(self):
        if self.keyboard:
            self.keyboard.top.lift()
        else:
            self.keyboard = KeyboardWindow(self)

    def midi_setup(self):
        dialogs.MidiSetupDialog(self)

    def midi_settings_changed(self):
        self.save_settings()
        self.refresh()
        for dlg in self.dialogs.values():
            dlg.refresh()
        self.send_now()

    def about(self):
        dialogs.AboutDialog(self)

    # ---------------------------------------------------------------- undo
    def push_undo(self):
        snap = self.prog.snapshot()
        if not self.undo_stack or self.undo_stack[-1] != snap:
            self.undo_stack.append(snap)
            del self.undo_stack[:-50]

    def undo(self):
        if self.undo_stack:
            snap = self.undo_stack.pop()
            if snap == self.prog.snapshot() and self.undo_stack:
                snap = self.undo_stack.pop()
            self.prog.load(snap)

    def cut(self):
        self.copy()
        self.clear()

    def copy(self):
        self.clipboard = self.prog.snapshot()

    def paste(self):
        if self.clipboard:
            self.push_undo()
            self.prog.load(self.clipboard)

    def clear(self):
        self.push_undo()
        self.prog.load(resources.data()['init_program'])

    def copy_eg(self):
        p = self.prog

        def act(which, src, dst):
            return lambda: (self.push_undo(), p.copy_eg(which, src, dst))
        dialogs.ChoiceDialog(self, 1027, 'Copy EG', {3: act('vdf', 0, 1), 4: act('vdf', 1, 0),
                                                     5: act('vda', 0, 1), 6: act('vda', 1, 0)})

    def copy_osc(self):
        p = self.prog
        dialogs.ChoiceDialog(self, 1028, 'Copy OSC', {
            3: lambda: (self.push_undo(), p.copy_osc(0, 1)),
            4: lambda: (self.push_undo(), p.copy_osc(1, 0))})

    def swap_osc(self):
        self.push_undo()
        self.prog.swap_osc()

    # --------------------------------------------------------------- files
    def update_title(self):
        name = os.path.basename(self.path) if self.path else resources.data()['strings'][100]
        self.root.title(f"AG SoundEditor - {name}{' *' if self.dirty else ''}")

    def confirm_discard(self, action):
        if not self.dirty:
            return True
        name = os.path.basename(self.path) if self.path else 'Untitled'
        ans = messagebox.askyesnocancel(
            'AG SoundEditor', f'Do you want to save the changes to "{name}" before {action}?',
            parent=self.root)
        if ans is None:
            return False
        if ans:
            return self.save()
        return True

    def close_dialogs(self):
        for dlg in list(self.dialogs.values()):
            dlg.ok()

    def new(self):
        if self.confirm_discard('closing'):
            self.close_dialogs()
            self.push_undo()
            self.prog.load(resources.data()['init_program'])
            self.path, self.dirty = None, False
            self.update_title()

    def open(self):
        if not self.confirm_discard('opening another file'):
            return
        path = filedialog.askopenfilename(parent=self.root, title='Open Program Data',
                                          filetypes=[('Program data', '*.mid *.midi *.syx'),
                                                     ('All files', '*')])
        if path:
            self.close_dialogs()
            self.load_file(path)

    def load_file(self, path):
        try:
            with open(path, 'rb') as f:
                data = P.Program.parse_file(f.read())
        except (OSError, ValueError) as e:
            messagebox.showerror('AG SoundEditor', f'Could not load "{os.path.basename(path)}".\n{e}',
                                 parent=self.root)
            return
        self.push_undo()
        self.prog.load(data)
        self.path, self.dirty = path, False
        self.update_title()

    def save(self):
        if not self.path:
            return self.save_as()
        try:
            self.prog.save(self.path)
        except OSError as e:
            messagebox.showerror('AG SoundEditor', str(e), parent=self.root)
            return False
        self.dirty = False
        self.update_title()
        return True

    def save_as(self):
        strings = resources.data()['strings']
        path = filedialog.asksaveasfilename(parent=self.root, title=strings[101], defaultextension='.mid',
                                            filetypes=[('Standard MIDI File', '*.mid')],
                                            initialfile=os.path.basename(self.path) if self.path
                                            else strings[100] + '.mid')
        if not path:
            return False
        self.path = path
        return self.save()

    def quit(self):
        if self.confirm_discard('quitting'):
            try:
                self.midi.all_notes_off()
            except Exception:
                pass
            self.save_settings()
            self.midi.close()
            self.root.destroy()

    def run(self):
        self.root.mainloop()
