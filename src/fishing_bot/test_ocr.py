import cv2
import pytesseract
import sys
import os
import numpy as np

# Tesseract yolu
default_path = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
if os.path.exists(default_path):
    pytesseract.pytesseract.tesseract_cmd = default_path

def test_ocr(image_path):
    if not os.path.exists(image_path):
        print(f"Resim bulunamadı: {image_path}")
        return

    # Resmi oku
    img = cv2.imread(image_path)
    
    # 1. Orijinal resmi göster
    cv2.imshow("1 - Orijinal Resim", img)
    
    # 2. Gri Tonlama
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    cv2.imshow("2 - Gri Tonlama", gray)
    
    # 3. Threshold (180 sınırı - Botun şu anki ayarı)
    _, thresh_180 = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY)
    cv2.imshow("3 - Threshold 180 (Mevcut)", thresh_180)
    
    # 4. Alternatif Threshold (Daha düşük sınır, pembe/gri yazılar için)
    _, thresh_130 = cv2.threshold(gray, 130, 255, cv2.THRESH_BINARY)
    cv2.imshow("4 - Threshold 130 (Test)", thresh_130)

    # 5. Otsu Threshold (Otomatik)
    _, thresh_otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    cv2.imshow("5 - Otsu Threshold (Test)", thresh_otsu)
    
    print("=== OCR TEST SONUÇLARI ===")
    
    # Mevcut ayarlarla okuma
    try:
        text_180 = pytesseract.image_to_string(thresh_180, lang='tur+eng', config='--psm 6')
        print("\n--- Mevcut Ayar (Threshold 180) ile Okunan: ---")
        print(text_180.strip())
    except Exception as e:
        print(f"Hata: {e}")

    # Yeni Threshold ile okuma
    try:
        text_130 = pytesseract.image_to_string(thresh_130, lang='tur+eng', config='--psm 6')
        print("\n--- Yeni Ayar (Threshold 130) ile Okunan: ---")
        print(text_130.strip())
    except Exception as e:
        print(f"Hata: {e}")

    print("\nLütfen açılan resim pencerelerini inceleyin. '3 - Threshold 180' penceresinde yazılar SİMSİYAH olmuşsa (görünmüyorsa), sorun Threshold değerindedir.")
    print("Pencereleri kapatmak için herhangi bir pencere seçiliyken klavyeden bir tuşa basın.")
    
    cv2.waitKey(0)
    cv2.destroyAllWindows()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        test_ocr(sys.argv[1])
    else:
        print("Kullanım: uv run python test_ocr.py <resim_yolu>")
