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

## Otomatik mod (önerilen): sadece oyna
Arka planda çalışan bekçi (`studyo/izle.py`) her şeyi kendisi yapar:

- **Otomatik kayıt:** Xbox uzaktan oynatma başlayınca (Xbox uygulamasının sesi akmaya başlayınca) OBS'i simge durumunda açar, **"Xbox (otomatik)"** sahnesine geçer ve kaydı başlatır; uzaktan oynatma kapanınca (1 dk sessizlik) durdurur. Kayıt sırasında masaüstü sesi kapatılır, yalnızca Xbox sesi kaydedilir; bitince önceki sahne ve ses ayarı geri gelir.
- **Otomatik kurgu:** Xbox sahnesindeki kayıt durunca (otomatik ya da elle) kurgu başlar; bitince Windows bildirimi gelir ve çıktı klasörü açılır. 3 dakikadan kısa kayıtlar atlanır.
- **Anı işaretle:** Oynarken güzel bir an olunca hemen ardından klavyede **F9**'a bas (PC'den iki kısa bip). O anın son ~25 saniyesi uzun videoya mutlaka girer, Shorts için de önce o anlara bakılır. Kumanda PC'ye bağlıysa **iki analog çubuğa birlikte basmak** da işaretler (kumanda Xbox'a bağlıysa PC onu göremez).

Kurulum (bir kez): `python -m studyo.izle --kur` — OBS'in uzaktan kumandasını (WebSocket) açar ve bekçiyi Windows açılışına ekler (OBS kapalıyken çalıştırın). Bekçiyi pencerede izlemek için `IZLE.bat`, açılıştan çıkarmak için `python -m studyo.izle --kaldir`. Günlük: `izle.log`, kurgu çıktısı: `izle_kurgu.log`.

> Not: Uzaktan oynatmanın tam ekran penceresi Windows'un pencere listesinde görünmediği için OBS pencere yakalama siyah kaydeder; sahne bu yüzden **ekran yakalama** kullanır. Oynarken PC'de başka pencere açarsan o da kayda girer. Uzaktan oynatmayı bitirirken oyunu kapatmak yetmez: sol üstteki ⋮ → **Bağlantıyı kes**.

Ayarlar (`ayarlar.json`): `oto_kayit`, `oto_kurgu`, `oto_kayit_basla_sn` (15), `oto_kayit_dur_sn` (60), `en_kisa_kayit_dk` (3), `isaret_tusu` (`"F9"`), `kumanda_isaret`, `mikrofon_kaydi`, `obs_exe`.

> OBS düzgün kapanmazsa (PC kapandı, işlem sonlandırıldı) bir sonraki açılışta "Güvenli modda başlat?" sorar; Güvenli Mod'da WebSocket çalışmaz ve otomatik kayıt başlayamaz. Bekçi OBS'i açmadan önce eski çalışma izlerini (`%APPDATA%\obs-studio\.sentinel\run_*`) siler, soru çıkmaz.

### Mikrofon (yorum)
Mikrofon **PC'ye** takılı olmalı (USB mikrofon; kulaklık Xbox kumandasına takılıysa ses Xbox'a gider, PC duymaz). Windows'ta varsayılan kayıt aygıtı yapılır; takınca Windows varsayılan **çıkışı** da mikrofona çevirebilir, *Ses ayarları → Çıkış*'ın TV'de kaldığını kontrol et. Otomatik kayıt sahnesine **"Mikrofon"** kaynağı (RNNoise gürültü bastırma ile) eklenir ve kayıt 2 ses kanallı olur:

| Kanal | İçerik | Ne için |
|---|---|---|
| 1 | Xbox sesi + mikrofon | Videoya giren ses |
| 2 | Yalnız mikrofon | Kurgu konuştuğun anları buradan bulur |

Konuştuğun anlar aday sahne olur ve öne çıkar, Claude yorumu ortadan kesmez. Yorum YouTube'un "tekrar kullanılan içerik" kuralına karşı kanalın en güçlü özgünlük kanıtıdır. Kapatmak için `"mikrofon_kaydi": false`.

Belirli bir kayıt için: `YAP.bat "D:\Kayitlar\2026-11-12 21-30-05.mkv"`. Sadece planı görmek için: `YAP.bat --sadece-plan`. Tek bir planlayıcı için: `YAP.bat --planlayici gemini` (`claude` / `gemini` / `yok`).

