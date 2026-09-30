"""Minimal QuickDraw PICT (v1/v2) renderer -> Pillow RGB image."""
import struct
from PIL import Image, ImageDraw, ImageFont, ImageChops

FONT_FILES = {
    'geneva': '/System/Library/Fonts/Geneva.ttf',
    'monaco': '/System/Library/Fonts/Monaco.ttf',
    'chicago': '/System/Library/Fonts/Geneva.ttf',
    'helvetica': '/System/Library/Fonts/Helvetica.ttc',
    'times': '/System/Library/Fonts/Times.ttc',
    'courier': '/System/Library/Fonts/Courier.ttc',
    'newyork': '/System/Library/Fonts/Times.ttc',
}
FONT_IDS = {0: 'chicago', 1: 'geneva', 2: 'newyork', 3: 'geneva', 4: 'monaco',
            20: 'times', 21: 'helvetica', 22: 'courier'}
OLD_COLORS = {33: (0, 0, 0), 30: (255, 255, 255), 205: (221, 0, 0), 341: (0, 170, 0),
              409: (0, 0, 221), 273: (0, 170, 221), 137: (221, 0, 170), 69: (255, 221, 0)}
BLACK_PAT = b'\xff' * 8


class Reader:
    def __init__(s, d, pos=0):
        s.d, s.p = d, pos
    def u8(s): v = s.d[s.p]; s.p += 1; return v
    def s8(s): v = struct.unpack_from('>b', s.d, s.p)[0]; s.p += 1; return v
    def u16(s): v = struct.unpack_from('>H', s.d, s.p)[0]; s.p += 2; return v
    def s16(s): v = struct.unpack_from('>h', s.d, s.p)[0]; s.p += 2; return v
    def u32(s): v = struct.unpack_from('>I', s.d, s.p)[0]; s.p += 4; return v
    def raw(s, n): v = s.d[s.p:s.p + n]; s.p += n; return v
    def rect(s): t, l, b, r = struct.unpack_from('>hhhh', s.d, s.p); s.p += 8; return (t, l, b, r)
    def pt(s): v, h = struct.unpack_from('>hh', s.d, s.p); s.p += 4; return (h, v)
    def rgb(s): r, g, b = struct.unpack_from('>HHH', s.d, s.p); s.p += 6; return (r >> 8, g >> 8, b >> 8)


def unpackbits(data, n):
    out = bytearray(); i = 0
    while len(out) < n and i < len(data):
        c = data[i]; i += 1
        if c < 128:
            out += data[i:i + c + 1]; i += c + 1
        elif c > 128:
            out += bytes([data[i]]) * (257 - c); i += 1
    return bytes(out[:n])


def unpack_words(data, n):  # packType 3 (16-bit runs)
    out = bytearray(); i = 0
    while len(out) < n and i < len(data):
        c = data[i]; i += 1
        if c < 128:
            out += data[i:i + 2 * (c + 1)]; i += 2 * (c + 1)
        elif c > 128:
            out += data[i:i + 2] * (257 - c); i += 2
    return bytes(out[:n])


