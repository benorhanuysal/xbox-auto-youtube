"""Kurgu plani: yapay zeka aday sahnelerden uzun video ve Shorts secer, baslik/aciklama/etiket yazar.
Sira ayarlar.json'daki "planlayicilar" listesidir (varsayilan: Claude, sonra Gemini).
Hicbiri olmazsa puana gore basit bir plan yapilir; video her durumda cikar."""
import json
import os
import re

from . import claude, gemini, kurgu

_KOMUT = """You are the video editor of the YouTube channel "{kanal}" (Turkish audience, game: {oyun}).
The channel posts gameplay with live AI-translated Turkish subtitles: story missions, heists, free-roam chaos, night drives.

Below are candidate scenes from one recording session. Each has: id, bas/son (seconds in the recording),
heyecan (how much louder than usual the audio gets, in loudness units: gunfights, crashes, explosions, shouting),
and diyalog (subtitles inside the scene: t = seconds from scene start, en = English, tr = Turkish).
Scenes with "isaretli": true were marked by the player with a "this was great" button pressed right after the
moment happened, so the highlight is in the last ~25 seconds of that scene. Always put every marked scene in
"uzun" and use the marked moments first when choosing Shorts.
{kareler}
Make an editing plan:
1. "uzun": a {dk_min}-{dk_max} minute YouTube video. Pick the scenes that tell the session's story and the best
   action, keep chronological order. Never cut a dialogue line in half. Drop dead time (menus, loading, walking
   with nothing happening). If the session is too short, use what fits.
2. "shorts": up to {shorts} vertical Shorts, each at most {short_sn} seconds in total (15-35 s is ideal).
   Every Short must work on its own for a viewer who has never seen the game:
   - Hook in the first 2 seconds: start right on the funny line, the crash, the twist. No build-up.
   - One clear idea per Short: one joke, one fail, one wild moment. A twist ending beats a long sequence.
   - End on the punchline or the peak moment; no dead air after it.
   - Use different moments for different Shorts.
3. Turkish metadata for a young Turkish gaming audience for every video: "baslik" (max 90 characters, include
   "{oyun}", an ironic or surprising angle beats a plain description, no lies, no hashtags), "aciklama"
   (2-4 short sentences), "etiketler" (8-15 tags, Turkish and English).

For each chosen scene give "id" and optionally tighter "bas"/"son" (must stay inside the candidate's range).
Reply with JSON only, no other text:
{{"uzun": {{"parcalar": [{{"id": 1, "bas": 10.0, "son": 40.0}}], "baslik": "", "aciklama": "", "etiketler": []}},
 "shorts": [{{"parcalar": [{{"id": 3}}], "baslik": "", "aciklama": "", "etiketler": []}}]}}

Candidate scenes:
{adaylar}"""

_KARE_BOLUMU = """
Frames: for some scenes there is an image file in the current directory named sahne_<id>.jpg (for example
sahne_7.jpg) showing three moments of that scene side by side (start, middle, end). Read the images of the
scenes you are considering with the Read tool before deciding, and use them to judge what happens on screen:
chases, crashes, explosions, scenery, funny situations. Skip scenes that only show menus, maps, loading or black screens.
Scenes with frames: {idler}
"""
EN_FAZLA_KARE = 30


def _baslik(metin, sinir):
    # "#shorts" vb. etiketler basliktan atilir; Shorts etiketi yuklerken tek sefer eklenir
    return re.sub(r"\s*#\w+", "", str(metin or "")).strip()[:sinir]


def _parcalari_dogrula(parcalar, adaylar_sozluk, en_fazla_sn=None):
    sonuc, toplam = [], 0.0
    for p in parcalar or []:
        try:
            a = adaylar_sozluk.get(int(p.get("id")))
        except (TypeError, ValueError):
            continue
        if not a:
            continue
        bas = min(max(float(p.get("bas", a["bas"])), a["bas"]), a["son"])
        son = max(min(float(p.get("son", a["son"])), a["son"]), bas)
        if son - bas < 1.5:
            continue
        if en_fazla_sn is not None:
            if toplam >= en_fazla_sn:
                break
            son = min(son, bas + en_fazla_sn - toplam)
        sonuc.append([round(bas, 2), round(son, 2)])
        toplam += son - bas
    return sonuc


