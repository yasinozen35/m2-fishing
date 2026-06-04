import os
import time
import threading
import pydirectinput


class TargetItemManager:
    def __init__(self, bot):
        self.bot = bot

    def handle(self, coords, image_path, fail_count=0):
        if getattr(self.bot, '_target_item_handling', False):
            return
        self.bot._target_item_handling = True
        thread = threading.Thread(target=self._process_item_pickup, args=(coords, image_path, fail_count))
        thread.daemon = True
        thread.start()

    def _is_monster_targeted(self):
        target_bar = self.bot.active_cv.get("target_bar_img", "")
        if target_bar and os.path.exists(target_bar):
            return self.bot.vision.find_image_on_screen(target_bar, threshold=0.7) is not None
        return False

    def _queue_retry(self, image_path, last_coords, fail_count, delay):
        """Başarısız/kesintiye uğrayan itemi kuyruğa ekle."""
        engine = self.bot.bot_engine
        # Aynı item zaten kuyrukta varsa güncelle, yoksa ekle
        for item in engine.pending_items:
            if item['image_path'] == image_path:
                item['last_coords'] = last_coords
                item['next_retry'] = time.time() + delay
                item['fail_count'] = fail_count
                return
        engine.pending_items.append({
            'image_path': image_path,
            'last_coords': last_coords,
            'next_retry': time.time() + delay,
            'fail_count': fail_count
        })

    def _process_item_pickup(self, coords, image_path, fail_count=0):
        mouse_held = False
        picked_up = False
        monster_interrupt = False
        last_coords = coords

        try:
            max_walk_duration = 10.0
            start_walk = time.time()
            last_monster_check = 0
            monster_check_grace = 2.0  # ilk 2 sn canavar kontrolü yapma, yürümeye başlasın

            while time.time() - start_walk < max_walk_duration:
                # İtemin güncel ekran konumunu tara
                fresh_coords = self._search_item_on_screen(image_path)
                if fresh_coords is None:
                    picked_up = True
                    break
                last_coords = fresh_coords

                # Mouse'u itemin güncel konumuna getir ve basılı tut
                pydirectinput.moveTo(fresh_coords[0], fresh_coords[1])
                if not mouse_held:
                    time.sleep(0.03)
                    pydirectinput.mouseDown()
                    mouse_held = True

                # Canavar kontrolü: ilk 2 sn atla, sonra 1 sn'de bir kontrol et
                elapsed = time.time() - start_walk
                if elapsed >= monster_check_grace and elapsed - last_monster_check >= 1.0:
                    last_monster_check = elapsed
                    if self._is_monster_targeted():
                        monster_interrupt = True
                        break

                time.sleep(0.05)

            if mouse_held:
                pydirectinput.mouseUp()
                mouse_held = False

            # Kuyruk yönetimi
            if not picked_up:
                if monster_interrupt:
                    # Canavar çıktı → 1.5 sn sonra tekrar dene (fail_count artmasın)
                    self._queue_retry(image_path, last_coords, fail_count, 1.5)
                else:
                    # Ulaşılamadı → escalating backoff
                    backoffs = [2.0, 4.0, 8.0, 16.0]
                    if fail_count < len(backoffs):
                        self._queue_retry(image_path, last_coords, fail_count + 1, backoffs[fail_count])
                    # fail_count >= len(backoffs): tamamen vazgeç

        finally:
            if mouse_held:
                try:
                    pydirectinput.mouseUp()
                except Exception:
                    pass
            self.bot._target_item_handling = False
            # Başarılı alımda normal tarama hemen devam etsin; başarısızda kuyruk halleder
            if picked_up:
                self.bot.target_item_pause_until = time.time() + 0.5

    def _search_item_on_screen(self, image_path):
        region_str = self.bot.active_cv.get("chat_region", "")
        if image_path and os.path.exists(image_path):
            coords = self.bot.vision.find_image_on_screen(image_path, threshold=0.70)
            if coords and not self.bot.vision.is_match_in_chat_region(coords, region_str):
                return coords
        return None
