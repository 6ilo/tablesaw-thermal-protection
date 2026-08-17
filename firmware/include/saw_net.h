#pragma once

/* Starts the Wi-Fi access point, the HTTP dashboard and (optionally) OTA on a low
 * priority core-1 task. Failure is non-fatal by design: SR-8 says Wi-Fi down means the
 * system still protects. */
void saw_net_begin(void);

/* True once the access point is up. Advisory; nothing in protection consults it. */
bool saw_net_ready(void);
