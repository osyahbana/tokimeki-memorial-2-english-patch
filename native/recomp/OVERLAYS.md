# Static overlay execution

The Disc 1 research runtime now links an initial batch of overlay code directly
into its Windows executable. The runtime does not compile this batch during
play. Interpreter fallback still handles uncovered code, so this remains an
incomplete native port.

## Measured results

On 2026-10-18, a capture-enabled boot with runtime compilation disabled produced
private code snapshots. A subset of 19 records was frozen for this experiment.
Four repeated image identities contained additional entry evidence: combining
those observations yielded **15 distinct images**. Different code bytes at the
same address remain separate variants. Simply emitting every observation led
to duplicate linker symbols; the preparation helper now unions entry and
segment evidence for identical images, with regression tests for this behavior.

The pinned framework's conservative discovery added 300 candidate roots. Its
static compiler accepted all 15 images with no reported failures, producing
**21 C translation units and 3,671 guarded function identities**. Of these,
3,167 are continuation/resume wrappers: this is not a count of 3,671 original
game functions. The runtime linked successfully with MSVC 19.39.

Two software-rendered runs, with runtime compilation disabled by configuration,
stopped near the same emulated frame target:

| Observation | Resident code only | With static overlays |
|---|---:|---:|
| Last sampled frame | 6,057 | 6,006 |
| Interpreted instructions at diagnostic collection | 187,707,287 | 40,105,619 |
| Static overlay hits | Not linked | 1,598,576 |
| Recorded interpreter aborts | 0 | 0 |
| Visual observation | Opening movie | Opening movie |

This is approximately **79% fewer interpreted instructions in this bounded
sample**, not 79% native coverage or a speedup measurement. Sampling/diagnostic
collection is asynchronous, and the frame counts are slightly different.
Both final captures show the same lyric passage, at different animation frames;
pixel parity has not been asserted. Remaining interpretation is dominated by
low-RAM startup paths, with further game/BIOS paths still uncovered.

The executable SHA-256 for this batch is
`edd20f6233b1088c2a69674df0b81f62885edda5d7b9bf64b77e3fd02e3910f3`.
These observations apply only to the documented patched Disc 1 and pinned
framework plus the three patches in [RUNTIME.md](RUNTIME.md).

Runtime byte anchors additionally match disc sectors 543 and 717 when mapped
to `0x800C0000`. This identifies producers for investigation; it does not yet
establish each complete module's extent or a release-ready extraction recipe.
Capture-derived coverage is a development step, not an inventory of all five
discs or proof that unvisited routes work.

## Interactive checkpoint

A separate 180-second run reached the translated **File Select Room**, then
the **Start a new game?** confirmation, and finally the English **Your last
name?** screen with the character artwork and Latin alphabet grid rendered.
Start/Circle pulses entered the interface; subsequent individual Circle, Up,
Circle inputs opened New, selected Yes, and accepted it. Port 1 was observed
connected in digital mode. This verifies visible menu response and new-game
progression; no complete dialogue scene or save/load round trip is claimed.

The initial diagnostic input route began at reported frame 7221 and alternated
120 neutral frames, 30 Start frames, 120 neutral frames, and 30 Circle frames.
It was stopped manually before the individual confirmation steps. This is a
recorded investigation, not a deterministic full-game regression. The final
run sample was frame 18441, with 172,603,562 interpreted instructions and
423,765 static-overlay hits at diagnostic collection. New interface paths still
add fallback. Earlier black captures were transitions: the longer capture run
continued through additional animation, and input now reaches the menus.

## Reproduce the offline compilation

First build the baseline using [RUNTIME.md](RUNTIME.md). Use a separate local
game config with `overlay_cache = true` to collect evidence. Set
`PSX_OVERLAY_AUTOCOMPILE_OFF=1` and `PSX_OVERLAY_CAPTURES` to a private path before
running the bounded probe. Stop the process before snapshotting its capture
history. The capture file and its adjacent `.d` directory contain game bytes
and must not be committed.

From the source repository, using absolute paths for `$framework` and `$private`:

```powershell
python native/recomp/prepare_overlays.py --framework $framework --captures "$private/overlay_captures.json" --include-history --output "$private/overlay-inputs"
python "$framework/tools/compile_overlays.py" --static --captures "$private/overlay-inputs/enriched.json" --game-toml "$private/game.toml" --recompiler "$framework/recompiler/build/Release/psxrecomp-game.exe" --runtime-include "$framework/runtime/include" --out-dir "$private/static-overlays" --cps --jobs 2 --target-os win
cmake -S native/recomp/runtime -B "$private/build" "-DTM2_STATIC_OVERLAYS=$private/static-overlays/overlays_static.c"
cmake --build "$private/build" --config Release --target psx-runtime --parallel 2
python native/recomp/boot_probe.py --framework $framework --exe "$private/build/Release/Tokimeki_Memorial_2___Recompilation_Research.exe" --game "$private/game.toml" --output "$private/overlay-boot" --seconds 90 --frames 6000
python -m unittest discover -s native/recomp -p test_prepare_overlays.py
```

Use fresh output directories and stop on command errors. Clear
`PSX_OVERLAY_CAPTURES` before invoking the compiler if it is still set: upstream
allows that environment variable to override `--captures`. Keep runtime
compilation disabled during validation. The original `overlay_cache = false`
game config can execute statically linked overlays; it disables dynamic cache
loading/capture, not the linked dispatcher.

`--frames` stops at or after the target sampled frame, subject to the wall-time
limit. Exit zero requires reaching that target when supplied, but still does
not certify gameplay. The report includes final screenshots, pad state and
static-dispatch counters. A specified but missing `TM2_STATIC_OVERLAYS` file is
a configuration error, preventing a silently empty overlay build.

## Remaining work

Verify a complete interactive scene and compare it with DuckStation, expand
disc-derived overlay recipes, replace remaining interpreted startup/BIOS paths,
and implement native PC services and five-disc resource selection. The current
hardware runtime and CPU fallback do not meet the final native release contract.
