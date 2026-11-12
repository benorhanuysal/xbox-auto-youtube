"""Aday sahneler: sesin tepe yaptigi anlar + diyalog kumeleri. Gemini bunlarin arasindan secer."""
import numpy as np

HEYECAN_ESIK = 7.0      # LU: cevresinden bu kadar yuksek ses = olay
TEPE_ONCE, TEPE_SONRA = 8, 5
DIYALOG_ARA = 5.0       # sn: bundan kisa aralikla gelen altyazilar ayni sahne
EN_UZUN = 90.0
EN_FAZLA_ADAY = 60


def _birlestir(araliklar, bosluk=2.0):
    araliklar.sort()
    sonuc = []
    for bas, son in araliklar:
        if sonuc and bas <= sonuc[-1][1] + bosluk:
            sonuc[-1][1] = max(sonuc[-1][1], son)
        else:
            sonuc.append([bas, son])
    # cok uzunlari bol
    bolunmus = []
    for bas, son in sonuc:
        while son - bas > EN_UZUN:
            bolunmus.append([bas, bas + EN_UZUN])
            bas += EN_UZUN
        if son - bas >= 3:
            bolunmus.append([bas, son])
    return bolunmus


def adaylar(heyecan_dizisi, ses_dizisi, satirlar, sure_sn):
    araliklar = []
    if len(heyecan_dizisi):
        tepeler = np.where((heyecan_dizisi >= HEYECAN_ESIK) & (ses_dizisi > -35))[0]
        grup = []
        for t in tepeler:
            if grup and t - grup[-1] > 3:
                araliklar.append([max(0, grup[0] - TEPE_ONCE), min(sure_sn, grup[-1] + TEPE_SONRA)])
                grup = []
            grup.append(int(t))
        if grup:
            araliklar.append([max(0, grup[0] - TEPE_ONCE), min(sure_sn, grup[-1] + TEPE_SONRA)])

    kume = []
    for s in satirlar:
        if kume and s.bas - kume[-1].son > DIYALOG_ARA:
            araliklar.append([max(0, kume[0].bas - 1.5), min(sure_sn, kume[-1].son + 1.0)])
            kume = []
        kume.append(s)
    if kume:
        araliklar.append([max(0, kume[0].bas - 1.5), min(sure_sn, kume[-1].son + 1.0)])

    if not araliklar:
        # Ne ses tepesi ne altyazi: her 3 dakikadan 30 sn
        araliklar = [[t, min(sure_sn, t + 30)] for t in np.arange(0, max(1, sure_sn - 30), 180)]

    sonuc = []
    for bas, son in _birlestir(araliklar):
        bas, son = float(bas), float(son)
        i, j = int(bas), int(son) + 1
        tepe = float(heyecan_dizisi[i:j].max()) if len(heyecan_dizisi[i:j]) else 0.0
        diyalog = [s for s in satirlar if s.bas < son and s.son > bas]
        sonuc.append({
            "bas": round(bas, 1), "son": round(son, 1),
            "heyecan": round(tepe, 1),
            "diyalog": [{"t": round(s.bas - bas, 1), "en": s.en, "tr": s.tr} for s in diyalog],
            "puan": tepe + 1.5 * len(diyalog),
        })
    if len(sonuc) > EN_FAZLA_ADAY:
        sonuc = sorted(sorted(sonuc, key=lambda a: -a["puan"])[:EN_FAZLA_ADAY], key=lambda a: a["bas"])
    for i, a in enumerate(sonuc, 1):
        a["id"] = i
    return sonuc
