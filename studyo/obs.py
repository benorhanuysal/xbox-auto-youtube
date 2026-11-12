"""OBS baglantisi (obs-websocket 5, OBS 28+ ile birlikte gelir). IKI OBS:
- KAYIT: kurulu OBS (%APPDATA%\\obs-studio). Temiz kayit: ekran + Xbox sesi + mikrofon, YouTube kurgusu buradan.
  Kayit 2 ses kanalli: 1 = karisim, 2 = yalniz mikrofon.
- YAYIN: tasinabilir ikinci OBS (ayar "yayin_obs_klasoru", kendi config klasoru, websocket 4456). Kick yayini:
  ayni goruntu + canli Turkce altyazi + Kick chat + bildirimler. Kayda bunlarin hicbiri girmez.
Port ve sifre her OBS'in kendi ayar dosyasindan okunur; ayrica bir yere yazilmaz.
Kullanicinin kendi sahnelerine dokunulmaz; kayit bitince onceki sahne ve ses ayarlari geri yuklenir."""
import json
import os
import subprocess
import time

KAYIT, YAYIN = "kayit", "yayin"
SAHNE = "Xbox (otomatik)"
GORUNTU = "Xbox goruntu"
SES = "Xbox ses"
MIKROFON = "Mikrofon"
# Yalniz YAYIN OBS'inde (kayit temiz kalir; kurgu kendi duzeltilmis altyazisini gomer):
KATMAN = "Turkce altyazi (yayin)"
KATMAN_HTML = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "yayin", "altyazi.html")
# Kick chat ve takip/abone bildirimleri (BotRix web adresleri, studyo.yayin --katmanlar)
WEB_KATMANLARI = {"chat": "Kick chat (yayin)", "bildirim": "Kick bildirimleri (yayin)"}
# Mola ekrani: sahnenin en altinda; ekran yakalama gizlenince (uzaktan oynatma kesildi) siyah yerine bu gorunur
MOLA = "Mola ekrani (yayin)"
MOLA_HTML = os.path.join(os.path.dirname(KATMAN_HTML), "mola.html")
# Kayit ses kanallari: 1 = videoya giren karisim (oyun + mikrofon), 2 = yalniz mikrofon (kurgu konusmayi bulur)
KANAL_KARISIM, KANAL_MIKROFON = "1", "2"
KAYIT_KANALLARI = "3"  # OBS Basit cikti: bit maskesi, 1|2 = kanal 1 ve 2
# OBS pencere secimi: "baslik:sinif:exe". Xbox uygulamasi bir UWP; ses ve goruntu exe adiyla eslenir.
XBOX_PENCERE = "XBOX:Windows.UI.Core.CoreWindow:XboxPcApp.exe"
ONCELIK_EXE = 2      # OBS window_priority: 0 sinif, 1 baslik, 2 exe
YONTEM_WGC = 2       # Windows 10 (1903+) yakalama: UWP pencereleri icin gerekli


def yayin_kok():
    from . import ayar as ayar_modulu
    return os.path.normcase(os.path.abspath(ayar_modulu.yukle()["yayin_obs_klasoru"]))


def ayar_klasoru(ornek=KAYIT):
    if ornek == YAYIN:
        return os.path.join(yayin_kok(), "config", "obs-studio")  # tasinabilir mod
    return os.path.join(os.environ.get("APPDATA", ""), "obs-studio")


def exe_yolu(ornek, obs_exe=None):
    if ornek == YAYIN:
        return os.path.join(yayin_kok(), "bin", "64bit", "obs64.exe")
    return obs_exe


def ws_ayar_dosyasi(ornek=KAYIT):
    return os.path.join(ayar_klasoru(ornek), "plugin_config", "obs-websocket", "config.json")


def ws_ayarlari(ornek=KAYIT):
    with open(ws_ayar_dosyasi(ornek), encoding="utf-8-sig") as f:
        return json.load(f)


def _surec(ornek=KAYIT):
    """O OBS'in calisan obs64.exe sureci (exe yolundan ayirt edilir) ya da None."""
    import psutil
    kok = yayin_kok()
    for p in psutil.process_iter(["name", "exe"]):
        if (p.info.get("name") or "").lower() != "obs64.exe":
            continue
        yayin_mi = os.path.normcase(p.info.get("exe") or "").startswith(kok + os.sep)
        if yayin_mi == (ornek == YAYIN):
            return p
    return None


