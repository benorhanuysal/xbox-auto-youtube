"""Kick canli yayini, AYRI (tasinabilir) ikinci OBS'ten.
- KAYIT OBS'i temiz kayit alir (YouTube kurgusu). YAYIN OBS'i ayni ekrani + Xbox sesini + mikrofonu alir, ustune
  canli Turkce altyazi, Kick chat ve takip/abone bildirimlerini koyup Kick'e verir. YouTube videolarinda chat ya da
  canli altyazi olmaz; bulaniklastirma, "altyaziyi tekrar gomme" gibi ozel durumlar gerekmez.
- Bekci (izle.py): Telegram kumandasi yayini acar/kapatir; yayin bitince yayin OBS'i kapanir.

  python -m studyo.yayin --ikinci-obs                     yayin OBS'ini kur (bir kez; OBS guncellenince tekrar)
  python -m studyo.yayin --kur [--dosya kick.txt]         Kick yayin adresi + anahtari (YAYIN_KUR.bat)
  python -m studyo.yayin --katmanlar --dosya botrix.txt   Kick chat + bildirim adresleri (BotRix)
  python -m studyo.yayin --dene                           yayin OBS'inin goruntusu (masaustu gizli)
"""
import argparse
import base64
import getpass
import json
import os
import re
import secrets
import shutil
import subprocess
import time

from . import ayar as ayar_modulu, obs

KOK = ayar_modulu.KOK
KATMANLAR = os.path.join(KOK, "kick_katmanlari.json")  # adreslerde kisisel anahtar var: git'e girmez
YAYIN_WS_PORT = 4456
# Bekci yayin surerken bu dosyayi tutar; kurgu sureci (ayri program) YouTube yuklemesini yayin bitene dek erteler:
# yukleme upload hizini yayinla paylasirsa Kick'te donma olur
BAYRAK = os.path.join(KOK, ".yayinda")


def bayrak(acik):
    try:
        if acik:
            open(BAYRAK, "w").close()
        elif os.path.exists(BAYRAK):
            os.remove(BAYRAK)
    except OSError:
        pass


def bitmesini_bekle(gunluk=print, en_fazla_sn=6 * 3600):
    """Yayin suruyorsa bitene kadar (en fazla 6 saat) bekler."""
    if not os.path.exists(BAYRAK):
        return
    gunluk("  Kick yayini suruyor: YouTube yuklemesi yayin bitince yapilacak (upload yayina kalsin)")
    bitis = time.time() + en_fazla_sn
    while os.path.exists(BAYRAK) and time.time() < bitis:
        time.sleep(30)


