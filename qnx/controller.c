/*
 * RescueSwarm – controller (QNX)
 *
 * Wartet per QNX-Message-Passing (name_attach / MsgReceive) auf den Zustand
 * des Schwarms und antwortet (MsgReply) mit einer Aktion pro Drohne.
 *
 * Zwei Schichten:
 *   1. Flug-Logik   – wohin soll jede Drohne? (vorerst Regeln, spaeter die KI-Policy in C)
 *   2. Sicherheits-Waechter – ueberstimmt Schicht 1, wenn der Akku es verlangt,
 *      und sorgt dafuer, dass nie alle Drohnen gleichzeitig laden
 *      (loest den "Saegezahn" aus dem RL-Training).
 */
#include <errno.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/dispatch.h>
#include <sys/neutrino.h>
#include <sys/iomsg.h>
#include <sys/syspage.h>
#include <inttypes.h>
#include <pthread.h>
#include <sched.h>

#include "proto.h"
#include "policy.h"

typedef struct {
    uint16_t type;
    uint16_t subtype;
    rs_obs_t obs;
} ctrl_msg_t;

typedef union {
    uint16_t          type;
    struct _pulse     pulse;
    ctrl_msg_t        ctrl;
} recv_buf_t;

/* ---- Parameter des Sicherheits-Waechters ---- */
#define CHARGE_START_MARGIN 0.15f   /* ab reserve + 15 % darf geladen werden          */
#define CHARGE_DONE         0.95f   /* bis 95 % laden                                   */
#define MAX_CHARGING_FRAC   0.30f   /* hoechstens 30 % des Schwarms laden gleichzeitig  */
#define HOLD_STATION_M      100.0f  /* nur noch v1 (alt): naeher als 100 m an der Station schweben */
#define HOLD_GAP_M          120.0f  /* naeher als 120 m am Hotspot: schweben und versorgen */
#define MIN_ALT_N           0.25f   /* unter 25 % der erlaubten Hoehe: steigen */
/* Wind-kompensierte Lade-Steuerung (v2). Drohnen-Grenzen wie in netzabdeckung_config.yaml. */
#define V_MAX               15.0f   /* m/s,  drone.max_geschwindigkeit_ms   */
#define A_MAX               5.0f    /* m/s2, drone.max_beschleunigung_ms2   */
#define STEER_TAU           1.5f    /* s, wie schnell die Wunschgeschwindigkeit erreicht werden soll */
#define APPROACH_GAIN       0.3f    /* Wunschtempo = (Distanz - 40 m) * 0.3, max V_MAX */
#define APPROACH_OFFSET_M   40.0f

static uint8_t charging_state[RS_MAX_AGENTS];   /* 1 = Waechter schickt Drohne zum Laden */

static uint8_t dir_to_action(float dx, float dy)
{
    if (fabsf(dx) < 1e-6f && fabsf(dy) < 1e-6f)
        return RS_ACT_HOVER;
    float a = atan2f(dy, dx);                       /* -pi..pi */
    int k = (int)lroundf(a / (float)(M_PI / 4.0));  /* -4..4 */
    k = ((k % 8) + 8) % 8;
    return (uint8_t)(1 + k);
}

/* Schicht 1: Flug-Logik (Platzhalter fuer die KI-Policy) */
static uint8_t flight_logic(const float *row, float diag)
{
    if (row[C_ALT] < MIN_ALT_N)
        return RS_ACT_UP;
    if (row[C_GAP_D] * diag < HOLD_GAP_M)
        return RS_ACT_HOVER;
    return dir_to_action(row[C_GAP_DX], row[C_GAP_DY]);
}

/* Schicht 2: Sicherheits-Waechter. Gibt die Anzahl der Eingriffe zurueck. */
/* Waechter-Steuerung zur Ladestation (v2): Wunschgeschwindigkeit zeigt zur Station und wird
 * kurz davor null; die noetige Beschleunigung ist (v_soll - v)/tau minus Wind. Gewaehlt wird die
 * der 9 Aktionen (schweben + 8 Richtungen), deren Schub dem am naechsten kommt.
 * v1 flog stur geradeaus und "schwebte" am Ziel -- schweben haelt aber die Geschwindigkeit,
 * und Wind schob die Drohnen weg. */
static uint8_t steer_to_station(const float *r, float diag_m)
{
    float d = r[C_ST_D] * diag_m;
    float speed = (d - APPROACH_OFFSET_M) * APPROACH_GAIN;
    if (speed < 0.0f) speed = 0.0f;
    if (speed > V_MAX) speed = V_MAX;
    float ax = (r[C_ST_DX] * speed - r[C_VX] * V_MAX) / STEER_TAU - r[C_WIND_X] * V_MAX;
    float ay = (r[C_ST_DY] * speed - r[C_VY] * V_MAX) / STEER_TAU - r[C_WIND_Y] * V_MAX;
    uint8_t best = RS_ACT_HOVER;
    float best_e = ax * ax + ay * ay;                 /* schweben = kein eigener Schub */
    for (int k = 0; k < 8; k++) {
        float c = cosf((float)M_PI * k / 4.0f) * A_MAX, s = sinf((float)M_PI * k / 4.0f) * A_MAX;
        float e = (ax - c) * (ax - c) + (ay - s) * (ay - s);
        if (e < best_e) { best_e = e; best = (uint8_t)(1 + k); }
    }
    return best;
}

