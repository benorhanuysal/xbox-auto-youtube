"""OBS kayitlarini bulur; baslangic zamanini dosya adindan, suresini ffprobe ile okur."""
import datetime
import json
import os
import re
import subprocess

UZANTILAR = (".mkv", ".mp4", ".mov", ".flv")
# OBS varsayilan dosya adi: "2026-11-12 21-30-05.mkv"
_AD = re.compile(r"(\d{4})-(\d{2})-(\d{2})[ _](\d{2})-(\d{2})-(\d{2})")


def en_yeni(klasor):
    dosyalar = [
        os.path.join(klasor, d) for d in os.listdir(klasor)
        if d.lower().endswith(UZANTILAR) and os.path.isfile(os.path.join(klasor, d))
    ]
    if not dosyalar:
        raise SystemExit("Kayit bulunamadi: %s (OBS kayit klasorunu ayarlar.json'da 'kayit_klasoru' olarak yazin)" % klasor)
    return max(dosyalar, key=os.path.getmtime)


def sure(yol):
    cikti = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", yol],
        capture_output=True, text=True, check=True,
    ).stdout
    return float(json.loads(cikti)["format"]["duration"])


def baslangic(yol, sure_sn):
    m = _AD.search(os.path.basename(yol))
    if m:
        return datetime.datetime(*map(int, m.groups()))
    # Ad farkliysa: dosyanin son yazilma ani kaydin bitisidir
    return datetime.datetime.fromtimestamp(os.path.getmtime(yol)) - datetime.timedelta(seconds=sure_sn)
