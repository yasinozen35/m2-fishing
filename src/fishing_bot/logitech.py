"""
logitech.py — Logitech G-HUB Kernel Driver Wrapper

Windows'un "Sanal Tıklama" (LLMHF_INJECTED) damgasını atlatmak için
Logitech G-HUB sanal sürücüsüne (Kernel) doğrudan komut gönderir.
Anti-Cheat (CheatBlocker vb.) bunu fiziksel bir donanımdan gelmiş gibi algılar.
"""

import ctypes
from ctypes import wintypes
import time

# Win32 API Constants
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
FILE_ATTRIBUTE_NORMAL = 0x80
INVALID_HANDLE_VALUE = -1

# Logitech G-HUB Virtual Mouse IOCTL and Path
LGHUB_MOUSE_IOCTL = 0x2A2010
LGHUB_KEYBOARD_IOCTL = 0x2A200C
LGHUB_DEVICE_PATH = r"\\?\root#system#0000#{1cb15dcd-2055-46e7-a009-caa3779e03c5}\mouse"
LGHUB_KEYBOARD_PATH = r"\\?\root#system#0000#{1cb15dcd-2055-46e7-a009-caa3779e03c5}\kbd"

kernel32 = ctypes.windll.kernel32

class MouseStruct(ctypes.Structure):
    _fields_ = [
        ("Button", ctypes.c_char),
        ("X", ctypes.c_char),
        ("Y", ctypes.c_char),
        ("Wheel", ctypes.c_char),
        ("Unk1", ctypes.c_int),
    ]

class KeyboardStruct(ctypes.Structure):
    _fields_ = [
        ("Key", ctypes.c_char),
        ("State", ctypes.c_char),
        ("Unk1", ctypes.c_char),
        ("Unk2", ctypes.c_char),
        ("Unk3", ctypes.c_int),
    ]

class LogitechDriver:
    def __init__(self):
        self.mouse_handle = INVALID_HANDLE_VALUE
        self.kbd_handle = INVALID_HANDLE_VALUE

        for i in range(10):
            mouse_path = f"\\\\?\\root#system#000{i}#{{1cb15dcd-2055-46e7-a009-caa3779e03c5}}\\mouse"
            if self.mouse_handle == INVALID_HANDLE_VALUE:
                h = kernel32.CreateFileW(
                    mouse_path,
                    GENERIC_READ | GENERIC_WRITE,
                    0,
                    None,
                    OPEN_EXISTING,
                    FILE_ATTRIBUTE_NORMAL,
                    None
                )
                if h != INVALID_HANDLE_VALUE:
                    self.mouse_handle = h

            kbd_path = f"\\\\?\\root#system#000{i}#{{1cb15dcd-2055-46e7-a009-caa3779e03c5}}\\kbd"
            if self.kbd_handle == INVALID_HANDLE_VALUE:
                h = kernel32.CreateFileW(
                    kbd_path,
                    GENERIC_READ | GENERIC_WRITE,
                    0,
                    None,
                    OPEN_EXISTING,
                    FILE_ATTRIBUTE_NORMAL,
                    None
                )
                if h != INVALID_HANDLE_VALUE:
                    self.kbd_handle = h
                    
            if self.mouse_handle != INVALID_HANDLE_VALUE and self.kbd_handle != INVALID_HANDLE_VALUE:
                break

        self.mouse_connected = (self.mouse_handle != INVALID_HANDLE_VALUE)
        self.kbd_connected = (self.kbd_handle != INVALID_HANDLE_VALUE)
        
        if not self.mouse_connected:
            print("⚠️ [Uyarı] Logitech G-HUB fare sürücüsü bulunamadı! G-HUB'ın kurulu olduğundan emin olun.")
        if not self.kbd_connected:
            print("⚠️ [Uyarı] Logitech G-HUB klavye sürücüsü bulunamadı!")

    def _send_mouse_event(self, button=0, x=0, y=0, wheel=0):
        if not self.mouse_connected:
            return False
            
        mouse_data = MouseStruct()
        mouse_data.Button = button
        mouse_data.X = x
        mouse_data.Y = y
        mouse_data.Wheel = wheel
        mouse_data.Unk1 = 0

        bytes_returned = wintypes.DWORD(0)
        
        success = kernel32.DeviceIoControl(
            self.mouse_handle,
            LGHUB_MOUSE_IOCTL,
            ctypes.byref(mouse_data),
            ctypes.sizeof(mouse_data),
            None,
            0,
            ctypes.byref(bytes_returned),
            None
        )
        return bool(success)

    def mouse_down(self, button="left"):
        b_code = 1 if button == "left" else 2
        return self._send_mouse_event(button=b_code)

    def mouse_up(self, button="left"):
        return self._send_mouse_event(button=0)

    def click(self, button="left", duration=0.03):
        """Donanımsal tıklama simülasyonu."""
        if not self.mouse_connected:
            # Fallback
            import pyautogui
            pyautogui.click(button=button)
            return False
            
        self.mouse_down(button)
        time.sleep(duration)
        self.mouse_up(button)
        return True

    def move(self, dx: int, dy: int):
        """Göreli (Relative) hareket."""
        if not self.mouse_connected:
            import pyautogui
            cx, cy = pyautogui.position()
            pyautogui.moveTo(cx + dx, cy + dy)
            return False

        while dx != 0 or dy != 0:
            step_x = max(-127, min(127, dx))
            step_y = max(-127, min(127, dy))
            self._send_mouse_event(x=step_x, y=step_y)
            dx -= step_x
            dy -= step_y
            if dx != 0 or dy != 0:
                time.sleep(0.001)
        return True

    def move_to(self, target_x: int, target_y: int):
        """Absolute adrese gitme."""
        import pyautogui
        cur_x, cur_y = pyautogui.position()
        dx = target_x - cur_x
        dy = target_y - cur_y
        self.move(dx, dy)

    # ── Klavye İşlemleri ──
    def _send_keyboard_event(self, key_code, state):
        if not self.kbd_connected:
            return False
        
        kbd_data = KeyboardStruct()
        kbd_data.Key = key_code
        kbd_data.State = state # 1=Down, 0=Up
        kbd_data.Unk1 = 0
        kbd_data.Unk2 = 0
        kbd_data.Unk3 = 0
        
        bytes_returned = wintypes.DWORD(0)
        success = kernel32.DeviceIoControl(
            self.kbd_handle,
            LGHUB_KEYBOARD_IOCTL,
            ctypes.byref(kbd_data),
            ctypes.sizeof(kbd_data),
            None,
            0,
            ctypes.byref(bytes_returned),
            None
        )
        return bool(success)
        
    def key_down(self, key_code: int):
        return self._send_keyboard_event(key_code, 1)
        
    def key_up(self, key_code: int):
        return self._send_keyboard_event(key_code, 0)
        
    def press(self, key_code: int, duration=0.08):
        if not self.kbd_connected:
            # Fallback
            import pyautogui
            # pyautogui needs str key, this requires conversion, skipping for fallback simplicity
            return False
            
        self.key_down(key_code)
        time.sleep(duration)
        self.key_up(key_code)
        return True

    def close(self):
        if self.mouse_connected and self.mouse_handle:
            kernel32.CloseHandle(self.mouse_handle)
            self.mouse_connected = False
        if self.kbd_connected and self.kbd_handle:
            kernel32.CloseHandle(self.kbd_handle)
            self.kbd_connected = False

logitech_driver = LogitechDriver()
