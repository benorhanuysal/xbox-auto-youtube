"""Videodaki Turkce altyaziyi Claude ile duzelt: canli ceviri (cogunlukla Google) harfiyen ve uzun oluyor,
GTA'da konusma hizli oldugu icin izleyici okumaya yetisemiyor. Claude her satiri ekranda kaldigi sureye
sigacak kadar kisa, dogal Turkceye cevirir; OCR hatalarini Ingilizcesine bakarak duzeltir.
Claude yoksa ya da hata verirse altyazilar oldugu gibi kalir."""
import json

from . import claude

OKUMA_HIZI = 14     # harf/sn: rahat okunan altyazi hizi
EN_AZ_HARF = 16

_KOMUT = """You are the Turkish subtitle editor of a YouTube channel that posts {oyun} gameplay.
Below are the in-game subtitles of the video. For each item: i (id), en (the English subtitle as read from the
screen by OCR, may contain OCR errors like "vou" = you, "plavers" = players), tr (a fast machine translation,
often too literal and too long), max (the most characters a viewer can read in the time the line is on screen).

Write a Turkish subtitle for every item:
- natural, casual spoken Turkish, like a good fan-sub; keep the meaning and the tone (jokes, sarcasm, slang)
- at most "max" characters: shorten by dropping filler words, never by dropping the point
- fix OCR and translation mistakes using "en"
- never translate names of people, places, brands, vehicles or missions (Lester, Raf De Angelis, Mr. Faber,
  Los Santos, Prix Luxury Real Estate, Cayo Perico ...)
- if "en" is not dialogue or an objective but leftover screen text (menu, HUD, garbage), return "" for it

Reply with JSON only, no other text: {{"altyazi": {{"0": "...", "1": "..."}}}}

Items:
{ogeler}"""


def duzelt(satirlar, ayar, klasor, gunluk=print):
    """satirlar listesindeki .tr metinlerini yerinde gunceller; bos donenleri listeden cikarir."""
    if not satirlar or not claude.var_mi():
        return satirlar
    ogeler = []
    for i, s in enumerate(satirlar):
        sure = max(0.5, s.son - s.bas)
        ogeler.append({"i": i, "en": s.en, "tr": s.tr, "max": max(EN_AZ_HARF, int(sure * OKUMA_HIZI))})
    gunluk("  Claude altyazilari duzeltiyor (%d satir)..." % len(ogeler))
    ham = claude.iste(_KOMUT.format(oyun=ayar["oyun"], ogeler=json.dumps(ogeler, ensure_ascii=False)),
                      klasor, ayar.get("claude_model"), gunluk)
    yeni = (ham or {}).get("altyazi") if isinstance(ham, dict) else None
    if not isinstance(yeni, dict):
        gunluk("  altyazi duzeltilemedi, canli ceviri kullaniliyor")
        return satirlar
    sonuc, degisen = [], 0
    for i, s in enumerate(satirlar):
        metin = yeni.get(str(i))
        if metin is None:
            sonuc.append(s)
            continue
        metin = str(metin).strip()
        if not metin:
            continue  # ekran yazisi / cop: videoya girmesin
        if metin != s.tr:
            degisen += 1
        s.tr = metin
        sonuc.append(s)
    gunluk("  altyazi: %d satir duzeltildi, %d satir cikarildi" % (degisen, len(satirlar) - len(sonuc)))
    return sonuc
