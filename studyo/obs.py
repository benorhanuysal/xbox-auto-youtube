"""OBS baglantisi (obs-websocket 5, OBS 28+ ile birlikte gelir).
Port ve sifre OBS'in kendi ayar dosyasindan okunur; ayrica bir yere yazilmaz.
Otomatik kayit icin ayri bir "Xbox (otomatik)" sahnesi kurulur: Xbox penceresi + yalnizca Xbox sesi.
Kullanicinin kendi sahnelerine dokunulmaz; kayit bitince onceki sahne ve ses ayarlari geri yuklenir."""
import json
import os
import subprocess
import time

WS_AYAR = os.path.join(os.environ.get("APPDATA", ""), "obs-studio", "plugin_config", "obs-websocket", "config.json")
SAHNE = "Xbox (otomatik)"
GORUNTU = "Xbox goruntu"
SES = "Xbox ses"
# OBS pencere secimi: "baslik:sinif:exe". Xbox uygulamasi bir UWP; ses ve goruntu exe adiyla eslenir.
XBOX_PENCERE = "XBOX:Windows.UI.Core.CoreWindow:XboxPcApp.exe"
ONCELIK_EXE = 2      # OBS window_priority: 0 sinif, 1 baslik, 2 exe
YONTEM_WGC = 2       # Windows 10 (1903+) yakalama: UWP pencereleri icin gerekli


def ws_ayarlari():
    with open(WS_AYAR, encoding="utf-8-sig") as f:
        return json.load(f)


def calisiyor_mu():
    r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq obs64.exe", "/NH"], capture_output=True, text=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return "obs64.exe" in r.stdout.lower()


def ws_ac():
    """obs-websocket sunucusunu acar. OBS kapaliyken yapilmali (acikken OBS kapanirken eski ayari yazar).
    Donus: True = acildi ya da zaten acik."""
    a = ws_ayarlari()
    if a.get("server_enabled"):
        return True
    if calisiyor_mu():
        return False
    a["server_enabled"] = True
    with open(WS_AYAR, "w", encoding="utf-8") as f:
        json.dump(a, f, indent=4)
    return True


def baslat(obs_exe):
    klasor = os.path.dirname(obs_exe)
    subprocess.Popen([obs_exe, "--minimize-to-tray", "--disable-shutdown-check"], cwd=klasor)


def baglan(zaman_asimi=0):
    """ReqClient dondurur; zaman_asimi > 0 ise OBS acilana kadar bekler."""
    import obsws_python as obsws
    a = ws_ayarlari()
    bitis = time.time() + zaman_asimi
    while True:
        try:
            return obsws.ReqClient(host="localhost", port=a.get("server_port", 4455),
                                   password=a.get("server_password", "") if a.get("auth_required", True) else "",
                                   timeout=5)
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
    return yeni


def _masaustu_sesleri(cl):
    ozel = cl.get_special_inputs()
    adlar = []
    for anahtar, deger in vars(ozel).items():
        if anahtar.startswith("desktop") and deger:
            adlar.append(deger)
    return adlar


def kayda_hazirla(cl):
    """Xbox sahnesine gec, masaustu sesini kapat (Xbox sesi iki kez kaydedilmesin).
    Geri yukleme icin onceki durumu dondurur."""
    xbox_sahnesi(cl)
    onceki = {"sahne": _ozellik(cl.get_current_program_scene(), "current_program_scene_name", "scene_name"),
              "sessiz": {}}
    for ad in _masaustu_sesleri(cl):
        onceki["sessiz"][ad] = cl.get_input_mute(ad).input_muted
        cl.set_input_mute(ad, True)
    cl.set_current_program_scene(SAHNE)
    return onceki


def geri_yukle(cl, onceki):
    if not onceki:
        return
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
