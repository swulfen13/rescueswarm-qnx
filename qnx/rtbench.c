/*
 * RescueSwarm – rtbench (QNX)
 *
 * Misst, wie puenktlich ein periodischer Regel-Takt aufwacht (wie die Flugsteuerung).
 * Schlaeft mit clock_nanosleep(TIMER_ABSTIME) jeweils bis zum naechsten Takt und
 * misst die Verspaetung (Jitter) in Mikrosekunden.
 *
 *   rtbench [-f Hz] [-s Sekunden] [-r Prio]    (-r = SCHED_FIFO mit dieser Prioritaet)
 *
 * Ausgabe: Median, 99 %, 99,9 %, Maximum der Verspaetung, Takte > 1 ms.
 */
#include <pthread.h>
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

static int cmp(const void *a, const void *b)
{
    long x = *(const long *)a, y = *(const long *)b;
    return (x > y) - (x < y);
}

static void add_ns(struct timespec *t, long ns)
{
    t->tv_nsec += ns;
    while (t->tv_nsec >= 1000000000L) { t->tv_nsec -= 1000000000L; t->tv_sec++; }
}

int main(int argc, char **argv)
{
    int hz = 1000, secs = 10, prio = 0, opt;
    while ((opt = getopt(argc, argv, "f:s:r:")) != -1) {
        if (opt == 'f') hz = atoi(optarg);
        else if (opt == 's') secs = atoi(optarg);
        else if (opt == 'r') prio = atoi(optarg);
    }
    if (prio > 0) {
        struct sched_param sp = { .sched_priority = prio };
        int rc = pthread_setschedparam(pthread_self(), SCHED_FIFO, &sp);
        if (rc != 0) fprintf(stderr, "rtbench: Prioritaet %d nicht gesetzt: %s\n", prio, strerror(rc));
    }

    long period = 1000000000L / hz;
    int n = hz * secs;
    long *late = malloc(sizeof(long) * n);
    struct timespec next, now;
    clock_gettime(CLOCK_MONOTONIC, &next);
    add_ns(&next, period);

    for (int i = 0; i < n; i++) {
        clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &next, NULL);
        clock_gettime(CLOCK_MONOTONIC, &now);
        late[i] = (now.tv_sec - next.tv_sec) * 1000000000L + (now.tv_nsec - next.tv_nsec);
        add_ns(&next, period);
    }

    int over1ms = 0;
    for (int i = 0; i < n; i++) if (late[i] > 1000000L) over1ms++;
    qsort(late, n, sizeof(long), cmp);
    char pdesc[32];
    if (prio > 0) snprintf(pdesc, sizeof pdesc, "FIFO %d", prio);
    else snprintf(pdesc, sizeof pdesc, "normal");
    printf("rtbench: %d Takte a %d Hz, Prio %s | Verspaetung us: Median %ld | 99%% %ld | 99.9%% %ld | max %ld | >1ms: %d\n",
           n, hz, pdesc,
           late[n / 2] / 1000, late[(int)(n * 0.99)] / 1000, late[(int)(n * 0.999)] / 1000,
           late[n - 1] / 1000, over1ms);
    return 0;
}
