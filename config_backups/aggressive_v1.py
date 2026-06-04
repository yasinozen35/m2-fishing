"""
AGRESIF OPTIMIZASYON DEGERLERI (Referans: 2024-06-04)
=====================================================
Bu değerlerle her oyunda 3/3 tıklama yapılabiliyor.
Anti-cheat için uygun DEĞİLDİR. İnsanileştirme için referans alınacak.
"""

# ============================================================
# config.py - HumanConfig
# ============================================================
AGGRESSIVE_CONFIG = {
    "reaction_min": 0.0,        # Reaksiyon gecikmesi (sıfır - anında tepki)
    "reaction_max": 0.0,        # Reaksiyon gecikmesi (sıfır - anında tepki)
    "aim_offset_px": 0,          # Tıklama sapması (sıfır - tam hedef)
    "click_cooldown": 0.08,      # Tıklamalar arası süre (80ms - spam)
}

# ============================================================
# clicker.py - Win32Clicker.fastClick()
# ============================================================
AGGRESSIVE_CLICKER = {
    "fastClick_hold_min": 0.005,  # Mouse basılı tutma minimum (5ms)
    "fastClick_hold_max": 0.015,  # Mouse basılı tutma maksimum (15ms)
    "mouse_movement": "teleport", # SetCursorPos direkt ışınlanma
    "pre_click_sleep": 0.0,       # Tık öncesi bekleme (kaldırıldı)
}

# ============================================================
# bot_logic.py - Minigame prediction
# ============================================================
AGGRESSIVE_PREDICTION = {
    "look_ahead_time": 0.06,      # Velocity tahmin süresi (60ms)
    "lead_px": 8,                 # Hareket yönünde ek lead (8 piksel)
    "lead_min_speed": 15,         # Lead uygulamak için min hız (px/s)
    "safe_radius_ratio": 0.82,    # Daire yarıçapının güvenli bölge oranı
    "first_frame_skip": False,    # İlk kare atlanmaz, raw pozisyona tıklar
    "stale_data_fallback": True,  # Eski veride raw pozisyona tıkla
}

# ============================================================
# PENCERE: Toplam gecikme zinciri
# ============================================================
# Detection → safe check → predict(60ms+8px) → teleport → fastClick(5-15ms)
# Toplam: ~10-20ms (frame capture + processing + click delivery)
# Tahmin 60ms ileri + 8px lead → balığın hareket yönünde burnuna tıklar
