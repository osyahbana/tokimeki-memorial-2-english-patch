"""Pictures with Japanese text (menu buttons, labels): find, export, re-import.

How they are stored (docs/game-internals.md section 15; verified on the
name-entry buttons, Disc 1):

  * Texture data lives in CDPACK in packets, and inside code modules as bare
    lz1 streams (u24 size + 0 byte + stream; the name-entry module embeds the
    buttons it uses). Packets: a stream of, each with a 32-byte
    header (u32 type, u32 a, u32 b, 20 zero bytes) and a payload:
      0x100 / 0x104  lz1 (u24 size + 1 byte, then the stream) -> 8 / 16 KiB
      0x204          lz2 -> 16 KiB
      0x004          raw
    A decoded chunk is a block of VRAM rows (e.g. the name-entry buttons:
    8 KiB = 128 rows of 64 bytes, a 4-bit 128x128 texture at VRAM x 960).
    The game streams it to VRAM through a queue (EXE 0x8002E6F0) and
    decodes with lz1 (0x8002E950) or lz2 (0x8001A830).
  * Code modules also hold image records: u32 2, u16 x, y, w, h (w in
    16-bit units; x, y were 0 in the ones checked), then an lz2 stream of w*h*2 bytes, the
    next record at the next 4-byte boundary (the main screen's stat labels,
    Disc 2 sectors 11403 and 12419, are two of these; the screen draws from
    them, not from the lz1 packet with the same labels).
  * Palettes (CLUTs) come from the code modules and are separate; a picture
    may be drawn with several of them (each button has its own colour).

The tool works from a DuckStation save state taken while the picture is on
screen: it finds which chunk is in VRAM and where, exports it as an indexed
PNG (pixel values = palette indices, shown with a palette from VRAM), and
puts an edited PNG back: the indices are packed, compressed again
(tools/lz1enc.py, tools/lz2enc.py) and written over the old payload, which must not grow.

usage:
  python tools/pictures.py find   <disc.bin> <state.sav> [--range FIRST,LAST]   (sectors to search for bare lz1 streams and image records too)
  python tools/pictures.py export <disc.bin> <state.sav> <chunk> <out.png> [--clut X,Y] [--bpp 4|8]
  python tools/pictures.py import <image.bin> <chunk> <in.png> [--bpp 4|8]     (patches the image in place)
<chunk> is "sector:offset" of a packet header, "s<sector>:<offset>" of a
bare lz1 stream or "r<sector>:<offset>" of an image record, as printed by find. The same picture can exist in several
places; the one the game uses is the one in VRAM after loading from the
patched disc, so patch every copy find lists for the same VRAM position.
"""
import hashlib
import re
import struct
import sys
from functools import lru_cache

import cdimage
import compression as C

RAM_OFF = 0x1A62               # in the decompressed DuckStation state
VRAM_OFF = 0x201A5C            # fallback only: state_vram looks for the GPU-VRAM tag
TYPES = {0x100: "lz1", 0x104: "lz1", 0x204: "lz2", 0x004: "raw"}
HDR = re.compile(rb"(?:\x00\x01|\x04\x01|\x04\x02|\x04\x00)\x00\x00.{8}\x00{20}", re.S)


def state_vram(path):
    import numpy as np
    import zstandard
    d = open(path, "rb").read()
    starts = [m.start() for m in re.finditer(rb"\x28\xb5\x2f\xfd", d)]
    raw = zstandard.ZstdDecompressor().decompressobj().decompress(d[starts[-1]:])
    k = raw.find(b"GPU-VRAM")             # the VRAM follows this tag; where it is varies
    off = k + 8 if k >= 0 else VRAM_OFF   # between states (0x201A5C and 0x201DDC seen)
    return np.frombuffer(raw[off:off + 1024 * 1024], dtype="<u2").reshape(512, 1024)


class Chunk:
    def __init__(self, sector, offset, kind, a, b, data, payload_len, room):
        self.sector, self.offset, self.kind, self.a, self.b = sector, offset, kind, a, b
        self.data = data                # decoded bytes
        self.payload_len = payload_len  # bytes of the compressed payload (incl. its 4-byte header)
        self.room = room                # bytes up to the next packet header

    stream = False                  # True: a bare lz1 stream (no packet header)
    record = False                  # True: an image record (12-byte header + lz2)

    @property
    def name(self):
        return ("r%d:%d" if self.record else "s%d:%d" if self.stream else "%d:%d") % (self.sector, self.offset)

    @property
    def payload_at(self):
        return self.sector * 2048 + self.offset + (12 if self.record else 0 if self.stream else 32)

    @property
    def limit(self):
        """Most bytes a new payload may take (a record may use its padding)."""
        return (self.payload_len + 3) & ~3 if self.record else self.payload_len

    @property
    def key(self):
        return "pic-" + hashlib.sha1(self.data).hexdigest()[:10]


