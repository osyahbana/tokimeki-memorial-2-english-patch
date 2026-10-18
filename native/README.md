# Native PC engine development

This branch starts a native Windows reimplementation of Tokimeki Memorial 2.
It is **not a playable full-game port yet**. The executable is a C#/.NET 8 desktop
application with its own script interpreter. It does not launch DuckStation,
execute MIPS instructions, load a PlayStation BIOS, or embed a console emulator.
The .NET runtime is included in the self-contained Windows build.

See the [static recompilation assessment](recomp/README.md) for the newly tested
PSXRecomp path. It is separate from this C# research application and is now the
recommended next gameplay experiment.

## What exists

- A read-only importer for the five documented original or English-patched BINs.
  It hashes the exact source bytes, preserves decoded instruction addresses and
  branch targets, and exports English text with provenance. Existing output
  folders and source images are not overwritten.
- A native resource catalog that can access all five imported discs concurrently.
  Resource identities retain disc, content key and source location. The same scene
  name on different discs cannot silently select the wrong resource.
- A native interpreter for the recovered main-engine expression subset, ordinary
  variables, relative branches, F0 context resets, message text, abstract waits and end events.
  Unsupported instructions/state queries stop at their original address.
- A Windows research interface with separate execution and source-inspection tabs,
  proportional English rendering and native interpreter checkpoints.
- Synthetic regression tests and 383 expression test vectors whose expected
  results/state were obtained by executing the actual game routines offline.

The importer currently indexes **scanned script candidates**, including abandoned
copies left by patch relocation. It does not establish that the game reaches every
candidate. The text inspection tab lists instructions in address order, which is
not a playthrough. Running from an arbitrary scene with zeroed research registers
does not reproduce the original event's initial state.

**Current execution boundary:** real main-game scene candidates begin with F0.
The native engine reconstructs its register/context reset and emits host event
`01/0C`, then remains pending. The outer game needs scene context and media/resource
state that are not yet reconstructed. Pressing Continue does not skip this event.
Only a machine-code-established direct-completion case is implemented and tested
with synthetic context. No imported full scene is claimed to play through yet.

## Build and run

Requirements: Windows, .NET 8 SDK, and Python with the root `requirements.txt`
dependencies. The importer reuses the attributed patch project's format parsers.

From the repository root:

```powershell
python -m pip install -r requirements.txt
python native/import_game.py --disc-dir "PATH_TO_YOUR_DISCS" --output native/data
dotnet run --project native/Tm2.Native -- --manifest native/data/manifest.json
```

The input must match one of the full-file hashes in `docs/supported-images.json`
or `docs/integration-results.json`. Arbitrary patched revisions are rejected.
For single-disc research, explicit `--discs FILE.bin --allow-subset` is supported.

Build a standalone Windows folder without requiring .NET on the target PC:

```powershell
dotnet publish native/Tm2.Native -c Release -r win-x64 --self-contained true -o native/publish/app
```

Launch `Tokimeki2.Native.exe` and select your imported `manifest.json`, or place
the imported `data` directory beside `app`. Keep all published runtime files
together. The executable is a research client; use DuckStation for the currently
playable English patch.

## Disc handling

A native engine has no physical disc drive to swap. All five resource banks are
available locally. The catalog resolves an exact resource identity directly,
including when loading a checkpoint from another bank. Synthetic tests exercise
nonsequential access `1 → 5 → 2 → 4 → 3 → 1` without remounting anything.

**Automatic story progression is not implemented.** The game-specific event
dispatcher, disc-request state and group/variant selection must be reconstructed
before the game can choose those resources correctly. Merely concatenating discs
or advancing through dialogue lists does not solve that problem.

## Tests and evidence

```powershell
python -m unittest discover -s native/tests -v
dotnet run --project native/Tm2.Tests -c Release
dotnet run --project native/Tm2.Tests -c Release -- --audit native/data/manifest.json
```

Tests need no game files except the explicitly requested content audit. Audit
results describe zero-state research execution, not successful gameplay.
See [machine-code findings](research/vm-findings.md),
[synthetic machine oracle vectors](research/vm-vectors.json), and
[development roadmap](ROADMAP.md). The oracle generator uses Unicorn only as an
offline research tool; it is not linked into the native application.

## Scope and credits

Graphics assembly, animation, backgrounds, menus, simulation, dating/relationship
state, choices, route progression, minigames, XA audio, STR movies, EVS speech,
original saves and complete childhood-engine behavior remain unimplemented.
Native checkpoints preserve only the implemented research state; they are not
PlayStation memory-card saves. Message waits/end events currently abstract helper
effects that still require reconstruction.

The original game and assets belong to their respective rights holders. Parsers,
translation data and prior research derive from jonny-anime's English patch and
the improvements documented in this repository. Preserve [ATTRIBUTION.md](../ATTRIBUTION.md)
and the upstream history. No new license is assigned to inherited material.
Game images, extracted scripts/artwork/media, and local build outputs stay outside
Git. No game content is supplied in the native executable.
