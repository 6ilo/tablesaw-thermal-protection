---
code: X00
title: Short operator-facing name
severity: trip          # trip | lockout | warning | info
event: FIRMWARE_EVENT   # log event name emitted by the firmware
state: TRIPPED          # BOOT | ARMED | TRIPPED | COOLDOWN | MANUAL_LOCKOUT
led: Fast blink (5 Hz)  # must match ARCHITECTURE.md § Status LED patterns
clears: auto            # auto | ack | power | none
loto: false             # true if remediation requires locking out the disconnect
since: "1.0.0"
summary: One line, max 160 characters. Shown on the status card and in the index.
refs:
  - title: Section name in the repository
    url: https://github.com/6ilo/tablesaw-thermal-protection/blob/main/ARCHITECTURE.md#anchor
---

## What happened

Two or three sentences. Plain language. What the supervisor observed, and what it
did about it. Name the threshold and its value if one is involved.

## Do this now

1. Numbered, imperative, in the order the operator should do them.
2. Shortest safe path back to cutting first; investigation second.
3. Never more than about six steps — this is read on a phone at the machine.

## Why it happens

The causes, most likely first. Ground them in this specific saw — TEFC motor,
sawdust, service factor 1.0 — not in general electrical theory.

## When it clears

Exactly what has to become true, and what the operator will see when it does.
State plainly whether the saw restarts on its own. It does not: the 3-wire
seal-in means someone presses Start.

## If it keeps happening

The escalation path. What repetition means, and the point at which this stops
being an operator task and becomes a builder task.