static int safety_guard(const rs_obs_t *o, uint8_t *act, uint16_t *n_charging_out)
{
    int n = o->n_agents, overrides = 0, alive = 0, charging = 0;
    float reserve = o->reserve;

    for (int i = 0; i < n; i++) {
        const float *r = o->agents[i];
        if (r[C_ALIVE] < 0.5f) { charging_state[i] = 0; continue; }
        alive++;
        if (charging_state[i] && r[C_BATT] >= CHARGE_DONE)
            charging_state[i] = 0;                        /* fertig geladen */
        if (r[C_BATT] < reserve)
            charging_state[i] = 1;                        /* Pflicht: unter Reserve -> immer laden */
        charging += charging_state[i];
    }

    /* Freie Lade-Slots an die Drohnen mit dem niedrigsten Akku vergeben */
    int limit = (int)ceilf(alive * MAX_CHARGING_FRAC);
    while (charging < limit) {
        int best = -1; float best_b = 2.0f;
        for (int i = 0; i < n; i++) {
            const float *r = o->agents[i];
            if (r[C_ALIVE] < 0.5f || charging_state[i]) continue;
            if (r[C_BATT] < reserve + CHARGE_START_MARGIN && r[C_BATT] < best_b) {
                best = i; best_b = r[C_BATT];
            }
        }
        if (best < 0) break;
        charging_state[best] = 1;
        charging++;
    }

    for (int i = 0; i < n; i++) {
        const float *r = o->agents[i];
        if (r[C_ALIVE] < 0.5f || !charging_state[i]) continue;
        uint8_t a = steer_to_station(r, o->diag_m);
        if (a != act[i]) overrides++;
        act[i] = a;
    }
    *n_charging_out = (uint16_t)charging;
    return overrides;
}

static policy_t policy;
static int use_policy = 0;
static int use_safety = 1;

int main(int argc, char **argv)
{
    /* Aufruf: controller [-p policy.bin] [-n] [-r prio]  (-n = Waechter aus, -r = SCHED_FIFO-Prioritaet) */
    int opt;
    while ((opt = getopt(argc, argv, "p:nr:")) != -1) {
        if (opt == 'p') {
            if (policy_load(&policy, optarg) != 0) return EXIT_FAILURE;
            use_policy = 1;
            printf("controller: KI-Policy geladen (%s, H=%d, %d Aktionen)\n", optarg, policy.H, policy.Na);
        } else if (opt == 'n') {
            use_safety = 0;
        } else if (opt == 'r') {
            struct sched_param sp = { .sched_priority = atoi(optarg) };
            int rc = pthread_setschedparam(pthread_self(), SCHED_FIFO, &sp);
            printf("controller: Echtzeit-Prioritaet FIFO %s %s\n", optarg, rc == 0 ? "gesetzt" : "NICHT gesetzt");
        }
    }
    printf("controller: Flug = %s, Sicherheitswaechter = %s\n",
           use_policy ? "KI-Policy" : "Regeln", use_safety ? "AN" : "AUS");

    name_attach_t *att = name_attach(NULL, RS_CTRL_NAME, 0);
    if (att == NULL) {
        perror("name_attach");
        return EXIT_FAILURE;
    }
    printf("controller: bereit (Name '%s', chid=%d)\n", RS_CTRL_NAME, att->chid);
    fflush(stdout);

    uint64_t cps = SYSPAGE_ENTRY(qtime)->cycles_per_sec;
    static recv_buf_t msg;

    for (;;) {
        int rcvid = MsgReceive(att->chid, &msg, sizeof(msg), NULL);
        if (rcvid == -1) { perror("MsgReceive"); continue; }

        if (rcvid == 0) {                                   /* Puls */
            if (msg.pulse.code == _PULSE_CODE_DISCONNECT)
                ConnectDetach(msg.pulse.scoid);
            continue;
        }
        if (msg.type == _IO_CONNECT) {                      /* name_open() eines Clients */
            MsgReply(rcvid, EOK, NULL, 0);
            continue;
        }
        if (msg.type != RS_MSG_OBS) {
            MsgError(rcvid, ENOSYS);
            continue;
        }

        uint64_t t0 = ClockCycles();
        const rs_obs_t *o = &msg.ctrl.obs;
        rs_act_t rep;
        memset(&rep, 0, sizeof(rep));
        rep.magic = RS_MAGIC_ACT;
        rep.seq = o->seq;
        rep.n_agents = o->n_agents > RS_MAX_AGENTS ? RS_MAX_AGENTS : o->n_agents;

        if (use_policy)
            policy_act(&policy, rep.n_agents, &o->agents[0][0], RS_AGENT_FLOATS, rep.actions);
        else
            for (int i = 0; i < rep.n_agents; i++)
                rep.actions[i] = o->agents[i][C_ALIVE] < 0.5f ? RS_ACT_HOVER
                                                              : flight_logic(o->agents[i], o->diag_m);

        int ov = use_safety ? safety_guard(o, rep.actions, &rep.n_charging) : 0;
        rep.n_overrides = (uint16_t)ov;
        if (ov > 0) rep.flags |= RS_FLAG_SAFETY;
        rep.compute_us = (uint32_t)((ClockCycles() - t0) * 1000000ull / cps);

        MsgReply(rcvid, EOK, &rep, sizeof(rep));
    }
}
