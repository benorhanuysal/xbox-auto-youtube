"""Gecici herkese acik adres. Instagram, Reels kapagini dosya olarak almiyor; internetteki bir adresten kendisi
indiriyor (cover_url). Kapak, kanalin GitHub deposundaki "reels-kapak" surumune varlik (asset) olarak yuklenir,
Reels yayinlaninca silinir. Kapak zaten Instagram'da herkese acik olacagi icin gizlilik kaybi yok.

Jeton: git'in Windows'ta kayitli GitHub girisi (git credential), ek kurulum yok. Pencere acmaz: giris yoksa hata
verir, Instagram tarafi kapagi videonun icinden secilen kareyle (thumb_offset) verir.
"""
import datetime
import json
import os
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request

from .ayar import KOK

ETIKET = "reels-kapak"
_API = "https://api.github.com"
_PENCERESIZ = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_jeton_onbellek = None


class BarinakHatasi(Exception):
    pass


def _jeton():
    global _jeton_onbellek
    if _jeton_onbellek:
        return _jeton_onbellek
    ortam = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
    r = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n", capture_output=True,
                       text=True, env=ortam, timeout=30, creationflags=_PENCERESIZ)
    m = re.search(r"^password=(.+)$", r.stdout or "", re.M)
    if not m:
        raise BarinakHatasi("git'te kayitli GitHub girisi yok")
    _jeton_onbellek = m.group(1).strip()
    return _jeton_onbellek


def _depo():
    r = subprocess.run(["git", "-C", KOK, "remote", "get-url", "origin"], capture_output=True, text=True,
                       creationflags=_PENCERESIZ)
    m = re.search(r"github\.com[:/]([^/]+)/([^/\s]+?)(?:\.git)?\s*$", r.stdout or "")
    if not m:
        raise BarinakHatasi("depo adresi okunamadi (git remote origin)")
    return m.group(1), m.group(2)


def _gh(yontem, url, veri=None, govde=None, tur=None):
    jeton = _jeton()
    basliklar = {"Authorization": "Bearer " + jeton, "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "studyo"}
    if veri is not None:
        govde = json.dumps(veri).encode("utf-8")
        tur = "application/json"
    if tur:
        basliklar["Content-Type"] = tur
    istek = urllib.request.Request(url if url.startswith("http") else _API + url, data=govde, method=yontem,
                                   headers=basliklar)
    try:
        with urllib.request.urlopen(istek, timeout=120) as y:
            metin = y.read()
            return json.loads(metin) if metin else {}
    except urllib.error.HTTPError as h:
        if h.code == 404 and yontem == "GET":
            return None
        raise BarinakHatasi("GitHub HTTP %d: %s" % (h.code, h.read().decode("utf-8", "replace")[:200].replace(jeton, "***")))
    except urllib.error.URLError as e:
        raise BarinakHatasi("GitHub baglanti: %s" % e.reason)


def _surum(sahip, depo):
    s = _gh("GET", "/repos/%s/%s/releases/tags/%s" % (sahip, depo, ETIKET))
    if s:
        return s
    return _gh("POST", "/repos/%s/%s/releases" % (sahip, depo), {
        "tag_name": ETIKET, "name": "Reels kapakları (geçici)", "prerelease": True, "make_latest": "false",
        "body": "Otomatik, geçici: Instagram Reels kapağını yalnızca bir internet adresinden alıyor. "
                "Kapaklar Reels yayınlanınca buradan silinir. Yazılım sürümü değildir."})


def _eskileri_sil(sahip, depo, surum, saat=24):
    """Silinemeden kalmis eski kapaklar (ornegin bilgisayar kapandi): bir gunden eskiyse temizle."""
    sinir = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=saat)
    for v in surum.get("assets") or []:
        try:
            tarih = datetime.datetime.fromisoformat(v["created_at"].replace("Z", "+00:00"))
            if tarih < sinir:
                _gh("DELETE", "/repos/%s/%s/releases/assets/%d" % (sahip, depo, v["id"]))
        except (KeyError, ValueError, BarinakHatasi):
            pass


def yukle(yol, ad=None):
    """Dosyayi yukler; (herkese acik adres, varlik kimligi) dondurur."""
    sahip, depo = _depo()
    surum = _surum(sahip, depo)
    _eskileri_sil(sahip, depo, surum)
    ad = ad or "%s_%s" % (datetime.datetime.now().strftime("%Y%m%d%H%M%S"), os.path.basename(yol))
    with open(yol, "rb") as f:
        veri = f.read()
    yukleme = surum["upload_url"].split("{", 1)[0] + "?name=" + urllib.parse.quote(ad)
    v = _gh("POST", yukleme, govde=veri, tur="image/jpeg" if ad.lower().endswith((".jpg", ".jpeg")) else
            "application/octet-stream")
    return v["browser_download_url"], v["id"]


def sil(varlik_id):
    sahip, depo = _depo()
    _gh("DELETE", "/repos/%s/%s/releases/assets/%d" % (sahip, depo, varlik_id))
