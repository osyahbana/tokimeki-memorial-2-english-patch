# Changes from upstream

Base: jonny-anime/tokimeki-memorial-2-english-patch at `401c95498289c8d6796ea13da05742c3126a6b0a`.

## Compatibility

- Guarded original Japan / v1.0 layouts for all five discs, including glyph rendering, name entry, EVS, overlays, string tables, date rendering and the group loader.
- 709 original-release scene variants mapped with original offsets and control codes; 132 revision-specific lines reviewed.
- Corrected graphic locations and direct lookup of explicitly addressed compressed streams.

## Text and correctness

- Preserve packed scene edits when relocating the containing group.
- Resolve string-table exclusions per revision so adjacent honorific fields are not skipped.
- Shorten six overflowing dialogue lines and the tea-ceremony club label.
- Add the missing `Year 3` script-marker label.
- Fix `--no-exe` so executable bytes cannot accidentally enable code patches.

## Build reliability

- Stage requested outputs, validate every disc and publish the playlist last.
- Fail on missing dialogue/speaker translations by default; explicitly report partial builds.
- Verify live translated strings and EDC/ECC for every changed sector.
- Emit per-disc reports with source/output hashes, coverage and warnings.
- Validate single-track CUE layout and normalize output references.
- Handle Windows console encoding and bounded diagnostics.
- Cache identical translated texture compression and verify round trips.

## Maintenance

- Synthetic regression tests and Windows/Linux CI configuration.
- Read-only verification command, supported-source hashes, review and validation documentation.
- Upstream history, credits and archived README retained.
