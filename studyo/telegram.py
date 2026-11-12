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
MOLA = "☕ Mola"
YAYIN_ALTYAZI = "💬 Yayın altyazısı"
DURUM = "📊 Durum"
MIKROFON = "🎙 Mikrofon"
LUNA = "🔁 Luna'yı yeniden başlat"
EYLEMLER = {ISARET: "isaret", YAYIN_AC: "yayin_ac", YAYIN_KAPA: "yayin_kapa", MOLA: "mola",
            YAYIN_ALTYAZI: "yayin_altyazi", DURUM: "durum", MIKROFON: "mikrofon", LUNA: "luna",
            "🎙 Mikrofon aç/kapa": "mikrofon",  # eski klavyeden basilirsa
            "/durum": "durum", "/start": "yardim", "/yardim": "yardim"}
KLAVYE = {"keyboard": [[{"text": ISARET}],
                       [{"text": YAYIN_AC}, {"text": YAYIN_KAPA}],
                       [{"text": MOLA}, {"text": YAYIN_ALTYAZI}],
                       [{"text": MIKROFON}, {"text": DURUM}],
                       [{"text": LUNA}]],
          "resize_keyboard": True, "is_persistent": True}
YARDIM = ("Night Drive Club kumandası\n\n"
          "⭐ İşaretle: güzel bir an olunca hemen ardından bas, son ~25 sn videoya mutlaka girer.\n"
          "🔴 / ⏹ Kick yayınını başlat / bitir (Xbox uzaktan oynatma açıkken).\n"
          "☕ Mola: yayında oyun görüntüsünü gizle, mola ekranı çıksın (tekrar bas: geri gelir).\n"
          "💬 Yayın altyazısı: Kick'teki canlı Türkçe altyazıyı aç/kapa.\n"
          "🎙 Mikrofon: kayıtta ve yayında sesini kapat/aç.\n"
          "📊 Durum: oynatma, kayıt, yayın, mikrofon, Luna.\n"
          "🔁 Luna'yı yeniden başlat: altyazı takılırsa.")
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


def yetkili_mi(m, sohbet):
    """Yalniz sahibin bota OZEL sohbetten yazdigi mesaj: sohbet de gonderen de eslesen hesap olmali
    (bot bir gruba eklense bile oradaki mesajlar, sahibinkiler dahil, gecmez)."""
    c = m.get("chat") or {}
    return c.get("type") == "private" and c.get("id") == sohbet and (m.get("from") or {}).get("id") == sohbet


def _yabanci_uyarisi(m, son_uyari):
    kimden = m.get("from") or {}
    kim = "@" + kimden["username"] if kimden.get("username") else (kimden.get("first_name") or "biri")
    anahtar = kimden.get("id") or kim
    log.warning("telegram: yabanci hesap yok sayildi (%s)", kim)
    if time.time() - son_uyari.get(anahtar, 0) > 3600:  # ayni kisi icin saatte bir
        son_uyari[anahtar] = time.time()
        gonder("⚠️ %s botuna yazmaya çalıştı; yok sayıldı. Bot yalnız sana cevap verir." % kim)


def dinle(istekler, durdur):
    """Uzun sorgu. Eslesen sohbetin dugmeleri istekler kuyruguna (eylem, basilma_zamani) olarak girer."""
    a = oku()
    token, sohbet = a.get("token"), a.get("sohbet")
    if not (token and sohbet):
        return
    son_uyari = {}
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
            if not yetkili_mi(m, sohbet):
                if (m.get("from") or {}).get("id") == sohbet:
                    log.info("telegram: sahibin grup mesaji yok sayildi (komutlar yalniz ozel sohbetten)")
                else:
                    _yabanci_uyarisi(m, son_uyari)
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


def kur(dosya=None, sifirla=False):
    print("Telegram kumandasi kurulumu")
    eski = oku()
    if eski.get("sohbet") and not sifirla:
        # Tekrar calistirmak eslesmeyi bota o sirada yazan BASKASINA gecirmesin
        print("[OK] Zaten eslesmis: %s (@%s). Bot yalniz bu hesaba cevap veriyor." % (
            eski.get("ad") or "sahip", eski.get("bot")))
        print("     Baska hesap/bot icin: python -m studyo.telegram --kur --sifirla")
        return 0
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
    _yaz({"token": token, "sohbet": sohbet, "ad": ad, "bot": bot.get("username"),
          "eslesme": datetime.datetime.now().isoformat(timespec="seconds")})
    gonder("✅ Merhaba %s! Kumanda hazır.\n\n%s" % (ad, YARDIM))
    print("[OK] Eslesti: %s. Bot artik yalniz bu sohbete cevap verir. Bekciyi yeniden baslatinca devreye girer." % (ad or sohbet))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="studyo.telegram", description="Telegram uzaktan kumandasi")
    ap.add_argument("--kur", action="store_true", help="bot jetonu + sohbet eslestirme")
    ap.add_argument("--dosya", help="--kur ile: jetonu bu metin dosyasindan oku")
    ap.add_argument("--sifirla", action="store_true", help="--kur ile: mevcut eslesmeyi silip yeniden esle")
    ap.add_argument("--dene", action="store_true", help="deneme mesaji")
    arg = ap.parse_args(argv)
    if arg.kur:
        return kur(arg.dosya, arg.sifirla)
    if arg.dene:
        print("[OK] gonderildi" if gonder("Deneme mesajı 👋") else "[!] gonderilemedi (once --kur)")
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
