"""Build .icns (macOS) and .ico (Windows) files from the original 16/32 px icons.

Larger sizes are pixel-doubled (nearest neighbour) so the 1995 artwork stays crisp.
Output: build/icons/{AGSoundEditor,AGDocument}.{icns,ico}
"""
import os
import shutil
import subprocess
import sys
import tempfile

from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
ASSETS = os.path.join(ROOT, 'agse', 'assets')
OUT = os.path.join(ROOT, 'build', 'icons')


def sized(kind, size):
    """16 px uses the original ics8 artwork, everything else scales the 32 px icl8."""
    src = Image.open(os.path.join(ASSETS, f'icon_{kind}_{16 if size <= 16 else 32}.png')).convert('RGBA')
    return src if src.width == size else src.resize((size, size), Image.NEAREST)


def make_icns(kind, path):
    if sys.platform == 'darwin' and shutil.which('iconutil'):
        tmp = tempfile.mkdtemp()
        iconset = os.path.join(tmp, 'icon.iconset')
        os.mkdir(iconset)
        for s in (16, 32, 128, 256, 512):
            sized(kind, s).save(os.path.join(iconset, f'icon_{s}x{s}.png'))
            sized(kind, s * 2).save(os.path.join(iconset, f'icon_{s}x{s}@2x.png'))
        subprocess.run(['iconutil', '-c', 'icns', iconset, '-o', path], check=True)
        shutil.rmtree(tmp)
    else:  # Pillow's writer works everywhere
        big = sized(kind, 1024)
        big.save(path, append_images=[sized(kind, s) for s in (16, 32, 64, 128, 256, 512)])


def make_ico(kind, path):
    sizes = (16, 24, 32, 48, 64, 128, 256)
    sized(kind, 256).save(path, sizes=[(s, s) for s in sizes],
                          append_images=[sized(kind, s) for s in sizes[:-1]])


def main():
    os.makedirs(OUT, exist_ok=True)
    for kind, name in (('app', 'AGSoundEditor'), ('doc', 'AGDocument')):
        make_icns(kind, os.path.join(OUT, name + '.icns'))
        make_ico(kind, os.path.join(OUT, name + '.ico'))
    print('icons written to', OUT)


if __name__ == '__main__':
    main()
