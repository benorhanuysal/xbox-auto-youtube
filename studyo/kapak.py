"""Reels kapagi: Shorts'tan en iyi kare + kisa kanca yazisi, kanalin synthwave renkleriyle (1080x1920 JPEG).

Kare, kaynak kayittan alinir (Shorts'taki gomulu baslik/altyazi kapakta olmasin); kayit silinmisse Shorts'tan.
Kareyi ve yaziyi Claude secer (aday kareleri gorur); Claude yoksa kare goruntu olcusuyle (netlik, renk, isik),
yazi basliktan secilir. Sonuc: short_N_kapak.jpg + kapak.json (secilen anin Shorts icindeki saniyesi: kapak
adresi kurulamazsa Instagram'a o kare "thumb_offset" ile verilir).

Instagram kapagi uc yerde kirpar: Reels sekmesi 9:16 tam, profil izgarasi ortadaki 3:4, akis ortadaki 1:1.
Yazi bu yuzden dikey ortaya (y 600-1320) konur: her kirpimda gorunur.

  python -m studyo.kapak CIKTI_KLASORU [--yeniden] [--claudesuz]   klasordeki Shorts'larin kapaklarini hazirla
"""
import argparse
import json
import os
import re
import shutil
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

G, Y = 1080, 1920
ADAY_SAYISI = 12
YAZI_FONTU = r"C:\Windows\Fonts\seguibli.ttf"   # Segoe UI Black Italic (banner'daki yazi)
ETIKET_FONTU = r"C:\Windows\Fonts\seguisb.ttf"  # Segoe UI Semibold
PEMBE, CAMGOBEGI, MOR, GECE = (255, 79, 176), (95, 243, 255), (43, 6, 64), (11, 4, 32)
_PENCERESIZ = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_KOMUT = """You design Instagram Reels covers for the gaming channel "{kanal}" ({oyun} gameplay with live Turkish
subtitles, young Turkish audience). For each Short below there is a contact sheet image in the current directory
(secim_<no>.jpg): {aday} numbered candidate frames from that Short. Read every sheet with the Read tool.

For each Short:
- "kare": the number of the frame that sells the clip best as a small thumbnail: a clear subject (character,
  vehicle, police, explosion, the WASTED screen, a striking view), sharp, well lit, no heavy motion blur.
  Avoid black, faded, menu or loading frames and frames where game subtitle text covers the middle.
- "yazi": Turkish cover text printed big in the middle of the cover: the hook of the clip in 2-5 words, max 28
  characters. It must make someone stop scrolling, but promise only what happens in the clip. Do not repeat the
  title word for word, no hashtags, no emoji, no profanity.

Shorts:
{shorts}

Reply with JSON only, no other text:
{{"shorts": [{{"no": 1, "kare": 3, "yazi": "..."}}]}}"""


# ---------------------------------------------------------------- yardimcilar
def _ffmpeg(*arg):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *arg], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", creationflags=_PENCERESIZ)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg: " + (r.stderr or "")[-300:])


