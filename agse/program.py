"""AG-10 program (edit buffer) model, SysEx encoding and file I/O.

Reverse-engineered from AG SoundEditor 1.1.1 (KORG, 1995):

* A program is 116 bytes: 26 common bytes followed by two 45-byte
  oscillator blocks (OSC1 at 26, OSC2 at 71).  Field names come from the
  application's own TMPL 131 resource.
* It is sent as  F0 42 3n 34 40 <116 bytes, KORG 7-bit packed> F7
  (n = MIDI channel, always 0 in the original), preceded by
  Bank Select 62/0 + Program Change 96 on channel 1 (the edit slot).
* Files are Standard MIDI Files holding that single SysEx event.
"""
from . import resources

SIZE = 116
OSC_BASE = (26, 71)

KORG_ID = 0x42
MODEL_ID = 0x34
FUNC_PROGRAM_DUMP = 0x40

# ---- common block
OSC_MODE = 0            # bits 0-1: 0 Single, 1 Double, 2 Drums; bit 3: Hold
OSC1_MS, OSC1_OCT, OSC2_MS, OSC2_OCT = 1, 2, 3, 4
INTERVAL, DETUNE, DELAY_START = 5, 6, 7
PEG_SL, PEG_AT, PEG_AL, PEG_DT, PEG_RT, PEG_RL = 8, 9, 10, 11, 12, 13
PEG_TIME_VS, PEG_LEVEL_VS = 14, 15
VDF_MG_WAVE = 16        # bits 0-2 waveform, bits 5-6 OSC select
VDF_MG_FREQ, VDF_MG_DELAY, VDF_MG_INT = 17, 18, 19
AT_BEND, AT_VDF_CUTOFF, AT_VDF_MG, AT_VDA_AMP = 20, 21, 22, 23
JS_VDF_SWEEP, MOD2_VDF_MG = 24, 25

# ---- per-oscillator block (offsets relative to OSC_BASE[n])
O_PEG_INT = 0
O_PMG_WAVE = 1          # bits 0-2 waveform, bit 7 key sync
O_PMG_FREQ, O_PMG_DELAY, O_PMG_FADE, O_PMG_INT = 2, 3, 4, 5
O_PMG_FREQ_KBD, O_PMG_AT_INT, O_PMG_MOD1_INT, O_PMG_ATMOD1_FREQ = 6, 7, 8, 9
O_VDF_CUTOFF, O_VDF_KEY, O_VDF_KBD, O_VDF_EG_INT = 10, 11, 12, 13
O_VDF_EGT_KBD, O_VDF_EGT_VS, O_VDF_EGI_VS = 14, 15, 16
O_VDF_EG = 17           # AT AL DT BP ST SL RT RL (8 bytes)
O_VDA_LEVEL, O_VDA_KEY, O_VDA_KBD, O_VDA_VS = 25, 26, 27, 28
O_VDA_EGT_KBD, O_VDA_EGT_VS = 29, 30
O_VDA_EG = 31           # AT AL DT BP ST SL RT (7 bytes)
O_VDF_KBD_BITS, O_VDF_VS_BITS, O_VDA_KBD_BITS, O_VDA_VS_BITS = 38, 39, 40, 41
O_COLOR_INT, O_COLOR_VS = 42, 43
O_KBD_MODE = 44         # bits 0-1 VDF (Off/Low/High/All), bits 2-3 VDA

MODE_SINGLE, MODE_DOUBLE, MODE_DRUMS = 0, 1, 2


def s8(v):
    v &= 0xFF
    return v - 256 if v >= 128 else v