def scan(data, lo=0, hi=None):
    """All packets of the disc's user data (optionally a byte range)."""
    hdrs = []
    for m in HDR.finditer(data, lo, hi or len(data)):
        if m.start() % 4 == 0:
            t, a, b = struct.unpack_from("<3I", data, m.start())
            hdrs.append((m.start(), t, a, b))
    out = []
    for i, (p, t, a, b) in enumerate(hdrs):
        nxt = hdrs[i + 1][0] if i + 1 < len(hdrs) else p + 0x10000
        kind = TYPES[t]
        try:
            if kind == "lz1":
                dec, n = C.lz1(data, p + 32, limit=1 << 16)
            elif kind == "lz2":
                dec, n = C.lz2(data, p + 32, limit=1 << 16)
            else:
                dec, n = data[p + 32:min(nxt, p + 32 + 0x4000)], 0
        except Exception:
            continue
        if len(dec) < 512:
            continue
        out.append(Chunk(p // 2048, p % 2048, kind, a, b, dec, n, nxt - p - 32))
    return out


def scan_streams(data, lo_sector, hi_sector):
    """Header-less lz1 streams (u24 size + 0 byte + stream) at 4-byte aligned
    offsets in a sector range: code modules embed their own textures this way
    (the name-entry buttons the game actually uses are one, Disc 1 2067:952)."""
    out = []
    p, end = lo_sector * 2048, min(len(data), hi_sector * 2048)
    while p < end - 8:
        sz = data[p] | data[p + 1] << 8 | data[p + 2] << 16
        if 64 < sz < 0x8000 and data[p + 3] == 0:
            try:
                dec, n = C.lz1(data, p, limit=1 << 16)
            except Exception:
                dec = b""
            if len(dec) >= 2048 and len(dec) % 512 == 0:
                c = Chunk(p // 2048, p % 2048, "lz1", 0, 0, dec, n, n)
                c.stream = True
                out.append(c)
                p += (n + 3) & ~3
                continue
        p += 4
    return out


def scan_records(data, lo_sector, hi_sector):
    """Image records (u32 2, u16 x, y, w, h, lz2 stream) at 4-byte aligned
    offsets in a sector range."""
    out = []
    p, end = lo_sector * 2048, min(len(data), hi_sector * 2048)
    while p < end - 16:
        c = record_at(data, p)
        if c:
            out.append(c)
            p += (12 + c.payload_len + 3) & ~3
        else:
            p += 4
    return out


def all_records(data, key=None):
    """Every image record on the disc (optionally only those decoding to key)."""
    out = []
    for m in re.finditer(rb"\x02\x00\x00\x00", data):
        p = m.start()
        if p % 4 or p + 12 > len(data):
            continue
        x, y, w, h = struct.unpack_from("<4H", data, p + 4)
        if not (x < 1024 and y < 512 and 8 <= w <= 1024 - x and 8 <= h <= 512 - y):
            continue
        c = record_at(data, p)
        if c and (key is None or c.key == key):
            out.append(c)
    return out


def record_at(data, p):
    if data[p:p + 4] != b"\2\0\0\0":
        return None
    x, y, w, h = struct.unpack_from("<4H", data, p + 4)
    size = w * h * 2
    if not (x < 1024 and y < 512 and 0 < w <= 1024 - x and 0 < h <= 512 - y and size >= 512):
        return None
    try:
        dec, n = C.lz2(data, p + 12, limit=size)
    except Exception:
        return None
    if len(dec) != size:
        return None
    c = Chunk(p // 2048, p % 2048, "lz2", x | y << 16, w | h << 16, dec, n, n)
    c.record = True
    return c


def find(data, vram, chunks=None):
    """[(chunk, x, y, row_bytes)] for chunks whose rows are in VRAM now."""
    vb = vram.view("u1").reshape(512, 2048)
    rows = [bytes(r) for r in vb]
    found = []
    for c in chunks or scan(data):
        for w in (32, 64, 128, 256):
            if len(c.data) % w:
                continue
            probe = [k for k in range(min(len(c.data) // w, 64)) if len(set(c.data[k * w:k * w + w])) > 3][:4]
            if len(probe) < 2:
                continue
            k0 = probe[0]
            seg = c.data[k0 * w:k0 * w + w]
            for y, r in enumerate(rows):
                x = r.find(seg)
                if x < 0 or x % 2:
                    continue
                y0 = y - k0
                if y0 < 0 or not all(0 <= y0 + k < 512 and rows[y0 + k][x:x + w] == c.data[k * w:k * w + w] for k in probe):
                    continue
                found.append((c, x // 2, y0, w))
                break
            else:
                continue
            break
    return found


def pixels(chunk, w, bpp):
    import numpy as np
    b = np.frombuffer(chunk.data, np.uint8).reshape(-1, w)
    if bpp == 8:
        return b.copy()
    px = np.zeros((b.shape[0], w * 2), np.uint8)
    px[:, 0::2] = b & 15
    px[:, 1::2] = b >> 4
    return px


def pack(px, bpp):
    import numpy as np
    px = np.asarray(px, np.uint8)
    if bpp == 8:
        return px.tobytes()
    if px.max() > 15:
        raise ValueError("4-bit picture uses palette index > 15")
    return (px[:, 0::2] | (px[:, 1::2] << 4)).astype(np.uint8).tobytes()


def palette(vram, clut, n):
    x, y = clut
    pal = []
    for c in vram[y, x:x + n]:
        c = int(c)
        pal += [(c & 31) << 3, (c >> 5 & 31) << 3, (c >> 10 & 31) << 3]
    return pal


def export(chunk, w, out, vram=None, clut=None, bpp=4):
    from PIL import Image
    px = pixels(chunk, w, bpp)
    im = Image.fromarray(px, "P")
    n = 16 if bpp == 4 else 256
    if vram is not None and clut:
        pal = palette(vram, clut, n)
    else:
        pal = sum(([v * 255 // (n - 1)] * 3 for v in range(n)), [])
    im.putpalette(pal + [0] * (768 - len(pal)))
    im.save(out)


@lru_cache(maxsize=32)
def _compress_picture(kind, raw):
    """Reuse identical translated textures across discs; verify each encoding."""
    if kind == 'lz1':
        import lz1enc
        encoded = lz1enc.compress(raw)
        decoded, _ = C.lz1(encoded, 0, limit=len(raw))
    elif kind == 'lz2':
        import lz2enc
        encoded = lz2enc.compress(raw)
        decoded, _ = C.lz2(encoded, 0, limit=len(raw))
    else:
        raise ValueError('unsupported picture compression: ' + kind)
    if bytes(decoded) != raw:
        raise ValueError('compressed picture failed round-trip validation')
    return encoded


def encode(chunk, png, w, bpp=4):
    """New payload bytes (compressed) for an edited PNG."""
    from PIL import Image
    im = Image.open(png)
    if im.mode != "P":
        raise ValueError("%s: must be an indexed (palette) PNG; edit with palette indices kept" % png)
    import numpy as np
    px = np.array(im)
    if px.shape != pixels(chunk, w, bpp).shape:
        raise ValueError("%s: size %s, expected %s" % (png, px.shape[::-1], pixels(chunk, w, bpp).shape[::-1]))
    raw = pack(px, bpp)
    z = _compress_picture(chunk.kind, bytes(raw))
    if len(z) > chunk.limit:
        raise ValueError("compressed picture is %d bytes, room for %d: simplify the edit" % (len(z), chunk.limit))
    return z


def write(f, chunk, z):
    """Overwrite chunk's payload in an open image file; old bytes beyond the
    new stream are kept zero (the decoder stops at its own size field)."""
    p = chunk.payload_at
    span = max(chunk.payload_len, len(z))
    assert len(z) <= chunk.limit
    sec0, n = p // 2048, -(-(p % 2048 + span) // 2048)
    old = cdimage.read_user_data(f, sec0, n)
    new = bytearray(old)
    o = p - sec0 * 2048
    new[o:o + span] = z + b"\0" * (span - len(z))
    return cdimage.write_changed(f, sec0, old, bytes(new))


def apply_manifest(path, folder):
    """Patch every picture listed in <folder>/pictures.json into the disc
    image at path (in place). Manifest entries:
        "pic-6bd6dd34c6": {"png": "name_buttons.png", "width": 64, "bpp": 4,
                           "at": ["s2067:952"], "what": "..."}
    A location is used only if the picture there still decodes to that key
    (so the same manifest works on every disc that has the picture);
    "packets" / "records" mean every packet / image record on the disc
    that holds it.
    Returns ([applied names], [errors])."""
    import json
    import os
    import extract_scripts as X
    mf = os.path.join(folder, "pictures.json")
    if not os.path.exists(mf):
        return [], []
    entries = json.load(open(mf, encoding="utf-8"))
    data = X.read_user_data(path)
    done, errors = [], []
    with open(path, "r+b") as f:
        allpk = None
        for key, e in entries.items():
            cands = []
            for loc in e["at"]:
                if loc == "packets":           # every packet on the disc with this picture
                    if allpk is None:
                        allpk = scan(data)
                    cands += [c for c in allpk if c.key == key]
                    continue
                if loc == "records":           # every image record on the disc with it
                    cands += all_records(data, key)
                    continue
                try:
                    cands.append(_chunk_at(data, loc))
                except SystemExit:
                    continue
            for c in cands:
                if c.key != key:
                    continue
                loc = c.name
                try:
                    z = encode(c, os.path.join(folder, e["png"]), e.get("width", 64), e.get("bpp", 4))
                except ValueError as ex:
                    errors.append("%s %s: %s" % (key, loc, ex))
                    continue
                write(f, c, z)
                done.append("%s@%s" % (key, loc))
    return done, errors


def _chunk_at(data, name):
    s, o = map(int, name.lstrip("sr").split(":"))
    p = s * 2048 + o
    if name.startswith("r"):
        cs = [c for c in [record_at(data, p)] if c]
    elif name.startswith("s"):
        # An explicit location must be decoded directly. A plausible overlapping
        # stream earlier in the sector can make the heuristic scanner skip it.
        # apply_manifest still requires the decoded picture's content hash.
        cs = []
        if 0 <= p <= len(data) - 8 and p % 4 == 0:
            try:
                dec, n = C.lz1(data, p, limit=1 << 16)
                if n > 0 and p + n <= len(data) and len(dec) >= 512 and len(dec) % 512 == 0:
                    c = Chunk(s, o, "lz1", 0, 0, dec, n, n)
                    c.stream = True
                    cs = [c]
            except (ValueError, IndexError, AssertionError):
                pass
    else:
        cs = scan(data, p, p + 0x10000)
    for c in cs:
        if c.sector == s and c.offset == o:
            return c
    raise SystemExit("no packet at %s" % name)


def main(a):
    import extract_scripts as X
    opts = {}
    for k in ("--clut", "--bpp", "--width", "--range"):
        if k in a:
            i = a.index(k)
            opts[k] = a[i + 1]
            del a[i:i + 2]
    bpp = int(opts.get("--bpp", 4))
    cmd = a[0]
    if cmd == "find":
        data = X.read_user_data(a[1])
        vram = state_vram(a[2])
        chunks = scan(data)
        if "--range" in opts:
            lo, hi = map(int, opts["--range"].split(","))
            chunks += scan_streams(data, lo, hi) + scan_records(data, lo, hi)
        for c, x, y, w in find(data, vram, chunks):
            print("%-12s %s %-3s %5d bytes  VRAM x=%d y=%d, %d bytes/row (%d px at 4 bit), %d rows; room for %d compressed bytes"
                  % (c.name, c.key, c.kind, len(c.data), x, y, w, w * 2, len(c.data) // w, c.payload_len))
    elif cmd == "export":
        data = X.read_user_data(a[1])
        vram = state_vram(a[2])
        c = _chunk_at(data, a[3])
        hits = [h for h in find(data, vram, [c])]
        w = int(opts.get("--width", hits[0][3] if hits else 64))
        clut = tuple(map(int, opts["--clut"].split(","))) if "--clut" in opts else None
        export(c, w, a[4], vram, clut, bpp)
        print("wrote %s (%s, %d bytes/row)" % (a[4], c.key, w))
    elif cmd == "import":
        data = X.read_user_data(a[1])
        c = _chunk_at(data, a[2])
        w = int(opts.get("--width", 64))
        z = encode(c, a[3], w, bpp)
        with open(a[1], "r+b") as f:
            secs = write(f, c, z)
        print("%s: %d -> %d compressed bytes, sectors %s" % (c.name, c.payload_len, len(z), secs))
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
