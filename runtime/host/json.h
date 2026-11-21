/* Minimal JSON reader for golden vector files (host tools only; uses the heap). */
#ifndef UT_JSON_H
#define UT_JSON_H

#include <stddef.h>
#include <stdint.h>

typedef enum { J_NULL, J_BOOL, J_NUM, J_STR, J_ARR, J_OBJ } jtype;

typedef struct jval {
    jtype type;
    int64_t i; /* integer value (numbers are parsed as integers when possible) */
    double d;
    char *s; /* J_STR: UTF-8, NUL-terminated */
    struct jval **items; /* J_ARR / J_OBJ values */
    char **keys;         /* J_OBJ keys */
    size_t n;
} jval;

jval *json_parse(const char *text);
void json_free(jval *v);
const jval *json_get(const jval *obj, const char *key);
char *read_file(const char *path, size_t *size);

#endif
