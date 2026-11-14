"""Instagram Reels: YouTube'da herkese acik olan Shorts'u Instagram'a da yayinla (Meta Graph API).

Karar YouTube'da verilir: Instagram API'sinde gizli/taslak yukleme yok, yayinlanan Reels hemen herkese acik.
Bekci (izle.py) 10 dakikada bir YouTube'a bakar; Studio'da herkese actigin (ya da zamani gelip acilan) Shorts
buraya gelir. Canli yayin sirasinda beklenir.

Akis (Instagram API, Facebook altyapisi): kap olustur (media_type=REELS, upload_type=resumable) -> dosyayi
rupload.facebook.com'a dogrudan gonder (internete acik bir adres gerekmez) -> Instagram isleyene kadar bekle
(status_code FINISHED) -> media_publish. Yayinlanmayan kap 24 saatte kendiliginden silinir.

Reels sartlari: H.264, en fazla 25 Mbps, AAC 48 kHz, moov basta, 3 sn - 15 dk, 300 MB. Shorts ~24 Mbps ortalama
ile cikiyor (anlik tepeler sinirin ustune cikabilir), bu yuzden Instagram'a tepesi 20 Mbps ile sinirli ayri bir
kopya gider (short_N_reels.mp4); YouTube'daki kalite degismez.

Kurulum (bir kez, README > "Instagram Reels"): developers.facebook.com'da uygulama (Instagram API, Unified login),
uygulama kanalin isletme portfoyune bagli, Instagram hesabi "Instagram Tester", panelden "Generate token".
instagram.json (git'e girmez): {"erisim_anahtari": "EAA...", "ig_kullanici_id": "1784...",
"graph": "https://graph.facebook.com/v24.0"}. Bu sistem kullanicisi anahtarinin suresi dolmaz.

  python -m studyo.instagram --durum          baglanti, kota, bekleyen Shorts
  python -m studyo.instagram --dene DOSYA     kap + yukleme + isleme; YAYINLAMAZ (24 saatte silinir)
  python -m studyo.instagram --paylas         YouTube'da herkese acik olup henuz gitmemis Shorts'u yayinla
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

from .ayar import KOK

AYAR = os.path.join(KOK, "instagram.json")
DURUM = os.path.join(KOK, "instagram_durum.json")
UPLOAD = "https://rupload.facebook.com/ig-api-upload"
EN_FAZLA_DENEME = 3  # ayni Shorts bu kadar kez basarisiz olursa birakilir (bildirim gelir)


class MetaHatasi(Exception):
    pass


# ---------------------------------------------------------------- ayar / durum
def ayar_oku():
    try:
        with open(AYAR, encoding="utf-8") as f:
            a = json.load(f)
    except (OSError, ValueError):
        return None
    if not a.get("erisim_anahtari") or not a.get("ig_kullanici_id"):
        return None
    a.setdefault("graph", "https://graph.facebook.com/v24.0")
    return a


def hazir_mi():
    return ayar_oku() is not None


def durum_oku():
    try:
        with open(DURUM, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    d.setdefault("paylasilan", {})  # youtube_id -> {ig_id, permalink, tarih, dosya}
    d.setdefault("hatalar", {})  # youtube_id -> {sayi, son, mesaj}
    return d


def durum_yaz(d):
    gecici = DURUM + ".yeni"
    with open(gecici, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    os.replace(gecici, DURUM)


# ---------------------------------------------------------------- Graph API
def _istek(a, yontem, url, alanlar=None, govde=None, basliklar=None, zaman_asimi=60):
    """alanlar: form/sorgu parametreleri (anahtar eklenir). govde: ham bayt (yukleme). Hata mesajinda anahtar gizlenir."""
    anahtar = a["erisim_anahtari"]
    if not url.startswith("http"):
        url = a["graph"] + url
    basliklar = dict(basliklar or {})
    veri = govde
    if govde is None:
        p = dict(alanlar or {})
        p["access_token"] = anahtar
        kodlu = urllib.parse.urlencode(p)
        if yontem == "GET":
            url += "?" + kodlu
        else:
            veri = kodlu.encode()
            basliklar["Content-Type"] = "application/x-www-form-urlencoded"
    istek = urllib.request.Request(url, data=veri, method=yontem, headers=basliklar)
    try:
        with urllib.request.urlopen(istek, timeout=zaman_asimi) as y:
            return json.load(y)
    except urllib.error.HTTPError as h:
        metin = h.read().decode("utf-8", "replace").replace(anahtar, "***")
        try:
            j = json.loads(metin)
            hata = j.get("error") or {}
            if hata:
                metin = "%s (kod %s/%s)" % (hata.get("error_user_msg") or hata.get("message"), hata.get("code"),
                                            hata.get("error_subcode"))
            elif j.get("debug_info"):  # rupload.facebook.com hata bicimi
                metin = "%s: %s" % (j["debug_info"].get("type"), j["debug_info"].get("message"))
        except (ValueError, AttributeError):
            pass
        raise MetaHatasi("HTTP %d: %s" % (h.code, metin[:400])) from None
    except urllib.error.URLError as e:
        raise MetaHatasi("baglanti: %s" % e.reason) from None


def hesap(a=None):
    a = a or ayar_oku()
    return _istek(a, "GET", "/" + a["ig_kullanici_id"], {"fields": "id,username,name,media_count,followers_count"})


def kota(a=None):
    a = a or ayar_oku()
    r = _istek(a, "GET", "/%s/content_publishing_limit" % a["ig_kullanici_id"], {"fields": "config,quota_usage"})
    v = (r.get("data") or [{}])[0]
    return v.get("quota_usage", 0), (v.get("config") or {}).get("quota_total", 100)


# ---------------------------------------------------------------- dosya
def reels_kopyasi(kaynak, gunluk=print):
    """short_1.mp4 -> short_1_reels.mp4 (tepe 20 Mbps, AAC 128k 48 kHz, faststart). Varsa ve yeniyse tekrar yapilmaz."""
    from . import kurgu

    hedef = os.path.splitext(kaynak)[0] + "_reels.mp4"
    if os.path.exists(hedef) and os.path.getmtime(hedef) >= os.path.getmtime(kaynak) and os.path.getsize(hedef) > 0:
        return hedef
    ad, _ = kurgu.kodlayici()
    video = {
        "h264_nvenc": ["-c:v", "h264_nvenc", "-preset", "p6", "-tune", "hq", "-rc", "vbr", "-cq", "21",
                       "-b:v", "14M", "-maxrate", "20M", "-bufsize", "40M", "-profile:v", "high", "-g", "120",
                       "-spatial-aq", "1"],
        "h264_qsv": ["-c:v", "h264_qsv", "-preset", "medium", "-global_quality", "22", "-maxrate", "20M",
                     "-bufsize", "40M", "-g", "120"],
    }.get(ad, ["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-maxrate", "20M", "-bufsize", "40M",
               "-g", "120", "-profile:v", "high"])
    gecici = hedef + ".yeni.mp4"
    komut = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", kaynak, "-map", "0:v:0", "-map", "0:a:0?",
             *video, "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
             "-movflags", "+faststart", gecici]
    gunluk("  Reels kopyasi: %s (%s)" % (os.path.basename(hedef), ad))
    r = subprocess.run(komut, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode != 0 or not os.path.exists(gecici):
        raise MetaHatasi("ffmpeg: " + (r.stderr or "")[-300:])
    os.replace(gecici, hedef)
    return hedef


def aciklama_olustur(cikti, etiket, ek=""):
    """yukleme_bilgisi.txt'teki baslik + ilk aciklama paragrafi + ek (kanal, hashtag'ler). En fazla 2200 karakter."""
    yol = os.path.join(cikti, "yukleme_bilgisi.txt")
    baslik = aciklama = ""
    try:
        metin = open(yol, encoding="utf-8").read()
        bolum = re.search(r"=====\s*%s:.*?=====(.*?)(?:\n=====|\Z)" % re.escape(etiket), metin, re.S)
        if bolum:
            b = bolum.group(1)
            m = re.search(r"BASLIK:\s*\n(.+)", b)
            baslik = re.sub(r"\s*#Shorts\b", "", m.group(1)).strip() if m else ""
            m = re.search(r"ACIKLAMA:\s*\n(.+?)(?:\n\s*\n|\Z)", b, re.S)
            aciklama = m.group(1).strip() if m else ""
    except OSError:
        pass
    parcalar = [p for p in (baslik, aciklama, "🎮 GTA V · Türkçe altyazılı oynanış\n🤖 Altyazılar yapay zekâ ile canlı çevrildi.",
                            ek.strip()) if p]
    return "\n\n".join(parcalar)[:2200]


# ---------------------------------------------------------------- yayin akisi
def reels_gonder(dosya, aciklama, yayinla=True, gunluk=print, a=None):
    """Kap + dogrudan yukleme + isleme bekleme (+ yayin). Donus: {"kap": id, "ig_id": id|None, "permalink": url|None}."""
    a = a or ayar_oku()
    if a is None:
        raise MetaHatasi("instagram.json yok ya da eksik (README > Instagram Reels)")
    boyut = os.path.getsize(dosya)
    if boyut > 300 * 1024 * 1024:
        raise MetaHatasi("dosya 300 MB'tan buyuk: %s" % dosya)
    ig = a["ig_kullanici_id"]
    with open(dosya, "rb") as f:
        veri = f.read()
    # rupload, yeni olusturulan kabi bazen henuz taniyamiyor ve "ProcessingFailedError" donuyor (olculdu: ayni
    # dosya/aciklama bir denemede geciyor, digerinde reddediliyor). Kisa bekleyip tekrar dene; olmazsa yeni kap.
    son_hata = None
    for kap_denemesi in range(3):
        kap = _istek(a, "POST", "/%s/media" % ig, {"media_type": "REELS", "upload_type": "resumable",
                                                  "caption": aciklama, "share_to_feed": "true"})
        kap_id = kap["id"]
        gunluk("  kap: %s, yukleniyor (%.1f MB)" % (kap_id, boyut / 1048576))
        url = kap.get("uri") or "%s/%s/%s" % (UPLOAD, a["graph"].rsplit("/", 1)[-1], kap_id)
        for deneme in range(4):
            time.sleep(5 + 10 * deneme)
            try:
                r = _istek(a, "POST", url, govde=veri, zaman_asimi=600, basliklar={
                    "Authorization": "OAuth " + a["erisim_anahtari"], "offset": "0", "file_size": str(boyut),
                    "Content-Type": "application/octet-stream"})
                if not r.get("success", True):
                    raise MetaHatasi("yukleme reddedildi: %s" % r)
                son_hata = None
                break
            except MetaHatasi as e:
                son_hata = e
                if "ProcessingFailed" not in str(e):
                    raise
                gunluk("  yukleme reddedildi (gecici), tekrar: %d" % (deneme + 1))
        if son_hata is None:
            break
    if son_hata is not None:
        raise son_hata
    bas = time.time()
    while True:
        s = _istek(a, "GET", "/" + kap_id, {"fields": "status_code,status"})
        kod = s.get("status_code")
        if kod == "FINISHED":
            break
        if kod in ("ERROR", "EXPIRED"):
            raise MetaHatasi("Instagram isleyemedi: %s %s" % (kod, s.get("status", "")))
        if time.time() - bas > 900:
            raise MetaHatasi("Instagram 15 dakikada isleyemedi (son durum %s)" % kod)
        time.sleep(15)
    gunluk("  islendi (%.0f sn)" % (time.time() - bas))
    if not yayinla:
        return {"kap": kap_id, "ig_id": None, "permalink": None}
    m = _istek(a, "POST", "/%s/media_publish" % ig, {"creation_id": kap_id})
    ig_id = m["id"]
    try:
        link = _istek(a, "GET", "/" + ig_id, {"fields": "permalink"}).get("permalink")
    except MetaHatasi:
        link = None
    gunluk("  YAYINDA: %s" % (link or ig_id))
    return {"kap": kap_id, "ig_id": ig_id, "permalink": link}


def _shorts_dosyasi(v):
    m = re.match(r"SHORTS\s+(\d+)", v.get("etiket", ""))
    if not m or not v.get("cikti"):
        return None
    yol = os.path.join(v["cikti"], "short_%s.mp4" % m.group(1))
    return yol if os.path.exists(yol) else None


def bekleyenler(gunluk=print):
    """YouTube'da herkese acik, dosyasi duran ve henuz Instagram'a gitmemis Shorts (youtube_durum.json kaydindan)."""
    from . import youtube

    d, yt = durum_oku(), youtube.durum_oku()
    adaylar = [v for v in yt["videolar"] if v.get("tur") == "shorts" and v["id"] not in d["paylasilan"]
               and d["hatalar"].get(v["id"], {}).get("sayi", 0) < EN_FAZLA_DENEME]
    if not adaylar:
        return []
    servis = youtube._servis()
    acik = set()
    for i in range(0, len(adaylar), 50):
        r = servis.videos().list(part="status", id=",".join(v["id"] for v in adaylar[i:i + 50])).execute()
        acik |= {it["id"] for it in r.get("items", []) if it["status"].get("privacyStatus") == "public"}
    sonuc = []
    for v in adaylar:
        if v["id"] not in acik:
            continue
        dosya = _shorts_dosyasi(v)
        if dosya is None:
            gunluk("  %s herkese acik ama dosyasi yok, atlandi" % v["id"])
            continue
        sonuc.append(dict(v, dosya=dosya))
    return sonuc


def takip_et(ek="", gunluk=print, bildir=None, en_fazla=3):
    """Bekleyen Shorts'u (eskiden yeniye) Reels olarak yayinla. Donus: yayinlanan sayisi."""
    a = ayar_oku()
    if a is None:
        return 0
    bekleyen = sorted(bekleyenler(gunluk), key=lambda v: v.get("yukleme", ""))[:en_fazla]
    sayi = 0
    for v in bekleyen:
        gunluk("Instagram: %s (%s)" % (v["baslik"], v["id"]))
        try:
            dosya = reels_kopyasi(v["dosya"], gunluk)
            sonuc = reels_gonder(dosya, aciklama_olustur(v["cikti"], v["etiket"], ek), True, gunluk, a)
        except Exception as e:
            d = durum_oku()
            h = d["hatalar"].setdefault(v["id"], {"sayi": 0})
            h.update(sayi=h["sayi"] + 1, son=_simdi(), mesaj=str(e)[:300])
            durum_yaz(d)
            gunluk("  HATA: %s" % e)
            if bildir and h["sayi"] >= EN_FAZLA_DENEME:
                bildir("Instagram: Reels gonderilemedi", "%s\n%s" % (v["baslik"][:80], str(e)[:150]))
            continue
        d = durum_oku()
        d["paylasilan"][v["id"]] = {"ig_id": sonuc["ig_id"], "permalink": sonuc["permalink"], "tarih": _simdi(),
                                    "dosya": v["dosya"], "baslik": v["baslik"]}
        d["hatalar"].pop(v["id"], None)
        durum_yaz(d)
        sayi += 1
        if bildir:
            bildir("📸 Reels yayınlandı", "%s\n%s" % (v["baslik"][:90], sonuc["permalink"] or ""))
    return sayi


