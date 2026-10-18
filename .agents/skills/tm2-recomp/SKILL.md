---
name: tm2-recomp
description: Investigate and develop the Tokimeki Memorial 2 native recompilation path using pinned PSXRecomp and psxdecomp evidence. Use for this project's native port, overlay coverage, boot compatibility or automatic disc transitions.
---

# Tokimeki Memorial 2 recompilation

Read [the measured assessment](../../../native/recomp/README.md) before changing
the implementation direction. The C# client is a research tool. No playable
native port has been established.

This workflow adapts the identify/research/implement/verify staging of
[psxdecomp](https://github.com/anzaldoivan/psxdecomp), credited with its MIT notice
in [THIRD_PARTY.md](../../../native/recomp/THIRD_PARTY.md). Use local shell tools
and project evidence; its Claude agents, hooks and restart protocol are not
prerequisites for this workflow.

1. **Identify.** Run `native/recomp/probe_set.py` against five explicitly ordered
   user-supplied CUEs and the pinned framework. Keep private outputs outside Git.
   Treat SDK stamps and function seeds as leads, not compiler identification or
   proven function boundaries. Keep pristine and patched revisions distinct.
2. **Resolve the input boundary.** These EXEs contain trailing bytes beyond the
   declared boot payload. A shorter analysis view is valid only as an analysis
   input; retain the complete source image for runtime resource reads. Check
   loaded bounds, source hashes and every executable's differing bytes.
3. **Choose the execution approach.** Use PSXRecomp for native machine-code
   translation. Use matching-decompilation techniques for difficult functions,
   loader behavior and missing evidence. Record exact upstream revisions and
   inspect changes before updating them. Do not install unrelated global hooks.
4. **Validate one layer at a time.** Record separate outcomes for code generation,
   host compilation, runtime linking, boot, one playable scene, and full routes.
   Compilation cannot stand in for execution. Diagnose emitter warnings before
   trusting the affected control flow. Compare observable behavior to the same
   revision under DuckStation and use existing VM oracle vectors where relevant.
5. **Cover overlays and discs.** Preserve per-disc/overlay hash and load identity;
   reused addresses do not imply identical code. The current five-disc scaffold
   rejects this set as multiple programs. Do not remove that guard without a
   supported dispatch design. Automatic disc selection requires observed request
   and acknowledgement behavior, not merely a list of five paths.
6. **Measure native coverage.** Track interpreter fallback and native overlay
   dispatch. Distinguish a native host executable, native game-code coverage and
   a complete native engine reconstruction. Report remaining gaps explicitly.

Retain attribution; publish project source, metadata and synthetic tests only.
Keep ROMs, extracted game content, generated game-code translations and saves
private. Repository-wide workflow and the user's publication instructions govern
commits and pushes; this skill does not authorize publication by itself.
