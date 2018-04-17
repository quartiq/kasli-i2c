#!/bin/bash

set -e
set -x

SERIAL=${1:-0}
FT_SERIAL=Kasli-v1.1-$SERIAL

{

IP=10.0.16.1$SERIAL
FT_BUS=1
FT_PORT=4
UART_DEV=/dev/serial/by-id/usb-ARTIQ_Sinara_Quad_RS232-HS_$FT_SERIAL-if02-port0
BUSNUM=$(cat /sys/bus/usb/devices/$FT_BUS-$FT_PORT/busnum)
DEVNUM=$(cat /sys/bus/usb/devices/$FT_BUS-$FT_PORT/devnum)

cat kasli-ft4232h.conf.in | m4 -DFT_SERIAL=$FT_SERIAL > kasli-ft4232h.conf
ftdi_eeprom --device d:$BUSNUM/$DEVNUM --flash-eeprom kasli-ft4232h.conf
sleep 3
MAC=$(python flash_ee.py $SERIAL)
artiq_mkfs storage.img -s mac $MAC -s ip $IP -s startup_clock e
artiq_flash -t kasli -I "ftdi_serial $FT_SERIAL" -V opticlock --srcbuild artiq_kasli -f storage.img gateware bootloader firmware storage start
stty -F $UART_DEV 115200 cs8 -cstopb -parenb opost onlcr
timeout --foreground 15 socat stdio $UART_DEV || true
ping -c4 $IP
echo SUCCESS

} 2>&1 | tee deploy_$FT_SERIAL.log
