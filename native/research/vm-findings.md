# Main-game VM: machine-code-derived native implementation notes

Scope: Disc 2 original-release-compatible main engine, load base `0x800c0000`.
The prior extracted `engine.bin` (prior extracted module) is 393,216 bytes,
SHA-256 `13267eac4b5f31bf8d07facd29faecd890d74368a5180d483b95a9a4c8d0c548`.
Its extraction script selects 192 logical user-data sectors starting at LBA1559.
A fresh read from the user's current Disc2 BIN differs in text/data (the current
BIN is patched), so it is **not** called a pristine image. Its extracted module
SHA-256 is `235b12d8e144347fa49b258a0aaba18d16b11ae5c7ba32104c4c373237d81ae8`.
All code and table ranges used below are byte-identical between both artifacts:

| Module range | SHA-256 |
|---|---|
|14e4..15d0 expression tables|242d67a3c84d536e7443d583703e155b02558293220e54473ad94bc3c72bf515|
|24090..245a4 evaluator|de23f62aab3ee49d31324e5ef8fd40562d4bfcecbb8de4e3a357820a053bb784|
|1624..1a24 statement table|298c2de2d4540df6f59e619adb0c6dd357d197e44f5af80a27d3baba0d627b79|
|2494c..26400 statement engine|769d330c50de3b027e82ca7a587bcbb83fdd68e0664dc51ccb6d286192d77dc8|

The previous Rev1 notes' addresses cannot be used unchanged: this evaluator
is `0x800e4090`, expression table `0x800c14e4`, binary table `0x800c156c`,
statement table `0x800c1624`, script pointer word `0x8011b3cc`.

## Expression semantics

Prefix expression encoding, left operand before right operand; both operands
are always evaluated, including logical operators. Values are signed 32-bit.
Addition, subtraction, multiplication and negation wrap modulo 2^32. A subsequent
Unicorn check also confirms INT_MIN / -1 = INT_MIN and INT_MIN % -1 = 0; these
cases are included in the portable vectors. Constants
are signed16 little-endian. C# should use unchecked operations and explicit
zero/overflow handling for division. Division by zero remains unsupported:
Unicorn produced behavior that should not be treated as proof of PS1 hardware
semantics.

|Opcode|Semantics|
|---|---|
|40|prefix; evaluate following expression|
|41,42,43|add, subtract, multiply|
|44,45|signed division truncating toward zero; signed remainder|
|46|unary negation|
|47,48,49,4a|less, greater, less-or-equal, greater-or-equal|
|4b,4c|equal, not-equal (return 0 or1)|
|4d|assignment target u8 followed by expression except target14|
|4e|signed16LE constant|
|4f|read variable identifier u8|
|58,59|eager logical OR, eager logical AND (return0/1)|
|5a|unary logical NOT (return0/1)|
|5b|evaluate two expressions then return0; no binary table slot exists|

5b's behavior is intentional evidence reporting, not a guess of the intended
language operator. At 44bc the second jump-table bound is 0x19 entries from41;
5b falls outside it, reaches458c, and returnszero. Unrecognized expression
opcodes also reach the binary fallback, so a native VM should reject unknown
opcodes rather than invent a parser interpretation.

## Variables / assignment

- Slots00..07: signed32 words at `0x8011b550 + id*4`.
- Slots08..0f: signed32 words at `0x8011b588 + (id-8)*4`.
- 4D returns the assigned value for ordinary slots.
- Target10: evaluates value, calls executable function80059e98(value), returns
  value; read10 calls80059e68. Meaning not established in this study.
- Target11: writes signed32 at8011b574. Read11 reads sameword.
- Target12/13: evaluates and returns value but does not assign it.
- Read12 reads8011b578. Read13 returns unsigned byte80076c2e plus1.
- Target14: consumes no value-expression and returns word8011b5a8.
- Read14 is *not* the same special operation: falls through array addressing,
  reading8011b5b8. This asymmetry matters. Higher variable IDs have no bounds
  check in game code; reject unsupported IDs in a native reconstruction until
  their addressed state has been understood.

## Statements

- 30 at800e4d34: evaluate expression; consume signed16LE displacement. On zero,
  PC becomes post-displacement PC + displacement; on nonzero, continue.
- 31 at800e4d58: consume signed16LE; unconditionally add to post-displacement PC.
- 40 at800e4d8c: evaluate expression, discard result, continue.
- 00 and3e both target800e6398: no operation beyond shared scheduling/yield logic.
- 38 at800e6278 is **not** a general call instruction. If bit18 at
  `*(0x8006c694)+0x2d4` is clear, set it, save currentPC at8011b3d0,
  jump to fixed address80111514. If set, continue.
- 3f at800e62c0 restores PC from8011b3d0 (single saved return slot, not a stack).
- 80 at800e4da8 polls a helper800e384c; when notready restores PC to the
  opcode and yields an 8-byte event. On acceptance calls800e75d0 and800f6b34.
  A UI-level wait/continue event is a suitable provisional representation,
  but helper side effects are not reconstructed here.
- FF at800e6310 calls800e3804 and8003dcd4(0x20), restores PC to the FF opcode,
  copies a fixed8-byte event template from800c15e8 and returns to caller.
  It is an end-of-script event, not exit-process. Caller transitions remain unknown.

## Remaining game-state expressions

Static evidence, not high-level game-state implementation:
-50 calls800d6950(u8);51/53 call800d6930(u8);52 calls800d69b0(u8).
-54 returns (word80075794 >>1)&3;55 returns (word>>8)&15;
 56 returns byte80075794 >>3;57 calls800eed40(u16 at80075798).
