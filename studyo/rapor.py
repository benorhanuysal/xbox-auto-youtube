"""Kanal performans raporu + Claude'un ogrenmesi.
Data API: tum videolarin izlenme/begeni/yorum sayilari. Analytics API (Cloud'da "YouTube Analytics API" acik olmali):
izlenme suresi, ortalama izlenme yuzdesi, abone kazanimi, trafik kaynaklari (son 28 gun, ~2 gun gecikmeli).
Claude veriyi yorumlar: sana Turkce ozet (cikti/raporlar/rapor_TARIH.md), kurgu planina dersler (ogrenme.json).

  python -m studyo.rapor              raporu olustur ve ac
  python -m studyo.rapor --arka-plan  acmadan (bekci kullanir)
"""
import argparse
import datetime
import json
import os
import re
import sys

from . import ayar as ayar_modulu, claude, youtube
from .ayar import KOK

OGRENME = os.path.join(KOK, "ogrenme.json")
EN_AZ_IZLENME = 30   # bundan az toplam izlenmede ders cikarilmaz (gurultu)

_KOMUT = """You are the growth analyst of the YouTube channel "{kanal}" ({oyun} gameplay with live AI-translated Turkish
subtitles; long videos + Shorts made automatically from play sessions by an AI editor).
Below is the channel's performance data (last 28 days from YouTube Analytics where available, lifetime counters
otherwise). "tur" is uzun (long video) or shorts.

{veri}

Return JSON only, no other text:
{{"ozet_tr": "<for the creator, in casual Turkish: 4-8 short lines, what works, what does not, 2-3 concrete next steps>",
 "dersler": ["<short, specific English lessons for the AI editor that picks scenes and writes titles, e.g. 'Shorts that
 start with a crash get 3x more views than dialogue Shorts: prefer action hooks'; max 8, only what the data supports>"]}}"""


def _sure_sn(iso):
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    g, s, d, sn = (int(x or 0) for x in m.groups())
    return g * 86400 + s * 3600 + d * 60 + sn


def _tum_videolar(servis):
    kanal = servis.channels().list(part="contentDetails,statistics,snippet", mine=True).execute()["items"][0]
    yuklemeler = kanal["contentDetails"]["relatedPlaylists"]["uploads"]
    idler, istek = [], servis.playlistItems().list(part="contentDetails", playlistId=yuklemeler, maxResults=50)
    while istek is not None and len(idler) < 200:
        cevap = istek.execute()
        idler += [i["contentDetails"]["videoId"] for i in cevap.get("items", [])]
        istek = servis.playlistItems().list_next(istek, cevap)
    bizim = {v["id"]: v for v in youtube.durum_oku()["videolar"]}
    videolar = []
    for i in range(0, len(idler), 50):
        for v in servis.videos().list(part="snippet,statistics,contentDetails,status",
                                      id=",".join(idler[i:i + 50])).execute().get("items", []):
            sure = _sure_sn(v["contentDetails"].get("duration"))
            st = v.get("statistics", {})
            videolar.append({
                "id": v["id"], "baslik": v["snippet"]["title"], "yayin": v["snippet"].get("publishedAt", "")[:10],
                "gizlilik": v["status"]["privacyStatus"],
                "tur": bizim.get(v["id"], {}).get("tur") or ("shorts" if sure <= 180 else "uzun"),
                "sure_sn": sure, "izlenme": int(st.get("viewCount", 0)), "begeni": int(st.get("likeCount", 0)),
                "yorum": int(st.get("commentCount", 0)), "otomatik": v["id"] in bizim,
            })
    return kanal, videolar


def _analitik(bitis, baslangic):
    """(video bazinda metrikler, trafik kaynaklari, kanal toplami) ya da hata metni."""
    from googleapiclient.errors import HttpError
    try:
        a = youtube.analitik_servis()
        ortak = dict(ids="channel==MINE", startDate=baslangic, endDate=bitis)
        v = a.reports().query(metrics="views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,"
                                      "likes,subscribersGained", dimensions="video", sort="-views", maxResults=50,
                              **ortak).execute()
        t = a.reports().query(metrics="views", dimensions="insightTrafficSourceType", sort="-views", **ortak).execute()
        k = a.reports().query(metrics="views,estimatedMinutesWatched,subscribersGained,subscribersLost", **ortak).execute()
    except youtube.GirisGerekli as e:
        return None, None, None, str(e)
    except HttpError as e:
        metin = str(e)
        if "accessNotConfigured" in metin or "has not been used" in metin or "disabled" in metin:
            return None, None, None, "Google Cloud'da 'YouTube Analytics API' acik degil (APIs & Services > Library > Enable)."
        return None, None, None, "Analytics API hatasi: %s" % metin[:200]

    def satirlar(r):
        adlar = [c["name"] for c in r.get("columnHeaders", [])]
        return [dict(zip(adlar, s)) for s in r.get("rows") or []]
    video = {s["video"]: s for s in satirlar(v)}
    return video, satirlar(t), (satirlar(k) or [{}])[0], None


