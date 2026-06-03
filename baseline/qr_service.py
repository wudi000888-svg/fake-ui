import io
import subprocess

from panel_config import QR_CMD


def qr_png_for_link(link):
    try:
        return qr_png_with_python(link)
    except ImportError:
        return qr_png_with_command(link)


def qr_png_with_python(link):
    import qrcode

    img = qrcode.make(link)
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def qr_png_with_command(link):
    p = subprocess.run(
        [QR_CMD, "-t", "PNG", "-o", "-", link],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode(errors="ignore") or f"{QR_CMD} failed")
    return p.stdout
