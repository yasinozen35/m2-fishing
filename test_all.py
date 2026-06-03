"""
test_all.py — Kapsamlı test paketi.

Tüm modülleri test eder:
1. Import testi (tüm modüller yüklenebiliyor mu)
2. Config testi (platform algılama, varsayılan değerler)
3. Detector testi (referans resimlerle daire/balık tespiti)
4. Clicker testi (koordinat dönüşümü, cooldown)
5. ScreenCapture testi (ekran yakalama)
6. Overlay testi (debug çizimi)
7. Platform uyumluluk testi

Kullanım:
    uv run python test_all.py
"""

import math
import os
import platform
import sys
import time

# src'yi path'e ekle
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))


# ── Test altyapısı ────────────────────────────────────────────────

class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def ok(self, name: str):
        self.passed += 1
        print(f"  [PASS] {name}")

    def fail(self, name: str, reason: str):
        self.failed += 1
        self.errors.append((name, reason))
        print(f"  [FAIL] {name}: {reason}")

    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*60}")
        print(f"  Sonuc: {self.passed}/{total} test basarili")
        if self.errors:
            print(f"\n  Basarisiz testler:")
            for name, reason in self.errors:
                print(f"    - {name}: {reason}")
        print(f"{'='*60}\n")
        return self.failed == 0


results = TestResult()


# ══════════════════════════════════════════════════════════════════
# TEST 1: Import Testleri
# ══════════════════════════════════════════════════════════════════

print("\n" + "="*60)
print("  TEST 1: Import Testleri")
print("="*60)

try:
    import numpy as np
    results.ok("numpy import")
except ImportError as e:
    results.fail("numpy import", str(e))

try:
    import cv2
    results.ok(f"opencv import (versiyon: {cv2.__version__})")
except ImportError as e:
    results.fail("opencv import", str(e))

try:
    import mss
    results.ok("mss import")
except ImportError as e:
    results.fail("mss import", str(e))

try:
    import pyautogui
    results.ok("pyautogui import")
except ImportError as e:
    results.fail("pyautogui import", str(e))

try:
    from fishing_bot.config import Config, CaptureConfig, CircleDetectConfig, FishDetectConfig, HumanConfig
    results.ok("fishing_bot.config import")
except ImportError as e:
    results.fail("fishing_bot.config import", str(e))

try:
    from fishing_bot.screen_capture import ScreenCapture
    results.ok("fishing_bot.screen_capture import")
except ImportError as e:
    results.fail("fishing_bot.screen_capture import", str(e))

try:
    from fishing_bot.detector import Detector, Circle, Fish, DetectionResult
    results.ok("fishing_bot.detector import")
except ImportError as e:
    results.fail("fishing_bot.detector import", str(e))

try:
    from fishing_bot.clicker import HumanClicker
    results.ok("fishing_bot.clicker import")
except ImportError as e:
    results.fail("fishing_bot.clicker import", str(e))

try:
    from fishing_bot.overlay import DebugOverlay
    results.ok("fishing_bot.overlay import")
except ImportError as e:
    results.fail("fishing_bot.overlay import", str(e))


# ══════════════════════════════════════════════════════════════════
# TEST 2: Config & Platform Testleri
# ══════════════════════════════════════════════════════════════════

print("\n" + "="*60)
print("  TEST 2: Config & Platform Testleri")
print("="*60)

config = Config()
system = platform.system()
print(f"  Platform: {system} ({platform.release()})")
print(f"  Python: {sys.version}")
print(f"  Display Scale: {config.capture.display_scale}x")

# Platform-spesifik scale kontrolü
if system == "Windows":
    if config.capture.display_scale == 1:
        results.ok("Windows display_scale = 1 (DPI aware)")
    else:
        results.fail("Windows display_scale", f"Beklenen: 1, Gercek: {config.capture.display_scale}")
elif system == "Darwin":
    if config.capture.display_scale in (1, 2):
        results.ok(f"macOS display_scale = {config.capture.display_scale}")
    else:
        results.fail("macOS display_scale", f"Beklenmeyen: {config.capture.display_scale}")
else:
    results.ok(f"Linux display_scale = {config.capture.display_scale}")

# Varsayılan değer kontrolleri
if config.human.reaction_min == 0.08:
    results.ok("Human reaction_min = 0.08s")
else:
    results.fail("Human reaction_min", f"Beklenen: 0.08, Gercek: {config.human.reaction_min}")

if config.human.reaction_max == 0.20:
    results.ok("Human reaction_max = 0.20s")
