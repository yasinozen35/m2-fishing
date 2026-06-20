"""
window_utils.py — Otomatik oyun penceresi tespiti.

Windows API kullanarak belirlenen başlıklı (veya process ismine sahip)
tüm oyun pencerelerinin koordinatlarını otomatik bulur.
"""

import sys
from dataclasses import dataclass

@dataclass
class GameWindow:
    hwnd: int
    title: str
    left: int
    top: int
    width: int
    height: int


def get_game_windows(title_keyword: str = "METIN2") -> list[GameWindow]:
    """
    Belirtilen anahtar kelimeyi başlığında içeren tüm pencereleri bulur.
    
    Args:
        title_keyword: Pencere başlığında aranacak metin (büyük/küçük harf duyarsız).
        
    Returns:
        Tespit edilen pencerelerin listesi (GameWindow objeleri).
    """
    windows = []
    if sys.platform != "win32":
        return windows

    try:
        import ctypes
        from ctypes import wintypes
        
        user32 = ctypes.windll.user32
        
        def callback(hwnd, extra):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buff, length + 1)
                    title = buff.value
                    
                    if title_keyword.lower() in title.lower():
                        rect = wintypes.RECT()
                        user32.GetWindowRect(hwnd, ctypes.byref(rect))
                        
                        width = rect.right - rect.left
                        height = rect.bottom - rect.top
                        
                        # Simge durumunda küçültülmüş pencereleri (width/height 0) atla
                        if width > 0 and height > 0:
                            # Bazı durumlarda görünmez pencereler çok küçük olur
                            if width > 400 and height > 300:
                                windows.append(GameWindow(
                                    hwnd=hwnd,
                                    title=title,
                                    left=rect.left,
                                    top=rect.top,
                                    width=width,
                                    height=height
                                ))
            return True
            
        CMPFUNC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
        cb_func = CMPFUNC(callback)
        user32.EnumWindows(cb_func, 0)
        
    except Exception as e:
        print(f"[WindowUtils] Pencere tespiti hatası: {e}")
        
    # Soldan sağa sırala (Ekrandaki yerleşime göre Bot 1, Bot 2 gibi)
    windows.sort(key=lambda w: w.left)
    return windows
