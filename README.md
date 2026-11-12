# xbox-auto-youtube

**Oyun kaydından otomatik YouTube videosu + Shorts — Türkçe altyazılı.**

OBS ile kaydettiğin oyun oturumunu alır; heyecanlı anları ve diyalogları bulur, yapay zekâya (Claude ya da Gemini) kurgu planı yaptırır, Türkçe altyazıyı gömerek **uzun video** ve **dikey Shorts** üretir, başlık/açıklama/etiketleri de yazar.

Türkçe altyazılar [xbox-samsung-subtitles-tv](https://github.com/benorhanuysal/xbox-samsung-subtitles-tv) sisteminin çeviri günlüğünden gelir: oynarken TV'de gördüğün altyazılar videoya da aynen girer.

> 🇬🇧 **English:** Turns an OBS gameplay recording into an edited long video and vertical Shorts. It finds exciting moments from the audio (gunfights, crashes, shouting) and dialogue clusters from the live subtitle log, lets Claude (via the local Claude Code CLI and your subscription, with scene frame strips) or Gemini pick scenes and write Turkish titles/descriptions, burns in Turkish subtitles and renders with NVENC/QSV/x264 via ffmpeg. Run `KUR.bat` once, then `YAP.bat` after each session.

## Nasıl çalışır

```
OBS kaydı (.mkv) ──┬─> ses analizi: çevresinden belirgin yüksek anlar (çatışma, kaza, bağırış)
                   ├─> altyazi_ceviri.log: hangi saniyede hangi diyalog (Türkçe + İngilizce)
                   │
                   └─> aday sahneler (+ kare şeritleri) ──> Claude / Gemini: uzun video + Shorts planı, başlık, açıklama, etiketler
                                              │
                                              └─> ffmpeg: kes, 9:16 düzen, Türkçe altyazı gömme, geçişler
                                                     │
                                                     └─> cikti/<kayit>/ uzun.mp4, short_1.mp4..., kapak, yükleme bilgisi
```

- **Planlayıcı sırası** `ayarlar.json`'daki `planlayicilar` listesidir (varsayılan: önce Claude, sonra Gemini). Hiçbiri olmazsa puana göre basit plan yapılır; video her durumda çıkar.
- **Claude:** bilgisayardaki [Claude Code](https://claude.com/claude-code) arka planda (`claude -p`) çalıştırılır ve **Claude aboneliğinle** cevap verir, ayrıca API ücreti yok. En yüksek puanlı 30 sahnenin 3'er karelik şeridini kendisi okur; yani sadece sese ve diyaloğa değil, ekranda olana da bakarak seçer. Kullanım limitin dolarsa sıra Gemini'ye geçer.
- **Gemini:** yalnızca metin gider (sahne zamanları, ses ölçümü, diyaloglar); ücretsiz kota yeter. Meşgulse (503) birkaç kez bekleyip tekrar dener.
- Ekran kartı kodlayıcısı otomatik seçilir: NVIDIA (NVENC) → Intel (QSV) → işlemci (x264).

## Gereksinimler
- Windows 10/11, [OBS Studio](https://obsproject.com/)
- Python 3.10+ ve ffmpeg (`KUR.bat` kurar)
- Planlayıcı (biri yeter): [Claude Code](https://claude.com/claude-code) kurulu ve Claude hesabıyla giriş yapılmış, ve/veya Gemini API anahtarı ([Google AI Studio](https://aistudio.google.com/apikey), ücretsiz; altyazı sistemi kuruluysa oradaki anahtar kullanılır).
- İsteğe bağlı: [xbox-samsung-subtitles-tv](https://github.com/benorhanuysal/xbox-samsung-subtitles-tv) (Türkçe altyazı için)

## Kurulum
1. Repoyu indir (Code → Download ZIP ya da `git clone`).
2. **`KUR.bat`**'a çift tıkla: Python ve ffmpeg yoksa kurar, kütüphaneleri yükler, `ayarlar.json` oluşturur.
3. `ayarlar.json`'u aç ve doldur:

| Ayar | Ne |
|---|---|
| `kayit_klasoru` | OBS'in kayıt klasörü (boş: `Videolar`) |
| `luna_userconfig` | LunaTranslator'ın `userconfig` klasörü (Türkçe altyazı + Gemini anahtarı buradan) |
| `planlayicilar` | Planı kim yapsın, sırayla: `["claude", "gemini"]` |
| `claude_model` | Boş: Claude Code'un varsayılanı. Ör. `"sonnet"` |
| `claude_kare` | Claude'a sahne kareleri de gösterilsin (`true`) |
| `gemini_anahtari` | Boş bırak: Luna'daki anahtar kullanılır. Luna yoksa buraya yaz. |
| `oyun`, `kanal` | Başlık ve açıklamalarda kullanılır |
| `uzun_video_dk` | Uzun videonun hedef süresi, ör. `[8, 15]` |
| `shorts_sayisi` | Her oturumdan kaç Shorts |
| `altyazi_gom` | Türkçe altyazıyı videonun üstüne yaz |

### OBS ayarları (bir kez)
- **Kaynak:** Kaynaklar → `+` → **Pencere Yakalama** → pencere: *Xbox* uygulaması, yakalama yöntemi: *Windows 10 (1903 ve üstü)*. Görüntüyü tuvale sığdır (sağ tık → Dönüştür → Ekrana sığdır).
- **Ses:** `+` → **Uygulama Ses Yakalama** → *Xbox*. **Masaüstü sesini kapat** (bildirim, Discord sesi kayda girmesin).
- **Ayarlar → Çıkış → Kayıt:** Biçim **mkv** (elektrik kesilse de kayıt bozulmaz), Kodlayıcı **NVIDIA NVENC H.264** (yoksa QuickSync), Kalite: *Yüksek kalite, orta dosya boyutu*.
- **Ayarlar → Video:** 1920×1080, **60 FPS**.
- Dosya adını değiştirme: varsayılan `2026-11-12 21-30-05.mkv` biçimi, altyazıyı doğru saniyeye eşlemek için kullanılır.

## Kullanım
1. Oynamaya başlarken OBS'de **Kaydı Başlat**, bitince **Kaydı Durdur**.
2. **`YAP.bat`**'a çift tıkla: en yeni kaydı işler (birkaç dakika). Bitince çıktı klasörü açılır:
   - `uzun.mp4`, `uzun_kapak.jpg`, `uzun_tr.srt`
   - `short_1.mp4`, `short_2.mp4`, ...
   - `yukleme_bilgisi.txt`: her video için hazır başlık, açıklama, etiketler
   - `plan.json`: Gemini'nin seçtiği sahneler (merak edersen)
3. [YouTube Studio](https://studio.youtube.com) → **Oluştur → Video yükle** → dosyayı sürükle, `yukleme_bilgisi.txt`'den başlık ve açıklamayı yapıştır, kapak olarak `uzun_kapak.jpg`'yi seç.

Belirli bir kayıt için: `YAP.bat "D:\Kayitlar\2026-11-12 21-30-05.mkv"`. Sadece planı görmek için: `YAP.bat --sadece-plan`. Tek bir planlayıcı için: `YAP.bat --planlayici gemini` (`claude` / `gemini` / `yok`).

## Neden otomatik yükleme kapalı?
YouTube API ile yükleme kodu hazır (`studyo/youtube.py`), ama Google'ın **API denetiminden** (audit) geçmemiş projelerden yüklenen videolar **kalıcı olarak gizli** kalıyor ve itiraz edilemiyor. Bu yüzden `"youtube_yukle": false` varsayılan; Studio'dan yüklemek 1 dakika sürer. Denetim onayı alırsan:
1. Google Cloud'da proje → **YouTube Data API v3**'ü etkinleştir → OAuth izin ekranı → OAuth istemcisi (*Masaüstü uygulaması*).
2. JSON'u bu klasöre `client_secret.json` olarak koy, `ayarlar.json`'da `"youtube_yukle": true`.
3. İlk çalışmada tarayıcıda kanal hesabınla izin ver. Videolar **gizli** yüklenir; kontrol edip sen yayınlarsın.

## Gizlilik
`ayarlar.json`, `client_secret.json`, `token.json`, kayıtlar ve `cikti/` git'e girmez (`.gitignore`). Yapay zekâya yalnızca diyalog metni, sahne zamanları ve (Claude'da) sahne kareleri gider; kaydın tamamı gönderilmez.

## Lisans
[MIT](LICENSE)
