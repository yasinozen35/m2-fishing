"""
split_fishes.py — Uzun, dikey olarak birleştirilmiş balık ikonları resmini
15 eşit parçaya böler ve templates klasörüne tek tek kaydeder.
"""

import os
import cv2

FISH_NAMES = [
    "sudak",
    "tekir",
    "buyuk_sudak",
    "lufer",
    "dere_alabaligi",
    "ringa",
    "nehir_alabaligi",
    "som",
    "yayin",
    "gokkusagi_alabaligi",
    "levrek",
    "sazan",
    "ot_sazani",
    "zargana",
    "hamsi"
]

def split_image(image_path: str):
    if not os.path.exists(image_path):
        print(f"Hata: {image_path} bulunamadi!")
        return
        
    img = cv2.imread(image_path)
    if img is None:
        print("Hata: Resim okunamadi.")
        return

    print(f"Orijinal Resim Okundu. Ikonlar tespit ediliyor...")
    
    # Görüntüyü gri tonlamaya çevir ve bulanıklaştır (gürültü için)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    
    # Arka planla çerçeveleri ayırmak için edge detection (Canny) kullan
    edges = cv2.Canny(blurred, 50, 150)
    
    # Konturları bul (Kutuları tespit et)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    bounding_boxes = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        # Sadece belirli bir boyuttan büyük olanları ikon olarak kabul et
        # (Örn: En az 20x20 boyutunda olmalı)
        if w > 20 and h > 20:
            bounding_boxes.append((x, y, w, h))
            
    # Eğer iç içe geçmiş veya çok yakın olanlar varsa, birleştirilebilir.
    # Ancak basitçe Y koordinatına göre sıralayalım
    bounding_boxes = sorted(bounding_boxes, key=lambda b: b[1])
    
    # Birbirine çok yakın (aynı ikonun parçası olan) kutuları filtrele
    filtered_boxes = []
    for box in bounding_boxes:
        x, y, w, h = box
        if not filtered_boxes:
            filtered_boxes.append(box)
        else:
            prev_x, prev_y, prev_w, prev_h = filtered_boxes[-1]
            if y > prev_y + (prev_h * 0.5):  # Yeterince aşağıdaysa yeni bir ikondur
                filtered_boxes.append(box)

    # BAZI BALIKLAR BIRLESIK CIKMIS!
    # Bunun cozumu: Kutularin normal yuksekligini (medyan) bul.
    # Eger bir kutunun yuksekligi normalin iki katisaysa, onu tam ortadan ikiye bol.
    if filtered_boxes:
        import statistics
        heights = [b[3] for b in filtered_boxes]
        median_h = statistics.median(heights)
        
        final_boxes = []
        for (x, y, w, h) in filtered_boxes:
            # Bu kutunun içinde tahminen kaç ikon var?
            count = max(1, round(h / median_h))
            
            if count == 1:
                final_boxes.append((x, y, w, h))
            else:
                # Kutu iki (veya daha fazla) balığı içeriyorsa eşit parçalara böl
                step_h = h // count
                for c in range(count):
                    final_boxes.append((x, y + c * step_h, w, step_h))
                    
        # Y eksenine gore tekrar sirala
        final_boxes = sorted(final_boxes, key=lambda b: b[1])
    else:
        final_boxes = filtered_boxes

    print(f"Toplam {len(final_boxes)} adet balik ikonu cercevesi tespit edildi.")
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    templates_dir = os.path.join(base_dir, "templates")
    os.makedirs(templates_dir, exist_ok=True)
    
    saved_count = 0
    saved_count = 0
    # Eğer FISH_NAMES sayısı yeterli değilse (örneğin yeni bir resim yüklendiyse) 
    # otomatik olarak jenerik isimlerle kaydet.
    for i in range(len(final_boxes)):
        x, y, w, h = final_boxes[i]
        
        if i < len(FISH_NAMES) and "baliklar_liste" in image_path:
            name = f"fish_{FISH_NAMES[i]}"
        else:
            # İsmi bilinmeyen balıklar veya farklı resimler için
            name = f"nadir_parca_{i+1}"
            
        # Kutunun içindeki balığı kes
        piece = img[y:y+h, x:x+w]
        
        # Kaydet
        save_path = os.path.join(templates_dir, f"{name}.png")
        cv2.imwrite(save_path, piece)
        print(f"Kesildi ve Kaydedildi: {save_path} (Boyut: {w}x{h})")
        saved_count += 1
        
    print(f"\nBasariyla {saved_count} adet ikon düzgün bir sekilde cikarildi!")

if __name__ == "__main__":
    import sys
    print("Metin2 Ikon Parcalayici")
    print("-" * 30)
    
    # Kullanıcıdan argüman olarak veya varsayılan isimle bekle
    target_img = sys.argv[1] if len(sys.argv) > 1 else "baliklar_liste.png"
    split_image(target_img)
