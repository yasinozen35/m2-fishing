import os
import cv2
from fishing_bot.config import Config
from fishing_bot.detector import Detector
from fishing_bot.overlay import DebugOverlay

def debug_images():
    config = Config()
    config.circle.min_radius = 30
    config.circle.max_radius = 500
    config.circle.param2 = 30
    
    # Eşik değerini daha koyu pikselleri arayacak şekilde test edelim
    # (Botun şu anki hali mean_val - 25 kullanıyor)
    
    detector = Detector(config.circle, config.fish)
    overlay = DebugOverlay()
    
    image_dir = "images"
    test_images = [
        f for f in os.listdir(image_dir)
        if f.lower().endswith((".png", ".jpg", ".jpeg"))
        and not f.startswith("debug_")
    ]
    
    for img_name in test_images:
        img_path = os.path.join(image_dir, img_name)
        img = cv2.imread(img_path)
        if img is None: continue
        
        detector.invalidate_circle_cache()
        result = detector.detect(img)
        
        rendered = overlay.render(img, result, clicked=result.is_fish_inside)
        
        out_path = os.path.join(image_dir, f"debug_fish_{img_name}")
        cv2.imwrite(out_path, rendered)
        
        print(f"{img_name} -> Balık bulundu mu: {result.fish is not None}, İçeride mi: {result.is_fish_inside}")

if __name__ == "__main__":
    debug_images()
