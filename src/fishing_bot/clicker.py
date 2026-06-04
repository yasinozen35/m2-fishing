"""
clicker.py — İnsan benzeri mouse kontrol modülü.

Makine hızında değil, süper-insan hızında tıklama yapar.
Rastgele reaksiyon gecikmesi, doğal mouse hareketi ve
hafif koordinat sapması ile insan davranışını simüle eder.
"""

import random
import sys
import time

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

    class Win32Clicker:
        """PyAutoGUI ve PyDirectInput'un yerini alacak süper hızlı Native Windows Tıklayıcı."""
        @staticmethod
        def moveTo(x, y):
            try:
                import pydirectinput
                move_func = pydirectinput.moveTo
            except ImportError:
                move_func = ctypes.windll.user32.SetCursorPos

            import pyautogui
            import math
            import time
            import random

            start_x, start_y = pyautogui.position()
            end_x, end_y = int(x), int(y)
            
            dist = math.hypot(end_x - start_x, end_y - start_y)
            if dist < 5:
                move_func(end_x, end_y)
                return

            # Hızlı ama insansı kaydırma süresi (50-80 milisaniye)
            duration = random.uniform(0.05, 0.08)
            steps = max(5, int(dist / 20))  
            if steps > 12: steps = 12
            
            # Bezier kontrol noktaları (Kavis eklemek için)
            offset = dist * 0.2
            p1_x = start_x + (end_x - start_x) * 0.3 + random.uniform(-offset, offset)
            p1_y = start_y + (end_y - start_y) * 0.3 + random.uniform(-offset, offset)
            
            p2_x = start_x + (end_x - start_x) * 0.7 + random.uniform(-offset, offset)
            p2_y = start_y + (end_y - start_y) * 0.7 + random.uniform(-offset, offset)

            sleep_time = duration / steps

            for i in range(1, steps + 1):
                t = i / steps
                bx = (1-t)**3 * start_x + 3*(1-t)**2 * t * p1_x + 3*(1-t) * t**2 * p2_x + t**3 * end_x
                by = (1-t)**3 * start_y + 3*(1-t)**2 * t * p1_y + 3*(1-t) * t**2 * p2_y + t**3 * end_y
                move_func(int(bx), int(by))
                time.sleep(sleep_time)

            move_func(end_x, end_y)
            
        @staticmethod
        def fastClick():
            """Minigame için optimize edilmiş hızlı tıklama (15-30ms basılı tutma - e-sporcu)."""
            ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            time.sleep(random.uniform(0.015, 0.030))
            ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

        @staticmethod
        def click():
            import random
            ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            time.sleep(random.uniform(0.06, 0.11))
            ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            
        @staticmethod
        def rightClick():
            import random
            ctypes.windll.user32.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
            time.sleep(random.uniform(0.06, 0.11))
            ctypes.windll.user32.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
            
        @staticmethod
        def mouseDown(button='left'):
            flag = MOUSEEVENTF_LEFTDOWN if button == 'left' else MOUSEEVENTF_RIGHTDOWN
            ctypes.windll.user32.mouse_event(flag, 0, 0, 0, 0)
            
        @staticmethod
        def mouseUp(button='left'):
            flag = MOUSEEVENTF_LEFTUP if button == 'left' else MOUSEEVENTF_RIGHTUP
            ctypes.windll.user32.mouse_event(flag, 0, 0, 0, 0)
            
        @staticmethod
        def keyDown(key):
            # DirectX oyunlarında klavye basışları için PyAutoGUI çalışmaz.
            try:
                import pydirectinput
                pydirectinput.keyDown(key)
            except:
                pyautogui.keyDown(key)
            
        @staticmethod
        def keyUp(key):
            try:
                import pydirectinput
                pydirectinput.keyUp(key)
            except:
                pyautogui.keyUp(key)

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

        # ── 4. Mouse'u ANINDA hareket ettir ve Tıkla (ASENKRON) ──
        # Not: Anti-Cheat sistemleri sentetik tıklama aldıklarında o Thread'i 2-3 saniye dondurabilir (Tarpit tekniği).
        # Botun FPS'inin 3'e düşmemesi (Ana görüntü işleme thread'inin donmaması) için
        # Işınlanma ve tıklama işlemini anlık (Fire-and-Forget) bir Thread içinde atıyoruz!
        def _async_click():
            # Teleport: Bezier animasyonu yok, direkt hedefe ışınlan (minigame için hız kritik)
            ctypes.windll.user32.SetCursorPos(int(final_x), int(final_y))
            gui_module.fastClick()
            
        import threading
        threading.Thread(target=_async_click, daemon=True).start()

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

    def right_click_at(self, screen_x: int, screen_y: int) -> None:
        """
        Belirtilen ekran koordinatına (Global koordinat) insan benzeri sağ tıklar.
        Zırh değişimi ve envanter yönetimi için kullanılır.
        """
        # Mouse'u anında hareket ettir
        gui_module.moveTo(screen_x, screen_y)
        
        # Oyunun mouse'u algılaması için
        time.sleep(random.uniform(0.05, 0.1))
        
        # Sağ tıkla
        gui_module.rightClick() if hasattr(gui_module, 'rightClick') else gui_module.click(button='right')

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
