# Childhood scene execution

Tested on 2026-10-18 with the same English-patched Disc 1, pinned PSXRecomp
revision and three compatibility patches documented in [RUNTIME.md](RUNTIME.md).
The runtime uses the software renderer, bundled OpenBIOS and default HLE
scheduling. Runtime overlay compilation is disabled. This is progress toward
the [native release contract](../ROADMAP.md#required-final-deliverable), not a
finished native PC port.

## Observed progression

With the initial 15-image build, an interactive run proceeded from name entry
through birthday/blood-type confirmation, declined the optional E.V.S. prompts,
and reached classroom dialogue. It continued through the Hikari/Kasumi street
encounter, the return home and the free neighborhood map. The run was manually
stopped after collecting evidence; its bounded-probe exit is not a completed
time-limit pass.

Those observations provided new private code snapshots. Combining 54 capture
records with the previous evidence yielded 41 distinct images. Conservative
discovery added 1,951 candidate roots. Offline compilation produced 53 C
translation units and 27,142 guarded function identities, including 24,381
continuation wrappers. These are not counts of original source functions.

A fresh process with the 41-image build resumed a private classroom checkpoint
and advanced through the street encounter, changing character expressions,
portraits and backgrounds, the return home and English map controls. It sampled
24,015 frames after the confirmed load, with 10,715,836 additional native
overlay hits, 2,738,822 additional dirty-RAM interpreter instructions and zero
recorded interpreter aborts. A separate map checkpoint responded to Right
input by moving the player sprite. Screenshots and command/response logs are
retained privately; no pixel-perfect parity claim is made.

Capturing several remaining interpreter entry points expanded the batch to
**46 distinct images, 2,001 added discovery roots, 59 C translation units and
28,024 guarded function identities**. The framework reported 46 successful
image compilations, no failures/skips, and 26 isolated interior fragments.
MSVC 19.39 linked the expanded build successfully. All variants retain live-byte
guards; a reused address alone never selects a code image.

## Matched map checkpoint

Both builds resumed the same private OpenBIOS checkpoint in fresh save folders.
Counters were sampled after the runtime acknowledged a successful load, then
again after at least 600 additional frames. They exclude startup before that
baseline; diagnostic collection is asynchronous.

| Measurement | Initial 15-image build | Expanded 46-image build |
|---|---:|---:|
| Sampled frames after load | 689 | 686 |
| Additional dirty-RAM interpreter instructions | 31,684,584 | 0 |
| Additional static overlay hits | 0 | 425,532 |
| Recorded interpreter aborts | 0 | 0 |
| Visual result | Neighborhood map | Neighborhood map |

The expanded build also renders the classroom checkpoint correctly, with
3,240 additional dirty-RAM interpreter instructions still recorded there.
A separate 3,060-frame map-input check moves the player using Right twice,
records 1,863,817 additional native overlay hits and records zero dirty-RAM
interpreter instructions. A fresh opening boot also reaches the movie, while
still recording 39,147,070 interpreted instructions from startup onward. The
machine-readable [validation record](scene-validation.json) pins build hashes,
checkpoint hashes and measured results. Zero in this counter describes this
bounded map interval. It does not establish complete game coverage, remove the
interpreter from the executable, or prove that all BIOS/hardware compatibility
paths are native PC services. No speedup percentage is inferred.

## Reproduce private checkpoint checks

Create checkpoints through the runtime debug API, and wait for `savestate_status`
to report a new generation, `last_ok = 1`, the requested operation and slot.
A save/load request acknowledgement alone does not establish completion.
Use only checkpoints from the documented disc/configuration. Checkpoint files
contain game data and remain outside Git.

```powershell
$env:PSX_OVERLAY_AUTOCOMPILE_OFF = "1"
python native/recomp/boot_probe.py --framework $framework --exe $exe --game "$private/game.toml" --output "$private/map-check" --seconds 60 --load-state "$private/checkpoints/state_800175C8_slot08.pst" --after-load-frames 600
python -m unittest discover -s native/recomp -p "test_*.py"
```

The probe checks the filename's entry address, slot range and configured BIOS,
copies the checkpoint into a fresh private save directory, and waits for the
runtime's load-completion result. The runtime validates checkpoint contents;
the filename is not proof of game revision compatibility. The report includes
the copied checkpoint's SHA-256, executable/configuration hashes, baseline
counters and resolved frame target. Reaching a frame target remains a capture
check, not a gameplay pass. Debug checkpoints are not normal in-game saves.

For capture runs, use `overlay_cache = true`, set `PSX_OVERLAY_CAPTURES` to a
private filename, and add `--dump-overlays`. The probe flushes capture evidence
before shutting down its own process. Stop the game before merging snapshots.
`prepare_overlays.py --captures` accepts multiple paths; include needed history
files explicitly, or use `--include-history` when every supplied snapshot has
an adjacent `.d` directory. For example:

```powershell
$captures = @("$private/previous/captures.json", "$private/latest.json")
$captures += @(Get-ChildItem "$private/latest.json.d" -Filter *.json).FullName
python native/recomp/prepare_overlays.py --framework $framework --captures @captures --output "$private/next-inputs"
```

Then follow the offline compile/link commands in [OVERLAYS.md](OVERLAYS.md).
Clear `PSX_OVERLAY_CAPTURES` before compiling: the upstream tool lets that
environment variable override its input argument. Keep generated C, captures,
disc data, screenshots and checkpoints private.

## Remaining gaps

- Opening/startup and unvisited code still use fallback. The runtime still
  includes PlayStation hardware compatibility and BIOS/HLE services.
- Japanese date/location graphics and the profile-confirmation image remain;
  this work does not translate those assets.
- Audio/voice, normal memory-card saves, choices, complete routes and minigames
  have not passed parity checks. The tutorial and map tests are narrow samples.
- The five-disc executable differences and automatic resource/disc selection
  remain unresolved. The multi-program guard stays in place.
- Capture-derived coverage is not a reproducible inventory of every module on
  every disc. Disc-derived extraction recipes and fail-visible native-only
  validation are still required before a release.