def _json_oku(yol, varsayilan):
    try:
        with open(yol, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return varsayilan


def tr_buyuk(metin):
    """Turkce buyuk harf: i -> İ, ı -> I (Python'un upper()'i i'yi I yapar)."""
    return metin.replace("i", "İ").replace("ı", "I").upper()


def yedek_yazi(baslik):
    """Claude yoksa basliktan kanca: tirnak icindeki soz > iki noktadan sonrasi > son virgulden sonrasi."""
    b = re.sub(r"\s*#\w+", "", baslik or "").strip()
    # Tek tirnak sayilmaz: Turkcede ek ayiraci ("GTA V'te")
    m = re.search(r"[\"“”]([^\"“”]{4,40})[\"“”]", b)
    if m:
        return m.group(1).strip(" .")
    for ayrac in (":", ","):
        if ayrac in b:
            parca = b.rsplit(ayrac, 1)[1].strip(" .\"")
            if 4 <= len(parca) <= 40:
                return parca
    b = re.sub(r"^(GTA\s*\w+)'?\w*\s+", "", b)  # "GTA V'te ..." -> "..."
    return b[:40].rsplit(" ", 1)[0] if len(b) > 40 else b


def _puan(yol):
    """Kapaklik kare olcusu: netlik x renklilik, cok karanlik/aydinlik kareye ceza."""
    im = np.asarray(Image.open(yol).convert("RGB").resize((270, 480)), dtype=np.float32)
    gri = im.mean(axis=2)
    netlik = np.abs(np.diff(gri, axis=0)).mean() + np.abs(np.diff(gri, axis=1)).mean()
    r, g, b = im[..., 0], im[..., 1], im[..., 2]
    rg, yb = r - g, 0.5 * (r + g) - b
    renk = np.sqrt(rg.std() ** 2 + yb.std() ** 2) + 0.3 * np.sqrt(rg.mean() ** 2 + yb.mean() ** 2)
    isik = gri.mean()
    ceza = 1.0 if 45 <= isik <= 210 else (0.35 if isik < 25 or isik > 235 else 0.7)
    return netlik * (20 + renk) * ceza


# ---------------------------------------------------------------- aday kareler
def _short_kaynagi(cikti, no):
    """(kayit yolu ya da None, [(kayit_bas, kayit_son), ...]) - Shorts'un kayittaki parcalari, sirasiyla."""
    kayit = _json_oku(os.path.join(cikti, "plan.json"), {}).get("kayit")
    parcalar = [(float(p[1]), float(p[2])) for p in
                _json_oku(os.path.join(cikti, "kurgu.json"), {}).get("short_%d" % no, {}).get("parcalar", [])]
    if not kayit or not os.path.exists(kayit) or not parcalar:
        kayit = None
    return kayit, parcalar


def _sure(yol):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", yol],
                       capture_output=True, text=True, creationflags=_PENCERESIZ)
    return float(r.stdout.strip() or 0)


def aday_kareler(cikti, no, klasor, sayi=ADAY_SAYISI):
    """Shorts boyunca esit aralikli adaylar: [(yol, shorts_sn), ...]. Gecis kararmalari (bas/son 0,6 sn) disarida."""
    kayit, parcalar = _short_kaynagi(cikti, no)
    short = os.path.join(cikti, "short_%d.mp4" % no)
    if kayit:
        araliklar = parcalar
    else:
        araliklar = [(0.0, _sure(short))]
    toplam = sum(s - b for b, s in araliklar)
    adaylar, gecen = [], 0.0
    for b, s in araliklar:
        ic_b, ic_s = b + 0.6, s - 0.6
        adet = max(1, round(sayi * (s - b) / toplam)) if toplam > 0 else 1
        for k in range(adet):
            t = ic_b + (ic_s - ic_b) * (k + 0.5) / adet if ic_s > ic_b else (b + s) / 2
            adaylar.append((t, gecen + (t - b)))
        gecen += s - b
    adaylar = adaylar[:sayi]
    sonuc = []
    for k, (t, short_sn) in enumerate(adaylar, 1):
        yol = os.path.join(klasor, "aday_%d_%d.jpg" % (no, k))
        if kayit:
            # kurgu.sahne_isle'deki dikey kirpimin aynisi (gomulu yazi yok)
            _ffmpeg("-ss", "%.3f" % t, "-i", kayit, "-frames:v", "1", "-vf",
                    "crop=trunc(ih*9/16/2)*2:ih:(iw-ow)/2:0,scale=%d:%d:flags=lanczos" % (G, Y), "-q:v", "2", yol)
        else:
            _ffmpeg("-ss", "%.3f" % short_sn, "-i", short, "-frames:v", "1", "-vf", "scale=%d:%d" % (G, Y),
                    "-q:v", "2", yol)
        if os.path.exists(yol):
            sonuc.append((yol, round(short_sn, 2)))
    return sonuc


