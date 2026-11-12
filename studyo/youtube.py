"""YouTube Data API: yukleme (varsayilan GIZLI), Ingilizce baslik/aciklama, bolumler, altyazi parcalari,
oynatma listeleri, zamanlanmis yayin. Yorumlar: studyo/yorumlar.py, performans raporu: studyo/rapor.py.

2 Kasim 2026'dan beri denetimden (audit) gecmemis API projelerinden yuklenen videolar gizliye kilitlenmiyor
(YouTube Data API revision history). Yukleme kotasi ayri: gunde 100 video. Diger islemler gunde 10.000 birim
(altyazi parcasi 400, liste/guncelleme/kapak 50, okuma 1).

Kurulum (bir kez): README > "YouTube'a otomatik yukleme". Kisaca: Google Cloud'da proje + YouTube Data API v3
(+ rapor icin YouTube Analytics API) + OAuth istemcisi (Masaustu) -> client_secret.json -> python -m studyo.youtube --kur
"""
import argparse
import datetime
import json
import os

from .ayar import KOK

_G = "https://www.googleapis.com/auth/"
KAPSAM_YUKLE = [_G + "youtube.upload", _G + "youtube.readonly"]
# force-ssl: altyazi parcasi, oynatma listesi, video guncelleme, yorum cevabi | yt-analytics: performans raporu
KAPSAM_TAM = KAPSAM_YUKLE + [_G + "youtube.force-ssl", _G + "yt-analytics.readonly"]
KAPSAM_ANALIZ = [_G + "yt-analytics.readonly", _G + "youtube.readonly"]
SIRLAR = os.path.join(KOK, "client_secret.json")
JETON = os.path.join(KOK, "token.json")
DURUM = os.path.join(KOK, "youtube_durum.json")
KATEGORI_OYUN = "20"


class GirisGerekli(Exception):
    """Jeton yok, gecersiz ya da istenen izin verilmemis: arka planda tarayici acilmaz, --kur gerekir."""


