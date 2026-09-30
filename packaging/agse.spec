# PyInstaller spec for AG SoundEditor.
#   macOS  : dist/AG SoundEditor.app   (windowed .app bundle)
#   Windows: dist/AGSoundEditor.exe    (single-file windowed .exe)
# Run through build_mac.sh / build_windows.bat, which create the icons first.
import os
import sys

ROOT = os.path.abspath(os.path.join(SPECPATH, '..'))
sys.path.insert(0, ROOT)
from agse import __version__  # noqa: E402

NAME = 'AG SoundEditor'
ICONS = os.path.join(ROOT, 'build', 'icons')

a = Analysis(
    [os.path.join(ROOT, 'run.py')],
    pathex=[ROOT],
    datas=[(os.path.join(ROOT, 'agse', 'assets'), os.path.join('agse', 'assets'))]
    + ([(os.path.join(ICONS, 'AGDocument.icns'), '.')] if sys.platform == 'darwin' else []),
    # mido picks its backend at runtime, so PyInstaller cannot see it
    hiddenimports=['mido.backends.rtmidi', 'rtmidi'],
    excludes=['PIL', 'numpy'],   # Pillow is only needed by the build tools
)
pyz = PYZ(a.pure)

if sys.platform == 'darwin':
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=NAME, console=False,
              icon=os.path.join(ICONS, 'AGSoundEditor.icns'))
    coll = COLLECT(exe, a.binaries, a.datas, name=NAME)
    app = BUNDLE(
        coll,
        name=NAME + '.app',
        icon=os.path.join(ICONS, 'AGSoundEditor.icns'),
        bundle_identifier='local.agsoundeditor',
        version=__version__,
        info_plist={
            'CFBundleName': NAME,
            'CFBundleDisplayName': NAME,
            'CFBundleShortVersionString': __version__,
            'NSHighResolutionCapable': True,
            'NSHumanReadableCopyright': 'Original software (c) 1995 KORG Inc.',
            # allow "Open With" for program files without claiming them as default
            'CFBundleDocumentTypes': [{
                'CFBundleTypeName': 'AG Program Data',
                'CFBundleTypeRole': 'Editor',
                'LSHandlerRank': 'Alternate',
                'CFBundleTypeExtensions': ['mid', 'midi', 'syx'],
                'CFBundleTypeIconFile': 'AGDocument.icns',
            }],
        },
    )
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='AGSoundEditor', console=False,
              icon=os.path.join(ICONS, 'AGSoundEditor.ico'))
