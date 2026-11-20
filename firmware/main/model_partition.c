/* Model partition lookup + esp_partition_mmap (research.md R7). Weights stay in flash. */
#include "model_partition.h"

#include "esp_partition.h"

#define MODEL_PARTITION_SUBTYPE 0x40

int model_partition_map(const void **data, size_t *size) {
    const esp_partition_t *p =
        esp_partition_find_first(ESP_PARTITION_TYPE_DATA, MODEL_PARTITION_SUBTYPE, "model");
    if (p == NULL) return -1;
    esp_partition_mmap_handle_t handle;
    if (esp_partition_mmap(p, 0, p->size, ESP_PARTITION_MMAP_DATA, data, &handle) != ESP_OK)
        return -2;
    *size = p->size;
    return 0;
}
