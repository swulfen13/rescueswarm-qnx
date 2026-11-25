/*
 * RescueSwarm – watchdog (QNX)
 *
 * Startet controller und gateway als Kindprozesse (posix_spawn) und wartet mit
 * waitpid() auf ihr Ende. Stirbt einer (Absturz, kill, slay), wird er sofort neu
 * gestartet. Jede Erkennung und jeder Neustart wird mit Zeitstempel (us) geloggt.
 *
 *   watchdog [-p policy.bin] [-n] [-r prio]
 *     -p/-n werden an den controller durchgereicht, -r an controller und gateway.
 */
#include <errno.h>
#include <signal.h>
#include <spawn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <sys/wait.h>
#include <sys/neutrino.h>
#include <sys/syspage.h>
#include <inttypes.h>

extern char **environ;

typedef struct {
    const char *name;
    char *argv[12];
    pid_t pid;
    unsigned restarts;
} child_t;

static uint64_t cps;
static uint64_t now_us(void) { return ClockCycles() * 1000000ull / cps; }

static pid_t start_child(child_t *c)
{
    pid_t pid;
    int rc = posix_spawn(&pid, c->argv[0], NULL, NULL, c->argv, environ);
    if (rc != 0) {
        fprintf(stderr, "watchdog: %s konnte nicht gestartet werden: %s\n", c->name, strerror(rc));
        return -1;
    }
    return pid;
}

int main(int argc, char **argv)
{
    cps = SYSPAGE_ENTRY(qtime)->cycles_per_sec;
    static child_t kids[2] = {
        { "controller", { "./controller" }, -1, 0 },
        { "gateway",    { "./gateway" },    -1, 0 },
    };
    int ca = 1, ga = 1;
    int opt;
    while ((opt = getopt(argc, argv, "p:nr:")) != -1) {
        if (opt == 'p') { kids[0].argv[ca++] = "-p"; kids[0].argv[ca++] = optarg; }
        else if (opt == 'n') { kids[0].argv[ca++] = "-n"; }
        else if (opt == 'r') {
            kids[0].argv[ca++] = "-r"; kids[0].argv[ca++] = optarg;
            kids[1].argv[ga++] = "-r"; kids[1].argv[ga++] = optarg;
        }
    }
    kids[0].argv[ca] = NULL;
    kids[1].argv[ga] = NULL;

    for (int i = 0; i < 2; i++) {
        kids[i].pid = start_child(&kids[i]);
        printf("watchdog: %s gestartet (pid %d)\n", kids[i].name, kids[i].pid);
        if (i == 0) usleep(200000);   /* controller zuerst, damit name_attach steht */
    }
    fflush(stdout);

    for (;;) {
        int status;
        pid_t dead = waitpid(-1, &status, 0);
        if (dead == -1) {
            if (errno == EINTR) continue;
            perror("waitpid");
            sleep(1);
            continue;
        }
        uint64_t t_detect = now_us();
        for (int i = 0; i < 2; i++) {
            if (kids[i].pid != dead) continue;
            const char *why = WIFSIGNALED(status) ? "Signal" : "Exit";
            int code = WIFSIGNALED(status) ? WTERMSIG(status) : WEXITSTATUS(status);
            kids[i].pid = start_child(&kids[i]);
            uint64_t t_up = now_us();
            kids[i].restarts++;
            printf("watchdog: %s beendet (%s %d) -> neu gestartet als pid %d in %" PRIu64 " us (Neustart Nr. %u)\n",
                   kids[i].name, why, code, kids[i].pid, t_up - t_detect, kids[i].restarts);
            fflush(stdout);
            if (kids[i].pid == -1) sleep(1);
        }
    }
}
