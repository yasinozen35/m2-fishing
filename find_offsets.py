"""
find_offsets.py — Otomatik memory offset keşif aracı.

Mevcut botun OpenCV tespitlerini kullanarak Metin2'nin
hafızasındaki balık/daire pozisyonlarını otomatik bulur.

Çalışma Mantığı:
1. Bot'u başlat, mini-game sırasında OpenCV tespitlerini al
2. Her frame'de:
   - OpenCV'nin bulduğu circle (cx, cy, radius) ve fish (fx, fy) değerlerini
   - Memory'de bu float değerleri tara
3. İteratif filtreleme ile doğru adresleri bul
4. Pointer chain keşfi ile kalıcı offset'leri kaydet

Kullanım:
    uv run python find_offsets.py
"""

import os
import sys
import time
import math

# Proje import'ları için path ayarla
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from fishing_bot.memory_scanner import MemoryScanner, ScanResult


def print_header(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_step(step: int, msg: str) -> None:
    print(f"\n🔍 Adım {step}: {msg}")


def guided_scan_float(scanner: MemoryScanner,
                      known_value: float,
                      label: str) -> list[ScanResult]:
    """
    Bilinen bir float değerle tarama yap.
    İlk tarama geniş, sonraki taramalar mevcut sonuçları filtreler.
    """
    if not scanner._last_results:
        # İlk tarama — tüm memory
        print(f"  [{label}] İlk tarama: değer = {known_value:.4f}")
        results = scanner.scan_float(known_value, tolerance=1.0)
        scanner.set_results(results)
        print(f"  [{label}] {len(results)} adres bulundu (ilk tarama)")
    else:
        # Sonraki tarama — mevcut sonuçları filtrele
        results = scanner.filter_by_value(known_value, value_type="float",
                                          tolerance=1.5)
        print(f"  [{label}] {len(results)} adres kaldı (filtre sonrası)")
    return results


def main():
    print_header("Metin2 Memory Offset Keşif Aracı")
    print("\nBu araç, Cheat Engine kullanmadan Metin2'nin hafızasındaki")
    print("balık/daire pozisyonlarını otomatik olarak bulur.")
    print()
    print("ÖNCE: Metin2'yi açın, oltayı atın ve balık mini-game başlasın.")
    print("Ardından bu script'i çalıştırın.")
    print()
    input("Hazırsanız ENTER'a basın...")

    # ── Scanner başlat ──
    scanner = MemoryScanner("metin2client.exe")
    if not scanner.find_and_attach():
        print("\n❌ Metin2 bulunamadı! Önce oyunu başlatın.")
        return 1

    scanner.enumerate_regions()
    scanner.print_regions_summary()

    # ── Manuel değer girişi ile tarama ──
    # Kullanıcı overlay'den veya bot'tan circle/fish değerlerini girer
    print_header("Manuel Değer Girişi ile Tarama")
    print()
    print("Circle ve fish değerlerini overlay penceresinden okuyun.")
    print("Veya bot çalışıyorsa bot_logic.py size koordinatları gösterir.")
    print("\nTarama modları:")
    print("  1: Circle X tara")
    print("  2: Circle Y tara")
    print("  3: Circle Radius tara")
    print("  4: Fish X tara")
    print("  5: Fish Y tara")
    print("  6: Circle Visible (int: 0=gizli, 1=görünür)")
    print("  7: Tüm değerleri tek seferde gir")
    print("  0: Pointer chain keşfine geç")

    scanning = True
    scan_labels = {
        "circle_x": ("float", "Circle X"),
        "circle_y": ("float", "Circle Y"),
        "circle_radius": ("float", "Circle Radius"),
        "fish_x": ("float", "Fish X"),
        "fish_y": ("float", "Fish Y"),
        "circle_visible": ("int32", "Circle Visible"),
    }

    while scanning:
        print()
        choice = input("Mod seçin (0-7): ").strip()

        if choice == "0":
            scanning = False
        elif choice == "7":
            # Tüm değerleri tek seferde al
            print("\nTüm değerleri girin (bot overlay'den okuyun):")
            try:
                cx = float(input("  Circle X: ").strip())
                cy = float(input("  Circle Y: ").strip())
                cr = float(input("  Circle Radius: ").strip())
                fx = float(input("  Fish X: ").strip())
                fy = float(input("  Fish Y: ").strip())
                cv = int(input("  Circle Visible (0/1): ").strip())
            except ValueError:
                print("❌ Geçersiz değer!")
                continue

            targets = [
                ("circle_x", "float", cx),
                ("circle_y", "float", cy),
                ("circle_radius", "float", cr),
                ("fish_x", "float", fx),
                ("fish_y", "float", fy),
                ("circle_visible", "int32", cv),
            ]

            for name, vtype, val in targets:
                print(f"\n── {name} = {val} ──")
                if vtype == "float":
                    # Her değer için ayrı tarama context'i
                    if name not in scanner._scan_contexts:
                        scanner._scan_contexts = getattr(scanner, '_scan_contexts', {})
                        scanner._scan_contexts[name] = {"last_results": {}}

                    results = scanner.scan_float(val, tolerance=2.0)
                    scanner.set_results(results)
                    scanner.print_results(results, max_show=15)

                    if results:
                        # En olası adresleri işaretle
                        # Circle/fish koordinatları genelde heap'te
                        heap_results = [r for r in results
                                        if r.address > 0x01000000]
                        if heap_results:
                            print(f"  💡 Heap bölgesinde {len(heap_results)} adres var")
                            scanner.discovered_offsets[name] = heap_results[0].address
                elif vtype == "int32":
                    results = scanner.scan_int32(val)
                    scanner.set_results(results)
                    scanner.print_results(results, max_show=15)
                    if results:
                        scanner.discovered_offsets[name] = results[0].address

        elif choice in ("1", "2", "3", "4", "5", "6"):
            name_map = {
                "1": "circle_x", "2": "circle_y", "3": "circle_radius",
                "4": "fish_x", "5": "fish_y", "6": "circle_visible",
            }
            name = name_map[choice]
            vtype, label = scan_labels[name]

            try:
                val = float(input(f"  {label} değeri: ").strip())
            except ValueError:
                print("❌ Geçersiz değer!")
                continue

            if vtype == "float":
                results = guided_scan_float(scanner, val, label)
            else:
                if not scanner._last_results:
                    results = scanner.scan_int32(int(val))
                else:
                    results = scanner.filter_by_value(int(val), "int32")
                scanner.set_results(results)

            scanner.print_results(results, max_show=20)

            # En iyi adayı otomatik kaydet
            if results:
                heap_results = [r for r in results
                                if r.address > 0x01000000
                                and r.address < 0x70000000]
                best = heap_results[0] if heap_results else results[0]
                scanner.discovered_offsets[name] = best.address
                print(f"  💡 Kaydedildi: {name} → 0x{best.address:08X}")

    # ── Sonuçları göster ──
    print_header("Keşfedilen Offset'ler")
    if scanner.discovered_offsets:
        for name, addr in scanner.discovered_offsets.items():
            print(f"  {name:20s} → 0x{addr:08X}  "
                  f"(base+0x{addr - scanner._base_addr:08X})")

        # Kaydet
        save = input("\nOffset'leri JSON'a kaydedilsin mi? [E/h]: ").strip().lower()
        if save != 'h':
            scanner.save_offsets()
    else:
        print("  ❌ Hiç offset keşfedilmedi!")
        print("  İpucu: Overlay penceresinden tam koordinatları alın.")
        print("  Balık mini-game'i AKTİF olmalı (circle görünür olmalı).")

    print("\n── Bitti ──")
    scanner.detach()
    return 0


if __name__ == "__main__":
    sys.exit(main())
