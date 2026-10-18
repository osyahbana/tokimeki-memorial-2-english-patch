# Controller replay and fallback checks

`boot_probe.py` can replay a bounded digital controller route after a confirmed
private checkpoint load, and reject a run that exceeds a dirty-RAM interpreter
budget. These checks help detect regressions while expanding native code
coverage. They do not disable the interpreter or satisfy the full native
release contract by themselves.

## Childhood introduction route

[routes/childhood-intro.json](routes/childhood-intro.json) contains 120 neutral
frames followed by 40 Circle pulses: three pressed frames, then 180 neutral
frames each. The final step releases all buttons. This route uses active-low
pad words (`57343` / `0xDFFF` for Circle, `65535` / `0xFFFF` for neutral).
It is intended for the classroom checkpoint identified in
[scene-validation.json](scene-validation.json), after the first player reply.
The checkpoint itself contains game data and is not distributed.

From the source repository, with absolute paths in `$framework`, `$exe` and
`$private`:

```powershell
$env:PSX_OVERLAY_AUTOCOMPILE_OFF = "1"
python native/recomp/boot_probe.py --framework $framework --exe $exe --game "$private/game.toml" --output "$private/intro-replay" --seconds 150 --load-state "$private/checkpoints/state_800175C8_slot02.pst" --after-load-frames 9000 --input-route native/recomp/routes/childhood-intro.json --max-ram-fallback 0
```

Use a fresh output directory. A checkpoint filename identifies a slot and entry
address, not a compatible game revision: compare its hash with the validation
record before using this specific route. Loading the wrong scene can send
valid inputs to unintended menus. These probes use their own copied saves.

The helper validates the whole route before launching the game. Each JSON step
contains only integer `buttons` and `frames` fields. Routes have at most 4,096
steps and 1,000,000 total frames, and end neutral. After boot/checkpoint load,
the helper clears the runtime's route, appends each step and starts it. A
rejected command or uncertain mutation aborts the probe instead of replaying
possibly applied inputs. The final report must confirm every step completed.

The checkpoint baseline is sampled before route setup. `--max-ram-fallback 0`
requires zero additional `dirty_ram_stats.insns_run` by the final diagnostic
sample. Missing, failed, invalid or decreasing counters fail the check. A
positive budget is supported for intermediate experiments. The option requires
`--load-state`, because a startup-inclusive counter and a post-load counter
answer different questions.

Exit zero requires the frame target, confirmed checkpoint load, complete route
and requested fallback budget to pass. It does **not** prove correct dialogue,
graphics, audio or game state. Inspect the private screenshots and compare the
observed sequence independently. Counters and screenshots are sampled
asynchronously; no exact-frame or pixel-parity claim follows from this probe.

For capture runs, use an `overlay_cache = true` config, set a private
`PSX_OVERLAY_CAPTURES` path and add `--dump-overlays`. Freeze snapshots after the
process stops, merge all relevant image/entry evidence, and compile offline as
described in [OVERLAYS.md](OVERLAYS.md). Do not treat runtime generation as
native-only validation.

## Measured results

On 2026-10-18, the contextual build compiled 51 distinct captured images into
65 C translation units. It contains 28,933 guarded function identities, including
26,009 continuation wrappers, and 27 isolated interior fragments. Generation
and MSVC linking succeeded with no reported image failures or skips. The
preparation retained 17 provenance links covering 23 added canonical dispatch
entries; different code variants remain separate.

The final [validation record](replay-validation.json) pins the executable,
checkpoint and controller-route hashes. The same final executable passed both
checks below with runtime overlay compilation disabled:

| Check | Sample | Dirty-RAM interpretation | Result |
|---|---|---:|---|
| Introduction replay after classroom checkpoint | 9,035 additional frames; all 81 controller steps completed | 0 additional instructions | Classroom, street encounter, return home and map-controls prompt rendered; zero-fallback budget passed |
| Fresh boot through opening movie | Last sampled frame 6,037 | 33 total instructions | Frame target reached, opening movie rendered |

The replay recorded 3,602,788 additional static overlay hits and no interpreter
aborts. The fresh boot recorded 6,766,485 static overlay hits and no interpreter
aborts. An earlier comparable 46-image boot recorded 39,147,070 interpreted
instructions. These are asynchronously collected counters at slightly different
frames, not a speedup or full-game coverage percentage.

The remaining cold-boot fallback report names low-RAM sites `0x0001154C` and
`0x00011364`. Its per-entry rows do not account for every instruction in the
aggregate counter, so their sum must not replace the measured total of 33.
The interpreter is still present, and native-only startup has not passed.

The intermediate 48-image replay was rejected for 10 additional interpreted
instructions, despite reaching the map prompt. Adding a page fragment exposed
a further continuation at the next boundary. Giving the compiler compatible
larger-image context resolved these transitions in the final replay. This is
why the budget check is independent of visual progression and process liveness.

Startup captures were collected early, before transient code evidence was
cleared. The compiled preparation includes the captured `0x80010000` image and
its later observed continuation. Raw bytes, generated C, checkpoints and
screenshots remain local. These results do not establish cold-boot-to-map input
replay in a single process, audiovisual parity, normal saves, complete routes,
minigames, five-disc switching or replacement of every hardware compatibility
service. The [full native release contract](../ROADMAP.md#required-final-deliverable)
remains unmet.

## Continuations and larger code context

A page-sized capture can cut through a larger function. Compiling it may remove
one fallback entry while exposing another at the next page boundary. The
optional `prepare_overlays.py --contextual-entries` mode addresses this when a
larger compatible capture is already available.

The helper compares the entire smaller snapshot, including its guard bytes,
at the same virtual address inside each larger snapshot. Only exact matches
qualify. It derives dispatch-entry candidates in the containing images while
preserving observed KUSEG/KSEG0/KSEG1 labels and existing implicit KSEG0 entries.
Guard-only entries are excluded. It does not promote an entry to a proven
function boundary, invent segment aliases, remove smaller captures or collapse
different larger-image variants.

Raw merged evidence remains in `captures.json`. The derived input is written
separately to `contextual-captures.json`, and `entry-context.json` records source
and target hashes, addresses and additions. The entries are conditional on
matching code, not evidence that the entire larger variant was observed in the
same runtime instant. The existing compiler revalidates boundaries and emits
live-byte guards for each resulting function variant. This remains an
experimental preparation mode requiring runtime checks.

```powershell
python native/recomp/prepare_overlays.py --framework $framework --captures "$private/previous/captures.json" "$private/new-captures.json" --contextual-entries --output "$private/next-inputs"
```

Compile `next-inputs/enriched.json` as usual. Preserve its provenance files with
the private build evidence. The tests include mismatched code/guard bytes,
out-of-range entries, segment preservation and distinct containing variants.

## Verification

The synthetic tests check checkpoint identity, bounded input validation,
non-repetition after uncertain route mutations, and rejection of missing/reset
fallback counters:

```powershell
python -m unittest discover -s native/recomp -p "test_*.py"
```

The integration negative control uses the earlier 46-image build and the same
classroom checkpoint. It reaches the frame target and remains alive, but its
zero-fallback check fails with 3,030 additional interpreted instructions. This
guards against mistaking successful process execution for native coverage.
