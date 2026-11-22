/* Alphabet mapping and UTF-8 helpers (research.md R2). */
#include "utiny.h"

int ut_token_from_codepoint(const ut_model *m, uint32_t cp) {
    for (int i = m->n_special; i < m->vocab_size; i++)
        if (m->alphabet[i] == cp) return i;
    return UT_TOK_UNK;
}

uint32_t ut_codepoint_from_token(const ut_model *m, int token) {
    if (token < m->n_special || token >= m->vocab_size) return 0;
    return m->alphabet[token];
}

int ut_utf8_encode(uint32_t cp, char out[4]) {
    if (cp < 0x80) {
        out[0] = (char)cp;
        return 1;
    }
    if (cp < 0x800) {
        out[0] = (char)(0xC0 | (cp >> 6));
        out[1] = (char)(0x80 | (cp & 0x3F));
        return 2;
    }
    if (cp < 0x10000) {
        out[0] = (char)(0xE0 | (cp >> 12));
        out[1] = (char)(0x80 | ((cp >> 6) & 0x3F));
        out[2] = (char)(0x80 | (cp & 0x3F));
        return 3;
    }
    out[0] = (char)(0xF0 | (cp >> 18));
    out[1] = (char)(0x80 | ((cp >> 12) & 0x3F));
    out[2] = (char)(0x80 | ((cp >> 6) & 0x3F));
    out[3] = (char)(0x80 | (cp & 0x3F));
    return 4;
}

int ut_utf8_feed(ut_utf8_dec *d, uint8_t b, uint32_t *cp) {
    if (d->need == 0) {
        if (b < 0x80) {
            *cp = b;
            return 1;
        }
        if ((b & 0xE0) == 0xC0) {
            d->cp = b & 0x1F;
            d->need = 1;
        } else if ((b & 0xF0) == 0xE0) {
            d->cp = b & 0x0F;
            d->need = 2;
        } else if ((b & 0xF8) == 0xF0) {
            d->cp = b & 0x07;
            d->need = 3;
        } else {
            return -1;
        }
        return 0;
    }
    if ((b & 0xC0) != 0x80) {
        d->need = 0;
        return -1;
    }
    d->cp = (d->cp << 6) | (b & 0x3F);
    if (--d->need == 0) {
        *cp = d->cp;
        return 1;
    }
    return 0;
}
