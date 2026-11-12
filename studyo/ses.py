"""Ses yuksekligi egrisi: her saniye icin en yuksek anlik ses (LUFS, EBU R128).
Silah, patlama, kaza, bagirma gibi anlar ses egrisinde tepe yapar."""
import re
import subprocess

import numpy as np

_SATIR = re.compile(r"t:\s*([\d.]+)\s+.*?M:\s*(-?[\d.]+|-inf)")


def egri(yol, sure_sn):
    """saniye basina dizi (uzunluk = sure); ses yoksa bos dizi."""
    islem = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", yol, "-vn", "-map", "0:a:0?",
         "-af", "ebur128=framelog=verbose", "-f", "null", "-"],
        capture_output=True, text=True, errors="replace",
    )
    n = int(sure_sn) + 1
    dizi = np.full(n, -70.0)
    bulundu = False
    for m in _SATIR.finditer(islem.stderr):
        t = int(float(m.group(1)))
        if 0 <= t < n:
            deger = -70.0 if m.group(2) == "-inf" else max(-70.0, float(m.group(2)))
            dizi[t] = max(dizi[t], deger)
            bulundu = True
    return dizi if bulundu else np.array([])


def heyecan(dizi, pencere=90):
    """Sesin, etrafindaki 'normal' seviyeye gore ne kadar yukseldigi (LU)."""
    if not len(dizi):
        return dizi
    yari = pencere // 2
    taban = np.empty_like(dizi)
    for i in range(len(dizi)):
        taban[i] = np.median(dizi[max(0, i - yari): i + yari + 1])
    return dizi - taban
