"""Oynarken isaretlenen anlar ("bu cok iyiydi"). Isaret tusuna basilan saat isaretler.txt'ye yazilir;
kurgu sirasinda kaydin icine dusenler saniyeye cevrilir ve o sahneler videoya mutlaka girer."""
import datetime
import os

from .ayar import KOK

DOSYA = os.path.join(KOK, "isaretler.txt")


def ekle(zaman=None):
    zaman = zaman or datetime.datetime.now()
    with open(DOSYA, "a", encoding="utf-8") as f:
        f.write(zaman.isoformat(timespec="seconds") + "\n")
    return zaman


def kayittakiler(bas, sure_sn):
    """Kayit baslangicina gore saniye cinsinden, kaydin icindeki isaretler."""
    if not os.path.exists(DOSYA):
        return []
    sonuc = []
    with open(DOSYA, encoding="utf-8") as f:
        for satir in f:
            try:
                t = datetime.datetime.fromisoformat(satir.strip())
            except ValueError:
                continue
            fark = (t - bas).total_seconds()
            if 0 <= fark <= sure_sn:
                sonuc.append(round(fark, 1))
    return sorted(sonuc)
