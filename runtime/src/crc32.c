#include "utiny.h"

/* Bitwise CRC-32 (IEEE, reflected, poly 0xEDB88320). Called once at boot, so no table. */
uint32_t ut_crc32(const void *data, size_t n) {
    const uint8_t *p = (const uint8_t *)data;
    uint32_t crc = 0xFFFFFFFFu;
    for (size_t i = 0; i < n; i++) {
        crc ^= p[i];
        for (int k = 0; k < 8; k++) {
            crc = (crc >> 1) ^ (0xEDB88320u & (0u - (crc & 1u)));
        }
    }
    return crc ^ 0xFFFFFFFFu;
}
