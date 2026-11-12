"""ffmpeg ile kurgu: her sahne ayri islenir (olcek, Shorts icin dikey, altyazi gomme, yumusak gecis),
sonra kayipsiz birlestirilir. Ekran karti kodlayicisi varsa (NVIDIA NVENC / Intel QSV) o kullanilir."""
import os
import re
import subprocess

from . import altyazi

_KODLAYICILAR = [
    ("h264_nvenc", ["-c:v", "h264_nvenc", "-preset", "p6", "-tune", "hq", "-rc", "vbr", "-cq", "19", "-b:v", "0",
                    "-spatial-aq", "1"]),
    ("h264_qsv", ["-c:v", "h264_qsv", "-preset", "medium", "-global_quality", "20"]),
    ("libx264", ["-c:v", "libx264", "-preset", "medium", "-crf", "19"]),
]
_secili = None
GECIS = 0.35  # sn: sahne basinda/sonunda kararma


def kodlayici():
    global _secili
    if _secili is None:
        for ad, argumanlar in _KODLAYICILAR:
            r = subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=s=256x256:d=0.2",
                 *argumanlar, "-f", "null", "-"],
                capture_output=True,
            )
            if r.returncode == 0:
                _secili = (ad, argumanlar)
                break
    return _secili


_ses_onbellek = {}


def ses_var(kaynak):
    if kaynak not in _ses_onbellek:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                            "-of", "csv=p=0", kaynak], capture_output=True, text=True)
        _ses_onbellek[kaynak] = bool(r.stdout.strip())
    return _ses_onbellek[kaynak]


def _calistir(komut, klasor):
    r = subprocess.run(komut, cwd=klasor, capture_output=True, text=True, errors="replace")
    if r.returncode != 0:
        raise RuntimeError("ffmpeg hatasi:\n" + r.stderr[-2000:])


def sahne_isle(kaynak, bas, son, cikti, bicim, satirlar, baslik=None, altyazi_gom=True):
    """Kaynaktan [bas, son] araligini isleyip cikti dosyasina yazar."""
    klasor = os.path.dirname(os.path.abspath(cikti))
    sure = son - bas
    if bicim == "dikey":
        # 9:16 tam ekran: oyunun ortasindan (karakter genelde ortada) dikey kirp, buyutup hafif keskinlestir
        goruntu = ("[0:v]crop=trunc(ih*9/16/2)*2:ih:(iw-ow)/2:0,scale=1080:1920:flags=lanczos,"
                   "unsharp=5:5:0.5:5:5:0,fps=60,setsar=1")
    else:
        goruntu = ("[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
                   "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=60,setsar=1")
    sahne_satirlari = altyazi.kes(satirlar, bas, son) if altyazi_gom else []
    if sahne_satirlari or baslik:
        ass_ad = os.path.splitext(os.path.basename(cikti))[0] + ".ass"
        altyazi.ass_yaz(sahne_satirlari, os.path.join(klasor, ass_ad), bicim, baslik, sure)
        goruntu += ",subtitles=%s" % ass_ad  # goreli ad: Windows yolundaki ':' kacis derdi yok
    goruntu += ",fade=t=in:st=0:d=%.2f,fade=t=out:st=%.2f:d=%.2f[v]" % (GECIS, max(0, sure - GECIS), GECIS)
    # Ses kanali yoksa sessizlik uret (birlestirmede tum parcalarda ses olmali)
    # 1. ses kanali = oyun + mikrofon karisimi (2. kanal yalniz mikrofon, analiz icin)
    ses_girdisi = "[0:a:0]" if ses_var(kaynak) else "anullsrc=r=48000:cl=stereo,atrim=0:%.3f," % sure
    ses = ses_girdisi + "aresample=48000,afade=t=in:st=0:d=%.2f,afade=t=out:st=%.2f:d=%.2f[a]" % (
        GECIS, max(0, sure - GECIS), GECIS)

    _, kod = kodlayici()
    komut = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", "%.3f" % bas, "-t", "%.3f" % sure,
             "-i", os.path.abspath(kaynak), "-filter_complex", goruntu + ";" + ses,
             "-map", "[v]", "-map", "[a]", *kod, "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-video_track_timescale", "90000",
             os.path.basename(cikti)]
    _calistir(komut, klasor)


