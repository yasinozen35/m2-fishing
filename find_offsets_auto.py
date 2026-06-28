"""
find_offsets_auto.py — Zekice Zaman Farkı Taraması (Differential Scan) V3 (Numpy-Powered).

Ekranda OpenCV'nin gördüğü X koordinatıyla, oyunun RAM'e yazdığı X koordinatı 
(göreceli koordinat, pencere içi koordinat vb.) farklı olabilir. 
Bu yüzden "Bilinmeyen İlk Değer" (Unknown Initial Value) taraması yaparız.

Sadece balığın "DEĞİŞİM MİKTARINI" (Delta X) kullanarak tüm RAM'i saniyeler içinde tarar.
"""

import os
import struct
import sys
import time

if sys.platform == "win32":
    try:
        import ctypes
        if ctypes.windll.shell32.IsUserAnAdmin() == 0:
            print("Admin yetkisi isteniyor...")
            params = ' '.join(f'"{a}"' if ' ' in a else a for a in sys.argv[1:])
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable,
                f'"{sys.argv[0]}" {params}',
                os.getcwd(), 1,
            )
            sys.exit(0)
    except Exception:
        pass

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import numpy as np
from fishing_bot.memory_scanner import MemoryScanner
from fishing_bot.config import CaptureConfig, CircleDetectConfig, FishDetectConfig
from fishing_bot.screen_capture import ScreenCapture
from fishing_bot.detector import Detector

