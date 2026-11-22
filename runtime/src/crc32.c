#include "mathx.h"
#include "utiny.h"

/* Bitwise CRC-32 (IEEE, reflected, poly 0xEDB88320). Called once at boot, so no table.
 * Aligned data is read as 32-bit words via ut_ld32 (model images live in ESP8266 mapped flash,
 * where byte loads fault); the bytes of each word are fed in little-endian order, so the result
 * is identical to a byte-wise CRC. Unaligned buffers and a final partial word (never present in
 * a valid model image) fall back to byte reads. */
static uint32_t crc_byte(uint32_t crc, uint8_t b) {
    crc ^= b;
    for (int k = 0; k < 8; k++) crc = (crc >> 1) ^ (0xEDB88320u & (0u - (crc & 1u)));
    return crc;
}

uint32_t ut_crc32(const void *data, size_t n) {
    const uint8_t *p = (const uint8_t *)data;
    uint32_t crc = 0xFFFFFFFFu;
    size_t i = 0;
    if (((uintptr_t)p & 3u) == 0) {
        for (; i + 4 <= n; i += 4) {
            uint32_t w = ut_ld32(p + i);
            for (int k = 0; k < 4; k++) crc = crc_byte(crc, (uint8_t)(w >> (8 * k)));
        }
    }
    for (; i < n; i++) crc = crc_byte(crc, p[i]);
    return crc ^ 0xFFFFFFFFu;
}
