# Static recompilation experiment

Tested on 2026-10-18 against the five English-patched original-release images.
**Disc 1 now executes an initial batch of compiled overlays and reaches the
English new-game/name-entry interface using PSXRecomp.**
Keep the C# client as a format/behavior research tool. Neither route currently
provides a playable native Tokimeki Memorial 2 build.

## Projects evaluated

| Project | Pinned revision | Role |
|---|---|---|
| [PSXRecomp](https://github.com/RetroPortingToolKit/psxrecomp) | `53a057f548cd1f93f1b4d8300caaeded72f4160d` | MIPS-to-C recompiler and PlayStation hardware runtime |
| [psxdecomp](https://github.com/anzaldoivan/psxdecomp) | `cd1d02fd088d571368001f8fff74b12a34498233` | Identification and matching-decompilation workflow; not a native PC runtime |

PSXRecomp executes ahead-of-time translated game code, native overlay modules,
and interpreter fallback for uncovered paths. This is a promising native
recompilation route, but its default fallback means a build is not automatically
fully native. Coverage must be measured on this game; framework-wide correctness
or coverage claims are not test results for Tokimeki Memorial 2.
See its [execution model](https://github.com/RetroPortingToolKit/psxrecomp/blob/53a057f548cd1f93f1b4d8300caaeded72f4160d/docs/EXECUTION_MODEL.md)
and [static overlay support](https://github.com/RetroPortingToolKit/psxrecomp/blob/53a057f548cd1f93f1b4d8300caaeded72f4160d/docs/AOT_SHARDING.md).

psxdecomp's portable identification script ran successfully under Python 3.11
on Windows in this assessment, despite its full plugin's documented Python 3.12+
requirement. Its complete bootstrap was not installed or validated. The
project-local [workflow](../../.agents/skills/tm2-recomp/SKILL.md) adapts its useful
investigation stages without depending on Claude-specific agents or hooks.

## Measured results

- Both probes identify Disc 1 as `SLPM-86355`, boot `SLPM_863.55`, entry
  `0x800175C8`, load address `0x80015800`, loaded size `0x57800` (358,400 bytes).
- psxdecomp found ten PsyQ library stamps, versions `4.5,4.5.10`, 770 prologue
  candidates, and no debug files by its file scan. SDK stamps do not establish
  the original compiler version. PSXRecomp found 851 entry/JAL seed candidates;
  these counts use different discovery methods and are not conflicting totals.
- All five boot EXE files are 1,048,576 bytes. Each contains 688,128 bytes beyond
  the header plus declared loaded image. Those bytes remain in the source discs.
- The framework's five-disc verifier returns **exit 3 / `n-programs`** because
  full executable hashes differ. It refuses to scaffold the set. Its explanation
  cites unprefixed generated symbols colliding when linking multiple programs.
- A more precise comparison finds **13 differing bytes in the loaded image**
  for each later disc compared with Disc 1. Offsets and identities are in
  [assessment.json](assessment.json). Their meaning and code/data roles remain
  unclassified. Do not bypass the framework's guard or assume one executable
  safely covers every disc.
- Built `psxrecomp-game.exe` from the pinned source using Visual Studio 2022,
  MSVC 19.39, CMake, x64 Release, with CHD support disabled and two build jobs.
- Unmodified Disc 1 EXE extraction fails its parser's exact-file-size check:
  header implies 360,448 total bytes, file contains 1,048,576.
- A **separate analysis copy** containing the header and declared loaded payload
  passes strict code generation: **2,044 function bodies**, **2,043 dispatch
  entries**, **27 C shards**. Ten out-of-function branch/jump warnings remain.
  Generation success does not establish correct function boundaries.
- All 27 shards plus the dispatch source compile successfully into Windows x64
  object files using MSVC C11. The follow-up runtime build links these with
  PSXRecomp and generated OpenBIOS code; its opening movie renders after the
  CD-controller correction described in [runtime validation](RUNTIME.md).
- The 45-second fixed-runtime probe recorded **118,666,453 interpreted
  instructions** and **74,361 native handoffs**. These different counters are
  not a native coverage percentage. Overlay addresses dominate
  fallback; the linked executable is **not yet a fully native game port**.
- The subsequent [static overlay experiment](OVERLAYS.md) links 15 distinct
  captured images and records 1,598,576 static hits near frame 6,000. Interpreted
  instructions fall from 187,707,287 to 40,105,619 in comparable bounded runs.
  A separate input run reaches File Select, the new-game confirmation and English
  name entry. This establishes menu interaction, not a complete playable scene.

The probe emits a generic one-track warning. It is not evidence that these
particular discs are missing tracks; the patch's documented input is a
single-track MODE2/2352 image. Netplay/catalog admission is outside this test.

## Remaining work, in order

1. Extend the verified new-game interface to a complete playable scene
   and comparison with DuckStation. Preserve the original full EXE on the mounted
   disc; isolate its shorter analysis view. Audio and gameplay are unverified.
2. Classify the 13 loaded-image differences and trailing data. Either establish
   a byte-guarded common-code strategy with per-disc data or implement namespaced
   per-program dispatch. Test starting directly from every disc and loading saves.
3. Inventory and compile CDPACK overlays, including main and childhood engines.
   Existing VM research identifies a main-engine load at `0x800C0000`; every
   overlay needs its own revision/hash, extent, load address and entry evidence.
4. Trace the game's requested-disc state and acknowledgement sequence, then
   implement automatic selection of the local disc image. The current source
   has menu/provider disc-insert plumbing; that alone does not detect which disc
   Tokimeki Memorial 2 requests. Preserve timing and game state across changes.
5. Validate opening, dialogue, graphics, XA/SPU audio, movies, choices, simulation,
   minigames and saves. Measure fallback use. Claim fully native execution only
   for validated coverage with fallback eliminated or proven unused.

## Reproduce the assessment

Use clean checkouts at the revisions above. From this repository root, with
`FRAMEWORK`, `OUTSIDE_REPO` and the five CUE paths replaced by local paths:

```powershell
python native/recomp/probe_set.py --framework FRAMEWORK --output OUTSIDE_REPO --prepare-disc1 DISC1.cue DISC2.cue DISC3.cue DISC4.cue DISC5.cue
cmake -S FRAMEWORK/recompiler -B FRAMEWORK/recompiler/build -G "Visual Studio 17 2022" -A x64 -DPSXRECOMP_ENABLE_CHD=OFF -DBUILD_TESTING=OFF
cmake --build FRAMEWORK/recompiler/build --config Release --target psxrecomp-game --parallel 2
FRAMEWORK/recompiler/build/Release/psxrecomp-game.exe OUTSIDE_REPO/boot-loaded.exe --seeds OUTSIDE_REPO/seeds.txt --out-dir OUTSIDE_REPO/generated --strict --project-root FRAMEWORK
cmake -S native/recomp/compile-probe -B OUTSIDE_REPO/build -G "Visual Studio 17 2022" -A x64 -DFRAMEWORK=ABSOLUTE_FRAMEWORK_PATH -DGENERATED=ABSOLUTE_GENERATED_PATH
cmake --build OUTSIDE_REPO/build --config Release --parallel 2
```

The helper pins the probe source revision, refuses an existing output directory,
checks disc order and loaded bounds, and reports hashes/counts without game bytes.
`--prepare-disc1` additionally creates private inputs. Keep those inputs,
generated C, objects and runtime assets outside the public source tree.
The evidence here does not redistribute them. See [third-party attribution](THIRD_PARTY.md).

For the linked runtime, framework fixes, regression test and bounded boot probe,
continue with [RUNTIME.md](RUNTIME.md).