# ---------------------------------------------------------------- Kick chat + bildirimler (BotRix)
def web_adresleri():
    try:
        with open(KATMANLAR, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def adresleri_ayikla(metin):
    """BotRix (ya da benzeri) web adreslerini 'chat' / 'bildirim' diye ayirir. Satirdaki etiket ('chat:',
    'alerts:', 'bildirim:') ya da adresin kendisi (.../chat..., .../alert...) belirler."""
    sonuc = {}
    for satir in metin.splitlines():
        adres = re.search(r"https://\S+", satir)
        if not adres:
            continue
        ipucu = satir.lower()
        if "chat" in ipucu or "sohbet" in ipucu:
            sonuc.setdefault("chat", adres.group(0))
        elif "alert" in ipucu or "bildirim" in ipucu or "uyari" in ipucu:
            sonuc.setdefault("bildirim", adres.group(0))
    return sonuc


def hazirla(cl, ayar):
    """Yayin OBS'inin sahnesini kur: ekran, Xbox sesi, mikrofon + altyazi, chat, bildirimler (hep acik) + mola."""
    obs.yayin_sahnesi(cl, web_adresleri(), ayar["yayin_chat_kutusu"], ayar.get("yayin_mola_gorseli"))


def katmanlar_komutu(dosya):
    ayar = ayar_modulu.yukle()
    with open(dosya, encoding="utf-8-sig") as f:
        adresler = adresleri_ayikla(f.read())
    print("Bulunan: %s" % (", ".join("%s (%s...)" % (t, u.split("?")[0][:40]) for t, u in adresler.items()) or "YOK"))
    if not adresler:
        print("[!] Dosyada 'chat: https://...' / 'alerts: https://...' satirlari yok.")
        return 1
    with open(KATMANLAR, "w", encoding="utf-8") as f:
        json.dump(adresler, f, indent=2)
    if obs.calisiyor_mu(obs.YAYIN):
        hazirla(obs.baglan(30, obs.YAYIN), ayar)
    print("[OK] Kaydedildi; yayin OBS'i her acilista bunlari sahneye koyar: %s" % ", ".join(adresler))
    return 0


# ---------------------------------------------------------------- OBS
def ayarli_mi(cl):
    try:
        a = cl.get_stream_service_settings()
        ayar = getattr(a, "stream_service_settings", None) or {}
        return bool(ayar.get("server")) and bool(ayar.get("key"))
    except Exception:
        return False


def kalite_ayarla(cl, ayar):
    """Basit cikti yayin kodlayicisi: NVENC, CBR (Basit modda sabit), 2 sn anahtar kare (Basit mod varsayilani)."""
    cl.set_profile_parameter("SimpleOutput", "StreamEncoder", "nvenc")
    cl.set_profile_parameter("SimpleOutput", "VBitrate", str(ayar["yayin_bit_hizi"]))
    cl.set_profile_parameter("SimpleOutput", "ABitrate", "160")
    cl.set_profile_parameter("SimpleOutput", "NVENCPreset2", ayar["yayin_on_ayar"])


def kurulu_mu():
    return os.path.exists(obs.exe_yolu(obs.YAYIN)) and os.path.exists(obs.ws_ayar_dosyasi(obs.YAYIN))


def yayin_obs(bekle=90):
    """Yayin OBS'ine baglan; kapaliysa ac. Kurulu degilse RuntimeError."""
    if not kurulu_mu():
        raise RuntimeError("Yayin OBS'i kurulu degil: python -m studyo.yayin --ikinci-obs")
    if not obs.calisiyor_mu(obs.YAYIN):
        obs.baslat(ornek=obs.YAYIN)
    return obs.baglan(bekle, obs.YAYIN)


# ---------------------------------------------------------------- ikinci OBS kurulumu
_ATLA = {"logs", "crashes", "profiler_data", "updates", ".sentinel", "obs-browser"}


def _locations_duzelt(global_ini, yeni_kok):
    """global.ini [Locations] profilleri/sahneleri %APPDATA%'ya yonlendiriyor: kopyada kalsa iki OBS ayni
    profil ve sahne dosyalarini kullanirdi. Hepsi ikinci OBS'in config klasorune cevrilir."""
    with open(global_ini, encoding="utf-8-sig") as f:
        satirlar = f.read().splitlines()
    bolum, yeni = None, []
    deger = yeni_kok.replace("\\", "\\\\")
    for s in satirlar:
        if s.startswith("["):
            bolum = s.strip()
        elif bolum == "[Locations]" and "=" in s:
            s = s.split("=", 1)[0] + "=" + deger
        yeni.append(s)
    with open(global_ini, "w", encoding="utf-8") as f:
        f.write("\n".join(yeni) + "\n")


def ikinci_obs_kur():
    ayar = ayar_modulu.yukle()
    kok = obs.yayin_kok()
    kaynak_exe = ayar["obs_exe"]
    kaynak_kok = os.path.dirname(os.path.dirname(os.path.dirname(kaynak_exe)))  # ...\obs-studio
    for ornek in (obs.KAYIT, obs.YAYIN):
        if obs.calisiyor_mu(ornek):
            try:
                cl = obs.baglan(10, ornek)
                if obs.kayitta_mi(cl) or obs.yayinda_mi(cl):
                    print("[!] %s OBS'i kayitta/yayinda; once durdur." % ornek)
                    return 1
            except Exception:
                pass
    kayit_acikti = obs.calisiyor_mu(obs.KAYIT)
    print("1) OBS'ler kapatiliyor (ayarlar tutarli kopyalansin)...")
    for ornek in (obs.YAYIN, obs.KAYIT):
        if not obs.kapat(ornek):
            print("[!] %s OBS'i kapanmadi." % ornek)
            return 1

    print("2) Program kopyalaniyor: %s -> %s" % (kaynak_kok, kok))
    r = subprocess.run(["robocopy", kaynak_kok, kok, "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/NP", "/R:1", "/W:1"],
                       capture_output=True, text=True)
    if r.returncode >= 8:
        print("[!] Kopyalama hatasi:\n" + r.stdout[-800:])
        return 1
    open(os.path.join(kok, "portable_mode.txt"), "w").close()  # ayarlar <kok>\config altinda

    hedef = obs.ayar_klasoru(obs.YAYIN)
    if not os.path.exists(os.path.join(hedef, "global.ini")):
        print("3) Ayarlar kopyalaniyor (profil, Kick anahtari, sahne)...")
        shutil.copytree(obs.ayar_klasoru(obs.KAYIT), hedef, dirs_exist_ok=True,
                        ignore=lambda d, adlar: [a for a in adlar if a in _ATLA])
        _locations_duzelt(os.path.join(hedef, "global.ini"), os.path.dirname(hedef))
    else:
        print("3) Ayarlar zaten var, korunuyor.")
    # Kopyalanan websocket ayari kayit OBS'inin portunu (4455) tasir: iki OBS ayni portu acamaz
    ws_yolu = obs.ws_ayar_dosyasi(obs.YAYIN)
    mevcut = obs.ws_ayarlari(obs.YAYIN) if os.path.exists(ws_yolu) else {}
    if mevcut.get("server_port") != YAYIN_WS_PORT:
        ws = dict(obs.ws_ayarlari(obs.KAYIT))
        ws.update(server_enabled=True, server_port=YAYIN_WS_PORT, auth_required=True, alerts_enabled=False,
                  first_load=False, server_password=secrets.token_urlsafe(16))  # kayit OBS'inden ayri sifre
        os.makedirs(os.path.dirname(ws_yolu), exist_ok=True)
        with open(ws_yolu, "w", encoding="utf-8") as f:
            json.dump(ws, f, indent=4)

    print("4) Yayin OBS'i aciliyor ve sahnesi kuruluyor...")
    cl2 = yayin_obs(120)
    hazirla(cl2, ayar)
    kalite_ayarla(cl2, ayar)
    print("   Kick ayari: %s | surum: %s" % ("var" if ayarli_mi(cl2) else "YOK -> --kur",
                                           cl2.get_version().obs_version))
    obs.kapat(obs.YAYIN)

    print("5) Kayit OBS'i temizleniyor (yayin katmanlari ve Kick anahtari yalniz yayin OBS'inde)...")
    obs.ws_ac()
    obs.baslat(kaynak_exe)
    cl1 = obs.baglan(120)
    silinen = obs.katmanlari_kaldir(cl1)
    cl1.set_stream_service_settings("rtmp_custom", {"server": "", "key": ""})
    print("   silinen kaynaklar: %s" % (", ".join(silinen) or "yok"))
    if not kayit_acikti:
        obs.kapat(obs.KAYIT)
    print("[OK] Hazir. Yayin OBS'i: %s (websocket %d). Bekci yayin baslarken acar, bitince kapatir." % (
        kok, YAYIN_WS_PORT))
    return 0


# ---------------------------------------------------------------- Kick anahtari
def dosyadan_oku(yol):
    """Metin dosyasindan (adres, anahtar): adres rtmp(s):// ile baslayan ilk sozcuk; anahtar 'key: ...' /
    'anahtar = ...' satiri ya da adres disindaki ilk dolu satir."""
    adres, anahtar = None, None
    with open(yol, encoding="utf-8-sig") as f:
        satirlar = [s.strip() for s in f if s.strip()]
    for s in satirlar:
        bulunan = re.search(r"rtmps?://\S+", s)
        if bulunan and not adres:
            adres = bulunan.group(0)
            continue
        etiketli = re.match(r"^\s*(stream\s*key|key|anahtar|yayin\s*anahtari)\s*[:=]\s*(\S+)\s*$", s, re.I)
        if etiketli:
            anahtar = etiketli.group(2)
        elif anahtar is None and not bulunan:
            anahtar = s.split()[-1]
    return adres, anahtar


def kur(dosya=None):
    ayar = ayar_modulu.yukle()
    print("Kick yayin ayari")
    if dosya:
        adres, anahtar = dosyadan_oku(dosya)
        print("  %s okundu: adres %s, anahtar %s" % (os.path.basename(dosya), "var" if adres else "YOK",
                                                     "var (%d karakter)" % len(anahtar) if anahtar else "YOK"))
        adres, anahtar = adres or "", anahtar or ""
    else:
        print("  1) kick.com > sag ustte profil resmi > Yayinci Paneli (Creator Dashboard)")
        print("     > 'Stream URL and Key' (Kanal ya da Ayarlar menusunde). Gelistirici Modu GEREKMEZ.")
        print("  2) 'Stream URL' ve 'Stream Key' degerlerini kopyalayip asagiya yapistir.")
        print("     Anahtar yazarken ekranda gorunmez; yalniz yayin OBS'inin kendi ayarina yazilir.\n")
        adres = input("Stream URL: ").replace("﻿", "").strip()
    if not adres.lower().startswith(("rtmp://", "rtmps://")):
        print("[!] Adres rtmps:// ile baslamali (Kick panelindeki 'Stream URL'). Vazgecildi.")
        return 1
    if not dosya:
        anahtar = getpass.getpass("Stream Key: ").replace("﻿", "").strip()
    if len(anahtar) < 8:
        print("[!] Anahtar bos ya da cok kisa. Vazgecildi.")
        return 1
    cl = yayin_obs()
    if obs.yayinda_mi(cl):
        print("[!] Su an yayindasin; once yayini kapat.")
        return 1
    cl.set_stream_service_settings("rtmp_custom", {"server": adres, "key": anahtar, "use_auth": False,
                                                   "bwtest": False})
    kalite_ayarla(cl, ayar)
    print("\n[OK] Yayin OBS'i Kick'e ayarlandi (%d kbps, NVENC %s, 1080p60)." % (
        ayar["yayin_bit_hizi"], ayar["yayin_on_ayar"]))
    print("     Oynarken yayini ac/kapat: Telegram kumandasi%s (uzaktan oynatma acikken)." % (
        " ya da klavyede " + ayar["yayin_tusu"] if ayar.get("yayin_tusu") else ""))
    return 0


def dene(cikti=None):
    """Yayin OBS'inin goruntusu: ekran yakalama gizli (masaustu goruntuye girmez), altyazi ornekli."""
    ayar = ayar_modulu.yukle()
    cl = yayin_obs()
    hazirla(cl, ayar)
    obs.ekran_goster(cl, False)
    url = "file:///" + obs.KATMAN_HTML.replace("\\", "/") + "?test=1"
    cl.set_input_settings(obs.KATMAN, {"is_local_file": False, "url": url}, True)
    time.sleep(3)
    cikti = cikti or os.path.join(KOK, "yayin", "deneme.png")
    r = cl.get_source_screenshot(obs.SAHNE, "png", 1920, 1080, -1)
    with open(cikti, "wb") as f:
        f.write(base64.b64decode(r.image_data.split(",", 1)[1]))
    cl.set_input_settings(obs.KATMAN, {"is_local_file": True, "local_file": obs.KATMAN_HTML}, True)
    obs.ekran_goster(cl, True)
    print("[OK] Ornek goruntu: %s" % cikti)
    return cikti


def main(argv=None):
    ap = argparse.ArgumentParser(prog="studyo.yayin", description="Kick canli yayin (ikinci OBS)")
    ap.add_argument("--ikinci-obs", action="store_true", help="yayin OBS'ini kur/guncelle")
    ap.add_argument("--kur", action="store_true", help="Kick yayin adresi ve anahtarini yayin OBS'ine yaz")
    ap.add_argument("--dosya", help="--kur / --katmanlar ile: bilgileri bu metin dosyasindan oku")
    ap.add_argument("--katmanlar", action="store_true",
                    help="Kick chat + bildirim web adreslerini (BotRix) kaydet; --dosya ile")
    ap.add_argument("--dene", action="store_true", help="yayin goruntusunu ornek altyaziyla al")
    arg = ap.parse_args(argv)
    import logging
    logging.getLogger("obsws_python").setLevel(logging.CRITICAL)  # "kaynak yok" kontrolleri hata gibi basilmasin
    if arg.ikinci_obs:
        return ikinci_obs_kur()
    if arg.kur:
        return kur(arg.dosya)
    if arg.katmanlar:
        if not arg.dosya:
            print("--katmanlar icin --dosya gerekli (chat: https://... / alerts: https://... satirlari)")
            return 1
        return katmanlar_komutu(arg.dosya)
    if arg.dene:
        dene()
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
