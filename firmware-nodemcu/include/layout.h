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

#endif
