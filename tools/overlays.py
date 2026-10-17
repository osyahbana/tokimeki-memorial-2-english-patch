"""Code overlays that carry script packs (phone calls etc., Discs 1-5).

Verified on all five discs (docs/game-internals.md section 10.2):

  * A resource table at disc sector 541 + 0x440 (loaded at RAM 0x80010C40)
    lists 8 overlays as (u32 RAM address & 0x7FFFFF, u32 sector); all load
    at 0x8013DD50.
  * Their sizes are in the EXE at 0x80062178 (u32 bytes, same order); the
    EXE keeps pointers to the 8 table entries at 0x80062198. The game reads
    ceil(size / 2048) sectors.
  * Script packs inside an overlay (`80 35`, u16 n, u32 offsets relative to
    the pack) are found by offset, so a block can be moved past the end of
    the overlay by changing its offset; the overlay then grows, moves to the
    end of the disc (new sector in the table) and gets a new size (EXE).

Free memory after an overlay: during a phone call (save state) RAM is zero
from the end of the phone overlay (0x80172090) to 0x80180C00; event modules
load at 0x80181228. Overlays are allowed to end at SLOT_END at most.
"""
import struct

SECTOR = 2048
TOC_SECTOR, TOC_OFF, TOC_N = 541, 0x440, 8
SLOT_DEST = 0x0013DD50
SLOT_ADDR = 0x8013DD50
SLOT_END = 0x80180000
EXE_BASE = 0x80015800
SIZES_ADDR = 0x80062178
PTRS_ADDR = 0x80062198


class Overlay:
    def __init__(self, index, sector, size, slot_addr=SLOT_ADDR, sizes_addr=SIZES_ADDR):
        self.index = index
        self.sector = sector
        self.size = size
        self.toc_off = TOC_SECTOR * SECTOR + TOC_OFF + 8 * index   # byte offset in disc data
        self.size_addr = sizes_addr + 4 * index
        self.slot_addr = slot_addr
        self.packs = {}            # pack offset in overlay -> list of block offsets (pack-relative)

    @property
    def start(self):
        return self.sector * SECTOR

    def max_size(self):
        return SLOT_END - self.slot_addr


def exe_word(exe, addr):
    return struct.unpack_from("<I", exe, 0x800 + addr - EXE_BASE)[0]


def find(data, exe):
    """[Overlay] with their script packs, or [] if the tables don't look as expected."""
    # Original Japan release and Rev 1 have the same eight resource entries
    # but different resident-code/data addresses. Validate the entire table.
    layouts = [(SLOT_DEST, SIZES_ADDR, PTRS_ADDR),
               (SLOT_DEST + 0x10, SIZES_ADDR - 0x6C, PTRS_ADDR - 0x6C)]
    matches = [(dest, sizes, ptrs) for dest, sizes, ptrs in layouts
               if all(struct.unpack_from("<I", data, TOC_SECTOR * SECTOR + TOC_OFF + 8 * i)[0] == dest
                      and exe_word(exe, ptrs + 4 * i) == 0x80010C40 + 8 * i
                      for i in range(TOC_N))]
    if len(matches) != 1:
        return []
    slot_dest, sizes_addr, ptrs_addr = matches[0]
    out = []
    for i in range(TOC_N):
        dest, sector = struct.unpack_from("<II", data, TOC_SECTOR * SECTOR + TOC_OFF + 8 * i)
        if dest != slot_dest or exe_word(exe, ptrs_addr + 4 * i) != 0x80010C40 + 8 * i:
            return []
        size = exe_word(exe, sizes_addr + 4 * i)
        if not size:
            continue
        if size > SLOT_END - (0x80000000 | slot_dest) or (sector * SECTOR + size) > len(data):
            return []
        ov = Overlay(i, sector, size, 0x80000000 | slot_dest, sizes_addr)
        buf = data[ov.start:ov.start + size]
        p = 0
        while True:
            p = buf.find(b"\x80\x35", p)
            if p < 0:
                break
            if p % 4 == 0 and p + 8 <= len(buf):
                n = struct.unpack_from("<H", buf, p + 2)[0]
                if 1 <= n <= 255 and p + 4 + 4 * n <= len(buf):
                    offs = list(struct.unpack_from("<%dI" % n, buf, p + 4))
                    if offs == sorted(offs) and offs[0] >= 4 + 4 * n and p + offs[-1] < len(buf) and \
                            all(buf[p + o:p + o + 4] == b"\x38\x35\0\0" for o in offs):
                        ov.packs[p] = offs
            p += 2
        out.append(ov)
    return out


def block_map(overlays):
    """{block offset in disc data: (overlay, pack offset, index)}."""
    m = {}
    for ov in overlays:
        for p, offs in ov.packs.items():
            for i, o in enumerate(offs):
                m[ov.start + p + o] = (ov, p, i)
    return m
