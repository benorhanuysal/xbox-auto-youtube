"""Kullanim:
  python -m studyo                 en yeni OBS kaydini isle
  python -m studyo "kayit.mkv"     belirli bir kaydi isle
  python -m studyo --sadece-plan   video uretmeden plani goster
  python -m studyo --planlayici gemini   yalnizca Gemini ile planla (claude / gemini / yok)
"""
import argparse
import datetime
import json
import os
import sys
import time

from . import aday, altyazi, altyazi_duzelt, ayar as ayar_modulu, isaret, kayit, kurgu, plan as plan_modulu, ses


def _yaz(metin):
    print(metin, flush=True)


def _aciklama(meta, ayar):
    alt = ("\n\n🎮 %s · Türkçe altyazılı oynanış\n🤖 Altyazılar yapay zekâ ile canlı çevrildi. Sistem açık kaynak: %s\n\n#%s #türkçealtyazı #gaming"
           % (ayar["oyun"], ayar["kanal_linki"], ayar["oyun"].replace(" ", "")))
    return (meta.get("aciklama") or "").strip() + alt


def _youtube_yukle(videolar, ayar, cikti):
    """Her videoyu ayri dene: biri basarisiz olursa digerleri yine yuklensin. Linkler youtube_linkleri.txt'ye."""
    from . import youtube
    from .izle import bildirim
    gizlilik = ayar["youtube_gizlilik"]
    _yaz("6/6 YouTube'a yukleme (%s)" % gizlilik)
    linkler, hatalar = [], []
    for etiket, dosya, meta in videolar:
        baslik = meta["baslik"] + (" #Shorts" if etiket.startswith("SHORTS") else "")
        kapak = os.path.join(cikti, "uzun_kapak.jpg") if etiket == "UZUN VIDEO" else None
        _yaz("  %s: %s" % (etiket, baslik))
        try:
            link = youtube.yukle(dosya, baslik, _aciklama(meta, ayar), meta["etiketler"], gizlilik, kapak, _yaz)
        except youtube.GirisGerekli as e:
            hatalar.append(str(e))
            break  # diger videolar da ayni sebeple yuklenemez
        except Exception as e:
            hatalar.append("%s: %s" % (etiket, str(e)[:200]))
            continue
        _yaz("    " + link)
        linkler.append("%s: %s\n  %s" % (etiket, baslik, link))
    if linkler:
        with open(os.path.join(cikti, "youtube_linkleri.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(linkler) + "\n\nStudio: https://studio.youtube.com\n")
    for h in hatalar:
        _yaz("  [HATA] " + h)
    if linkler:
        bildirim("YouTube'a yuklendi", "%d video %s yuklendi. Studio'da kontrol edip yayinla." %
                 (len(linkler), "gizli" if gizlilik == "private" else gizlilik))
    if hatalar:
        bildirim("YouTube yuklemesi basarisiz", hatalar[0][:150])


def main():
    ap = argparse.ArgumentParser(prog="studyo", description="OBS kaydindan Turkce altyazili uzun video + Shorts")
    ap.add_argument("kayit", nargs="?", help="video dosyasi (bos: en yeni kayit)")
    ap.add_argument("--sadece-plan", action="store_true")
    ap.add_argument("--planlayici", choices=["claude", "gemini", "yok"],
                    help="yalnizca bunu kullan (varsayilan: ayarlar.json sirasi)")
    ap.add_argument("--plani-kullan", action="store_true",
                    help="yapay zekaya sormadan cikti klasorundeki plan.json ile yeniden kurgula")
    ap.add_argument("--sadece-yukle", action="store_true",
                    help="kurgulamadan, cikti klasorundeki hazir videolari YouTube'a yukle")
    arg = ap.parse_args()

    ayar = ayar_modulu.yukle()
    t0 = time.time()
    yol = arg.kayit or kayit.en_yeni(ayar["kayit_klasoru"])
    sure = kayit.sure(yol)
    bas = kayit.baslangic(yol, sure)
    _yaz("Kayit: %s (%.1f dk, baslangic %s)" % (os.path.basename(yol), sure / 60, bas.strftime("%Y-%m-%d %H:%M:%S")))

    ad = os.path.splitext(os.path.basename(yol))[0].replace(" ", "_")
    cikti = os.path.join(ayar["cikti_klasoru"], ad)
    os.makedirs(cikti, exist_ok=True)

    if arg.sadece_yukle:
        with open(os.path.join(cikti, "plan.json"), encoding="utf-8") as f:
            plan = json.load(f)["plan"]
        videolar = [("UZUN VIDEO", os.path.join(cikti, "uzun.mp4"), plan["uzun"])]
        videolar += [("SHORTS %d" % i, os.path.join(cikti, "short_%d.mp4" % i), s) for i, s in enumerate(plan["shorts"], 1)]
        _youtube_yukle([v for v in videolar if os.path.exists(v[1])], ayar, cikti)
        return

    satirlar = altyazi.kayda_esle(ayar["luna_userconfig"], bas, sure, ayar["altyazi_gecikme_sn"])
    _yaz("1/5 Turkce altyazi: %d satir" % len(satirlar))
    if satirlar:
        altyazi.srt_yaz(satirlar, os.path.join(cikti, "kayit_tamami_tr.srt"))

    _yaz("2/5 Ses analizi (heyecanli anlar)...")
    ses_dizisi = ses.egri(yol, sure)
    heyecan = ses.heyecan(ses_dizisi)

    isaretler = isaret.kayittakiler(bas, sure)
    adaylar = aday.adaylar(heyecan, ses_dizisi, satirlar, sure, isaretler)
    _yaz("3/5 Aday sahne: %d (isaretli an: %d), kurgu plani hazirlaniyor..." % (len(adaylar), len(isaretler)))
    planlayicilar = None if not arg.planlayici else ([] if arg.planlayici == "yok" else [arg.planlayici])
    eski_plan = os.path.join(cikti, "plan.json")
    if arg.plani_kullan and os.path.exists(eski_plan):
        with open(eski_plan, encoding="utf-8") as f:
            plan = json.load(f)["plan"]
        _yaz("  Kayitli plan kullaniliyor: %s" % eski_plan)
    else:
        plan = plan_modulu.plan(adaylar, ayar, yol, cikti, _yaz, planlayicilar, sure)
    with open(os.path.join(cikti, "plan.json"), "w", encoding="utf-8") as f:
        json.dump({"kayit": yol, "adaylar": adaylar, "plan": plan}, f, ensure_ascii=False, indent=2)
    uzun_sn = sum(s - b for b, s in plan["uzun"]["parcalar"])
    _yaz("  Uzun video: %d sahne, %.1f dk | Shorts: %d" % (len(plan["uzun"]["parcalar"]), uzun_sn / 60, len(plan["shorts"])))
    if arg.sadece_plan:
        _yaz("Plan: %s" % os.path.join(cikti, "plan.json"))
        return

    if ayar["altyazi_gom"] and ayar["altyazi_duzelt"] and satirlar:
        # Yalnizca videoya girecek satirlar: canli ceviri uzun/harfiyen, izleyici okumaya yetismiyor
        parcalar = list(plan["uzun"]["parcalar"]) + [p for s in plan["shorts"] for p in s["parcalar"]]
        kullanilan = [s for s in satirlar if any(s.bas < son and s.son > bas for bas, son in parcalar)]
        kalan = {id(s) for s in altyazi_duzelt.duzelt(kullanilan, ayar, cikti, _yaz)}
        satirlar = [s for s in satirlar if id(s) in kalan or s not in kullanilan]

    ad_kod, _ = kurgu.kodlayici()
    _yaz("4/5 Kurgu (kodlayici: %s)" % ad_kod)
    videolar = []
    if plan["uzun"]["parcalar"]:
        _yaz("  Uzun video")
        dosya = os.path.join(cikti, "uzun.mp4")
        kurgu.video_yap(yol, plan["uzun"]["parcalar"], dosya, "yatay", satirlar, None, ayar["altyazi_gom"], _yaz)
        # Kapak: en heyecanli secilen sahnenin ortasi
        en_iyi = max(plan["uzun"]["parcalar"], key=lambda p: heyecan[int(p[0]):int(p[1]) + 1].max() if len(heyecan) else 0)
        kurgu.kucuk_resim(yol, (en_iyi[0] + en_iyi[1]) / 2, os.path.join(cikti, "uzun_kapak.jpg"))
        altyazi.srt_yaz(altyazi.yeniden_zamanla(satirlar, plan["uzun"]["parcalar"]), os.path.join(cikti, "uzun_tr.srt"))
        videolar.append(("UZUN VIDEO", dosya, plan["uzun"]))
    for i, s in enumerate(plan["shorts"], 1):
        _yaz("  Shorts %d" % i)
        dosya = os.path.join(cikti, "short_%d.mp4" % i)
        kurgu.video_yap(yol, s["parcalar"], dosya, "dikey", satirlar, s["baslik"], ayar["altyazi_gom"], _yaz)
        videolar.append(("SHORTS %d" % i, dosya, s))

    _yaz("5/5 Yukleme bilgileri")
    with open(os.path.join(cikti, "yukleme_bilgisi.txt"), "w", encoding="utf-8") as f:
        for etiket, dosya, meta in videolar:
            baslik = meta["baslik"] + (" #Shorts" if etiket.startswith("SHORTS") else "")
            f.write("===== %s: %s =====\nBASLIK:\n%s\n\nACIKLAMA:\n%s\n\nETIKETLER:\n%s\n\n"
                    % (etiket, os.path.basename(dosya), baslik, _aciklama(meta, ayar), ", ".join(meta["etiketler"])))
    if ayar["youtube_yukle"] and videolar:
        _youtube_yukle(videolar, ayar, cikti)

    _yaz("Bitti (%.1f dk): %s" % ((time.time() - t0) / 60, cikti))
    if sys.platform == "win32":
        os.startfile(cikti)


if __name__ == "__main__":
    main()