## Kick'te canlı yayın (Türkçe altyazılı)
**İki OBS:** yayın, kurulu OBS'in taşınabilir bir kopyasından (`yayin_obs_klasoru`, varsayılan `%USERPROFILE%\obs-yayin`, kendi ayar klasörü, WebSocket 4456) yapılır. Kick'e giden görüntüde Türkçe altyazı, chat ve bildirimler vardır; kurulu OBS aynı anda **temiz kayıt** alır (yalnız oyun + Xbox sesi + mikrofon). YouTube videolarında chat ya da canlı altyazı olmaz, bulanıklaştırmaya gerek kalmaz; kurgu kendi düzelttiği okunaklı altyazıyı gömer. Ölçüm (RTX 2070, ikisi aynı anda): iki OBS'te de kodlayıcı gecikmesi 0, 60 fps, kare başına 0,3 ms, işlemci %1. Yayın bitince ikinci OBS kendiliğinden kapanır.

| | Kayıt OBS'i (kurulu) | Yayın OBS'i (kopya) |
|---|---|---|
| Ne için | YouTube kurgusu | Kick |
| Sahne | ekran + Xbox sesi + mikrofon | aynısı + altyazı + chat + bildirimler |
| Çıktı | 2 ses kanallı kayıt | 7800 kbps yayın |

Kurulum (bir kez; OBS güncellenince tekrar): `python -m studyo.yayin --ikinci-obs` → OBS'i kopyalar, ayarları (profil, Kick anahtarı, sahne) ayırır, `global.ini` [Locations] yollarını kopyanın kendi klasörüne çevirir (yoksa iki OBS aynı profil/sahne dosyalarını kullanırdı), kurulu OBS'ten yayın katmanlarını ve Kick anahtarını siler.

