#include "policy.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAXA 32
#define MAXH 256

/* y[o] = b[o] + sum_i W[o*in + i] * x[i]   (PyTorch-Layout: weight[out][in]) */
static void linear(const float *W, const float *b, const float *x, int in, int out, float *y)
{
    for (int o = 0; o < out; o++) {
        const float *w = W + (size_t)o * in;
        float s = b[o];
        for (int i = 0; i < in; i++)
            s += w[i] * x[i];
        y[o] = s;
    }
}

static void tanh_inplace(float *x, int n)
{
    for (int i = 0; i < n; i++)
        x[i] = tanhf(x[i]);
}

int policy_load(policy_t *p, const char *path)
{
    FILE *f = fopen(path, "rb");
    if (!f) { perror(path); return -1; }
    uint32_t hdr[5];
    if (fread(hdr, sizeof(uint32_t), 5, f) != 5 || hdr[0] != POLICY_MAGIC) {
        fprintf(stderr, "policy: %s ist keine gueltige policy.bin\n", path);
        fclose(f);
        return -1;
    }
    p->H = (int)hdr[1]; p->De = (int)hdr[2]; p->Dsg = (int)hdr[3]; p->Na = (int)hdr[4];
    int H = p->H, De = p->De, Dsg = p->Dsg, Na = p->Na;
    if (H > MAXH || Na > 32) { fclose(f); return -1; }

    size_t sizes[14] = {
        (size_t)H * De, H, (size_t)H * H, H,           /* embed */
        (size_t)H * H, H, (size_t)H * H, H, (size_t)H * H, H,   /* q k v */
        (size_t)H * (3 * H + Dsg), H, (size_t)Na * H, Na /* actor */
    };
    size_t total = 0;
    for (int i = 0; i < 14; i++) total += sizes[i];
    p->blob = malloc(total * sizeof(float));
    if (!p->blob || fread(p->blob, sizeof(float), total, f) != total) {
        fprintf(stderr, "policy: Datei zu kurz\n");
        fclose(f);
        return -1;
    }
    fclose(f);

    float **dst[14] = { &p->emb1_w, &p->emb1_b, &p->emb2_w, &p->emb2_b,
                        &p->q_w, &p->q_b, &p->k_w, &p->k_b, &p->v_w, &p->v_b,
                        &p->act1_w, &p->act1_b, &p->act2_w, &p->act2_b };
    float *cur = p->blob;
    for (int i = 0; i < 14; i++) { *dst[i] = cur; cur += sizes[i]; }
    return 0;
}

void policy_act(const policy_t *p, int n, const float *rows, int stride, uint8_t *actions)
{
    const int H = p->H, De = p->De, Dsg = p->Dsg, Na = p->Na;
    static float emb[MAXA][MAXH], q[MAXA][MAXH], k[MAXA][MAXH], v[MAXA][MAXH];
    float tmp[MAXH], x[3 * MAXH + 64], hid[MAXH], logits[32], score[MAXA];

    if (n > MAXA) n = MAXA;

    /* Embedding + q/k/v fuer jeden Agenten */
    for (int a = 0; a < n; a++) {
        const float *ent = rows + (size_t)a * stride + 1;
        linear(p->emb1_w, p->emb1_b, ent, De, H, tmp);
        tanh_inplace(tmp, H);
        linear(p->emb2_w, p->emb2_b, tmp, H, H, emb[a]);
        tanh_inplace(emb[a], H);
        linear(p->q_w, p->q_b, emb[a], H, H, q[a]);
        linear(p->k_w, p->k_b, emb[a], H, H, k[a]);
        linear(p->v_w, p->v_b, emb[a], H, H, v[a]);
    }

    const float scale = 1.0f / sqrtf((float)H);
    for (int a = 0; a < n; a++) {
        const float *row = rows + (size_t)a * stride;
        if (row[0] < 0.5f) { actions[a] = 0; continue; }     /* tot -> egal */

        /* maskierte Softmax-Attention ueber lebende Agenten (alle im selben Team) */
        float mx = -INFINITY;
        for (int j = 0; j < n; j++) {
            if (rows[(size_t)j * stride] < 0.5f) { score[j] = -INFINITY; continue; }
            float s = 0.0f;
            for (int h = 0; h < H; h++) s += q[a][h] * k[j][h];
            score[j] = s * scale;
            if (score[j] > mx) mx = score[j];
        }
        float sum = 0.0f;
        for (int j = 0; j < n; j++) {
            score[j] = (score[j] == -INFINITY) ? 0.0f : expf(score[j] - mx);
            sum += score[j];
        }
        float *pool = x + H;
        memset(pool, 0, sizeof(float) * H);
        if (sum > 0.0f)
            for (int j = 0; j < n; j++) {
                float w = score[j] / sum;
                if (w == 0.0f) continue;
                for (int h = 0; h < H; h++) pool[h] += w * v[j][h];
            }

        /* x = [emb, pool_ally, pool_enemy(=0, ein Team), self_global] */
        memcpy(x, emb[a], sizeof(float) * H);
        memset(x + 2 * H, 0, sizeof(float) * H);
        memcpy(x + 3 * H, row + 1 + De, sizeof(float) * Dsg);

        linear(p->act1_w, p->act1_b, x, 3 * H + Dsg, H, hid);
        tanh_inplace(hid, H);
        linear(p->act2_w, p->act2_b, hid, H, Na, logits);

        int best = 0;
        for (int i = 1; i < Na; i++) if (logits[i] > logits[best]) best = i;
        actions[a] = (uint8_t)best;
    }
}
