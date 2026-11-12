"""Yorumlar: cevaplanmamis yorumlari okur, Claude cevap taslagi yazar, sen tek tek onaylarsin (YORUMLAR.bat).
Hicbir cevap onayin olmadan gonderilmez.

  python -m studyo.yorumlar          yeni yorumlar, taslaklar, onay
  python -m studyo.yorumlar --say    yalnizca yeni yorum sayisi
"""
import argparse
import json

from . import ayar as ayar_modulu, claude, youtube
from .ayar import KOK

_KOMUT = """You manage the comments of the YouTube channel "{kanal}": {oyun} gameplay with live AI-translated Turkish
subtitles, made by a Turkish gamer. The subtitle system is free and open source: {link}

Write a reply to each comment below as the channel owner: 1-2 short sentences, warm and casual, a little humor if it
fits, answer questions honestly, reply in the commenter's language (usually Turkish), no hashtags, do not ask for
subscriptions in every reply. If a comment is spam, hate, a scam link or needs no answer, return "" for it.
Return JSON only, no other text: {{"cevaplar": {{"<id>": "<reply>"}}}}

Comments:
{yorumlar}"""
EN_FAZLA_SAYFA = 3
SAKLANAN_ISLENEN = 3000


def yeniler(servis=None):
    """Kanalin cevaplamadigi, daha once islenmemis ust yorumlar (en yenisi once)."""
    servis = servis or youtube._servis(youtube.KAPSAM_TAM)
    _, kanal_id = youtube.kanal(servis)
    islenen = set(youtube.durum_oku()["yorum_islenen"])
    sonuc, sayfa = [], 0
    istek = servis.commentThreads().list(part="snippet,replies", allThreadsRelatedToChannelId=kanal_id,
                                         maxResults=100, order="time", textFormat="plainText")
    while istek is not None and sayfa < EN_FAZLA_SAYFA:
        cevap = istek.execute()
        sayfa += 1
        for t in cevap.get("items", []):
            ust = t["snippet"]["topLevelComment"]["snippet"]
            if t["id"] in islenen or ust.get("authorChannelId", {}).get("value") == kanal_id:
                continue
            yanitlar = (t.get("replies") or {}).get("comments", [])
            if any(r["snippet"].get("authorChannelId", {}).get("value") == kanal_id for r in yanitlar):
                continue
            sonuc.append({"id": t["id"], "video": t["snippet"].get("videoId"), "yazar": ust.get("authorDisplayName"),
                          "metin": ust.get("textOriginal") or ust.get("textDisplay") or "", "tarih": ust.get("publishedAt")})
        istek = servis.commentThreads().list_next(istek, cevap)
    return sonuc


def _basliklar(servis, video_idleri):
    bilinen = {v["id"]: v.get("baslik", "") for v in youtube.durum_oku()["videolar"]}
    eksik = [v for v in video_idleri if v and v not in bilinen]
    for i in range(0, len(eksik), 50):
        for v in servis.videos().list(part="snippet", id=",".join(eksik[i:i + 50])).execute().get("items", []):
            bilinen[v["id"]] = v["snippet"]["title"]
    return bilinen


def islendi(yorum_id):
    d = youtube.durum_oku()
    d["yorum_islenen"] = (d["yorum_islenen"] + [yorum_id])[-SAKLANAN_ISLENEN:]
    youtube.durum_yaz(d)


def taslaklar(yorumlar, basliklar, ayar):
    if not yorumlar or not claude.var_mi():
        return {}
    ogeler = [{"id": y["id"], "video": basliklar.get(y["video"], ""), "yazar": y["yazar"], "yorum": y["metin"][:1500]}
              for y in yorumlar]
    ham = claude.iste(_KOMUT.format(kanal=ayar["kanal"], oyun=ayar["oyun"], link=ayar["kanal_linki"],
                                    yorumlar=json.dumps(ogeler, ensure_ascii=False)),
                      KOK, ayar.get("claude_model"), lambda m: None)
    cevaplar = ham.get("cevaplar") if isinstance(ham, dict) else None
    return {k: str(v).strip() for k, v in (cevaplar or {}).items()}


def gonder(servis, yorum_id, metin):
    servis.comments().insert(part="snippet", body={"snippet": {"parentId": yorum_id, "textOriginal": metin}}).execute()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="studyo.yorumlar")
    ap.add_argument("--say", action="store_true", help="yalnizca yeni yorum sayisini yaz")
    arg = ap.parse_args(argv)
    ayar = ayar_modulu.yukle()
    try:
        servis = youtube._servis(youtube.KAPSAM_TAM)
    except youtube.GirisGerekli as e:
        print("[!] %s" % e)
        return
    yorumlar = yeniler(servis)
    if arg.say:
        print(len(yorumlar))
        return
    if not yorumlar:
        print("Cevaplanmamis yeni yorum yok.")
        return
    basliklar = _basliklar(servis, {y["video"] for y in yorumlar})
    print("%d yeni yorum. Claude cevap taslaklarini yaziyor..." % len(yorumlar))
    taslak = taslaklar(yorumlar, basliklar, ayar)
    gonderilen = 0
    for i, y in enumerate(yorumlar, 1):
        print("\n" + "=" * 70)
        print("[%d/%d] %s" % (i, len(yorumlar), basliklar.get(y["video"], y["video"])))
        print("%s: %s" % (y["yazar"], y["metin"]))
        oneri = taslak.get(y["id"], "")
        print("\nTaslak cevap: %s" % (oneri or "(Claude cevap gerekmiyor dedi: spam ya da tesekkur gerektirmeyen yorum)"))
        secim = input("[Enter] gonder   [d] kendin yaz   [a] atla   [c] cik > ").strip().lower()
        if secim == "c":
            break
        if secim == "a":
            islendi(y["id"])
            continue
        metin = input("Cevabin: ").strip() if secim == "d" else oneri
        if not metin:
            print("Bos cevap gonderilmedi.")
            if secim != "d":
                islendi(y["id"])
            continue
        try:
            gonder(servis, y["id"], metin)
        except Exception as e:
            print("[HATA] gonderilemedi: %s" % str(e)[:200])
            continue
        islendi(y["id"])
        gonderilen += 1
        print("Gonderildi.")
    print("\n%d cevap gonderildi." % gonderilen)


if __name__ == "__main__":
    main()
