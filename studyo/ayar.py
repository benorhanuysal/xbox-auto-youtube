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
    # Luna ceviriyi altyazi ekrana geldikten yaklasik bu kadar sonra yazar
    "altyazi_gecikme_sn": 1.0,
    # Turkce altyaziyi videonun uzerine yaz
    "altyazi_gom": True,
    # YouTube API ile yukleme. Google denetiminden gecmemis projelerde videolar KALICI olarak gizli kalir;
    # denetim onayi gelmeden acmayin, videolari Studio'dan yukleyin.
    "youtube_yukle": False,
    "cikti_klasoru": "cikti",
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
