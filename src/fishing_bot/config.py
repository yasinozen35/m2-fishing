"""
config.py — Tüm yapılandırılabilir parametreler.

Oyun penceresinin konumu, tespit algoritma parametreleri,
ve insan benzeri davranış ayarları burada tanımlanır.
Platform (Windows/macOS) otomatik algılanır.
"""

import platform
import sys
from dataclasses import dataclass, field


def _detect_display_scale() -> int:
    """
    Ekran ölçeklendirme faktörünü otomatik algılar.

    - Windows: DPI Awareness ayarlandıktan sonra her zaman 1 (piksel koordinatları gerçek).
    - macOS: Retina ekranlarda 2, normal ekranlarda 1.
    """
    system = platform.system()

    if system == "Windows":
        # Windows'ta DPI awareness ayarlandıktan sonra mss
        # gerçek piksel koordinatlarını döndürür, scale = 1.
        return 1
    elif system == "Darwin":
        # macOS Retina ekranlarda mss 2x çözünürlükte yakalar.
        try:
            import subprocess
            result = subprocess.run(
                ["system_profiler", "SPDisplaysDataType"],
                capture_output=True, text=True, timeout=5,
            )
            if "Retina" in result.stdout:
                return 2
        except Exception:
            pass
        return 2  # Varsayılan olarak Retina varsay.
    else:
        return 1


@dataclass
class CaptureConfig:
    """Ekran yakalama ayarları."""
    # Oyun penceresinin ekrandaki konumu (piksel).
    # İlk çalıştırmada kalibrasyon aracı ile otomatik belirlenir.
    top: int = 0
    left: int = 0
    width: int = 400
    height: int = 400

    # Ekran ölçeklendirme faktörü.
    # Otomatik algılanır: Windows=1, macOS Retina=2.
    display_scale: int = field(default_factory=_detect_display_scale)


@dataclass
class CircleDetectConfig:
    """Hough Circle Transform parametreleri."""
    dp: float = 1.2                # Çözünürlük oranı (1 = orijinal, 2 = yarı)
    min_dist: int = 100            # Daireler arası minimum mesafe
    param1: int = 100              # Canny edge üst eşiği
    param2: int = 40               # Merkez tespit eşiği (düşük = daha hassas)
    min_radius: int = 50           # Minimum daire yarıçapı (px)
    max_radius: int = 300          # Maksimum daire yarıçapı (px)
    cache_ttl_frames: int = 40     # Daire cache süresi (kare sayısı). Uzun: tespit dalgalanmasını bastırmak için.
    inner_margin: float = 0.95     # Daire iç bölge oranı (Daha geniş alan toleransı)


@dataclass
class FishDetectConfig:
    """Balık tespit parametreleri (HSV renk filtreleme)."""
    # Koyu balık silueti için HSV aralığı.
    # Balık koyu/siyahımsı olduğu için düşük Value değeri kullanılır.
    hsv_lower: tuple = (0, 0, 0)        # H, S, V alt sınır
    hsv_upper: tuple = (180, 255, 120)  # H, S, V üst sınır

    # Contour alan filtresi (piksel²).
    # Çok küçük contour'lar gürültü, çok büyükler arka plan.
    min_area: int = 30
    max_area: int = 5000

    # Balık koyuluğu eşik değeri (Gölge vs Balık ayırımı).
    # Suyun ortalama renginden ne kadar koyu olan pikselleri balık olarak kabul edeceğini belirler.
    # 25 çok hassastır (dalgaları balık sanır), 50-70 arası idealdir.
    threshold_offset: int = 40

    # Morfolojik işlem kernel boyutu.
    morph_kernel_size: int = 3

    # Gaussian blur kernel boyutu (tek sayı olmalı).
    blur_kernel_size: int = 5


