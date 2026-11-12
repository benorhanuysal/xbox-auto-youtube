"""ffmpeg ile kurgu: her sahne ayri islenir (olcek, Shorts icin dikey, altyazi gomme, yumusak gecis),
sonra kayipsiz birlestirilir. Ekran karti kodlayicisi varsa (NVIDIA NVENC / Intel QSV) o kullanilir."""
import os
import subprocess

from . import altyazi

_KODLAYICILAR = [
    ("h264_nvenc", ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "21", "-b:v", "0"]),
    ("h264_qsv", ["-c:v", "h264_qsv", "-preset", "medium", "-global_quality", "22"]),
    ("libx264", ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21"]),
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
        # 9:16: arkada bulaniklastirilmis tam ekran, ortada oyunun kendisi
        goruntu = ("[0:v]split[a][b];"
                   "[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=24:2,eq=brightness=-0.12[arka];"
                   "[b]scale=1080:-2[on];[arka][on]overlay=(W-w)/2:(H-h)/2,fps=60,setsar=1")
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
    ses_girdisi = "[0:a]" if ses_var(kaynak) else "anullsrc=r=48000:cl=stereo,atrim=0:%.3f," % sure
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


def video_yap(kaynak, parcalar, cikti, bicim, satirlar, baslik=None, altyazi_gom=True, gunluk=print):
    """parcalar: [[bas, son], ...] -> tek video."""
    klasor = os.path.dirname(os.path.abspath(cikti))
    ad = os.path.splitext(os.path.basename(cikti))[0]
    ara = []
    for i, (bas, son) in enumerate(parcalar, 1):
        gunluk("    sahne %d/%d (%.0f-%.0f sn)" % (i, len(parcalar), bas, son))
        p = os.path.join(klasor, "_%s_%03d.mp4" % (ad, i))
        sahne_isle(kaynak, bas, son, p, bicim, satirlar, baslik, altyazi_gom)
        ara.append(p)
    birlestir(ara, cikti)
    for p in ara:
        os.remove(p)
        ass = os.path.splitext(p)[0] + ".ass"
        if os.path.exists(ass):
            os.remove(ass)
