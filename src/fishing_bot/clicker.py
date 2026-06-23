"""
clicker.py — İnsan benzeri mouse kontrol modülü.

Makine hızında değil, süper-insan hızında tıklama yapar.
Rastgele reaksiyon gecikmesi, doğal mouse hareketi ve
hafif koordinat sapması ile insan davranışını simüle eder.
"""

import random
import sys
import time
import math

import pyautogui

# Windows'ta PyDirectInput bile bazen oyun içi kilitlenmelere ve donmalara yol açıyor.
# Bu yüzden en düşük seviyeli donanım API'sini (Ctypes Win32) kendimiz yazıyoruz!
if sys.platform == "win32":
    import ctypes

    # Win32 Flag sabitleri
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    MOUSEEVENTF_RIGHTDOWN = 0x0008
    MOUSEEVENTF_RIGHTUP = 0x0010

    from fishing_bot.logitech import logitech_driver

    class Win32Clicker:
        """PyAutoGUI ve PyDirectInput'un yerini alacak Logitech G-HUB Tıklayıcı."""
        @staticmethod
        def moveTo(x, y):
            logitech_driver.move_to(int(x), int(y))
            
        @staticmethod
        def fastClick():
            logitech_driver.click(duration=random.uniform(0.020, 0.040))

        @staticmethod
        def click():
            logitech_driver.click(duration=random.uniform(0.07, 0.12))

        @staticmethod
        def rightClick():
            logitech_driver.click(button="right", duration=random.uniform(0.07, 0.12))

        @staticmethod
        def mouseDown(button='left'):
            logitech_driver.mouse_down(button=button)

        @staticmethod
        def mouseUp(button='left'):
            logitech_driver.mouse_up(button=button)
            
        @staticmethod
        def _get_scan_code(key: str) -> int:
            k = str(key).lower()
            mapping = {
                'escape': 0x01, '1': 0x02, '2': 0x03, '3': 0x04, '4': 0x05, 
                '5': 0x06, '6': 0x07, '7': 0x08, '8': 0x09, '9': 0x0A, '0': 0x0B,
                'space': 0x39, 'i': 0x17, 'enter': 0x1C
            }
            return mapping.get(k, 0x39)

        @staticmethod
        def keyDown(key):
            logitech_driver.key_down(Win32Clicker._get_scan_code(key))
            
        @staticmethod
        def keyUp(key):
            logitech_driver.key_up(Win32Clicker._get_scan_code(key))

    gui_module = Win32Clicker()
else:
    gui_module = pyautogui

from fishing_bot.config import HumanConfig, CaptureConfig

