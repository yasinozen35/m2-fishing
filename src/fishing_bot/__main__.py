"""
fishing_bot — Balık tutma oyunu otomatik botu.

python -m fishing_bot ile çalıştırılır.

ÖNEMLİ: Windows DPI Awareness TÜM import'lardan önce ayarlanmalıdır.
Bu dosya modül giriş noktası olduğu için burada yapıyoruz.
"""

import os
import sys

# ══════════════════════════════════════════════════════════════════
# WINDOWS PLATFORM BAŞLATMA — DİĞER TÜM IMPORT'LARDAN ÖNCE
# ══════════════════════════════════════════════════════════════════
# Windows'ta DPI Awareness ayarı mss, pyautogui ve cv2'den ÖNCE
# yapılmalıdır. Aksi halde ekran koordinatları yanlış çalışır.
# ══════════════════════════════════════════════════════════════════

if sys.platform == "win32":
    # ── Admin Yetkisi Kontrolü (EN BAŞTA) ──
    # Oyun admin yetkisiyle çalışıyorsa, bot da admin olmalı.
    # Aksi halde Windows UIPI, SendInput'un oyuna ulaşmasını engeller.
    try:
        import ctypes
        if ctypes.windll.shell32.IsUserAnAdmin() == 0:
            # Admin değil → UAC prompt ile yeniden başlat
            params = ' '.join(f'"{a}"' if ' ' in a else a for a in sys.argv[1:])
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable,
                f'"{sys.argv[0]}" {params}',
                os.getcwd(), 1,
            )
            sys.exit(0)
    except Exception:
        pass

    try:
        import ctypes

        # ── DPI Awareness ──
        # Per-Monitor DPI Aware v2 (Windows 10 1703+).
        # Bu olmadan mss ve pyautogui farklı koordinat sistemleri kullanır.
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            # Fallback: System DPI Aware (eski Windows).
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except (AttributeError, OSError):
                pass

        # ── ANSI Renk Desteği ──
        # Windows 10+ terminal'de ANSI escape kodlarını etkinleştir.
        try:
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            mode = ctypes.c_ulong()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
                kernel32.SetConsoleMode(handle, mode.value | 0x0004)
        except Exception:
            pass

        # ── UTF-8 Konsol ──
        try:
            sys.stdout.reconfigure(encoding="utf-8")  # type: ignore
        except Exception:
            pass

        # ── Windows Timer Resolution Ayarı (1ms precision) ──
        try:
            ctypes.windll.winmm.timeBeginPeriod(1)
        except Exception:
            pass

    except ImportError:
        pass

# ══════════════════════════════════════════════════════════════════
# ŞİMDİ güvenle import edebiliriz.
# ══════════════════════════════════════════════════════════════════

from fishing_bot.gui import launch_gui

launch_gui()
