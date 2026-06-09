"""
bot_logic.py — Tam otonom balık botu durum makinesi (State Machine).

Oyun döngüsünü yönetir:
1. Yem tak (PREPARE)
2. Zırh değiştir (PREPARE - opsiyonel)
3. Olta at (CAST)
4. Balık bekle (WAITING)
5. Mini-oyunu oyna (MINIGAME)
6. Bekle ve başa dön (POST_CATCH)
"""

import math
import random
import time
from collections import deque
from enum import Enum, auto

from fishing_bot.config import AutoBotConfig
from fishing_bot.clicker import HumanClicker
from fishing_bot.detector import DetectionResult


class BotState(Enum):
    """Botun mevcut durumu."""
    IDLE = auto()          # Çalışmıyor / duraklatıldı
    PREPARE = auto()       # Yem takma ve zırh değiştirme
    CAST = auto()          # Oltayı suya atma
    WAITING = auto()       # Dairenin belirmesini bekleme
    MINIGAME = auto()      # Balık yakalama mini-oyunu (3 tık)
    POST_CATCH = auto()    # Yakaladıktan sonra bekleme / envanter yönetimi
    FATIGUE_BREAK = auto() # İnsan yorulması, AFK bekleme modu


class BotLogic:
    """Otonom bot döngüsünü yöneten sınıf."""

    def __init__(self, config: AutoBotConfig, clicker: HumanClicker, capture=None):
        self._cfg = config
        self._clicker = clicker
        self._capture = capture

        self.state = BotState.IDLE
        self._state_start_time = 0.0

        self.successful_catches = 0
        self.total_casts = 0
        self._click_count_in_minigame = 0
        self._prepare_action_done = False
        self._postcatch_action_done = False

        self._next_fatigue_time = 0.0
        self._fatigue_duration = 0.0

        # Frame-timer: time.sleep() yerine non-blocking bekleme
        self._block_until: float = 0.0
        # WAITING state: ardışık circle tespit sayacı (false positive önleme)
        self._consecutive_circle_count: int = 0
        # MINIGAME: balık pozisyon geçmişi (son 5 frame) — adaptif prediction için
        self._fish_pos_history: deque = deque(maxlen=5)
        # MINIGAME: tıklama ritim pattern'i (insansı çeşitlilik)
        self._click_rhythm: list[float] = []
        self._click_rhythm_idx: int = 0
        # MINIGAME: bilerek ıskalama (her ~8 balıkta bir)
        self._intentional_miss: bool = False
        self._catch_streak: int = 0
        # WAITING: idle mouse hareket zamanlayıcısı
        self._last_idle_move: float = 0.0
        # MINIGAME: İnsansı reaksiyon gecikmesi sistemi
        self._reaction_delay: float = 0.0       # Bu tıklama için random reaksiyon süresi
        self._fish_entered_safe_at: float = 0.0  # Balık safe zone'a ilk girdiği an
        self._fish_was_inside: bool = False      # Önceki frame'de balık içerde miydi?

    def start(self) -> None:
        """Döngüyü başlatır."""
        self.state = BotState.PREPARE
        self._state_start_time = time.time()
        self._click_count_in_minigame = 0
        
        if self._cfg.use_fatigue_system:
            self._next_fatigue_time = time.time() + random.uniform(
                self._cfg.fatigue_interval_min, 
                self._cfg.fatigue_interval_max
            )

    def stop(self) -> None:
        """Döngüyü durdurur."""
        self.state = BotState.IDLE

    def update(self, detection: DetectionResult, frame=None, detector=None) -> tuple[bool, str]:
        """
        Her karede durum makinesini günceller.
        
        Args:
        Args:
            detection: Ekran görüntüsünden tespit sonuçları.
            detector: Detector objesi (opsiyonel, envanter taramak için).
            
        Returns:
            (clicked, status_message): Bu update'te tıklama yapıldı mı, mevcut durum stringi.
        """
        now = time.time()
        elapsed = now - self._state_start_time
        clicked = False
        status_msg = ""

        if self.state == BotState.IDLE:
            status_msg = "Bot Durduruldu"

        elif self.state == BotState.PREPARE:
            # Non-blocking: sadece bu state'e ilk girildiğinde aksiyonu yap
            if not getattr(self, "_prepare_action_done", False):
                self._prepare_action_done = True

                # 1. Yem tak
                bait_clicked = False
                # Ekranda (envanterde) minik balık var mı kontrol et
                if self._capture is not None and detector is not None:
                    full_frame = self._capture.grab_full_frame()
                    baits = detector.detect_inventory_items(full_frame, item_type="bait")
                    if baits:
                        bx, by = baits[0]
                        self._clicker.right_click_at(bx, by)
                        bait_clicked = True
                        status_msg = "Minik Balik yeme takildi"

                if not bait_clicked:
                    self._clicker.press_key(self._cfg.key_bait)
                    status_msg = "Hazirlik: Normal Yem takildi"

                # 1 saniye bekle (±random) — yem takıldıktan sonra olta atmak için
                self._block_until = now + random.uniform(0.90, 1.20)

            # Yem takma sonrası bekleme süresi doldu mu?
            if now < self._block_until:
                status_msg = f"Hazirlik: Bekleniyor... ({self._block_until - now:.1f}s)"
                return False, status_msg

            # 2. Zırh değiştir (opsiyonel trick - Animasyon İptali)
            if self._cfg.use_armor_trick and self._cfg.armor_x > 0 and self._cfg.armor_y > 0:
                # Zırh trick'i sadece bir kez yap
                if not getattr(self, "_armor_trick_done", False):
                    self._armor_trick_done = True
                    self._clicker.right_click_at(self._cfg.armor_x, self._cfg.armor_y)
                    self._block_until = now + 0.15
                    status_msg = "Hazirlik: Zirh cikariliyor..."
                    return False, status_msg
                elif now < self._block_until:
                    status_msg = "Hazirlik: Zirh takiliyor..."
                    return False, status_msg
                elif not getattr(self, "_armor_trick_phase2", False):
                    self._armor_trick_phase2 = True
                    self._clicker.right_click_at(self._cfg.armor_x, self._cfg.armor_y)
                    self._block_until = now + self._cfg.delay_after_armor
                    status_msg = "Hazirlik: Zirh geri takildi"
                    return False, status_msg
                elif now < self._block_until:
                    status_msg = f"Hazirlik: Zirh bekleniyor... ({self._block_until - now:.1f}s)"
                    return False, status_msg

            self._transition_to(BotState.CAST)
            if not status_msg:
                status_msg = "Hazirlik: Yem takildi"

        elif self.state == BotState.CAST:
            # Non-blocking: oltayı sadece bir kez at
            if not getattr(self, "_cast_done", False):
                self._cast_done = True
                # Oltayı at - oyunun yemi algılaması için mini gecikme
                self._block_until = now + 0.05
                status_msg = "CAST: Hazirlaniyor..."
                return False, status_msg

            if now < self._block_until:
                status_msg = "CAST: Hazirlaniyor..."
                return False, status_msg

            if not getattr(self, "_cast_pressed", False):
                self._cast_pressed = True
                # Space tuşuna bas
                self._clicker.press_key(self._cfg.key_fish, hold_min=0.12, hold_max=0.25)
                self.total_casts += 1
                # Cast sonrası animasyon beklemesi başlat (bu sürede tespit yapma)
                self._block_until = now + self._cfg.delay_after_cast
                status_msg = "CAST: Olta atildi, animasyon bekleniyor..."
                return False, status_msg

            # Animasyon süresi doldu mu?
            if now < self._block_until:
                status_msg = f"CAST: Animasyon... ({self._block_until - now:.1f}s)"
                return False, status_msg

            self._transition_to(BotState.WAITING)
            status_msg = "Olta atildi, balik bekleniyor"

        elif self.state == BotState.WAITING:
            status_msg = f"Balik bekleniyor... ({int(elapsed)}s)"

            # ── Idle Mouse Hareketi (İnsan sıkılmış gibi) ──
            # Her 3-7 saniyede bir fareyi hafifçe oynat
            if now - self._last_idle_move > random.uniform(3.0, 7.0):
                self._last_idle_move = now
                try:
                    import pyautogui
                    cur_x, cur_y = pyautogui.position()
                    jitter_x = cur_x + random.randint(-25, 25)
                    jitter_y = cur_y + random.randint(-25, 25)
                    # Küçük, yavaş hareket (oyuncu etrafa bakıyor gibi)
                    import ctypes
                    ctypes.windll.user32.SetCursorPos(jitter_x, jitter_y)
                except Exception:
                    pass  # Mouse hareketi başarısız olursa sessizce devam et

            # Daire tespit edilirse MINIGAME'e geç (anında, bekleme yok)
            if detection.circle is not None:
                self._transition_to(BotState.MINIGAME)
            else:
                # Circle yok → sayacı sıfırla
                self._consecutive_circle_count = 0

            # Timeout (balık vurmadıysa veya kaçtıysa)
            if elapsed > self._cfg.timeout_waiting_fish:
                self._transition_to(BotState.POST_CATCH)

        elif self.state == BotState.MINIGAME:
            status_msg = f"MINIGAME: {self._click_count_in_minigame}/3 Tik"

            # Daire kaybolduysa hemen çıkma — 5 frame üst üste yoksa gerçekten bitti
            if detection.circle is None:
                missing_count = getattr(self, "_circle_missing_count", 0) + 1
                self._circle_missing_count = missing_count
                if missing_count >= 5:
                    if self._click_count_in_minigame >= 3:
                        self.successful_catches += 1
                    if detector is not None:
                        detector.invalidate_circle_cache()
                    self._circle_missing_count = 0
                    self._transition_to(BotState.POST_CATCH)
                else:
                    status_msg = f"MINIGAME: Circle yok ({missing_count}/5)..."
                    return False, status_msg  # Tıklama yapma, bekle
            else:
                self._circle_missing_count = 0
                # Maksimum 8 tık — 15sn minigame'de ~0.5sn aralıklarla doğal ritim
                if self._click_count_in_minigame >= 8:
                    status_msg = f"MINIGAME: {self._click_count_in_minigame} tik tamam, circle kapaniyor..."
                    return False, status_msg
                # Balık içerdeyse işle
                if detection.is_fish_inside and detection.fish is not None:

                    # ── ADAPTİF HIZ VE TAHMİN (PREDICTION) ALGORİTMASI ──
                    current_x = detection.fish.center_x
                    current_y = detection.fish.center_y
                    now = time.time()

                    # Pozisyon geçmişine ekle (son 5 frame)
                    self._fish_pos_history.append((current_x, current_y, now))

                    # Hız hesapla (son 5 frame moving average)
                    speed = 0.0
                    vx, vy = 0.0, 0.0
                    if len(self._fish_pos_history) >= 2:
                        velocities = []
                        history_list = list(self._fish_pos_history)
                        for i in range(1, len(history_list)):
                            px, py, pt = history_list[i]
                            ppx, ppy, ppt = history_list[i - 1]
                            dt_i = pt - ppt
                            if 0 < dt_i < 0.2:
                                vx_i = (px - ppx) / dt_i
                                vy_i = (py - ppy) / dt_i
                                velocities.append((vx_i, vy_i))
                        if velocities:
                            vx = sum(v[0] for v in velocities) / len(velocities)
                            vy = sum(v[1] for v in velocities) / len(velocities)
                            speed = math.hypot(vx, vy)

                    # Hıza göre DİNAMİK safe_radius
                    base_radius = detection.circle.radius
                    if speed > 250:       # Efsanevi/ultra hızlı balık
                        safe_radius = base_radius * 0.65
                    elif speed > 150:     # Nadir/çok hızlı balık
                        safe_radius = base_radius * 0.72
                    elif speed > 80:      # Orta-hızlı balık
                        safe_radius = base_radius * 0.78
                    else:                 # Normal/yavaş balık
                        safe_radius = base_radius * 0.85

                    dist_to_center = math.hypot(
                        current_x - detection.circle.center_x,
                        current_y - detection.circle.center_y
                    )

                    if dist_to_center > safe_radius:
                        # Balık safe zone dışında → reaksiyon sıfırla
                        self._fish_was_inside = False
                        self._fish_entered_safe_at = 0.0
                        self._reaction_delay = 0.0
                        return False, status_msg

                    # ── İNSANSI REAKSİYON GECİKMESİ SİSTEMİ (ANTI-CHEAT) ──
                    # Balık safe zone'a İLK girdiğinde zamanı kaydet.
                    # Her tıklama için yeni bir reaksiyon süresi belirle.
                    if not self._fish_was_inside:
                        self._fish_was_inside = True
                        self._fish_entered_safe_at = now
                        self._reaction_delay = random.uniform(
                            self._clicker._human.reaction_min,
                            self._clicker._human.reaction_max
                        )

                    # Reaksiyon süresi dolmadıysa tıklama YAPMA
                    reaction_elapsed = now - self._fish_entered_safe_at
                    if reaction_elapsed < self._reaction_delay:
                        status_msg = (
                            f"MINIGAME: {self._click_count_in_minigame}/3 Tik "
                            f"(reaksiyon: {reaction_elapsed*1000:.0f}/{self._reaction_delay*1000:.0f}ms)"
                        )
                        return False, status_msg

                    # ── PREDICTION: TÜM BALIKLARA UYGULA (hız > eşik ise) ──
                    target_x = current_x
                    target_y = current_y

                    pred_threshold = self._clicker._human.prediction_speed_threshold
                    if speed > pred_threshold:
                        # Dinamik look_ahead: hıza göre ölçeklenir
                        # Hızlı balık = daha fazla lead (insan da öyle yapar)
                        speed_factor = min(1.0, speed / 300.0)  # 0-1 arası normalleştir
                        look_ahead = self._clicker._human.prediction_look_ahead_base + \
                                     speed_factor * (self._clicker._human.prediction_look_ahead_max -
                                                     self._clicker._human.prediction_look_ahead_base)

                        # Velocity bazlı pozisyon tahmini
                        target_x = int(current_x + vx * look_ahead)
                        target_y = int(current_y + vy * look_ahead)

                        # Ek lead: balık yönüne doğru ekstra offset
                        if speed > 0:
                            lead_px = min(
                                self._clicker._human.prediction_max_lead_px,
                                int(speed * look_ahead * 0.7)
                            )
                            target_x = int(target_x + (vx / speed) * lead_px)
                            target_y = int(target_y + (vy / speed) * lead_px)

                    # ── ÇEMBER SINIRI KORUMASI ──
                    # Prediction hedefi çember dışına taşıyabilir.
                    # Tıklama HER ZAMAN çemberin İÇİNDE kalmalı.
                    circle_cx = detection.circle.center_x
                    circle_cy = detection.circle.center_y
                    target_dist = math.hypot(target_x - circle_cx, target_y - circle_cy)

                    # Maksimum izin verilen mesafe: çember yarıçapının %90'ı
                    # (inner_margin 0.95 ile tutarlı, ama tıklama için biraz daha güvenli)
                    max_click_radius = int(detection.circle.radius * 0.90)

                    if target_dist > max_click_radius and target_dist > 0:
                        # Hedefi çember sınırına geri çek (yönde clamp)
                        scale = max_click_radius / target_dist
                        target_x = int(circle_cx + (target_x - circle_cx) * scale)
                        target_y = int(circle_cy + (target_y - circle_cy) * scale)

                    # ── TIKLAMA KARARI ──
                    if self._clicker.is_ready:
                        # ── Bilerek Iskalama (~%12 ihtimal) ──
                        if self._intentional_miss and self._click_count_in_minigame >= 2:
                            self._intentional_miss = False
                            self._clicker._last_click_time = time.time()
                            # Reaksiyonu sıfırla — yeni tık için yeniden bekle
                            self._fish_was_inside = False
                            self._fish_entered_safe_at = 0.0
                            self._reaction_delay = 0.0
                            return False, status_msg

                        # Tahmin edilen noktaya HIZLI tıkla (bezier'siz, insansı)
                        if self._clicker.fast_click_at(target_x, target_y):
                            clicked = True
                            self._click_count_in_minigame += 1

                            # ── Tıklama sonrası: reaksiyonu sıfırla ──
                            # Her tıklama yeni bir "görsel karar" gerektirir
                            self._fish_was_inside = False
                            self._fish_entered_safe_at = 0.0
                            self._reaction_delay = 0.0

                            # ── İnsansı Ritim: tıklamadan SONRA cooldown'u ayarla ──
                            if self._click_rhythm and self._click_rhythm_idx < len(self._click_rhythm):
                                self._clicker._human.click_cooldown = self._click_rhythm[self._click_rhythm_idx]
                                self._click_rhythm_idx += 1

        elif self.state == BotState.POST_CATCH:
            status_msg = f"Toparlaniyor... ({int(self._cfg.delay_after_catch - elapsed)}s)"
            
            if not getattr(self, "_postcatch_action_done", False):
                self._postcatch_action_done = True
                
                full_frame = None
                
                # Çöpleri Yere At
                if self._cfg.auto_drop_trash and self._capture is not None and detector is not None:
                    if full_frame is None:
                        full_frame = self._capture.grab_full_frame()
                        
                    trashes = detector.detect_inventory_items(full_frame, item_type="trash")
                    if trashes:
                        status_msg = f"Envanterdeki {len(trashes)} cop atiliyor..."
                        for tx, ty in trashes:
                            # Sürükle bırak (hedef x=50, y=50 oyunun köşesi veya dışı)
                            self._clicker.drag_and_drop(tx, ty, 50, 50)
                            # 'Yere at' onay diyalogu için Enter bas.
                            self._clicker.press_key('enter')
                            time.sleep(0.5)
                
                # Balıkları aç
                if self._cfg.auto_open_fishes and self._capture is not None and detector is not None:
                    if full_frame is None:
                        full_frame = self._capture.grab_full_frame()
                        
                    fishes = detector.detect_inventory_items(full_frame, item_type="fish")
                    if fishes:
                        status_msg = f"Envanterde {len(fishes)} balik aciliyor..."
                        for fx, fy in fishes:
                            self._clicker.right_click_at(fx, fy)
                            time.sleep(0.1)
            
            # Animasyon beklemesi
            if elapsed > self._cfg.delay_after_catch:
                # Yorulma (Fatigue) kontrolü
                if self._cfg.use_fatigue_system and time.time() > self._next_fatigue_time:
                    self._fatigue_duration = random.uniform(
                        self._cfg.fatigue_duration_min, 
                        self._cfg.fatigue_duration_max
                    )
                    self._transition_to(BotState.FATIGUE_BREAK)
                else:
                    # Başa dön
                    self._transition_to(BotState.PREPARE)
                    
        elif self.state == BotState.FATIGUE_BREAK:
            remaining = self._fatigue_duration - elapsed
            status_msg = f"Cay Molasi ☕ (Kalan: {int(remaining)}s)"
            
            if remaining <= 0:
                self._next_fatigue_time = time.time() + random.uniform(
                    self._cfg.fatigue_interval_min, 
                    self._cfg.fatigue_interval_max
                )
                self._transition_to(BotState.PREPARE)

        return clicked, status_msg

    def _transition_to(self, new_state: BotState) -> None:
        """Durum değiştirir ve zamanlayıcıyı sıfırlar."""
        self.state = new_state
        self._state_start_time = time.time()

        if new_state == BotState.MINIGAME:
            self._click_count_in_minigame = 0
            self._fish_clicked_this_pass = False
            self._fish_pos_history.clear()  # Yeni minigame → temiz pozisyon geçmişi
            self._circle_missing_count = 0  # Circle dalgalanma sayacı
            # Reaksiyon gecikmesi sıfırla
            self._reaction_delay = 0.0
            self._fish_entered_safe_at = 0.0
            self._fish_was_inside = False

            # ── Rastgele Tıklama Ritim Pattern'i ──
            # Her minigame'de farklı ritim (insansı çeşitlilik)
            base_cooldown = self._clicker._human.click_cooldown
            patterns = [
                [base_cooldown, base_cooldown * 1.1, base_cooldown * 0.9],       # Dengeli
                [base_cooldown * 0.85, base_cooldown * 0.9, base_cooldown * 1.2], # Hızlıdan yavaşa
                [base_cooldown * 1.15, base_cooldown * 0.85, base_cooldown * 0.9],# Yavaştan hızlıya
                [base_cooldown * 0.95, base_cooldown * 1.1, base_cooldown * 0.95],# Düzensiz
                [base_cooldown * 1.05, base_cooldown * 0.8, base_cooldown * 1.1], # Karışık
            ]
            self._click_rhythm = random.choice(patterns)
            self._click_rhythm_idx = 0

            # ── Bilerek Iskalama (her ~8 balıkta bir) ──
            self._catch_streak += 1
            self._intentional_miss = (self._catch_streak >= random.randint(7, 10))
            if self._intentional_miss:
                self._catch_streak = 0  # Sayaç sıfırla
        elif new_state == BotState.PREPARE:
            self._prepare_action_done = False
            self._armor_trick_done = False
            self._armor_trick_phase2 = False
        elif new_state == BotState.POST_CATCH:
            self._postcatch_action_done = False
        elif new_state == BotState.CAST:
            self._cast_done = False
            self._cast_pressed = False
        elif new_state == BotState.WAITING:
            self._consecutive_circle_count = 0
