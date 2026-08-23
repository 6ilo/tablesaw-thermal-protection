# Archive

Documents that are no longer the instructions but are still the reasoning.

Nothing here is deleted, and nothing here is wrong. A document lands in this folder when
something newer took over its *job* — when following it would send someone down a path the
project has since moved past — while the thinking inside it is still what the current
design rests on. Deleting those explanations would leave a project whose decisions look
arbitrary six months later; leaving them at the top level would leave two documents
competing to be followed.

Each entry says what replaced it and what it is still good for.

## Contents

| Document | Superseded by | Still worth reading for |
|---|---|---|
| [`BUILD-TONIGHT.md`](BUILD-TONIGHT.md) | [`../NEXT-STEPS.md`](../NEXT-STEPS.md) | The design reasoning behind Path A: why the heartbeat link inverts the usual failure logic, why the receiver must be in momentary mode and what a latched one would mean, why the thresholds sit where they do, what each bench fault test is actually proving, the level-shifter fallbacks, and the FCC Part 15 note on continuous 433 MHz transmission |

`BUILD-TONIGHT.md` was written for one person working alone in a single evening who already
knew what a contactor was. The people finishing the build are neither of those things, so
the procedure was rewritten for them in `NEXT-STEPS.md`. The *why* did not need rewriting —
it needed to stop being mixed in with the *how*.

Its section numbers are still cited from the firmware, from
[`../ARCHITECTURE.md`](../ARCHITECTURE.md) and from
[`../BUILD-LOG.md`](../BUILD-LOG.md). Those citations are live references, not history: if a
threshold or a test changes, this file is still the place the reasoning gets updated.

## Before adding anything here

Ask whether the document is *superseded* or merely *finished*. A completed checklist is not
archive material — it belongs in [`../BUILD-LOG.md`](../BUILD-LOG.md) as a dated entry.
This folder is for documents that would actively mislead if followed, and would leave a gap
if deleted.