-5e compares u16 at80075798 against thresholds11b,207,244,374,3b1,
 returning bucket1..6.
-5f checks month field equals12 and dayfield is less than26.
-60 compares month/day fields of80075794 against80075040.
-5c/5d/61 use bytes80074faa/80074fb9 and helper800d68bc.
These fields can be exposed as unsupported game-state queries; returning zero
silently would select wrong routes and is unsuitable for a playable port.

## Evidence / executable checks

The initial internal differential harness executed evaluator/branch machine code using Unicorn
MIPS32LE with synthetic input memory. It compares a separately written model
against **1,562 passing cases**: randomized/boundary arithmetic/comparisons,
constants by assignment, prefix/unary ops, side-effect eagerevaluation,
32-bit assignments, specialtarget14, and branch truth/displacement cases.
The portable `generate_vm_vectors.py` reproduces the expression subset with an
explicit module path and emits `vm-vectors.json`. Its 383 synthetic vectors
include initial/final ordinary variables and expected results. No game bytes
are distributed. Initial analysis also used Capstone for the table/control-flow
observations above. This is offline testing of tiny routines, not runtime
emulation in the native product, not full gameplay verification, and does not
establish childhood-engine equivalence.

Implement now: pure expressions; proven ordinary variables; explicit context
for special slots;30/31/40; no-op00/3e; UI end/wait events. Stop explicitly on
unknown state queries, graphics/audio operations, and game-specific calls.
Never present guessed defaults as faithfully executed gameplay.

## F0 initialization and the host barrier

Additional code-derived evidence: statement `F0` dispatches to `0x800e61a4`.
Its handler has no calls. It resets the following state, copies the eight-byte
event `01 0c 00 00 00 00 00 00` from `0x800c15e0` to the caller's output,
and returns through `0x800e63f8`. The script PC stays at the next instruction.

|State|Width|F0 effect|
|---|---|---|
|ordinary variables 0..7, `0x8011b550..0x8011b56c`|eight signed32 words|zero|
|ordinary variables 8..15, `0x8011b588..0x8011b5a4`|eight signed32 words|preserved|
|`0x8011b574`|word|zero|
|`0x80111550`|word|zero|
|`0x8011b5b0`|word|zero|
|`0x80111554`|word|zero|
|`0x8011b3c0`|word|zero|
|`0x8011b570`|word|zero|
|`0x8011b5ac`|byte|zero|
|`0x8011b534`|word|zero|

The event is not permission to continue automatically. The main outer caller
at `0x800f3f8c` dispatches event type1/subtype12 to `0x800f4028`. In host phase
zero (`word[0x8011c104] == 0`), it reads scene-context pointer `0x8011c2c4`:

1. If `context[0x3c] != byte[0x80076bee]`, return without changing the VM
   resume gate at `0x8011c10c`.
2. If those bytes match and `context[0x3d] % 10 == 1`, return completed through
   `0x800f6b0c` without calling any external service or changing the resume gate.
3. Matching tags with other modulo values clear the resume gate, then enter a
   transition involving `0x8003caa0`, `0x8003dcd4` and
   `0x800449f0`, plus another host phase and a polling counter. The semantic
   identity of those context bytes and transition is not established here.

Therefore a native host can implement the exact reset and pending event now.
The caller runs the VM again when that gate is nonzero (`0x800f3f7c`), so both
no-transition branches resume on the next invocation. Their return address
alone does not distinguish pending and completed events. A native host can
acknowledge these measured no-transition branches only when real context is
available. Inventing default context bytes to pass the condition
would bypass game behavior. The imported scene JSON currently contains neither
these header fields nor the current global tag; the first F0 must remain
pending until that state is recovered. An explicit laboratory fixture is useful
for tests but cannot be described as a faithful game startup.

The native core currently takes the more conservative subset: it acknowledges
only matching tags with remainder1. Mismatched tags remain unsupported in the
native core even though the original caller leaves its resume gate set. This
is an implementation limit, not a claim that the original game waits there.

`generate_lifecycle_vectors.py ENGINE_MODULE --output lifecycle-vectors.json`
reproduces three synthetic reset vectors and six synthetic host-condition
vectors in Unicorn, without helper stubs. It checks all reset fields, preserves
the other eight variables, checks event bytes, and observes both the stop
address and resume-gate changes. The transition case stops at its first external
call without fabricating a result. No ROM bytes are included in the vectors.

|Additional module range|SHA-256|
|---|---|
|261a4..26230 F0 handler|85d22cb391f848cc5e1f8b63b6966488c2a266ecc7fbfa1211e603dea7fbc730|
|34028..340a4 host condition|c0a91a65d855a7726c0f3bd49e49ecf6aa4b0c82fbbed914e14b56f3e7ef9203|

Related boundaries: `F1` enters `0x800e6318`, calls executable service
`0x8003dcd4(0x20)`, returns the same end event as FF and rewinds the PC. `90`
either clears a state flag or calls the text-engine clear helper. Neither is
a proven unconditional no-op. The common next instruction `A2 0b aa bb`
creates event `05 0b aa bb 00 00 00 00`; its host effect remains unsupported.

An entry survey of the current import found 8,899 candidates reaching
`A2 0b 01 00` immediately after F0/no-ops. Some candidates reach a speaker
label directly, but they still require the F0 host context above. The survey
includes scanned scene copies and does not establish which copy a live caller
would select.