def calisiyor_mu(ornek=KAYIT):
    return _surec(ornek) is not None


def ws_ac():
    """Kayit OBS'inin websocket sunucusunu acar. OBS kapaliyken yapilmali (acikken OBS kapanirken eski ayari yazar).
    Donus: True = acildi ya da zaten acik."""
    a = ws_ayarlari()
    if a.get("server_enabled"):
        return True
    if calisiyor_mu():
        return False
    a["server_enabled"] = True
    with open(ws_ayar_dosyasi(), "w", encoding="utf-8") as f:
        json.dump(a, f, indent=4)
    return True


def _eski_calisma_izlerini_sil(ornek=KAYIT):
    """OBS her acilista .sentinel/run_* dosyasi birakir, duzgun kapaninca siler. Dosya kalmissa (PC kapandi,
    OBS kapatildi) bir sonraki acilista "Guvenli modda baslat?" sorulur; bekci acarken Guvenli Mod secilirse
    eklentiler, dolayisiyla websocket kapali kalir ve otomatik kayit baslayamaz. OBS calismiyorsa bu izler eskidir."""
    klasor = os.path.join(ayar_klasoru(ornek), ".sentinel")
    if calisiyor_mu(ornek) or not os.path.isdir(klasor):
        return
    for ad in os.listdir(klasor):
        if ad.startswith("run_"):
            try:
                os.remove(os.path.join(klasor, ad))
            except OSError:
                pass


def baslat(obs_exe=None, ornek=KAYIT):
    """--multi: iki OBS ayni anda calisirken 'OBS zaten acik' uyarisi cikmasin."""
    exe = exe_yolu(ornek, obs_exe)
    _eski_calisma_izlerini_sil(ornek)  # OBS 30+ --disable-shutdown-check'e ragmen Guvenli Mod soruyor
    subprocess.Popen([exe, "--multi", "--minimize-to-tray", "--disable-shutdown-check"], cwd=os.path.dirname(exe))


def kapat(ornek, bekle=60):
    """Duzgun kapanis (ayarlar kaydedilir, Guvenli Mod izi kalmaz). Tepsideki OBS WM_CLOSE'u 'gizle' sayar:
    once ana pencere gorunur yapilir, sonra kapatilir (menuden Cikis gibi). Tarayici kaynaklari varken kapanis
    20 sn'yi gecebiliyor. Donus: kapandi mi."""
    import ctypes
    import ctypes.wintypes as wt
    p = _surec(ornek)
    if p is None:
        return True
    u = ctypes.windll.user32
    bulunan = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def tara(h, _):
        pid = wt.DWORD()
        u.GetWindowThreadProcessId(h, ctypes.byref(pid))
        if pid.value == p.pid:
            n = u.GetWindowTextLengthW(h)
            b = ctypes.create_unicode_buffer(n + 1)
            u.GetWindowTextW(h, b, n + 1)
            if b.value.startswith("OBS ") and " - " in b.value:
                bulunan.append(h)
        return True

    u.EnumWindows(tara, 0)
    if not bulunan:
        return False
    u.ShowWindow(bulunan[0], 5)
    time.sleep(0.7)
    u.PostMessageW(bulunan[0], 0x0010, 0, 0)  # WM_CLOSE
    bitis = time.time() + bekle
    while time.time() < bitis:
        if not p.is_running():
            return True
        time.sleep(0.5)
    return False


def baglan(zaman_asimi=0, ornek=KAYIT):
    """ReqClient dondurur; zaman_asimi > 0 ise OBS acilana (ve istek kabul edene) kadar bekler."""
    import obsws_python as obsws
    a = ws_ayarlari(ornek)
    bitis = time.time() + zaman_asimi
    while True:
        try:
            cl = obsws.ReqClient(host="localhost", port=a.get("server_port", 4455),
                                 password=a.get("server_password", "") if a.get("auth_required", True) else "",
                                 timeout=5)
            cl.get_version()  # acilirken baglanti kabul edilir ama istekler 207 "hazir degil" doner
            return cl
        except Exception:
            if time.time() >= bitis:
                raise
            time.sleep(2)


