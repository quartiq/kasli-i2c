import requests
import shutil


def render_zpl(zpl, *, resolution=8, width=1.2, height=0.6, index=0,
               accept="image/png", **kwargs):
    url = "http://api.labelary.com/v1/printers/{:d}dpmm/labels/{:g}x{:g}/{:d}/".format(
        resolution, width, height, index)
    headers = {
        "Accept": accept,
    }
    headers.update(kwargs)
    response = requests.post(
        url, headers=headers, files={"file": zpl})
    if response.status_code == 200:
        return response.content
    else:
        raise RuntimeError(response.status_code, response.text)


if __name__ == "__main__":
    zpl = """
    ^XA
    ~SD20
    ^FX QUARTIQ Sinara label
    ^PW240
    ^LH20,10
    ^CFA
    ^FO0,10^FDQUARTIQ GmbH^FS
    ^FO0,20^FDRudower Chausse 29^FS
    ^FO0,30^FD12489 Berlin, Germany^FS
    ^FX name-variant/version
    ^FO0,45^FDUrukul-AD9910/v1.4^FS
    ^FX description
    ^FO0,55^FD4 channel, 1 GS/s DDS^FS
    ^FX date, serial
    ^FO0,75^FD2019-08-30, SN 42^FS
    ^FX license
    ^FO0,65^FDCERN OHL v1.2^FS
    ^FX url
    ^FO0,90^FDhttps://sinara-hw.github.io^FS
    ^FX mac/serial/uuid
    ^FO0,100^FDaa:bb:cc:dd:ee:ff, aa:bb:cc:dd:ee:ff^FS
    ^FX qr code with uuid max 54 char after the .de/
    ^FO140,0^BQN,2,2^FDQA,https://qr.quartiq.de/sinara/aabbccddeeff^FS
    ^XZ
    """
    with open("label.png", "wb") as f:
        f.write(render_zpl(zpl))
