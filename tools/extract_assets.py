"""Regenerate agse/assets from the original KORG AG-302J Macintosh floppy image.

Pipeline:
  1. read the HFS floppy (machfs) -> "Install AudioGallery" (Compact Pro SEA)
  2. unpack it with `unar` (The Unarchiver CLI) -> "AG SoundEditor" resource fork
  3. render every PICT to PNG (tools/pict.py) and export the dialog layouts,
     name tables and init program to data.json

Usage:
  pip install machfs rsrcfork pillow
  brew install unar        # or: apt install unar / choco install unar
  python tools/extract_assets.py KORG_Audio_Gallery_AG-302J_for_Macintosh.img

Note: PICT text is rendered with system fonts (Geneva etc. on macOS); the
bundled PNGs were generated on macOS.
"""
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile

import machfs
import rsrcfork

sys.path.insert(0, os.path.dirname(__file__))
import macicon  # noqa: E402
import pict  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, '..', 'agse', 'assets')


def pstr(b):
    return b[1:1 + b[0]].decode('mac_roman')


def parse_cntl(d):
    t, l, b, r, val, vis, fill, mx, mn, proc, ref = struct.unpack('>hhhhhBBhhhi', d[:22])
    return dict(rect=[t, l, b, r], value=val, max=mx, min=mn, procID=proc, refCon=ref,
                title=pstr(d[22:]))


def parse_ditl(d):
    n = struct.unpack('>h', d[:2])[0] + 1
    p = 2
    items = []
    for k in range(n):
        t, l, b, r = struct.unpack('>hhhh', d[p + 4:p + 12])
        typ = d[p + 12]
        ln = d[p + 13]
        data = d[p + 14:p + 14 + ln]
        p += 14 + ln + (ln & 1)
        it = dict(n=k + 1, rect=[t, l, b, r], type=typ & 0x7F, disabled=bool(typ & 0x80))
        if it['type'] in (4, 5, 6, 8, 16):
            it['text'] = data.decode('mac_roman')
        if it['type'] in (7, 32, 64):
            it['id'] = struct.unpack('>h', data[:2])[0]
        items.append(it)
    return items


def parse_dlog(d):
    t, l, b, r, proc, vis, _, goaway, _, ref, ditl = struct.unpack('>hhhhhBBBBih', d[:20])
    return dict(rect=[t, l, b, r], procID=proc, goAway=bool(goaway), ditl=ditl, title=pstr(d[20:]))


def parse_menu(d):
    p = 14
    title = pstr(d[p:])
    p += 1 + d[p]
    items = []
    while d[p]:
        s = pstr(d[p:])
        p += 1 + d[p]
        _icon, key, _mark, _style = d[p:p + 4]
        p += 4
        items.append([s, chr(key) if key else ''])
    return dict(title=title, items=items)


def words(d):
    n = struct.unpack('>H', d[:2])[0]
    return list(struct.unpack(f'>{n}H', d[2:2 + 2 * n]))


def main(img):
    tmp = tempfile.mkdtemp()
    try:
        vol = machfs.Volume()
        vol.read(open(img, 'rb').read())
        sea = vol['Install AudioGallery']
        sea_path = os.path.join(tmp, 'install.cpt')
        open(sea_path, 'wb').write(sea.data)
        subprocess.run(['unar', '-q', '-f', '-o', tmp, sea_path], check=True)
        app = os.path.join(tmp, 'AudioGallery', 'AG SoundEditor', 'AG SoundEditor')
        rsrc = open(app + '/..namedfork/rsrc', 'rb').read() if os.path.exists(app + '/..namedfork/rsrc') \
            else open(app + '.rsrc', 'rb').read()
        rf = rsrcfork.ResourceFile(__import__('io').BytesIO(rsrc))
        get = lambda t, i: rf[t.encode('mac_roman')][i].data  # noqa: E731

        os.makedirs(ASSETS, exist_ok=True)
        for i in rf[b'PICT']:
            pict.render(get('PICT', i)).save(os.path.join(ASSETS, f'pict_{i}.png'))

        # icon families: 128 = application (FREF 'APPL'), 129 = document ('Midi')
        for i, kind in ((128, 'app'), (129, 'doc')):
            macicon.icon(get('icl8', i), get('ICN#', i), 32).save(os.path.join(ASSETS, f'icon_{kind}_32.png'))
            macicon.icon(get('ics8', i), get('ics#', i), 16).save(os.path.join(ASSETS, f'icon_{kind}_16.png'))

        data = dict(dlog={}, ditl={}, cntl={}, menu={})
        for i in rf[b'DLOG']:
            data['dlog'][i] = parse_dlog(get('DLOG', i))
        for i in rf[b'DITL']:
            data['ditl'][i] = parse_ditl(get('DITL', i))
        for i in rf[b'CNTL']:
            data['cntl'][i] = parse_cntl(get('CNTL', i))
        for i in rf[b'MENU']:
            data['menu'][i] = parse_menu(get('MENU', i))
        ms = get('NMTB', 1000)
        data['multisound_names'] = [ms[i:i + 10].decode('mac_roman').rstrip() for i in range(0, len(ms), 10)]
        dk = get('NMTB', 1001)
        data['drumkit_names'] = [dk[i:i + 10].decode('mac_roman').rstrip() for i in range(0, len(dk), 10)]
        data['msno_index_to_number'] = words(get('MSNO', 1000))
        data['msno_number_to_index'] = words(get('MSNO', 1001))
        data['init_program'] = list(get('IPRG', 1000))
        data['pgpr'] = {i: list(get('PGpr', i)) for i in rf[b'PGpr']}
        kb = []
        for i in (1000, 1001):
            d = get('KBDT', i)
            n = struct.unpack('>H', d[:2])[0]
            keys = []
            for j in range(n):
                v = struct.unpack('>10h', d[2 + j * 20:22 + j * 20])
                keys.append(dict(area=list(v[0:4]), invert=list(v[4:8]), key=v[8], link=v[9]))
            kb.append(keys)
        data['kbdt'] = kb
        data['kbdg'] = list(struct.unpack('>3h', get('KBDG', 1000)))
        s = get('STR#', 104)
        n = struct.unpack('>H', s[:2])[0]
        names, p = [], 2
        for _ in range(n):
            names.append(pstr(s[p:]).strip())
            p += 1 + s[p]
        data['key_names'] = names
        data['strings'] = {i: pstr(get('STR ', i)) for i in rf[b'STR ']}
        with open(os.path.join(ASSETS, 'data.json'), 'w') as f:
            json.dump(data, f, indent=1)
        # sample patches shipped with the editor
        for name in ('Air Rider', 'Ephemerals'):
            src = os.path.join(tmp, 'AudioGallery', 'AG SoundEditor', name)
            dst = os.path.join(HERE, '..', 'patches', name.replace(' ', '_') + '.mid')
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy(src, dst)
        print('assets written to', os.path.normpath(ASSETS))
    finally:
        shutil.rmtree(tmp)


if __name__ == '__main__':
    main(sys.argv[1])