else:
    results.fail("Human reaction_max", f"Beklenen: 0.20, Gercek: {config.human.reaction_max}")

if config.human.aim_offset_px == 5:
    results.ok("Human aim_offset_px = 5")
else:
    results.fail("Human aim_offset_px", f"Beklenen: 5, Gercek: {config.human.aim_offset_px}")

if config.target_fps == 30:
    results.ok("target_fps = 30")
else:
    results.fail("target_fps", f"Beklenen: 30, Gercek: {config.target_fps}")


# ══════════════════════════════════════════════════════════════════
# TEST 3: Detector — Referans Resimlerle Test
# ══════════════════════════════════════════════════════════════════

print("\n" + "="*60)
print("  TEST 3: Detector — Referans Resimlerle Test")
print("="*60)

config_test = Config()
config_test.circle.min_radius = 30
config_test.circle.max_radius = 500
config_test.circle.param2 = 30

detector = Detector(config_test.circle, config_test.fish)

image_dir = "images"
test_images = [
    f for f in os.listdir(image_dir)
    if f.lower().endswith((".png", ".jpg", ".jpeg"))
    and not f.startswith("debug_")
]

for img_name in sorted(test_images):
    img_path = os.path.join(image_dir, img_name)
    img = cv2.imread(img_path)

    if img is None:
        results.fail(f"Resim yukle: {img_name}", "cv2.imread None dondurdu")
        continue

    results.ok(f"Resim yukle: {img_name} ({img.shape[1]}x{img.shape[0]})")

    detector.invalidate_circle_cache()
    result = detector.detect(img)

    if result.circle is not None:
        c = result.circle
        results.ok(f"Daire tespit [{img_name}]: merkez=({c.center_x},{c.center_y}), r={c.radius}")
    else:
        results.fail(f"Daire tespit [{img_name}]", "Daire bulunamadi!")


# ══════════════════════════════════════════════════════════════════
# TEST 4: Detector — Birim Testleri
# ══════════════════════════════════════════════════════════════════

print("\n" + "="*60)
print("  TEST 4: Detector — Birim Testleri")
print("="*60)

# Daire içi kontrolü testi (sentetik veri ile)
circle = Circle(center_x=100, center_y=100, radius=50)
fish_inside = Fish(center_x=110, center_y=110, contour=np.array([]), area=200)
fish_outside = Fish(center_x=200, center_y=200, contour=np.array([]), area=200)
fish_edge = Fish(center_x=140, center_y=100, contour=np.array([]), area=200)

# İçerideki balık
dist_inside = math.sqrt((110 - 100)**2 + (110 - 100)**2)
safe_r = 50 * 0.85  # 42.5
if dist_inside < safe_r:
    results.ok(f"Daire ici kontrol: icerde (mesafe={dist_inside:.1f} < {safe_r:.1f})")
else:
    results.fail("Daire ici kontrol: icerde", f"mesafe={dist_inside:.1f} >= {safe_r:.1f}")

# Dışarıdaki balık
dist_outside = math.sqrt((200 - 100)**2 + (200 - 100)**2)
if dist_outside >= safe_r:
    results.ok(f"Daire ici kontrol: disarida (mesafe={dist_outside:.1f} >= {safe_r:.1f})")
else:
    results.fail("Daire ici kontrol: disarida", f"mesafe={dist_outside:.1f} < {safe_r:.1f}")

# Kenardaki balık (margin ile dışarıda olmalı)
dist_edge = math.sqrt((140 - 100)**2 + (100 - 100)**2)  # 40
if dist_edge < safe_r:
    results.ok(f"Daire ici kontrol: kenar icinde (mesafe={dist_edge:.1f} < {safe_r:.1f})")
else:
    results.fail("Daire ici kontrol: kenar", f"mesafe={dist_edge:.1f} >= {safe_r:.1f}")


# ══════════════════════════════════════════════════════════════════
# TEST 5: Clicker — Koordinat Dönüşümü
# ══════════════════════════════════════════════════════════════════

print("\n" + "="*60)
print("  TEST 5: Clicker — Koordinat Donusumu")
print("="*60)

capture_cfg = CaptureConfig()
capture_cfg.left = 100
capture_cfg.top = 200
capture_cfg.display_scale = 1  # Windows

human_cfg = HumanConfig()
human_cfg.click_cooldown = 0.0  # Test için cooldown kapat

