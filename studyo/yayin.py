"""Kick canli yayini.
- Kurulum: Kick'in yayin adresi ve anahtari OBS'e yazilir (anahtar ekranda gorunmez, baska yere kaydedilmez).
- Bekci (izle.py): Telegram kumandasi (studyo/telegram.py) yayini acar/kapatir; yayin surerken Turkce altyazi
  katmani goruntude olur.
- Yayin araliklari yayin_araliklari.txt'ye yazilir: kurgu o araliklarda altyaziyi tekrar gommez (zaten goruntude).

  python -m studyo.yayin --kur    Kick yayin adresi + anahtari (YAYIN_KUR.bat)
  python -m studyo.yayin --dene   katmani ornek altyaziyla gosterir, OBS'ten ekran goruntusu alir
"""
import argparse
import base64
import datetime
import getpass
import json
import os
import re
import time

from . import ayar as ayar_modulu, obs

KOK = ayar_modulu.KOK
ARALIKLAR = os.path.join(KOK, "yayin_araliklari.txt")
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
PAY_SN = 10  # katman acilip kapanirken ekranda kalan altyazi payi


# ---------------------------------------------------------------- yayin araliklari (git'e girmez)
def olay_yaz(tur, zaman=None):
    zaman = zaman or datetime.datetime.now()
    with open(ARALIKLAR, "a", encoding="utf-8") as f:
        f.write("%s %s\n" % (tur, zaman.isoformat(timespec="seconds")))


def _araliklar():
    """[(bas, son|None)] mutlak zaman. Bekci yayin sirasinda kapandiysa son None kalir."""
    if not os.path.exists(ARALIKLAR):
        return []
    sonuc, acik = [], None
    with open(ARALIKLAR, encoding="utf-8") as f:
        for satir in f:
            parca = satir.split()
            if len(parca) != 2:
                continue
            try:
                t = datetime.datetime.fromisoformat(parca[1])
            except ValueError:
                continue
            if parca[0] == "BASLA":
                if acik is not None:
                    sonuc.append((acik, t))  # BITTI yazilamamis: en gec yeni yayin basinda bitmistir
                acik = t
            elif parca[0] == "BITTI" and acik is not None:
                sonuc.append((acik, t))
                acik = None
    if acik is not None:
        sonuc.append((acik, None))
    return sonuc


def acik_kalani_kapat():
    """Bekci acilisinda: son olay BASLA ise (bekci yayin sirasinda kapanmis) BITTI yaz. Yayin hala suruyorsa
    bekcinin ilk turu hemen yeni BASLA yazar; aradaki birkac saniyelik bosluk PAY_SN icinde kalir."""
    araliklar = _araliklar()
    if araliklar and araliklar[-1][1] is None:
        olay_yaz("BITTI")


def kayittakiler(bas, sure_sn):
    """Kaydin icinde yayinin (altyazi katmaninin goruntude oldugu) araliklari, kayit saniyesi olarak."""
    sonuc = []
    for b, s in _araliklar():
        b_sn = (b - bas).total_seconds() - PAY_SN
        s_sn = sure_sn if s is None else (s - bas).total_seconds() + PAY_SN
        if s_sn > 0 and b_sn < sure_sn:
            sonuc.append([max(0.0, round(b_sn, 1)), min(float(sure_sn), round(s_sn, 1))])
    return sonuc


def gomulmeyecekler(satirlar, araliklar):
    """Canli yayin araligina dusen satirlar videoda zaten var: kurgu bunlari tekrar gommesin."""
    return [s for s in satirlar if any(s.bas < son and s.son > bas for bas, son in araliklar)]


# ---------------------------------------------------------------- Kick chat + bildirimler (BotRix)
KATMANLAR = os.path.join(KOK, "kick_katmanlari.json")  # adreslerde kisisel anahtar var: git'e girmez


def katmanlar_var_mi():
    try:
        with open(KATMANLAR, encoding="utf-8") as f:
            return bool(json.load(f))
    except (OSError, ValueError):
        return False


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


def katmanlari_kur(cl, ayar, adresler=None):
    if adresler is None:
        try:
            with open(KATMANLAR, encoding="utf-8") as f:
                adresler = json.load(f)
        except (OSError, ValueError):
            return []
    kurulan = []
    for tur, url in adresler.items():
        if tur in obs.WEB_KATMANLARI:
            obs.web_katmani_kur(cl, tur, url, ayar["yayin_chat_kutusu"] if tur == "chat" else None)
            kurulan.append(tur)
    obs.katman_goster(cl, obs.yayinda_mi(cl))
    return kurulan


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
    cl = _obs(ayar)
    obs.xbox_sahnesi(cl)
    print("[OK] OBS'e eklendi (yalniz yayinda gorunur): %s" % ", ".join(katmanlari_kur(cl, ayar, adresler)))
    return 0


