#!/bin/bash

SRC=false

while [[ $# -gt 0 ]]
do
key="$1"

case $key in
    -d|--dir)
    DIR="$2"
    shift # past argument
    shift # past value
    ;;
    -v|--version)
    VERSION="$2"
    shift # past argument
    shift # past value
    ;;
    --src)
    SRC=true
    shift # past argument
    shift # past value
    ;;
    *)
    -
esac
done

set -e
set -x

SERIAL=$(python3 kasli_get_mac.py)
FT_SERIAL=$SERIAL


{

IP=10.34.16.100
FT_BUS=1
FT_PORT=4.4.2

UART_DEV=/dev/serial/by-id/usb-ARTIQ_Sinara_Quad_RS232-HS_$FT_SERIAL-if02-port0
BUSNUM=$(cat /sys/bus/usb/devices/$FT_BUS-$FT_PORT/busnum)
DEVNUM=$(cat /sys/bus/usb/devices/$FT_BUS-$FT_PORT/devnum)

cat kasli-ft4232h.conf.in | m4 -DFT_SERIAL=$FT_SERIAL > kasli-ft4232h.conf
ftdi_eeprom --device d:$BUSNUM/$DEVNUM --flash-eeprom kasli-ft4232h.conf
sleep 3
artiq_mkfs storage.img -s ip $IP -s rtio_clock ext0_synth0_10to125
if [ "$SRC" = true ]; then
    artiq_flash -t kasli -I "ftdi_serial $FT_SERIAL" -d $DIR --srcbuild -f storage.img gateware bootloader firmware storage start
else
    artiq_flash -t kasli -I "ftdi_serial $FT_SERIAL" -d $DIR  -f storage.img gateware bootloader firmware storage start
fi
stty -F $UART_DEV 115200 cs8 -cstopb -parenb opost onlcr
timeout --foreground 15 socat stdio $UART_DEV || true
sudo ip neigh flush to $IP || true
ping -w40 -W40 -c4 $IP
echo SUCCESS

} 2>&1 | tee deploy_$FT_SERIAL.log
