# Reconstruction roadmap

Target: one native PC installation using locally imported assets from all five
discs, with correct English presentation, game state, resource selection and saves.
The port is incomplete. None of the later milestones is claimed by the current
research executable.

The [PSXRecomp assessment](recomp/README.md) establishes a second route that can
retain the original gameplay logic through static recompilation. Prioritize a
Disc 1 runtime boot experiment, then overlay coverage and the five-disc program
differences. The milestones below describe the existing C# reconstruction;
they are not prerequisites for that separate recompilation experiment.

| Milestone | Required evidence and acceptance check | Current state |
|---|---|---|
| Content import | Hash-qualified sources; valid decoded branches; retain disc and instance identity | Implemented for documented images; global reachability unresolved |
| Core script expressions | Compare results, consumed bytes and variable writes to original routines | 383 native oracle vectors; broader offline research tests |
| Native research client | Build/run without DuckStation or BIOS; inspect sources separately from executed branches | Implemented |
| Event and resource dispatch | Trace boot through an actual event; recover group/variant/bundle requests and next-event return handling | Unresolved; scanned scene names are insufficient |
| One complete playable scene | Correct background, assembled character, expression, dialogue, voice, choices and return transition | Not implemented; sprite texture format partially decoded |
| Childhood engine | Compare statement and expression semantics for the second interpreter; reproduce the opening sequence | Not implemented; execution intentionally blocked for YG scripts |
| Simulation and routes | Recover calendar, stats, relationship state, scheduling and all event predicates; compare event traces | Not implemented |
| Media and presentation | Native XA/SPU audio, STR movies, drawing order/transparency, animation, UI and EVS | Not implemented |
| Disc-free progression | Original event requests select correct local resource banks; test forward/backward requests and save loading | Catalog supports direct access; game selection logic not implemented |
| Saves and minigames | Reconstruct complete native state, optional memory-card import, all minigames | Only interpreter research checkpoints exist |
| Release | Full route playthroughs, all endings, disc-boundary scenarios, media timing and regression checks | Not ready |

## Working rules

1. Anchor behavior to a specific artifact hash, load address and code/data span.
2. Separate observed behavior, inferred interpretation and unknown behavior.
3. Never silently skip an unknown opcode, invent state query values, or describe
   an address-sorted dialogue viewer as a running game.
4. In the C# reconstruction, use original CPU routines only for offline
   differential tests. In the recompilation route, measure native translation
   and fallback coverage separately; do not present fallback as native execution.
5. Import user-supplied assets locally. Commit source, synthetic tests and research
   findings; keep extracted copyrighted content and original code bytes out of Git.
6. Preserve each resource's disc/revision and locator even when deduplicating
   identical payloads. Original scene names are not globally unique.
