# Native development validation — 18 October 2026

This is validation of a development milestone, not of a finished port.

- Windows build: .NET SDK 8.0.202, C#/.NET 8, self-contained `win-x64` publication.
- 383 synthetic expression inputs match results and final ordinary-variable state
  from the original main-engine routines executed offline in Unicorn.
- 12 native test groups pass: expression and lifecycle oracles/malformed input, branch selection,
  conditional assignment, F0 context reset/pending event, unsupported-operation
  preservation, expression rollback, loop budget, branch-boundary validation,
  checkpoint identity/resume, and five-disc resource routing/integrity.
- 16 Python tests pass: importer bounds/branches/translations, image identity,
  source mutation, duplicate discs, atomic output, manifest identity, duplicate
  scene names, and texture descriptor/palette/compressed-span bounds.
- All five currently supplied images are recognized as the previously verified
  English-patched original-release images. All 11,466 scanned scene candidates
  were imported, hash checked and structurally validated by the native loader.
- Native execution audit: 120 childhood candidates were intentionally not
  executed; 11,346 main-engine candidates reach the pending F0 host event. **Zero
  candidates currently reach a dialogue message from entry without unresolved
  host initialization.** No full scene or gameplay route is claimed working.
- Three actual childhood graphic bundles were decoded into 25 texture tiles and
  33 palette-candidate PNGs, retained privately. Sprite assembly, palette selection
  and transparency remain unverified.
- The desktop interface was rendered and visually inspected. It separates source
  inspection from execution and labels missing gameplay explicitly.

The scanned corpus includes abandoned relocated copies. Counts are not counts of
live story events. Register state in the audit is synthetic/zeroed; original
calendar, event, relationship, audio and graphics state has not been recreated.

## Research evidence

[VM findings](research/vm-findings.md) record artifact hashes, code ranges and
known/unknown semantics. [Content findings](research/content-findings.md) record
scene and texture locations and extraction limitations. Oracle vectors contain
synthetic operands and results, not original game code. The native product has no
Unicorn, emulator or BIOS dependency.

## Continuous checks

`Native engine checks` runs the Python suite and native core suite on Windows and
Linux, and compiles the Windows interface on Windows. See this fork's Actions
results for the specific published commit. CI does not contain or import ROMs.