class PictRenderer:
    def __init__(self, data):
        self.d = data
        r = Reader(data)
        r.u16()
        self.frame = r.rect()
        t, l, b, rr = self.frame
        self.w, self.h = rr - l, b - t
        self.ox, self.oy = l, t
        self.img = Image.new('RGB', (max(1, self.w), max(1, self.h)), (255, 255, 255))
        self.r = r
        self.fg = (0, 0, 0); self.bg = (255, 255, 255)
        self.pnpat = BLACK_PAT; self.fillpat = BLACK_PAT; self.bkpat = b'\x00' * 8
        self.pnsize = (1, 1); self.pnmode = 8
        self.pnloc = (0, 0); self.txloc = (0, 0)
        self.font = 0; self.face = 0; self.size = 12; self.txmode = 1
        self.fontnames = {}
        self.ovsize = (0, 0)
        self.last = {}
        self.clip = None
        self.origin = (0, 0)
        self.version = 1
        self.pnpix = None; self.fillpix = None; self.bkpix = None

    # ---- coordinate helpers
    def xy(self, h, v):
        return (h - self.ox, v - self.oy)
    def box(self, rect):
        t, l, b, r = rect
        return (l - self.ox, t - self.oy, r - self.ox, b - self.oy)

    # ---- paint through mask
    def pat_image(self, pat, fg, bg, size, pix=None):
        if pix is not None:
            tile = pix
        else:
            tile = Image.new('RGB', (8, 8))
            px = tile.load()
            for y in range(8):
                for x in range(8):
                    px[x, y] = fg if (pat[y] >> (7 - x)) & 1 else bg
        W, H = size
        im = Image.new('RGB', size)
        for y in range(0, H, tile.height):
            for x in range(0, W, tile.width):
                im.paste(tile, (x, y))
        return im

    def apply_clip(self, mask):
        if self.clip is not None:
            mask = ImageChops.multiply(mask, self.clip)
        return mask

    def paint_mask(self, mask, verb, pen=False):
        mask = self.apply_clip(mask)
        size = self.img.size
        if verb == 'invert':
            inv = ImageChops.invert(self.img)
            self.img = Image.composite(inv, self.img, mask)
            return
        if verb == 'erase':
            src = self.pat_image(self.bkpat, self.bg, self.bg, size, self.bkpix) if self.bkpix else \
                self.pat_image(self.bkpat, self.fg, self.bg, size)
            # erase uses background pattern in bg colour
            src = self.pat_image(self.bkpat, self.bg, self.bg, size) if self.bkpat == b'\x00' * 8 else src
            self.img = Image.composite(src, self.img, mask)
            return
        if verb == 'fill':
            src = self.pat_image(self.fillpat, self.fg, self.bg, size, self.fillpix)
        else:  # frame / paint use pen pattern
            src = self.pat_image(self.pnpat, self.fg, self.bg, size, self.pnpix)
        mode = self.pnmode if verb in ('frame', 'paint') else 8
        if mode in (8, 0):  # patCopy
            self.img = Image.composite(src, self.img, mask)
        elif mode in (9, 1):  # patOr: only fg pixels
            patm = self.pat_image(self.pnpat, (255,) * 3, (0,) * 3, size).convert('L')
            m2 = ImageChops.multiply(mask, patm)
            self.img = Image.composite(src, self.img, m2)
        elif mode in (10, 2):  # patXor
            patm = self.pat_image(self.pnpat, (255,) * 3, (0,) * 3, size).convert('L')
            m2 = ImageChops.multiply(mask, patm)
            self.img = Image.composite(ImageChops.invert(self.img), self.img, m2)
        elif mode in (11, 3):  # patBic
            patm = self.pat_image(self.pnpat, (255,) * 3, (0,) * 3, size).convert('L')
            m2 = ImageChops.multiply(mask, patm)
            self.img = Image.composite(Image.new('RGB', size, self.bg), self.img, m2)
        else:
            self.img = Image.composite(src, self.img, mask)

    def new_mask(self):
        return Image.new('L', self.img.size, 0)

    # ---- shapes
    def shape(self, kind, verb, rect, extra=None):
        m = self.new_mask(); dr = ImageDraw.Draw(m)
        x0, y0, x1, y1 = self.box(rect)
        if x1 <= x0 or y1 <= y0:
            return
        pw, ph = self.pnsize
        def draw(bx, fill):
            a0, b0, a1, b1 = bx
            if a1 <= a0 or b1 <= b0:
                return
            a1 -= 1; b1 -= 1
            if kind == 'rect':
                dr.rectangle((a0, b0, a1, b1), fill=fill)
            elif kind == 'rrect':
                rad = min(self.ovsize[0], self.ovsize[1]) // 2
                dr.rounded_rectangle((a0, b0, a1, b1), radius=max(0, rad), fill=fill)
            elif kind == 'oval':
                dr.ellipse((a0, b0, a1, b1), fill=fill)
            elif kind == 'arc':
                st, ang = extra
                s = st - 90; e = st + ang - 90
                if ang < 0: s, e = e, s
                dr.pieslice((a0, b0, a1, b1), s, e, fill=fill)
        if verb == 'frame':
            if pw == 0 or ph == 0:
                return
            draw((x0, y0, x1, y1), 255)
            draw((x0 + pw, y0 + ph, x1 - pw, y1 - ph), 0)
        else:
            draw((x0, y0, x1, y1), 255)
        self.paint_mask(m, verb)

    def poly(self, verb, pts):
        m = self.new_mask(); dr = ImageDraw.Draw(m)
        p = [self.xy(h, v) for h, v in pts]
        if verb == 'frame':
            for a, b in zip(p, p[1:]):
                self.line_on(dr, a, b)
        else:
            if len(p) >= 3:
                dr.polygon(p, fill=255)
        self.paint_mask(m, verb)

    def line_on(self, dr, a, b):
        pw, ph = self.pnsize
        if pw <= 0 or ph <= 0:
            return
        (x0, y0), (x1, y1) = a, b
        if pw == 1 and ph == 1:
            dr.line((x0, y0, x1, y1), fill=255)
            return
        n = max(abs(x1 - x0), abs(y1 - y0), 1)
        for i in range(n + 1):
            x = round(x0 + (x1 - x0) * i / n); y = round(y0 + (y1 - y0) * i / n)
            dr.rectangle((x, y, x + pw - 1, y + ph - 1), fill=255)

    def line(self, p0, p1):
        m = self.new_mask(); dr = ImageDraw.Draw(m)
        self.line_on(dr, self.xy(*p0), self.xy(*p1))
        self.paint_mask(m, 'frame')
        self.pnloc = p1

    # ---- regions
    def read_rgn(self):
        r = self.r
        start = r.p
        size = r.u16()
        bbox = r.rect()
        m = self.new_mask()
        x0, y0, x1, y1 = self.box(bbox)
        if size <= 10:
            ImageDraw.Draw(m).rectangle((x0, y0, x1 - 1, y1 - 1), fill=255)
        else:
            rr = Reader(self.d, r.p)
            state = set()
            lines = []
            while True:
                v = rr.s16()
                if v == 0x7FFF:
                    break
                xs = []
                while True:
                    h = rr.s16()
                    if h == 0x7FFF:
                        break
                    xs.append(h)
                lines.append((v, xs))
            cur = set(); prev_v = None
            dr = ImageDraw.Draw(m)
            for i, (v, xs) in enumerate(lines):
                cur ^= set(xs)
                nv = lines[i + 1][0] if i + 1 < len(lines) else v
                edges = sorted(cur)
                for a, b in zip(edges[0::2], edges[1::2]):
                    if nv > v:
                        dr.rectangle((a - self.ox, v - self.oy, b - 1 - self.ox, nv - 1 - self.oy), fill=255)
        r.p = start + size
        return m, bbox

    # ---- pixmaps
    def read_pixdata(self, direct=False, has_rgn=False):
        r = self.r
        if direct:
            r.u32()
        rowbytes = r.u16()
        is_pix = bool(rowbytes & 0x8000)
        rowbytes &= 0x3FFF
        bounds = r.rect()
        pixsize = 1; ctab = None; packtype = 0; cmpcount = 1
        if is_pix:
            r.u16(); packtype = r.u16(); r.u32(); r.u32(); r.u32()
            r.u16(); pixsize = r.u16(); cmpcount = r.u16(); r.u16()
            r.u32(); r.u32(); r.u32()
            if not direct:
                r.u32(); flags = r.u16(); n = r.u16()
                ctab = {}
                for i in range(n + 1):
                    idx = r.u16(); c = r.rgb()
                    ctab[i if flags & 0x8000 else idx] = c
        src = r.rect(); dst = r.rect(); mode = r.u16()
        mask = None
        if has_rgn:
            mask, _ = self.read_rgn()
        bw = bounds[3] - bounds[1]; bh = bounds[2] - bounds[0]
        rows = []
        for y in range(bh):
            if rowbytes < 8 or packtype == 1:
                rows.append(r.raw(rowbytes))
            else:
                cnt = r.u16() if rowbytes > 250 else r.u8()
                chunk = r.raw(cnt)
                if pixsize == 16 and packtype == 3:
                    rows.append(unpack_words(chunk, rowbytes))
                elif direct and pixsize == 32 and packtype == 4:
                    rows.append(unpackbits(chunk, bw * cmpcount))
                else:
                    rows.append(unpackbits(chunk, rowbytes))
        im = Image.new('RGB', (bw, bh))
        px = im.load()
        opaque = Image.new('L', (bw, bh), 255)
        opx = opaque.load()
        for y, row in enumerate(rows):
            for x in range(bw):
                if pixsize == 1 and not is_pix:
                    bit = (row[x >> 3] >> (7 - (x & 7))) & 1 if (x >> 3) < len(row) else 0
                    px[x, y] = self.fg if bit else self.bg
                    opx[x, y] = 255 if bit else 0
                elif pixsize in (1, 2, 4, 8):
                    per = 8 // pixsize
                    bi = x // per
                    val = (row[bi] >> ((per - 1 - x % per) * pixsize)) & ((1 << pixsize) - 1) if bi < len(row) else 0
                    c = ctab.get(val, (0, 0, 0)) if ctab else (0, 0, 0)
                    px[x, y] = c
                    opx[x, y] = 0 if c == (255, 255, 255) else 255
                elif pixsize == 16:
                    v = (row[2 * x] << 8) | row[2 * x + 1] if 2 * x + 1 < len(row) else 0
                    px[x, y] = (((v >> 10) & 31) * 255 // 31, ((v >> 5) & 31) * 255 // 31, (v & 31) * 255 // 31)
                elif pixsize == 32:
                    if packtype == 4:
                        off = (cmpcount - 3) * bw
                        px[x, y] = (row[off + x], row[off + bw + x], row[off + 2 * bw + x])
                    else:
                        px[x, y] = tuple(row[4 * x + 1:4 * x + 4])
        # crop src from bounds, scale to dst
        sx0 = src[1] - bounds[1]; sy0 = src[0] - bounds[0]
        part = im.crop((sx0, sy0, sx0 + src[3] - src[1], sy0 + src[2] - src[0]))
        opart = opaque.crop((sx0, sy0, sx0 + src[3] - src[1], sy0 + src[2] - src[0]))
        dw, dh = dst[3] - dst[1], dst[2] - dst[0]
        if part.size != (dw, dh) and dw > 0 and dh > 0:
            part = part.resize((dw, dh), Image.NEAREST); opart = opart.resize((dw, dh), Image.NEAREST)
        x, y = self.xy(dst[1], dst[0])
        m = self.new_mask(); canvas = Image.new('RGB', self.img.size)
        canvas.paste(part, (x, y))
        base = mode & 0x3F
        if base in (1, 36, 0x24) or mode == 36:  # srcOr / transparent
            m.paste(opart, (x, y))
        elif base == 2:  # srcXor
            m.paste(opart, (x, y))
            if mask is not None: m = ImageChops.multiply(m, mask)
            m = self.apply_clip(m)
            self.img = Image.composite(ImageChops.invert(self.img), self.img, m)
            return
        elif base == 3:  # srcBic
            m.paste(opart, (x, y))
            canvas = Image.new('RGB', self.img.size, self.bg)
        else:
            m.paste(255, (x, y, x + part.width, y + part.height))
        if mask is not None:
            m = ImageChops.multiply(m, mask)
        m = self.apply_clip(m)
        self.img = Image.composite(canvas, self.img, m)

    def read_pixpat(self):
        r = self.r
        ptype = r.u16(); pat = r.raw(8)
        if ptype == 2:
            c = r.rgb()
            return pat, Image.new('RGB', (8, 8), c)
        # full pixpat: pixmap + ctab + data
        rowbytes = r.u16() & 0x3FFF; bounds = r.rect()
        r.u16(); packtype = r.u16(); r.u32(); r.u32(); r.u32(); r.u16()
        pixsize = r.u16(); r.u16(); r.u16(); r.u32(); r.u32(); r.u32()
        r.u32(); flags = r.u16(); n = r.u16(); ctab = {}
        for i in range(n + 1):
            idx = r.u16(); ctab[i if flags & 0x8000 else idx] = r.rgb()
        bw = bounds[3] - bounds[1]; bh = bounds[2] - bounds[0]
        rows = []
        for y in range(bh):
            if rowbytes < 8:
                rows.append(r.raw(rowbytes))
            else:
                cnt = r.u16() if rowbytes > 250 else r.u8()
                rows.append(unpackbits(r.raw(cnt), rowbytes))
        im = Image.new('RGB', (bw, bh)); px = im.load()
        per = 8 // pixsize
        for y, row in enumerate(rows):
            for x in range(bw):
                val = (row[x // per] >> ((per - 1 - x % per) * pixsize)) & ((1 << pixsize) - 1)
                px[x, y] = ctab.get(val, (0, 0, 0))
        return pat, im

    # ---- text
    def get_font(self):
        name = self.fontnames.get(self.font) or FONT_IDS.get(self.font, 'geneva')
        key = name.lower().replace(' ', '')
        path = FONT_FILES.get(key, FONT_FILES['geneva'])
        size = self.size or 12
        try:
            f = ImageFont.truetype(path, size)
        except Exception:
            f = ImageFont.load_default()
        return f

    def text(self, s):
        s = s.decode('mac_roman', 'replace')
        f = self.get_font()
        m = self.new_mask(); dr = ImageDraw.Draw(m)
        dr.fontmode = '1'
        x, y = self.xy(*self.txloc)
        dr.text((x, y), s, font=f, fill=255, anchor='ls')
        if self.face & 1:
            dr.text((x + 1, y), s, font=f, fill=255, anchor='ls')
        mask = self.apply_clip(m)
        self.img = Image.composite(Image.new('RGB', self.img.size, self.fg), self.img, mask)

    # ---- main loop
    def render(self):
        r = self.r
        v2 = False
        while r.p < len(self.d):
            if v2 and r.p & 1:
                r.p += 1
            if v2:
                op = r.u16()
            else:
                op = r.u8()
                if op == 0x11:
                    ver = r.u8()
                    if ver == 2:
                        v2 = True; r.u8()  # 0xFF
                    continue
            if op == 0x0011:  # version in v2 stream
                r.u16(); continue
            if op == 0x00FF:
                break
            self.op(op, v2)
        return self.img

    def op(self, op, v2):
        r = self.r
        if op == 0x00: return
        if op == 0x01:
            m, bbox = self.read_rgn(); self.clip = m; return
        if op in (0x02,): self.bkpat = r.raw(8); self.bkpix = None; return
        if op == 0x03: self.font = r.u16(); return
        if op == 0x04: self.face = r.u8(); return
        if op == 0x05: self.txmode = r.u16(); return
        if op == 0x06: r.u32(); return
        if op == 0x07: v, h = r.s16(), r.s16(); self.pnsize = (h, v); return
        if op == 0x08: self.pnmode = r.u16(); return
        if op == 0x09: self.pnpat = r.raw(8); self.pnpix = None; return
        if op == 0x0A: self.fillpat = r.raw(8); self.fillpix = None; return
        if op == 0x0B: v, h = r.s16(), r.s16(); self.ovsize = (h, v); return
        if op == 0x0C:
            dh, dv = r.s16(), r.s16(); self.ox += dh; self.oy += dv; return
        if op == 0x0D: self.size = r.u16(); return
        if op == 0x0E: self.fg = OLD_COLORS.get(r.u32(), (0, 0, 0)); return
        if op == 0x0F: self.bg = OLD_COLORS.get(r.u32(), (255, 255, 255)); return
        if op == 0x10: r.raw(8); return
        if op == 0x12: self.bkpat, self.bkpix = self.read_pixpat(); return
        if op == 0x13: self.pnpat, self.pnpix = self.read_pixpat(); return
        if op == 0x14: self.fillpat, self.fillpix = self.read_pixpat(); return
        if op == 0x15: r.u16(); return
        if op == 0x16: r.u16(); return
        if op in (0x17, 0x18, 0x19): return
        if op == 0x1A: self.fg = r.rgb(); return
        if op == 0x1B: self.bg = r.rgb(); return
        if op == 0x1C: return
        if op == 0x1D: r.rgb(); return
        if op == 0x1E: return
        if op == 0x1F: r.rgb(); return
        if op == 0x20:
            p0 = r.pt(); p1 = r.pt(); self.line(p0, p1); return
        if op == 0x21:
            p1 = r.pt(); self.line(self.pnloc, p1); return
        if op == 0x22:
            p0 = r.pt(); dh = r.s8(); dv = r.s8(); self.line(p0, (p0[0] + dh, p0[1] + dv)); return
        if op == 0x23:
            dh = r.s8(); dv = r.s8(); p0 = self.pnloc; self.line(p0, (p0[0] + dh, p0[1] + dv)); return
        if op in (0x24, 0x25, 0x26, 0x27, 0x2D, 0x2E, 0x2F):
            n = r.u16(); r.raw(n); return
        if op == 0x28:
            self.txloc = r.pt(); n = r.u8(); self.text(r.raw(n)); return
        if op == 0x29:
            dh = r.u8(); self.txloc = (self.txloc[0] + dh, self.txloc[1]); n = r.u8(); self.text(r.raw(n)); return
        if op == 0x2A:
            dv = r.u8(); self.txloc = (self.txloc[0], self.txloc[1] + dv); n = r.u8(); self.text(r.raw(n)); return
        if op == 0x2B:
            dh = r.u8(); dv = r.u8(); self.txloc = (self.txloc[0] + dh, self.txloc[1] + dv)
            n = r.u8(); self.text(r.raw(n)); return
        if op == 0x2C:
            n = r.u16(); end = r.p + n; fid = r.u16(); ln = r.u8()
            self.fontnames[fid] = r.raw(ln).decode('mac_roman'); r.p = end; return
        verbs = ['frame', 'paint', 'erase', 'invert', 'fill']
        if 0x30 <= op <= 0x3F:
            if (op & 7) > 4: return
            rect = r.rect() if op < 0x38 else self.last.get('rect')
            self.last['rect'] = rect; self.shape('rect', verbs[op & 7], rect); return
        if 0x40 <= op <= 0x4F:
            if (op & 7) > 4: return
            rect = r.rect() if op < 0x48 else self.last.get('rrect')
            self.last['rrect'] = rect; self.shape('rrect', verbs[op & 7], rect); return
        if 0x50 <= op <= 0x5F:
            if (op & 7) > 4: return
            rect = r.rect() if op < 0x58 else self.last.get('oval')
            self.last['oval'] = rect; self.shape('oval', verbs[op & 7], rect); return
        if 0x60 <= op <= 0x6F:
            if (op & 7) > 4:
                r.u32() if op < 0x68 else None; return
            rect = r.rect() if op < 0x68 else self.last.get('arc')
            st, ang = r.s16(), r.s16()
            self.last['arc'] = rect; self.shape('arc', verbs[op & 7], rect, (st, ang)); return
        if 0x70 <= op <= 0x7F:
            if (op & 7) > 4: return
            if op < 0x78:
                n = r.u16(); r.rect(); pts = [r.pt() for _ in range((n - 10) // 4)]
                self.last['poly'] = pts
            else:
                pts = self.last.get('poly', [])
            self.poly(verbs[op & 7], pts); return
        if 0x80 <= op <= 0x8F:
            if (op & 7) > 4: return
            if op < 0x88:
                m, _ = self.read_rgn(); self.last['rgn'] = m
            else:
                m = self.last['rgn']
            v = verbs[op & 7]
            if v == 'frame':
                # outline of region: mask minus eroded mask
                from PIL import ImageFilter
                er = m.filter(ImageFilter.MinFilter(3))
                m = ImageChops.subtract(m, er)
            self.paint_mask(m, v); return
        if op in (0x90, 0x91, 0x98, 0x99):
            self.read_pixdata(False, op in (0x91, 0x99)); return
        if op in (0x9A, 0x9B):
            self.read_pixdata(True, op == 0x9B); return
        if op == 0xA0: r.u16(); return
        if op == 0xA1: r.u16(); n = r.u16(); r.raw(n); return
        if 0xA2 <= op <= 0xAF or 0x92 <= op <= 0x97 or 0x9C <= op <= 0x9F:
            n = r.u16(); r.raw(n); return
        if 0xB0 <= op <= 0xCF: return
        if 0xD0 <= op <= 0xFE: n = r.u32(); r.raw(n); return
        if op == 0x0C00: r.raw(24); return
        if 0x100 <= op <= 0x7FFF: r.raw(2 * (op >> 8)); return
        if op >= 0x8000 and op <= 0x80FF: return
        if op >= 0x8100: n = r.u32(); r.raw(n); return
        raise ValueError(f'unknown opcode {op:#x} at {r.p}')


def render(data):
    return PictRenderer(data).render()


if __name__ == '__main__':
    import sys
    render(open(sys.argv[1], 'rb').read()).save(sys.argv[2])