def calistir(gunluk=print):
    ayar = ayar_modulu.yukle()
    servis = youtube._servis()
    kanal, videolar = _tum_videolar(servis)
    bugun = datetime.date.today()
    video_analiz, trafik, toplam, analiz_hatasi = _analitik(bugun.isoformat(), (bugun - datetime.timedelta(days=28)).isoformat())
    for v in videolar:
        a = (video_analiz or {}).get(v["id"], {})
        v["izlenme_28g"] = a.get("views")
        v["izlenme_dk_28g"] = a.get("estimatedMinutesWatched")
        v["ort_izlenme_sn"] = a.get("averageViewDuration")
        v["ort_izlenme_yuzde"] = a.get("averageViewPercentage")
        v["abone_kazanimi"] = a.get("subscribersGained")
    videolar.sort(key=lambda v: -v["izlenme"])
    acik = [v for v in videolar if v["gizlilik"] == "public"]
    toplam_izlenme = sum(v["izlenme"] for v in acik)

    ozet, dersler = None, []
    if acik and toplam_izlenme >= EN_AZ_IZLENME and claude.var_mi():
        veri = {"kanal_28g": toplam, "trafik_kaynaklari_28g": trafik,
                "videolar": [{k: v[k] for k in v if k not in ("id", "otomatik")} for v in acik[:40]]}
        gunluk("Claude veriyi yorumluyor...")
        ham = claude.iste(_KOMUT.format(kanal=ayar["kanal"], oyun=ayar["oyun"], veri=json.dumps(veri, ensure_ascii=False)),
                          KOK, ayar.get("claude_model"), gunluk)
        if isinstance(ham, dict):
            ozet = str(ham.get("ozet_tr") or "").strip() or None
            dersler = [str(d).strip() for d in (ham.get("dersler") or []) if str(d).strip()][:8]
    if dersler:
        with open(OGRENME, "w", encoding="utf-8") as f:
            json.dump({"tarih": bugun.isoformat(), "dersler": dersler}, f, ensure_ascii=False, indent=2)

    klasor = os.path.join(ayar["cikti_klasoru"], "raporlar")
    os.makedirs(klasor, exist_ok=True)
    yol = os.path.join(klasor, "rapor_%s.md" % bugun.isoformat())
    st = kanal.get("statistics", {})
    with open(yol, "w", encoding="utf-8") as f:
        f.write("# %s performans raporu (%s)\n\n" % (kanal["snippet"]["title"], bugun.isoformat()))
        f.write("Abone: %s | Toplam izlenme: %s | Video: %s\n\n" % (st.get("subscriberCount", "?"), st.get("viewCount", "?"),
                                                                 st.get("videoCount", "?")))
        if toplam:
            f.write("Son 28 gün: %s izlenme, %s dk izlenme süresi, +%s / -%s abone\n\n" % (
                toplam.get("views", 0), toplam.get("estimatedMinutesWatched", 0), toplam.get("subscribersGained", 0),
                toplam.get("subscribersLost", 0)))
        if analiz_hatasi:
            f.write("> Ayrıntılı analiz yok: %s\n\n" % analiz_hatasi)
        f.write("## Claude'un yorumu\n\n%s\n\n" % (ozet or (
            "Henüz yorum için yeterli veri yok (herkese açık videolarda toplam %d izlenme; en az %d gerekiyor)."
            % (toplam_izlenme, EN_AZ_IZLENME))))
        if dersler:
            f.write("## Kurguya aktarılan dersler\n\n%s\n\n" % "\n".join("- " + d for d in dersler))
        if trafik:
            f.write("## İzleyiciler nereden geliyor (28 gün)\n\n%s\n\n" % "\n".join(
                "- %s: %s" % (t.get("insightTrafficSourceType"), t.get("views")) for t in trafik[:8]))
        f.write("## Videolar\n\n| İzlenme | Beğeni | Yorum | Ort. izlenme % | Tür | Durum | Başlık |\n|---|---|---|---|---|---|---|\n")
        for v in videolar:
            yuzde = "%.0f" % v["ort_izlenme_yuzde"] if v.get("ort_izlenme_yuzde") is not None else "-"
            f.write("| %d | %d | %d | %s | %s | %s | [%s](https://youtu.be/%s) |\n" % (
                v["izlenme"], v["begeni"], v["yorum"], yuzde, v["tur"], v["gizlilik"],
                v["baslik"].replace("|", "/"), v["id"]))
    d = youtube.durum_oku()
    d["son_rapor"] = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    youtube.durum_yaz(d)
    return yol, ozet, analiz_hatasi


def main(argv=None):
    ap = argparse.ArgumentParser(prog="studyo.rapor")
    ap.add_argument("--arka-plan", action="store_true", help="raporu acma (bekci)")
    arg = ap.parse_args(argv)
    try:
        yol, ozet, hata = calistir()
    except youtube.GirisGerekli as e:
        print("[!] %s" % e)
        sys.exit(2)
    print("Rapor: %s" % yol)
    if hata:
        print("[!] %s" % hata)
    if not arg.arka_plan and sys.platform == "win32":
        os.startfile(yol)


if __name__ == "__main__":
    main()
