"""Arka plan bekcisi: oyna, gerisini o yapsin.
- Xbox uzaktan oynatma baslayinca (Xbox uygulamasinin sesi akmaya baslayinca) OBS kaydini baslatir,
  uzaktan oynatma kapaninca durdurur. OBS kapaliysa simge durumunda acar.
- Kayit durunca (otomatik ya da elle) kurguyu baslatir; bitince Windows bildirimi gelir.
- Isaret: klavyede F9 ya da kumandada iki analog cubuga birlikte basmak o ani isaretler;
  isaretli anlar videoya mutlaka girer.

  python -m studyo.izle            bekciyi calistir (pencere kapaninca durur)
  python -m studyo.izle --kur      OBS uzaktan kumandasini ac + Windows acilisinda calistir
  python -m studyo.izle --kaldir   Windows acilisindan cikar
Arka planda pencere olmadan: IZLE.pyw (--kur bunu Windows acilisina ekler).
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import datetime
import logging
import os
import queue
import subprocess
import sys
import threading
import time

from . import ayar as ayar_modulu, isaret, kayit, obs

KOK = ayar_modulu.KOK
log = logging.getLogger("izle")
BASLANGIC_ANAHTARI = r"Software\Microsoft\Windows\CurrentVersion\Run"
BASLANGIC_ADI = "xbox-auto-youtube"
_GIZLI = getattr(subprocess, "CREATE_NO_WINDOW", 0)


# ---------------------------------------------------------------- bildirim
_TOST = r"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
$x = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$t = $x.GetElementsByTagName('text')
$t.Item(0).AppendChild($x.CreateTextNode($env:TOST_BASLIK)) > $null
$t.Item(1).AppendChild($x.CreateTextNode($env:TOST_METIN)) > $null
$id = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($id).Show([Windows.UI.Notifications.ToastNotification]::new($x))
"""


def bildirim(baslik, metin):
    log.info("bildirim: %s - %s", baslik, metin)
    try:
        ortam = dict(os.environ, TOST_BASLIK=baslik, TOST_METIN=metin)
        subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-Command", _TOST], env=ortam,
                         creationflags=_GIZLI, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


# ---------------------------------------------------------------- uzaktan oynatma algilama
def xbox_sesi_akiyor():
    """Uzaktan oynatma sirasinda Xbox uygulamasinin ses oturumu AKTIF olur; menude/kapaliyken degil."""
    from pycaw.pycaw import AudioUtilities
    for s in AudioUtilities.GetAllSessions():
        try:
            if s.Process and s.Process.name().lower() == "xboxpcapp.exe" and s.State == 1:
                return True
        except Exception:
            continue
    return False


# ---------------------------------------------------------------- isaret tuslari
class _GAMEPAD(ctypes.Structure):
    _fields_ = [("wButtons", wt.WORD), ("bLeftTrigger", ctypes.c_ubyte), ("bRightTrigger", ctypes.c_ubyte),
                ("sThumbLX", ctypes.c_short), ("sThumbLY", ctypes.c_short),
                ("sThumbRX", ctypes.c_short), ("sThumbRY", ctypes.c_short)]


class _DURUM(ctypes.Structure):
    _fields_ = [("dwPacketNumber", wt.DWORD), ("Gamepad", _GAMEPAD)]


IKI_CUBUK = 0x0040 | 0x0080  # sol + sag analog cubuga basma


def _xinput():
    for dll in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
        try:
            return getattr(ctypes.windll, dll).XInputGetState
        except OSError:
            continue
    return None


def _tus_kodu(ad):
    ad = (ad or "").strip().upper()
    if ad.startswith("F") and ad[1:].isdigit() and 1 <= int(ad[1:]) <= 24:
        return 0x6F + int(ad[1:])
    return None


def isaret_dinle(ayar, durdur):
    vk = _tus_kodu(ayar["isaret_tusu"])
    xget = _xinput() if ayar["kumanda_isaret"] else None
    tus_onceki, cubuk_onceki, son = False, {}, 0.0
    bagli = {i: True for i in range(4)}
    son_tarama = 0.0
    durum = _DURUM()
    import winsound
    while not durdur.is_set():
        basildi = False
        if vk:
            simdi = bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)
            basildi |= simdi and not tus_onceki
            tus_onceki = simdi
        if xget:
            t = time.time()
            for i in range(4):
                # Bagli olmayan kumandayi sik sorgulamak yavas: 2 sn'de bir dene
                if not bagli[i] and t - son_tarama < 2:
                    continue
                bagli[i] = xget(i, ctypes.byref(durum)) == 0
                ikisi = bagli[i] and (durum.Gamepad.wButtons & IKI_CUBUK) == IKI_CUBUK
                basildi |= ikisi and not cubuk_onceki.get(i, False)
                cubuk_onceki[i] = ikisi
            if t - son_tarama >= 2:
                son_tarama = t
        if basildi and time.time() - son > 2:
            son = time.time()
            zaman = isaret.ekle()
            log.info("isaret: %s", zaman.strftime("%H:%M:%S"))
            try:
                winsound.Beep(1400, 80)
                winsound.Beep(1900, 120)
            except RuntimeError:
                pass
        time.sleep(0.03)