def _ozellik(yanit, *adlar):
    for ad in adlar:
        if hasattr(yanit, ad):
            return getattr(yanit, ad)
    return None


def _sigdir(cl, kaynak):
    """Kaynagi tuvale sigdir (ekran 4K, tuval 1080p olsa da)."""
    v = cl.get_video_settings()
    w, h = _ozellik(v, "base_width"), _ozellik(v, "base_height")
    oge = _ozellik(cl.get_scene_item_id(SAHNE, kaynak), "scene_item_id")
    if w and h and oge is not None:
        cl.set_scene_item_transform(SAHNE, oge, {
            "positionX": 0, "positionY": 0, "alignment": 5,
            "boundsType": "OBS_BOUNDS_SCALE_INNER", "boundsWidth": w, "boundsHeight": h, "boundsAlignment": 0,
        })


def _goruntu_kur(cl):
    """Ekran yakalama. Uzaktan oynatma tam ekran acilir ama penceresi Windows'un pencere listesinde
    gorunmez; OBS'in pencere yakalamasi bu yuzden siyah kaydeder. Ekranin tamami ise oyunu gorur."""
    try:
        tur = _ozellik(cl.get_input_settings(GORUNTU), "input_kind")
    except Exception:
        tur = None
    if tur is not None and tur != "monitor_capture":
        cl.remove_input(GORUNTU)  # eski surumdeki pencere yakalama
        time.sleep(0.5)
        tur = None
    if tur is None:
        cl.create_input(SAHNE, GORUNTU, "monitor_capture", {"method": 0, "capture_cursor": False}, True)
        _sigdir(cl, GORUNTU)
    if cl.get_input_settings(GORUNTU).input_settings.get("monitor_id", "DUMMY") == "DUMMY":
        # Ilk secenek "Yakalanacak bir ekran secin" yer tutucusu (DUMMY); birincil ekrani sec
        ekranlar = [e for e in cl.get_input_properties_list_property_items(GORUNTU, "monitor_id").property_items
                    if e.get("itemValue") not in (None, "", "DUMMY") and e.get("itemEnabled", True)]
        birincil = [e for e in ekranlar if "@ 0,0" in (e.get("itemName") or "")]
        if ekranlar:
            cl.set_input_settings(GORUNTU, {"monitor_id": (birincil or ekranlar)[0]["itemValue"]}, True)


def xbox_sahnesi(cl):
    """Sahneyi kurar ya da eski surumden gunceller (tekrar cagirmak guvenli)."""
    sahneler = [s["sceneName"] for s in cl.get_scene_list().scenes]
    yeni = SAHNE not in sahneler
    if yeni:
        cl.create_scene(SAHNE)
        cl.create_input(SAHNE, SES, "wasapi_process_output_capture",
                        {"window": XBOX_PENCERE, "priority": ONCELIK_EXE}, True)
    _goruntu_kur(cl)
    _mikrofon_kur(cl)
    return yeni


def _mola_kur(cl, gorsel=None):
    """Sahnenin en altina mola ekrani (tam ekran, opak ekran yakalamanin arkasinda kalir)."""
    url = "file:///" + MOLA_HTML.replace("\\", "/")
    if gorsel and os.path.exists(gorsel):
        url += "?gorsel=" + "file:///" + gorsel.replace("\\", "/")
    ayar = {"is_local_file": False, "url": url, "width": 1920, "height": 1080, "shutdown": False,
            "restart_when_active": False, "reroute_audio": False}
    try:
        cl.get_input_settings(MOLA)
        cl.set_input_settings(MOLA, ayar, True)
    except Exception:
        cl.create_input(SAHNE, MOLA, "browser_source", ayar, True)
        time.sleep(0.5)
        _sigdir(cl, MOLA)
    cl.set_scene_item_index(SAHNE, _oge(cl, MOLA), 0)
    cl.set_scene_item_enabled(SAHNE, _oge(cl, MOLA), True)