# ---------------------------------------------------------------- OBS
def ayarli_mi(cl):
    try:
        a = cl.get_stream_service_settings()
        ayar = _deger(a, "stream_service_settings") or {}
        return bool(ayar.get("server")) and bool(ayar.get("key"))
    except Exception:
        return False


def _deger(yanit, ad):
    return getattr(yanit, ad, None)


def kalite_ayarla(cl, ayar):
    """Basit cikti yayin kodlayicisi: NVENC, CBR (Basit modda sabit), 2 sn anahtar kare (Basit mod varsayilani).
    Yayin/kayit surerken degisiklik bir sonraki baslatmada gecerli olur."""
    cl.set_profile_parameter("SimpleOutput", "StreamEncoder", "nvenc")
    cl.set_profile_parameter("SimpleOutput", "VBitrate", str(ayar["yayin_bit_hizi"]))
    cl.set_profile_parameter("SimpleOutput", "ABitrate", "160")
    cl.set_profile_parameter("SimpleOutput", "NVENCPreset2", ayar["yayin_on_ayar"])


def _obs(ayar):
    if not obs.calisiyor_mu():
        obs.ws_ac()
        obs.baslat(ayar["obs_exe"])
    return obs.baglan(90)


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
        print("     Anahtar yazarken ekranda gorunmez; yalniz OBS'in kendi ayarina yazilir.\n")
        adres = input("Stream URL: ").replace("﻿", "").strip()
    if not adres.lower().startswith(("rtmp://", "rtmps://")):
        print("[!] Adres rtmps:// ile baslamali (Kick panelindeki 'Stream URL'). Vazgecildi.")
        return 1
    if not dosya:
        anahtar = getpass.getpass("Stream Key: ").replace("﻿", "").strip()
    if len(anahtar) < 8:
        print("[!] Anahtar bos ya da cok kisa. Vazgecildi.")
        return 1
    cl = _obs(ayar)
    if obs.yayinda_mi(cl):
        print("[!] OBS su an yayinda; once yayini kapat.")
        return 1
    cl.set_stream_service_settings("rtmp_custom", {"server": adres, "key": anahtar, "use_auth": False,
                                                   "bwtest": False})
    # Basit cikti: NVENC, CBR; anahtar kare araligi 2 sn (Kick'in istedigi)
    kalite_ayarla(cl, ayar)
    obs.xbox_sahnesi(cl)
    print("\n[OK] OBS Kick'e ayarlandi (%d kbps, NVENC %s, 1080p60)." % (ayar["yayin_bit_hizi"], ayar["yayin_on_ayar"]))
    print("     Oynarken yayini ac/kapat: Telegram kumandasi%s (uzaktan oynatma acikken)." % (
        " ya da klavyede " + ayar["yayin_tusu"] if ayar.get("yayin_tusu") else ""))
    return 0


def dene(cikti=None):
    """Katmani ornek altyaziyla acar, OBS ciktisinin ekran goruntusunu alir, katmani eski haline getirir."""
    ayar = ayar_modulu.yukle()
    cl = _obs(ayar)
    obs.xbox_sahnesi(cl)
    gorunur = cl.get_scene_item_enabled(obs.SAHNE, obs._oge(cl, obs.KATMAN)).scene_item_enabled
    url = "file:///" + obs.KATMAN_HTML.replace("\\", "/") + "?test=1"
    cl.set_input_settings(obs.KATMAN, {"is_local_file": False, "url": url}, True)
    obs.katman_goster(cl, True)
    time.sleep(3)
    cikti = cikti or os.path.join(KOK, "yayin", "deneme.png")
    r = cl.get_source_screenshot(obs.SAHNE, "png", 1920, 1080, -1)
    veri = r.image_data.split(",", 1)[1]
    with open(cikti, "wb") as f:
        f.write(base64.b64decode(veri))
    cl.set_input_settings(obs.KATMAN, {"is_local_file": True, "local_file": obs.KATMAN_HTML}, True)
    obs.katman_goster(cl, gorunur)
    print("[OK] Ornek goruntu: %s" % cikti)
    return cikti


def main(argv=None):
    ap = argparse.ArgumentParser(prog="studyo.yayin", description="Kick canli yayin")
    ap.add_argument("--kur", action="store_true", help="Kick yayin adresi ve anahtarini OBS'e yaz")
    ap.add_argument("--dosya", help="--kur / --katmanlar ile: bilgileri bu metin dosyasindan oku")
    ap.add_argument("--katmanlar", action="store_true",
                    help="Kick chat + bildirim web adreslerini (BotRix) OBS'e ekle; --dosya ile")
    ap.add_argument("--dene", action="store_true", help="altyazi katmanini ornekle goster, ekran goruntusu al")
    arg = ap.parse_args(argv)
    import logging
    logging.getLogger("obsws_python").setLevel(logging.CRITICAL)  # "kaynak yok" kontrolleri hata gibi basilmasin
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
