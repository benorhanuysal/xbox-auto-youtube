"""Ayarlar: ayarlar.json (gitignore'da) varsayilanlarin ustune yazilir."""
import json
import os

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AYAR_DOSYASI = os.path.join(KOK, "ayarlar.json")

VARSAYILAN = {
    # OBS'in kayit klasoru. Bos ise Windows "Videolar" klasoru.
    "kayit_klasoru": "",
    # LunaTranslator'in userconfig klasoru: Turkce altyazi gunlugu ve Gemini anahtari buradan okunur.
    "luna_userconfig": "",
    # Kurgu planini kim yapsin, sirayla denenir. "claude": bilgisayardaki Claude Code (abonelikle, ek ucret yok);
    # "gemini": Gemini API (ucretsiz kota). Hicbiri olmazsa puana gore basit plan.
    "planlayicilar": ["claude", "gemini"],
    # Bos: Claude Code'un varsayilan modeli. Ornek: "sonnet", "opus"
    "claude_model": "",
    # Claude'a sahnelerden kare seritleri de goster (goruntuye bakarak secsin)
    "claude_kare": True,
    # Bos ise Luna'daki Gemini anahtari kullanilir (ayni anahtari iki yere yazmayin).
    "gemini_anahtari": "",
    # Sirayla denenir; ilki mesgulse (503) sonraki.
    "gemini_modelleri": ["gemini-flash-latest", "gemini-flash-lite-latest"],
    "oyun": "GTA V",
    "kanal": "Night Drive Club",
    "kanal_linki": "https://github.com/benorhanuysal/xbox-samsung-subtitles-tv",
    # Uzun videonun hedef suresi (dakika, en az / en cok)
    "uzun_video_dk": [8, 15],
    "shorts_sayisi": 3,
    "shorts_en_uzun_sn": 58,
    # Luna ceviriyi altyazi ekrana geldikten yaklasik bu kadar sonra yazar (OCR + ceviri).
    # Kayitta olculdu: Ingilizce satir ekrana geldikten 1,5-2 sn sonra gunlukte.
    "altyazi_gecikme_sn": 2.0,
    # Turkce altyaziyi videonun uzerine yaz
    "altyazi_gom": True,
    # Videoya girecek altyazilari Claude ile kisalt/duzelt (okuma hizina sigsin, OCR hatalari gitsin)
    "altyazi_duzelt": True,
    # YouTube API ile otomatik yukleme (kurulum: python -m studyo.youtube --kur). 2 Kasim 2026'dan beri
    # denetimsiz projelerin videolari gizliye kilitlenmiyor.
    "youtube_yukle": False,
    # private: gizli yuklenir, Studio'da kontrol edip sen yayinlarsin | unlisted: liste disi | public: hemen yayinda
    "youtube_gizlilik": "private",
    # Ingilizce baslik/aciklama (izleyicinin dili Ingilizceyse YouTube bunlari gosterir)
    "youtube_ingilizce": True,
    # Uzun videonun aciklamasina bolumler (00:00 ...) -> YouTube'da bolum cubugu
    "youtube_bolumler": True,
    # Oynatma listeleri ({oyun} oyun adiyla degisir); yoksa olusturulur. Bos "" = listeye ekleme
    "youtube_listeler": {"uzun": "{oyun} Türkçe Altyazılı Oynanış", "shorts": "{oyun} Shorts | Türkçe Altyazılı"},
    "youtube_liste_aciklamasi": "{oyun} oynanışı, yapay zekâ ile canlı çevrilmiş Türkçe altyazılarla. {kanal}",
    # Ayri altyazi parcalari (her biri 400 kota birimi; gunluk 10.000). Shorts'ta Turkce zaten videonun ustunde.
    "youtube_altyazi_dilleri": {"uzun": ["tr", "en"], "shorts": ["en"]},
    # Zamanlanmis yayin: true ise uzun video ertesi gun youtube_uzun_saat'te, Shorts'lar sonraki gunlerde
    # birer birer youtube_shorts_saat'te kendiliginden yayina girer (saatler bilgisayarin saat diliminde).
    "youtube_zamanla": False,
    "youtube_uzun_saat": "20:00",
    "youtube_shorts_saat": "18:00",
    # Performans raporu kac gunde bir (bekci kendisi calistirir; elle: python -m studyo.rapor)
    "rapor_gun": 7,
    # Yeni yorum kontrolu kac saatte bir (bildirim gelir; cevaplamak icin YORUMLAR.bat)
    "yorum_kontrol_saat": 3,
    "cikti_klasoru": "cikti",
    # ---- Bekci (python -m studyo.izle / IZLE.pyw)
    # Xbox uzaktan oynatma baslayinca OBS kaydini baslat, kapaninca durdur
    "oto_kayit": True,
    # Xbox sahnesindeki kayit durunca kurguyu kendiliginden baslat
    "oto_kurgu": True,
    # Uzaktan oynatma sesi bu kadar sn kesintisiz akinca kayit baslar; bu kadar sn kesilince durur
    "oto_kayit_basla_sn": 15,
    "oto_kayit_dur_sn": 60,
    # Bundan kisa kayitlar kurgulanmaz (yanlislikla acilan uzaktan oynatma vb.)
    "en_kisa_kayit_dk": 3,
    # Ani isaretleme: klavye tusu (F1-F24) ve kumandada iki analog cubuga birlikte basma
    "isaret_tusu": "F9",
    "kumanda_isaret": True,
    # Mikrofon (Windows varsayilan kayit aygiti) kayda girsin: yorum videoya ozgun deger katar,
    # kurgu konustugun anlari ayri ses kanalindan bulup one cikarir
    "mikrofon_kaydi": True,
    # Uzaktan oynatma baslayinca LunaTranslator kapaliysa ac (TV altyazisi ve yayin katmani ona bagli)
    "luna_oto_baslat": True,
    # ---- Kick canli yayini (python -m studyo.yayin --kur / YAYIN_KUR.bat)
    # Uzaktan oynatma acikken bu tus yayini acar/kapatir; oynatma kapaninca yayin kendiliginden biter
    "yayin_tusu": "F10",
    "yayin_bit_hizi": 6000,   # kbps; Kick en fazla 8000, 1080p60 icin 6000 yeterli
    # Yayindayken uzaktan oynatma bu kadar sn kesilirse ekran gizlenir (masaustu izleyiciye gorunmesin)
    "yayin_ekran_gizle_sn": 4,
    "obs_exe": r"C:\Program Files\obs-studio\bin\64bit\obs64.exe",
}


def yukle():
    ayar = dict(VARSAYILAN)
    if os.path.exists(AYAR_DOSYASI):
        with open(AYAR_DOSYASI, encoding="utf-8-sig") as f:
            ayar.update(json.load(f))
    if not ayar["kayit_klasoru"]:
        ayar["kayit_klasoru"] = os.path.join(os.path.expanduser("~"), "Videos")
    if not os.path.isabs(ayar["cikti_klasoru"]):
        ayar["cikti_klasoru"] = os.path.join(KOK, ayar["cikti_klasoru"])
    return ayar


def gemini_anahtari(ayar):
    if ayar.get("gemini_anahtari"):
        return ayar["gemini_anahtari"].strip()
    yol = os.path.join(ayar.get("luna_userconfig") or "", "translatorsetting.json")
    try:
        with open(yol, encoding="utf-8") as f:
            a = json.load(f)["chatgpt-3rd-party"]["args"]
        return a.get("SECRET_KEY", "").split("|")[0].strip()
    except Exception:
        return ""
