/* Internal deterministic math helpers; mirrored exactly by training/src/ultratiny/reference.py. */
#ifndef UT_MATHX_H
#define UT_MATHX_H

#include <stddef.h>
#include <stdint.h>

float ut_expf(float x);
float ut_round_half_away(float v);
/* Per-vector absmax int8 quantization; returns the scale. */
float ut_quantize(const float *x, int n, int8_t *q);
/* y[r] = ((float)dot(w[r], xq) * w_scale[r]) * xs */
void ut_matvec(const int8_t *w, const float *w_scale, int rows, int cols, const int8_t *xq,
               float xs, float *y);
int32_t ut_dot_i8(const int8_t *a, const int8_t *b, int n);
void ut_rmsnorm(const float *x, const float *g, int n, float eps, float *y);
/* In-place softmax over n values. */
void ut_softmax(float *z, int n);

#endif