def birlestir(parcalar, cikti):
    klasor = os.path.dirname(os.path.abspath(cikti))
    liste = os.path.join(klasor, "_liste.txt")
    with open(liste, "w", encoding="utf-8") as f:
        for p in parcalar:
            f.write("file '%s'\n" % os.path.basename(p).replace("'", "'\\''"))
    _calistir(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
               "-i", "_liste.txt", "-c", "copy", "-movflags", "+faststart", os.path.basename(cikti)], klasor)
    os.remove(liste)


def kucuk_resim(kaynak, t, cikti):
    _calistir(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", "%.2f" % t, "-i", os.path.abspath(kaynak),
               "-frames:v", "1", "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2",
               "-q:v", "3", os.path.abspath(cikti)], os.path.dirname(os.path.abspath(cikti)))


def kare_seridi(kaynak, bas, son, cikti, genislik=400):
    """Sahnenin basindan, ortasindan ve sonundan 3 kare, yan yana tek resim (yapay zeka goruntuye baksin)."""
    sure = son - bas
    girdiler, filtre = [], []
    for i, oran in enumerate((0.15, 0.5, 0.85)):
        girdiler += ["-ss", "%.2f" % (bas + sure * oran), "-i", os.path.abspath(kaynak)]
        filtre.append("[%d:v]scale=%d:-2,setsar=1[k%d]" % (i, genislik, i))
    filtre.append("[k0][k1][k2]hstack=inputs=3[v]")
    _calistir(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *girdiler, "-filter_complex", ";".join(filtre),
               "-map", "[v]", "-frames:v", "1", "-q:v", "4", os.path.abspath(cikti)],
              os.path.dirname(os.path.abspath(cikti)))


def ozet_sayfalari(kaynak, sure_sn, klasor, aralik=10, sutun=6, satir=8):
    """Kaydin tamamindan her `aralik` saniyede bir kare; her sayfada sutun x satir kare, uzerinde saniyesi.
    Yapay zeka ses/diyalogla bulunamayan anlari (dusme, kaza, komik fizik) buradan bulur.
    Yalnizca anahtar kareler cozulur: saatlik kayit da hizli biter."""
    os.makedirs(klasor, exist_ok=True)
    for eski in os.listdir(klasor):
        if eski.startswith("ozet_") and eski.endswith(".jpg"):
            os.remove(os.path.join(klasor, eski))
    yazi = ("drawtext=fontfile='C\\:/Windows/Fonts/arialbd.ttf':text='%{eif\\:t\\:d}':x=6:y=6:fontsize=26:"
            "fontcolor=yellow:box=1:boxcolor=black@0.7")
    _calistir(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-skip_frame", "nokey", "-i", os.path.abspath(kaynak),
               "-vf", "fps=1/%d,scale=320:-2,%s,tile=%dx%d" % (aralik, yazi, sutun, satir), "-fps_mode", "vfr",
               "-q:v", "4", "ozet_%d.jpg"], klasor)
    return sorted((d for d in os.listdir(klasor) if d.startswith("ozet_") and d.endswith(".jpg")),
                  key=lambda d: int(d[5:-4]))


