# Balik Tutma Botu

Oyun ici balikcilik mini-oyununu otomatik oynayan Python botu.
Ekrandan anlik goruntu isleme ile daire icindeki baligi tespit eder ve
insan benzeri hizda tiklama yapar.

## Kurulum

```bash
# Proje dizinine gidin
cd fishing

# Bagimliliklari kurun (uv ile)
uv sync
```

> **Windows Notu:** `uv` kurulu degilse: `pip install uv` veya `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`

## Kullanim

### 1. Kalibrasyon (Ilk Kullanim)

Oyun penceresinin ekrandaki konumunu belirlemek icin:

```bash
uv run python -m fishing_bot --calibrate
```

Acilan tam ekran goruntusunde, oyun penceresini mouse ile secin ve **ENTER**'a basin.

### 2. Manuel Bolge Belirtme

Bolgeyi dogrudan komut satirindan belirtebilirsiniz:

```bash
uv run python -m fishing_bot --region "100,200,400,350"
#                                      sol,ust,genislik,yukseklik
```

### 3. Botu Calistirma

```bash
# Debug overlay ile (onerilen — ilk kullanimda)
uv run python -m fishing_bot --region "SOL,UST,GENISLIK,YUKSEKLIK"

# Debug overlay olmadan (daha iyi performans)
uv run python -m fishing_bot --no-debug --region "SOL,UST,GENISLIK,YUKSEKLIK"
```

### 4. Durdurma

**Ctrl+C** ile botu guvenle durdurabilirsiniz.

## Platform Destegi

### Windows
- **DPI Scaling** otomatik olarak handle edilir (ctypes ile DPI Awareness ayarlanir)
- **ANSI renk kodlari** Windows 10+ terminal'de otomatik etkinlestirilir
- Ek izin gerekmez

### macOS
- **Ekran Kaydi** izni gereklidir:
  1. **Sistem Ayarlari** > **Gizlilik ve Guvenlik** > **Ekran Kaydi**
  2. Terminal uygulamaniza (Terminal, iTerm2, VS Code vb.) izin verin
  3. Uygulamayi yeniden baslatin
- **Retina ekran** otomatik algilanir (2x scale)

## CLI Argumanlari

| Arguman | Kisaltma | Aciklama |
|---------|----------|----------|
| `--calibrate` | `-c` | Kalibrasyon modunu baslat |
| `--no-debug` | | Debug overlay'i kapat |
| `--region` | | Yakalama bolgesi: `"sol,ust,genislik,yukseklik"` |
| `--scale` | | Ekran olceklendirme (1=normal, 2=Retina) |

## Yapilandirma

Parametreler `src/fishing_bot/config.py` dosyasindan ayarlanabilir:

| Parametre | Varsayilan | Aciklama |
|-----------|-----------|----------|
| `reaction_min/max` | 0.08-0.20s | Insan benzeri reaksiyon suresi |
| `aim_offset_px` | ±5px | Tiklama sapmasi |
| `mouse_speed_min/max` | 0.05-0.12s | Mouse hareket hizi |
| `click_cooldown` | 0.4s | Tiklamalar arasi bekleme |
| `debug_mode` | True | Debug overlay penceresi |

## Mimari

```
src/fishing_bot/
├── __init__.py
├── __main__.py        # Giris noktasi (DPI Awareness burada)
├── config.py          # Tum ayarlar (dataclass, platform algilama)
├── screen_capture.py  # mss ile ekran yakalama
├── detector.py        # Daire + balik tespit (OpenCV, hibrit)
├── clicker.py         # Insan benzeri mouse kontrol
├── overlay.py         # Debug gorsellestime
└── main.py            # Ana dongu + CLI
```

## Gereksinimler

- Python 3.12+
- Windows 10+ veya macOS
- uv (paket yoneticisi)
