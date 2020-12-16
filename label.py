import requests


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
    ^FO0,10^FDQUARTIQ GmbH^FS
    ^XZ
    """
    with open("label.png", "wb") as f:
        f.write(render_zpl(zpl))