@dataclass
class HumanConfig:
    """İnsan benzeri davranış parametreleri."""
    # ── İnsansı Reaksiyon Sistemi (Anti-Cheat) ──
    # Gerçek insan visual-motor reaksiyon süresi: 150-250ms
    # Profesyonel oyuncu seviyesi: 100-180ms
    # Bot, balık safe zone'a girdikten SONRA bu kadar bekler.
    # Bu, anti-cheat için EN KRİTİK parametredir.
    reaction_min: float = 0.10     # 100ms — çok hızlı refleks (profesyonel oyuncu alt sınırı)
    reaction_max: float = 0.18     # 180ms — normal refleks (yorgun/anlık dalgınlık)

    # Tıklama noktasında rastgele sapma (piksel).
    # ±2px sapma ile her seferinde tam merkeze tıklanmaz.
    aim_offset_px: int = 3       # ±3px sapma (insansı mikro hata)

    # Mouse hareket süresi aralığı (saniye) — sadece envanter/zırh için.
    mouse_speed_min: float = 0.02  # 20ms
    mouse_speed_max: float = 0.05  # 50ms

    # Tıklamalar arası minimum bekleme (saniye).
    # 0.35s = saniyede ~2.8 tıklama. Hızlı nadir balıkları yakalamak için optimize.
    # İnsan seri tıklama hızı: 150-250ms aralığı. 350ms güvenli üst sınır.
    click_cooldown: float = 0.35

    # ── Prediction (Hedef Öngörü) Parametreleri ──
    # İnsanlar balığın gideceği yeri doğal olarak tahmin eder (lead targeting).
    # Bu parametreler botun tahmin gücünü kontrol eder.
    prediction_look_ahead_base: float = 0.10   # Temel ileriye bakma süresi (100ms)
    prediction_look_ahead_max: float = 0.18    # Maksimum ileriye bakma (hızlı balıklar için)
    prediction_speed_threshold: float = 50.0   # px/s: bu hızın üstünde prediction aktif
    prediction_max_lead_px: int = 35           # Maksimum lead mesafesi (piksel)


@dataclass
class AutoBotConfig:
    """Tam otonom oyun döngüsü parametreleri."""
    key_bait: str = '1'          # Yem tuşu (hızlı erişim slotu)
    key_fish: str = 'space'      # Olta atma tuşu

    # Zırh animasyon iptali (Çıkar-Tak) için envanterdeki zırhın piksel koordinatları.
    # GUI üzerinden seçilecek.
    armor_x: int = 0
    armor_y: int = 0
    use_armor_trick: bool = False # Zırh çıkar-tak aktif mi?
    auto_open_fishes: bool = True # Yakalanan balıklar otomatik açılsın mı?
    auto_drop_trash: bool = True  # Çöpler yere atılsın mı?

    # İnsan Yorulması (Fatigue System)
    use_fatigue_system: bool = True
    fatigue_interval_min: float = 40.0 * 60.0  # Dakika cinsinden minimum çalışma süresi (saniye)
    fatigue_interval_max: float = 75.0 * 60.0  # Dakika cinsinden maksimum çalışma süresi (saniye)
    fatigue_duration_min: float = 4.0 * 60.0   # Minimum mola süresi (saniye)
    fatigue_duration_max: float = 12.0 * 60.0  # Maksimum mola süresi (saniye)

    # Döngü zamanlamaları (saniye)
    delay_after_bait: float = 0.15   # Yem taktıktan sonra ÇOK KISA bekleme (random ekleniyor)
    delay_after_armor: float = 0.3   # Zırh değiştirdikten sonra bekleme
    delay_after_cast: float = 0.3    # Oltayı attıktan sonra kısa bekleme (2.0s çok uzundu, çember bu sırada kaçıyordu)
    delay_after_catch: float = 3.0   # Minigame bittikten sonra 3sn bekle, sonra 1'e bas
    timeout_waiting_fish: float = 30.0 # Suya attıktan sonra max bekleme süresi (45sn çok uzundu)


@dataclass
class Config:
    """Ana yapılandırma sınıfı."""
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    circle: CircleDetectConfig = field(default_factory=CircleDetectConfig)
    fish: FishDetectConfig = field(default_factory=FishDetectConfig)
    human: HumanConfig = field(default_factory=HumanConfig)
    autobot: AutoBotConfig = field(default_factory=AutoBotConfig)

    # Debug modu: True ise overlay penceresi açılır.
    debug_mode: bool = True

    # FPS sınırı (ana döngü).
    target_fps: int = 60

    def __post_init__(self):
        """Uygulama başlatıldığında kalibrasyon dosyasını otomatik yükler."""
        self.load_calibration()

    def save_calibration(self, filepath="calibration.json"):
        """Kalibrasyon ayarlarını json dosyasına kaydeder."""
        import json
        data = {
            "capture_top": self.capture.top,
            "capture_left": self.capture.left,
            "capture_width": self.capture.width,
            "capture_height": self.capture.height,
            "armor_x": self.autobot.armor_x,
            "armor_y": self.autobot.armor_y,
        }
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Kalibrasyon kaydedilemedi: {e}")

    def load_calibration(self, filepath="calibration.json"):
        """Kalibrasyon ayarlarını json dosyasından yükler."""
        import json
        import os
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.capture.top = data.get("capture_top", self.capture.top)
                    self.capture.left = data.get("capture_left", self.capture.left)
                    self.capture.width = data.get("capture_width", self.capture.width)
                    self.capture.height = data.get("capture_height", self.capture.height)
                    self.autobot.armor_x = data.get("armor_x", self.autobot.armor_x)
                    self.autobot.armor_y = data.get("armor_y", self.autobot.armor_y)
            except Exception as e:
                print(f"Kalibrasyon yuklenemedi: {e}")
