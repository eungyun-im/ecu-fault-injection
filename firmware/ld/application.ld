/* Application behind the bootloader: the slot from 0x08004000 up to the info page. */

MEMORY
{
  RAM   (xrw) : ORIGIN = 0x20000000, LENGTH = 32K
  FLASH (rx)  : ORIGIN = 0x08004000, LENGTH = 110K
}

INCLUDE sections.ld
