"""
detector.py — Daire ve balık tespit modülü.

OpenCV ile ekran görüntüsünden:
1. Hough Circle Transform ile büyük daireyi tespit eder.
2. HSV renk filtreleme + contour analizi ile balık siluetini bulur.
3. Balığın dairenin içinde olup olmadığını matematiksel olarak kontrol eder.
"""

import math
import os
import glob
from dataclasses import dataclass

import cv2
import numpy as np

from fishing_bot.config import CircleDetectConfig, FishDetectConfig


@dataclass
class Circle:
    """Tespit edilen daire bilgisi."""
    center_x: int
    center_y: int
    radius: int


@dataclass
class Fish:
    """Tespit edilen balık bilgisi."""
    center_x: int
    center_y: int
    contour: np.ndarray
    area: float


@dataclass
class DetectionResult:
    """Bir karenin tespit sonuçları."""
    circle: Circle | None
    fish: Fish | None
    is_fish_inside: bool


class Detector:
    """Daire ve balık tespit motoru."""

    def __init__(
        self,
        circle_config: CircleDetectConfig,
        fish_config: FishDetectConfig,
    ):
        self._circle_cfg = circle_config
        self._fish_cfg = fish_config

        # Daire cache mekanizması.
        self._cached_circle: Circle | None = None
        self._cache_counter: int = 0

        # Morfolojik işlem kerneli (gürültü temizleme).
        k = fish_config.morph_kernel_size
        self._morph_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))

        # Envanter template'leri
        self._fish_templates = []
        self._bait_templates = []
        self._trash_templates = []
        self._load_templates()

    def _load_templates(self) -> None:
        """templates klasöründeki balık resimlerini (şablonları) yükler."""
        template_dir = os.path.join(os.path.dirname(__file__), "templates")
        if not os.path.exists(template_dir):
            return
            
        for img_path in glob.glob(os.path.join(template_dir, "*.png")):
            filename = os.path.basename(img_path)
            tpl = cv2.imread(img_path)
            if tpl is not None:
                if filename.startswith("bait_"):
                    self._bait_templates.append(tpl)
                elif filename.startswith("trash_"):
                    self._trash_templates.append(tpl)
                else:
                    self._fish_templates.append(tpl)

    def detect(self, frame: np.ndarray) -> DetectionResult:
        """
        Tek bir karede daire ve balık tespiti yapar.

        Args:
            frame: BGR formatında (H, W, 3) görüntü.

        Returns:
            DetectionResult: Tespit sonuçları.
        """
        circle = self._detect_circle(frame)
        fish = self._detect_fish(frame, circle)
        is_inside = self._is_fish_inside_circle(circle, fish)

        return DetectionResult(
            circle=circle,
            fish=fish,
            is_fish_inside=is_inside,
        )

    # ── Daire Tespiti ──────────────────────────────────────────────

    def _detect_circle(self, frame: np.ndarray) -> Circle | None:
        """
        Hough Circle Transform ile büyük daireyi tespit eder.
        Cache mekanizması ile her karede yeniden hesaplamaz.
        """
        # Cache hala geçerliyse, cached değeri döndür.
        if self._cached_circle is not None and self._cache_counter > 0:
            self._cache_counter -= 1
            return self._cached_circle

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (9, 9), 2)

        cfg = self._circle_cfg
        circles = cv2.HoughCircles(
            gray,
            cv2.HOUGH_GRADIENT,
            dp=cfg.dp,
            minDist=cfg.min_dist,
            param1=cfg.param1,
            param2=cfg.param2,
            minRadius=cfg.min_radius,
            maxRadius=cfg.max_radius,
        )

        if circles is None:
            self._cached_circle = None
            return None

        # En büyük yarıçaplı daireyi seç.
        circles = np.uint16(np.around(circles))
        best = max(circles[0], key=lambda c: c[2])

        detected = Circle(
            center_x=int(best[0]),
            center_y=int(best[1]),
            radius=int(best[2]),
        )

        # Cache'e kaydet.
        self._cached_circle = detected
        self._cache_counter = cfg.cache_ttl_frames

        return detected

    def invalidate_circle_cache(self) -> None:
        """Daire cache'ini temizler (kalibrasyon sonrası vb.)."""
        self._cached_circle = None
        self._cache_counter = 0

    # ── Balık Tespiti ──────────────────────────────────────────────

    def _detect_fish(
        self,
        frame: np.ndarray,
        circle: Circle | None,
    ) -> Fish | None:
        """
        Balık siluetini tespit eder.
        Süper Hızlı Adaptive Threshold yöntemi kullanılır.
        """
        cfg = self._fish_cfg

        # Daire ROI maskesi oluştur.
        mask_roi = None
        if circle is not None:
            mask_roi = np.zeros(frame.shape[:2], dtype=np.uint8)
            cv2.circle(
                mask_roi,
                (circle.center_x, circle.center_y),
                int(circle.radius * self._circle_cfg.inner_margin),
                255,
                -1,
            )

        # ── Süper Hızlı Adaptive Threshold ──
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        if mask_roi is not None:
            # Sadece ROI bölgesinin ortalamasını al (Suyun rengi)
            roi_pixels = gray[mask_roi > 0]
            if len(roi_pixels) == 0:
                return None
            mean_val = np.mean(roi_pixels)
        else:
            mean_val = np.mean(gray)

        # Ortalamadan N birim daha koyu pikselleri (gölgeyi/balığı) kabul et.
        threshold = max(0, int(mean_val - cfg.threshold_offset))
        mask = cv2.inRange(gray, 0, threshold)

        if mask_roi is not None:
            mask = cv2.bitwise_and(mask, mask_roi)

        return self._find_best_contour(mask, cfg)

    def _find_best_contour(
        self,
        mask: np.ndarray,
        cfg: FishDetectConfig,
    ) -> Fish | None:
        """Maskeden en uygun contour'u bulur ve Fish döndürür."""
        # Yüksek performanslı morfolojik işlemler (Gürültü temizleme).
        mask = cv2.erode(mask, self._morph_kernel, iterations=1)
        mask = cv2.dilate(mask, self._morph_kernel, iterations=1)

        mask = cv2.GaussianBlur(mask, (3, 3), 0)
        _, mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)

        contours, _ = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        if not contours:
            return None

        # SÜPER HIZLI OPTİMİZASYON: Tüm contour'lar üzerinde Python FOR döngüsü çevirmek 
        # (Özellikle su dalgaları binlerce gürültü oluşturduğunda) FPS'i 2'ye kadar düşürür ve bilgisayarı kilitler!
        # Bunun yerine C seviyesinde çalışan max() ile doğrudan en büyük parçayı buluyoruz.
        best_contour = max(contours, key=cv2.contourArea)
        best_area = cv2.contourArea(best_contour)

        # En büyük parça balık olmak için çok küçük veya çok büyükse (örn: Sadece su dalgasıysa) yoksay.
        if not (cfg.min_area <= best_area <= cfg.max_area):
            return None

        moments = cv2.moments(best_contour)
        if moments["m00"] == 0:
            return None

        cx = int(moments["m10"] / moments["m00"])
        cy = int(moments["m01"] / moments["m00"])

        return Fish(
            center_x=cx,
            center_y=cy,
            contour=best_contour,
            area=best_area,
        )

    # ── Daire İçi Kontrolü ─────────────────────────────────────────

    def _is_fish_inside_circle(
        self,
        circle: Circle | None,
        fish: Fish | None,
    ) -> bool:
        """
        Balığın dairenin iç bölgesinde olup olmadığını kontrol eder.

        Inner margin kullanılarak kenar bölgesi dışlanır
        (yanlış pozitif önleme).
        """
        if circle is None or fish is None:
            return False

        # Balık merkezi ile daire merkezi arası mesafe.
        distance = math.sqrt(
            (fish.center_x - circle.center_x) ** 2
            + (fish.center_y - circle.center_y) ** 2
        )

        # Dairenin iç güvenli bölgesi.
        safe_radius = circle.radius * self._circle_cfg.inner_margin

        return distance < safe_radius

    # ── Envanter Tespiti (Balık / Yem) ─────────────────────────────
    
    def detect_inventory_items(self, frame: np.ndarray, item_type: str = "fish", threshold: float = 0.8) -> list[tuple[int, int]]:
        """
        Envanterde bulunan itemlerin koordinatlarını döndürür.
        
        Args:
            frame: Tam ekran veya envanter bölgesini içeren görüntü.
            item_type: 'fish' (açılacak balıklar) veya 'bait' (yem yapılacak minik balıklar)
            threshold: Template matching eşik değeri (0.0 - 1.0)
            
        Returns:
            list[tuple[int, int]]: Bulunan itemlerin merkez koordinatları [(x, y), ...]
        """
        if item_type == "bait":
            templates = self._bait_templates
        elif item_type == "trash":
            templates = self._trash_templates
        else:
            templates = self._fish_templates
        
        if not templates:
            return []
            
        found_fishes = []
        
        for template in templates:
            th, tw = template.shape[:2]
            
            # Template matching yap
            result = cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED)
            locations = np.where(result >= threshold)
            
            # Bulunan tüm noktaların merkez koordinatlarını al
            for pt in zip(*locations[::-1]):
                center_x = pt[0] + tw // 2
                center_y = pt[1] + th // 2
                
                # Çok yakın koordinatları mükerrer olmaması için filtrele
                is_duplicate = False
                for (fx, fy) in found_fishes:
                    if abs(fx - center_x) < 10 and abs(fy - center_y) < 10:
                        is_duplicate = True
                        break
                        
                if not is_duplicate:
                    found_fishes.append((center_x, center_y))
                    
        return found_fishes
