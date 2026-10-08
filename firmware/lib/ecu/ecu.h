/* The ECU application. Three calls connect it to a platform:
 *
 *   ecu_init      once at start
 *   ecu_on_frame  for every received CAN frame
 *   ecu_step      once per millisecond
 */

#ifndef ECU_H
#define ECU_H

#include <stdint.h>

#include "ecu_port.h"

void ecu_init(const ecu_port_t *port, uint32_t now_ms);
void ecu_on_frame(const can_frame_t *frame, uint32_t now_ms);
void ecu_step(uint32_t now_ms);

#endif /* ECU_H */
