/* NodeMCU flash layout and RAM budget (specs/005-nodemcu-port/contracts/flash-layout.md,
 * data-model.md "Board budget profile"). Keep in sync with ld/eagle.flash.4m.ultratiny.ld,
 * the Makefile target nodemcu-flash-model and tools/budget_report.py. */
#ifndef UT_LAYOUT_H
#define UT_LAYOUT_H

#define UT_FLASH_MAP_BASE 0x40200000u    /* flash offset 0 as seen by the CPU (first 1 MB) */
#define UT_MODEL_FLASH_OFFSET 0x58000u   /* model area start in flash */
#define UT_MODEL_AREA_SIZE 0xA8000u      /* 672 KB, up to the end of the mapped megabyte */
#define UT_MODEL_ADDR (UT_FLASH_MAP_BASE + UT_MODEL_FLASH_OFFSET) /* 0x40258000 */
#define UT_ARENA_MAX (36 * 1024)         /* 40 KB budget minus 10 % headroom */

/* Fact table (UTFT, specs/006-hybrid-chemielehrer/contracts/fact-table-format.md): first byte after
 * the mapped megabyte, read with ESP.flashRead (not memory-mapped). Flash: make nodemcu-flash-facts. */
#define UT_FACTS_FLASH_OFFSET 0x100000u
#define UT_FACTS_AREA_SIZE 0x10000u    /* 64 KB */
#define UT_FACTS_MAX 58982u            /* 90 % of the area (10 % headroom) */

#endif
