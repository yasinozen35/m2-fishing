"""
main.py — Ana giriş noktası ve oyun döngüsü.

Windows ve macOS uyumlu.

Kullanım:
    uv run python -m fishing_bot
    uv run python -m fishing_bot --autobot     (tam otonom gece modu)
    uv run python -m fishing_bot --calibrate   (kalibrasyon modu)
    uv run python -m fishing_bot --no-debug    (debug overlay kapalı)
"""

import argparse
import os
import platform
import sys
import time

import cv2
import numpy as np

from fishing_bot.config import Config
from fishing_bot.screen_capture import ScreenCapture
from fishing_bot.detector import Detector
from fishing_bot.clicker import HumanClicker
from fishing_bot.overlay import DebugOverlay
from fishing_bot.bot_logic import BotLogic, BotState


# ── Platform başlatma ──────────────────────────────────────────────

def _init_platform() -> None:
    system = platform.system()
    if system == "Windows":
        # ── Admin Yetkisi Kontrolü ──
        try:
            import ctypes as _ctypes
            if _ctypes.windll.shell32.IsUserAnAdmin() == 0:
                params = ' '.join(f'"{a}"' if ' ' in a else a for a in sys.argv[1:])
                print("Bot yonetici yetkisiyle yeniden baslatiliyor...")
                _ctypes.windll.shell32.ShellExecuteW(
                    None, "runas", sys.executable,
                    f'"{sys.argv[0]}" {params}',
                    os.getcwd(), 1,
                )
                sys.exit(0)
        except Exception:
            pass

        try:
            import ctypes
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except (AttributeError, OSError):
                try:
                    ctypes.windll.user32.SetProcessDPIAware()
                except (AttributeError, OSError):
                    pass
        except ImportError:
            pass

        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)
            mode = ctypes.c_ulong()
            kernel32.GetConsoleMode(handle, ctypes.byref(mode))
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
        except Exception:
            pass

        try:
            sys.stdout.reconfigure(encoding="utf-8")  # type: ignore
        except Exception:
            pass

        # ── Windows Timer Resolution Ayarı (1ms precision) ──
        try:
            import ctypes as _ctypes
            _ctypes.windll.winmm.timeBeginPeriod(1)
        except Exception:
            pass

_init_platform()


# ── Terminal renk kodları ──────────────────────────────────────────

def _supports_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if platform.system() == "Windows":
        return os.environ.get("WT_SESSION") is not None or "ANSICON" in os.environ or True
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


class Colors:
    _enabled = _supports_color()
    RESET = "\033[0m" if _enabled else ""
    GREEN = "\033[92m" if _enabled else ""
    RED = "\033[91m" if _enabled else ""
    YELLOW = "\033[93m" if _enabled else ""
    CYAN = "\033[96m" if _enabled else ""
    BOLD = "\033[1m" if _enabled else ""


def print_banner() -> None:
    banner = f"""
{Colors.CYAN}{Colors.BOLD}
  +======================================+
  |     BALIK TUTMA BOTU                 |
  |     Otomatik Goruntu Isleme          |
  +======================================+
{Colors.RESET}"""
    print(banner)


def print_status_classic(fps: float, circle_ok: bool, fish_found: bool, fish_inside: bool, click_count: int) -> None:
    """Klasik (sadece mini-oyun) mod için durum bilgisi."""
    circle_str = f"{Colors.GREEN}[O]{Colors.RESET}" if circle_ok else f"{Colors.RED}[X]{Colors.RESET}"
    fish_str = f"{Colors.GREEN}BALIK{Colors.RESET}" if fish_found else f"{Colors.RED} --- {Colors.RESET}"
    inside_str = f"{Colors.GREEN}{Colors.BOLD}HIT!{Colors.RESET}" if fish_inside else f"{Colors.YELLOW} -- {Colors.RESET}"

    sys.stdout.write(
        f"\r  FPS: {fps:5.1f} | Daire: {circle_str} | Balik: {fish_str} | Durum: {inside_str} | Tiklama: {click_count}  "
    )
    sys.stdout.flush()


def print_status_autobot(fps: float, bot_state: str, catches: int, casts: int) -> None:
    """AutoBot (Tam Otonom) mod için durum bilgisi."""
    sys.stdout.write(
        f"\r  FPS: {fps:5.1f} | Durum: {Colors.YELLOW}{bot_state:<25}{Colors.RESET} | Yakalanan: {Colors.GREEN}{catches}{Colors.RESET} | Atis: {casts}  "
    )
    sys.stdout.flush()


