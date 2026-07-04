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
        self._button_yes_templates = []  # Normal + aktif hali
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
                elif filename.startswith("button_"):
                    self._button_yes_templates.append(tpl)
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

    def _verify_cached_circle(self, frame: np.ndarray, circle: Circle) -> bool:
        """
        Cache'teki çemberin hala ekranda olup olmadığını doğrular.
        Çember çevresinden 8 noktada beyaz piksel kontrolü yapar.
        Frame içindeki noktaların en az %60'ı beyaz olmalı.
        """
        import math
        cx, cy, r = circle.center_x, circle.center_y, circle.radius
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        white_points = 0
        total_checked = 0
        # 8 açı — daha fazla örnek, daha toleranslı
        for angle in [0, 45, 90, 135, 180, 225, 270, 315]:
            px = int(cx + r * 0.92 * math.cos(math.radians(angle)))
            py = int(cy + r * 0.92 * math.sin(math.radians(angle)))
            if 0 <= px < frame.shape[1] and 0 <= py < frame.shape[0]:
                total_checked += 1
                v = int(hsv[py, px, 2])
                s = int(hsv[py, px, 1])
                if v > 130 and s < 100:  # Daha toleranslı beyaz eşiği
                    white_points += 1
        # Frame içindeki noktaların en az %60'ı beyaz olmalı (en az 1 nokta)
        if total_checked == 0:
            return True  # Doğrulayamıyorsak varsayılan: geçerli
        return white_points >= max(1, total_checked * 0.6)

    def _detect_circle(self, frame: np.ndarray) -> Circle | None:
        """
        Hough Circle Transform ile büyük daireyi tespit eder.
        Cache mekanizması ile her karede yeniden hesaplamaz.
        Cache doğrulama: çember çevresinde beyaz piksel kontrolü.
        """
        # Cache hala geçerliyse döndür.
        if self._cached_circle is not None and self._cache_counter > 0:
            self._cache_counter -= 1
            # Her 6 frame'de bir doğrulama yap.
            # NOT: counter > 0 kontrolü ile ilk hit'te doğrulama yapmayı engelliyoruz
            # (counter 1'den 0'a düşer, 0 > 0 false → doğrulama atlanır).
            if self._cache_counter > 0 and self._cache_counter % 6 == 0:
                if not self._verify_cached_circle(frame, self._cached_circle):
                    self._cached_circle = None
                    self._cache_counter = 0
                    return None
            return self._cached_circle

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (9, 9), 2)

        cfg = self._circle_cfg

        # ── İKİ AŞAMALI DAİRE TESPİTİ ──
        # Aşama 1: Beyaz HSV maskesi ile (tercih edilen)
        # Aşama 2: Normal gray ile (fallback)
        best_circle = None

        for attempt, (use_mask, src_gray) in enumerate([
            (True, gray),       # Aşama 1: beyaz maskeli
            (False, gray),      # Aşama 2: normal gray
        ]):
            if use_mask:
                hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
                lower_white = np.array([0, 0, 120])
                upper_white = np.array([180, 120, 255])
                white_mask = cv2.inRange(hsv, lower_white, upper_white)
                search_gray = cv2.bitwise_and(src_gray, src_gray, mask=white_mask)
            else:
                search_gray = src_gray

            circles = cv2.HoughCircles(
                search_gray,
                cv2.HOUGH_GRADIENT,
                dp=cfg.dp,
                minDist=cfg.min_dist,
                param1=cfg.param1,
                param2=cfg.param2,
                minRadius=cfg.min_radius,
                maxRadius=cfg.max_radius,
            )

            if circles is not None:
                circles = np.uint16(np.around(circles))
                best = max(circles[0], key=lambda c: c[2])
                candidate = Circle(
                    center_x=int(best[0]),
                    center_y=int(best[1]),
                    radius=int(best[2]),
                )
                # İç bölge doğrulaması (sadece beyaz maskeli aşamada)
                if not use_mask or self._verify_circle_interior(frame, candidate):
                    best_circle = candidate
                    break  # Geçerli daire bulundu, diğer aşamaya geçme

        if best_circle is None:
            self._cached_circle = None
            return None

        # Cache'e kaydet.
        self._cached_circle = best_circle
        self._cache_counter = cfg.cache_ttl_frames

        return best_circle

    def _verify_circle_interior(self, frame: np.ndarray, circle: Circle) -> bool:
        """
        Tespit edilen çemberin iç bölgesinin su renginde olup olmadığını kontrol eder.
        Su: orta-yüksek saturation (mavi/yeşil), orta value.
        False dönerse tespit edilen şey oyun çemberi değildir.
        """
        cx, cy, r = circle.center_x, circle.center_y, circle.radius
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # Çemberin iç bölgesinden örnek al (merkeze yakın %25'lik alan)
        inner_r = max(5, int(r * 0.25))
        y1 = max(0, cy - inner_r)
        y2 = min(frame.shape[0], cy + inner_r)
        x1 = max(0, cx - inner_r)
        x2 = min(frame.shape[1], cx + inner_r)

        if y2 <= y1 or x2 <= x1:
            return False

        inner_region = hsv[y1:y2, x1:x2]
        avg_saturation = np.mean(inner_region[:, :, 1])
        avg_value = np.mean(inner_region[:, :, 2])

        # Su: orta-yüksek saturation (>15), orta value (30-235)
        # Siyah/gri düz renk: düşük saturation → sahte tespit
        # Daha toleranslı değerler (oyun içi aydınlatma farkları için)
        is_water = avg_saturation > 15 and 30 < avg_value < 235
        return is_water

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
        Balık siluetini HİBRİT yöntemle tespit eder:
        1. Adaptive Threshold: Sudan koyu pikselleri bulur
        2. HSV Gri Filtre: Gri tonları (balık) mavi/yeşil (su) ayrımı
        3. İki mask'ı BİRLEŞTİR — iki yöntem de aynı bölgeyi işaret ediyorsa balıktır
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

        # ── METHOD 1: Adaptive Threshold ──
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        if mask_roi is not None:
            roi_pixels = gray[mask_roi > 0]
            if len(roi_pixels) == 0:
                return None
            mean_val = np.mean(roi_pixels)
        else:
            mean_val = np.mean(gray)

        # Ortalamadan threshold_offset kadar koyu pikseller
        threshold = max(0, int(mean_val - cfg.threshold_offset))
        mask_adaptive = cv2.inRange(gray, 0, threshold)

        # ── METHOD 2: HSV Gri Tonlama Filtresi ──
        # Balık: gri (düşük saturation, orta value)
        # Su: mavi/yeşil (yüksek saturation) → FİLTRELENİR
        # Beyaz çember: yüksek value, düşük saturation → FİLTRELENİR
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        lower_gray = np.array([0, 0, 30])     # Düşük S, düşük V (koyu gri-siyah)
        upper_gray = np.array([180, 100, 200]) # Saturation < 100 (gevşek), Value 30-200
        mask_hsv = cv2.inRange(hsv, lower_gray, upper_gray)

        # ── HİBRİT BİRLEŞTİRME ──
        # İki mask'ın KESİŞİMİ: iki yöntem de balık diyorsa güvenilir
        mask_combined = cv2.bitwise_and(mask_adaptive, mask_hsv)

        # ROI ile sınırla
        if mask_roi is not None:
            mask_combined = cv2.bitwise_and(mask_combined, mask_roi)

        # Önce birleşik mask'ta ara. Bulamazsa adaptive-only mask'a dön (yeni balık tipleri için).
        result = self._find_best_contour(mask_combined, cfg, circle)
        if result is not None:
            return result

        # Fallback: sadece adaptive threshold (yeni/görülmemiş balık renkleri için)
        if mask_roi is not None:
            mask_adaptive = cv2.bitwise_and(mask_adaptive, mask_roi)
        return self._find_best_contour(mask_adaptive, cfg, circle)

    def _find_best_contour(
        self,
        mask: np.ndarray,
        cfg: FishDetectConfig,
        circle: Circle | None = None,
    ) -> Fish | None:
        """
        Maskeden en uygun contour'u bulur ve Fish döndürür.

        TOP-3 contour'u değerlendirir ve balıklık skoru hesaplar:
        - Alan puanı: orta boyut tercih edilir
        - Şekil puanı: width/height oranı 1.5-5.0 arası (uzun cisim = balık)
        - Pozisyon puanı: daire merkezine yakınlık
        - Vücut merkezi: bounding box yatay ortası, dikey %40'ı (kuyruktan kaçın)
        """
        # Morfolojik işlemler (gürültü temizleme — YUMUŞAK).
        # ÖNCE dilate (parçaları birleştir), SONRA erode (gereksiz genişlemeyi geri al).
        # Eskiden erode→dilate (opening) yapıyorduk ama bu küçük balıkları YOK EDİYORDU.
        # Şimdi dilate→erode (closing) ile önce parçaları birleştiriyoruz.
        small_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
        mask = cv2.dilate(mask, self._morph_kernel, iterations=1)
        mask = cv2.erode(mask, small_kernel, iterations=1)
        mask = cv2.GaussianBlur(mask, (3, 3), 0)
        _, mask = cv2.threshold(mask, 100, 255, cv2.THRESH_BINARY)  # 127→100 daha toleranslı

        contours, _ = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        if not contours:
            return None

        # Filtrelenmiş contour'ları topla (min/max alan arası)
        valid_contours = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if cfg.min_area <= area <= cfg.max_area:
                valid_contours.append(cnt)

        if not valid_contours:
            return None

        # En büyük 3 contour'u al (performans için C-level sırala)
        valid_contours.sort(key=cv2.contourArea, reverse=True)
        top_contours = valid_contours[:3]

        # Her contour için balıklık skoru hesapla
        best_score = -1.0
        best_contour = None
        circle_center = (circle.center_x, circle.center_y) if circle else None

        for cnt in top_contours:
            score = self._score_contour(cnt, circle_center)
            if score > best_score:
                best_score = score
                best_contour = cnt

        if best_contour is None:
            return None

        # Rotasyon-uyumlu gerçek vücut merkezini hesapla (Moments / Centroid)
        # Bounding box yerine Image Moments kullanarak balığın dönüş yönünden bağımsız
        # olarak tam kütle merkezini hedefleriz (böylece kuyruk yerine gövdeye tıklar).
        M = cv2.moments(best_contour)
        if M["m00"] != 0:
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
        else:
            # Fallback: Bounding box merkezi
            x, y, w, h = cv2.boundingRect(best_contour)
            cx = x + w // 2
            cy = y + h // 2

        return Fish(
            center_x=cx,
            center_y=cy,
            contour=best_contour,
            area=cv2.contourArea(best_contour),
        )

    def _score_contour(
        self,
        cnt: np.ndarray,
        circle_center: tuple[int, int] | None = None,
    ) -> float:
        """
        Bir contour'un balık olma ihtimalini skorlar (0.0 - 1.0).

        Puanlama:
        - Alan puanı (%30): ~300-1500px² ideal balık alanı
        - Şekil puanı (%40): width/height > 1.5 (uzun cisim = balık, yuvarlak = gürültü)
        - Pozisyon puanı (%30): daire merkezine yakınlık
        """
        area = cv2.contourArea(cnt)
        x, y, w, h = cv2.boundingRect(cnt)

        # ── Alan Puanı ──
        # İdeal alan ~500px² (orta boy balık). Çok küçük veya çok büyük düşük puan.
        ideal_area = 500.0
        area_deviation = abs(area - ideal_area) / max(ideal_area, 1.0)
        area_score = max(0.0, 1.0 - area_deviation)

        # ── Şekil Puanı ──
        # Balık uzun bir cisimdir. width/height oranı yüksekse balık ihtimali yüksek.
        if h > 0:
            aspect_ratio = w / h
            if 1.8 <= aspect_ratio <= 5.0:
                shape_score = 1.0  # İdeal balık şekli
            elif 1.2 <= aspect_ratio < 1.8:
                shape_score = 0.6  # Hafif oval, olabilir
            elif aspect_ratio > 5.0:
                shape_score = 0.4  # Çok uzun, muhtemelen yılan/dalga
            else:
                shape_score = 0.2  # Yuvarlak, muhtemelen gürültü
        else:
            shape_score = 0.0

        # ── Pozisyon Puanı ──
        if circle_center is not None:
            cx = x + w // 2
            cy = y + h // 2
            dist = math.hypot(cx - circle_center[0], cy - circle_center[1])
            # 200px içinde tam puan, uzaklaştıkça düşer
            pos_score = max(0.0, 1.0 - dist / 200.0)
        else:
            pos_score = 0.5  # Circle yoksa nötr

        # Ağırlıklı toplam
        return area_score * 0.30 + shape_score * 0.40 + pos_score * 0.30

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
    
    def detect_yes_button(self, frame: np.ndarray, threshold: float = 0.65) -> tuple[int, int] | None:
        """
        Ekrandaki "Yes/Evet" butonunu template matching ile bulur.
        Hem normal hem aktif (highlighted) halini dener.

        Args:
            frame: Tam ekran görüntü (BGR).
            threshold: Eşleşme eşiği (0.0 - 1.0).

        Returns:
            (x, y): Butonun merkez koordinatı, bulunamazsa None.
        """
        if not self._button_yes_templates:
            return None

        best_val = 0.0
        best_loc = None
        best_tw, best_th = 0, 0

        for tpl in self._button_yes_templates:
            th, tw = tpl.shape[:2]
            result = cv2.matchTemplate(frame, tpl, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            if max_val > best_val:
                best_val = max_val
                best_loc = max_loc
                best_tw, best_th = tw, th

        if best_val >= threshold and best_loc is not None:
            cx = best_loc[0] + best_tw // 2
            cy = best_loc[1] + best_th // 2
            return (cx, cy)
        return None

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
