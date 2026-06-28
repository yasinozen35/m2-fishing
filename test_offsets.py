"""
test_offsets.py — Bulunan adreslerin gerçekten doğru olup olmadığını 5 sn canlı okur.
Botu başlatmadan önce çalıştırın!
"""
import sys, os, time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from fishing_bot.memory_reader import MemoryReader

def main():
    print("=" * 55)
    print("  Offset Doğrulama Testi")
    print("=" * 55)
    print("Minigame'i AÇIK tutun ve ENTER'a basın...")
    input()

    try:
        reader = MemoryReader()
    except Exception as e:
        print(f"Baglanılamadı: {e}")
        time.sleep(5)
        return

    print("\n5 saniye boyunca her 0.2 sn'de bir okuyorum...\n")
    print(f"{'Aktif?':>7} | {'Timer':>6} | {'CX':>8} {'CY':>8} {'CR':>7} | {'FishX':>8} {'FishY':>8} | Icinde?")
    print("-" * 80)

    for _ in range(25):
        state = reader.get_fishing_state()
        inside = "EVET" if state.is_fish_inside else "Hayir"
        visible = "AKTIF" if state.circle_visible else "---"

        # Timer'ı ayrıca oku
        timer_addr = reader._resolve_addr("timer")
        timer_val = reader.read_float(timer_addr) if timer_addr else 0.0

        print(f"{visible:>7} | {(timer_val or 0):6.2f} | "
              f"{state.circle_x:8.1f} {state.circle_y:8.1f} {state.circle_radius:7.1f} | "
              f"{state.fish_x:8.1f} {state.fish_y:8.1f} | {inside}")
        time.sleep(0.2)

    reader.close()
    print("\nTest tamamlandı.")
    print("Eger degerler minigame boyunca makul sekilde degisiyorsa bot hazir!")
    time.sleep(5)

if __name__ == "__main__":
    main()
