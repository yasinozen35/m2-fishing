# Metin2 Balık Tutma Botu — Proje Dokümantasyonu

## Proje Özeti

Bu proje, Metin2 MMORPG oyunundaki balık tutma mini-oyununu otomatik oynayan bir Python botudur.
Amaç, anti-cheat sistemlerine (HackShield/XIGNCODE) takılmadan, insan benzeri davranışlar sergileyerek
balık tutma işlemini otomatikleştirmektir.

## Oyun Mekaniği (Doğrulanmış Bilgiler)

| Özellik | Detay |
|---------|-------|
| **Su rengi** | Sabit, haritaya göre değişmez |
| **Çember** | Sabit pozisyonda, beyaz tonlarında, mini-game'in ana göstergesi |
| **Balık rengi** | Gri tonlarında, kuyrukta siyah nokta var |
| **Tıklama hedefi** | Balığın **vücut ortası** (kuyruk değil!) |
| **Yakalama** | **3 tıklama** ile balık yakalanır |
| **Mini-game sonu** | Çember ekrandan **tamamen kaybolur** |
| **Balık hızı** | Değişken — normal balıklar yavaş-orta, nadir/değerli balıklar çok hızlı |
| **Döngü tetikleyici** | Çemberin KAYBOLMASI yeni döngüye geçişi tetikler (tıklama sayısı DEĞİL) |
| **Çember yoksa** = yeni olta atma turuna hazır demektir |

## Mimari

```
src/fishing_bot/
├── __init__.py           # Boş
├── __main__.py           # Giriş noktası — DPI Awareness ayarları + GUI başlatma
├── config.py             # Tüm ayarlar (dataclass yapısında)
├── screen_capture.py     # mss ile ekran yakalama
├── detector.py           # Çember + balık tespit motoru (OpenCV)
├── clicker.py            # Win32 API ile insan benzeri mouse kontrolü
├── clicker_subprocess.py # Ayrı process'te pydirectinput tıklama sunucusu
├── bot_logic.py          # Tam otonom state machine (6 state)
├── overlay.py            # Debug görselleştirme (OpenCV penceresi)
├── gui.py                # CustomTkinter masaüstü arayüzü
├── templates/            # Envanter tespiti için balık/çöp/yem ikonları
├── download_fish_icons.py
└── split_fishes.py
```

## State Machine (bot_logic.py)

```
IDLE → PREPARE → CAST → WAITING → MINIGAME → POST_CATCH → (döngü)
                                  ↑                        │
                                  └────────────────────────┘
                     FATIGUE_BREAK (molalar)
```

### State'ler:
- **IDLE**: Bot durduruldu
- **PREPARE**: Yem takma, zırh çıkar-tak (opsiyonel)
- **CAST**: Oltayı suya atma (space tuşu)
- **WAITING**: Çemberin belirmesini bekleme (timeout: 30sn)
- **MINIGAME**: Balık yakalama — 3 tıklama yap, çember kaybolana kadar devam et
- **POST_CATCH**: Yakalama sonrası toparlanma, envanter yönetimi, çöp atma
- **FATIGUE_BREAK**: İnsan yorulması simülasyonu (40-75dk çalışma sonrası 4-12dk mola)

## Bilinen Kritik Bug'lar (Düzeltilmesi Gereken)

### BUG 1: Circle Cache Minigame Bitişini Geciktiriyor
- **Dosya**: `detector.py:116-118`
- **Sorun**: `cache_ttl_frames = 60` → çember kaybolduktan sonra 1 saniye daha cache'ten dönüyor
- **Etki**: Minigame bitiş tespiti gecikiyor, gereksiz tıklamalar, yeni döngüye geç başlama

### BUG 2: Tıklama Cooldown'u Hızlı Balıklar İçin Çok Yavaş
- **Dosya**: `config.py:115`
- **Sorun**: `click_cooldown = 0.80` → saniyede sadece 1.25 tıklama
- **Etki**: Hızlı nadir balıklar daire içinde yeterince kalmadığı için 3 tık yapılamıyor

### BUG 3: Tek Contour Stratejisi
- **Dosya**: `detector.py:229`
- **Sorun**: `max(contours, key=cv2.contourArea)` sadece en büyük contour'u alıyor
- **Etki**: Küçük/hızlı balıklar veya birden fazla balık aynı anda ekrandayken kaçırıyor

### BUG 4: State Machine'de time.sleep() Kullanımı
- **Dosya**: `bot_logic.py:110,129,135`
- **Sorun**: PREPARE ve CAST state'lerinde `time.sleep()` ana döngüyü blokluyor
- **Etki**: FPS düşüyor, tespit gecikiyor

### BUG 5: Prediction Algoritması Zayıf
- **Dosya**: `bot_logic.py:186-203`
- **Sorun**: Sadece 2 frame velocity, sabit look_ahead_time (0.05s), sabit lead_px (14)
- **Etki**: Hızlı nadir balıkların pozisyonu doğru tahmin edilemiyor

## Geliştirme Hedefleri

1. **Balık tespitini iyileştir**: HSV gri tonlama + adaptive threshold hibrit sistemi
2. **Circle cache bug'ını düzelt**: TTL 60→8, cache doğrulama ekle
3. **Tıklama hızını optimize et**: Cooldown 0.80→0.30, ama insansı pattern'lerle
4. **Prediction'ı güçlendir**: 5 frame tracking, adaptif look_ahead, dinamik safe zone
5. **Anti-cheat gizlenme**: Hata simülasyonu, ritim çeşitlendirme, bekleme davranışları
6. **Session çeşitliliği**: Her başlatmada farklı oyuncu profili (acemi/normal/profesyonel/yorgun)

## Kod Standartları

- ❌ `time.sleep()` kullanma — ana döngüyü bloklar. Frame-count timer kullan
- ❌ Circle cache'e körü körüne güvenme — her zaman doğrula
- ❌ Sadece en büyük contour'u alma — TOP-3 değerlendir
- ✅ Çember kayboldu = minigame bitti — tek güvenilir state trigger'ı bu
- ✅ Tıklama sayısı değil, çember durumu state geçişlerini belirler
- ✅ Balığın vücut ortasına tıkla — bounding box'ın yatay merkezi, dikey %40'ı
- ✅ Tüm değişikliklerde platform uyumluluğunu koru (Windows + macOS)
- ✅ Yeni eklenen özellikleri config'den kontrol edilebilir yap

## Platform

- **Geliştirme**: Windows 11 Pro
- **Python**: 3.12+
- **Paket yöneticisi**: uv
- **Bağımlılıklar**: mss, opencv-python, numpy, pyautogui, customtkinter, pydirectinput

## Kullanım

```bash
# GUI ile başlat (önerilen)
uv run python -m fishing_bot

# CLI ile başlat
uv run python -m fishing_bot --autobot --region "left,top,width,height"

# Debug görüntüleri test et
uv run python debug_fish_script.py
```