def _siyahlar(kaynak, bas, sure):
    """[bas, bas+sure] icindeki siyah araliklar (kaynaga gore saniye)."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-ss", "%.3f" % bas, "-t", "%.3f" % sure,
                        "-i", os.path.abspath(kaynak), "-an", "-vf", "scale=480:-2,blackdetect=d=0.4:pix_th=0.08",
                        "-f", "null", "-"], capture_output=True, text=True, errors="replace")
    sonuc = []
    for m in re.finditer(r"black_start:([\d.]+) black_end:([\d.]+)", r.stderr):
        sonuc.append((bas + float(m.group(1)), bas + float(m.group(2))))
    return sonuc


def siyahi_kirp(kaynak, bas, son, bakis=8.0):
    """Sahnenin basindaki/sonundaki siyah kismi (yukleme, olum ekrani kararmasi) at."""
    try:
        for b, s in _siyahlar(kaynak, bas, min(bakis, son - bas)):
            if b <= bas + 0.2:
                bas = max(bas, s)
        if son - bas > 2:
            ilk = max(bas, son - bakis)
            for b, s in _siyahlar(kaynak, ilk, son - ilk):
                if s >= son - 0.2:
                    son = min(son, b + 0.3)
    except OSError:
        pass
    return bas, son


def video_yap(kaynak, parcalar, cikti, bicim, satirlar, baslik=None, altyazi_gom=True, gunluk=print):
    """parcalar: [[bas, son], ...] -> tek video.
    Donus: videoya giren parcalar [(plandaki_sira, bas, son), ...] (siyahi kirpilmis gercek sinirlar):
    bolum zamanlari ve altyazi dosyalari bunlara gore hesaplanir."""
    klasor = os.path.dirname(os.path.abspath(cikti))
    ad = os.path.splitext(os.path.basename(cikti))[0]
    ara, giren = [], []
    for i, (bas, son) in enumerate(parcalar, 1):
        yeni = siyahi_kirp(kaynak, bas, son)
        if yeni[1] - yeni[0] < 1.5:
            gunluk("    sahne %d/%d atlandi (tamami siyah)" % (i, len(parcalar)))
            continue
        if (round(yeni[0], 1), round(yeni[1], 1)) != (round(bas, 1), round(son, 1)):
            gunluk("    siyah kirpildi: %.1f-%.1f -> %.1f-%.1f" % (bas, son, yeni[0], yeni[1]))
        bas, son = yeni
        gunluk("    sahne %d/%d (%.0f-%.0f sn)" % (i, len(parcalar), bas, son))
        p = os.path.join(klasor, "_%s_%03d.mp4" % (ad, i))
        sahne_isle(kaynak, bas, son, p, bicim, satirlar, baslik, altyazi_gom)
        ara.append(p)
        giren.append((i - 1, bas, son))
    birlestir(ara, cikti)
    for p in ara:
        os.remove(p)
        ass = os.path.splitext(p)[0] + ".ass"
        if os.path.exists(ass):
            os.remove(ass)
    return giren


def bolum_listesi(giren, adlar, en_kisa=10.0):
    """YouTube bolumleri (chapters): [(saniye, ad), ...]. Kurallar: ilk 00:00, en az 3 bolum, her biri >= 10 sn.
    Ardisik ayni adli ya da 10 sn'den kisa parcalar oncekiyle birlesir. Kurala uymuyorsa bos liste."""
    bolumler, t = [], 0.0
    for sira, bas, son in giren:
        ad = ((adlar[sira] if sira < len(adlar) else "") or "").strip()
        if ad and (not bolumler or ad != bolumler[-1][1]):
            if bolumler and t - bolumler[-1][0] < en_kisa:
                bolumler[-1][1] = ad  # onceki bolum 10 sn'den kisa: bu bolume katilir
            else:
                bolumler.append([t, ad])
        t += son - bas
    if bolumler:
        bolumler[0][0] = 0.0
    # son bolum de en az 10 sn olmali
    while len(bolumler) > 1 and t - bolumler[-1][0] < en_kisa:
        bolumler.pop()
    return [tuple(b) for b in bolumler] if len(bolumler) >= 3 else []


def bolum_metni(bolumler):
    def zaman(sn):
        sn = int(sn)
        return "%d:%02d:%02d" % (sn // 3600, sn // 60 % 60, sn % 60) if sn >= 3600 else "%02d:%02d" % (sn // 60, sn % 60)
    return "\n".join("%s %s" % (zaman(t), ad) for t, ad in bolumler)