# ---------------------------------------------------------------- kurgu kuyrugu
def _python_exe():
    yol = os.path.join(os.path.dirname(sys.executable), "python.exe")
    return yol if os.path.exists(yol) else sys.executable


def kurgu_isci(ayar, is_kuyrugu):
    while True:
        yol = is_kuyrugu.get()
        try:
            time.sleep(5)  # OBS dosyayi kapatsin
            sure = kayit.sure(yol)
            if sure < ayar["en_kisa_kayit_dk"] * 60:
                log.info("kisa kayit, kurgu yapilmadi: %s (%.1f dk)", yol, sure / 60)
                continue
            bildirim("Kurgu basladi", "%s (%.0f dk). Bitince haber verecegim." % (os.path.basename(yol), sure / 60))
            gunluk = os.path.join(KOK, "izle_kurgu.log")
            with open(gunluk, "a", encoding="utf-8") as f:
                f.write("\n===== %s %s\n" % (datetime.datetime.now().isoformat(timespec="seconds"), yol))
                f.flush()
                r = subprocess.run([_python_exe(), "-m", "studyo", yol], cwd=KOK, stdout=f, stderr=subprocess.STDOUT,
                                   creationflags=_GIZLI, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
            if r.returncode == 0:
                bildirim("Videolar hazir", "Uzun video ve Shorts hazir: cikti klasoru acildi.")
            else:
                bildirim("Kurgu basarisiz", "Ayrinti: izle_kurgu.log")
        except Exception as e:
            log.exception("kurgu hatasi")
            bildirim("Kurgu basarisiz", str(e)[:120])


# ---------------------------------------------------------------- ana dongu
class Bekci:
    def __init__(self, ayar):
        self.ayar = ayar
        self.cl = None
        self.ilk_aktif = None     # uzaktan oynatma sesinin kesintisiz akmaya basladigi an
        self.son_aktif = 0.0
        self.oto = False          # kaydi biz mi baslattik
        self.onceki = None        # geri yuklenecek sahne/ses durumu
        self.elle_durdu = False   # oynarken kullanici kaydi durdurduysa bu oturumda tekrar baslatma
        self.kayitta = False
        self.xbox_kaydi = False   # suren kayit Xbox sahnesinde mi (SCUM vb. elle kayitlar kurguya girmesin)
        self.kuyruk = queue.Queue()

    def _baglanti(self, bekle=0):
        if self.cl is not None:
            try:
                self.cl.get_version()
                return self.cl
            except Exception:
                self.cl = None
        if not obs.calisiyor_mu() and not bekle:
            return None
        try:
            self.cl = obs.baglan(bekle)
        except Exception as e:
            log.debug("OBS'e baglanilamadi: %s", e)
            self.cl = None
        return self.cl

    def kayit_baslat(self):
        cl = self._baglanti()
        if cl is None:
            if not obs.ws_ayarlari().get("server_enabled"):
                log.warning("OBS uzaktan kumandasi kapali: python -m studyo.izle --kur")
                return
            log.info("OBS aciliyor")
            obs.baslat(self.ayar["obs_exe"])
            cl = self._baglanti(bekle=90)
            if cl is None:
                bildirim("OBS'e baglanilamadi", "Kayit baslatilamadi.")
                return
        if obs.kayitta_mi(cl):
            return  # kullanici zaten kaydediyor
        self.onceki = obs.kayda_hazirla(cl)
        cl.start_record()
        self.oto, self.kayitta, self.xbox_kaydi = True, True, True
        log.info("kayit basladi (otomatik)")
        bildirim("Kayit basladi", "Uzaktan oynatma algilandi. Iyi oyunlar! Ani isaretlemek: F9 / iki analoga birlikte bas.")

    def kayit_durdur(self):
        cl = self._baglanti()
        if cl is None:
            return
        try:
            cl.stop_record()
        except Exception as e:
            log.warning("kayit durdurulamadi: %s", e)
        log.info("kayit durduruldu (otomatik)")

    def _kayit_bitti(self, cl):
        """Kayit durdu (otomatik ya da elle): ayarlari geri yukle, kurguyu kuyruga ekle."""
        if self.oto:
            obs.geri_yukle(cl, self.onceki)
        xbox_kaydi = self.xbox_kaydi
        self.oto, self.onceki, self.xbox_kaydi = False, None, False
        if not self.ayar["oto_kurgu"] or not xbox_kaydi:
            return
        try:
            yol = kayit.en_yeni(self.ayar["kayit_klasoru"])
        except SystemExit:
            return
        if time.time() - os.path.getmtime(yol) < 300:
            log.info("kurgu kuyruga eklendi: %s", yol)
            self.kuyruk.put(yol)

    def tur(self):
        simdi = time.time()
        aktif = xbox_sesi_akiyor()
        if aktif:
            self.son_aktif = simdi
            self.ilk_aktif = self.ilk_aktif or simdi
        else:
            self.ilk_aktif = None
        oturum_bitti = simdi - self.son_aktif >= self.ayar["oto_kayit_dur_sn"]
        if oturum_bitti:
            self.elle_durdu = False

        cl = self._baglanti()
        kayitta = False
        if cl is not None:
            try:
                kayitta = obs.kayitta_mi(cl)
            except Exception:
                self.cl, cl = None, None
        if kayitta and not self.kayitta and cl is not None and not self.oto:
            # Elle baslatilan kayit: Xbox sahnesindeyse o da kurgulanir
            sahne = obs._ozellik(cl.get_current_program_scene(), "current_program_scene_name", "scene_name")
            self.xbox_kaydi = sahne == obs.SAHNE
        if self.kayitta and not kayitta and cl is not None:
            if self.oto and not oturum_bitti:
                self.elle_durdu = True  # oynarken elle durduruldu
            self._kayit_bitti(cl)
        self.kayitta = kayitta

        if not self.ayar["oto_kayit"]:
            return
        if (not kayitta and aktif and not self.elle_durdu
                and simdi - self.ilk_aktif >= self.ayar["oto_kayit_basla_sn"]):
            self.kayit_baslat()
        elif kayitta and self.oto and oturum_bitti:
            self.kayit_durdur()

    def calis(self):
        durdur = threading.Event()
        threading.Thread(target=isaret_dinle, args=(self.ayar, durdur), daemon=True).start()
        threading.Thread(target=kurgu_isci, args=(self.ayar, self.kuyruk), daemon=True).start()
        log.info("bekci basladi (oto_kayit=%s, oto_kurgu=%s, isaret=%s%s)", self.ayar["oto_kayit"], self.ayar["oto_kurgu"],
                 self.ayar["isaret_tusu"], " + iki analog" if self.ayar["kumanda_isaret"] else "")
        try:
            while True:
                try:
                    self.tur()
                except Exception:
                    log.exception("dongu hatasi")
                time.sleep(2)
        finally:
            durdur.set()


# ---------------------------------------------------------------- kurulum
def _pythonw():
    yol = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return yol if os.path.exists(yol) else sys.executable


def kur():
    import winreg
    if obs.ws_ac():
        print("[OK] OBS uzaktan kumandasi (websocket) acik")
    else:
        print("[!] OBS acik: kapatip 'python -m studyo.izle --kur' komutunu tekrar calistirin "
              "(ya da OBS > Araclar > WebSocket Sunucusu Ayarlari > Sunucuyu etkinlestir).")
    komut = '"%s" "%s"' % (_pythonw(), os.path.join(KOK, "IZLE.pyw"))
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, BASLANGIC_ANAHTARI, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, BASLANGIC_ADI, 0, winreg.REG_SZ, komut)
    print("[OK] Windows acilisinda arka planda calisacak: %s" % komut)


def kaldir():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, BASLANGIC_ANAHTARI, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, BASLANGIC_ADI)
        print("[OK] Windows acilisindan cikarildi")
    except FileNotFoundError:
        print("Zaten kayitli degil")


def _tek_ornek():
    ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\xbox-auto-youtube-izle")
    return ctypes.windll.kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


def main(argv=None):
    ap = argparse.ArgumentParser(prog="studyo.izle")
    ap.add_argument("--kur", action="store_true")
    ap.add_argument("--kaldir", action="store_true")
    arg = ap.parse_args(argv)
    if arg.kur:
        return kur()
    if arg.kaldir:
        return kaldir()

    isleyiciler = [logging.FileHandler(os.path.join(KOK, "izle.log"), encoding="utf-8")]
    if sys.stdout:
        isleyiciler.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S",
                        handlers=isleyiciler)
    logging.getLogger("obsws_python").setLevel(logging.CRITICAL)
    if not _tek_ornek():
        log.info("bekci zaten calisiyor, cikiliyor")
        return
    Bekci(ayar_modulu.yukle()).calis()


if __name__ == "__main__":
    main()
