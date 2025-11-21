import json
import logging
import os
import threading
from pathlib import Path
from typing import List, Dict, Any, Optional

# Setup Logger
logger = logging.getLogger(__name__)

class Bookmark:
    """
    Manajer Bookmark yang Stabil, Modern, dan Thread-Safe.
    Menggunakan Atomic Writes untuk mencegah korupsi data.
    """
    _instance = None
    _initialized = False
    _lock = threading.RLock()

    def __new__(cls):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(Bookmark, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            with self._lock:
                if not self._initialized:
                    self.file_path = Path("bookmark.json")
                    self.packages: List[Dict[str, Any]] = []
                    
                    # Load data saat inisialisasi
                    self._load()
                    self._initialized = True

    def _load(self):
        """
        Memuat bookmark dari file dengan Error Handling yang kuat.
        Jika file corrupt, otomatis backup dan reset.
        """
        if not self.file_path.exists():
            self._save()
            return

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            if isinstance(data, list):
                self.packages = data
                self._ensure_schema()
            else:
                logger.warning("Format bookmark salah (bukan list). Resetting.")
                self.packages = []
                
        except json.JSONDecodeError:
            logger.error("File bookmark.json rusak (Corrupt). Membuat backup dan reset.")
            try:
                backup_path = self.file_path.with_suffix(".bak")
                self.file_path.rename(backup_path)
            except OSError:
                pass
            self.packages = []
            self._save()
        except Exception as e:
            logger.error(f"Gagal memuat bookmark: {e}")
            self.packages = []

    def _save(self):
        """
        Menyimpan bookmark menggunakan Atomic Write (Tulis ke temp -> Rename).
        Ini mencegah file kosong/rusak jika proses dimatikan paksa saat menulis.
        """
        tmp_path = self.file_path.with_suffix(".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.packages, f, indent=2, ensure_ascii=False)
            
            # Atomic replace (Windows/Linux compatible di Python 3.8+)
            tmp_path.replace(self.file_path)
            
        except Exception as e:
            logger.error(f"Gagal menyimpan bookmark: {e}")
            if tmp_path.exists():
                try:
                    os.remove(tmp_path)
                except: pass

    def _ensure_schema(self):
        """
        Migrasi skema otomatis: Memastikan semua field wajib ada.
        """
        updated = False
        required_fields = {
            "family_code": "",
            "family_name": "Unknown Family",
            "is_enterprise": False,
            "variant_name": "Unknown Variant",
            "option_name": "Unknown Option",
            "order": 0
        }

        for p in self.packages:
            for key, default_val in required_fields.items():
                if key not in p:
                    p[key] = default_val
                    updated = True
        
        if updated:
            logger.info("Schema bookmark diperbarui.")
            self._save()

    def add_bookmark(
        self,
        family_code: str,
        family_name: str,
        is_enterprise: bool,
        variant_name: str,
        option_name: str,
        order: int,
    ) -> bool:
        """
        Menambah bookmark baru (Cegah duplikat).
        """
        with self._lock:
            # Cek duplikat berdasarkan kombinasi unik
            for p in self.packages:
                if (p.get("family_code") == family_code and 
                    p.get("variant_name") == variant_name and 
                    p.get("order") == order):
                    logger.info("Bookmark sudah ada.")
                    return False

            new_item = {
                "family_code": family_code,
                "family_name": family_name,
                "is_enterprise": is_enterprise,
                "variant_name": variant_name,
                "option_name": option_name,
                "order": order,
                "created_at": int(os.times()[4]) # Timestamp sederhana
            }
            
            self.packages.append(new_item)
            self._save()
            logger.info(f"Bookmark ditambahkan: {variant_name}")
            return True

    def remove_bookmark(
        self,
        family_code: str,
        is_enterprise: bool,
        variant_name: str,
        order: int,
    ) -> bool:
        """
        Menghapus bookmark.
        """
        with self._lock:
            initial_len = len(self.packages)
            self.packages = [
                p for p in self.packages
                if not (
                    p.get("family_code") == family_code and
                    p.get("is_enterprise") == is_enterprise and
                    p.get("variant_name") == variant_name and
                    p.get("order") == order
                )
            ]
            
            if len(self.packages) < initial_len:
                self._save()
                logger.info("Bookmark dihapus.")
                return True
            
            return False

    def get_bookmarks(self) -> List[Dict[str, Any]]:
        """Mengembalikan salinan list bookmark."""
        with self._lock:
            return self.packages.copy()

# Singleton Instance
BookmarkInstance = Bookmark()
