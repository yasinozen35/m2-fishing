"""
test_detection.py — Referans resimlerle daire ve balık tespiti doğrulaması.

Bu script referans resimleri yükler ve tespit algoritmasının
doğru çalıştığını kontrol eder.
"""

import sys
import os

import cv2
import numpy as np

# src'yi path'e ekle
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from fishing_bot.config import Config
from fishing_bot.detector import Detector


def test_image(filepath: str, detector: Detector) -> None:
    """Tek bir resmi test eder."""
    print(f"\n{'='*60}")
    print(f"  Test: {os.path.basename(filepath)}")
    print(f"{'='*60}")

    img = cv2.imread(filepath)
    if img is None:
        print(f"  ❌ Resim yüklenemedi!")
        return

    print(f"  Boyut: {img.shape[1]}x{img.shape[0]} (WxH)")

    # Tespit
    result = detector.detect(img)

    # Daire
    if result.circle:
        c = result.circle
        print(f"  ✅ Daire bulundu:")
        print(f"     Merkez: ({c.center_x}, {c.center_y})")
        print(f"     Yarıçap: {c.radius}px")
    else:
        print(f"  ❌ Daire bulunamadı!")

    # Balık
    if result.fish:
        f = result.fish
        print(f"  ✅ Balık bulundu:")
        print(f"     Merkez: ({f.center_x}, {f.center_y})")
        print(f"     Alan: {f.area:.0f}px²")
    else:
        print(f"  ⚠️  Balık bulunamadı (resimde olmayabilir)")

    # Daire içi
    if result.is_fish_inside:
        print(f"  🎯 SONUÇ: Balık DAİRENİN İÇİNDE → TIKLA!")
    elif result.fish:
        print(f"  ⏳ SONUÇ: Balık dairenin DIŞINDA → Bekle")
    else:
        print(f"  ⏳ SONUÇ: Balık yok → Bekle")

    # Debug görüntü oluştur
    overlay = img.copy()
    if result.circle:
        c = result.circle
        cv2.circle(overlay, (c.center_x, c.center_y), c.radius, (0, 255, 0), 2)
        cv2.circle(overlay, (c.center_x, c.center_y), 4, (255, 255, 0), -1)
    if result.fish:
        f = result.fish
        color = (0, 255, 0) if result.is_fish_inside else (0, 0, 255)
        cv2.drawContours(overlay, [f.contour], -1, color, 2)
        cv2.circle(overlay, (f.center_x, f.center_y), 6, color, -1)

    # Sonucu kaydet
    basename = os.path.splitext(os.path.basename(filepath))[0]
    output_path = os.path.join("images", f"debug_{basename}.png")
    cv2.imwrite(output_path, overlay)
    print(f"  💾 Debug görüntü kaydedildi: {output_path}")


def main():
    print("\n🎣 Balık Tutma Botu — Tespit Doğrulaması\n")

    config = Config()
    # Test için daha geniş parametreler
    config.circle.min_radius = 30
    config.circle.max_radius = 500
    config.circle.param2 = 30

    detector = Detector(config.circle, config.fish)

    # Referans resimler
    image_dir = "images"
    images = [
        os.path.join(image_dir, f)
        for f in os.listdir(image_dir)
        if f.lower().endswith((".png", ".jpg", ".jpeg"))
        and not f.startswith("debug_")
    ]

    if not images:
        print("❌ images/ klasöründe resim bulunamadı!")
        return

    print(f"  {len(images)} referans resim bulundu.")

    for img_path in sorted(images):
        # Her resim için cache'i temizle (bağımsız test)
        detector.invalidate_circle_cache()
        test_image(img_path, detector)

    print(f"\n{'='*60}")
    print(f"  Tüm testler tamamlandı!")
    print(f"  Debug görüntüleri images/ klasörüne kaydedildi.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
