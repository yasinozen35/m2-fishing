"""
clicker_subprocess.py — AYRI PROCESS'te çalışan tıklama sunucusu.

Ana bottan stdin üzerinden koordinat alır, pydirectinput ile tıklar.
pydirectinput = SendInput tabanlı, DirectX uyumlu, mouse_event'ten daha güvenli.

Protokol (stdin, her satır):
    CLICK:<x>:<y>          → direkt ışınlan + sol tık (eski, hızlı)
    MOVE_CLICK:<x>:<y>     → insan gibi bezier hareket + sol tık (yeni)
    RIGHT:<x>:<y>          → sağ tık
    PING                   → PONG
    QUIT                   → çık
"""

import math
import random
import sys
import time


def _bezier_curve(start, end, control_offset=0.3, steps=12):
    """
    İki nokta arasında rastgele sapmalı bezier eğrisi oluşturur.

    İnsan eli düz çizgi çizmez, hafif kavisli hareket eder.
    """
    sx, sy = start
    ex, ey = end

    # Orta nokta
    mx = (sx + ex) / 2
    my = (sy + ey) / 2

    # Mesafe
    dist = math.sqrt((ex - sx) ** 2 + (ey - sy) ** 2)

    # Kontrol noktası: orta noktadan rastgele sapma
    offset = dist * control_offset
    angle = random.uniform(0, 2 * math.pi)
    cx = mx + offset * math.cos(angle)
    cy = my + offset * math.sin(angle)

    # İkinci kontrol noktası (daha küçük sapma)
    angle2 = angle + random.uniform(-1.5, 1.5)
    cx2 = mx + offset * 0.5 * math.cos(angle2)
    cy2 = my + offset * 0.5 * math.sin(angle2)

    points = []
    for i in range(steps):
        t = i / (steps - 1)
        # Kübik bezier: B(t) = (1-t)³P0 + 3(1-t)²tP1 + 3(1-t)t²P2 + t³P3
        u = 1 - t
        x = u**3 * sx + 3 * u**2 * t * cx + 3 * u * t**2 * cx2 + t**3 * ex
        y = u**3 * sy + 3 * u**2 * t * cy + 3 * u * t**2 * cy2 + t**3 * ey
        points.append((int(x), int(y)))

    return points


def _human_move_to(target_x: int, target_y: int) -> None:
    """
    HIZLI insan benzeri mouse hareketi — toplam ~30ms.

    Az adımlı, mikro gecikmeli. Işınlanma gibi değil ama çok seri.
    """
    import pydirectinput

    try:
        current = pydirectinput.position()
    except Exception:
        pydirectinput.moveTo(target_x, target_y)
        return

    start_x, start_y = current
    dist = math.sqrt((target_x - start_x) ** 2 + (target_y - start_y) ** 2)

    # Çok yakınsa direkt
    if dist < 8:
        pydirectinput.moveTo(target_x, target_y)
        return

    # Sadece 3-5 adım (hızlı)
    steps = min(max(int(dist / 30), 3), 5)
    points = _bezier_curve((start_x, start_y), (target_x, target_y),
                           control_offset=random.uniform(0.05, 0.15),
                           steps=steps)

    for px, py in points:
        pydirectinput.moveTo(px, py)
        # Mikro gecikme (toplam ~3-10ms)
        time.sleep(random.uniform(0.001, 0.003))

    # Hedefe son git
    pydirectinput.moveTo(target_x, target_y)


def _click(x: int, y: int) -> None:
    """pydirectinput ile direkt tıklama."""
    import pydirectinput
    pydirectinput.moveTo(x, y)
    pydirectinput.mouseDown()
    time.sleep(0.003)
    pydirectinput.mouseUp()


def _human_click(x: int, y: int) -> None:
    """Hızlı insan benzeri: bezier hareket (~30ms) + anında tık."""
    _human_move_to(x, y)
    # Mikro bekleme + tık
    import pydirectinput
    time.sleep(random.uniform(0.005, 0.015))
    pydirectinput.mouseDown()
    time.sleep(random.uniform(0.002, 0.006))
    pydirectinput.mouseUp()


def _right_click(x: int, y: int) -> None:
    """pydirectinput ile sağ tık."""
    import pydirectinput
    pydirectinput.moveTo(x, y)
    time.sleep(0.03)
    pydirectinput.mouseDown(button='right')
    time.sleep(0.005)
    pydirectinput.mouseUp(button='right')


def main():
    """Stdin'den komut dinle, anında uygula."""
    sys.stdin.reconfigure(encoding="utf-8")   # type: ignore
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore

    sys.stdout.write("READY\n")
    sys.stdout.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        parts = line.split(":")
        cmd = parts[0].upper()

        try:
            if cmd == "CLICK" and len(parts) == 3:
                x, y = int(parts[1]), int(parts[2])
                _click(x, y)
                sys.stdout.write("OK\n")

            elif cmd == "MOVE_CLICK" and len(parts) == 3:
                x, y = int(parts[1]), int(parts[2])
                _human_click(x, y)
                sys.stdout.write("OK\n")

            elif cmd == "RIGHT" and len(parts) == 3:
                x, y = int(parts[1]), int(parts[2])
                _right_click(x, y)
                sys.stdout.write("OK\n")

            elif cmd == "PING":
                sys.stdout.write("PONG\n")

            elif cmd == "QUIT":
                sys.stdout.write("BYE\n")
                sys.stdout.flush()
                break

            else:
                sys.stdout.write(f"ERR:unknown command {cmd}\n")

            sys.stdout.flush()

        except Exception as e:
            sys.stdout.write(f"ERR:{e}\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
