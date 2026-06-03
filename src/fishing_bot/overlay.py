"""
overlay.py — Debug görselleştirme modülü.

Tespit edilen daire, balık ve durum bilgilerini
OpenCV penceresi üzerinde gösterir. Sadece debug modunda aktif.
"""

import time

import cv2
import numpy as np

from fishing_bot.detector import DetectionResult


class DebugOverlay:
    """Debug görselleştirme yöneticisi."""

    # Renk sabitleri (BGR).
    COLOR_CIRCLE = (0, 255, 0)         # Yeşil — daire
    COLOR_FISH_INSIDE = (0, 255, 0)    # Yeşil — balık içeride
    COLOR_FISH_OUTSIDE = (0, 0, 255)   # Kırmızı — balık dışarıda
    COLOR_CENTER = (255, 255, 0)       # Cyan — merkez noktası
    COLOR_TEXT_BG = (0, 0, 0)          # Siyah — metin arka planı
    COLOR_TEXT = (255, 255, 255)       # Beyaz — metin

    WINDOW_NAME = "Fishing Bot — Debug"

    def __init__(self):
        self._frame_count: int = 0
        self._fps_time: float = time.time()
        self._current_fps: float = 0.0

    def render(
        self,
        frame: np.ndarray,
        result: DetectionResult,
        clicked: bool = False,
    ) -> np.ndarray:
        """
        Frame üzerine debug bilgilerini çizer ve pencerede gösterir.

        Args:
            frame: Orijinal BGR frame (kopyası alınır).
            result: Tespit sonuçları.
            clicked: Bu karede tıklama yapıldı mı.

        Returns:
            Çizilmiş frame (debug amaçlı).
        """
        overlay = frame.copy()

        # ── Daire çiz ──
        if result.circle is not None:
            c = result.circle
            # Daire çevresi.
            cv2.circle(overlay, (c.center_x, c.center_y), c.radius, self.COLOR_CIRCLE, 2)
            # Merkez noktası.
            cv2.circle(overlay, (c.center_x, c.center_y), 4, self.COLOR_CENTER, -1)

        # ── Balık çiz ──
        if result.fish is not None:
            f = result.fish
            color = (
                self.COLOR_FISH_INSIDE if result.is_fish_inside
                else self.COLOR_FISH_OUTSIDE
            )
            # Contour çiz.
            cv2.drawContours(overlay, [f.contour], -1, color, 2)
            # Balık merkez noktası.
            cv2.circle(overlay, (f.center_x, f.center_y), 6, color, -1)
            # Etiket.
            label = "ICERDE!" if result.is_fish_inside else "Disarida"
            self._put_text(overlay, label, f.center_x + 10, f.center_y - 10, color)

        # ── Tıklama bildirimi ──
        if clicked:
            h, w = overlay.shape[:2]
            self._put_text(
                overlay, ">>> CLICK <<<", w // 2 - 60, 30,
                (0, 255, 255), scale=0.8, thickness=2
            )

        # ── FPS bilgisi ──
        self._update_fps()
        self._put_text(
            overlay, f"FPS: {self._current_fps:.1f}", 10, 25,
            self.COLOR_TEXT, scale=0.6
        )

        # ── Durum bilgisi ──
        status_parts = []
        if result.circle is not None:
            status_parts.append("Daire: OK")
        else:
            status_parts.append("Daire: YOK")

        if result.fish is not None:
            status_parts.append(f"Balik: ({result.fish.center_x},{result.fish.center_y})")
        else:
            status_parts.append("Balik: YOK")

        status = " | ".join(status_parts)
        h = overlay.shape[0]
        self._put_text(overlay, status, 10, h - 10, self.COLOR_TEXT, scale=0.5)

        # Pencerede göster.
        import platform
        import threading
        
        # MacOS (Darwin), UI (cv2.imshow) güncellemelerinin SADECE ana thread'den yapılmasına izin verir.
        # Botumuz BotRunnerThread (arka plan) içinde çalıştığı için Apple bunu bloklar ve Unknown C++ Exception fırlatır.
        # Bu yüzden Mac'te arka plan threadindeysek cv2 penceresi açılmasını engelliyoruz.
        is_mac_bg = platform.system() == "Darwin" and threading.current_thread() is not threading.main_thread()
        
        if not is_mac_bg:
            cv2.imshow(self.WINDOW_NAME, overlay)
            cv2.waitKey(1)

        return overlay

    def close(self) -> None:
        """Debug penceresini kapatır."""
        cv2.destroyAllWindows()

    def _update_fps(self) -> None:
        """FPS hesaplayıcı."""
        self._frame_count += 1
        now = time.time()
        elapsed = now - self._fps_time
        if elapsed >= 1.0:
            self._current_fps = self._frame_count / elapsed
            self._frame_count = 0
            self._fps_time = now

    @staticmethod
    def _put_text(
        img: np.ndarray,
        text: str,
        x: int,
        y: int,
        color: tuple,
        scale: float = 0.55,
        thickness: int = 1,
    ) -> None:
        """Arka planlı metin çizer (okunabilirlik için)."""
        font = cv2.FONT_HERSHEY_SIMPLEX
        (tw, th), _ = cv2.getTextSize(text, font, scale, thickness)
        # Arka plan dikdörtgeni.
        cv2.rectangle(img, (x - 2, y - th - 4), (x + tw + 2, y + 4), (0, 0, 0), -1)
        # Metin.
        cv2.putText(img, text, (x, y), font, scale, color, thickness, cv2.LINE_AA)
