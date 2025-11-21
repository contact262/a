import os
import json
import time
import logging
from app.client.ciam import get_new_token
from app.client.engsel import get_profile
from app.util import ensure_api_key

logger = logging.getLogger(__name__)

class Auth:
    _instance_ = None
    _initialized_ = False

    def __new__(cls, *args, **kwargs):
        if not cls._instance_:
            cls._instance_ = super().__new__(cls)
        return cls._instance_
    
    def __init__(self):
        if not self._initialized_:
            self.api_key = ensure_api_key()
            self.refresh_tokens = []
            self.active_user = None
            self.last_refresh_time = 0
            self.token_file = "refresh-tokens.json"
            self.active_user_file = "active.number"

            # Initial Load
            self.load_tokens()
            self.load_active_number()
            
            self._initialized_ = True
            
    def load_tokens(self):
        """Memuat database token dengan proteksi file corrupt."""
        if not os.path.exists(self.token_file):
            self._init_empty_file()
            return

        try:
            with open(self.token_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            if isinstance(data, list):
                # Filter data sampah
                self.refresh_tokens = [
                    t for t in data 
                    if isinstance(t, dict) and "number" in t and "refresh_token" in t
                ]
            else:
                logger.warning("Format file token salah, mereset...")
                self.refresh_tokens = []
        except json.JSONDecodeError:
            logger.error("File token rusak (JSON Error). Mereset database token.")
            self.refresh_tokens = []
        except Exception as e:
            logger.error(f"Gagal memuat token: {e}")
            self.refresh_tokens = []

    def _init_empty_file(self):
        try:
            with open(self.token_file, "w", encoding="utf-8") as f:
                json.dump([], f)
            self.refresh_tokens = []
        except Exception as e:
            logger.error(f"Gagal inisialisasi file token: {e}")

    def add_refresh_token(self, number: int, refresh_token: str):
        """Menambah atau update token user."""
        if not number or not refresh_token:
            return False

        try:
            # Cek apakah user sudah ada
            existing = next((rt for rt in self.refresh_tokens if rt["number"] == number), None)
            
            # Ambil info profile untuk melengkapi data
            # Kita generate token baru sebentar untuk ambil profile
            temp_tokens = get_new_token(self.api_key, refresh_token, "")
            if not temp_tokens:
                logger.error("Token awal tidak valid/expired.")
                return False

            profile_data = get_profile(self.api_key, temp_tokens["access_token"], temp_tokens["id_token"])
            if not profile_data:
                logger.error("Gagal mengambil profil user.")
                return False

            prof = profile_data.get("profile", {})
            sub_id = prof.get("subscriber_id", "")
            sub_type = prof.get("subscription_type", "PREPAID")

            new_entry = {
                "number": int(number),
                "subscriber_id": sub_id,
                "subscription_type": sub_type,
                "refresh_token": temp_tokens.get("refresh_token", refresh_token) # Simpan RT terbaru
            }

            if existing:
                existing.update(new_entry)
            else:
                self.refresh_tokens.append(new_entry)
            
            self.write_tokens_to_file()
            self.set_active_user(number)
            return True
            
        except Exception as e:
            logger.error(f"Error adding token: {e}")
            return False
            
    def remove_refresh_token(self, number: int):
        """Menghapus user dari database."""
        initial_len = len(self.refresh_tokens)
        self.refresh_tokens = [rt for rt in self.refresh_tokens if rt["number"] != number]
        
        if len(self.refresh_tokens) < initial_len:
            self.write_tokens_to_file()
            
            # Jika user yg dihapus adalah user aktif
            if self.active_user and self.active_user["number"] == number:
                self.active_user = None
                if self.refresh_tokens:
                    self.set_active_user(self.refresh_tokens[0]["number"])
                else:
                    self._clear_active_file()
            return True
        return False

    def set_active_user(self, number: int):
        """Mengganti user aktif dan melakukan refresh token instan."""
        target = next((rt for rt in self.refresh_tokens if rt["number"] == number), None)
        if not target:
            logger.error(f"User {number} tidak ditemukan di database.")
            return False

        try:
            # Refresh token saat switch user agar sesi segar
            tokens = get_new_token(self.api_key, target["refresh_token"], target.get("subscriber_id", ""))
            if not tokens:
                logger.error("Gagal refresh token saat switch user.")
                return False

            # Update data di memory dan file
            target["refresh_token"] = tokens["refresh_token"]
            self.write_tokens_to_file()

            self.active_user = {
                "number": int(number),
                "subscriber_id": target["subscriber_id"],
                "subscription_type": target["subscription_type"],
                "tokens": tokens
            }
            
            self.last_refresh_time = int(time.time())
            self._write_active_file(number)
            return True
        except Exception as e:
            logger.error(f"Gagal set active user: {e}")
            return False

    def get_active_user(self):
        """Mengambil user aktif dengan auto-refresh jika token kedaluwarsa (> 4 menit)."""
        if not self.active_user:
            # Coba restore dari file jika memory kosong
            self.load_active_number()
            if not self.active_user and self.refresh_tokens:
                # Fallback ke user pertama
                self.set_active_user(self.refresh_tokens[0]["number"])
            
            if not self.active_user: return None
        
        # Cek umur token (refresh setiap 4 menit / 240 detik untuk aman)
        if (int(time.time()) - self.last_refresh_time) > 240:
            logger.info("Token kedaluwarsa, memperbarui...")
            if not self._renew_active_token():
                logger.warning("Gagal memperbarui token otomatis.")
        
        return self.active_user

    def get_active_tokens(self):
        u = self.get_active_user()
        return u["tokens"] if u else None

    def _renew_active_token(self):
        if not self.active_user: return False
        try:
            rt = self.active_user["tokens"]["refresh_token"]
            sub_id = self.active_user["subscriber_id"]
            
            tokens = get_new_token(self.api_key, rt, sub_id)
            if tokens:
                self.active_user["tokens"] = tokens
                self.last_refresh_time = int(time.time())
                
                # Update RT di list utama juga
                for u in self.refresh_tokens:
                    if u["number"] == self.active_user["number"]:
                        u["refresh_token"] = tokens["refresh_token"]
                        break
                
                self.write_tokens_to_file()
                return True
            return False
        except Exception as e:
            logger.error(f"Renew token error: {e}")
            return False

    def write_tokens_to_file(self):
        try:
            with open(self.token_file, "w", encoding="utf-8") as f:
                json.dump(self.refresh_tokens, f, indent=4)
        except Exception as e:
            logger.error(f"Gagal menulis file token: {e}")

    def _write_active_file(self, number):
        try:
            with open(self.active_user_file, "w") as f:
                f.write(str(number))
        except: pass

    def _clear_active_file(self):
        if os.path.exists(self.active_user_file):
            os.remove(self.active_user_file)

    def load_active_number(self):
        if os.path.exists(self.active_user_file):
            try:
                with open(self.active_user_file, "r") as f:
                    num = int(f.read().strip())
                    # Jangan panggil set_active_user disini untuk menghindari rekursi loop saat init
                    # Cukup cari di list local
                    target = next((rt for rt in self.refresh_tokens if rt["number"] == num), None)
                    if target:
                        # Kita set active user nanti saat get_active_user dipanggil pertama kali
                        # atau panggil set_active_user tapi tanpa refresh jika baru init (opsional)
                        # Disini kita biarkan lazy load di get_active_user
                        pass
            except: pass

AuthInstance = Auth()
