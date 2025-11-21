import os
import time
import json
import logging
from typing import Optional, Dict, Any

# Import internal modules
from app.client.engsel import get_package_details
from app.service.auth import AuthInstance

# Setup Logger
logger = logging.getLogger(__name__)

class DecoyPackage:
    """
    Manajer paket pancingan (Decoy).
    Bertugas memuat konfigurasi decoy dari file JSON dan mengambil detailnya dari API XL.
    """
    _instance_ = None
    _initialized_ = False
    
    # Lokasi file JSON konfigurasi decoy
    DECOY_DIR = "decoy_data"
    
    # Tipe akun yang membutuhkan decoy khusus (Prio)
    PRIO_TYPES = ["PRIORITAS", "PRIOHYBRID", "GO"]
    
    # Durasi cache dalam detik (5 menit)
    CACHE_TTL = 300  
    
    def __new__(cls, *args, **kwargs):
        if not cls._instance_:
            cls._instance_ = super().__new__(cls)
        return cls._instance_
    
    def __init__(self):
        if not self._initialized_:
            self.current_sub_id = None
            self.file_prefix = "default-"
            
            # In-memory cache: { "default-balance": {"data": {...}, "ts": 123456} }
            self.cache = {} 
            
            # Pastikan direktori ada
            if not os.path.exists(self.DECOY_DIR):
                try:
                    os.makedirs(self.DECOY_DIR, exist_ok=True)
                except OSError:
                    pass # Ignore permission errors
                
            self._initialized_ = True

    def _refresh_context(self):
        """
        Mengecek apakah user berubah. Jika ya, sesuaikan prefix file (prio/default).
        """
        user = AuthInstance.get_active_user()
        if not user: 
            return

        sub_id = user.get("subscriber_id")
        sub_type = user.get("subscription_type", "")

        # Jika user berganti, reset prefix dan cache terkait
        if sub_id != self.current_sub_id:
            self.current_sub_id = sub_id
            
            new_prefix = "prio-" if sub_type in self.PRIO_TYPES else "default-"
            
            if new_prefix != self.file_prefix:
                self.file_prefix = new_prefix
                self.cache.clear() # Clear cache karena konteks berubah
                logger.info(f"Decoy context switched to: {self.file_prefix} ({sub_type})")

    def get_decoy(self, decoy_type: str) -> Optional[Dict[str, Any]]:
        """
        Mengambil data decoy siap pakai (Option Code, Price, Token).
        
        Args:
            decoy_type (str): 'balance', 'qris', atau 'qris0'
        """
        self._refresh_context()
        
        valid_types = ["balance", "qris", "qris0"]
        if decoy_type not in valid_types:
            logger.warning(f"Tipe decoy tidak dikenal: {decoy_type}")
            return None

        # Nama kunci cache/file: default-balance, prio-qris, dll.
        full_key = f"{self.file_prefix}{decoy_type}"
        
        # 1. Cek Cache Memory
        cached_item = self.cache.get(full_key)
        if cached_item:
            age = time.time() - cached_item["timestamp"]
            if age < self.CACHE_TTL:
                return cached_item["data"]
            else:
                logger.info(f"Cache decoy {full_key} expired. Refreshing...")
        
        # 2. Load Config dari JSON
        file_name = f"decoy-{full_key}.json"
        file_path = os.path.join(self.DECOY_DIR, file_name)
        
        if not os.path.exists(file_path):
            logger.error(f"File konfigurasi hilang: {file_path}")
            print(f"⚠️  File decoy '{file_name}' tidak ditemukan di folder '{self.DECOY_DIR}'.")
            return None

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception as e:
            logger.error(f"Gagal membaca file {file_name}: {e}")
            return None

        # 3. Fetch Detail dari API MyXL
        try:
            api_key = AuthInstance.api_key
            tokens = AuthInstance.get_active_tokens()
            
            if not tokens: 
                logger.warning("Tidak ada token aktif untuk fetch decoy.")
                return None

            # Validasi struktur JSON
            required_keys = ["family_code", "variant_code", "order"]
            if not all(k in config for k in required_keys):
                logger.error(f"Config decoy {full_key} tidak lengkap.")
                return None

            logger.info(f"Fetching decoy package details for {full_key}...")
            
            pkg_detail = get_package_details(
                api_key, 
                tokens,
                config["family_code"],
                config["variant_code"],
                config["order"],
                config.get("is_enterprise", False),
                config.get("migration_type", "NONE")
            )

            if not pkg_detail:
                logger.error(f"API mengembalikan kosong untuk decoy {full_key}.")
                return None

            # 4. Konstruksi Data Hasil
            pkg_opt = pkg_detail.get("package_option", {})
            
            result = {
                "option_code": pkg_opt.get("package_option_code", ""),
                "price": config.get("price", 0), # Harga override dari JSON (bukan API)
                "name": pkg_opt.get("name", "Unknown Decoy"),
                "token_confirmation": pkg_detail.get("token_confirmation", "")
            }
            
            if not result["option_code"]:
                logger.error("Option Code tidak ditemukan dalam respon API.")
                return None
            
            # 5. Simpan ke Cache
            self.cache[full_key] = {
                "timestamp": time.time(),
                "data": result
            }
            
            logger.info(f"Decoy {full_key} updated successfully.")
            return result

        except Exception as e:
            logger.error(f"Error processing decoy {full_key}: {e}")
            return None

# Singleton Instance
DecoyInstance = DecoyPackage()
