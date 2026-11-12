"""Kullanim:
  python -m studyo                 en yeni OBS kaydini isle
  python -m studyo "kayit.mkv"     belirli bir kaydi isle
  python -m studyo --sadece-plan   video uretmeden plani goster
  python -m studyo --planlayici gemini   yalnizca Gemini ile planla (claude / gemini / yok)
  python -m studyo "kayit.mkv" --plani-kullan --youtube-guncelle
                                   kayitli planla yeniden kurgula, YouTube'daki videolari (yeniden yuklemeden) guncelle
"""
import argparse
import datetime
import json
import os
import re
import sys
import time

from . import aday, altyazi, altyazi_duzelt, ayar as ayar_modulu, isaret, kayit, kurgu, plan as plan_modulu, ses, yayin


def _yaz(metin):
    print(metin, flush=True)


def _aciklama(meta, ayar, dil="tr"):
    oyun_etiketi = ayar["oyun"].replace(" ", "")
    if dil == "en":
        metin = (meta.get("aciklama_en") or "").strip()
        bolum_basligi = "Chapters:"
        alt = ("\n\n🎮 %s · gameplay with live AI-translated Turkish subtitles\n🤖 Open-source system: %s\n\n#%s #gaming"
               % (ayar["oyun"], ayar["kanal_linki"], oyun_etiketi))
    else:
        metin = (meta.get("aciklama") or "").strip()
        bolum_basligi = "Bölümler:"
        alt = ("\n\n🎮 %s · Türkçe altyazılı oynanış\n🤖 Altyazılar yapay zekâ ile canlı çevrildi. Sistem açık kaynak: %s\n\n#%s #türkçealtyazı #gaming"
               % (ayar["oyun"], ayar["kanal_linki"], oyun_etiketi))
    if meta.get("_bolumler") and ayar["youtube_bolumler"]:
        metin += "\n\n%s\n%s" % (bolum_basligi, meta["_bolumler"])
    return metin + alt


def _mevcut_videolar(cikti):
    """Bu cikti klasorunden daha once yuklenen videolar: {etiket: video_id} (youtube_durum.json, yoksa link dosyasi)."""
    from . import youtube
    sonuc = {v["etiket"]: v["id"] for v in youtube.durum_oku()["videolar"]
             if os.path.normcase(v.get("cikti", "")) == os.path.normcase(cikti) and v.get("etiket")}
    yol = os.path.join(cikti, "youtube_linkleri.txt")
    if os.path.exists(yol):
        with open(yol, encoding="utf-8") as f:
            for etiket, vid in re.findall(r"^(UZUN VIDEO|SHORTS \d+):.*\n\s*https://youtu\.be/([\w-]+)", f.read(), re.M):
                sonuc.setdefault(etiket, vid)
    return sonuc


