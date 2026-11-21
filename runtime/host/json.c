#include "json.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    const char *p;
    int err;
} jp;

static void ws(jp *s) {
    while (*s->p == ' ' || *s->p == '\n' || *s->p == '\r' || *s->p == '\t') s->p++;
}

static jval *mk(jtype t) {
    jval *v = calloc(1, sizeof *v);
    if (!v) abort();
    v->type = t;
    return v;
}

static void push(jval *v, jval *item, char *key) {
    v->items = realloc(v->items, (v->n + 1) * sizeof *v->items);
    if (!v->items) abort();
    v->items[v->n] = item;
    if (v->type == J_OBJ) {
        v->keys = realloc(v->keys, (v->n + 1) * sizeof *v->keys);
        if (!v->keys) abort();
        v->keys[v->n] = key;
    }
    v->n++;
}

static char *parse_str(jp *s) {
    if (*s->p != '"') {
        s->err = 1;
        return NULL;
    }
    s->p++;
    size_t cap = 16, n = 0;
    char *out = malloc(cap);
    while (*s->p && *s->p != '"') {
        char ch = *s->p++;
        if (ch == '\\') {
            char e = *s->p++;
            switch (e) {
            case 'n': ch = '\n'; break;
            case 't': ch = '\t'; break;
            case 'r': ch = '\r'; break;
            case 'u': { /* only BMP escapes; enough for our files */
                unsigned cp = 0;
                if (sscanf(s->p, "%4x", &cp) != 1) s->err = 1;
                s->p += 4;
                char b[4];
                int k = 0;
                if (cp < 0x80) b[k++] = (char)cp;
                else if (cp < 0x800) { b[k++] = (char)(0xC0 | (cp >> 6)); b[k++] = (char)(0x80 | (cp & 0x3F)); }
                else { b[k++] = (char)(0xE0 | (cp >> 12)); b[k++] = (char)(0x80 | ((cp >> 6) & 0x3F)); b[k++] = (char)(0x80 | (cp & 0x3F)); }
                for (int i = 0; i < k; i++) {
                    if (n + 2 > cap) out = realloc(out, cap *= 2);
                    out[n++] = b[i];
                }
                continue;
            }
            default: ch = e; break;
            }
        }
        if (n + 2 > cap) out = realloc(out, cap *= 2);
        out[n++] = ch;
    }
    if (*s->p != '"') s->err = 1;
    else s->p++;
    out[n] = 0;
    return out;
}

static jval *parse_val(jp *s) {
    ws(s);
    char c = *s->p;
    if (c == '{' || c == '[') {
        jval *v = mk(c == '{' ? J_OBJ : J_ARR);
        char close = c == '{' ? '}' : ']';
        s->p++;
        ws(s);
        if (*s->p == close) {
            s->p++;
            return v;
        }
        for (;;) {
            char *key = NULL;
            if (v->type == J_OBJ) {
                ws(s);
                key = parse_str(s);
                ws(s);
                if (*s->p != ':') s->err = 1;
                s->p++;
            }
            push(v, parse_val(s), key);
            ws(s);
            if (*s->p == ',') { s->p++; continue; }
            if (*s->p == close) { s->p++; break; }
            s->err = 1;
            break;
        }
        return v;
    }
    if (c == '"') {
        jval *v = mk(J_STR);
        v->s = parse_str(s);
        return v;
    }
    if (!strncmp(s->p, "true", 4) || !strncmp(s->p, "false", 5)) {
        jval *v = mk(J_BOOL);
        v->i = c == 't';
        s->p += c == 't' ? 4 : 5;
        return v;
    }
    if (!strncmp(s->p, "null", 4)) {
        s->p += 4;
        return mk(J_NULL);
    }
    jval *v = mk(J_NUM);
    char *end;
    v->d = strtod(s->p, &end);
    v->i = strtoll(s->p, NULL, 10);
    if (end == s->p) s->err = 1;
    s->p = end;
    return v;
}

jval *json_parse(const char *text) {
    jp s = {text, 0};
    jval *v = parse_val(&s);
    if (s.err) {
        json_free(v);
        return NULL;
    }
    return v;
}

void json_free(jval *v) {
    if (!v) return;
    for (size_t i = 0; i < v->n; i++) {
        json_free(v->items[i]);
        if (v->keys) free(v->keys[i]);
    }
    free(v->items);
    free(v->keys);
    free(v->s);
    free(v);
}

const jval *json_get(const jval *obj, const char *key) {
    if (!obj || obj->type != J_OBJ) return NULL;
    for (size_t i = 0; i < obj->n; i++)
        if (!strcmp(obj->keys[i], key)) return obj->items[i];
    return NULL;
}

char *read_file(const char *path, size_t *size) {
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    /* 16-byte aligned buffer with a trailing NUL (model images must be 4-byte aligned) */
    char *buf = aligned_alloc(16, ((size_t)n + 16) & ~(size_t)15);
    if (!buf || fread(buf, 1, (size_t)n, f) != (size_t)n) {
        fclose(f);
        free(buf);
        return NULL;
    }
    fclose(f);
    buf[n] = 0;
    if (size) *size = (size_t)n;
    return buf;
}