def secim_sayfasi(adaylar, yol, sutun=6, genislik=220):
    """Numarali kucuk kareler tek resimde (Claude bakip secsin)."""
    yuk = genislik * Y // G
    satir = (len(adaylar) + sutun - 1) // sutun
    sayfa = Image.new("RGB", (sutun * genislik, satir * yuk), (0, 0, 0))
    yazi = ImageFont.truetype(YAZI_FONTU, 40)
    for i, (kare, _) in enumerate(adaylar):
        k = Image.open(kare).convert("RGB").resize((genislik, yuk))
        d = ImageDraw.Draw(k)
        d.rectangle((0, 0, 62, 52), fill=(0, 0, 0))
        d.text((8, 2), str(i + 1), font=yazi, fill=(255, 230, 0))
        sayfa.paste(k, ((i % sutun) * genislik, (i // sutun) * yuk))
    sayfa.save(yol, quality=85)


# ---------------------------------------------------------------- cizim
def _satirlara_bol(metin, font, en_genislik, cizici):
    kelimeler, satirlar, satir = metin.split(), [], ""
    for k in kelimeler:
        dene = (satir + " " + k).strip()
        if satir and cizici.textlength(dene, font=font) > en_genislik:
            satirlar.append(satir)
            satir = k
        else:
            satir = dene
    if satir:
        satirlar.append(satir)
    return satirlar


def kapak_ciz(kare, yazi, oyun, kanal, cikti):
    taban = Image.open(kare).convert("RGB").resize((G, Y), Image.LANCZOS)
    isik = np.asarray(taban.convert("L"), dtype=np.float32).mean()
    taban = ImageEnhance.Color(taban).enhance(1.18)
    taban = ImageEnhance.Contrast(taban).enhance(1.08)
    if isik < 70:  # gece kareleri: biraz ac
        taban = ImageEnhance.Brightness(taban).enhance(min(1.45, 70 / max(isik, 20)))

    # Okunurluk: ortada yumusak koyu bant + kenarlarda hafif vinyet
    y = np.arange(Y, dtype=np.float32)
    bant = 170 * np.exp(-((y - Y / 2) / 420) ** 2)
    x = np.arange(G, dtype=np.float32)
    vinyet = 90 * (((x[None, :] - G / 2) / (G / 2)) ** 2 * 0.5 + ((y[:, None] - Y / 2) / (Y / 2)) ** 4)
    alfa = np.clip(bant[:, None] + vinyet, 0, 215).astype(np.uint8)
    taban = Image.composite(Image.new("RGB", (G, Y), GECE), taban, Image.fromarray(alfa, "L"))

    cizici = ImageDraw.Draw(taban)
    metin = tr_buyuk(" ".join(yazi.split()))
    for boyut in range(160, 70, -6):
        font = ImageFont.truetype(YAZI_FONTU, boyut)
        satirlar = _satirlara_bol(metin, font, 930, cizici)
        if len(satirlar) <= 3 and all(cizici.textlength(s, font=font) <= 930 for s in satirlar):
            break
    satir_y = int(boyut * 1.08)
    blok = satir_y * len(satirlar)
    ust = Y // 2 - blok // 2 - 20

    # Yazi katmani: dolgu (beyaz -> acik pembe -> pembe), koyu mor kontur, pembe neon parilti
    maske = Image.new("L", (G, Y), 0)
    kontur = Image.new("L", (G, Y), 0)
    dm, dk = ImageDraw.Draw(maske), ImageDraw.Draw(kontur)
    for i, s in enumerate(satirlar):
        sx = (G - cizici.textlength(s, font=font)) / 2
        sy = ust + i * satir_y
        dk.text((sx, sy), s, font=font, fill=255, stroke_width=max(6, boyut // 14), stroke_fill=255)
        dm.text((sx, sy), s, font=font, fill=255)
    parilti = kontur.filter(ImageFilter.GaussianBlur(22))
    taban = Image.composite(Image.new("RGB", (G, Y), PEMBE), taban, parilti.point(lambda v: min(255, v * 2)))
    taban = Image.composite(Image.new("RGB", (G, Y), MOR), taban, kontur)
    egim = np.zeros((Y, G, 3), dtype=np.uint8)
    for yy in range(ust, min(Y, ust + blok + 40)):
        o = (yy - ust) / max(1, blok)
        if o < 0.55:
            r = np.array([255, 255, 255]) + (np.array([255, 214, 240]) - 255) * (o / 0.55)
        else:
            r = np.array([255, 214, 240]) + (np.array([255, 95, 180]) - np.array([255, 214, 240])) * ((o - 0.55) / 0.45)
        egim[yy, :, :] = np.clip(r, 0, 255)
    taban = Image.composite(Image.fromarray(egim, "RGB"), taban, maske)

    # Ustte kanal adi (camgobegi, aralikli), altta oyun etiketi (koyu hap icinde)
    cizici = ImageDraw.Draw(taban)
    kf = ImageFont.truetype(YAZI_FONTU, 46)
    kanal_yazi = " ".join(kanal.upper())  # Ingilizce ad: Turkce buyuk harf kurali uygulanmaz (NIGHT, NİGHT degil)
    kx = (G - cizici.textlength(kanal_yazi, font=kf)) / 2
    ky = ust - 92
    pk = Image.new("L", (G, Y), 0)
    ImageDraw.Draw(pk).text((kx, ky), kanal_yazi, font=kf, fill=255)
    taban = Image.composite(Image.new("RGB", (G, Y), CAMGOBEGI), taban, pk.filter(ImageFilter.GaussianBlur(10)))
    cizici = ImageDraw.Draw(taban)
    cizici.text((kx, ky), kanal_yazi, font=kf, fill=(225, 255, 255))

    ef = ImageFont.truetype(ETIKET_FONTU, 40)
    etiket = "%s  •  TÜRKÇE ALTYAZILI" % oyun.upper()
    eg = cizici.textlength(etiket, font=ef) + 70
    ey = ust + blok + 46
    hap = Image.new("RGBA", (G, Y), (0, 0, 0, 0))
    ImageDraw.Draw(hap).rounded_rectangle(((G - eg) / 2, ey, (G + eg) / 2, ey + 70), radius=35,
                                          fill=GECE + (200,), outline=PEMBE + (255,), width=3)
    taban = Image.alpha_composite(taban.convert("RGBA"), hap).convert("RGB")
    ImageDraw.Draw(taban).text((G / 2, ey + 35), etiket, font=ef, fill=(255, 255, 255), anchor="mm")
    taban.save(cikti, "JPEG", quality=90, optimize=True)


# ---------------------------------------------------------------- ana akis
def _shorts_basliklari(cikti):
    """{no: (baslik, aciklama)} - plan.json'dan."""
    plan = _json_oku(os.path.join(cikti, "plan.json"), {}).get("plan", {})
    return {i: (s.get("baslik", ""), s.get("aciklama", "")) for i, s in enumerate(plan.get("shorts", []), 1)}


def hazirla(cikti, ayar, gunluk=print, yeniden=False, sadece=None):
    """Klasordeki Shorts'larin kapagini hazirla (varsa atlar). Donus: {no: {"yol", "kare_sn", "yazi"}}."""
    from . import claude

    kayit_yolu = os.path.join(cikti, "kapak.json")
    kayitli = {int(k): v for k, v in _json_oku(kayit_yolu, {}).items()}
    nolar = sorted(int(m.group(1)) for d in os.listdir(cikti) for m in [re.fullmatch(r"short_(\d+)\.mp4", d)] if m)
    if sadece is not None:
        nolar = [n for n in nolar if n in sadece]
    eksik = [n for n in nolar if yeniden or n not in kayitli
             or not os.path.exists(os.path.join(cikti, "short_%d_kapak.jpg" % n))]
    if not eksik:
        return {n: dict(kayitli[n], yol=os.path.join(cikti, "short_%d_kapak.jpg" % n)) for n in nolar if n in kayitli}

    klasor = os.path.join(cikti, "kapak_adaylari")
    os.makedirs(klasor, exist_ok=True)
    basliklar = _shorts_basliklari(cikti)
    adaylar = {}
    for n in eksik:
        try:
            adaylar[n] = aday_kareler(cikti, n, klasor)
        except Exception as e:
            gunluk("  kapak karesi alinamadi (Shorts %d): %s" % (n, str(e)[:120]))
        if adaylar.get(n):
            secim_sayfasi(adaylar[n], os.path.join(klasor, "secim_%d.jpg" % n))
    adaylar = {n: a for n, a in adaylar.items() if a}

    secim = {}
    if adaylar and "claude" in ayar.get("planlayicilar", []) and claude.var_mi():
        shorts = "\n".join('- no %d: title "%s", description "%s"' % (n, *basliklar.get(n, ("", "")))
                           for n in adaylar)
        gunluk("  Claude kapak karesi ve yazisi seciyor (%d Shorts)..." % len(adaylar))
        ham = claude.iste(_KOMUT.format(kanal=ayar["kanal"], oyun=ayar["oyun"], aday=ADAY_SAYISI, shorts=shorts),
                          klasor, ayar.get("claude_model"), gunluk) or {}
        for s in ham.get("shorts", []) if isinstance(ham, dict) else []:
            try:
                n, k = int(s.get("no")), int(s.get("kare"))
            except (TypeError, ValueError):
                continue
            if n in adaylar and 1 <= k <= len(adaylar[n]):
                secim[n] = {"kare": k, "yazi": str(s.get("yazi") or "").strip()[:40], "kaynak": "claude"}

    for n, liste in adaylar.items():
        s = secim.get(n) or {}
        if not s.get("kare"):
            puanlar = [_puan(y) for y, _ in liste]
            s = {"kare": int(np.argmax(puanlar)) + 1, "kaynak": "olcu"}
        if not s.get("yazi"):
            s["yazi"] = yedek_yazi(basliklar.get(n, ("", ""))[0]) or ayar["oyun"]
        kare, kare_sn = liste[s["kare"] - 1]
        hedef = os.path.join(cikti, "short_%d_kapak.jpg" % n)
        kapak_ciz(kare, s["yazi"], ayar["oyun"], ayar["kanal"], hedef)
        kayitli[n] = {"kare_sn": kare_sn, "yazi": s["yazi"], "kaynak": s["kaynak"]}
        gunluk("  Kapak: short_%d_kapak.jpg (%s, kare %.1f sn): %s" % (n, s["kaynak"], kare_sn, s["yazi"]))
    with open(kayit_yolu, "w", encoding="utf-8") as f:
        json.dump({str(k): v for k, v in sorted(kayitli.items())}, f, ensure_ascii=False, indent=2)
    shutil.rmtree(klasor, ignore_errors=True)
    return {n: dict(kayitli[n], yol=os.path.join(cikti, "short_%d_kapak.jpg" % n)) for n in nolar if n in kayitli}


def main(argv=None):
    from .ayar import yukle

    p = argparse.ArgumentParser(prog="python -m studyo.kapak", description="Shorts icin Reels kapagi")
    p.add_argument("cikti", help="cikti klasoru (short_N.mp4'lerin oldugu)")
    p.add_argument("--yeniden", action="store_true", help="var olan kapaklari da yeniden yap")
    p.add_argument("--claudesuz", action="store_true", help="Claude'a sorma (kare olcuyle, yazi basliktan)")
    a = p.parse_args(argv)
    ayar = yukle()
    if a.claudesuz:
        ayar["planlayicilar"] = []
    for n, k in hazirla(os.path.abspath(a.cikti), ayar, yeniden=a.yeniden).items():
        print("Shorts %d: %s" % (n, k["yol"]))


if __name__ == "__main__":
    main()
