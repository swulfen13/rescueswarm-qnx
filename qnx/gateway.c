/*
 * RescueSwarm – gateway (QNX)
 *
 * Nimmt den Schwarm-Zustand per UDP von der PC-Simulation entgegen, reicht ihn
 * per QNX-Message-Passing (MsgSend) an den controller weiter und schickt dessen
 * Antwort per UDP zurueck.
 *
 * Ist der controller nicht erreichbar (abgestuerzt, wird neu gestartet), antwortet
 * das gateway sofort mit "alle schweben" und versucht, sich neu zu verbinden.
 * So bekommt die Simulation in jedem Takt eine Antwort.
 */
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <sys/dispatch.h>
#include <sys/neutrino.h>
#include <sys/syspage.h>
#include <inttypes.h>
#include <pthread.h>
#include <sched.h>

#include "proto.h"

typedef struct {
    uint16_t type;
    uint16_t subtype;
    rs_obs_t obs;
} ctrl_msg_t;

static int ctrl_coid = -1;

static int connect_ctrl(void)
{
    if (ctrl_coid != -1)
        return ctrl_coid;
    ctrl_coid = name_open(RS_CTRL_NAME, 0);
    if (ctrl_coid != -1) {
        printf("gateway: mit controller verbunden (coid=%d)\n", ctrl_coid);
        fflush(stdout);
    }
    return ctrl_coid;
}

int main(int argc, char **argv)
{
    int port = RS_PORT, opt;
    while ((opt = getopt(argc, argv, "P:r:")) != -1) {
        if (opt == 'P') port = atoi(optarg);
        else if (opt == 'r') {
            struct sched_param sp = { .sched_priority = atoi(optarg) };
            int rc = pthread_setschedparam(pthread_self(), SCHED_FIFO, &sp);
            printf("gateway: Echtzeit-Prioritaet FIFO %s %s\n", optarg, rc == 0 ? "gesetzt" : "NICHT gesetzt");
        }
    }

    int s = socket(AF_INET, SOCK_DGRAM, 0);
    if (s < 0) { perror("socket"); return EXIT_FAILURE; }
    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = htonl(INADDR_ANY);
    addr.sin_port = htons((uint16_t)port);
    if (bind(s, (struct sockaddr *)&addr, sizeof(addr)) < 0) { perror("bind"); return EXIT_FAILURE; }
    printf("gateway: lausche auf UDP-Port %d\n", port);
    fflush(stdout);

    uint64_t cps = SYSPAGE_ENTRY(qtime)->cycles_per_sec;
    static ctrl_msg_t msg;
    static uint8_t buf[sizeof(rs_obs_t)];
    uint32_t fallbacks = 0, handled = 0, outage = 0;

    for (;;) {
        struct sockaddr_in from;
        socklen_t flen = sizeof(from);
        ssize_t len = recvfrom(s, buf, sizeof(buf), 0, (struct sockaddr *)&from, &flen);
        if (len < (ssize_t)RS_OBS_HEADER_BYTES) continue;
        uint64_t t0 = ClockCycles();

        memset(&msg, 0, sizeof(msg));
        memcpy(&msg.obs, buf, (size_t)len);
        if (msg.obs.magic != RS_MAGIC_OBS || msg.obs.n_agents > RS_MAX_AGENTS
            || msg.obs.agent_floats != RS_AGENT_FLOATS)
            continue;
        msg.type = RS_MSG_OBS;

        rs_act_t rep;
        memset(&rep, 0, sizeof(rep));
        int ok = 0;
        if (connect_ctrl() != -1) {
            if (MsgSend(ctrl_coid, &msg, sizeof(msg), &rep, sizeof(rep)) != -1)
                ok = 1;
            else {                                   /* controller weg -> Verbindung verwerfen */
                name_close(ctrl_coid);
                ctrl_coid = -1;
            }
        }
        if (ok && outage > 0) {
            printf("gateway: controller wieder da nach %" PRIu32 " Takten im Notbetrieb (schweben)\n", outage);
            fflush(stdout);
            outage = 0;
        }
        if (!ok) {
            outage++;
            memset(&rep, 0, sizeof(rep));
            rep.magic = RS_MAGIC_ACT;
            rep.seq = msg.obs.seq;
            rep.n_agents = msg.obs.n_agents;
            rep.flags = RS_FLAG_FALLBACK;            /* actions bleiben 0 = schweben */
            fallbacks++;
        }
        rep.roundtrip_us = (uint32_t)((ClockCycles() - t0) * 1000000ull / cps);

        sendto(s, &rep, RS_ACT_HEADER_BYTES + rep.n_agents, 0, (struct sockaddr *)&from, flen);

        if (++handled % 500 == 0) {
            printf("gateway: %" PRIu32 " Takte, %" PRIu32 " Fallbacks\n", handled, fallbacks);
            fflush(stdout);
        }
    }
}
