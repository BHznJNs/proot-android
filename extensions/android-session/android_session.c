/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Optional Android-owned, noninteractive PRoot session. */
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/prctl.h>
#include <sys/wait.h>
#include <unistd.h>

#include "extension/android_session/android_session.h"

static volatile sig_atomic_t stop_requested;
static bool session_worker;

static void request_stop(int signum)
{
    (void)signum;
    stop_requested = 1;
}

/* Only the opt-in session worker changes its inherited signal mask. */
void android_session_guest_ready(void)
{
    if (session_worker) {
        sigset_t empty;
        sigemptyset(&empty);
        if (sigprocmask(SIG_SETMASK, &empty, NULL) < 0) {
            perror("android-session: guest signal mask");
            _exit(71);
        }
    }
}

void android_session_tracer_ready(void)
{
    if (session_worker) {
        sigset_t quit;
        sigemptyset(&quit);
        sigaddset(&quit, SIGQUIT);
        /* A stop or parent death during startup stays pending until PRoot
         * has installed its tracee-cleanup handler. */
        if (sigprocmask(SIG_UNBLOCK, &quit, NULL) < 0) {
            perror("android-session: tracer signal mask");
            exit(71);
        }
    }
}

int android_session_main(int argc, char *const argv[], android_session_entry_t entry)
{
    if (argc < 3) {
        fputs("Usage: proot --android-session [proot options] command [args...]\n", stderr);
        return 64;
    }
    char **worker_argv = calloc((size_t)argc, sizeof(*worker_argv));
    if (worker_argv == NULL) return 71;
    worker_argv[0] = argv[0];
    for (int i = 2; i < argc; i++) worker_argv[i - 1] = argv[i];

    struct sigaction action = { .sa_handler = request_stop };
    sigemptyset(&action.sa_mask);
    if (sigaction(SIGTERM, &action, NULL) < 0 ||
        sigaction(SIGINT, &action, NULL) < 0 ||
        sigaction(SIGQUIT, &action, NULL) < 0 ||
        signal(SIGPIPE, SIG_IGN) == SIG_ERR) {
        perror("android-session: signal handler");
        free(worker_argv);
        return 71;
    }

    /* Clear ART's inherited mask, but block QUIT across fork so an early
     * stop cannot terminate the tracer before its cleanup handler exists. */
    sigset_t mask;
    sigemptyset(&mask);
    sigaddset(&mask, SIGQUIT);
    if (sigprocmask(SIG_SETMASK, &mask, NULL) < 0) {
        perror("android-session: signal mask");
        free(worker_argv);
        return 71;
    }
    pid_t owner = getpid();
    pid_t child = fork();
    if (child < 0) {
        perror("android-session: fork");
        free(worker_argv);
        return 71;
    }
    if (child == 0) {
        session_worker = true;
        signal(SIGTERM, SIG_DFL);
        signal(SIGINT, SIG_DFL);
        signal(SIGQUIT, SIG_DFL);
        if (prctl(PR_SET_PDEATHSIG, SIGQUIT) < 0) {
            perror("android-session: parent death signal");
            _exit(71);
        }
        if (getppid() != owner) _exit(125);
        int input = open("/dev/null", O_RDONLY);
        if (input < 0 || (input != STDIN_FILENO && dup2(input, STDIN_FILENO) < 0)) {
            perror("android-session: guest stdin");
            _exit(71);
        }
        if (input != STDIN_FILENO) close(input);
        /* Enter normal PRoot before talloc or tracees have been created.
         * No executable lookup or separate supervisor binary is needed. */
        exit(entry(argc - 1, worker_argv));
    }
    free(worker_argv);
    sigemptyset(&mask);
    if (sigprocmask(SIG_SETMASK, &mask, NULL) < 0) {
        /* QUIT is blocked only in this exceptional parent; keep reaping. */
        perror("android-session: owner signal mask");
        stop_requested = 1;
    }

    bool signalled = false;
    int status;
    for (;;) {
        pid_t result = waitpid(child, &status, WNOHANG);
        if (result == child) break;
        if (result < 0) {
            if (errno == EINTR) continue;
            perror("android-session: waitpid");
            return 71;
        }
        struct pollfd control = { .fd = STDIN_FILENO, .events = POLLIN | POLLHUP };
        int ready = poll(signalled ? NULL : &control, signalled ? 0 : 1, 100);
        if (ready < 0 && errno != EINTR) stop_requested = 1;
        if (ready > 0 && !signalled) {
            if (control.revents & (POLLERR | POLLNVAL)) stop_requested = 1;
            else {
                char byte;
                ssize_t count = read(STDIN_FILENO, &byte, 1);
                if (count == 0 || (count > 0 && byte == 'q') ||
                    (count < 0 && errno != EINTR && errno != EAGAIN))
                    stop_requested = 1;
            }
        }
        if (stop_requested && !signalled) {
            /* Preserve the existing immediate cleanup semantics: PRoot's
             * QUIT handler kills tracees and drains its wait loop. */
            if (kill(child, SIGQUIT) == 0 || errno == ESRCH) signalled = true;
            else perror("android-session: stop");
        }
    }
    return WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status);
}
