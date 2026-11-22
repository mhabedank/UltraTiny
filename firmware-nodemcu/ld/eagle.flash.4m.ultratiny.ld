/* UltraTiny flash split for 4 MB NodeMCU boards (specs/005-nodemcu-port/contracts/flash-layout.md).
 * Only flash 0x000000-0x0FFFFF is memory-mapped (at 0x40200000), so firmware and model share it:
 *   firmware @0x40200000 (352 KB, flash 0x000000-0x057FFF; irom starts after the 0x1010 header)
 *   model    @0x40258000 (672 KB, flash 0x058000-0x0FFFFF), written by `make nodemcu-flash-model`
 *   facts    flash 0x100000-0x10FFFF (64 KB, NOT mapped, read via ESP.flashRead), written by
 *            `make nodemcu-flash-facts` (specs/006-hybrid-chemielehrer); no section needed here
 *   fs       @0x40500000 (unused by UltraTiny; kept as in eagle.flash.4m1m.ld)
 *   eeprom   @0x405FB000, rfcal/wifi sectors at the end of flash as the core expects
 * Keep UT_MODEL_FLASH_OFFSET in include/layout.h in sync with the irom0 end below. */

MEMORY
{
  dport0_0_seg :                        org = 0x3FF00000, len = 0x10
  dram0_0_seg :                         org = 0x3FFE8000, len = 0x14000
  irom0_0_seg :                         org = 0x40201010, len = 0x56ff0
}

PROVIDE ( _FS_start = 0x40500000 );
PROVIDE ( _FS_end = 0x405FA000 );
PROVIDE ( _FS_page = 0x100 );
PROVIDE ( _FS_block = 0x2000 );
PROVIDE ( _EEPROM_start = 0x405fb000 );
PROVIDE ( _SPIFFS_start = 0x40500000 );
PROVIDE ( _SPIFFS_end = 0x405FA000 );
PROVIDE ( _SPIFFS_page = 0x100 );
PROVIDE ( _SPIFFS_block = 0x2000 );

INCLUDE "local.eagle.app.v6.common.ld"
