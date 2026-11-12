"""YouTube Data API ile GIZLI yukleme.

UYARI: Google'in "API denetimi"nden (audit) gecmemis projelerden yuklenen videolar KALICI olarak gizli kalir,
itiraz edilemez. Denetim onayi gelene kadar ayarlar.json'da "youtube_yukle": false kalsin ve videolari
YouTube Studio'dan yukleyin (yukleme_bilgisi.txt'deki baslik/aciklamayi kopyalayin).

Gerekenler: Google Cloud'da proje + YouTube Data API v3 + OAuth istemcisi (Masaustu uygulamasi);
indirilen JSON bu klasore client_secret.json olarak konur. Ilk calismada tarayicida kanal hesabiyla izin verilir."""
import os

from .ayar import KOK

KAPSAM = ["https://www.googleapis.com/auth/youtube.upload"]
SIRLAR = os.path.join(KOK, "client_secret.json")
JETON = os.path.join(KOK, "token.json")


def _servis():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    kimlik = Credentials.from_authorized_user_file(JETON, KAPSAM) if os.path.exists(JETON) else None
    if not kimlik or not kimlik.valid:
        if kimlik and kimlik.expired and kimlik.refresh_token:
            kimlik.refresh(Request())
        else:
            if not os.path.exists(SIRLAR):
                raise SystemExit("client_secret.json yok: README'deki 'YouTube API' adimlarina bakin.")
            kimlik = InstalledAppFlow.from_client_secrets_file(SIRLAR, KAPSAM).run_local_server(port=0)
        with open(JETON, "w", encoding="utf-8") as f:
            f.write(kimlik.to_json())
    return build("youtube", "v3", credentials=kimlik)


def yukle(dosya, baslik, aciklama, etiketler, gunluk=print):
    from googleapiclient.http import MediaFileUpload

    istek = _servis().videos().insert(
        part="snippet,status",
        body={
            "snippet": {"title": baslik[:100], "description": aciklama[:5000], "tags": etiketler,
                        "categoryId": "20", "defaultLanguage": "tr", "defaultAudioLanguage": "en"},
            "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False},
        },
        media_body=MediaFileUpload(dosya, chunksize=16 * 1024 * 1024, resumable=True),
    )
    cevap = None
    while cevap is None:
        durum, cevap = istek.next_chunk()
        if durum:
            gunluk("    yukleniyor %%%d" % int(durum.progress() * 100))
    return "https://youtu.be/" + cevap["id"]
