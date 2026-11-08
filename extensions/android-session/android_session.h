/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef ANDROID_SESSION_H
#define ANDROID_SESSION_H

typedef int (*android_session_entry_t)(int argc, char *const argv[]);

int android_session_main(int argc, char *const argv[], android_session_entry_t entry);
void android_session_guest_ready(void);
void android_session_tracer_ready(void);

#endif
