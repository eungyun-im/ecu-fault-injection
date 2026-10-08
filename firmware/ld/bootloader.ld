/* Bootloader: the first 16 kB of flash. */

MEMORY
{
  RAM   (xrw) : ORIGIN = 0x20000000, LENGTH = 32K
  FLASH (rx)  : ORIGIN = 0x08000000, LENGTH = 16K
}

INCLUDE sections.ld