class Program:
    def __init__(self, data=None):
        self.data = bytearray(data if data is not None else resources.data()['init_program'])
        assert len(self.data) == SIZE
        self.listeners = []
        self.device = 'AG-10'   # 'AG-3' allows 5 drum kits

    # ------------------------------------------------------------------ raw
    def get(self, off):
        return s8(self.data[off])

    def set(self, off, value, notify=True):
        self.data[off] = value & 0xFF
        if notify:
            self.changed()

    def get_bits(self, off, mask, shift):
        return (self.data[off] & mask) >> shift

    def set_bits(self, off, mask, shift, value, notify=True):
        self.data[off] = (self.data[off] & ~mask & 0xFF) | ((value << shift) & mask)
        if notify:
            self.changed()

    def changed(self):
        for fn in list(self.listeners):
            fn()

    def load(self, data):
        self.data[:] = bytes(data)
        self.changed()

    def snapshot(self):
        return bytes(self.data)

    # -------------------------------------------------------- derived views
    @property
    def mode(self):
        return self.data[OSC_MODE] & 3

    @property
    def osc2_active(self):
        return self.mode == MODE_DOUBLE

    def ms_index(self, osc):
        """UI index of the multisound (or raw drum-kit number for OSC1 in Drums mode)."""
        off = OSC1_MS if osc == 0 else OSC2_MS
        raw = self.data[off]
        if osc == 0 and self.mode == MODE_DRUMS:
            return raw
        table = resources.data()['msno_number_to_index']
        return table[raw] if raw < len(table) else 0

    def set_ms_index(self, osc, index):
        off = OSC1_MS if osc == 0 else OSC2_MS
        if osc == 0 and self.mode == MODE_DRUMS:
            self.set(off, index)
        else:
            self.set(off, resources.data()['msno_index_to_number'][index])

    def ms_max(self, osc):
        if osc == 0 and self.mode == MODE_DRUMS:
            return 4 if self.device == 'AG-3' else 3
        return len(resources.data()['msno_index_to_number']) - 1

    def ms_name(self, osc):
        d = resources.data()
        i = self.ms_index(osc)
        if osc == 0 and self.mode == MODE_DRUMS:
            names = d['drumkit_names']
            return names[i] if i < len(names) else f'Kit {i + 1}'
        names = d['multisound_names']
        return f'{i:03d}: {names[i]}' if i < len(names) else f'{i:03d}'

    def tri(self, off, seg):
        """EG-time tri-state for segment 0..3 (AT DT ST RT): 0 off, +1, -1."""
        b = self.data[off] >> seg
        return {0x00: 0, 0x01: 1, 0x10: 0, 0x11: -1}[b & 0x11]

    def set_tri(self, off, seg, value, notify=True):
        bits = {0: 0x00, 1: 0x01, -1: 0x11}[value] << seg
        mask = 0x11 << seg
        self.data[off] = (self.data[off] & ~mask & 0xFF) | bits
        if notify:
            self.changed()

    # ------------------------------------------------------------- editing
    def copy_osc(self, src, dst):
        a, b = OSC_BASE[src], OSC_BASE[dst]
        self.data[b:b + 45] = self.data[a:a + 45]
        self.data[(OSC1_MS, OSC2_MS)[dst]] = self.data[(OSC1_MS, OSC2_MS)[src]]
        self.data[(OSC1_OCT, OSC2_OCT)[dst]] = self.data[(OSC1_OCT, OSC2_OCT)[src]]
        self.changed()

    def swap_osc(self):
        a, b = OSC_BASE
        blk = self.data[a:a + 45]
        self.data[a:a + 45] = self.data[b:b + 45]
        self.data[b:b + 45] = blk
        for x, y in ((OSC1_MS, OSC2_MS), (OSC1_OCT, OSC2_OCT)):
            self.data[x], self.data[y] = self.data[y], self.data[x]
        self.changed()

    def copy_eg(self, which, src, dst):
        """which: 'vdf' (8 bytes + time bits) or 'vda' (7 bytes + time bits)."""
        a, b = OSC_BASE[src], OSC_BASE[dst]
        if which == 'vdf':
            spans = [(O_VDF_EG, 8), (O_VDF_KBD_BITS, 2)]
        else:
            spans = [(O_VDA_EG, 7), (O_VDA_KBD_BITS, 2)]
        for o, n in spans:
            self.data[b + o:b + o + n] = self.data[a + o:a + o + n]
        self.changed()

    # --------------------------------------------------------------- SysEx
    def sysex(self, channel=0):
        """Complete program-dump SysEx message including F0/F7."""
        return bytes([0xF0, KORG_ID, 0x30 | (channel & 15), MODEL_ID, FUNC_PROGRAM_DUMP]) \
            + pack7(self.data) + b'\xF7'

    # --------------------------------------------------------------- files
    def to_smf(self):
        body = self.sysex()[1:]
        ev = b'\x00\xF0' + varlen(len(body)) + body + b'\x00\xFF\x2F\x00'
        return (b'MThd' + (6).to_bytes(4, 'big') + b'\x00\x00\x00\x01\x00\x60'
                + b'MTrk' + len(ev).to_bytes(4, 'big') + ev)

    def save(self, path):
        with open(path, 'wb') as f:
            f.write(self.to_smf())

    @staticmethod
    def parse_file(blob):
        """Return 116 program bytes from an SMF or raw .syx file."""
        i = 0
        while True:
            i = blob.find(bytes([KORG_ID]), i)
            if i < 0:
                raise ValueError('File format is invalid')
            if i + 4 <= len(blob) and blob[i + 1] & 0xF0 == 0x30 and blob[i + 2] == MODEL_ID \
                    and blob[i + 3] == FUNC_PROGRAM_DUMP:
                end = blob.find(b'\xF7', i)
                if end < 0:
                    raise ValueError('File format is invalid')
                data = unpack7(blob[i + 4:end])
                if len(data) < SIZE:
                    raise ValueError('File format is invalid')
                return data[:SIZE]
            i += 1

    @staticmethod
    def parse_sysex(msg):
        """msg without F0/F7 (as delivered by mido); returns bytes or None."""
        if len(msg) > 4 and msg[0] == KORG_ID and msg[1] & 0xF0 == 0x30 and msg[2] == MODEL_ID \
                and msg[3] == FUNC_PROGRAM_DUMP:
            data = unpack7(bytes(msg[4:]))
            if len(data) >= SIZE:
                return data[:SIZE]
        return None


def pack7(data):
    """KORG 8->7 bit packing: each group of up to 7 bytes is preceded by their MSBs."""
    out = bytearray()
    for i in range(0, len(data), 7):
        grp = data[i:i + 7]
        msb = 0
        for j, b in enumerate(grp):
            msb |= ((b >> 7) & 1) << j
        out.append(msb)
        out += bytes(b & 0x7F for b in grp)
    return bytes(out)


def unpack7(data):
    out = bytearray()
    for i in range(0, len(data), 8):
        grp = data[i:i + 8]
        msb = grp[0]
        for j, b in enumerate(grp[1:]):
            out.append(b | (0x80 if (msb >> j) & 1 else 0))
    return bytes(out)


def varlen(n):
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.append(0x80 | (n & 0x7F))
        n >>= 7
    return bytes(reversed(out))


def note_name(n):
    names = resources.data()['key_names']
    return f'{names[n % 12]}{n // 12 - 1}'