def _yedek_plan(adaylar, ayar):
    hedef = ayar["uzun_video_dk"][1] * 60
    secilen, toplam = [], 0.0
    for a in sorted(adaylar, key=lambda a: -a["puan"]):
        if toplam >= hedef:
            break
        secilen.append(a)
        toplam += a["son"] - a["bas"]
    uzun = [{"id": a["id"]} for a in sorted(secilen, key=lambda a: a["bas"])]
    en_heyecanli = sorted(adaylar, key=lambda a: -a["heyecan"])[: ayar["shorts_sayisi"]]
    oyun = ayar["oyun"]
    return {
        "uzun": {"parcalar": uzun, "baslik": "%s Türkçe Altyazılı | %s" % (oyun, ayar["kanal"]),
                 "aciklama": "%s oynanışı, canlı Türkçe altyazılı." % oyun, "etiketler": [oyun, "türkçe altyazılı", "gameplay"]},
        "shorts": [{"parcalar": [{"id": a["id"]}], "baslik": "%s anı %d" % (oyun, i + 1),
                    "aciklama": "", "etiketler": [oyun, "shorts"]} for i, a in enumerate(en_heyecanli)],
    }


def _komut(adaylar, ayar, kare_idleri):
    return _KOMUT.format(
        kanal=ayar["kanal"], oyun=ayar["oyun"], dk_min=ayar["uzun_video_dk"][0], dk_max=ayar["uzun_video_dk"][1],
        shorts=ayar["shorts_sayisi"], short_sn=ayar["shorts_en_uzun_sn"],
        kareler=_KARE_BOLUMU.format(idler=", ".join(map(str, kare_idleri))) if kare_idleri else "",
        adaylar=json.dumps([{k: a[k] for k in ("id", "bas", "son", "heyecan", "diyalog", "isaretli") if k in a}
                            for a in adaylar], ensure_ascii=False),
    )


def _kareleri_hazirla(kayit_yolu, adaylar, klasor, gunluk):
    """En yuksek puanli sahnelerden kare seritleri (Claude goruntuye de bakabilsin)."""
    secilen = sorted(adaylar, key=lambda a: -a["puan"])[:EN_FAZLA_KARE]
    os.makedirs(klasor, exist_ok=True)
    idler = []
    for a in secilen:
        try:
            kurgu.kare_seridi(kayit_yolu, a["bas"], a["son"], os.path.join(klasor, "sahne_%d.jpg" % a["id"]))
            idler.append(a["id"])
        except Exception as e:
            gunluk("  kare alinamadi (sahne %d): %s" % (a["id"], str(e)[:80]))
    return sorted(idler)


def plan(adaylar, ayar, kayit_yolu, cikti_klasoru, gunluk=print, planlayicilar=None):
    adaylar_sozluk = {a["id"]: a for a in adaylar}
    ham = None
    for ad in (planlayicilar if planlayicilar is not None else ayar["planlayicilar"]):
        if ham or not adaylar:
            break
        if ad == "claude":
            if not claude.var_mi():
                gunluk("  Claude Code bulunamadi, atlaniyor")
                continue
            kare_klasoru = os.path.join(cikti_klasoru, "kareler")
            idler = _kareleri_hazirla(kayit_yolu, adaylar, kare_klasoru, gunluk) if ayar["claude_kare"] else []
            gunluk("  Claude planliyor (%d sahnenin karesiyle)..." % len(idler))
            ham = claude.iste(_komut(adaylar, ayar, idler), kare_klasoru, ayar.get("claude_model"), gunluk)
        elif ad == "gemini":
            ham = gemini.iste(_komut(adaylar, ayar, []), ayar, gunluk)
    if not ham:
        gunluk("  Yapay zeka plani alinamadi: puana gore basit plan")
        ham = _yedek_plan(adaylar, ayar)

    uzun = ham.get("uzun") or {}
    sonuc = {
        "uzun": {
            "parcalar": sorted(_parcalari_dogrula(uzun.get("parcalar"), adaylar_sozluk)),
            "baslik": _baslik(uzun.get("baslik"), 100),
            "aciklama": str(uzun.get("aciklama", "")),
            "etiketler": [str(e) for e in uzun.get("etiketler", [])][:20],
        },
        "shorts": [],
    }
    # Isaretli sahne plana girmediyse (yapay zeka atladiysa) yine de uzun videoya ekle
    parcalar = sonuc["uzun"]["parcalar"]
    for a in adaylar:
        if a.get("isaretli") and not any(b < a["son"] and s > a["bas"] for b, s in parcalar):
            gunluk("  Isaretli sahne plana eklendi: %.0f-%.0f sn" % (a["bas"], a["son"]))
            parcalar.append([a["bas"], a["son"]])
    parcalar.sort()
    for s in (ham.get("shorts") or [])[: ayar["shorts_sayisi"]]:
        parcalar = _parcalari_dogrula(s.get("parcalar"), adaylar_sozluk, ayar["shorts_en_uzun_sn"])
        if parcalar:
            sonuc["shorts"].append({
                "parcalar": parcalar,
                "baslik": _baslik(s.get("baslik"), 90),
                "aciklama": str(s.get("aciklama", "")),
                "etiketler": [str(e) for e in s.get("etiketler", [])][:15],
            })
    return sonuc