# PyAutoGUI güvenlik ayarları.
pyautogui.FAILSAFE = False      # Sol üst köşeye gidince program çökmesin (Oyunlarda sık olur).
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
        Minigame için optimize EDİLMEMİŞ tıklama (envanter/kalibrasyon).
        Minigame içi tıklamalar için fast_click_at() kullanın.

        Koordinatlar yakalama bölgesi içindeki yerel koordinatlardır.
        Gerçek ekran koordinatına çevrilir.

        Args:
            local_x: Yakalama bölgesi içindeki X koordinatı.
            local_y: Yakalama bölgesi içindeki Y koordinatı.

        Returns:
            True: Tıklama başarıyla yapıldı.
            False: Cooldown nedeniyle tıklama yapılmadı.
        """
        return self.fast_click_at(local_x, local_y)

    def fast_click_at(self, local_x: int, local_y: int, duration: float = 0.0) -> bool:
        """
        Minigame için optimize EDİLMİŞ insansı tıklama.

        Farklar:
        - Bezier eğrisi YOK → direkt mikro hareket (insan 10-30px için bezier çizmez)
        - SetCursorPos ile anında pozisyonlama + pydirectinput ile tıklama
        - Toplam gecikme: ~15-30ms (bezier'li halde 50-80ms idi)
        - ±aim_offset_px jitter KORUNUYOR (anti-cheat)
        - mouseDown/Up arası insansı micro-pause (15-30ms)

        Bu hız İNSANSIDIR çünkü:
        - Reaksiyon gecikmesi bot_logic.py'da reaction_min/max ile uygulanıyor
        - İnsan bir kez tıklamaya karar verdiğinde motor hareketi ÇOK hızlıdır
        - Profesyonel oyuncularda karar-sonrası tıklama: 20-50ms
        """
        # Cooldown kontrolü.
        now = time.time()
        elapsed = now - self._last_click_time
        if elapsed < self._human.click_cooldown:
            return False

        # ── 1. Yerel koordinatı ekran koordinatına çevir ──
        scale = self._capture.display_scale
        screen_x = self._capture.left + (local_x // scale)
        screen_y = self._capture.top + (local_y // scale)

        # ── 2. İnsansı sapma (Gaussian veya Uniform) ──
        offset = self._human.aim_offset_px
        if self._human.use_gaussian_jitter:
            # Gaussian: merkeze yakın atışlar daha sık (insan gibi)
            jitter_x = int(random.gauss(0, offset / 2.5))
            jitter_y = int(random.gauss(0, offset / 2.5))
            jitter_x = max(-offset, min(offset, jitter_x))
            jitter_y = max(-offset, min(offset, jitter_y))
        else:
            jitter_x = random.randint(-offset, offset)
            jitter_y = random.randint(-offset, offset)
        final_x = screen_x + jitter_x
        final_y = screen_y + jitter_y

        # ── 3. Mikro-hareketli tıklama (Anti-Cheat / Logitech) ──
        try:
            from fishing_bot.logitech import logitech_driver

            logitech_driver.move_to(int(final_x), int(final_y))

            # OS'nin event'i işlemesi için mikro bekleme
            time.sleep(0.004)
            logitech_driver.mouse_down()
            time.sleep(random.uniform(0.015, 0.030))
            logitech_driver.mouse_up()
        except Exception:
            pass
        except Exception:
            # Fallback: Win32 API
            if duration > 0.0:
                import pyautogui as _pg
                cur_x, cur_y = _pg.position()
                dist = math.hypot(final_x - cur_x, final_y - cur_y)
                if dist > 3:
                    move_duration = max(0.01, duration - 0.02)
                    steps = max(3, int(move_duration / 0.015))
                    sleep_per_step = move_duration / steps
                    for i in range(1, steps + 1):
                        t = i / steps
                        mx = int(cur_x + (final_x - cur_x) * t)
                        my = int(cur_y + (final_y - cur_y) * t)
                        ctypes.windll.user32.SetCursorPos(mx, my)
                        time.sleep(sleep_per_step)
                else:
                    ctypes.windll.user32.SetCursorPos(int(final_x), int(final_y))
            elif self._human.use_micro_movement:
                import pyautogui as _pg
                cur_x, cur_y = _pg.position()
                dist = math.hypot(final_x - cur_x, final_y - cur_y)
                if dist > 3:
                    steps = self._human.micro_movement_steps
                    for i in range(1, steps + 1):
                        t = i / steps
                        mx = int(cur_x + (final_x - cur_x) * t)
                        my = int(cur_y + (final_y - cur_y) * t)
                        ctypes.windll.user32.SetCursorPos(mx, my)
                        time.sleep(random.uniform(0.002, 0.005))
                else:
                    ctypes.windll.user32.SetCursorPos(int(final_x), int(final_y))
            else:
                ctypes.windll.user32.SetCursorPos(int(final_x), int(final_y))
            time.sleep(0.004)
            ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
            time.sleep(random.uniform(0.015, 0.030))
            ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)

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

    def press_key(self, key: str, hold_min: float = 0.08, hold_max: float = 0.15) -> None:
        """
        Belirtilen tuşa insan benzeri bir sürede basar ve bırakır.

        Args:
            key: Basılacak tuş (ör: '1', 'space', 'i')
            hold_min: Minimum basılı tutma süresi (varsayılan: 0.08)
            hold_max: Maksimum basılı tutma süresi (varsayılan: 0.15)
        """
        hold_time = random.uniform(hold_min, hold_max)

        gui_module.keyDown(key)
        time.sleep(hold_time)
        gui_module.keyUp(key)

    def left_click_screen(self, screen_x: int, screen_y: int) -> None:
        """
        Ekran koordinatına sol tık (Yes butonu vs için).
        Logitech API kullanır.
        """
        try:
            from fishing_bot.logitech import logitech_driver
            logitech_driver.move_to(int(screen_x), int(screen_y))
            time.sleep(random.uniform(0.06, 0.12))  # Buton aktif olsun
            logitech_driver.mouse_down()
            time.sleep(random.uniform(0.08, 0.15))  # Basılı tut
            logitech_driver.mouse_up()
        except Exception:
            # Fallback: Win32 API
            ctypes.windll.user32.SetCursorPos(int(screen_x), int(screen_y))
            time.sleep(random.uniform(0.06, 0.12))
            ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
            time.sleep(random.uniform(0.08, 0.15))
            ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)

    def right_click_at(self, screen_x: int, screen_y: int) -> None:
        """
        Belirtilen ekran koordinatına (Global koordinat) insan benzeri sağ tıklar.
        """
        try:
            from fishing_bot.logitech import logitech_driver
            logitech_driver.move_to(int(screen_x), int(screen_y))
            time.sleep(0.005)
            logitech_driver.mouse_down(button="right")
            time.sleep(random.uniform(0.03, 0.08))
            logitech_driver.mouse_up(button="right")
        except Exception:
            import pyautogui as _pg
            cur_x, cur_y = _pg.position()
            ctypes.windll.user32.SetCursorPos(int(screen_x), int(screen_y))
            time.sleep(0.005)
            ctypes.windll.user32.mouse_event(0x0008, 0, 0, 0, 0)
            time.sleep(random.uniform(0.03, 0.08))
            ctypes.windll.user32.mouse_event(0x0010, 0, 0, 0, 0)

    def drag_and_drop(self, start_x: int, start_y: int, end_x: int, end_y: int) -> None:
        """
        Belirtilen koordinattaki eşyayı sol tık ile tutup başka bir koordinata sürükler.
        (Çöpleri yere atmak için)
        """
        # Başlangıca git (Işınlanma)
        gui_module.moveTo(start_x, start_y)
        time.sleep(random.uniform(0.08, 0.15))
        
        # Sol tıkı basılı tut
        gui_module.mouseDown(button='left')
        time.sleep(random.uniform(0.1, 0.2)) # Tutma payı
        
        # Sürükle (Işınlanma)
        gui_module.moveTo(end_x, end_y)
        time.sleep(random.uniform(0.1, 0.2))
        
        # Bırak
        gui_module.mouseUp(button='left')
        
        # Onay penceresinin açılması için bekle
        time.sleep(random.uniform(0.4, 0.7))
