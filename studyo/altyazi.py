"""Turkce altyazi: LunaTranslator ceviri gunlugunu (altyazi_ceviri.log) video zamanina esler,
SRT ve ASS (videoya gomulecek, stilli) dosyalari uretir."""
import datetime
import difflib
import os
from dataclasses import dataclass


@dataclass
class Satir:
    bas: float  # saniye, kaynak videoda
    son: float
    tr: str
    en: str


def _gunluk_satirlari(userconfig):
    """(tarihli_mi, zaman, ingilizce, turkce) listesi; eski dosya once."""
    sonuc = []
    for ad in ("altyazi_ceviri.log.1", "altyazi_ceviri.log"):
        yol = os.path.join(userconfig or "", ad)
        if not os.path.exists(yol):
            continue
        with open(yol, encoding="utf-8", errors="replace") as f:
            for satir in f:
                p = satir.rstrip("\n").split("\t")
                if len(p) < 5 or p[1] == "HATA" or not p[4].startswith("=> "):
                    continue
                zaman = p[0].strip()
                try:
                    if len(zaman) > 8:
                        t = datetime.datetime.strptime(zaman, "%Y-%m-%d %H:%M:%S")
                        sonuc.append((True, t, p[3], p[4][3:]))
                    else:
                        t = datetime.datetime.strptime(zaman, "%H:%M:%S")
                        sonuc.append((False, t, p[3], p[4][3:]))
                except ValueError:
                    continue
    return sonuc


def _ayni_mi(onceki, en, tr):
    # OCR ayni altyaziyi bir-iki harf farkla okuyabiliyor ("quard"/"guard")
    if onceki.en == en or onceki.tr == tr:
        return True
    return difflib.SequenceMatcher(None, onceki.en.lower(), en.lower()).ratio() >= 0.85


def kayda_esle(userconfig, baslangic, sure_sn, gecikme=1.0):
    """Kaydin suresine dusen ceviri satirlari; ayni cumlenin tekrar okunmalari birlestirilir."""
    ham = []
    for tarihli, t, en, tr in _gunluk_satirlari(userconfig):
        if tarihli:
            sn = (t - baslangic).total_seconds()
        else:
            # Eski bicim (yalnizca saat): kaydin gunune koy, gece yarisi gecisini duzelt
            tam = datetime.datetime.combine(baslangic.date(), t.time())
            sn = (tam - baslangic).total_seconds()
            if sn < -3600:
                sn += 86400
        sn -= gecikme
        if 0 <= sn <= sure_sn and tr.strip():
            ham.append((sn, en.strip(), tr.strip()))
    ham.sort()

    satirlar = []
    for sn, en, tr in ham:
        # OCR ayni altyaziyi birkac kez okuyabiliyor: 12 sn icinde ayni metin -> tek satir
        if satirlar and sn - satirlar[-1].bas < 12 and _ayni_mi(satirlar[-1], en, tr):
            continue
        satirlar.append(Satir(sn, sn, tr, en))
    for i, s in enumerate(satirlar):
        okuma = min(6.0, max(2.0, len(s.tr) * 0.075))
        sonraki = satirlar[i + 1].bas - 0.05 if i + 1 < len(satirlar) else s.bas + okuma
        s.son = max(s.bas + 0.8, min(s.bas + okuma, sonraki))
    return satirlar


def kes(satirlar, bas, son):
    """[bas, son] araligindaki satirlar, zamani 0'dan baslayacak sekilde."""
    sonuc = []
    for s in satirlar:
        if s.son <= bas or s.bas >= son:
            continue
        sonuc.append(Satir(max(0.0, s.bas - bas), min(son, s.son) - bas, s.tr, s.en))
    return sonuc


def yeniden_zamanla(satirlar, parcalar):
    """Kurguda arka arkaya eklenen parcalar icin cikis videosu zamanina tasir."""
    sonuc, kayma = [], 0.0
    for bas, son in parcalar:
        for s in kes(satirlar, bas, son):
            sonuc.append(Satir(s.bas + kayma, s.son + kayma, s.tr, s.en))
        kayma += son - bas
    return sonuc


def _srt_zaman(sn):
    ms = int(round(sn * 1000))
    return "%02d:%02d:%02d,%03d" % (ms // 3600000, ms // 60000 % 60, ms // 1000 % 60, ms % 1000)


def srt_yaz(satirlar, yol, alan="tr"):
    """alan: "tr" (Turkce) ya da "en" (oyunun Ingilizce altyazisi; YouTube'a ayri altyazi parcasi)."""
    with open(yol, "w", encoding="utf-8") as f:
        n = 0
        for s in satirlar:
            metin = (getattr(s, alan) or "").strip()
            if metin:
                n += 1
                f.write("%d\n%s --> %s\n%s\n\n" % (n, _srt_zaman(s.bas), _srt_zaman(s.son), metin))
    return n


def _ass_zaman(sn):
    cs = int(round(max(0.0, sn) * 100))
    return "%d:%02d:%02d.%02d" % (cs // 360000, cs // 6000 % 60, cs // 100 % 60, cs % 100)


def _ass_metin(metin):
    return metin.replace("\\", "/").replace("{", "(").replace("}", ")").replace("\n", "\\N")


# Yatay: TV'deki gibi, oyunun Ingilizce altyazisinin hemen ustunde.
# Dikey (Shorts): oyun goruntusunun altinda, buyuk.
_STILLER = {
    "yatay": (1920, 1080, [
        "Style: Altyazi,Segoe UI,50,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,3.2,1.5,2,120,120,190,1",
    ]),
    "dikey": (1080, 1920, [
        "Style: Altyazi,Segoe UI,62,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,4,2,8,60,60,1320,1",
        "Style: Baslik,Segoe UI,78,&H00FFFFFF,&H00FFFFFF,&H00561A7A,&H96000000,-1,-1,0,0,100,100,0,0,1,5,3,8,60,60,330,1",
    ]),
}


def ass_yaz(satirlar, yol, bicim="yatay", baslik=None, sure_sn=None):
    genislik, yukseklik, stiller = _STILLER[bicim]
    with open(yol, "w", encoding="utf-8-sig") as f:
        f.write("[Script Info]\nScriptType: v4.00+\nPlayResX: %d\nPlayResY: %d\nWrapStyle: 0\n\n" % (genislik, yukseklik))
        f.write("[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
                "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, "
                "Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n")
        f.write("\n".join(stiller) + "\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
        if baslik and sure_sn:
            f.write("Dialogue: 1,%s,%s,Baslik,,0,0,0,,%s\n" % (_ass_zaman(0), _ass_zaman(sure_sn), _ass_metin(baslik)))
        for s in satirlar:
            f.write("Dialogue: 0,%s,%s,Altyazi,,0,0,0,,%s\n" % (_ass_zaman(s.bas), _ass_zaman(s.son), _ass_metin(s.tr)))
