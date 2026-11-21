/*
 * Deterministic math (research.md R4/R5). Every operation here has a 1:1 float32
 * counterpart in training/src/ultratiny/reference.py; keep them in sync. Build with
 * -ffp-contract=off so no fused multiply-add changes rounding.
 */
#include "mathx.h"

#include <math.h>

/* Exact float32 values as hex literals (identical constants in reference.py). */
#define UT_LOG2E 0x1.715476p+0f
#define UT_LN2_HI 0x1.62e4p-1f
#define UT_LN2_LO 0x1.7f7d1cp-20f
#define UT_C720 0x1.6c16c2p-10f
#define UT_C120 0x1.111112p-7f
#define UT_C24 0x1.555556p-5f
#define UT_C6 0x1.555556p-3f
#define UT_EXP_MIN (-80.0f)

/* exp(x) for x <= 0 via range reduction + degree-6 Taylor polynomial (Horner). */
float ut_expf(float x) {
    if (x < UT_EXP_MIN) return 0.0f;
    float n = floorf(x * UT_LOG2E + 0.5f);
    float r = x - n * UT_LN2_HI;
    r = r - n * UT_LN2_LO;
    float p = UT_C720;
    p = p * r + UT_C120;
    p = p * r + UT_C24;
    p = p * r + UT_C6;
    p = p * r + 0.5f;
    p = p * r + 1.0f;
    p = p * r + 1.0f;
    return ldexpf(p, (int)n);
}

float ut_round_half_away(float v) {
    float mag = floorf(fabsf(v) + 0.5f);
    return v < 0.0f ? -mag : mag;
}

float ut_quantize(const float *x, int n, int8_t *q) {
    float amax = 0.0f;
    for (int i = 0; i < n; i++) {
        float a = fabsf(x[i]);
        if (a > amax) amax = a;
    }
    if (amax == 0.0f) {
        for (int i = 0; i < n; i++) q[i] = 0;
        return 1.0f;
    }
    float scale = amax / 127.0f;
    for (int i = 0; i < n; i++) {
        float v = ut_round_half_away(x[i] / scale);
        if (v > 127.0f) v = 127.0f;
        if (v < -127.0f) v = -127.0f;
        q[i] = (int8_t)v;
    }
    return scale;
}

int32_t ut_dot_i8(const int8_t *a, const int8_t *b, int n) {
    int32_t acc = 0;
    int i = 0;
    for (; i + 4 <= n; i += 4) {
        acc += (int32_t)a[i] * b[i] + (int32_t)a[i + 1] * b[i + 1] +
               (int32_t)a[i + 2] * b[i + 2] + (int32_t)a[i + 3] * b[i + 3];
    }
    for (; i < n; i++) acc += (int32_t)a[i] * b[i];
    return acc;
}

void ut_matvec(const int8_t *w, const float *w_scale, int rows, int cols, const int8_t *xq,
               float xs, float *y) {
    for (int r = 0; r < rows; r++) {
        int32_t acc = ut_dot_i8(w + (size_t)r * cols, xq, cols);
        y[r] = ((float)acc * w_scale[r]) * xs;
    }
}

void ut_rmsnorm(const float *x, const float *g, int n, float eps, float *y) {
    float ss = 0.0f;
    for (int i = 0; i < n; i++) ss += x[i] * x[i];
    float ms = ss / (float)n;
    float inv = 1.0f / sqrtf(ms + eps);
    for (int i = 0; i < n; i++) y[i] = (x[i] * inv) * g[i];
}

void ut_softmax(float *z, int n) {
    float m = z[0];
    for (int i = 1; i < n; i++)
        if (z[i] > m) m = z[i];
    float total = 0.0f;
    for (int i = 0; i < n; i++) {
        z[i] = ut_expf(z[i] - m);
        total += z[i];
    }
    for (int i = 0; i < n; i++) z[i] = z[i] / total;
}
