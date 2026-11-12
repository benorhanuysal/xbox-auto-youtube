"""Telegram uzaktan kumandasi: oynarken telefondan yayini ac/kapat, ani isaretle, durumu gor, mikrofonu kapat.
Bekcinin bildirimleri de buraya gelir (yayindayken ekrana dusmeden).

Guvenlik: bot yalniz eslestirilen TEK sohbete (senin hesabin) cevap verir; baska herkesin mesaji yok sayilir.
Jeton ve sohbet kimligi telegram.json'da (git'e girmez).

  python -m studyo.telegram --kur [--dosya telegram.txt]   BotFather jetonu + eslestirme (TELEGRAM_KUR.bat)
  python -m studyo.telegram --dene                          deneme mesaji gonder
"""
import argparse
import datetime
import getpass
import json
import logging
import os
import re
import time
import urllib.request

from .ayar import KOK

AYAR = os.path.join(KOK, "telegram.json")
_API = "https://api.telegram.org/bot%s/%s"
log = logging.getLogger("izle")

ISARET = "⭐ İşaretle"
YAYIN_AC = "🔴 Yayını başlat"
YAYIN_KAPA = "⏹ Yayını bitir"
DURUM = "📊 Durum"
MIKROFON = "🎙 Mikrofon aç/kapa"
EYLEMLER = {ISARET: "isaret", YAYIN_AC: "yayin_ac", YAYIN_KAPA: "yayin_kapa", DURUM: "durum",
            MIKROFON: "mikrofon", "/durum": "durum", "/start": "yardim", "/yardim": "yardim"}
KLAVYE = {"keyboard": [[{"text": ISARET}],
                       [{"text": YAYIN_AC}, {"text": YAYIN_KAPA}],
                       [{"text": DURUM}, {"text": MIKROFON}]],
          "resize_keyboard": True, "is_persistent": True}
YARDIM = ("Night Drive Club kumandası\n\n"
          "⭐ İşaretle: güzel bir an olunca hemen ardından bas, son ~25 sn videoya mutlaka girer.\n"
          "🔴 / ⏹ Kick yayınını başlat / bitir (Xbox uzaktan oynatma açıkken).\n"
          "📊 Durum: oynatma, kayıt, yayın, mikrofon, Luna.\n"
          "🎙 Mikrofonu kapat/aç (kayıt ve yayın için).")
ESKI_KOMUT_SN = 120  # telefon cevrimdisiyken birikmis komutlar sonradan calismasin