def yayin_sahnesi(cl, web=None, chat_kutusu=None, mola_gorseli=None):
    """YAYIN OBS'i: kayit sahnesinin aynisi + canli altyazi + Kick chat/bildirimleri, hepsi hep acik; en altta
    mola ekrani. Genel masaustu ve Mic/Aux sesleri kalici olarak kapali (Xbox sesi ve mikrofon sahnede; PC'nin
    bip/bildirim sesleri yayina girmesin). web: {"chat": url, "bildirim": url}."""
    xbox_sahnesi(cl)
    _mola_kur(cl, mola_gorseli)
    _katman_kur(cl, gorunur=True)
    for tur, url in (web or {}).items():
        if tur in WEB_KATMANLARI:
            web_katmani_kur(cl, tur, url, chat_kutusu if tur == "chat" else None, gorunur=True)
    for ad in _ozel_sesler(cl, "desktop") + _ozel_sesler(cl, "mic"):
        cl.set_input_mute(ad, True)
    cl.set_current_program_scene(SAHNE)
    ekran_goster(cl, True)


def katmanlari_kaldir(cl):
    """KAYIT OBS'inden yayin katmanlarini sil (eski surumde oradaydi)."""
    silinen = []
    for ad in [KATMAN, MOLA] + list(WEB_KATMANLARI.values()):
        try:
            cl.remove_input(ad)
            silinen.append(ad)
        except Exception:
            pass
    return silinen


def _oge(cl, kaynak):
    return _ozellik(cl.get_scene_item_id(SAHNE, kaynak), "scene_item_id")


def _katman_kur(cl, gorunur=False):
    """Tarayici kaynagi. Her cagrida dosya yolu, gorunurlugu ve en ustte olmasi tazelenir."""
    ayar = {"is_local_file": True, "local_file": KATMAN_HTML, "width": 1920, "height": 1080,
            "shutdown": False, "restart_when_active": False, "reroute_audio": False, "css": ""}
    try:
        cl.get_input_settings(KATMAN)
        cl.set_input_settings(KATMAN, ayar, True)
    except Exception:
        cl.create_input(SAHNE, KATMAN, "browser_source", ayar, gorunur)
        time.sleep(0.5)
        _sigdir(cl, KATMAN)
    ogeler = cl.get_scene_item_list(SAHNE).scene_items
    cl.set_scene_item_index(SAHNE, _oge(cl, KATMAN), len(ogeler) - 1)
    cl.set_scene_item_enabled(SAHNE, _oge(cl, KATMAN), gorunur)


def katman_goster(cl, acik):
    """Turkce altyazi + (kuruluysa) Kick chat ve bildirimleri."""
    cl.set_scene_item_enabled(SAHNE, _oge(cl, KATMAN), bool(acik))
    for ad in WEB_KATMANLARI.values():
        try:
            cl.set_scene_item_enabled(SAHNE, _oge(cl, ad), bool(acik))
        except Exception:
            pass  # kurulmamis


def web_katmani_kur(cl, tur, url, kutu=None, gorunur=False):
    """BotRix gibi bir web adresini sahneye koyar. kutu [x, y, g, y] (1920x1080) yoksa tam ekran.
    Bildirim sesleri OBS'e alinir (reroute_audio) ve YALNIZ 1. kanala (videoya giren karisim) gider:
    2. kanal mikrofon kanali; oraya girse kurgu bildirim sesini 'konusma' sanardi."""
    ad = WEB_KATMANLARI[tur]
    x, y, g, h = kutu or (0, 0, 1920, 1080)
    ayar = {"is_local_file": False, "url": url, "width": g, "height": h, "reroute_audio": True,
            "shutdown": False, "restart_when_active": False}
    try:
        cl.get_input_settings(ad)
        cl.set_input_settings(ad, ayar, True)
    except Exception:
        cl.create_input(SAHNE, ad, "browser_source", ayar, False)
        time.sleep(0.5)
    cl.set_input_audio_tracks(ad, _kanallar((KANAL_KARISIM,)))
    oge = _oge(cl, ad)
    cl.set_scene_item_transform(SAHNE, oge, {"positionX": x, "positionY": y, "alignment": 5,
                                             "scaleX": 1.0, "scaleY": 1.0, "boundsType": "OBS_BOUNDS_NONE"})
    # Altyazinin altinda, oyunun ustunde
    ogeler = cl.get_scene_item_list(SAHNE).scene_items
    cl.set_scene_item_index(SAHNE, oge, max(0, len(ogeler) - 2))
    cl.set_scene_item_index(SAHNE, _oge(cl, KATMAN), len(ogeler) - 1)
    cl.set_scene_item_enabled(SAHNE, oge, gorunur)