def print_header(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def take_snapshots(scanner):
    """Tüm okunabilir bellek bölgelerini Numpy dizisi olarak kaydeder."""
    snapshots = []
    total_mb = 0
    for region in scanner._regions:
        data = scanner.read_bytes(region.base, region.size)
        if data and len(data) > 4:
            pad = len(data) % 4
            if pad != 0:
                data = data[:-pad]
            
            # Belleği float32 ve int32 olarak aynı anda yorumla (4-byte aligned)
            arr_f32 = np.frombuffer(data, dtype=np.float32)
            arr_i32 = np.frombuffer(data, dtype=np.int32)
            snapshots.append((region.base, arr_f32, arr_i32))
            total_mb += len(data) / (1024*1024)
            
    print(f"  Toplam Okunan Bellek: {total_mb:.1f} MB")
    return snapshots

def main():
    print_header("Zekice Offset Keşfi (Numpy Delta Scan V4 - Çember Göreceli)")
    print("Oltayı atın ve minigame'in ekranda GÖRÜNÜR olmasını sağlayın.")
    input("Minigame aktifse ve balık yüzüyorsa ENTER'a basın...")

    scanner = MemoryScanner("metin2client.exe")
    if not scanner.find_and_attach():
        print("❌ Metin2 bulunamadı! Yönetici olarak çalıştırdığınıza emin olun.")
        time.sleep(3)
        return 1
    scanner.enumerate_regions()
    print(f"✓ Memory taramaya hazır.")

    capture = ScreenCapture(CaptureConfig())
    detector = Detector(CircleDetectConfig(), FishDetectConfig())

    # ─── Adım 1: Çemberi ve balığın göreceli pozisyonunu bul ───
    print("\n🔍 Adım 1: Minigame'i ekranda tespit ediyorum...")
    
    state1 = None
    for _ in range(80):
        frame = capture.grab_full_frame()
        result = detector.detect(frame)
        if result.fish and result.circle:
            # Balığın çembere göre koordinatı (göreceli, küçük sayılar: -100..+100)
            rel_x = result.fish.center_x - result.circle.center_x
            rel_y = result.fish.center_y - result.circle.center_y
            state1 = {
                "rel_x": rel_x, "rel_y": rel_y,
                "abs_x": result.fish.center_x, "abs_y": result.fish.center_y,
                "cx": result.circle.center_x, "cy": result.circle.center_y,
                "cr": result.circle.radius
            }
            break
        time.sleep(0.05)

    if state1 is None:
        print("❌ Ekranda balık veya çember tespit edilemedi!")
        capture.close()
        time.sleep(3)
        return 1

    print(f"  Çember Merkezi: ({state1['cx']}, {state1['cy']}), Yarıçap: {state1['cr']}")
    print(f"  Balık Göreceli: ({state1['rel_x']:+.1f}, {state1['rel_y']:+.1f})")
    print(f"  Balık Mutlak:   ({state1['abs_x']}, {state1['abs_y']})")
    
    # ─── Adım 2: İlk Memory Snapshot ───
    print("\n🔍 Adım 2: Memory Snapshot 1 alınıyor...")
    snap1 = take_snapshots(scanner)

    # ─── Adım 3: Balığın az hareket etmesini bekle ───
    print("\n🔍 Adım 3: Balığın ÇEMBER İÇİNDE hareket etmesi bekleniyor...")
    print("  (Sadece küçük hareketler kabul ediliyor: 3-60 piksel)")
    
    state2 = None
    start_wait = time.time()
    while time.time() - start_wait < 15.0:
        frame = capture.grab_full_frame()
        result = detector.detect(frame)
        if result.fish and result.circle:
            rel_x2 = result.fish.center_x - result.circle.center_x
            rel_y2 = result.fish.center_y - result.circle.center_y
            dx = rel_x2 - state1["rel_x"]
            dy = rel_y2 - state1["rel_y"]
            # Sadece makul hareketleri (3-60px) kabul et. 900px zıplamalar OpenCV hatasıdır.
            if 3 < abs(dx) < 60 or 3 < abs(dy) < 60:
                state2 = {"rel_x": rel_x2, "rel_y": rel_y2, "dx": dx, "dy": dy}
                break
        time.sleep(0.04)
        
    if state2 is None:
        print("❌ Makul bir balık hareketi tespit edilemedi.")
        print("   Balık çok hızlı veya çok yavaş hareket ediyor olabilir.")
        capture.close()
        time.sleep(3)
        return 1

    print(f"  Hareket! Göreceli Δ = ({state2['dx']:+.1f}, {state2['dy']:+.1f})")

    # ─── Adım 4: Snapshot 2 + Delta Karşılaştırması ───
    print("\n🔍 Adım 4: Memory Snapshot 2 alınıyor ve Delta aranıyor...")
    
    dx_rel = state2["dx"]
    dy_rel = state2["dy"]
    
    candidates = []  # (addr, curr_val, fmt, axis)
    for base, old_f32, old_i32 in snap1:
        data = scanner.read_bytes(base, len(old_f32) * 4)
        if not data or len(data) != len(old_f32) * 4:
            continue
            
        new_f32 = np.frombuffer(data, dtype=np.float32)
        new_i32 = np.frombuffer(data, dtype=np.int32)

        with np.errstate(invalid='ignore', over='ignore'):
            # FLOAT: Δ olarak dx_rel'e yakın mı?
            diff_f32 = new_f32.astype(np.float64) - old_f32.astype(np.float64)
            fin = np.isfinite(diff_f32)
            for delta_target, axis in [(dx_rel, "X"), (dy_rel, "Y")]:
                match = fin & (np.abs(diff_f32 - delta_target) <= 2.5)
                for idx in np.where(match)[0]:
                    candidates.append((base + int(idx) * 4, float(new_f32[idx]), "float", axis))

        with np.errstate(invalid='ignore', over='ignore'):
            # INT32: Δ olarak dx_rel'e yakın mı? 
            diff_i32 = new_i32.astype(np.float64) - old_i32.astype(np.float64)
            for delta_target, axis in [(dx_rel, "X"), (dy_rel, "Y")]:
                match = np.abs(diff_i32 - delta_target) <= 2.5
                for idx in np.where(match)[0]:
                    candidates.append((base + int(idx) * 4, float(new_i32[idx]), "int32", axis))

    print(f"  Aday sayısı: {len(candidates)}")
    
    # ─── Adım 5: Makul değer aralığı filtresi ───
    # Balık çember içinde koordinatları. Mutlak ekran/pencere koordinatı veya göreceli olabilir.
    # Ekran çözünürlükleri düşünülerek sınırı -2500..+2500 yapıyoruz (aşırı alakasız RAM adreslerini engellemek için)
    filtered = [(a, v, f, ax) for a, v, f, ax in candidates
                if abs(v) <= 2500.0]
    print(f"  Makul değer aralığında kalan: {len(filtered)}")
    candidates = filtered if filtered else candidates

    # ─── Adım 6: 3. Hareket ile son eleme ───
    if len(candidates) > 10:
        print("\n🔍 Adım 5: 3. hareket bekleniyor (son eleme)...")
        state3 = None
        start_wait = time.time()
        while time.time() - start_wait < 12.0:
            frame = capture.grab_full_frame()
            result = detector.detect(frame)
            if result.fish and result.circle:
                rel_x3 = result.fish.center_x - result.circle.center_x
                rel_y3 = result.fish.center_y - result.circle.center_y
                dx3 = rel_x3 - state2["rel_x"]
                dy3 = rel_y3 - state2["rel_y"]
                if 3 < abs(dx3) < 60 or 3 < abs(dy3) < 60:
                    state3 = {"dx": dx3, "dy": dy3}
                    break
            time.sleep(0.04)
            
        if state3:
            print(f"  3. Hareket: Δ = ({state3['dx']:+.1f}, {state3['dy']:+.1f})")
            new_candidates = []
            for addr, prev_val, fmt, axis in candidates:
                data = scanner.read_bytes(addr, 4)
                if data:
                    if fmt == "float":
                        curr_val = struct.unpack('<f', data)[0]
                    else:
                        curr_val = struct.unpack('<i', data)[0]
                    
                    delta_target = state3["dx"] if axis == "X" else state3["dy"]
                    dx_mem = float(curr_val) - prev_val
                    if abs(dx_mem - delta_target) <= 2.5:
                        new_candidates.append((addr, curr_val, fmt, axis))
                        
            print(f"  Kalan: {len(new_candidates)}")
            if new_candidates:
                candidates = new_candidates

    capture.close()

    if not candidates:
        print("❌ Balık adresi bulunamadı.")
        time.sleep(5)
        return 1

    # X ve Y adaylarını ayır
    x_candidates = [(a, v, f) for a, v, f, ax in candidates if ax == "X"]
    y_candidates = [(a, v, f) for a, v, f, ax in candidates if ax == "Y"]
    
    print(f"\n  X ekseni adayı: {len(x_candidates)}, Y ekseni adayı: {len(y_candidates)}")
    
    if not x_candidates:
        x_candidates = [(a, v, f) for a, v, f, ax in candidates]
        
    resolved_fish_x = x_candidates[0][0]
    best_fmt = x_candidates[0][2]
    
    # Y adresini bul (genelde X+4)
    resolved_fish_y = x_candidates[0][0] + 4
    if y_candidates:
        # Y adayından en yakın olanı seç
        resolved_fish_y = min(y_candidates, key=lambda c: abs(c[0] - (resolved_fish_x + 4)))[0]

    print_header("BAŞARILI! (Kısmi)")
    print(f"✅ Balık X Adresi: 0x{resolved_fish_x:08X} (Format: {best_fmt}, Değer: {x_candidates[0][1]:.1f})")
    print(f"✅ Balık Y Adresi: 0x{resolved_fish_y:08X}")

    # ─── Timer ile Circle Tarama ───
    # Minigame timer'ı 15 → 0 arası sürekli azalır.
    # Bu monoton azalan değeri kullanarak timer adresini buluruz,
    # ardından yakınındaki belleğe bakarak circle verilerini çıkarırız.
    print("\n🔍 Timer ile Çember adresi aranıyor...")
    print("  Yeni bir minigame başlatın (olta at, balık gelsin)...")
    print("  Timer başlayınca ENTER'a basın...")
    input()
    
    # Timer okuma 1
    t1_start = time.time()
    timer_snap1 = take_snapshots(scanner)
    t1_elapsed = time.time() - t1_start
    
    wait_secs = 2.5
    print(f"  {wait_secs:.1f} saniye bekleniyor...")
    time.sleep(wait_secs)
    
    # Timer okuma 2
    t2_start = time.time()
    timer_snap2_data = {}
    for base, old_f32, _ in timer_snap1:
        data = scanner.read_bytes(base, len(old_f32) * 4)
        if data and len(data) == len(old_f32) * 4:
            timer_snap2_data[base] = np.frombuffer(data, dtype=np.float32)
    t2_elapsed = time.time() - t2_start

    print(f"  {wait_secs:.1f} saniye daha bekleniyor (doğrulama için)...")
    time.sleep(wait_secs)

    # Timer okuma 3
    t3_start = time.time()
    timer_snap3_data = {}
    for base, old_f32, _ in timer_snap1:
        if base in timer_snap2_data:
            data = scanner.read_bytes(base, len(old_f32) * 4)
            if data and len(data) == len(old_f32) * 4:
                timer_snap3_data[base] = np.frombuffer(data, dtype=np.float32)
    t3_elapsed = time.time() - t3_start
    
    timer_candidates = []
    expected_decrease_1 = -(wait_secs + t1_elapsed)  # yaklaşık -2.5 saniye
    expected_decrease_2 = -(wait_secs + t2_elapsed)  # yaklaşık -2.5 saniye
    
    for base, old_f32, _ in timer_snap1:
        if base not in timer_snap3_data:
            continue
            
        mid_f32 = timer_snap2_data[base]
        new_f32 = timer_snap3_data[base]
        
        diff1 = mid_f32.astype(np.float64) - old_f32.astype(np.float64)
        diff2 = new_f32.astype(np.float64) - mid_f32.astype(np.float64)
        with np.errstate(invalid='ignore'):
            fin = np.isfinite(diff1) & np.isfinite(diff2)
            # Timer her iki adımda da istikrarlı şekilde azalmalı (±1.5 tolerans)
            match1 = (diff1 > expected_decrease_1 - 1.5) & (diff1 < expected_decrease_1 + 1.5)
            match2 = (diff2 > expected_decrease_2 - 1.5) & (diff2 < expected_decrease_2 + 1.5)
            # Ayrıca eski değer 0-15 arasında olmalı (timer range)
            valid_range = (old_f32 > 0.0) & (old_f32 <= 16.0)
            
            for idx in np.where(fin & match1 & match2 & valid_range)[0]:
                timer_candidates.append((base + int(idx) * 4, float(new_f32[idx])))
    
    print(f"  Timer adayı: {len(timer_candidates)}")
    
    circle_x_addr = 0
    timer_addr = 0
    
    if timer_candidates:
        timer_addr = timer_candidates[0][0]
        print(f"✅ Timer Adresi: 0x{timer_addr:08X} (Şu anki değer: {timer_candidates[0][1]:.2f}s)")
        
        # Timer adresinin yakınında (±2000 byte) circle verilerini ara
        # Circle X, Y genellikle timer ile aynı struct içinde bulunur
        search_start = max(0, timer_addr - 2000)
        search_data = scanner.read_bytes(search_start, 4000)
        
        if search_data:
            # Balık X'in göreceli değeri ~58.7 idi. Circle X genellikle 0'a yakın (merkez)
            # ya da mutlak koordinat. Radius her iki durumda da pozitif.
            for i in range(0, len(search_data) - 12, 4):
                v0 = struct.unpack_from('<f', search_data, i)[0]
                v1 = struct.unpack_from('<f', search_data, i+4)[0]
                v2 = struct.unpack_from('<f', search_data, i+8)[0]
                # v2 = circle radius (oyun koordinatı: muhtemelen 50-200 arası)
                # v0, v1 = circle center (göreceli ise 0'a yakın, mutlak ise 1000+ olur)
                if (np.isfinite(v0) and np.isfinite(v1) and np.isfinite(v2) and
                    10 < v2 < 400):  # mantıklı radius range
                    circle_x_addr = search_start + i
                    print(f"✅ Çember Adayı: 0x{circle_x_addr:08X}  CX={v0:.1f} CY={v1:.1f} R={v2:.1f}")
                    break
    else:
        print("  ⚠️ Timer adresi bulunamadı (minigame kapanmış olabilir).")

    # ─── Kaydet ───
    # hex() zaten "0x..." prefix'i içeriyor, save_offsets bunu int olarak bekliyor
    # Bu yüzden int olarak kaydediyoruz
    scanner.discovered_offsets["_format"] = best_fmt          # string, hex formatlanmaz
    scanner.discovered_offsets["fish_x"] = resolved_fish_x    # int
    scanner.discovered_offsets["fish_y"] = resolved_fish_y    # int
    if timer_addr:
        scanner.discovered_offsets["timer"] = timer_addr      # int
    if circle_x_addr:
        scanner.discovered_offsets["circle_x"] = circle_x_addr        # int
        scanner.discovered_offsets["circle_y"] = circle_x_addr + 4    # int
        scanner.discovered_offsets["circle_radius"] = circle_x_addr + 8  # int

    scanner.save_offsets("offsets.json")
    print("\n✅ offsets.json dosyasına KALICI olarak kaydedildi!")
    print("Artık botu başlatabilirsiniz.")
    
    scanner.detach()
    time.sleep(5)
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"Bilinmeyen Hata: {e}")
        import traceback
        traceback.print_exc()
        time.sleep(10)