def oku():
    try:
        with open(AYAR, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _yaz(d):
    with open(AYAR, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def hazir_mi():
    a = oku()
    return bool(a.get("token") and a.get("sohbet"))


def _api(token, metod, veri=None, zaman_asimi=15):
    istek = urllib.request.Request(_API % (token, metod), data=json.dumps(veri or {}).encode("utf-8"),
                                   headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(istek, timeout=zaman_asimi) as r:
        yanit = json.load(r)
    if not yanit.get("ok"):
        raise RuntimeError(yanit.get("description", "Telegram hatasi"))
    return yanit["result"]


def gonder(metin, klavye=True):
    """Eslesen sohbete mesaj; ayarli degilse ya da ag yoksa sessizce False."""
    a = oku()
    if not (a.get("token") and a.get("sohbet")):
        return False
    veri = {"chat_id": a["sohbet"], "text": metin[:4000], "disable_web_page_preview": True}
    if klavye:
        veri["reply_markup"] = KLAVYE
    try:
        _api(a["token"], "sendMessage", veri)
        return True
    except Exception as e:
        log.warning("telegram mesaji gonderilemedi: %s", e)
        return False


def dinle(istekler, durdur):
    """Uzun sorgu. Eslesen sohbetin dugmeleri istekler kuyruguna (eylem, basilma_zamani) olarak girer."""
    a = oku()
    token, sohbet = a.get("token"), a.get("sohbet")
    if not (token and sohbet):
        return
    ofset = None
    try:  # bekci kapaliyken basilmis eski dugmeler calismasin
        eski = _api(token, "getUpdates", {"timeout": 0})
        if eski:
            ofset = eski[-1]["update_id"] + 1
    except Exception:
        pass
    bekleme = 2
    while not durdur.is_set():
        try:
            veri = {"timeout": 25, "allowed_updates": ["message"]}
            if ofset is not None:
                veri["offset"] = ofset
            guncellemeler = _api(token, "getUpdates", veri, zaman_asimi=35)
            bekleme = 2
        except Exception as e:
            log.debug("telegram baglanti hatasi: %s", e)
            durdur.wait(bekleme)
            bekleme = min(60, bekleme * 2)
            continue
        for g in guncellemeler:
            ofset = g["update_id"] + 1
            m = g.get("message") or {}
            if (m.get("chat") or {}).get("id") != sohbet:
                log.warning("telegram: eslesmemis sohbetten mesaj yok sayildi")
                continue
            tarih = m.get("date", time.time())
            if time.time() - tarih > ESKI_KOMUT_SN:
                continue
            eylem = EYLEMLER.get((m.get("text") or "").strip(), "yardim")
            istekler.put((eylem, datetime.datetime.fromtimestamp(tarih)))


# ---------------------------------------------------------------- kurulum
def _jeton_dosyadan(yol):
    with open(yol, encoding="utf-8-sig") as f:
        bulunan = re.search(r"\d{6,12}:[A-Za-z0-9_-]{30,}", f.read())
    return bulunan.group(0) if bulunan else ""


def kur(dosya=None):
    print("Telegram kumandasi kurulumu")
    if dosya:
        token = _jeton_dosyadan(dosya)
        print("  %s okundu: jeton %s" % (os.path.basename(dosya), "var" if token else "YOK"))
    else:
        print("  1) Telegram'da @BotFather > /newbot > bir ad ve sonu 'bot' ile biten kullanici adi ver.")
        print("  2) Verdigi jetonu (123456:ABC...) asagiya yapistir (ekranda gorunmez).\n")
        token = getpass.getpass("Bot jetonu: ").replace("﻿", "").strip()
    if not re.fullmatch(r"\d{6,12}:[A-Za-z0-9_-]{30,}", token or ""):
        print("[!] Jeton bicimi yanlis (sayi:harfler). Vazgecildi.")
        return 1
    try:
        bot = _api(token, "getMe")
    except Exception as e:
        print("[!] Telegram jetonu kabul etmedi: %s" % e)
        return 1
    print("  Bot: @%s" % bot.get("username"))
    # Kullanici /start'a zaten bastiysa (son 15 dk) hemen eslesir; yoksa 3 dk beklenir
    sohbet, ad, ofset, bitis = None, None, None, time.time() + 180
    print("  Telegram'da t.me/%s adresini ac ve BASLAT'a (/start) bas..." % bot.get("username"))
    while sohbet is None and time.time() < bitis:
        veri = {"timeout": 20}
        if ofset is not None:
            veri["offset"] = ofset
        for g in _api(token, "getUpdates", veri, zaman_asimi=30):
            ofset = g["update_id"] + 1
            m = g.get("message") or {}
            if m.get("chat", {}).get("type") == "private" and time.time() - m.get("date", 0) < 900:
                sohbet, ad = m["chat"]["id"], m["chat"].get("first_name") or ""
    if sohbet is None:
        print("[!] 3 dk icinde mesaj gelmedi. Bota /start yazip komutu tekrar calistir.")
        return 1
    if ofset is not None:
        _api(token, "getUpdates", {"offset": ofset, "timeout": 0})  # eslesme mesajini tuket
    _yaz({"token": token, "sohbet": sohbet, "bot": bot.get("username"), "eslesme": datetime.datetime.now().isoformat(timespec="seconds")})
    gonder("✅ Merhaba %s! Kumanda hazır.\n\n%s" % (ad, YARDIM))
    print("[OK] Eslesti: %s. Bot artik yalniz bu sohbete cevap verir. Bekciyi yeniden baslatinca devreye girer." % (ad or sohbet))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="studyo.telegram", description="Telegram uzaktan kumandasi")
    ap.add_argument("--kur", action="store_true", help="bot jetonu + sohbet eslestirme")
    ap.add_argument("--dosya", help="--kur ile: jetonu bu metin dosyasindan oku")
    ap.add_argument("--dene", action="store_true", help="deneme mesaji")
    arg = ap.parse_args(argv)
    if arg.kur:
        return kur(arg.dosya)
    if arg.dene:
        print("[OK] gonderildi" if gonder("Deneme mesajı 👋") else "[!] gonderilemedi (once --kur)")
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
