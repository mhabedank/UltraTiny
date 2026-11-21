/* Internal deterministic math helpers; mirrored exactly by training/src/ultratiny/reference.py. */
#ifndef UT_MATHX_H
#define UT_MATHX_H

#include <stddef.h>
#include <stdint.h>

/*
 * Word access to the model image (specs/005-nodemcu-port/contracts/runtime-image-access.md).
 * The ESP8266 faults on byte or 16-bit loads from memory-mapped flash, so every int8/byte read
 * from the model image goes through ut_ld32: one aligned 32-bit load. The may_alias type keeps
 * it a single load (no byte-wise memcpy on targets without unaligned access) and alias-safe.
 */
typedef uint32_t __attribute__((may_alias)) ut_u32_alias;

static inline uint32_t ut_ld32(const void *p) {
#ifdef UT_IMAGE_ACCESS_CHECK
    if (((uintptr_t)p & 3u) != 0) __builtin_trap(); /* works with NDEBUG, unlike assert */
#endif
    return *(const ut_u32_alias *)p;
}

/* Byte k (0..3) of a little-endian word as int8 (the model format is little-endian). */
static inline int8_t ut_i8_of(uint32_t w, int k) { return (int8_t)(uint8_t)(w >> (8 * k)); }

/* Copies n bytes starting at the 4-byte aligned `src` using only 32-bit loads. Reads the whole
 * last word, so `src` must be readable up to the next multiple of 4. */
void ut_copy_words(void *dst, const void *src, size_t n);

float ut_expf(float x);
float ut_round_half_away(float v);
/* Per-vector absmax int8 quantization; returns the scale. */
float ut_quantize(const float *x, int n, int8_t *q);
/* y[r] = ((float)dot(w[r], xq) * w_scale[r]) * xs */
void ut_matvec(const int8_t *w, const float *w_scale, int rows, int cols, const int8_t *xq,
               float xs, float *y);
/* Integer dot product; both vectors 4-byte aligned, read as 32-bit words (n % 4 == 0 on the fast
 * path; a tail is summed byte-wise and never occurs for valid models). */
int32_t ut_dot_i8(const int8_t *a, const int8_t *b, int n);
void ut_rmsnorm(const float *x, const float *g, int n, float eps, float *y);
/* In-place softmax over n values. */
void ut_softmax(float *z, int n);

#endif
