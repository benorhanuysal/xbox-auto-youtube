"""Ses yuksekligi egrileri (anlik ses, LUFS, EBU R128).
- egri: 1. ses kanali (oyun + mikrofon), saniyede bir. Silah, patlama, kaza, bagirma tepe yapar.
- mikrofon_egri: 2. ses kanali (yalniz mikrofon), 0.1 sn'de bir. Kanal sahibinin konustugu anlari bulmak icin."""
import re
import subprocess

import numpy as np

_SATIR = re.compile(r"t:\s*([\d.]+)\s+.*?M:\s*(-?[\d.]+|-inf)")
TABAN = -70.0     # LUFS: bundan sessizi "sessiz" sayilir
ADIM = 0.1        # sn: ebur128 her 100 ms'de bir olcum yazar (M = son 400 ms'nin yuksekligi)


def kanal_sayisi(yol):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                        "-of", "csv=p=0", yol], capture_output=True, text=True)
    return len(r.stdout.split())


def _olcumler(yol, akis):
    """(t, M) ciftleri; o ses kanali yoksa hic donmez."""
    islem = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", yol, "-vn", "-map", "0:a:%d?" % akis,
         # framelog=info: olcum satirlari normal log seviyesinde yazilsin ("verbose" ile ffmpeg 7+ hic yazmaz)
         "-af", "ebur128=framelog=info", "-f", "null", "-"],
        capture_output=True, text=True, errors="replace",
    )
    for m in _SATIR.finditer(islem.stderr):
        yield float(m.group(1)), (TABAN if m.group(2) == "-inf" else max(TABAN, float(m.group(2))))


def egri(yol, sure_sn):
    """saniye basina dizi (uzunluk = sure); ses yoksa bos dizi."""
    n = int(sure_sn) + 1
    dizi = np.full(n, TABAN)
    bulundu = False
    for t, deger in _olcumler(yol, 0):
        i = int(t)
        if 0 <= i < n:
            dizi[i] = max(dizi[i], deger)
            bulundu = True
    return dizi if bulundu else np.array([])


def mikrofon_egri(yol, sure_sn):
    """ADIM aralikli dizi (i. eleman = i*ADIM saniyesi); kayitta mikrofon kanali yoksa bos dizi."""
    if kanal_sayisi(yol) < 2:
        return np.array([])  # ffmpeg olmayan "0:a:1?" yerine 1. kanali secer: oyun sesi konusma sanilmasin
    n = int(sure_sn / ADIM) + 1
    dizi = np.full(n, TABAN)
    bulundu = False
    for t, deger in _olcumler(yol, 1):
        i = int(round(t / ADIM))
        if 0 <= i < n:
            dizi[i] = deger
            bulundu = True
    return dizi if bulundu else np.array([])


def konusmalar(dizi, adim=ADIM):
    """Mikrofon egrisinden konusma araliklari: [[bas_sn, son_sn], ...] (sirali, cakismasiz).
    dizi: mikrofon_egri ciktisi. Sessizlik RNNoise sonrasi ~-70..-55 LUFS, normal konusma ~-35..-20.
    Bos dizi -> []."""
    if not len(dizi):
        return []
    # TODO(human): esik ustundeki ardisik olcumleri araliga cevir, kisa duraklamalari birlestir,
    # cok kisa sesleri (oksuruk, masaya vurma) at.
    return []


def heyecan(dizi, pencere=90):
    """Sesin, etrafindaki 'normal' seviyeye gore ne kadar yukseldigi (LU)."""
    if not len(dizi):
        return dizi
    yari = pencere // 2
    taban = np.empty_like(dizi)
    for i in range(len(dizi)):
        taban[i] = np.median(dizi[max(0, i - yari): i + yari + 1])
    return dizi - taban
