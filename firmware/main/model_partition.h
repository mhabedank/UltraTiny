#pragma once

#include <stddef.h>

/* Memory-maps the "model" data partition (read-only, data cache). Returns 0 on success. */
int model_partition_map(const void **data, size_t *size);
