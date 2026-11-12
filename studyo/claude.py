"""Claude ile kurgu plani: bilgisayardaki Claude Code arka planda calistirilir (`claude -p`),
kullanicinin Claude aboneligiyle cevap verir (ayrica API ucreti yok). Sahnelerin kare seritlerini
Read araciyla kendisi okuyup goruntuye de bakar. Claude Code yoksa ya da limit dolduysa None doner,
sira Gemini'ye gecer."""
import json
import shutil
import subprocess

ZAMAN_ASIMI = 900  # sn: kareleri okuyup plan yapmasi birkac dakika surebilir


def var_mi():
    return shutil.which("claude") is not None


def _json_cikar(metin):
    """Cevaptaki ilk { ile son } arasini JSON olarak oku (Claude bazen ```json bloguna sarar)."""
    bas, son = metin.find("{"), metin.rfind("}")
    if bas < 0 or son <= bas:
        raise ValueError("cevapta JSON yok")
    return json.loads(metin[bas:son + 1])


def iste(metin, klasor, model=None, gunluk=print):
    komut = [shutil.which("claude"), "-p", "--output-format", "json", "--allowedTools", "Read"]
    if model:
        komut += ["--model", model]
    try:
        r = subprocess.run(komut, input=metin, cwd=klasor, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=ZAMAN_ASIMI)
    except subprocess.TimeoutExpired:
        gunluk("  Claude zaman asimi (%d sn)" % ZAMAN_ASIMI)
        return None
    except OSError as e:
        gunluk("  Claude calistirilamadi: %s" % e)
        return None
    try:
        cikti = json.loads(r.stdout)
    except ValueError:
        gunluk("  Claude cevabi okunamadi (cikis kodu %d): %s" % (r.returncode, (r.stderr or r.stdout)[-300:].strip()))
        return None
    if cikti.get("is_error") or r.returncode != 0:
        # Ornek: kullanim limiti doldu, oturum acilmamis
        gunluk("  Claude hata verdi: %s" % str(cikti.get("result") or cikti.get("subtype"))[:300])
        return None
    try:
        ham = _json_cikar(cikti.get("result", ""))
    except ValueError as e:
        gunluk("  Claude plani JSON degil: %s" % e)
        return None
    gunluk("  Claude cevabi hazir (%.0f sn)" % (cikti.get("duration_ms", 0) / 1000))
    return ham
