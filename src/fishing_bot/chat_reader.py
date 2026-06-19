import mss
import numpy as np
import cv2
import pytesseract
from typing import Optional

class ChatReader:
    def __init__(self, region: dict):
        """
        region: {'top': int, 'left': int, 'width': int, 'height': int}
        """
        self.region = region
        self.sct = mss.mss()
        # Windows varsayılan kurulum yolu kontrolü:
        import os
        default_path = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
        if os.path.exists(default_path):
            pytesseract.pytesseract.tesseract_cmd = default_path

    def update_region(self, x: int, y: int, w: int, h: int):
        self.region = {'top': y, 'left': x, 'width': w, 'height': h}

    def read_chat(self) -> str:
        """
        Belirtilen chat bölgesini okur ve metin olarak döndürür.
        """
        if self.region['width'] <= 0 or self.region['height'] <= 0:
            return ""

        # Ekran görüntüsünü al
        screenshot = self.sct.grab(self.region)
        img = np.array(screenshot)

        # Görüntüyü OCR için hazırla
        # 1. Resmi 2 kat büyüt (OCR küçük yazılarda zorlanır). Performans için INTER_LINEAR kullanıyoruz.
        img_scaled = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_LINEAR)
        
        # 2. Gri tonlamaya çevir
        gray = cv2.cvtColor(img_scaled, cv2.COLOR_BGRA2GRAY)
        
        # 3. Arka plan genelde karanlık (su vs.), yazılar ise pembe/gri/beyaz
        # Pembe yazıların gri tonlama değeri genelde 150-170 civarıdır.
        # Threshold'u 120'ye düşürerek yazıları kaybetmemeyi garantiliyoruz.
        _, thresh = cv2.threshold(gray, 120, 255, cv2.THRESH_BINARY)
        
        # Yerel tessdata klasörünü belirtelim (Türkçe paket indirdik)
        import os
        project_dir = os.path.dirname(os.path.abspath(__file__))
        tessdata_dir = os.path.join(project_dir, 'tessdata')
        
        # Tesseract'a verilerin yerini ortam değişkeni ile bildiriyoruz
        if os.path.exists(os.path.join(tessdata_dir, 'tur.traineddata')):
            os.environ['TESSDATA_PREFIX'] = tessdata_dir
            
        # OCR işlemini hızlandırmak için sadece tesseract motorunu belirtiyoruz (OEM 3 = Default)
        config_to_use = '--psm 6'
        
        try:
            # Sadece tur kullanarak çift dil yükünü (tur+eng) kaldırıyoruz. Çok ciddi performans artışı sağlar.
            text = pytesseract.image_to_string(thresh, lang='tur', config=config_to_use)
            return text.strip()
        except Exception as e:
            try:
                text = pytesseract.image_to_string(thresh, lang='eng', config=config_to_use)
                return text.strip()
            except Exception as e2:
                print(f"OCR Hatası: {e2}")
                return ""

    def get_raw_chat(self) -> str:
        """
        Ekranda beliren yazıyı ham metin olarak döndürür.
        """
        return self.read_chat()
