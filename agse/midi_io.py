"""MIDI output/input via mido + python-rtmidi (optional)."""
import queue

try:
    import mido
except ImportError:  # the editor still works offline
    mido = None


class Midi:
    def __init__(self):
        self.out = None
        self.inp = None
        self.out_name = None
        self.in_name = None
        self.incoming = queue.Queue()
        self.error = None if mido else 'mido / python-rtmidi not installed'

    @property
    def available(self):
        return mido is not None

    def output_names(self):
        if not mido:
            return []
        try:
            return mido.get_output_names()
        except Exception as e:  # backend missing
            self.error = str(e)
            return []

    def input_names(self):
        if not mido:
            return []
        try:
            return mido.get_input_names()
        except Exception as e:
            self.error = str(e)
            return []

    def open_output(self, name):
        if self.out:
            self.out.close()
            self.out = None
        self.out_name = None
        if mido and name:
            self.out = mido.open_output(name)
            self.out_name = name

    def open_input(self, name):
        if self.inp:
            self.inp.close()
            self.inp = None
        self.in_name = None
        if mido and name:
            self.inp = mido.open_input(name, callback=self.incoming.put)
            self.in_name = name

    def send_bytes(self, data):
        """Send one complete MIDI message given as raw bytes."""
        if not self.out:
            return
        self.out.send(mido.Message.from_bytes(list(data)))

    def send(self, *status_and_data):
        self.send_bytes(bytes(status_and_data))

    # ----- the messages AG SoundEditor sends
    def send_program(self, program):
        # select the edit slot, then dump the program (CODE 2, 0x077C / 0x07BA)
        self.send(0xB0, 0x00, 0x3E)
        self.send(0xB0, 0x20, 0x00)
        self.send(0xC0, 0x60)
        self.send_bytes(program.sysex())

    def note(self, note, velocity):
        if 0 <= note < 128:
            self.send(0x90, note, velocity)

    def all_notes_off(self):
        for ch in range(16):
            self.send(0xB0 | ch, 0x78, 0x00)

    def reverb(self, value):
        for ch in range(16):
            self.send(0xB0 | ch, 0x5B, value)

    def chorus(self, value):
        for ch in range(16):
            self.send(0xB0 | ch, 0x5D, value)

    def surround(self, value):
        self.send(0xB0, 0x5F, value)

    def close(self):
        self.open_output(None)
        self.open_input(None)
