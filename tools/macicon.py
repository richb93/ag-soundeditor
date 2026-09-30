"""Decode classic Mac icon resources (icl8/ics8 + ICN#/ics# mask) to RGBA images."""
from PIL import Image


def mac_palette():
    """The standard Macintosh 8-bit system palette (clut 8)."""
    steps = (0xFF, 0xCC, 0x99, 0x66, 0x33, 0x00)
    pal = [(r, g, b) for r in steps for g in steps for b in steps][:-1]  # 215 cube colours, no black
    ramp = (0xEE, 0xDD, 0xBB, 0xAA, 0x88, 0x77, 0x55, 0x44, 0x22, 0x11)
    pal += [(v, 0, 0) for v in ramp] + [(0, v, 0) for v in ramp] + [(0, 0, v) for v in ramp]
    pal += [(v, v, v) for v in ramp] + [(0, 0, 0)]
    return pal


def icon(pixels8, mask_list, size):
    """pixels8: size*size bytes (icl8/ics8); mask_list: ICN#/ics# data (icon bitmap + mask)."""
    pal = mac_palette()
    rowbytes = size // 8
    mask = mask_list[size * rowbytes:2 * size * rowbytes]
    img = Image.new('RGBA', (size, size))
    px = img.load()
    for y in range(size):
        for x in range(size):
            on = (mask[y * rowbytes + x // 8] >> (7 - x % 8)) & 1
            px[x, y] = pal[pixels8[y * size + x]] + (255 if on else 0,)
    return img
