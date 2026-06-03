"""
screen_capture.py — Ekran yakalama modülü.

mss kütüphanesi ile belirli bir ekran bölgesini yüksek hızda yakalar
ve OpenCV uyumlu NumPy array olarak döndürür.
"""

import numpy as np
import mss

from fishing_bot.config import CaptureConfig


class ScreenCapture:
    """Ekran yakalama yöneticisi."""

    def __init__(self, config: CaptureConfig):
        self._config = config
        self._sct = mss.MSS()
        self._monitor = {
            "top": config.top,
            "left": config.left,
            "width": config.width,
            "height": config.height,
        }

    @property
    def region(self) -> dict:
        """Aktif yakalama bölgesini döndürür."""
        return self._monitor.copy()

    def update_region(self, top: int, left: int, width: int, height: int) -> None:
        """Yakalama bölgesini günceller (kalibrasyon sonrası)."""
        self._monitor = {
            "top": top,
            "left": left,
            "width": width,
            "height": height,
        }
        self._config.top = top
        self._config.left = left
        self._config.width = width
        self._config.height = height

    def grab_frame(self) -> np.ndarray:
        """
        Ekrandan bir kare yakalar ve BGR formatında NumPy array döndürür.

        Returns:
            np.ndarray: BGR formatında (H, W, 3) şeklinde görüntü.
        """
        raw = self._sct.grab(self._monitor)
        # mss BGRA formatında döndürür, alpha kanalını atıp BGR'ye çeviriyoruz.
        frame = np.array(raw, dtype=np.uint8)
        return frame[:, :, :3]  # BGRA → BGR (alpha kanalını at)

    def grab_full_frame(self) -> np.ndarray:
        """
        Tüm ekranı yakalar ve BGR formatında döndürür.
        (Envanter araması gibi mutlak koordinat gereken durumlar için kullanılır).
        """
        # monitors[1] ana monitörü temsil eder
        monitor = self._sct.monitors[1]
        raw = self._sct.grab(monitor)
        frame = np.array(raw, dtype=np.uint8)
        return frame[:, :, :3]

    def close(self) -> None:
        """Kaynakları serbest bırakır."""
        self._sct.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