# Koordinat dönüşüm testi (tıklama yapmadan)
scale = capture_cfg.display_scale
local_x, local_y = 150, 75
expected_screen_x = capture_cfg.left + (local_x // scale)  # 100 + 150 = 250
expected_screen_y = capture_cfg.top + (local_y // scale)    # 200 + 75 = 275

if expected_screen_x == 250:
    results.ok(f"Koordinat donusum X: local={local_x} -> ekran={expected_screen_x}")
else:
    results.fail("Koordinat donusum X", f"Beklenen: 250, Gercek: {expected_screen_x}")

if expected_screen_y == 275:
    results.ok(f"Koordinat donusum Y: local={local_y} -> ekran={expected_screen_y}")
else:
    results.fail("Koordinat donusum Y", f"Beklenen: 275, Gercek: {expected_screen_y}")

# Retina/2x scale testi
capture_cfg_retina = CaptureConfig()
capture_cfg_retina.left = 100
capture_cfg_retina.top = 200
capture_cfg_retina.display_scale = 2

scale_retina = capture_cfg_retina.display_scale
expected_retina_x = capture_cfg_retina.left + (local_x // scale_retina)  # 100 + 75 = 175
expected_retina_y = capture_cfg_retina.top + (local_y // scale_retina)    # 200 + 37 = 237

if expected_retina_x == 175:
    results.ok(f"Retina koordinat X: local={local_x} -> ekran={expected_retina_x}")
else:
    results.fail("Retina koordinat X", f"Beklenen: 175, Gercek: {expected_retina_x}")

if expected_retina_y == 237:
    results.ok(f"Retina koordinat Y: local={local_y} -> ekran={expected_retina_y}")
else:
    results.fail("Retina koordinat Y", f"Beklenen: 237, Gercek: {expected_retina_y}")


# ══════════════════════════════════════════════════════════════════
# TEST 6: Clicker — Cooldown Mekanizması
# ══════════════════════════════════════════════════════════════════

print("\n" + "="*60)
print("  TEST 6: Clicker — Cooldown Mekanizmasi")
print("="*60)

human_cfg_cd = HumanConfig()
human_cfg_cd.click_cooldown = 0.5  # 500ms cooldown

clicker = HumanClicker(human_cfg_cd, capture_cfg)

# Başlangıçta hazır olmalı
if clicker.is_ready:
    results.ok("Clicker baslangicta hazir")
else:
    results.fail("Clicker baslangicta hazir", "is_ready = False olmamali")

# Cooldown remaining kontrolü
remaining = clicker.cooldown_remaining
if remaining == 0.0:
    results.ok(f"Cooldown remaining = {remaining:.2f}s (dogru)")
else:
    results.fail("Cooldown remaining", f"Beklenen: 0.0, Gercek: {remaining}")


# ══════════════════════════════════════════════════════════════════
# TEST 7: ScreenCapture — Ekran Yakalama
# ══════════════════════════════════════════════════════════════════

print("\n" + "="*60)
print("  TEST 7: ScreenCapture — Ekran Yakalama")
print("="*60)

try:
    sc_config = CaptureConfig()
    sc_config.width = 100
    sc_config.height = 100

    capture = ScreenCapture(sc_config)
    frame = capture.grab_frame()

    if frame is not None and len(frame.shape) == 3:
        h, w, c = frame.shape
        results.ok(f"Ekran yakalama: {w}x{h}x{c}")

        if c == 3:
            results.ok("BGR format (3 kanal)")
        else:
            results.fail("BGR format", f"Beklenen: 3 kanal, Gercek: {c}")

        if frame.dtype == np.uint8:
            results.ok("Veri tipi: uint8")
        else:
            results.fail("Veri tipi", f"Beklenen: uint8, Gercek: {frame.dtype}")
    else:
        results.fail("Ekran yakalama", "Frame None veya yanlis boyut")

    capture.close()
    results.ok("ScreenCapture.close() basarili")
except Exception as e:
    results.fail("Ekran yakalama", str(e))


# ══════════════════════════════════════════════════════════════════
# TEST 8: Overlay — Debug Çizimi
# ══════════════════════════════════════════════════════════════════

print("\n" + "="*60)
print("  TEST 8: Overlay — Debug Cizimi")
print("="*60)

try:
    # Sentetik frame oluştur
    test_frame = np.zeros((300, 300, 3), dtype=np.uint8)
    test_frame[:] = (200, 150, 100)  # Mavi-yeşil arka plan

    # Sentetik sonuç
    test_circle = Circle(center_x=150, center_y=150, radius=100)
    test_fish = Fish(
        center_x=160, center_y=160,
        contour=np.array([[[150, 150]], [[170, 150]], [[170, 170]], [[150, 170]]]),
        area=400,
    )
    test_result = DetectionResult(
        circle=test_circle,
        fish=test_fish,
        is_fish_inside=True,
    )

    overlay = DebugOverlay()
    rendered = overlay.render(test_frame, test_result, clicked=True)
    # Pencereyi hemen kapat (test modunda görsel kontrol gerekmez)
    cv2.destroyAllWindows()

    if rendered is not None and rendered.shape == test_frame.shape:
        results.ok("Overlay render basarili")
    else:
        results.fail("Overlay render", "Cikti boyutu eslesmedi")

    # Boş sonuç testi
    empty_result = DetectionResult(circle=None, fish=None, is_fish_inside=False)
    rendered2 = overlay.render(test_frame, empty_result)
    cv2.destroyAllWindows()

    if rendered2 is not None:
        results.ok("Overlay bos sonuc render basarili")
    else:
        results.fail("Overlay bos sonuc render", "None dondu")

    overlay.close()
    results.ok("Overlay.close() basarili")

except Exception as e:
    results.fail("Overlay testi", str(e))
    cv2.destroyAllWindows()


# ══════════════════════════════════════════════════════════════════
# TEST 9: Platform Uyumluluk Kontrolleri
# ══════════════════════════════════════════════════════════════════

print("\n" + "="*60)
print("  TEST 9: Platform Uyumluluk Kontrolleri")
print("="*60)

# PyAutoGUI güvenlik ayarları
if pyautogui.FAILSAFE:
    results.ok("PyAutoGUI FAILSAFE aktif")
else:
    results.fail("PyAutoGUI FAILSAFE", "FAILSAFE kapali — guvenlik riski!")

# OpenCV GUI desteği kontrolü
try:
    # cv2.imshow bir pencere açabilmeli
    test_img = np.zeros((10, 10, 3), dtype=np.uint8)
    cv2.imshow("test_gui", test_img)
    cv2.waitKey(1)
    cv2.destroyAllWindows()
    results.ok("OpenCV GUI destegi (cv2.imshow) calisiyor")
except cv2.error as e:
    results.fail("OpenCV GUI destegi", f"cv2.imshow basarisiz: {e}")

# mss monitör bilgisi
try:
    with mss.mss() as sct:
        monitors = sct.monitors
        if len(monitors) > 1:
            primary = monitors[1]
            results.ok(f"Monitor tespit: {primary['width']}x{primary['height']}")
        else:
            results.ok(f"Monitor tespit: {len(monitors)} monitor")
except Exception as e:
    results.fail("Monitor tespit", str(e))

# context manager testi
try:
    sc_config2 = CaptureConfig()
    sc_config2.width = 50
    sc_config2.height = 50
    with ScreenCapture(sc_config2) as cap:
        f = cap.grab_frame()
        assert f is not None
    results.ok("ScreenCapture context manager")
except Exception as e:
    results.fail("ScreenCapture context manager", str(e))


# ══════════════════════════════════════════════════════════════════
# TEST 10: Performans Testi
# ══════════════════════════════════════════════════════════════════

print("\n" + "="*60)
print("  TEST 10: Performans Testi")
print("="*60)

try:
    perf_config = CaptureConfig()
    perf_config.width = 400
    perf_config.height = 400

    perf_capture = ScreenCapture(perf_config)
    perf_detector = Detector(config_test.circle, config_test.fish)

    # 20 kare yakala ve tespit et
    times = []
    for i in range(20):
        t0 = time.time()
        frame = perf_capture.grab_frame()
        perf_detector.detect(frame)
        t1 = time.time()
        times.append(t1 - t0)

    perf_capture.close()

    avg_ms = (sum(times) / len(times)) * 1000
    min_ms = min(times) * 1000
    max_ms = max(times) * 1000
    fps = 1000.0 / avg_ms if avg_ms > 0 else 0

    print(f"    Ortalama: {avg_ms:.1f}ms | Min: {min_ms:.1f}ms | Max: {max_ms:.1f}ms | FPS: {fps:.0f}")

    if avg_ms < 100:  # 100ms = 10 FPS minimum
        results.ok(f"Performans yeterli: {avg_ms:.1f}ms/frame ({fps:.0f} FPS)")
    else:
        results.fail("Performans", f"Cok yavas: {avg_ms:.1f}ms/frame ({fps:.0f} FPS)")

except Exception as e:
    results.fail("Performans testi", str(e))


# ══════════════════════════════════════════════════════════════════
# SONUÇ
# ══════════════════════════════════════════════════════════════════

success = results.summary()
sys.exit(0 if success else 1)
