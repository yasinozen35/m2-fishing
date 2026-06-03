"""
download_fish_icons.py — Metin2 Wiki'den balık resimlerini indirir.

Envanter taraması (Template Matching) yapabilmek için gerekli olan
resimleri indirip templates klasörüne kaydeder.
"""

import os
import requests

# TR ve EN Wiki'den doğrudan ikon URL'leri
FISH_URLS = {
    "sazan.png": "https://tr-wiki.metin2.gameforge.com/images/1/1a/Sazan.png",
    "sudak.png": "https://tr-wiki.metin2.gameforge.com/images/3/30/Sudak.png",
    "ringa.png": "https://tr-wiki.metin2.gameforge.com/images/a/ab/Ringa_Bal%C4%B1%C4%9F%C4%B1.png",
    "palamut.png": "https://tr-wiki.metin2.gameforge.com/images/d/da/Palamut_Bal%C4%B1%C4%9F%C4%B1.png",
    "yilan_baligi.png": "https://en-wiki.metin2.gameforge.com/images/7/7b/Eel.png",
    # Yem olarak kullanılacak balıklar 'bait_' ön ekiyle kaydedilir
    "bait_minnow.png": "https://en-wiki.metin2.gameforge.com/images/2/27/Minnow.png"
}

def download_icons():
    # templates klasörünü oluştur
    base_dir = os.path.dirname(os.path.abspath(__file__))
    templates_dir = os.path.join(base_dir, "templates")
    os.makedirs(templates_dir, exist_ok=True)
    
    print("Balik ikonlari indiriliyor...")
    
    for filename, url in FISH_URLS.items():
        filepath = os.path.join(templates_dir, filename)
        
        # Eğer resim zaten varsa indirme
        if os.path.exists(filepath):
            print(f"  [OK] Zaten mevcut: {filename}")
            continue
            
        try:
            # Gameforge sunucuları bazen User-Agent isteyebiliyor
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                with open(filepath, "wb") as f:
                    f.write(response.content)
                print(f"  [INDIRILDI] {filename}")
            else:
                print(f"  [HATA] {filename} indirilemedi. Status: {response.status_code}")
        except Exception as e:
            print(f"  [HATA] {filename} indirilirken hata olustu: {e}")

if __name__ == "__main__":
    download_icons()