def ekran_goster(cl, acik):
    """Yayinda uzaktan oynatma kapaninca masaustu izleyiciye gorunmesin: ekran yakalamayi gizle."""
    cl.set_scene_item_enabled(SAHNE, _oge(cl, GORUNTU), bool(acik))


def yayinda_mi(cl):
    return bool(cl.get_stream_status().output_active)


def _kanallar(acik):
    return {str(i): str(i) in acik for i in range(1, 7)}


def _mikrofon_kur(cl):
    """Windows'un varsayilan kayit aygiti (takilinca HyperX QuadCast). Aygit yoksa OBS sessizce bos kaydeder.
    Gurultu bastirma (RNNoise) fan/klavye sesini temizler; oyun sesi zaten ayri kaynaktan geliyor."""
    try:
        cl.get_input_settings(MIKROFON)
    except Exception:
        cl.create_input(SAHNE, MIKROFON, "wasapi_input_capture", {"device_id": "default"}, True)
        time.sleep(0.5)
    filtreler = [f.get("filterName") for f in (cl.get_source_filter_list(MIKROFON).filters or [])]
    if "Gurultu bastirma" not in filtreler:
        cl.create_source_filter(MIKROFON, "Gurultu bastirma", "noise_suppress_filter_v2", {"method": "rnnoise"})
    cl.set_input_audio_tracks(MIKROFON, _kanallar((KANAL_KARISIM, KANAL_MIKROFON)))
    cl.set_input_audio_tracks(SES, _kanallar((KANAL_KARISIM,)))


def _ozel_sesler(cl, onek):
    """OBS'in genel ses kaynaklari: desktop1/2 (masaustu), mic1-4 (Mic/Aux)."""
    ozel = cl.get_special_inputs()
    return [deger for anahtar, deger in vars(ozel).items() if anahtar.startswith(onek) and deger]


def kayda_hazirla(cl, mikrofon=True):
    """Xbox sahnesine gec; genel masaustu ve Mic/Aux seslerini kapat (oyun sesi ve mikrofon iki kez
    kaydedilmesin; sahnede kendi kaynaklari var). Kayit 2 ses kanalli olur. Onceki durumu dondurur."""
    xbox_sahnesi(cl)
    onceki = {"sahne": _ozellik(cl.get_current_program_scene(), "current_program_scene_name", "scene_name"),
              "sessiz": {}, "kanallar": None}
    for ad in _ozel_sesler(cl, "desktop") + _ozel_sesler(cl, "mic"):
        onceki["sessiz"][ad] = cl.get_input_mute(ad).input_muted
        cl.set_input_mute(ad, True)
    onceki["sessiz"][MIKROFON] = cl.get_input_mute(MIKROFON).input_muted
    cl.set_input_mute(MIKROFON, not mikrofon)
    try:
        eski = _ozellik(cl.get_profile_parameter("SimpleOutput", "RecTracks"), "parameter_value")
        if eski != KAYIT_KANALLARI:
            cl.set_profile_parameter("SimpleOutput", "RecTracks", KAYIT_KANALLARI)
            onceki["kanallar"] = eski
    except Exception:
        pass  # kayit tek kanalli olur: kurgu yine calisir, yalniz konusma algilama atlanir
    cl.set_current_program_scene(SAHNE)
    return onceki


def geri_yukle(cl, onceki):
    if not onceki:
        return
    if onceki.get("kanallar"):
        try:
            cl.set_profile_parameter("SimpleOutput", "RecTracks", onceki["kanallar"])
        except Exception:
            pass
    for ad, sessiz in onceki.get("sessiz", {}).items():
        try:
            cl.set_input_mute(ad, sessiz)
        except Exception:
            pass
    if onceki.get("sahne") and onceki["sahne"] != SAHNE:
        try:
            cl.set_current_program_scene(onceki["sahne"])
        except Exception:
            pass


def kayitta_mi(cl):
    return bool(cl.get_record_status().output_active)
