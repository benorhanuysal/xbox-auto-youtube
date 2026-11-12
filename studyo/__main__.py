"""Kullanim:
  python -m studyo                 en yeni OBS kaydini isle
  python -m studyo "kayit.mkv"     belirli bir kaydi isle
  python -m studyo --sadece-plan   video uretmeden plani goster
  python -m studyo --gemini-yok    Gemini'siz (puana gore) plan
"""
import argparse
import datetime
import json
import os
import sys
import time

from . import aday, altyazi, ayar as ayar_modulu, gemini, kayit, kurgu, ses


def _yaz(metin):
    print(metin, flush=True)


def _aciklama(meta, ayar):
    alt = ("\n\n🎮 %s · Türkçe altyazılı oynanış\n🤖 Altyazılar yapay zekâ ile canlı çevrildi. Sistem açık kaynak: %s\n\n#%s #türkçealtyazı #gaming"
           % (ayar["oyun"], ayar["kanal_linki"], ayar["oyun"].replace(" ", "")))
    return (meta.get("aciklama") or "").strip() + alt


def main():
    ap = argparse.ArgumentParser(prog="studyo", description="OBS kaydindan Turkce altyazili uzun video + Shorts")
    ap.add_argument("kayit", nargs="?", help="video dosyasi (bos: en yeni kayit)")
    ap.add_argument("--sadece-plan", action="store_true")
    ap.add_argument("--gemini-yok", action="store_true")
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

    satirlar = altyazi.kayda_esle(ayar["luna_userconfig"], bas, sure, ayar["altyazi_gecikme_sn"])
    _yaz("1/5 Turkce altyazi: %d satir" % len(satirlar))
    if satirlar:
        altyazi.srt_yaz(satirlar, os.path.join(cikti, "kayit_tamami_tr.srt"))

    _yaz("2/5 Ses analizi (heyecanli anlar)...")
    ses_dizisi = ses.egri(yol, sure)
    heyecan = ses.heyecan(ses_dizisi)

    adaylar = aday.adaylar(heyecan, ses_dizisi, satirlar, sure)
    _yaz("3/5 Aday sahne: %d, kurgu plani hazirlaniyor..." % len(adaylar))
    anahtar = "" if arg.gemini_yok else ayar_modulu.gemini_anahtari(ayar)
    plan = gemini.plan(adaylar, ayar, anahtar, _yaz)
    with open(os.path.join(cikti, "plan.json"), "w", encoding="utf-8") as f:
        json.dump({"kayit": yol, "adaylar": adaylar, "plan": plan}, f, ensure_ascii=False, indent=2)
    uzun_sn = sum(s - b for b, s in plan["uzun"]["parcalar"])
    _yaz("  Uzun video: %d sahne, %.1f dk | Shorts: %d" % (len(plan["uzun"]["parcalar"]), uzun_sn / 60, len(plan["shorts"])))
    if arg.sadece_plan:
        _yaz("Plan: %s" % os.path.join(cikti, "plan.json"))
        return

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
    if ayar["youtube_yukle"]:
        from . import youtube
        for etiket, dosya, meta in videolar:
            baslik = meta["baslik"] + (" #Shorts" if etiket.startswith("SHORTS") else "")
            _yaz("  %s yukleniyor (gizli)" % etiket)
            _yaz("    " + youtube.yukle(dosya, baslik, _aciklama(meta, ayar), meta["etiketler"], _yaz))

    _yaz("Bitti (%.1f dk): %s" % ((time.time() - t0) / 60, cikti))
    if sys.platform == "win32":
        os.startfile(cikti)


if __name__ == "__main__":
    main()
