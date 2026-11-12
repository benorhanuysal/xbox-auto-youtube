"""Arka plan bekcisi: oyna, gerisini o yapsin.
- Xbox uzaktan oynatma baslayinca (Xbox uygulamasinin sesi akmaya baslayinca) OBS kaydini baslatir,
  uzaktan oynatma kapaninca durdurur. OBS kapaliysa simge durumunda acar.
- Kayit durunca (otomatik ya da elle) kurguyu baslatir; bitince Windows bildirimi gelir.
- Isaret: klavyede F9 ya da kumandada iki analog cubuga birlikte basmak o ani isaretler;
  isaretli anlar videoya mutlaka girer.
- Kick yayini: uzaktan oynatma acikken Telegram kumandasindan (studyo/telegram.py) acilir/kapanir. Yayinda Turkce
  altyazi katmani goruntude olur, bildirimler ekran yerine yalniz telefona gider, oynatma kesilince ekran gizlenir,
  oturum bitince yayin kapanir.
- Telegram: isaretle, yayin ac/kapa, durum, mikrofon dugmeleri; bekcinin tum bildirimleri telefona da gelir.

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

from . import ayar as ayar_modulu, isaret, kayit, obs, telegram, yayin

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


SESSIZ = threading.Event()  # yayindayken: bildirim ekrana (dolayisiyla yayina) dusmesin, yalniz gunluge


def bildirim(baslik, metin):
    log.info("bildirim%s: %s - %s", " (yayinda, ekranda gosterilmedi)" if SESSIZ.is_set() else "", baslik, metin)
    # Telefona her zaman (ekrana dusmez, yayina girmez); arka planda: ag yavassa bekci beklemesin
    threading.Thread(target=telegram.gonder, args=("%s\n%s" % (baslik, metin),), daemon=True).start()
    if SESSIZ.is_set():
        return
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


def luna_acik_mi():
    r = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, errors="replace",
                       creationflags=_GIZLI)
    return "lunatranslator" in r.stdout.lower()


def luna_calistir(ayar):
    """LunaTranslator kapaliysa acar: TV altyazisi da yayin katmani da onun yerel servisine baglanir."""
    klasor = os.path.dirname(ayar.get("luna_userconfig") or "")
    exe = os.path.join(klasor, "LunaTranslator.exe")
    if not os.path.exists(exe) or luna_acik_mi():
        return
    log.info("LunaTranslator kapaliydi, aciliyor")
    subprocess.Popen([exe], cwd=klasor)


def _bip(tur):
    """Yayin tusu geri bildirimi (PC hoparlorunden; kayda/yayina girmez, orada yalniz Xbox sesi var)."""
    import winsound
    sesler = {"ac": [(800, 90), (1200, 90), (1600, 140)], "kapa": [(1600, 90), (1200, 90), (800, 140)],
              "hata": [(400, 180), (400, 180)], "isaret": [(1400, 80), (1900, 120)]}
    try:
        for frekans, sure in sesler[tur]:
            winsound.Beep(frekans, sure)
    except RuntimeError:
        pass


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


def isaret_dinle(ayar, durdur, istekler=None):
    vk = _tus_kodu(ayar["isaret_tusu"])
    vk_yayin = _tus_kodu(ayar.get("yayin_tusu")) if istekler is not None else None
    xget = _xinput() if ayar["kumanda_isaret"] else None
    tus_onceki, cubuk_onceki, son = False, {}, 0.0
    yayin_onceki, yayin_son = False, 0.0
    bagli = {i: True for i in range(4)}
    son_tarama = 0.0
    durum = _DURUM()
    import winsound
    while not durdur.is_set():
        if vk_yayin:
            simdi = bool(ctypes.windll.user32.GetAsyncKeyState(vk_yayin) & 0x8000)
            if simdi and not yayin_onceki and time.time() - yayin_son > 3:
                yayin_son = time.time()
                istekler.put("yayin")  # OBS islemi ana dongude (tek baglanti, sirali)
            yayin_onceki = simdi
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
        if SESSIZ.is_set():
            # Yayin suruyor: kurgu GPU kodlayicisini ve (yuklemede) upload'u yayinla paylasmasin
            log.info("yayin suruyor, kurgu yayin bitince yapilacak: %s", os.path.basename(yol))
            while SESSIZ.is_set():
                time.sleep(20)
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


# ---------------------------------------------------------------- YouTube: haftalik rapor, yeni yorum bildirimi
def _iso(metin):
    try:
        return datetime.datetime.fromisoformat(metin)
    except (TypeError, ValueError):
        return None


def youtube_isci(ayar, durdur):
    """10 dakikada bir: rapor zamani geldiyse raporu cikar, yorum kontrol zamani geldiyse yeni yorumlari say."""
    from . import youtube
    while not durdur.wait(600 if ayar["youtube_yukle"] else 3600):
        if not ayar["youtube_yukle"]:
            continue
        try:
            if not youtube.tam_izin_var_mi():
                continue
            simdi = datetime.datetime.now().astimezone()
            d = youtube.durum_oku()
            # Haftalik rapor: en az bir video 2 gundur yayindaysa (Analytics ~2 gun gecikmeli)
            son = _iso(d.get("son_rapor")) or _iso(d.get("son_rapor_deneme"))
            eski_video = any((_iso(v.get("yukleme")) or simdi) <= simdi - datetime.timedelta(days=2) for v in d["videolar"])
            if eski_video and (son is None or simdi - son >= datetime.timedelta(days=ayar["rapor_gun"])):
                d["son_rapor_deneme"] = simdi.isoformat(timespec="seconds")
                youtube.durum_yaz(d)
                log.info("haftalik rapor hazirlaniyor")
                r = subprocess.run([_python_exe(), "-m", "studyo.rapor", "--arka-plan"], cwd=KOK, creationflags=_GIZLI,
                                   capture_output=True, text=True, encoding="utf-8", errors="replace",
                                   env=dict(os.environ, PYTHONIOENCODING="utf-8"))
                if r.returncode == 0:
                    bildirim("Haftalik kanal raporu hazir", "RAPOR.bat ya da cikti\\raporlar. Dersler bir sonraki kurguya aktarildi.")
                else:
                    log.warning("rapor hatasi: %s", (r.stdout + r.stderr)[-300:])
            # Yeni yorumlar
            d = youtube.durum_oku()
            son = _iso(d.get("son_yorum_kontrol"))
            if son is None or simdi - son >= datetime.timedelta(hours=ayar["yorum_kontrol_saat"]):
                from . import yorumlar
                sayi = len(yorumlar.yeniler())
                d = youtube.durum_oku()
                d["son_yorum_kontrol"] = simdi.isoformat(timespec="seconds")
                if sayi and sayi != d.get("son_yorum_bildirimi"):
                    bildirim("%d yeni YouTube yorumu" % sayi, "Cevaplamak icin YORUMLAR.bat (Claude taslak yazar, sen onaylarsin).")
                d["son_yorum_bildirimi"] = sayi
                youtube.durum_yaz(d)
        except Exception:
            log.exception("youtube gorevi hatasi")


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
        self.istekler = queue.Queue()  # tus dinleyiciden: "yayin"
        self.yayinda = False
        self.yayin_oto = False    # yayini biz mi actik (oturum bitince biz kapatiriz)
        self.ekran_gizli = False
        self.ertelenen = None     # yayin surerken kayit biterse sahne geri yuklemesi yayin sonuna kalir
        self.yayin_istendi = None # start_stream zamani: yayin bu surede baslamazsa haber ver

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
        self.onceki = obs.kayda_hazirla(cl, self.ayar.get("mikrofon_kaydi", True))
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
            if self.yayinda:
                self.ertelenen = self.onceki  # sahne simdi degisirse yayinda baska sahne gorunur
            else:
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

    # ------------------------------------------------------------ Kick yayini
    def yayin_ac(self, aktif):
        """Donus: kullaniciya (Telegram) gidecek kisa metin."""
        cl = self._baglanti()
        if cl is not None and obs.yayinda_mi(cl):
            return "Zaten yayındasın 🔴"
        if not aktif:
            _bip("hata")
            return "Yayın açılmadı: önce Xbox uzaktan oynatmayı aç. Oyun ekranı yokken yayın açılmaz (masaüstü görünmesin)."
        SESSIZ.set()  # "Kayit basladi" bildirimi de ekrana dusmesin
        if not self.kayitta:
            self.kayit_baslat()  # sahneyi (goruntu, Xbox sesi, mikrofon) kurar; yayinin kaydi da olsun
        cl = self._baglanti()
        if cl is None or not yayin.ayarli_mi(cl):
            SESSIZ.clear()
            _bip("hata")
            return "Kick ayarlı değil: YAYIN_KUR.bat ile yayın adresini ve anahtarını gir."
        cl.set_current_program_scene(obs.SAHNE)
        obs.ekran_goster(cl, True)
        obs.katman_goster(cl, True)
        cl.start_stream()
        self.yayin_oto, self.yayin_istendi = True, time.time()
        log.info("yayin baslatiliyor")
        _bip("ac")
        return "Yayın başlatılıyor... Kick'e bağlanınca haber vereceğim."

    def yayin_kapa(self):
        cl = self._baglanti()
        if cl is None or not obs.yayinda_mi(cl):
            return "Zaten yayında değilsin."
        cl.stop_stream()
        log.info("yayin kapatiliyor")
        _bip("kapa")
        return "⏹ Yayın kapatılıyor."

    def yayin_ac_kapa(self, aktif):
        """Klavye tusu (yayin_tusu ayarliysa)."""
        cl = self._baglanti()
        log.info(self.yayin_kapa() if cl is not None and obs.yayinda_mi(cl) else self.yayin_ac(aktif))

    def mikrofon_degistir(self):
        cl = self._baglanti()
        if cl is None:
            return "OBS kapalı; mikrofon kayıt başlayınca açılır."
        try:
            sessiz = not cl.get_input_mute(obs.MIKROFON).input_muted
            cl.set_input_mute(obs.MIKROFON, sessiz)
        except Exception:
            return "OBS'te mikrofon kaynağı yok (ilk otomatik kayıtta kurulur)."
        log.info("mikrofon %s (telegram)", "kapatildi" if sessiz else "acildi")
        return "🎙 Mikrofon KAPALI 🔇" if sessiz else "🎙 Mikrofon AÇIK"

    def durum_metni(self, aktif):
        satirlar = ["🎮 Uzaktan oynatma: %s" % ("açık" if aktif else "kapalı")]
        cl = self._baglanti()
        if cl is None:
            satirlar.append("OBS: kapalı")
        else:
            try:
                k = cl.get_record_status()
                satirlar.append("⏺ Kayıt: %s" % ("sürüyor (%d dk)" % (k.output_duration / 60000) if k.output_active else "yok"))
                y = cl.get_stream_status()
                satirlar.append("🔴 Yayın: %s" % ("AÇIK (%d dk)" % (y.output_duration / 60000) if y.output_active else "kapalı"))
                satirlar.append("🎙 Mikrofon: %s" % ("kapalı 🔇" if cl.get_input_mute(obs.MIKROFON).input_muted else "açık"))
            except Exception as e:
                satirlar.append("OBS: %s" % str(e)[:80])
        satirlar.append("🈯 Luna (altyazı): %s" % ("açık" if luna_acik_mi() else "kapalı"))
        if self.kuyruk.qsize():
            satirlar.append("🎬 Kurgu kuyruğu: %d kayıt" % self.kuyruk.qsize())
        return "\n".join(satirlar)

    def istek_isle(self, eylem, zaman, aktif):
        if eylem == "yayin":  # klavye
            return self.yayin_ac_kapa(aktif)
        log.info("telegram tusu: %s", eylem)
        if eylem == "yayin_ac":
            cevap = self.yayin_ac(aktif)
        elif eylem == "yayin_kapa":
            cevap = self.yayin_kapa()
        elif eylem == "isaret":
            z = isaret.ekle(zaman)
            log.info("isaret (telegram): %s", z.strftime("%H:%M:%S"))
            _bip("isaret")
            cevap = ("⭐ İşaretlendi (%s). O anın son ~25 sn'si videoya girecek." % z.strftime("%H:%M:%S")
                     if self.kayitta else "⭐ İşaretlendi ama şu an kayıt yok; kayıt başlayınca işe yarar.")
        elif eylem == "durum":
            cevap = self.durum_metni(aktif)
        elif eylem == "mikrofon":
            cevap = self.mikrofon_degistir()
        else:
            cevap = telegram.YARDIM
        telegram.gonder(cevap)

    def _yayin_degisti(self, cl, yayinda):
        self.yayinda = yayinda
        yayin.olay_yaz("BASLA" if yayinda else "BITTI")
        yayin.bayrak(yayinda)
        log.info("yayin %s", "basladi" if yayinda else "bitti")
        try:
            obs.katman_goster(cl, yayinda)
        except Exception as e:
            log.warning("altyazi katmani ayarlanamadi: %s", e)
        if yayinda:
            SESSIZ.set()
            self.yayin_istendi = None
            bildirim("🔴 Yayın başladı", "Kick'te canlısın, Türkçe altyazı katmanı açık.")
            return
        SESSIZ.clear()
        self.yayin_oto = False
        if self.ekran_gizli:
            obs.ekran_goster(cl, True)
            self.ekran_gizli = False
        if self.ertelenen is not None:
            obs.geri_yukle(cl, self.ertelenen)
            self.ertelenen = None
        bildirim("Yayin bitti", "Kick yayini kapandi.")

    def _yayin_turu(self, cl, simdi, oturum_bitti):
        try:
            yayinda = obs.yayinda_mi(cl)
        except Exception:
            return
        if yayinda != self.yayinda:
            self._yayin_degisti(cl, yayinda)
        if not yayinda:
            if self.yayin_istendi and simdi - self.yayin_istendi > 30:
                self.yayin_istendi, self.yayin_oto = None, False
                SESSIZ.clear()
                try:
                    obs.katman_goster(cl, False)
                except Exception:
                    pass
                bildirim("Yayın başlamadı", "OBS 30 sn'de Kick'e bağlanamadı (anahtar ya da internet). Tekrar dene.")
            return
        gizle = simdi - self.son_aktif >= self.ayar["yayin_ekran_gizle_sn"]
        if gizle != self.ekran_gizli:
            try:
                obs.ekran_goster(cl, not gizle)
                self.ekran_gizli = gizle
                log.info("yayinda ekran %s", "gizlendi (uzaktan oynatma kesildi)" if gizle else "geri acildi")
            except Exception as e:
                log.warning("ekran gizlenemedi: %s", e)
        if self.yayin_oto and oturum_bitti:
            cl.stop_stream()
            log.info("yayin kapatiliyor (uzaktan oynatma bitti)")

    def tur(self):
        simdi = time.time()
        aktif = xbox_sesi_akiyor()
        if aktif:
            if self.ilk_aktif is None and self.ayar.get("luna_oto_baslat", True):
                luna_calistir(self.ayar)  # oynatma yeni basladi
            self.son_aktif = simdi
            self.ilk_aktif = self.ilk_aktif or simdi
        else:
            self.ilk_aktif = None
        while not self.istekler.empty():
            istek = self.istekler.get_nowait()
            eylem, zaman = istek if isinstance(istek, tuple) else (istek, None)
            try:
                self.istek_isle(eylem, zaman, aktif)
            except Exception as e:
                log.exception("istek hatasi: %s", eylem)
                telegram.gonder("⚠️ %s yapılamadı: %s" % (eylem, str(e)[:150]))
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
        if cl is not None:
            self._yayin_turu(cl, simdi, oturum_bitti)

        if not self.ayar["oto_kayit"]:
            return
        if (not kayitta and aktif and not self.elle_durdu
                and simdi - self.ilk_aktif >= self.ayar["oto_kayit_basla_sn"]):
            self.kayit_baslat()
        elif kayitta and self.oto and oturum_bitti:
            self.kayit_durdur()

    def calis(self):
        durdur = threading.Event()
        yayin.acik_kalani_kapat()
        yayin.bayrak(False)  # onceki calismadan kalmissa; yayin suruyorsa ilk tur yeniden koyar
        threading.Thread(target=isaret_dinle, args=(self.ayar, durdur, self.istekler), daemon=True).start()
        threading.Thread(target=kurgu_isci, args=(self.ayar, self.kuyruk), daemon=True).start()
        threading.Thread(target=youtube_isci, args=(self.ayar, durdur), daemon=True).start()
        if telegram.hazir_mi():
            threading.Thread(target=telegram.dinle, args=(self.istekler, durdur), daemon=True).start()
        log.info("bekci basladi (oto_kayit=%s, oto_kurgu=%s, isaret=%s%s, yayin tusu=%s, telegram=%s)",
                 self.ayar["oto_kayit"], self.ayar["oto_kurgu"], self.ayar["isaret_tusu"],
                 " + iki analog" if self.ayar["kumanda_isaret"] else "", self.ayar.get("yayin_tusu") or "yok",
                 "acik" if telegram.hazir_mi() else "kurulmadi")
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
