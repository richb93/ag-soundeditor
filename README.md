# AG SoundEditor (Python/Tkinter port)

A cross-platform (Windows / macOS / Linux) re-implementation of **KORG AG SoundEditor 1.1.1**
(1995), the Macintosh editor for the KORG Audio Gallery AG-10 / AG-3 sound module. It uses the
original 1-bit artwork and dialog layouts, extracted from `KORG_Audio_Gallery_AG-302J_for_Macintosh.img`.

## Running

```
pip install -r requirements.txt      # mido + python-rtmidi (optional: runs without MIDI too)
python run.py [patch.mid] [--scale 1|2|3|4]
```

Python 3.8+ with Tk 8.6 or newer.

The window is drawn at a whole-number zoom of the original artwork so it stays crisp. Choose
it under **Settings › Scale** (Windows/Linux) or **AG SoundEditor › Settings…** (macOS, Cmd+,):
*Automatic*, *1x*, *2x* or *3x*. The window rebuilds immediately and the choice is saved.
Automatic uses 1x below 900 px of screen height, 3x from 2000 px, and 2x in between.
`--scale N` overrides the saved choice for one run.

* Click a panel in the main window to open its editor (OSC Basic, Pitch EG, VDF MG, Color,
  Modulation, After Touch, VDF 1/2, VDA 1/2, Pitch MG 1/2). The OSC2 panels are greyed out
  unless OSC Mode is *Double*, as in the original.
* Every edit sends the whole program to the module: Bank Select 62/0, Program Change 96 (the
  edit slot), then the program dump.
* **MIDI › MIDI Setup** picks the output and input ports (these replace the Mac Modem/Printer
  choice) and the target (AG-3 allows five ROM drum kits, AG-10 four). Program dumps arriving
  on the input are loaded into the editor.
* **KBD** opens the test keyboard: use the mouse, or keys `A W S E D F T G Y H U J K O L P ;`
  (`Z`/`X` shift the octave). The window also has Velocity, and Reverb/Chorus (CC 91/93 on all
  channels) and Surround (CC 95).
* Click the multisound name in OSC Basic to pick from the full list.
* Files are Standard MIDI Files containing the single SysEx, which is the same format the
  original saved, so `patches/Air_Rider.mid` and `patches/Ephemerals.mid` (from the disk) open
  directly. Raw `.syx` dumps also load.
* Settings (ports, target) are stored in `~/.agse_settings.json`.

## Building a standalone app

Both scripts create a private virtualenv (`.build-venv`), install PyInstaller, build icons
from the original resources (app icon = `icl8/ICN# 128`, document icon = `129`), and run
`packaging/agse.spec`.

| Platform | Command | Output |
|---|---|---|
| macOS | `./build_mac.sh` | `dist/AG SoundEditor.app` and `dist/AG-SoundEditor-<ver>-mac-<arch>.dmg` |
| Windows | `build_windows.bat` | `dist\AGSoundEditor.exe` (single file) |

Notes:
* Build on the platform you are targeting. The Mac app is built for the architecture of the
  Python you use (arm64 or x86_64); set `PYTHON=/path/to/python3` to pick one.
* The Python you build with needs Tk (Homebrew: `brew install python-tk`; Windows: the
  python.org installer with "tcl/tk" ticked). On Windows, use a Python version that has a
  `python-rtmidi` wheel, or have MSVC build tools installed.
* On macOS the `.app` registers as an optional "Open With" editor for `.mid`/`.syx` files,
  with the original document icon. It does not become the default handler.
* The builds are not code-signed. On macOS, the first launch needs right-click › Open (or
  `xattr -dr com.apple.quarantine "AG SoundEditor.app"`). Windows SmartScreen may warn too.

## Reverse-engineered protocol

```
F0 42 3n 34 40 <116 data bytes, KORG 8→7-bit packed> F7        (n = 0)
```

The packing puts one byte holding the MSBs of each group of 7 in front of that group. The data
is 26 common bytes, then two 45-byte oscillator blocks (at offsets 26 and 71). The field names
come from the app's own `TMPL 131` resource, and the per-dialog byte maps from its `PGpr`
resources plus the 68k code (bitfields, tri-state EG switches, multisound number mapping via
`MSNO`). See `agse/program.py` for the full map.

## Layout

| Path | Contents |
|---|---|
| `agse/program.py` | program model, SysEx pack/unpack, SMF read/write |
| `agse/midi_io.py` | MIDI I/O (mido/rtmidi) |
| `agse/widgets.py` | classic Mac controls drawn on a Tk canvas |
| `agse/dialogs.py` | editor dialogs, built from the original DLOG/DITL data |
| `agse/keyboard.py`, `agse/app.py` | keyboard window, main window and menus |
| `agse/assets/` | PNGs rendered from the original PICTs, plus `data.json` (layouts and name tables) |
| `tools/` | `extract_assets.py` regenerates the assets from the `.img`; `pict.py` / `macicon.py` decode PICTs and icons; `make_icons.py` builds `.icns`/`.ico` |
| `packaging/`, `build_mac.sh`, `build_windows.bat` | PyInstaller build |

## Not verified against hardware

This port was tested only through a MIDI loopback, not on a real AG-10. Some details are best
guesses:

* **Edit menu actions.** What *Copy OSC*, *Swap OSC* and *Copy EG* copy is my interpretation.
* **Keyboard.** The octave base and the note-name convention (C4 = 60).
* **EG graphs.** How the envelope graphs are drawn.
* **Fonts.** Text drawn at runtime uses system fonts that stand in for Chicago and Geneva.
