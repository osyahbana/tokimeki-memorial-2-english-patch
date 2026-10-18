# Childhood content and resource routing

The scene parser and compression routines originate in the credited upstream
patch tooling. The research exporter adds bounded parsing of three childhood
graphics bundles. No game assets are distributed with this source.

Run from the repository root, using Python dependencies from `requirements.txt`:

```powershell
python native/research/export_sprite_tiles.py --disc "PATH/TO/DISC1.bin" --output "PATH/TO/NEW-PRIVATE-TILES"
```

The output must be new and outside the source tree. The importer validates the
entire supported image digest, then hashes the exact bytes used for extraction.
Both supported original and English-patched Disc 1 identities are accepted.
The private manifest records the actual revision and digest; patched images
must never be described as pristine Japanese source.

## Proven structure

The selected bundles are `YG_02506` at LBA 35550, `YG_04502` at LBA 49278 and
`YG_01503` at LBA 44747. Each contains a script, a 36-byte table and two graphics
containers. Bundle sizes are read from the source, allowing translated scripts
to grow without assuming their later parts have fixed byte offsets.

The graphics header starts with palette count and palette-descriptor-offset
array pointer. Each palette descriptor follows 512 bytes of RGB555 data; its
second word points backward to that palette. Header words at +40/+44 hold the
texture count and texture-descriptor-offset-array pointer. Each 32-byte type
0x204 descriptor follows its LZ2 data; its third word points backward to that
payload. Decode the bounded preceding stream, rather than interpreting it as
the following packet. Each observed texture yields 16,384 bytes. Compressed
payloads have up to seven zero bytes of alignment padding. The bounded decoder
checks both extent and padding before accepting a texture.

Interpreting these bytes as 128 by 128 indexed 8-bit tiles produces coherent
childhood character artwork, including heads, bodies and facial-expression
pieces. Each same-container palette is exported as a separate **candidate**.
No per-tile palette selection or transparency behavior is inferred from an
opaque RGB preview. The manifest records compressed and decoded hashes and
source offsets for auditing.

## What is still unknown

These are texture tiles, not rendered scenes. Sprite assembly, screen
coordinates, animation timing, palette selection, background association,
blending and engine-side script effects still require reconstruction. A scene
header provides a bytecode entrypoint, not the game's initial entrypoint.
Local CFG extraction must retain instruction starts and branch destinations;
sorting dialogue lines cannot reproduce gameplay.

## Native resource routing

All five discs can be imported into one native resource store. Keep image
revision/hash, disc serial and resource locator as aliases, then deduplicate
identical content by full hash. Scene ID alone is insufficient: different
variants share IDs, and patched images may contain abandoned copies left by
relocation. Scanner counts are therefore not live-scene counts.

For the main game, preserve group LBA and variant index from the `90 35` group
header and its sector-offset table. For childhood assets retain bundle LBA,
part index and script-pack index where present. This supports direct native
resource lookup without physical disc swapping, but exact event dispatch and
disc-transition state remain unresolved. XA and STR need raw-sector demuxing;
the 2048-byte Form 1 extraction used for scripts is not a complete media importer.
