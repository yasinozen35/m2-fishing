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
    "velocity_smoothing": 2,      # Son 2 frame ile hız hesabı
}

# ============================================================
# GÜNCEL E-SPORCU DEGERLERI (2024-06-04 v2)
# ============================================================
ESPORTS_CONFIG = {
    "reaction_min": 0.04,         # 40ms
    "reaction_max": 0.08,         # 80ms
    "aim_offset_px": 0,            # jitter kapalı
    "click_cooldown": 0.10,        # 100ms
}

ESPORTS_PREDICTION = {
    "look_ahead_time": 0.07,      # 70ms (reaksiyon gecikmesini kompanse)
    "lead_px": 12,                # 12px lead (arttırıldı)
    "lead_min_speed": 10,          # Daha düşük hızda da lead uygula
    "velocity_smoothing": 3,      # Son 3 frame ile smoothed velocity (gürültü azaltma)
}

# ============================================================
# PENCERE: Toplam gecikme zinciri (e-sporcu)
# ============================================================
# Detection → safe check → smoothed velocity(3 frame) → predict(70ms+12px) →
#   reaksiyon(40-80ms) → teleport → fastClick(15-30ms)
# Toplam: ~65-125ms
# Smoothing: 3 frame ortalaması yön sapmasını minimize eder
# Lead 12px: Balığın burnunun önüne tıkla
