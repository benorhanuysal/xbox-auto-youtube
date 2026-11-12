"""YouTube Data API ile yukleme (varsayilan GIZLI: Studio'da kontrol edip yayinlarsin).

2 Kasim 2026'dan beri denetimden (audit) gecmemis API projelerinden yuklenen videolar gizliye kilitlenmiyor
(YouTube Data API revision history). Yukleme kotasi ayri: gunde 100 video.

Kurulum (bir kez): README > "YouTube'a otomatik yukleme". Kisaca: Google Cloud'da proje + YouTube Data API v3 +
OAuth istemcisi (Masaustu uygulamasi) -> client_secret.json bu klasore -> python -m studyo.youtube --kur
"""
import argparse
import os

from .ayar import KOK

KAPSAM = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly"]  # readonly: hangi kanala yuklendigini gostermek icin
SIRLAR = os.path.join(KOK, "client_secret.json")
JETON = os.path.join(KOK, "token.json")
KATEGORI_OYUN = "20"


class GirisGerekli(Exception):
    """Jeton yok ya da gecersiz: arka planda tarayici acilmaz, kullanici --kur calistirmali."""


def _kimlik(etkilesimli=False):
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    kimlik = Credentials.from_authorized_user_file(JETON, KAPSAM) if os.path.exists(JETON) else None
    if kimlik and not kimlik.valid and kimlik.expired and kimlik.refresh_token:
        try:
            kimlik.refresh(Request())
        except RefreshError:
            kimlik = None  # izin geri alinmis ya da suresi dolmus
    if not kimlik or not kimlik.valid:
        if not etkilesimli:
            raise GirisGerekli("YouTube izni yok ya da suresi doldu: python -m studyo.youtube --kur")
        if not os.path.exists(SIRLAR):
            raise SystemExit("client_secret.json yok (%s). README > 'YouTube'a otomatik yukleme'." % SIRLAR)
        from google_auth_oauthlib.flow import InstalledAppFlow
        kimlik = InstalledAppFlow.from_client_secrets_file(SIRLAR, KAPSAM).run_local_server(
            port=0, prompt="consent", authorization_prompt_message="Tarayicida kanal hesabinla giris yap...")
    with open(JETON, "w", encoding="utf-8") as f:
        f.write(kimlik.to_json())
    return kimlik


def _servis(etkilesimli=False):
    from googleapiclient.discovery import build
    return build("youtube", "v3", credentials=_kimlik(etkilesimli), cache_discovery=False)


def kanal(servis=None):
    servis = servis or _servis()
    r = servis.channels().list(part="snippet", mine=True).execute()
    ogeler = r.get("items") or []
    return (ogeler[0]["snippet"]["title"], ogeler[0]["id"]) if ogeler else (None, None)


def yukle(dosya, baslik, aciklama, etiketler, gizlilik="private", kapak=None, gunluk=print):
    """Videoyu yukler, kapak varsa ekler; https://youtu.be/... dondurur."""
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    servis = _servis()
    istek = servis.videos().insert(
        part="snippet,status",
        body={
            "snippet": {"title": baslik[:100], "description": aciklama[:5000], "tags": etiketler,
                        "categoryId": KATEGORI_OYUN, "defaultLanguage": "tr", "defaultAudioLanguage": "en"},
            "status": {"privacyStatus": gizlilik, "selfDeclaredMadeForKids": False,
                       "containsSyntheticMedia": False},
        },
        media_body=MediaFileUpload(dosya, chunksize=16 * 1024 * 1024, resumable=True),
    )
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
    return "https://youtu.be/" + kimlik


def main(argv=None):
    ap = argparse.ArgumentParser(prog="studyo.youtube", description="YouTube yukleme izni")
    ap.add_argument("--kur", action="store_true", help="tarayicida kanal hesabiyla izin ver (bir kez)")
    ap.add_argument("--kontrol", action="store_true", help="izin gecerli mi, hangi kanal")
    arg = ap.parse_args(argv)
    if arg.kur:
        if os.path.exists(JETON):
            os.remove(JETON)  # baska kanal secilebilsin
        servis = _servis(etkilesimli=True)
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
    print("     ayarlar.json'da \"youtube_yukle\": true olunca videolar buraya %s yuklenir." % "gizli")


if __name__ == "__main__":
    main()
