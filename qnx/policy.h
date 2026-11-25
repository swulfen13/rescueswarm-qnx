/*
 * RescueSwarm – KI-Policy in reinem C (ohne Framework).
 *
 * Nachbau von swarm_sim/attn.py: AttnActorCritic.actor_logits()
 *   emb   = tanh(W2 * tanh(W1 * entity + b1) + b2)        (Embedding, H=128)
 *   q,k,v = Linear(emb)
 *   pool  = maskierte Single-Head-Attention ueber lebende Teamkollegen
 *   logits = W4 * tanh(W3 * [emb, pool_ally, pool_enemy(=0), self_global] + b3) + b4
 * Aktion = argmax(logits)  (wie show_netcov.py)
 *
 * Gewichte kommen aus policy.bin (erzeugt von pc/export_policy.py).
 */
#ifndef RS_POLICY_H
#define RS_POLICY_H

#include <stdint.h>

#define POLICY_MAGIC 0x31504352u   /* "RCP1" */

typedef struct {
    int H, De, Dsg, Na;
    float *emb1_w, *emb1_b, *emb2_w, *emb2_b;
    float *q_w, *q_b, *k_w, *k_b, *v_w, *v_b;
    float *act1_w, *act1_b, *act2_w, *act2_b;
    float *blob;
} policy_t;

/* Laedt policy.bin. Rueckgabe 0 = ok. */
int policy_load(policy_t *p, const char *path);

/*
 * n Agenten, je Zeile: alive(1) + entities(De) + self_global(Dsg)  (Layout aus proto.h)
 * stride = Floats pro Zeile. actions: n Ausgaben.
 */
void policy_act(const policy_t *p, int n, const float *rows, int stride, uint8_t *actions);

#endif