def run_calibration(config: Config) -> None:
    print(f"\n{Colors.YELLOW}  KALIBRASYON MODU{Colors.RESET}")
    print(f"  Tam ekran yakalanacak. Oyun penceresini secin.")
    print(f"  {Colors.CYAN}Mouse ile dikdortgen cizin, ENTER ile onaylayin, C ile iptal edin.{Colors.RESET}\n")

    import mss
    with mss.MSS() as sct:
        monitor = sct.monitors[1]
        raw = sct.grab(monitor)
        full_screen = np.array(raw, dtype=np.uint8)[:, :, :3]

    h, w = full_screen.shape[:2]
    display_scale = 1.0
    max_display = 1200
    if w > max_display:
        display_scale = max_display / w
        display = cv2.resize(full_screen, (int(w * display_scale), int(h * display_scale)))
    else:
        display = full_screen

    roi = cv2.selectROI("Oyun Penceresini Secin (ENTER=Onayla, C=Iptal)", display, fromCenter=False, showCrosshair=True)
    cv2.destroyAllWindows()

    if roi == (0, 0, 0, 0):
        print(f"  {Colors.RED}Iptal edildi. Varsayilan ayarlar kullanilacak.{Colors.RESET}")
        return

    x, y, rw, rh = roi
    real_x = int(x / display_scale)
    real_y = int(y / display_scale)
    real_w = int(rw / display_scale)
    real_h = int(rh / display_scale)

    scale = config.capture.display_scale
    config.capture.left = real_x // scale
    config.capture.top = real_y // scale
    config.capture.width = real_w // scale
    config.capture.height = real_h // scale

    print(f"\n  {Colors.GREEN}Bolge ayarlandi:{Colors.RESET}")
    print(f"    Sol: {config.capture.left}, Ust: {config.capture.top}")
    print(f"    Genislik: {config.capture.width}, Yukseklik: {config.capture.height}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Balik Tutma Botu")
    parser.add_argument("--autobot", action="store_true", help="Tam otonom modu baslat (yem, olta atma dahil)")
    parser.add_argument("--calibrate", "-c", action="store_true", help="Kalibrasyon modunu baslat")
    parser.add_argument("--no-debug", action="store_true", help="Debug overlay'i kapat")
    parser.add_argument("--region", type=str, default=None, help="Yakalama bolgesi: 'left,top,width,height'")
    parser.add_argument("--scale", type=int, default=None, help="Ekran olceklendirme faktoru")
    args = parser.parse_args()

    config = Config()

    if args.no_debug:
        config.debug_mode = False

    if args.scale is not None:
        config.capture.display_scale = args.scale

    if args.region:
        parts = [int(x.strip()) for x in args.region.split(",")]
        if len(parts) == 4:
            config.capture.left, config.capture.top = parts[0], parts[1]
            config.capture.width, config.capture.height = parts[2], parts[3]

    print_banner()
    print(f"  {Colors.CYAN}Platform:{Colors.RESET} {platform.system()} ({platform.release()})")
    print(f"  {Colors.CYAN}Mod:{Colors.RESET} {'AUTOBOT (Tam Otonom)' if args.autobot else 'KLASIK (Sadece Tiklama)'}")

    if args.calibrate:
        run_calibration(config)

    capture = ScreenCapture(config.capture)
    detector = Detector(config.circle, config.fish)
    clicker = HumanClicker(config.human, config.capture)
    overlay = DebugOverlay() if config.debug_mode else None
    
    # Autobot mantığını başlat
    bot_logic = BotLogic(config.autobot, clicker, capture) if args.autobot else None
    if bot_logic:
        bot_logic.start()

    print(f"  {Colors.CYAN}Yakalama bolgesi:{Colors.RESET}")
    print(f"    Sol: {config.capture.left}, Ust: {config.capture.top} | Genislik: {config.capture.width}, Yukseklik: {config.capture.height}")
    print(f"  {Colors.GREEN}{Colors.BOLD}> Bot calisiyor! Durdurmak icin Ctrl+C{Colors.RESET}\n")

    click_count = 0
    frame_count = 0
    fps_time = time.time()
    current_fps = 0.0
    frame_interval = 1.0 / config.target_fps

    try:
        while True:
            loop_start = time.time()

            # 1. Ekran yakala
            frame = capture.grab_frame()

            # 2. Tespit et
            result = detector.detect(frame)
            
            clicked = False
            status_msg = ""

            # 3. Otonom veya Klasik Mod Mantığı
            if bot_logic:
                # OTONOM MOD
                clicked, status_msg = bot_logic.update(result, detector=detector)
                if clicked:
                    click_count += 1
            else:
                # KLASIK MOD
                if result.is_fish_inside and result.fish is not None:
                    if clicker.is_ready:
                        clicked = clicker.click_at(result.fish.center_x, result.fish.center_y)
                        if clicked:
                            click_count += 1

            # 4. Debug overlay
            if overlay is not None:
                overlay.render(frame, result, clicked=clicked)

            # 5. FPS hesapla
            frame_count += 1
            now = time.time()
            if now - fps_time >= 1.0:
                current_fps = frame_count / (now - fps_time)
                frame_count = 0
                fps_time = now

            # 6. Terminal durumu
            if bot_logic:
                print_status_autobot(current_fps, status_msg, bot_logic.successful_catches, bot_logic.total_casts)
            else:
                print_status_classic(current_fps, result.circle is not None, result.fish is not None, result.is_fish_inside, click_count)

            # 7. FPS sınırla
            elapsed = time.time() - loop_start
            sleep_time = frame_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        print(f"\n\n  {Colors.YELLOW}Bot durduruldu.{Colors.RESET}")
        if bot_logic:
            print(f"  Toplam Atis: {bot_logic.total_casts} | Yakalanan: {Colors.GREEN}{bot_logic.successful_catches}{Colors.RESET}")
        else:
            print(f"  Toplam tiklama: {Colors.GREEN}{click_count}{Colors.RESET}")
        print()
    finally:
        capture.close()
        if overlay is not None:
            overlay.close()


if __name__ == "__main__":
    main()
