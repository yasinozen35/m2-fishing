"""
find_offsets_auto.py — Diagnostic tarama ile offset keşfi.

Circle ve fish değerlerini MULTIPLE FORMATTA arar:
- float (4 byte IEEE 754)
- double (8 byte IEEE 754)
- int32 / uint32
- int16 / uint16

Hangi formatta bulursa onu kullanır.
"""

import os
import struct
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from fishing_bot.memory_scanner import MemoryScanner


def print_header(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def scan_value(scanner, target: float, fmt: str, size: int, tolerance: float = 2.0):
    """
    Memory'de belirli bir formatta değer ara.
    Returns: list of addresses
    """
    results = []
    total_size = sum(r.size for r in scanner._regions)
    scanned = 0

    for region in scanner._regions:
        chunk_size = 65536
        offset = 0
        while offset < region.size:
            remain = region.size - offset
            read_size = min(chunk_size, remain)
            addr = region.base + offset
            data = scanner.read_bytes(addr, read_size)
            if data:
                for i in range(0, len(data) - size + 1, size):
                    try:
                        if fmt == '<f':
                            val = struct.unpack_from('<f', data, i)[0]
                        elif fmt == '<d':
                            val = struct.unpack_from('<d', data, i)[0]
                        elif fmt == '<i':
                            val = float(struct.unpack_from('<i', data, i)[0])
                        elif fmt == '<I':
                            val = float(struct.unpack_from('<I', data, i)[0])
                        elif fmt == '<h':
                            val = float(struct.unpack_from('<h', data, i)[0])
                        elif fmt == '<H':
                            val = float(struct.unpack_from('<H', data, i)[0])
                        else:
                            continue

                        # NaN/Inf kontrolü
                        if val != val or val == float('inf') or val == float('-inf'):
                            continue

                        if abs(val - target) <= tolerance:
                            results.append(addr + i)
                    except Exception:
                        pass
            scanned += read_size
            offset += read_size

    return results


def main():
    print_header("Diagnostic Offset Keşfi")
    print()
    print("Circle ve fish değerlerini 6 farklı formatta tarar.")
    print("Hangi formatta eşleşme bulursa onu kullanır.")
    print()
    print("⚠ Metin2'de balık mini-game'i BAŞLATIN (daire GÖRÜNÜR olsun)")
    input("\nMini-game aktifse ENTER'a basın...")

    # ── Scanner ──
    scanner = MemoryScanner("metin2client.exe")
    if not scanner.find_and_attach():
        print("\n❌ Metin2 bulunamadı!")
        return 1
    scanner.enumerate_regions()
    total_mb = sum(r.size for r in scanner._regions) // 1048576
    print(f"✓ Memory: {len(scanner._regions)} bölge, {total_mb}MB")

    # ── OpenCV tespit ──
    print("\nOpenCV tespiti yapılıyor...")
    from fishing_bot.config import CaptureConfig, CircleDetectConfig, FishDetectConfig
    from fishing_bot.screen_capture import ScreenCapture
    from fishing_bot.detector import Detector

    capture = ScreenCapture(CaptureConfig())
    detector = Detector(CircleDetectConfig(), FishDetectConfig())

    frame = capture.grab_full_frame()
    result = detector.detect(frame)

    if result.circle is None:
        # Birkaç frame daha dene
        for attempt in range(5):
            time.sleep(0.3)
            frame = capture.grab_full_frame()
            result = detector.detect(frame)
            if result.circle is not None:
                break

    if result.circle is None:
        print("❌ Circle tespit edilemedi!")
        return 1

    cx, cy, cr = result.circle.center_x, result.circle.center_y, result.circle.radius
    fx = result.fish.center_x if result.fish else 0
    fy = result.fish.center_y if result.fish else 0

    print(f"✓ Circle: ({cx}, {cy}, r={cr})")
    print(f"✓ Fish:   ({fx}, {fy})")

    capture.close()

    # ── DIAGNOSTIC: Her formatta circle_radius tara (en spesifik değer) ──
    print_header("Format Diagnostic — circle_radius taranıyor")

    formats = [
        ("float (4 byte)",  "<f", 4, 2.0),
        ("double (8 byte)", "<d", 8, 2.0),
        ("int32 signed",    "<i", 4, 1.0),
        ("uint32",          "<I", 4, 1.0),
        ("int16 signed",    "<h", 2, 1.0),
        ("uint16",          "<H", 2, 1.0),
    ]

    for fmt_name, fmt_char, size, tol in formats:
        results = scan_value(scanner, float(cr), fmt_char, size, tol)
        print(f"  {fmt_name:20s}: {len(results):>6d} adres bulundu")

    # ── Ana tarama: En iyi formatla circle struct ara ──
    print_header("En İyi Formatla Struct Taraması")

    # Her formatta circle_x tara ve en az sonuç vereni seç
    best_fmt = None
    best_count = 999999
    for fmt_name, fmt_char, size, tol in formats:
        results = scan_value(scanner, float(cx), fmt_char, size, tol)
        count = len(results)
        print(f"  circle_x {fmt_name:20s}: {count:>6d} adres")
        if 2 <= count < best_count:  # En az 2, en fazla 5000
            best_count = count
            best_fmt = (fmt_name, fmt_char, size, tol)

    if best_fmt is None:
        print("\n❌ Hiçbir formatta eşleşme bulunamadı!")
        print("   Circle değerleri: ", cx, cy, cr)
        return 1

    fmt_name, fmt_char, size, tol = best_fmt
    print(f"\n✓ En iyi format: {fmt_name} ({best_count} circle_x adayı)")

    # Bu formatta circle struct ara (x, y, r ardışık)
    print(f"\nStruct pattern aranıyor (format={fmt_name}, size={size})...")

    circle_candidates = []
    fish_candidates = []

    total_size = sum(r.size for r in scanner._regions)
    scanned = 0

    for region in scanner._regions:
        chunk_size = 65536
        offset = 0
        while offset < region.size:
            remain = region.size - offset
            read_size = min(chunk_size, remain)
            addr = region.base + offset
            data = scanner.read_bytes(addr, read_size)
            if data:
                step = size

                # Circle struct: 3 değer (x, y, radius) ardışık
                for i in range(0, len(data) - 3 * step + 1, step):
                    try:
                        v0 = struct.unpack_from(fmt_char, data, i)[0]
                        v1 = struct.unpack_from(fmt_char, data, i + step)[0]
                        v2 = struct.unpack_from(fmt_char, data, i + 2 * step)[0]

                        # NaN/Inf atla
                        if (v0 != v0 or v1 != v1 or v2 != v2 or
                                v0 == float('inf') or v1 == float('inf') or v2 == float('inf')):
                            continue

                        if (abs(v0 - cx) <= tol and
                                abs(v1 - cy) <= tol and
                                abs(v2 - cr) <= tol):
                            circle_candidates.append(addr + i)
                    except Exception:
                        pass

                # Fish struct: 2 değer (x, y) ardışık
                if fx > 0 and fy > 0:
                    for i in range(0, len(data) - 2 * step + 1, step):
                        try:
                            v0 = struct.unpack_from(fmt_char, data, i)[0]
                            v1 = struct.unpack_from(fmt_char, data, i + step)[0]

                            if v0 != v0 or v1 != v1:
                                continue

                            if abs(v0 - fx) <= tol and abs(v1 - fy) <= tol:
                                fish_candidates.append(addr + i)
                        except Exception:
                            pass

            scanned += read_size
            offset += read_size
            progress = (scanned / total_size) * 100 if total_size > 0 else 0
            if int(progress) % 20 == 0 and int(progress) != int((scanned - read_size) / total_size * 100):
                print(f"  %{int(progress)}... circle={len(circle_candidates)} fish={len(fish_candidates)}")

    # ── Sonuçlar ──
    print_header("Sonuçlar")

    print(f"\nFormat: {fmt_name}, Boyut: {size} byte")
    print(f"\nCircle struct adayları: {len(circle_candidates)}")
    for addr in circle_candidates[:10]:
        off = addr - scanner._base_addr
        print(f"  0x{addr:08X} (base+0x{off:08X})")
        v0 = struct.unpack_from(fmt_char, scanner.read_bytes(addr, size*3) or b'\x00'*size*3, 0)[0]
        v1 = struct.unpack_from(fmt_char, scanner.read_bytes(addr, size*3) or b'\x00'*size*3, size)[0]
        v2 = struct.unpack_from(fmt_char, scanner.read_bytes(addr, size*3) or b'\x00'*size*3, 2*size)[0]
        print(f"    → x={v0}, y={v1}, r={v2}")

    if circle_candidates:
        scanner.discovered_offsets["circle_x"] = circle_candidates[0]
        scanner.discovered_offsets["circle_y"] = circle_candidates[0] + size
        scanner.discovered_offsets["circle_radius"] = circle_candidates[0] + 2 * size
        scanner.discovered_offsets["_format"] = fmt_name
        scanner.discovered_offsets["_size"] = size
        print(f"\n✅ Circle struct: 0x{circle_candidates[0]:08X}")

    print(f"\nFish struct adayları: {len(fish_candidates)}")
    for addr in fish_candidates[:10]:
        off = addr - scanner._base_addr
        print(f"  0x{addr:08X} (base+0x{off:08X})")

    if fish_candidates:
        scanner.discovered_offsets["fish_x"] = fish_candidates[0]
        scanner.discovered_offsets["fish_y"] = fish_candidates[0] + size
        print(f"\n✅ Fish struct: 0x{fish_candidates[0]:08X}")

    if circle_candidates or fish_candidates:
        scanner.save_offsets("offsets.json")
    else:
        print("\n❌ Struct bulunamadı. Circle değerleri bellekte")
        print("   farklı bir formatta veya dağınık halde saklanıyor.")
        print(f"\n   Aranan değerler: cx={cx}, cy={cy}, r={cr}")
        print(f"   Kullanılan format: {fmt_name}")

    print("\n── Bitti ──")
    scanner.detach()
    return 0


if __name__ == "__main__":
    sys.exit(main())
