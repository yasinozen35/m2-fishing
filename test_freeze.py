import time
import ctypes
import sys

def test_tarpit():
    if sys.platform != "win32":
        print("Bu test sadece Windows'ta calisir!")
        return
        
    print("========================================")
    print("ANTI-CHEAT TARPIT (DONMA) TESTI")
    print("========================================")
    print("Lutfen 5 saniye icinde oyun ekranina gecin ve fareyi oyunda bos bir yere birakin...")
    
    for i in range(5, 0, -1):
        print(f"Test basliyor: {i}...")
        time.sleep(1)
        
    print("\n[TEST 1] Sadece Windows API Cagirisi (mouse_event)")
    start_time = time.time()
    
    # Fare sol tik bas
    ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.05)
    # Fare sol tik birak
    ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
    
    end_time = time.time()
    elapsed = end_time - start_time
    
    print(f"-> Sistem cagrisi tamamlandi. Gecen Sure: {elapsed:.3f} saniye")
    
    if elapsed > 1.0:
        print("\n[!!! SONUC !!!]")
        print("Sistem cagirisi saniyenin onda biri surmesi gerekirken 1 saniyeden uzun surdu!")
        print("Bu durum Anti-Cheat'in (Hile Korumasinin) bu fonksiyonu 'TARPIT' yontemiyle bilerek dondurdugunun %100 KANITIDIR.")
    else:
        print("\n[SONUC]")
        print("Fonksiyon cok hizli calisti. Eger oyun hala donuyorsa sorun baska bir yerdedir.")

if __name__ == "__main__":
    test_tarpit()