def _youtube_yukle(videolar, ayar, cikti, kayit_yolu, guncelle=False):
    """Her videoyu ayri dene: biri basarisiz olursa digerleri yine yuklensin.
    guncelle=True: daha once yuklenmis videolar yeniden yuklenmez, bilgileri/altyazilari/listeleri tamamlanir."""
    from . import youtube
    from .izle import bildirim
    gizlilik = ayar["youtube_gizlilik"]
    _yaz("6/6 YouTube (%s%s)" % ("guncelleme" if guncelle else gizlilik, ", zamanli" if ayar["youtube_zamanla"] else ""))
    mevcut = _mevcut_videolar(cikti) if guncelle else {}
    tam_izin = youtube.tam_izin_var_mi()
    if not tam_izin:
        _yaz("  [!] Yeni izin verilmemis: altyazi parcasi ve oynatma listesi atlanacak (python -m studyo.youtube --kur)")
    linkler, hatalar, shorts_sira = [], [], 0
    for etiket, dosya, meta in videolar:
        tur = "shorts" if etiket.startswith("SHORTS") else "uzun"
        ek = " #Shorts" if tur == "shorts" else ""
        baslik = meta["baslik"] + ek
        yerel = None
        if ayar["youtube_ingilizce"] and meta.get("baslik_en"):
            yerel = {"en": {"title": meta["baslik_en"] + ek, "description": _aciklama(meta, ayar, "en")}}
        yayin = None
        if ayar["youtube_zamanla"] and not guncelle:
            if tur == "uzun":
                yayin = youtube.yayin_zamani(ayar["youtube_uzun_saat"], 1)
            else:
                shorts_sira += 1
                yayin = youtube.yayin_zamani(ayar["youtube_shorts_saat"], shorts_sira)
        _yaz("  %s: %s" % (etiket, baslik))
        try:
            if etiket in mevcut:
                vid = mevcut[etiket]
                if tam_izin:
                    youtube.guncelle(vid, baslik, _aciklama(meta, ayar), meta["etiketler"], yerel)
                    _yaz("    bilgiler guncellendi (bolumler, Ingilizce baslik)")
            else:
                kapak = os.path.join(cikti, "uzun_kapak.jpg") if tur == "uzun" else None
                vid = youtube.yukle(dosya, baslik, _aciklama(meta, ayar), meta["etiketler"], gizlilik, kapak, _yaz,
                                    yerel, yayin)
                if yayin:
                    _yaz("    yayin zamani: %s (UTC)" % yayin)
        except youtube.GirisGerekli as e:
            hatalar.append(str(e))
            break  # diger videolar da ayni sebeple yuklenemez
        except Exception as e:
            hatalar.append("%s: %s" % (etiket, str(e)[:200]))
            continue
        link = "https://youtu.be/" + vid
        _yaz("    " + link)
        linkler.append("%s: %s\n  %s" % (etiket, baslik, link))
        youtube.video_kaydet({"id": vid, "etiket": etiket, "tur": tur, "baslik": meta["baslik"],
                              "baslik_en": meta.get("baslik_en", ""), "cikti": cikti, "kayit": kayit_yolu,
                              "sure_sn": meta.get("_sure_sn"), "bolum_sayisi": len(meta.get("_bolum_listesi") or []),
                              "yukleme": datetime.datetime.now().astimezone().isoformat(timespec="seconds")})
        if not tam_izin:
            continue
        # Oynatma listesi + altyazi parcalari: biri basarisiz olsa da video yuklenmis sayilir
        try:
            liste = (ayar["youtube_listeler"].get(tur) or "").format(oyun=ayar["oyun"], kanal=ayar["kanal"])
            liste_aciklamasi = ayar["youtube_liste_aciklamasi"].format(oyun=ayar["oyun"], kanal=ayar["kanal"])
            if liste and youtube.listeye_ekle(vid, youtube.liste_kimligi(liste, liste_aciklamasi)):
                _yaz("    listeye eklendi: %s" % liste)
        except Exception as e:
            hatalar.append("%s liste: %s" % (etiket, str(e)[:150]))
        for dil in ayar["youtube_altyazi_dilleri"].get(tur, []):
            srt = meta.get("_srt", {}).get(dil)
            if not srt or not os.path.exists(srt) or os.path.getsize(srt) == 0:
                continue
            try:
                if youtube.altyazi_yukle(vid, srt, dil, "Türkçe" if dil == "tr" else "English"):
                    _yaz("    altyazi parcasi: %s" % dil)
            except Exception as e:
                hatalar.append("%s altyazi %s: %s" % (etiket, dil, str(e)[:150]))
    if linkler:
        with open(os.path.join(cikti, "youtube_linkleri.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(linkler) + "\n\nStudio: https://studio.youtube.com\n")
    for h in hatalar:
        _yaz("  [HATA] " + h)
    if linkler and not guncelle:
        durum = "zamanlandi" if ayar["youtube_zamanla"] else ("gizli yuklendi" if gizlilik == "private" else gizlilik)
        bildirim("YouTube'a yuklendi", "%d video %s. Studio'da kontrol et." % (len(linkler), durum))
    if hatalar:
        bildirim("YouTube: sorun var", hatalar[0][:150])


def _kurgu_bilgisi_yaz(cikti, bilgi):
    with open(os.path.join(cikti, "kurgu.json"), "w", encoding="utf-8") as f:
        json.dump(bilgi, f, ensure_ascii=False, indent=2)


def _kurgu_bilgisi_oku(cikti):
    try:
        with open(os.path.join(cikti, "kurgu.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _videolar_listesi(cikti, plan, bilgi):
    """(etiket, dosya, meta) listesi; meta'ya bolum metni, altyazi dosyalari ve sure eklenir."""
    videolar = []
    adlar = [("UZUN VIDEO", "uzun", plan["uzun"])] + [("SHORTS %d" % i, "short_%d" % i, s)
                                                      for i, s in enumerate(plan["shorts"], 1)]
    for etiket, ad, meta in adlar:
        dosya = os.path.join(cikti, ad + ".mp4")
        if not os.path.exists(dosya):
            continue
        meta = dict(meta)
        b = bilgi.get(ad, {})
        meta["_bolum_listesi"] = b.get("bolumler") or []
        meta["_bolumler"] = kurgu.bolum_metni(meta["_bolum_listesi"]) if meta["_bolum_listesi"] else ""
        meta["_sure_sn"] = b.get("sure_sn")
        meta["_srt"] = {dil: os.path.join(cikti, "%s_%s.srt" % (ad, dil)) for dil in ("tr", "en")}
        videolar.append((etiket, dosya, meta))
    return videolar


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
    ap.add_argument("--youtube-guncelle", action="store_true",
                    help="daha once yuklenmis videolari yeniden yuklemeden guncelle (bolum, Ingilizce, altyazi, liste)")
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
        _youtube_yukle(_videolar_listesi(cikti, plan, _kurgu_bilgisi_oku(cikti)), ayar, cikti, yol, arg.youtube_guncelle)
        return

    satirlar = altyazi.kayda_esle(ayar["luna_userconfig"], bas, sure, ayar["altyazi_gecikme_sn"])
    _yaz("1/5 Turkce altyazi: %d satir" % len(satirlar))
    if satirlar:
        altyazi.srt_yaz(satirlar, os.path.join(cikti, "kayit_tamami_tr.srt"))

    _yaz("2/5 Ses analizi (heyecanli anlar)...")
    ses_dizisi = ses.egri(yol, sure)
    heyecan = ses.heyecan(ses_dizisi)
    mikrofon = ses.mikrofon_egri(yol, sure)
    konusmalar = ses.konusmalar(mikrofon)
    if len(mikrofon):
        _yaz("  Mikrofon: %d konusma, toplam %.0f sn" % (len(konusmalar), sum(s - b for b, s in konusmalar)))

    isaretler = isaret.kayittakiler(bas, sure)
    adaylar = aday.adaylar(heyecan, ses_dizisi, satirlar, sure, isaretler, konusmalar)
    _yaz("3/5 Aday sahne: %d (isaretli an: %d, yorumlu: %d), kurgu plani hazirlaniyor..." % (
        len(adaylar), len(isaretler), sum(1 for a in adaylar if a.get("yorum"))))
    planlayicilar = None if not arg.planlayici else ([] if arg.planlayici == "yok" else [arg.planlayici])
    eski_plan = os.path.join(cikti, "plan.json")
    if arg.plani_kullan and os.path.exists(eski_plan):
        with open(eski_plan, encoding="utf-8") as f:
            plan = json.load(f)["plan"]
        _yaz("  Kayitli plan kullaniliyor: %s" % eski_plan)
        plan_modulu.meta_tamamla(plan, satirlar, ayar, cikti, _yaz)
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

    # Kick yayini surerken canli Turkce altyazi katmani goruntudeydi: o araliklarda altyazi ikinci kez gomulmez
    # (SRT altyazi parcalari yine tum satirlarla yazilir)
    canli = yayin.kayittakiler(bas, sure)
    canli_satirlar = {id(s) for s in yayin.gomulmeyecekler(satirlar, canli)}
    gomulecek = [s for s in satirlar if id(s) not in canli_satirlar]
    if canli:
        _yaz("  Canli yayin araligi: %d (%.0f dk), %d satir zaten goruntude" % (
            len(canli), sum(s - b for b, s in canli) / 60, len(canli_satirlar)))

    ad_kod, _ = kurgu.kodlayici()
    _yaz("4/5 Kurgu (kodlayici: %s)" % ad_kod)
    bilgi = {}

    def _altyazi_dosyalari(ad_, giren):
        gercek = [(b, s) for _, b, s in giren]
        zamanli = altyazi.yeniden_zamanla(satirlar, gercek)
        for dil in ("tr", "en"):
            altyazi.srt_yaz(zamanli, os.path.join(cikti, "%s_%s.srt" % (ad_, dil)), dil)
        return sum(s - b for b, s in gercek)

    if plan["uzun"]["parcalar"]:
        _yaz("  Uzun video")
        dosya = os.path.join(cikti, "uzun.mp4")
        # Yayin parcalarinda Kick chat kutusu goruntudeydi: uzun videoda bulaniklasir (Shorts'a zaten girmez)
        sohbet_kutusu = ayar["yayin_chat_kutusu"] if canli and yayin.katmanlar_var_mi() else None
        giren = kurgu.video_yap(yol, plan["uzun"]["parcalar"], dosya, "yatay", gomulecek, None, ayar["altyazi_gom"], _yaz,
                                sohbet_kutusu, canli)
        # Kapak: en heyecanli secilen sahnenin ortasi
        en_iyi = max(plan["uzun"]["parcalar"], key=lambda p: heyecan[int(p[0]):int(p[1]) + 1].max() if len(heyecan) else 0)
        kurgu.kucuk_resim(yol, (en_iyi[0] + en_iyi[1]) / 2, os.path.join(cikti, "uzun_kapak.jpg"))
        bolumler = kurgu.bolum_listesi(giren, plan["uzun"].get("bolumler") or [])
        bilgi["uzun"] = {"parcalar": giren, "bolumler": bolumler, "sure_sn": _altyazi_dosyalari("uzun", giren)}
        if bolumler:
            _yaz("    %d bolum" % len(bolumler))
    for i, s in enumerate(plan["shorts"], 1):
        _yaz("  Shorts %d" % i)
        dosya = os.path.join(cikti, "short_%d.mp4" % i)
        giren = kurgu.video_yap(yol, s["parcalar"], dosya, "dikey", gomulecek, s["baslik"], ayar["altyazi_gom"], _yaz)
        bilgi["short_%d" % i] = {"parcalar": giren, "sure_sn": _altyazi_dosyalari("short_%d" % i, giren)}
    _kurgu_bilgisi_yaz(cikti, bilgi)
    videolar = _videolar_listesi(cikti, plan, bilgi)

    _yaz("5/5 Yukleme bilgileri")
    with open(os.path.join(cikti, "yukleme_bilgisi.txt"), "w", encoding="utf-8") as f:
        for etiket, dosya, meta in videolar:
            ek = " #Shorts" if etiket.startswith("SHORTS") else ""
            f.write("===== %s: %s =====\nBASLIK:\n%s\n\nACIKLAMA:\n%s\n\nETIKETLER:\n%s\n\n"
                    % (etiket, os.path.basename(dosya), meta["baslik"] + ek, _aciklama(meta, ayar), ", ".join(meta["etiketler"])))
            if meta.get("baslik_en"):
                f.write("ENGLISH TITLE:\n%s\n\nENGLISH DESCRIPTION:\n%s\n\n" % (meta["baslik_en"] + ek, _aciklama(meta, ayar, "en")))
    if (ayar["youtube_yukle"] or arg.youtube_guncelle) and videolar:
        yayin.bitmesini_bekle(_yaz)
        _youtube_yukle(videolar, ayar, cikti, yol, arg.youtube_guncelle)

    _yaz("Bitti (%.1f dk): %s" % ((time.time() - t0) / 60, cikti))
    if sys.platform == "win32" and not arg.youtube_guncelle:
        os.startfile(cikti)


if __name__ == "__main__":
    main()
