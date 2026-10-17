"""Scene groups: how the main game (Discs 2-5) finds its scene scripts.

Verified by reading the main engine (docs/game-internals.md section 10):

  * An event module (code loaded at about 0x80181228) holds a table of
    absolute sector numbers of **group headers** and calls
    0x800F3C10(group sector, variant index, buffer). The buffer address is a
    constant in the module (the first byte after its own data).
  * The group header sector starts `90 35`, u16 n, then u32 e[n+1]: variant
    i occupies the sectors [group + e[i], group + e[i+1]) (empty if equal).
    0x800F3E10 reads exactly those sectors into the buffer.

So a variant's data can move anywhere after its group header, and grow to
more sectors, by rewriting e[] - nothing else refers to it. How many sectors
a module's buffer takes is not stored anywhere; `cap` is the largest variant
any group of the same event module already has (the game loads that much
into the same buffer), taking the smallest such value if several modules
use the group. That is an inference, checked on screen for one scene.
"""
import collections
import hashlib
import struct

import numpy as np

SECTOR = 2048
LOADER = 0x800F3C10           # main engine: load variant of a group
JAL_LOADER = struct.pack("<I", (3 << 26) | ((LOADER >> 2) & 0x3FFFFFF))


def _loader_call(data):
    """Recognise the measured Japan-original loader; retain Rev 1 behavior.

    Original Discs 2-5 load the engine from sector 1559 at 0x800C0000.
    The loader moved +8 bytes, to 0x800F3C18. Verify both its header-read
    entry and its offset-table/span-read continuation before deriving any
    larger capacity from modules calling that address. No blanket pointer
    delta is valid for this engine.
    """
    base = 1559 * SECTOR
    spans = (
        (0x33C18, 0x33C74, "f340c8904d6069e84d5747f26ab930e271b8f11f36da1e9f571bee7b2d10b440"),
        (0x33DD0, 0x33EB4, "0f9e57a4a4eb3088bc78d0f8bcb0a2a433558f64d349634dca611a99742a5314"),
    )
    if all(hashlib.sha256(data[base + lo:base + hi]).hexdigest() == digest
           for lo, hi, digest in spans):
        return struct.pack("<I", (3 << 26) | ((0x800F3C18 >> 2) & 0x3FFFFFF))
    return JAL_LOADER


class Group:
    def __init__(self, sector, n, entries):
        self.sector = sector
        self.n = n
        self.e = list(entries)                # sector offsets, n+1 values
        self.cap = None                       # sectors a variant may take
        self.modules = set()

    def variants(self):
        """[(index, first sector, length in sectors)] of non-empty variants."""
        return [(i, self.sector + self.e[i], self.e[i + 1] - self.e[i])
                for i in range(self.n) if self.e[i + 1] > self.e[i]]

    def max_len(self):
        return max((l for _, _, l in self.variants()), default=0)


def find_groups(data):
    """{sector: Group} for every group header on a disc (user data)."""
    out = {}
    nsec = len(data) // SECTOR
    p = 0
    while True:
        p = data.find(b"\x90\x35", p)
        if p < 0:
            break
        if p % SECTOR == 0:
            n = struct.unpack_from("<H", data, p + 2)[0]
            if 1 <= n <= 500 and 4 + 4 * (n + 1) <= SECTOR:
                e = struct.unpack_from("<%dI" % (n + 1), data, p + 4)
                s = p // SECTOR
                if list(e) == sorted(e) and e[0] >= 1 and s + e[-1] <= nsec and e[-1] - e[0] <= 4096:
                    g = Group(s, n, e)
                    if any(data[v * SECTOR:v * SECTOR + 4] == b"\x38\x35\0\0" for _, v, _ in g.variants()):
                        out[s] = g
        p += 2
    _capabilities(data, out)
    return out


def _capabilities(data, groups):
    # event modules: clusters of sectors that call the loader
    jal_loader = _loader_call(data)
    sites = set()
    p = 0
    while True:
        p = data.find(jal_loader, p)
        if p < 0:
            break
        if p % 4 == 0:
            sites.add(p // SECTOR)
        p += 4
    mods = []
    for s in sorted(sites):
        if mods and s - mods[-1][-1] <= 8:
            mods[-1].append(s)
        else:
            mods.append([s])
    # references: u32 == group sector, inside a module's sectors (+-4)
    keys = np.array(sorted(groups), dtype=np.uint32)
    for mi, m in enumerate(mods):
        lo, hi = max(0, m[0] - 4), m[-1] + 5
        w = np.frombuffer(data[lo * SECTOR:hi * SECTOR], dtype="<u4")
        for v in np.unique(w[np.isin(w, keys)]).tolist():
            groups[v].modules.add(mi)
    mcap = collections.defaultdict(int)
    for g in groups.values():
        for mi in g.modules:
            mcap[mi] = max(mcap[mi], g.max_len())
    for g in groups.values():
        g.cap = min((mcap[mi] for mi in g.modules), default=g.max_len())


def variant_of(groups):
    """{first sector of a variant: (group, index, length)}."""
    out = {}
    for g in groups.values():
        for i, s, l in g.variants():
            out[s] = (g, i, l)
    return out
