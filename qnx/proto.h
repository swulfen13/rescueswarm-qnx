/*
 * RescueSwarm – gemeinsames Protokoll zwischen PC-Simulation und QNX.
 *
 * PC  --UDP-->  gateway (QNX)  --MsgSend-->  controller (QNX)
 * PC  <--UDP--  gateway (QNX)  <--MsgReply-- controller (QNX)
 *
 * Alle Zahlen little-endian (x86_64 auf beiden Seiten).
 */
#ifndef RS_PROTO_H
#define RS_PROTO_H

#include <stdint.h>

#define RS_PORT          5555
#define RS_MAX_AGENTS    32
#define RS_ENT_DIM       7    /* pos_x, pos_y, alt, vx, vy, vz, batt (alles normiert) */
#define RS_SG_DIM        16   /* siehe Spaltenindizes unten */
#define RS_TG_DIM        3    /* served_frac, connected_frac, mean_batt */
#define RS_AGENT_FLOATS  (1 + RS_ENT_DIM + RS_SG_DIM)   /* alive + entities + self_global = 24 */

#define RS_MAGIC_OBS     0x31575352u   /* "RSW1" */
#define RS_MAGIC_ACT     0x31415352u   /* "RSA1" */

/* Spalten einer Agenten-Zeile */
enum {
    C_ALIVE = 0,
    C_POS_X, C_POS_Y, C_ALT, C_VX, C_VY, C_VZ, C_BATT_E,
    C_UP_DX, C_UP_DY, C_UP_D,          /* Richtung + Distanz zum Uplink       */
    C_ST_DX, C_ST_DY, C_ST_D,          /* ... zur naechsten Ladestation        */
    C_GAP_DX, C_GAP_DY, C_GAP_D,       /* ... zum naechsten unversorgten Hotspot */
    C_BATT, C_CONN, C_WIND_X, C_WIND_Y,
    C_BATT_RANK, C_FRAC_CHARGING, C_FRAC_BELOW
};

/* Aktionen (identisch zu swarm_sim/env_netcov.py: _DIRS) */
#define RS_ACT_HOVER 0      /* 1..8 = Horizontalrichtung k*45 Grad, 9 = hoch, 10 = runter */
#define RS_ACT_UP    9
#define RS_ACT_DOWN  10

#pragma pack(push, 1)
typedef struct {
    uint32_t magic;
    uint32_t seq;
    uint16_t n_agents;
    uint16_t agent_floats;
    float    reserve;          /* Sicherheitsreserve Akku, 0..1 */
    float    diag_m;           /* Kartendiagonale in Metern (Distanzen sind dadurch normiert) */
    float    team_global[RS_TG_DIM];
    float    agents[RS_MAX_AGENTS][RS_AGENT_FLOATS];   /* nur n_agents Zeilen werden uebertragen */
} rs_obs_t;

#define RS_OBS_HEADER_BYTES (4 + 4 + 2 + 2 + 4 + 4 + 4 * RS_TG_DIM)

/* flags */
#define RS_FLAG_FALLBACK   0x0001   /* Controller nicht erreichbar -> Gateway hat "schweben" geantwortet */
#define RS_FLAG_SAFETY     0x0002   /* Sicherheitswaechter hat mindestens eine KI-/Regel-Entscheidung ueberstimmt */

typedef struct {
    uint32_t magic;
    uint32_t seq;
    uint16_t n_agents;
    uint16_t flags;
    uint32_t compute_us;       /* Rechenzeit Controller (Mikrosekunden) */
    uint32_t roundtrip_us;     /* Gateway: UDP rein -> UDP raus */
    uint16_t n_charging;       /* wie viele Drohnen der Waechter gerade zum Laden schickt */
    uint16_t n_overrides;      /* wie oft der Waechter in diesem Schritt eingegriffen hat */
    uint8_t  actions[RS_MAX_AGENTS];
} rs_act_t;
#pragma pack(pop)

#define RS_ACT_HEADER_BYTES (4 + 4 + 2 + 2 + 4 + 4 + 2 + 2)

/* QNX-Message zwischen gateway und controller */
#define RS_CTRL_NAME   "rescueswarm_ctrl"
#define RS_MSG_OBS     0x5201

#endif
