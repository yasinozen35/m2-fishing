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

    # ── Balık Vücut Tıklama Noktası ──
    # Balık bounding box'ının dikeyde % kaçına tıklanacağı.
    # 0.0 = balığın en üstü (kafa), 1.0 = en altı (kuyruk).
    # 0.45 = gövde ortası (varsayılan, çoğu balık için ideal).
    # DÜŞÜR: kuyruğa yakın / YÜKSELT: kafaya yakın tıklar.
    fish_body_offset_y: float = 0.45


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

    # ── Balığın Sağına/Soluna Rastgele Tıklama ──
    # 0 = balığın tam ortasına (varsayılan).
    # 5-12 = bazen başa bazen kuyruğa yakın tıkla (insansı dağılım).
    # Piksel cinsinden, HER tıklamada rastgele ±bu değer kadar sapar.
    horizontal_jitter_px: int = 0

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
    prediction_lead_factor: float = 0.7        # Lead çarpanı (0.3=az lead, 1.2=çok lead)
    click_inner_margin: float = 0.90           # Çember içi tıklama sınırı (0.75-0.95)

    # ── Anti-Cheat Gizlenme Parametreleri ──
    # Gaussian jitter: uniform yerine normal dağılım (daha insansı)
    use_gaussian_jitter: bool = True
    # Mikro mouse hareketi: ışınlanma yerine 2-4 adımlı hareket
    use_micro_movement: bool = True
    micro_movement_steps: int = 3              # Kaç adımda varılsın (2-5)
    # Tespit kör noktası: circle tespitini kasıtlı kaçırma oranı
    detection_blind_spot_rate: float = 0.02    # %2 frame'de circle "görme"
    # State geçiş tereddütü
    transition_hesitation_min: float = 0.03    # 30ms min tereddüt
    transition_hesitation_max: float = 0.12    # 120ms max tereddüt
    # Prediction gürültüsü: lead'i kasıtlı over/under-shoot
    prediction_noise_sigma: float = 0.15       # Gauss σ (0=optimal, 0.3=insansı hata)
    # Dinamik ritim: sabit pattern yerine prosedürel
    use_dynamic_rhythm: bool = True
    rhythm_noise_sigma: float = 0.12           # Ritim Gauss σ
    # Bilerek kaçırma oranları
    intentional_miss_rate: float = 0.08        # Normal balık kaçırma
    fast_fish_miss_rate: float = 0.18          # Hızlı balık kaçırma (insan daha çok kaçırır)
    # FPS jitter: frame'leri rastgele geciktir
    use_fps_jitter: bool = True
    fps_jitter_rate: float = 0.03              # %3 frame'de gecikme
    
    # ── Hedefleme Modu (Senkronizasyon) ──
    targeting_mode: str = "organic"            # "organic" veya "terminator"


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
    
    # ── Chat Okuma & İptal ──
    ignored_fishes: list = field(default_factory=list) # İptal edilecek balıklar listesi
    custom_fishes: list = field(default_factory=list)
    use_fish_ocr: bool = True
    chat_region_x: int = 0
    chat_region_y: int = 0
    chat_region_w: int = 400
    chat_region_h: int = 200
    
    # ── Auto Mod Ayarları ──
    auto_mode_min_mins: int = 3
    auto_mode_max_mins: int = 8
    auto_weight_terminator: int = 10
    auto_weight_esports: int = 50
    auto_weight_safe: int = 40

    auto_drop_trash: bool = True  # Çöpler yere atılsın mı?

    # İnsan Yorulması (Fatigue System)
    use_fatigue_system: bool = True
    fatigue_interval_min: float = 40.0 * 60.0  # Dakika cinsinden minimum çalışma süresi (saniye)
    fatigue_interval_max: float = 75.0 * 60.0  # Dakika cinsinden maksimum çalışma süresi (saniye)
    fatigue_duration_min: float = 4.0 * 60.0   # Minimum mola süresi (saniye)
    fatigue_duration_max: float = 12.0 * 60.0  # Maksimum mola süresi (saniye)

    # Döngü zamanlamaları (saniye)
    delay_after_bait: float = 1.5    # Yem taktıktan sonra olta atmadan önce bekleme (1.5sn)
    delay_after_armor: float = 0.3   # Zırh değiştirdikten sonra bekleme
    delay_after_cast: float = 0.3    # Oltayı attıktan sonra kısa bekleme
    delay_after_catch: float = 3.0   # Minigame bittikten sonra bekleme
    timeout_waiting_fish: float = 30.0 # Suya attıktan sonra max bekleme süresi

    # Minigame sonrası yeniden olta atma zaman aşımı
    # Minigame bittikten 10sn sonra hala yeni minigame başlamadıysa → space'e tekrar bas
    retry_cast_timeout: float = 10.0

    # Çöp atma hedef koordinatları (ekranın oyun dünyasına denk gelen bir yeri)
    trash_drop_x: int = 400
    trash_drop_y: int = 300

    # Minigame başına maksimum tıklama sayısı
    max_clicks_per_minigame: int = 8

    # Zamanlama rastgeleliği: sabit delay'leri ±% oranında rastgeleleştir
    timing_randomization: float = 0.30         # ±%30 gürültü


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
        """TÜM ayarları json dosyasına kaydeder (kalibrasyon + ince ayar)."""
        import json
        data = {
            # Capture
            "capture_top": self.capture.top,
            "capture_left": self.capture.left,
            "capture_width": self.capture.width,
            "capture_height": self.capture.height,
            # Zırh
            "armor_x": self.autobot.armor_x,
            "armor_y": self.autobot.armor_y,
            "trash_drop_y": self.autobot.trash_drop_y,
            "auto_open_fishes": self.autobot.auto_open_fishes,
            "auto_mode_min_mins": self.autobot.auto_mode_min_mins,
            "auto_mode_max_mins": self.autobot.auto_mode_max_mins,
            "auto_weight_terminator": self.autobot.auto_weight_terminator,
            "auto_weight_esports": self.autobot.auto_weight_esports,
            "auto_weight_safe": self.autobot.auto_weight_safe,
            "use_armor_trick": self.autobot.use_armor_trick,
            "auto_drop_trash": self.autobot.auto_drop_trash,
            "use_fatigue_system": self.autobot.use_fatigue_system,
            "ignored_fishes": self.autobot.ignored_fishes,
            "custom_fishes": self.autobot.custom_fishes,
            "use_fish_ocr": self.autobot.use_fish_ocr,
            "chat_region_x": self.autobot.chat_region_x,
            "chat_region_y": self.autobot.chat_region_y,
            "chat_region_w": self.autobot.chat_region_w,
            "chat_region_h": self.autobot.chat_region_h,
            # Human — reaksiyon & tıklama
            "reaction_min": self.human.reaction_min,
            "reaction_max": self.human.reaction_max,
            "click_cooldown": self.human.click_cooldown,
            "aim_offset_px": self.human.aim_offset_px,
            "horizontal_jitter_px": self.human.horizontal_jitter_px,
            # Human — prediction
            "prediction_look_ahead_base": self.human.prediction_look_ahead_base,
            "prediction_look_ahead_max": self.human.prediction_look_ahead_max,
            "prediction_speed_threshold": self.human.prediction_speed_threshold,
            "prediction_max_lead_px": self.human.prediction_max_lead_px,
            "prediction_lead_factor": self.human.prediction_lead_factor,
            "click_inner_margin": self.human.click_inner_margin,
            # Human — anti-cheat
            "use_gaussian_jitter": self.human.use_gaussian_jitter,
            "use_micro_movement": self.human.use_micro_movement,
            "detection_blind_spot_rate": self.human.detection_blind_spot_rate,
            "transition_hesitation_min": self.human.transition_hesitation_min,
            "transition_hesitation_max": self.human.transition_hesitation_max,
            "prediction_noise_sigma": self.human.prediction_noise_sigma,
            "use_dynamic_rhythm": self.human.use_dynamic_rhythm,
            "rhythm_noise_sigma": self.human.rhythm_noise_sigma,
            "intentional_miss_rate": self.human.intentional_miss_rate,
            "fast_fish_miss_rate": self.human.fast_fish_miss_rate,
            "use_fps_jitter": self.human.use_fps_jitter,
            "fps_jitter_rate": self.human.fps_jitter_rate,
            "targeting_mode": self.human.targeting_mode,
            # Fish
            "fish_body_offset_y": self.fish.fish_body_offset_y,
            # AutoBot
            "max_clicks_per_minigame": self.autobot.max_clicks_per_minigame,
            "timing_randomization": self.autobot.timing_randomization,
            "delay_after_bait": self.autobot.delay_after_bait,
            "retry_cast_timeout": self.autobot.retry_cast_timeout,
            "trash_drop_x": self.autobot.trash_drop_x,
        }
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Ayarlar kaydedilemedi: {e}")

    def load_calibration(self, filepath="calibration.json"):
        """TÜM ayarları json dosyasından yükler."""
        import json
        import os
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Capture
                    self.capture.top = data.get("capture_top", self.capture.top)
                    self.capture.left = data.get("capture_left", self.capture.left)
                    self.capture.width = data.get("capture_width", self.capture.width)
                    self.capture.height = data.get("capture_height", self.capture.height)
                    # Zırh
                    self.autobot.armor_x = data.get("armor_x", self.autobot.armor_x)
                    self.autobot.armor_y = data.get("armor_y", self.autobot.armor_y)
                    self.autobot.trash_drop_x = data.get("trash_drop_x", self.autobot.trash_drop_x)
                    self.autobot.trash_drop_y = data.get("trash_drop_y", self.autobot.trash_drop_y)
                    self.autobot.auto_open_fishes = data.get("auto_open_fishes", self.autobot.auto_open_fishes)
                    self.autobot.auto_mode_min_mins = data.get("auto_mode_min_mins", self.autobot.auto_mode_min_mins)
                    self.autobot.auto_mode_max_mins = data.get("auto_mode_max_mins", self.autobot.auto_mode_max_mins)
                    self.autobot.auto_weight_terminator = data.get("auto_weight_terminator", self.autobot.auto_weight_terminator)
                    self.autobot.auto_weight_esports = data.get("auto_weight_esports", self.autobot.auto_weight_esports)
                    self.autobot.auto_weight_safe = data.get("auto_weight_safe", self.autobot.auto_weight_safe)
                    self.autobot.use_armor_trick = data.get("use_armor_trick", self.autobot.use_armor_trick)
                    self.autobot.auto_drop_trash = data.get("auto_drop_trash", self.autobot.auto_drop_trash)
                    self.autobot.use_fatigue_system = data.get("use_fatigue_system", self.autobot.use_fatigue_system)
                    self.autobot.ignored_fishes = data.get("ignored_fishes", self.autobot.ignored_fishes)
                    self.autobot.custom_fishes = data.get("custom_fishes", self.autobot.custom_fishes)
                    self.autobot.use_fish_ocr = data.get("use_fish_ocr", self.autobot.use_fish_ocr)
                    self.autobot.chat_region_x = data.get("chat_region_x", self.autobot.chat_region_x)
                    self.autobot.chat_region_y = data.get("chat_region_y", self.autobot.chat_region_y)
                    self.autobot.chat_region_w = data.get("chat_region_w", self.autobot.chat_region_w)
                    self.autobot.chat_region_h = data.get("chat_region_h", self.autobot.chat_region_h)
                    # Human — reaksiyon & tıklama
                    self.human.reaction_min = data.get("reaction_min", self.human.reaction_min)
                    self.human.reaction_max = data.get("reaction_max", self.human.reaction_max)
                    self.human.click_cooldown = data.get("click_cooldown", self.human.click_cooldown)
                    self.human.aim_offset_px = data.get("aim_offset_px", self.human.aim_offset_px)
                    self.human.horizontal_jitter_px = data.get("horizontal_jitter_px", self.human.horizontal_jitter_px)
                    # Human — prediction
                    self.human.prediction_look_ahead_base = data.get("prediction_look_ahead_base", self.human.prediction_look_ahead_base)
                    self.human.prediction_look_ahead_max = data.get("prediction_look_ahead_max", self.human.prediction_look_ahead_max)
                    self.human.prediction_speed_threshold = data.get("prediction_speed_threshold", self.human.prediction_speed_threshold)
                    self.human.prediction_max_lead_px = data.get("prediction_max_lead_px", self.human.prediction_max_lead_px)
                    self.human.prediction_lead_factor = data.get("prediction_lead_factor", self.human.prediction_lead_factor)
                    self.human.click_inner_margin = data.get("click_inner_margin", self.human.click_inner_margin)
                    # Human — anti-cheat
                    self.human.use_gaussian_jitter = data.get("use_gaussian_jitter", self.human.use_gaussian_jitter)
                    self.human.use_micro_movement = data.get("use_micro_movement", self.human.use_micro_movement)
                    self.human.detection_blind_spot_rate = data.get("detection_blind_spot_rate", self.human.detection_blind_spot_rate)
                    self.human.transition_hesitation_min = data.get("transition_hesitation_min", self.human.transition_hesitation_min)
                    self.human.transition_hesitation_max = data.get("transition_hesitation_max", self.human.transition_hesitation_max)
                    self.human.prediction_noise_sigma = data.get("prediction_noise_sigma", self.human.prediction_noise_sigma)
                    self.human.use_dynamic_rhythm = data.get("use_dynamic_rhythm", self.human.use_dynamic_rhythm)
                    self.human.rhythm_noise_sigma = data.get("rhythm_noise_sigma", self.human.rhythm_noise_sigma)
                    self.human.intentional_miss_rate = data.get("intentional_miss_rate", self.human.intentional_miss_rate)
                    self.human.fast_fish_miss_rate = data.get("fast_fish_miss_rate", self.human.fast_fish_miss_rate)
                    self.human.use_fps_jitter = data.get("use_fps_jitter", self.human.use_fps_jitter)
                    self.human.fps_jitter_rate = data.get("fps_jitter_rate", self.human.fps_jitter_rate)
                    self.human.targeting_mode = data.get("targeting_mode", self.human.targeting_mode)
                    # Fish
                    self.fish.fish_body_offset_y = data.get("fish_body_offset_y", self.fish.fish_body_offset_y)
                    # AutoBot
                    self.autobot.max_clicks_per_minigame = data.get("max_clicks_per_minigame", self.autobot.max_clicks_per_minigame)
                    self.autobot.timing_randomization = data.get("timing_randomization", self.autobot.timing_randomization)
                    self.autobot.delay_after_bait = data.get("delay_after_bait", self.autobot.delay_after_bait)
                    self.autobot.retry_cast_timeout = data.get("retry_cast_timeout", self.autobot.retry_cast_timeout)
                    self.autobot.trash_drop_x = data.get("trash_drop_x", self.autobot.trash_drop_x)
                    self.autobot.trash_drop_y = data.get("trash_drop_y", self.autobot.trash_drop_y)
            except Exception as e:
                print(f"Ayarlar yuklenemedi: {e}")
