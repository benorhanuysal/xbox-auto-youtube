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
"yorum" lists when the channel owner talks on the microphone inside the scene ([start, end] seconds from scene
start): live Turkish voice commentary and reactions. This commentary is what makes the channel original rather
than reused game footage, so prefer scenes with commentary, and never cut a commentary range in half.
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
4. English metadata for international viewers for every video: "baslik_en" (max 90 characters, same angle,
   natural English, no hashtags) and "aciklama_en" (2-4 short sentences).
5. For every part of "uzun" give "bolum": a short Turkish chapter title (max 40 characters) for the YouTube chapter
   list, e.g. "Lester'dan şüpheli teklif", "Motordan uçuş". Consecutive parts of the same moment share the same title.

YouTube monetization policy (the whole channel is reviewed; follow these strictly):
- Every video must feel individually made, not mass-produced from a template. Vary title structure and opening
  across videos; do not reuse the formula of the channel's recent titles below. The same pattern on every video is
  a policy risk even if it performs well.
- No profanity, slurs or sexual words in titles, descriptions or on-screen Shorts titles. Never misleading: only
  promise what actually happens in the clip. No shock bait.
- Describe it as the creator's own gameplay; the added value is the live Turkish translation and the editing.
Recent titles on this channel (do not copy their structure):
{son_basliklar}

