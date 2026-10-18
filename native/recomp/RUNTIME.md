# Disc 1 runtime bring-up

The baseline Windows x64 runtime links and renders the opening movie from the documented
English-patched Disc 1. This is an incomplete recompilation experiment. It does
not establish a fully native port, playable routes, correct audio, save support
or automatic disc changes. Keep using the English patch in DuckStation for play.

Follow-up: [static overlay execution](OVERLAYS.md) now reduces fallback and
reaches the English new-game/name-entry interface. The measurements below
describe the earlier baseline and remain useful for reproducing the CD fix.

## Build corrections

The external framework is pinned to
`53a057f548cd1f93f1b4d8300caaeded72f4160d`. Apply the three ordered patches in
[framework-patches](framework-patches) to that checkout:

1. Move two compile-time checks outside a capturing lambda so MSVC 19.39 can
   evaluate them. The checks remain intact.
2. Use C11 atomic operations for the renderer's cross-thread PGXP flag, retaining
   release/acquire ordering. The previous GCC builtins do not compile in MSVC.
3. Correct explicit CD seek status: SeekL/SeekP stop the read/play state, set
   seeking during the operation, then finish paused. A subsequent ReadN/ReadS
   starts reading. The old completion set READ despite having no active stream.

The last defect made the game repeatedly poll Getstat while the drive reported
status `0x22` and `reading=0`. It stopped progressing beyond sector 547. The same
stall occurred with the thread scheduler's HLE disabled and with forced CPU
interpretation, helping separate the controller defect from generated game code.
After the correction, the 45-second probe reached sector 281721 and rendered
movie frames. No forced-interpreter workaround is enabled in the fixed build.

The seek behavior follows the [PSX CD-ROM command reference](https://psx-spx.consoledev.net/cdromdrive/).
DuckStation's [seek completion implementation](https://github.com/stenzek/duckstation/blob/master/src/core/cdrom.cpp)
was also inspected for comparison; no DuckStation source was copied.
The synthetic regression failed before the change and passes afterward for
both seek commands and subsequent ReadN/ReadS. Existing sector FIFO tests pass.
This is not a compatibility test of other games using the framework.

The CMake wrapper enables MSVC C11 atomics for the C files that need them. For
MSVC 19.39 only, it disables optimization of `psx_icache.c` to avoid an observed
compiler internal error; the cache algorithm is unchanged. Build Release only:
the pinned framework's generated configuration conflicts in a multi-config build.

## Reproduce locally

Use Windows, Python 3.11+, Visual Studio 2022 with C++ tools, CMake and Git.
Run from this source repository. Paths below are examples: set them to your own
checkout, a **fresh directory outside this repository**, and five ordered CUEs.
All generated game code, captures, disc data and saves must stay private.

```powershell
$framework = 'C:/research/psxrecomp'
$private = 'C:/research/tm2-runtime'
$cues = @('D:/games/disc1.cue', 'D:/games/disc2.cue', 'D:/games/disc3.cue', 'D:/games/disc4.cue', 'D:/games/disc5.cue')

# Check out the pinned revision before applying these patches, once each.
Get-ChildItem native/recomp/framework-patches/*.patch | Sort-Object Name | ForEach-Object {
    git -C $framework apply --check $_.FullName
    if ($LASTEXITCODE) { throw 'Patch preflight failed' }
    git -C $framework apply $_.FullName
    if ($LASTEXITCODE) { throw 'Patch application failed' }
}
python native/recomp/prepare_runtime.py --framework $framework --output $private @cues

cmake -S "$framework/recompiler" -B "$framework/recompiler/build" -G 'Visual Studio 17 2022' -A x64 -DPSXRECOMP_ENABLE_CHD=OFF -DBUILD_TESTING=OFF
cmake --build "$framework/recompiler/build" --config Release --target psxrecomp-game psxrecomp-bios --parallel 2
& "$framework/recompiler/build/Release/psxrecomp-game.exe" "$private/boot-loaded.exe" --seeds "$private/seeds.txt" --out-dir "$private/generated" --strict --project-root $framework

Push-Location $framework
try {
    & './recompiler/build/Release/psxrecomp-bios.exe' --config bios/OpenBIOS.toml
    cmake "-DROOT=$framework" "-DPROFILE=$framework/bios/OpenBIOS.toml" -P tools/bios_emitter_fingerprint.cmake | Set-Content -Encoding ascii generated/OpenBIOS.emitter.sha
} finally { Pop-Location }

cmake -S native/recomp/runtime -B "$private/build" -G 'Visual Studio 17 2022' -A x64 -DCMAKE_CONFIGURATION_TYPES=Release "-DPSXRECOMP_ROOT=$framework" "-DTM2_GENERATED_DIR=$private/generated" "-DTM2_GAME_CONFIG=$private/game.toml"
cmake --build "$private/build" --config Release --target psx-runtime tm2-cdrom-regression --parallel 2
& "$private/build/Release/tm2-cdrom-regression.exe"
$exe = "$private/build/Release/Tokimeki_Memorial_2___Recompilation_Research.exe"
python native/recomp/boot_probe.py --framework $framework --exe $exe --game "$private/game.toml" --output "$private/boot-01" --seconds 45
```

Stop on any command failure; PowerShell does not automatically stop after a
native command exits nonzero. CMake downloads pinned runtime dependencies. Use
absolute paths for both BIOS fingerprint parameters. Keep the staged BIOS and
its license, runtime assets and sidecar files next to the executable.

The probe starts its own headless process with a fresh memory-card directory,
records frame/capture/diagnostic data, and closes only that process. Exit zero
means the bounded capture completed while the process remained alive; it is
**not a gameplay pass**. Inspect screenshots and diagnostic evidence separately.
The debug server accepts active-low pad words: Start alone is `0xFFF7`, neutral
is `0xFFFF`; `0x0008` does not mean Start alone.

## Coverage and remaining checks

The fixed 45-second session recorded 118,666,453 interpreted instructions,
74,361 native handoffs and no recorded interpreter aborts. These counters do
not share a denominator and must not be converted into a native percentage.
Frequent fallback addresses include `0x000C3690`, `0x000C09D4` and `0x000C3D28`.
Native overlay generation is disabled for this first boot probe. Several
different modules reuse `0x800C0000`; addresses alone do not identify the main
game engine. The follow-up matches some observed code to sectors 543 and 717.

The profile is REFERENCE, with the default HLE boot/thread scheduling behavior
and the bundled OpenBIOS backend. REFERENCE does not mean all HLE is disabled.
Retail BIOS images were not used. A second fixed run remained alive for 100
seconds and continued rendering the opening movie; title/menu interaction,
audio and complete scenes have not yet been established by those captures.
Song lyrics remain Japanese, consistent with the patch's documented exclusions.

A 180-second follow-up also remained alive and reached frame 20119 in the last
sample. Active-low Start and Circle inputs were accepted by the debug server,
but this did not establish a visible menu response. Later captures were black;
recent CD reads continued, so a permanent stall is not established either.
It recorded 688,832,712 interpreted instructions and 308,222 native handoffs.
The input timing was manual, so this run is diagnostic evidence rather than a
repeatable controller test. Sanitized build and probe results are retained in
[runtime-validation.json](runtime-validation.json).

Next: verify title input and a complete scene, compare behavior against
DuckStation, then compile hash-qualified overlays and resolve the five-disc
executable differences. Do not bypass the multi-program guard. Automatic disc
selection still needs evidence of this game's request and acknowledgement
protocol. No five-disc native runtime is claimed.