# ---------------------------------------------------------------- yerel kayit (youtube_durum.json, git'e girmez)
def durum_oku():
    try:
        with open(DURUM, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    d.setdefault("videolar", [])
    d.setdefault("listeler", {})
    d.setdefault("yorum_islenen", [])
    return d


def durum_yaz(d):
    gecici = DURUM + ".yeni"
    with open(gecici, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    os.replace(gecici, DURUM)


def video_kaydet(bilgi):
    d = durum_oku()
    d["videolar"] = [v for v in d["videolar"] if v.get("id") != bilgi["id"]] + [bilgi]
    durum_yaz(d)


# ---------------------------------------------------------------- kimlik
def _kimlik(gerekli=KAPSAM_YUKLE, etkilesimli=False):
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    kimlik = Credentials.from_authorized_user_file(JETON) if os.path.exists(JETON) else None
    if kimlik is not None:
        verilen = set(getattr(kimlik, "granted_scopes", None) or kimlik.scopes or [])
        if not set(gerekli) <= verilen:
            if not etkilesimli:
                raise GirisGerekli("Yeni YouTube izni gerekli (altyazi/liste/yorum/rapor): python -m studyo.youtube --kur")
            kimlik = None
    if kimlik is not None and not kimlik.valid and kimlik.refresh_token:
        try:
            kimlik.refresh(Request())
        except RefreshError:
            kimlik = None  # izin geri alinmis ya da suresi dolmus
    if kimlik is None or not kimlik.valid:
        if not etkilesimli:
            raise GirisGerekli("YouTube izni yok ya da suresi doldu: python -m studyo.youtube --kur")
        if not os.path.exists(SIRLAR):
            raise SystemExit("client_secret.json yok (%s). README > 'YouTube'a otomatik yukleme'." % SIRLAR)
        from google_auth_oauthlib.flow import InstalledAppFlow
        kimlik = InstalledAppFlow.from_client_secrets_file(SIRLAR, KAPSAM_TAM).run_local_server(
            port=0, prompt="consent", authorization_prompt_message="Tarayicida kanal hesabinla giris yap...")
    with open(JETON, "w", encoding="utf-8") as f:
        f.write(kimlik.to_json())
    return kimlik


def _servis(gerekli=KAPSAM_YUKLE, etkilesimli=False):
    from googleapiclient.discovery import build
    return build("youtube", "v3", credentials=_kimlik(gerekli, etkilesimli), cache_discovery=False)


def analitik_servis():
    from googleapiclient.discovery import build
    return build("youtubeAnalytics", "v2", credentials=_kimlik(KAPSAM_ANALIZ), cache_discovery=False)


def tam_izin_var_mi():
    try:
        _kimlik(KAPSAM_TAM)
        return True
    except GirisGerekli:
        return False


def kanal(servis=None):
    servis = servis or _servis()
    r = servis.channels().list(part="snippet", mine=True).execute()
    ogeler = r.get("items") or []
    return (ogeler[0]["snippet"]["title"], ogeler[0]["id"]) if ogeler else (None, None)


# ---------------------------------------------------------------- video
def _govde(baslik, aciklama, etiketler, yerel):
    snippet = {"title": baslik[:100], "description": aciklama[:5000], "tags": etiketler,
               "categoryId": KATEGORI_OYUN, "defaultLanguage": "tr", "defaultAudioLanguage": "en"}
    govde = {"snippet": snippet}
    if yerel:
        # {"en": {"title": ..., "description": ...}}: izleyicinin dili Ingilizceyse YouTube bunu gosterir
        govde["localizations"] = {dil: {"title": d["title"][:100], "description": d["description"][:5000]}
                                  for dil, d in yerel.items() if d.get("title")}
    return govde


def yayin_zamani(saat_metni, gun_sonra=1, simdi=None):
    """"20:00" -> yarin 20:00 (bilgisayarin saat dilimi), YouTube icin UTC ISO."""
    simdi = simdi or datetime.datetime.now().astimezone()
    sa, dk = (int(x) for x in saat_metni.split(":"))
    t = (simdi + datetime.timedelta(days=gun_sonra)).replace(hour=sa, minute=dk, second=0, microsecond=0)
    return t.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def yukle(dosya, baslik, aciklama, etiketler, gizlilik="private", kapak=None, gunluk=print, yerel=None, yayin=None):
    """Videoyu yukler, kapak varsa ekler; video kimligini dondurur. yayin: UTC ISO zaman (zamanlanmis yayin)."""
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    servis = _servis()
    govde = _govde(baslik, aciklama, etiketler, yerel)
    govde["status"] = {"privacyStatus": "private" if yayin else gizlilik, "selfDeclaredMadeForKids": False,
                       "containsSyntheticMedia": False}
    if yayin:
        govde["status"]["publishAt"] = yayin
    istek = servis.videos().insert(part=",".join(govde), body=govde,
                                   media_body=MediaFileUpload(dosya, chunksize=16 * 1024 * 1024, resumable=True))
    cevap, son_yuzde = None, -1
    while cevap is None:
        durum, cevap = istek.next_chunk()
        if durum and int(durum.progress() * 100) // 25 != son_yuzde // 25:
            son_yuzde = int(durum.progress() * 100)
            gunluk("    yukleniyor %%%d" % son_yuzde)
    kimlik = cevap["id"]
    if kapak and os.path.exists(kapak):
        try:
            servis.thumbnails().set(videoId=kimlik, media_body=MediaFileUpload(kapak, mimetype="image/jpeg")).execute()
        except HttpError as e:
            # Ozel kapak icin kanalin telefonla dogrulanmis olmasi gerekir (youtube.com/verify)
            gunluk("    kapak eklenemedi (kanal dogrulamasi gerekebilir: youtube.com/verify): %s" % str(e)[:150])
    return kimlik


def guncelle(video_id, baslik, aciklama, etiketler, yerel=None):
    """Yuklenmis videonun baslik/aciklama/etiket ve Ingilizce bilgilerini yeniler (gizlilige dokunmaz)."""
    govde = _govde(baslik, aciklama, etiketler, yerel)
    govde["id"] = video_id
    _servis(KAPSAM_TAM).videos().update(part=",".join(k for k in govde if k != "id"), body=govde).execute()


def altyazi_yukle(video_id, srt, dil, ad, servis=None):
    """SRT'yi ayri altyazi parcasi olarak yukler (400 birim). Ayni dilde parca varsa tekrar yuklemez."""
    from googleapiclient.http import MediaFileUpload
    servis = servis or _servis(KAPSAM_TAM)
    mevcut = servis.captions().list(part="snippet", videoId=video_id).execute().get("items") or []
    if any(c["snippet"].get("language") == dil and c["snippet"].get("trackKind") != "asr" for c in mevcut):
        return False
    servis.captions().insert(
        part="snippet", body={"snippet": {"videoId": video_id, "language": dil, "name": ad, "isDraft": False}},
        media_body=MediaFileUpload(srt, mimetype="application/octet-stream")).execute()
    return True


def liste_kimligi(ad, aciklama="", servis=None):
    """Kanalda bu adda oynatma listesi varsa onu, yoksa yenisini (herkese acik) dondurur; youtube_durum.json'da saklanir."""
    d = durum_oku()
    if d["listeler"].get(ad):
        return d["listeler"][ad]
    servis = servis or _servis(KAPSAM_TAM)
    istek = servis.playlists().list(part="snippet", mine=True, maxResults=50)
    while istek is not None:
        cevap = istek.execute()
        for p in cevap.get("items", []):
            if p["snippet"]["title"].strip().lower() == ad.strip().lower():
                d["listeler"][ad] = p["id"]
                durum_yaz(d)
                return p["id"]
        istek = servis.playlists().list_next(istek, cevap)
    yeni = servis.playlists().insert(part="snippet,status", body={
        "snippet": {"title": ad[:150], "description": aciklama[:5000], "defaultLanguage": "tr"},
        "status": {"privacyStatus": "public"}}).execute()
    d = durum_oku()
    d["listeler"][ad] = yeni["id"]
    durum_yaz(d)
    return yeni["id"]


def listeye_ekle(video_id, liste_id, servis=None):
    servis = servis or _servis(KAPSAM_TAM)
    var = servis.playlistItems().list(part="id", playlistId=liste_id, videoId=video_id).execute().get("items")
    if var:
        return False
    servis.playlistItems().insert(part="snippet", body={
        "snippet": {"playlistId": liste_id, "resourceId": {"kind": "youtube#video", "videoId": video_id}}}).execute()
    return True


# ---------------------------------------------------------------- kanal "Hakkinda" metni
HAKKINDA = os.path.join(KOK, "kanal_hakkinda.txt")
HAKKINDA_YEDEK = os.path.join(KOK, "kanal_hakkinda.yedek.txt")
HAKKINDA_SINIR = 1000


def kanal_hakkinda(metin=None, servis=None):
    """metin None ise mevcut metni dondurur; verilirse kanala yazar (once eskisini yedekler).
    brandingSettings.update eksik alanlari SILER: once tamami okunur, yalniz aciklama degistirilir."""
    servis = servis or _servis(KAPSAM_TAM)
    k = servis.channels().list(part="brandingSettings", mine=True).execute()["items"][0]
    bs = k.setdefault("brandingSettings", {})
    eski = bs.get("channel", {}).get("description", "")
    if metin is None:
        return eski
    if len(metin) > HAKKINDA_SINIR or "<" in metin or ">" in metin:
        raise ValueError("Hakkinda metni en fazla %d karakter olmali ve < > icermemeli" % HAKKINDA_SINIR)
    with open(HAKKINDA_YEDEK, "w", encoding="utf-8") as f:
        f.write(eski)
    bs.setdefault("channel", {})["description"] = metin
    servis.channels().update(part="brandingSettings", body={"id": k["id"], "brandingSettings": bs}).execute()
    return kanal_hakkinda(servis=servis)


def _hakkinda_komutu():
    with open(HAKKINDA, encoding="utf-8") as f:
        yeni = f.read().strip()
    servis = _servis(KAPSAM_TAM)
    eski = kanal_hakkinda(servis=servis)
    if eski.strip() == yeni:
        print("[OK] Kanal Hakkinda metni zaten guncel.")
        return
    print("---- YENI METIN (%d/%d karakter) ----\n%s\n-------------------------------------" % (
        len(yeni), HAKKINDA_SINIR, yeni))
    # PowerShell'den borulanan girdinin basinda BOM (﻿) olur; strip() onu silmez
    if input("Kanala yazilsin mi? (e/h): ").replace("﻿", "").strip().lower() not in ("e", "evet", "y"):
        print("Vazgecildi, kanal degismedi.")
        return
    son = kanal_hakkinda(yeni, servis)
    print("[OK] Guncellendi." if son.strip() == yeni else "[!] Yazildi ama dogrulanamadi, Studio'dan bakin.")
    print("     Eski metin yedegi: %s" % HAKKINDA_YEDEK)


# ---------------------------------------------------------------- komut satiri
def main(argv=None):
    ap = argparse.ArgumentParser(prog="studyo.youtube", description="YouTube izni")
    ap.add_argument("--kur", action="store_true", help="tarayicida kanal hesabiyla izin ver (bir kez)")
    ap.add_argument("--kontrol", action="store_true", help="izin gecerli mi, hangi kanal")
    ap.add_argument("--hakkinda", action="store_true", help="kanal_hakkinda.txt'yi kanalin Hakkinda metni yap (onay sorar)")
    arg = ap.parse_args(argv)
    if arg.hakkinda:
        _hakkinda_komutu()
        return
    if arg.kur:
        if os.path.exists(JETON):
            os.remove(JETON)  # baska kanal secilebilsin, yeni izinler istensin
        servis = _servis(KAPSAM_TAM, etkilesimli=True)
    elif arg.kontrol:
        try:
            servis = _servis()
        except GirisGerekli as e:
            print("[!] %s" % e)
            return
    else:
        ap.print_help()
        return
    ad, kanal_id = kanal(servis)
    if not ad:
        print("[!] Bu hesapta YouTube kanali yok. --kur ile kanalin oldugu hesabi (marka hesabi) secin.")
        return
    print("[OK] YouTube kanali: %s (https://youtube.com/channel/%s)" % (ad, kanal_id))
    print("     Tam izin (altyazi, liste, yorum, rapor): %s" % ("var" if tam_izin_var_mi() else "YOK -> --kur"))


if __name__ == "__main__":
    main()
