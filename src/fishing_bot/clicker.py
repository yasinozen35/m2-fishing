"""
clicker.py — İnsan benzeri mouse kontrol modülü.

Makine hızında değil, süper-insan hızında tıklama yapar.
Rastgele reaksiyon gecikmesi, doğal mouse hareketi ve
hafif koordinat sapması ile insan davranışını simüle eder.
"""

import random
import time

import pyautogui

from fishing_bot.config import HumanConfig, CaptureConfig


# PyAutoGUI güvenlik ayarları.
pyautogui.FAILSAFE = True       # Sol üst köşeye gidince program durur.
pyautogui.PAUSE = 0.0           # Otomatik bekleme yok (biz kendimiz yönetiyoruz).


class HumanClicker:
    """İnsan benzeri tıklama motoru."""

    def __init__(
        self,
        human_config: HumanConfig,
        capture_config: CaptureConfig,
    ):
        self._human = human_config
        self._capture = capture_config
        self._last_click_time: float = 0.0

    def click_at(self, local_x: int, local_y: int) -> bool:
        """
        Belirtilen yerel koordinata insan benzeri tıklama yapar.

        Koordinatlar yakalama bölgesi içindeki yerel koordinatlardır.
        Gerçek ekran koordinatına çevrilir.

        Args:
            local_x: Yakalama bölgesi içindeki X koordinatı.
            local_y: Yakalama bölgesi içindeki Y koordinatı.

        Returns:
            True: Tıklama başarıyla yapıldı.
            False: Cooldown nedeniyle tıklama yapılmadı.
        """
        # Cooldown kontrolü.
        now = time.time()
        elapsed = now - self._last_click_time
        if elapsed < self._human.click_cooldown:
            return False

        # ── 1. Reaksiyon gecikmesi (80-200ms) ──
        delay = random.uniform(
            self._human.reaction_min,
            self._human.reaction_max,
        )
        time.sleep(delay)

        # ── 2. Yerel koordinatı ekran koordinatına çevir ──
        scale = self._capture.display_scale
        screen_x = self._capture.left + (local_x // scale)
        screen_y = self._capture.top + (local_y // scale)

        # ── 3. Hafif koordinat sapması (±N px) ──
        offset = self._human.aim_offset_px
        jitter_x = random.randint(-offset, offset)
        jitter_y = random.randint(-offset, offset)
        final_x = screen_x + jitter_x
        final_y = screen_y + jitter_y

        # ── 4. Mouse'u doğal hızda hareket ettir (50-120ms) ──
        move_duration = random.uniform(
            self._human.mouse_speed_min,
            self._human.mouse_speed_max,
        )
        pyautogui.moveTo(final_x, final_y, duration=move_duration)

        # ── 5. Tıkla ──
        pyautogui.click()

        self._last_click_time = time.time()
        return True

    @property
    def cooldown_remaining(self) -> float:
        """Kalan cooldown süresi (saniye). 0 ise tıklamaya hazır."""
        elapsed = time.time() - self._last_click_time
        remaining = self._human.click_cooldown - elapsed
        return max(0.0, remaining)

    @property
    def is_ready(self) -> bool:
        """Tıklamaya hazır mı (cooldown bitmiş mi)."""
        return self.cooldown_remaining <= 0.0

    def press_key(self, key: str) -> None:
        """
        Belirtilen tuşa insan benzeri bir sürede basar ve bırakır.
        
        Args:
            key: Basılacak tuş (ör: '1', 'space', 'i')
        """
        # İnsan tuşa anında basıp bırakamaz, ufak bir gecikme olur.
        hold_time = random.uniform(0.05, 0.12)
        
        pyautogui.keyDown(key)
        time.sleep(hold_time)
        pyautogui.keyUp(key)

    def right_click_at(self, screen_x: int, screen_y: int) -> None:
        """
        Belirtilen ekran koordinatına (Global koordinat) insan benzeri sağ tıklar.
        Zırh değişimi ve envanter yönetimi için kullanılır.
        """
        # Mouse'u doğal hızda hareket ettir
        move_duration = random.uniform(
            self._human.mouse_speed_min,
            self._human.mouse_speed_max,
        )
        pyautogui.moveTo(screen_x, screen_y, duration=move_duration)
        
        # Ufak bir gecikme
        time.sleep(random.uniform(0.05, 0.1))
        
        # Sağ tıkla
        pyautogui.click(button='right')
