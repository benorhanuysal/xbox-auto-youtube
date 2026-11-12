"""Kurgu plani: Gemini aday sahnelerden uzun video ve Shorts secer, baslik/aciklama/etiket yazar.
Gemini'ye yalnizca metin gider (sahne zamanlari, ses heyecani, diyaloglar): ucuz ve hizli.
Gemini'ye ulasilamazsa puana gore basit bir plan yapilir."""
import json
import re
import time

import requests

_KOMUT = """You are the video editor of the YouTube channel "{kanal}" (Turkish audience, game: {oyun}).
The channel posts gameplay with live AI-translated Turkish subtitles: story missions, heists, free-roam chaos, night drives.

Below are candidate scenes from one recording session. Each has: id, bas/son (seconds in the recording),
heyecan (how much louder than usual the audio gets, in loudness units: gunfights, crashes, explosions, shouting),
and diyalog (subtitles inside the scene: t = seconds from scene start, en = English, tr = Turkish).

Make an editing plan:
1. "uzun": a {dk_min}-{dk_max} minute YouTube video. Pick the scenes that tell the session's story and the best
   action, keep chronological order. Never cut a dialogue line in half. If the session is too short, use what fits.
2. "shorts": up to {shorts} vertical Shorts, each at most {short_sn} seconds in total, each one self-contained
   and gripping in the first 2 seconds (a funny line, a crash, a twist). Prefer different moments than each other.
3. For every video write Turkish metadata for a young Turkish gaming audience: "baslik" (catchy, max 90 characters,
   no clickbait lies, include "{oyun}"), "aciklama" (2-4 short sentences), "etiketler" (8-15 tags, Turkish and English).

For each chosen scene give "id" and optionally tighter "bas"/"son" (must stay inside the candidate's range).
Reply with JSON only:
{{"uzun": {{"parcalar": [{{"id": 1, "bas": 10.0, "son": 40.0}}], "baslik": "", "aciklama": "", "etiketler": []}},
 "shorts": [{{"parcalar": [{{"id": 3}}], "baslik": "", "aciklama": "", "etiketler": []}}]}}

Candidate scenes:
{adaylar}"""


def _gemini(model, anahtar, metin, zaman_asimi):
    r = requests.post(
        "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent" % model,
        headers={"x-goog-api-key": anahtar},
        json={"contents": [{"role": "user", "parts": [{"text": metin}]}],
              "generationConfig": {"temperature": 0.4, "responseMimeType": "application/json"}},
        timeout=zaman_asimi,
    )
    if r.status_code != 200:
        raise RuntimeError("HTTP %d" % r.status_code)
    cevap = r.json()
    return json.loads("".join(p.get("text", "") for p in cevap["candidates"][0]["content"]["parts"]))


def _baslik(metin, sinir):
    # "#shorts" vb. etiketler basliktan atilir; Shorts etiketi yuklerken tek sefer eklenir
    metin = re.sub(r"\s*#\w+", "", str(metin or "")).strip()
    return metin[:sinir]


def _parcalari_dogrula(parcalar, adaylar_sozluk, en_fazla_sn=None):
    sonuc, toplam = [], 0.0
    for p in parcalar or []:
        a = adaylar_sozluk.get(p.get("id"))
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


def plan(adaylar, ayar, anahtar, gunluk=print):
    adaylar_sozluk = {a["id"]: a for a in adaylar}
    ham = None
    if anahtar and adaylar:
        metin = _KOMUT.format(
            kanal=ayar["kanal"], oyun=ayar["oyun"], dk_min=ayar["uzun_video_dk"][0], dk_max=ayar["uzun_video_dk"][1],
            shorts=ayar["shorts_sayisi"], short_sn=ayar["shorts_en_uzun_sn"],
            adaylar=json.dumps([{k: a[k] for k in ("id", "bas", "son", "heyecan", "diyalog")} for a in adaylar],
                               ensure_ascii=False),
        )
        modeller = ayar["gemini_modelleri"]
        for sira, model in enumerate(modeller):
            son_model = sira == len(modeller) - 1
            # Guclu model sik sik mesgul (503 / cevapsiz): bir kez dene, sonrakine gec.
            # Son model: acele yok (video isi), artan beklemeyle birkac kez dene.
            bekleme = [10, 30, 60] if son_model else []
            for deneme in range(len(bekleme) + 1):
                try:
                    ham = _gemini(model, anahtar, metin, 120 if son_model else 60)
                    gunluk("  Gemini plani: %s" % model)
                    break
                except Exception as e:
                    gunluk("  %s olmadi (%s)" % (model, e))
                    if deneme < len(bekleme):
                        time.sleep(bekleme[deneme])
            if ham:
                break
    if not ham:
        gunluk("  Gemini yok/ulasilamadi: puana gore basit plan")
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