def _simdi():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


# ---------------------------------------------------------------- komut satiri
def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m studyo.instagram", description="Instagram Reels")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--durum", action="store_true", help="baglanti, kota ve bekleyen Shorts")
    g.add_argument("--dene", metavar="DOSYA", help="kap + yukleme + isleme, YAYINLAMAZ")
    g.add_argument("--paylas", action="store_true", help="YouTube'da herkese acik Shorts'u Reels olarak yayinla")
    args = p.parse_args(argv)
    from .ayar import yukle

    ayar = yukle()
    if args.durum:
        h = hesap()
        print("Hesap: @%s (%s), %s gonderi, %s takipci" % (h.get("username"), h.get("name"), h.get("media_count"),
                                                           h.get("followers_count")))
        print("Kota: %d / %d (24 saat)" % kota())
        for v in bekleyenler():
            print("  bekliyor: %s %s" % (v["id"], v["baslik"]))
        for yid, s in durum_oku()["paylasilan"].items():
            print("  paylasildi: %s -> %s" % (yid, s.get("permalink")))
    elif args.dene:
        dosya = reels_kopyasi(os.path.abspath(args.dene))
        print(reels_gonder(dosya, "deneme (yayinlanmaz)", yayinla=False))
    else:
        print("Yayinlanan: %d" % takip_et(ayar.get("instagram_ek", "")))


if __name__ == "__main__":
    main()
