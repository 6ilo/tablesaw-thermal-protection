#pragma once

#include <stdint.h>

#include "saw_state_machine.h"

/* Runs the boot self-test, decides the initial state, and starts the core-0 task.
 * Returns false if the sensor self-test failed — the relay stays open and the LED goes
 * to SOS, but the task still runs so the supervisor can recover if the sensor does. */
bool saw_protection_begin(void);

/* Never returns. Pinned to core 0 at high priority by saw_protection_begin(). */
void saw_protection_task(void *arg);

/* Read-only view for the boot banner. The live view for the dashboard is the snapshot in
 * saw_runtime.h — nothing outside core 0 gets a pointer to the real context. */
const SawLimits &saw_protection_limits(void);
