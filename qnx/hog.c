/*
 * RescueSwarm – hog (QNX): Stoerenfried fuer den Stresstest.
 * Startet N Threads, die die CPU zu 100 % belegen (z. B. eine Kamera-Bildverarbeitung,
 * die aus dem Ruder laeuft).
 *
 *   hog [-t Threads] [-s Sekunden] [-r Prio]
 *
 * Die Last-Threads laufen mit SCHED_RR (Zeitscheiben) und Prioritaet -r (Standard 10 =
 * normale Anwendungsprioritaet). Der Haupt-Thread laeuft mit FIFO 60, damit er nach
 * -s Sekunden garantiert aufwacht und den Spuk beendet.
 */
#include <pthread.h>
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static int prio = 10;
static volatile unsigned long sink;

static void *burn(void *arg)
{
    (void)arg;
    struct sched_param sp = { .sched_priority = prio };
    pthread_setschedparam(pthread_self(), SCHED_RR, &sp);
    for (;;) sink++;
    return NULL;
}

int main(int argc, char **argv)
{
    int threads = 4, secs = 15, opt;
    while ((opt = getopt(argc, argv, "t:s:r:")) != -1) {
        if (opt == 't') threads = atoi(optarg);
        else if (opt == 's') secs = atoi(optarg);
        else if (opt == 'r') prio = atoi(optarg);
    }
    struct sched_param mp = { .sched_priority = 60 };
    pthread_setschedparam(pthread_self(), SCHED_FIFO, &mp);
    printf("hog: %d Threads, %d s, RR-Prio %d\n", threads, secs, prio);
    fflush(stdout);
    for (int i = 0; i < threads; i++) {
        pthread_t t;
        pthread_create(&t, NULL, burn, NULL);
    }
    sleep(secs);
    return 0;
}