Kick anahtarı: **`YAYIN_KUR.bat`** → Kick'te *Yayıncı Paneli (Creator Dashboard) → Stream URL and Key*'den adresi ve anahtarı yapıştır (anahtar ekranda görünmez, yalnız yayın OBS'inin kendi ayarına yazılır). Ya da adres + `key: ...` satırlı bir metin dosyasından: `python -m studyo.yayin --kur --dosya kick.txt`. 1080p60, NVENC **p6**, CBR **7800 kbps** (Kick sınırı 8000), 2 sn anahtar kare. Kick API'si / Geliştirici Modu gerekmez.

Kalite ve akıcılık: 4K ekran 1080p'ye **Lanczos** ile küçültülür (sahnedeki "Xbox goruntu" öğesi; OBS kapalıyken sahne dosyasında `scale_filter`). Yayın sürerken kurgu ve YouTube yüklemesi bekletilir (GPU'yu ve upload'u yayınla paylaşmasınlar), yayın bitince kendiliğinden devam eder. Görüntüdeki takılmaların kaynağı en çok uzaktan oynatmanın kendisidir: Xbox'ı kabloyla (Ethernet) bağla, yayında indirme (Steam, Windows Update) olmasın.

Oynarken: uzaktan oynatma açıkken **Telegram kumandasından** 🔴 *Yayını başlat* (PC'den yükselen üç bip; Kick'e bağlanınca telefona "Yayın başladı" gelir), ⏹ *Yayını bitir*. Kayıt da açılır; yayının videosu da YouTube kurgusuna girer. OBS 30 sn'de Kick'e bağlanamazsa telefona haber gelir.

- **Canlı Türkçe katman:** `yayin/altyazi.html` yayın OBS'inde tarayıcı kaynağıdır. Altyazı motorunun (xbox-samsung-subtitles-tv `motor/`) konumlu olaylarına bağlanır (`ws://127.0.0.1:2333/api/ws/olay`). Hem alttaki altyazının hem sol üstteki görev/ipucu kutusunun Türkçesini İngilizcenin **tam üstüne, tam siyah zeminle** yazar (İngilizce görünmez), TV'dekiyle aynı. Önizleme: `?test=1`.
- **Mahremiyet:** OBS PC ekranının tamamını yakalar. Yayındayken bekçinin bildirimleri susar; uzaktan oynatma 4 sn kesilirse yayındaki ekran gizlenir (izleyici siyah ekran görür, masaüstünü değil); oturum bitince (1 dk) yayın kendiliğinden kapanır. Diğer uygulamaların bildirimleri için Windows'ta *Ayarlar → Sistem → Bildirimler → Rahatsız etmeyi otomatik aç → Tam ekran modunda bir uygulama kullanırken*'i aç.
- **Luna:** Uzaktan oynatma başlayınca kapalıysa bekçi açar (`luna_oto_baslat`).

**Chat ve takip/abone bildirimleri (BotRix):** [botrix.live](https://botrix.live)'a Kick hesabıyla gir; *Alerts* (takip, abone, hediye abonelik, baskın) ve *Chat* widget'larının "Browser Source" adreslerini kopyala, bir metin dosyasına `chat: https://...` ve `alerts: https://...` satırları olarak yaz, sonra `python -m studyo.yayin --katmanlar --dosya botrix.txt`. İkisi yalnız yayın OBS'inde; kayda girmez. Chat kutusu sağda (`yayin_chat_kutusu`, varsayılan `[1480, 170, 420, 420]`): GTA'nın sağ üst HUD'u ve sağ alttaki telefon açık kalır. Chat'in görünümü (yazı boyutu, mesaj süresi, ses, bot gizleme) BotRix adresindeki parametrelerdedir; bildirim metinleri BotRix panelinde. Bildirim sesleri yalnız 1. ses kanalına (videoya) gider; mikrofon kanalına girip "konuşma" sanılmaz. Adresler `kick_katmanlari.json`'da (git'e girmez; içinde kişisel anahtar var).

Ayarlar: `yayin_bit_hizi` (7800), `yayin_ekran_gizle_sn` (4), `yayin_tusu` (boş = klavye kısayolu yok; istersen `"F10"`). Denemek: `python -m studyo.yayin --dene` (yayın OBS'inin görüntüsü, örnek altyazıyla; masaüstü gizli).

## Telegram kumandası
Koltuktan, telefondan: sohbetin altında sabit tuşlar.

| Tuş | Ne yapar |
|---|---|
| ⭐ İşaretle | F9 ile aynı: o anın son ~25 sn'si videoya mutlaka girer (basıldığın saniye kullanılır) |
| 🔴 Yayını başlat / ⏹ Yayını bitir | Kick yayını (yalnız uzaktan oynatma açıkken açılır) |
| ☕ Mola | Yayında oyun görüntüsünü elle gizler, mola ekranı çıkar (Xbox'ta şifre girerken, kalkarken); tekrar basınca geri gelir |
| 💬 Yayın altyazısı | Kick'teki canlı Türkçe altyazıyı aç/kapa (TV'deki altyazı etkilenmez) |
| 🎙 Mikrofon | İki OBS'te birlikte mikrofonu susturur/açar (kayıt + yayın) |
| 📊 Durum | Uzaktan oynatma, kayıt süresi, yayın süresi, mola, mikrofon, Luna, kurgu kuyruğu |
| 🔁 Luna'yı yeniden başlat | Altyazı takılırsa Luna'yı kapatıp açar |

Bekçinin bütün bildirimleri (kayıt başladı, videolar hazır, yayın başladı/bitti, yeni yorumlar, rapor) telefona da gelir; yayındayken ekrana hiç düşmez.

Kurulum (bir kez): Telegram'da **@BotFather → /newbot** → ad ve sonu `bot` ile biten kullanıcı adı → verdiği jetonu al. Botuna **/start** yaz. Sonra **`TELEGRAM_KUR.bat`** (jetonu sorar; ya da `python -m studyo.telegram --kur --dosya telegram.txt`). Bot yalnız eşleştiği sohbete (sana) cevap verir, başkasının mesajını yok sayar; bekçi kapalıyken basılan ya da 2 dk'dan eski tuşlar çalıştırılmaz. Jeton `telegram.json`'da (git'e girmez).

## YouTube'a otomatik yükleme
Kurgu bitince uzun video ve Shorts'lar başlık, açıklama, etiket ve (uzun videoda) kapakla **gizli** yüklenir; Studio'da kontrol edip tek tıkla yayınlarsın. Linkler `cikti/<kayit>/youtube_linkleri.txt`'ye yazılır, Windows bildirimi gelir. 2 Kasım 2026'dan beri Google'ın denetiminden (audit) geçmemiş API projelerinin videoları artık gizliye kilitlenmiyor ([revision history](https://developers.google.com/youtube/v3/revision_history)); yükleme kotası ayrı: günde 100 video.

Kurulum (bir kez, ~5 dk):
1. [Google Cloud Console](https://console.cloud.google.com/) → yeni proje.
2. **APIs & Services → Library → YouTube Data API v3 → Enable**.
3. **Google Auth Platform** (OAuth izin ekranı) → *Get started*: uygulama adı, e-posta, **External**. Sonra **Audience → Publish app** (*In production*). *Testing*'de kalırsa izin 7 günde bir sona erer. Giriş ekranında "Google bu uygulamayı doğrulamadı" uyarısı normaldir (kendi uygulaman): *Gelişmiş → devam et*.
4. **Clients → Create client → Desktop app** → JSON'u indir → bu klasöre `client_secret.json` adıyla koy.
5. `python -m studyo.youtube --kur` → tarayıcıda **kanalın olduğu hesabı** (marka hesabıysa onu) seç, izin ver. Komut hangi kanala bağlandığını yazar.
6. `ayarlar.json`: `"youtube_yukle": true`. İstersen `"youtube_gizlilik"`: `"private"` (varsayılan) / `"unlisted"` / `"public"`.

İzin geçerli mi: `python -m studyo.youtube --kontrol`. Kanalın **Hakkında** metni `kanal_hakkinda.txt`'de durur; değiştirip `python -m studyo.youtube --hakkinda` çalıştırınca önizleme gösterir, onay verirsen kanala yazar (eski metin `kanal_hakkinda.yedek.txt`'ye yedeklenir). Özel kapak için kanalın telefonla doğrulanmış olması gerekir ([youtube.com/verify](https://www.youtube.com/verify)); değilse video kapaksız yüklenir.

### Her yüklemede otomatik
| Ne | Nasıl | Ayar |
|---|---|---|
| **Bölümler** | Claude her sahneye ad verir; açıklamaya `00:00 ...` listesi yazılır, YouTube oynatma çubuğunda bölüm olarak gösterir (en az 3 bölüm, her biri ≥10 sn; kısa sahne sonrakine katılır). Zamanlar siyahı kırpılmış gerçek sürelerden hesaplanır. | `youtube_bolumler` |
| **İngilizce başlık/açıklama** | `localizations.en`: dili İngilizce olan izleyici videoyu İngilizce başlıkla görür. | `youtube_ingilizce` |
| **Altyazı parçaları** | Uzun videoya TR + EN, Shorts'a EN (Türkçesi zaten videonun üstünde). EN, OCR hataları Claude'a düzeltilmiş oyun altyazısıdır. Parça başına 400 kota birimi. | `youtube_altyazi_dilleri` |
| **Oynatma listeleri** | `{oyun} Türkçe Altyazılı Oynanış` ve `{oyun} Shorts | Türkçe Altyazılı`; yoksa oluşturulur. | `youtube_listeler` |
| **Zamanlanmış yayın** (kapalı) | Açılırsa uzun video ertesi gün 20:00'de, Shorts sonraki günlerde birer birer 18:00'de kendiliğinden yayına girer. | `youtube_zamanla`, `youtube_uzun_saat`, `youtube_shorts_saat` |

Eski bir kaydın videolarını yeniden yüklemeden tamamlamak: `python -m studyo "kayit.mkv" --plani-kullan --youtube-guncelle`.

### Performans raporu ve öğrenme
**`RAPOR.bat`** (bekçi haftada bir kendisi de çalıştırır): tüm videoların izlenme/beğeni/yorum sayıları + son 28 günün izlenme süresi, ortalama izlenme yüzdesi, abone ve trafik kaynakları ([YouTube Analytics API](https://console.cloud.google.com/apis/library/youtubeanalytics.googleapis.com) açık olmalı; veriler ~2 gün gecikmeli). Claude veriyi yorumlar: sana Türkçe özet (`cikti/raporlar/rapor_TARIH.md`), kurguya dersler (`ogrenme.json`). Bir sonraki kurguda Claude bu dersleri uygular; toplam izlenme 30'un altındaysa ders çıkarılmaz.

### Yorumlar
Bekçi 3 saatte bir cevaplanmamış yorumları sayar, varsa bildirim gönderir. **`YORUMLAR.bat`**: Claude her yoruma kısa, samimi bir cevap taslağı yazar (spam ve cevap gerektirmeyenlere yazmaz); **Enter** gönderir, **d** ile kendin yazarsın, **a** atlar. Hiçbir cevap onayın olmadan gitmez.

## Gizlilik
`ayarlar.json`, `client_secret.json`, `token.json`, kayıtlar ve `cikti/` git'e girmez (`.gitignore`). Yapay zekâya yalnızca diyalog metni, sahne zamanları ve (Claude'da) sahne kareleri gider; kaydın tamamı gönderilmez.

## Lisans
[MIT](LICENSE)
