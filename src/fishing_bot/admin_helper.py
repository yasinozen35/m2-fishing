"""
admin_helper.py — Botun admin yetkisiyle çalışmasını sağlar.

Eğer bot admin değilse, UAC prompt gösterip admin olarak yeniden başlatır.
"""
import ctypes
import os
import sys


def is_admin() -> bool:
    """Mevcut process admin yetkisine sahip mi?"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def ensure_admin() -> bool:
    """
    Admin yetkisi yoksa UAC prompt ile yeniden başlatır.

    Returns:
        True: Zaten admin'di veya admin olarak yeniden başlatıldı.
        False: Kullanıcı UAC'ı reddetti (bu durumda process sonlanır).
    """
    if is_admin():
        return True

    # Admin olarak yeniden başlat
    script = sys.argv[0]
    params = ' '.join(f'"{a}"' if ' ' in a else a for a in sys.argv[1:])

    try:
        ctypes.windll.shell32.ShellExecuteW(
            None,                           # hwnd
            "runas",                        # Operation (UAC prompt)
            sys.executable,                 # Python exe
            f'"{script}" {params}',         # Parameters
            os.getcwd(),                    # Working directory
            1,                              # nShowCmd (SW_SHOWNORMAL)
        )
        # Başarılı — mevcut process'i sonlandır
        sys.exit(0)
    except Exception as e:
        print(f"\n  [HATA] Admin yetkisi alinamadi: {e}")
        print(f"  Botu YONETICI olarak calistirin!")
        print(f"  Windows tusu -> 'powershell' -> Yonetici olarak calistir")
        print(f"  Sonra: cd {os.getcwd()}")
        print(f"         uv run python -m fishing_bot")
        return False


def ensure_admin_or_exit() -> None:
    """
    Admin kontrolü yapar, değilse UAC prompt gösterir.
    Başarısız olursa programdan çıkar.
    """
    if not ensure_admin():
        sys.exit(1)