For each chosen candidate give "id" and optionally tighter "bas"/"son" (must stay inside the candidate's range).
{serbest}Reply with JSON only, no other text:
{{"uzun": {{"parcalar": [{{"id": 1, "bas": 10.0, "son": 40.0, "bolum": "..."}}{serbest_ornek}], "baslik": "", "aciklama": "",
  "baslik_en": "", "aciklama_en": "", "etiketler": []}},
 "shorts": [{{"parcalar": [{{"id": 3}}], "baslik": "", "aciklama": "", "baslik_en": "", "aciklama_en": "", "etiketler": []}}]}}
{ogrenme}
Candidate scenes:
{adaylar}"""

_OGRENME_BOLUMU = """
Lessons from this channel's own performance data so far. Apply them to WHICH moments you pick and what the
title is about; keep the title wording and structure varied (policy rule above):
{dersler}
"""

_META_KOMUT = """You write YouTube metadata for the channel "{kanal}" ({oyun} gameplay with Turkish subtitles).
The videos are already edited. Long video parts (seconds in the recording) with the dialogue inside each part:
{parcalar}
Current Turkish titles and descriptions:
{videolar}

Return JSON only, no other text:
{{"bolumler": ["<short Turkish chapter title per long-video part, max 40 characters, same order>"],
 "videolar": [{{"baslik_en": "<natural English title, max 90 characters, same angle, no hashtags>",
               "aciklama_en": "<2-4 short English sentences>"}}]}}
"videolar" must follow the same order as the titles above."""

_KARE_BOLUMU = """
Frames: for some scenes there is an image file in the current directory named sahne_<id>.jpg (for example
sahne_7.jpg) showing three moments of that scene side by side (start, middle, end). Read the images of the
scenes you are considering with the Read tool before deciding, and use them to judge what happens on screen:
chases, crashes, explosions, scenery, funny situations. Skip scenes that only show menus, maps, loading or black screens.
Scenes with frames: {idler}
"""

_OZET_BOLUMU = """
Overview of the WHOLE recording: {sayfalar} in the current directory. Each is a grid of small frames taken every
{aralik} seconds, read left to right, top to bottom; the yellow number on each frame is its time in seconds.
Read ALL overview sheets with the Read tool before deciding. The candidate list above only knows about loud audio
and dialogue, so it misses silent visual moments. Look for them yourself: falls and crashes (character thrown off a
bike, car flipped, ragdoll), funny physics and fails, police chases and arrests, explosions, stunts, near misses,
weird or absurd situations, and beautiful shots (sunset drives, city lights). Frames that show the Windows desktop,
a code editor, a browser, menus, loading screens or black are NOT gameplay: never use those times.
"""
_SERBEST = """You may also add moments you found in the overview sheets as parts WITHOUT an "id": {"bas": 412, "son": 436}
(seconds in the recording). The action happens somewhere between two frames, so start ~8 s before the first frame
that shows it and end ~4 s after the last; 6-40 s per part. Funny or crazy visual moments make great Shorts.
"""
EN_FAZLA_KARE = 30
OZET_ARALIK = 10       # sn: ozet sayfasindaki kare araligi
SERBEST_EN_KISA, SERBEST_EN_UZUN = 3.0, 60.0


def _baslik(metin, sinir):
    # "#shorts" vb. etiketler basliktan atilir; Shorts etiketi yuklerken tek sefer eklenir
    return re.sub(r"\s*#\w+", "", str(metin or "")).strip()[:sinir]


def _parcalari_dogrula(parcalar, adaylar_sozluk, en_fazla_sn=None, sure_sn=None, adlar=None):
    """adlar listesi verilirse kabul edilen her parcanin "bolum" adi (yoksa "") ayni sirayla eklenir."""
    sonuc, toplam = [], 0.0
    for p in parcalar or []:
        if not isinstance(p, dict):
            continue
        try:
            a = adaylar_sozluk.get(int(p.get("id")))
        except (TypeError, ValueError):
            a = None
        if a:
            bas = min(max(float(p.get("bas", a["bas"])), a["bas"]), a["son"])
            son = max(min(float(p.get("son", a["son"])), a["son"]), bas)
        elif sure_sn and "bas" in p and "son" in p:
            # Ozet sayfalarindan bulunan serbest an (aday listesinde yok)
            try:
                bas, son = max(0.0, float(p["bas"])), min(float(sure_sn), float(p["son"]))
            except (TypeError, ValueError):
                continue
            if son - bas < SERBEST_EN_KISA:
                continue
            son = min(son, bas + SERBEST_EN_UZUN)
        else:
            continue
        if son - bas < 1.5:
            continue
        if en_fazla_sn is not None:
            if toplam >= en_fazla_sn:
                break
            son = min(son, bas + en_fazla_sn - toplam)
        sonuc.append([round(bas, 2), round(son, 2)])
        if adlar is not None:
            adlar.append(str(p.get("bolum") or "").strip()[:60])
        toplam += son - bas
    return sonuc


def _ogrenme_metni():
    """rapor.py'nin yazdigi dersler (kanal performansindan); yoksa bos."""
    yol = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ogrenme.json")
    try:
        with open(yol, encoding="utf-8") as f:
            dersler = json.load(f).get("dersler") or []
    except (OSError, ValueError):
        return ""
    dersler = [str(d).strip() for d in dersler if str(d).strip()][:12]
    return _OGRENME_BOLUMU.format(dersler="\n".join("- " + d for d in dersler)) if dersler else ""


def _son_basliklar(sayi=12):
    """youtube_durum.json'daki son yuklenen basliklar: Claude ayni kalibi tekrarlamasin (ozgun olmayan icerik riski)."""
    from . import youtube
    basliklar = [v.get("baslik", "") for v in youtube.durum_oku()["videolar"] if v.get("baslik")][-sayi:]
    return "\n".join("- " + b for b in basliklar) if basliklar else "(none yet)"


def _en_alanlari(kaynak, hedef):
    if kaynak.get("baslik_en"):
        hedef["baslik_en"] = _baslik(kaynak.get("baslik_en"), 100)
        hedef["aciklama_en"] = str(kaynak.get("aciklama_en") or "")
    return hedef


def meta_tamamla(plan, satirlar, ayar, klasor, gunluk=print):
    """Eski planlarda (bolum adlari / Ingilizce baslik yok) eksikleri Claude'a tamamlat. Plan yerinde guncellenir."""
    videolar = [plan["uzun"]] + list(plan["shorts"])
    eksik_bolum = plan["uzun"]["parcalar"] and not any(plan["uzun"].get("bolumler") or [])
    eksik_en = any(not v.get("baslik_en") for v in videolar)
    if not (eksik_bolum or eksik_en) or not claude.var_mi():
        return plan
    parcalar = []
    for bas, son in plan["uzun"]["parcalar"]:
        diyalog = [s.en for s in satirlar if s.bas < son and s.son > bas][:8]
        parcalar.append({"bas": bas, "son": son, "diyalog": diyalog})
    komut = _META_KOMUT.format(kanal=ayar["kanal"], oyun=ayar["oyun"],
                               parcalar=json.dumps(parcalar, ensure_ascii=False),
                               videolar=json.dumps([{"baslik": v["baslik"], "aciklama": v.get("aciklama", "")}
                                                    for v in videolar], ensure_ascii=False))
    gunluk("  Claude eksik bilgileri tamamliyor (bolumler, Ingilizce baslik)...")
    ham = claude.iste(komut, klasor, ayar.get("claude_model"), gunluk) or {}
    bolumler = ham.get("bolumler") if isinstance(ham, dict) else None
    if eksik_bolum and isinstance(bolumler, list) and len(bolumler) == len(plan["uzun"]["parcalar"]):
        plan["uzun"]["bolumler"] = [str(b).strip()[:60] for b in bolumler]
    for v, m in zip(videolar, (ham.get("videolar") or []) if isinstance(ham, dict) else []):
        if isinstance(m, dict) and not v.get("baslik_en"):
            _en_alanlari(m, v)
    return plan


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


def _komut(adaylar, ayar, kare_idleri, ozetler=()):
    kareler = _KARE_BOLUMU.format(idler=", ".join(map(str, kare_idleri))) if kare_idleri else ""
    if ozetler:
        kareler += _OZET_BOLUMU.format(sayfalar=", ".join(ozetler), aralik=OZET_ARALIK)
    return _KOMUT.format(
        kanal=ayar["kanal"], oyun=ayar["oyun"], dk_min=ayar["uzun_video_dk"][0], dk_max=ayar["uzun_video_dk"][1],
        shorts=ayar["shorts_sayisi"], short_sn=ayar["shorts_en_uzun_sn"],
        kareler=kareler,
        serbest=_SERBEST if ozetler else "",
        serbest_ornek=', {"bas": 412, "son": 436, "bolum": "..."}' if ozetler else "",
        ogrenme=_ogrenme_metni(),
        son_basliklar=_son_basliklar(),
        adaylar=json.dumps([{k: a[k] for k in ("id", "bas", "son", "heyecan", "diyalog", "isaretli", "yorum") if k in a}
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


def plan(adaylar, ayar, kayit_yolu, cikti_klasoru, gunluk=print, planlayicilar=None, sure_sn=None):
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
            ozetler = []
            if ayar["claude_kare"] and sure_sn:
                try:
                    ozetler = kurgu.ozet_sayfalari(kayit_yolu, sure_sn, kare_klasoru, OZET_ARALIK)
                except Exception as e:
                    gunluk("  ozet sayfalari alinamadi: %s" % str(e)[:120])
            gunluk("  Claude planliyor (%d sahne karesi, %d ozet sayfasi)..." % (len(idler), len(ozetler)))
            ham = claude.iste(_komut(adaylar, ayar, idler, ozetler), kare_klasoru, ayar.get("claude_model"), gunluk)
        elif ad == "gemini":
            ham = gemini.iste(_komut(adaylar, ayar, []), ayar, gunluk)
    if not ham:
        gunluk("  Yapay zeka plani alinamadi: puana gore basit plan")
        ham = _yedek_plan(adaylar, ayar)

    uzun = ham.get("uzun") or {}
    adlar = []
    parcalar = _parcalari_dogrula(uzun.get("parcalar"), adaylar_sozluk, sure_sn=sure_sn, adlar=adlar)
    # Isaretli sahne plana girmediyse (yapay zeka atladiysa) yine de uzun videoya ekle
    for a in adaylar:
        if a.get("isaretli") and not any(b < a["son"] and s > a["bas"] for b, s in parcalar):
            gunluk("  Isaretli sahne plana eklendi: %.0f-%.0f sn" % (a["bas"], a["son"]))
            parcalar.append([a["bas"], a["son"]])
            adlar.append("İşaretli an")
    sirali = sorted(zip(parcalar, adlar), key=lambda x: x[0])
    sonuc = {
        "uzun": _en_alanlari(uzun, {
            "parcalar": [p for p, _ in sirali],
            "bolumler": [a for _, a in sirali],
            "baslik": _baslik(uzun.get("baslik"), 100),
            "aciklama": str(uzun.get("aciklama", "")),
            "etiketler": [str(e) for e in uzun.get("etiketler", [])][:20],
        }),
        "shorts": [],
    }
    for s in (ham.get("shorts") or [])[: ayar["shorts_sayisi"]]:
        parcalar = _parcalari_dogrula(s.get("parcalar"), adaylar_sozluk, ayar["shorts_en_uzun_sn"], sure_sn)
        if parcalar:
            sonuc["shorts"].append(_en_alanlari(s, {
                "parcalar": parcalar,
                "baslik": _baslik(s.get("baslik"), 90),
                "aciklama": str(s.get("aciklama", "")),
                "etiketler": [str(e) for e in s.get("etiketler", [])][:15],
            }))
    return sonuc
