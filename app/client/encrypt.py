import base64
import json
import logging
import os
import secrets
import time
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from random import randint
from typing import Optional, Dict, Any, Union # <-- Import Optional

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

# Import helper functions
from app.service.crypto_helper import (
    encrypt_xdata as helper_enc_xdata,
    decrypt_xdata as helper_dec_xdata,
    encrypt_circle_msisdn as helper_enc_msisdn,
    decrypt_circle_msisdn as helper_dec_msisdn,
    make_x_signature,
    make_x_signature_payment,
    make_ax_api_signature,
    make_x_signature_bounty,
    make_x_signature_loyalty,
    make_x_signature_bounty_allotment,
)

# Setup Logger
logger = logging.getLogger(__name__)

# =============================================================================
# GLOBAL VARIABLES (Environment & Constants)
# =============================================================================
API_KEY = os.getenv("API_KEY")
AES_KEY_ASCII = os.getenv("AES_KEY_ASCII")
AX_FP_KEY = os.getenv("AX_FP_KEY")
ENCRYPTED_FIELD_KEY = os.getenv("ENCRYPTED_FIELD_KEY")

@dataclass
class DeviceInfo:
    manufacturer: str
    model: str
    lang: str
    resolution: str
    tz_short: str
    ip: str
    font_scale: float
    android_release: str
    msisdn: str

@dataclass
class CryptoConfig:
    """Konfigurasi terpusat untuk enkripsi"""
    api_key: str = field(default_factory=lambda: API_KEY or "")
    aes_key_ascii: str = field(default_factory=lambda: AES_KEY_ASCII or "")
    ax_fp_key: str = field(default_factory=lambda: AX_FP_KEY or "")
    encrypted_field_key: str = field(default_factory=lambda: ENCRYPTED_FIELD_KEY or "")
    fp_file_path: Path = field(default_factory=lambda: Path("ax.fp"))

class EncryptionService:
    """
    Service modern untuk menangani semua operasi kriptografi.
    Menggunakan error handling yang robust (tahan banting).
    """
    
    def __init__(self, config: Optional[CryptoConfig] = None):
        self.config = config or CryptoConfig()

    def _get_gmt7_now(self) -> datetime:
        return datetime.now(timezone(timedelta(hours=7)))

    def build_fingerprint_plain(self, dev: DeviceInfo) -> str:
        return (
            f"{dev.manufacturer}|{dev.model}|{dev.lang}|{dev.resolution}|"
            f"{dev.tz_short}|{dev.ip}|{dev.font_scale}|Android {dev.android_release}|{dev.msisdn}"
        )

    def generate_ax_fingerprint(self, dev: DeviceInfo) -> str:
        try:
            if not self.config.ax_fp_key or len(self.config.ax_fp_key) != 32:
                logger.error("Invalid AX_FP_KEY length (must be 32 chars). Check .env file.")
                return ""

            key = self.config.ax_fp_key.encode("ascii")
            iv = b"\x00" * 16
            pt = self.build_fingerprint_plain(dev).encode("utf-8")
            
            cipher = AES.new(key, AES.MODE_CBC, iv)
            ct = cipher.encrypt(pad(pt, 16))
            
            return base64.b64encode(ct).decode("ascii")
        except Exception as e:
            logger.error(f"Fingerprint generation error: {e}")
            return ""

    def load_or_create_fingerprint(self) -> str:
        """
        Loads fingerprint from file, or generates a new one if missing/invalid.
        Ensures strict UTF-8 handling.
        """
        try:
            if self.config.fp_file_path.exists():
                content = self.config.fp_file_path.read_text(encoding="utf-8").strip()
                if content and len(content) > 10:
                    return content

            # Fallback / Generate New
            dev = DeviceInfo(
                manufacturer=f"Vertu{randint(1000, 9999)}",
                model=f"Asterion X1 Ultra{randint(1000, 9999)}",
                lang="en",
                resolution="720x1540",
                tz_short="GMT07:00",
                ip="127.0.0.1",
                font_scale=1.0,
                android_release="14",
                msisdn="6281911120078"
            )
            
            new_fp = self.generate_ax_fingerprint(dev)
            if new_fp:
                self.config.fp_file_path.write_text(new_fp, encoding="utf-8")
                return new_fp
            
            raise ValueError("Generated empty fingerprint")

        except Exception as e:
            logger.error(f"Fingerprint load/create error: {e}")
            # Return a safer fallback dummy to prevent app crash
            return "default_fingerprint_fallback_error"

    def get_ax_device_id(self) -> str:
        fp = self.load_or_create_fingerprint()
        return hashlib.md5(fp.encode("utf-8")).hexdigest()

    def build_encrypted_field(self, iv_hex16: Optional[str] = None, urlsafe_b64: bool = False) -> str:
        try:
            if not self.config.encrypted_field_key:
                logger.warning("ENCRYPTED_FIELD_KEY is missing")
                return ""
                
            key = self.config.encrypted_field_key.encode("ascii")
            iv_hex = iv_hex16 or secrets.token_hex(8)  # 8 bytes = 16 hex chars
            
            if len(iv_hex) != 16:
                raise ValueError("IV must be 16 hex characters")
                
            iv = iv_hex.encode("ascii")
            pt = pad(b"", AES.block_size) # Encrypting empty padded block? As per original logic.
            
            cipher = AES.new(key, AES.MODE_CBC, iv=iv)
            ct = cipher.encrypt(pt)
            
            encoder = base64.urlsafe_b64encode if urlsafe_b64 else base64.b64encode
            encoded_ct = encoder(ct).decode("ascii")
            
            return encoded_ct + iv_hex
        except Exception as e:
            logger.error(f"Build encrypted field error: {e}")
            return ""

    def java_like_timestamp(self, now: datetime) -> str:
        try:
            ms2 = f"{int(now.microsecond/10000):02d}" 
            tz = now.strftime("%z")
            tz_colon = f"{tz[:-2]}:{tz[-2:]}" if tz else "+00:00"
            return now.strftime(f"%Y-%m-%dT%H:%M:%S.{ms2}") + tz_colon
        except Exception:
            return now.isoformat()

    def ts_gmt7_without_colon(self, dt: datetime) -> str:
        try:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone(timedelta(hours=7)))
            else:
                dt = dt.astimezone(timezone(timedelta(hours=7)))
            
            millis = f"{int(dt.microsecond / 1000):03d}"
            tz = dt.strftime("%z")
            return dt.strftime(f"%Y-%m-%dT%H:%M:%S.{millis}") + tz
        except Exception:
            return ""

    def encrypt_and_sign_xdata(self, method: str, path: str, id_token: str, payload: Dict) -> Dict:
        try:
            plain_body = json.dumps(payload, separators=(",", ":"))
            xtime = int(time.time() * 1000)
            
            xdata = helper_enc_xdata(plain_body, xtime)
            if not xdata:
                raise ValueError("Encryption failed from helper (empty result)")

            sig_time_sec = xtime // 1000
            x_sig = make_x_signature(id_token, method, path, sig_time_sec)
            
            if not x_sig:
                raise ValueError("Signature generation failed")

            return {
                "x_signature": x_sig,
                "encrypted_body": {"xdata": xdata, "xtime": xtime}
            }
        except Exception as e:
            logger.error(f"EncryptSign XData error: {e}")
            return {}

    def decrypt_xdata_payload(self, encrypted_payload: Dict) -> Dict:
        try:
            if not isinstance(encrypted_payload, dict):
                raise ValueError(f"Invalid payload type: {type(encrypted_payload)}")

            xdata = encrypted_payload.get("xdata")
            xtime = encrypted_payload.get("xtime")
            
            if not xdata or not xtime:
                raise ValueError("Missing xdata or xtime in payload")

            plaintext = helper_dec_xdata(xdata, int(xtime))
            return json.loads(plaintext)
        except Exception as e:
            logger.error(f"Decrypt XData error: {e}")
            # Kembalikan dict kosong daripada crash, caller harus handle.
            return {}


# =============================================================================
# COMPATIBILITY LAYER
# Menjaga kompatibilitas penuh dengan kode legacy (tanpa mengubah argumen).
# =============================================================================

_service = EncryptionService()

def load_ax_fp() -> str:
    return _service.load_or_create_fingerprint()

def ax_device_id() -> str:
    return _service.get_ax_device_id()

def ax_fingerprint(dev: DeviceInfo, secret_key: str) -> str:
    # `secret_key` diabaikan, menggunakan kunci dari config internal
    return _service.generate_ax_fingerprint(dev)

def build_encrypted_field(iv_hex16: Optional[str] = None, urlsafe_b64: bool = False) -> str: # PENTING: Perubahan di sini!
    return _service.build_encrypted_field(iv_hex16, urlsafe_b64)

def java_like_timestamp(now: datetime) -> str:
    return _service.java_like_timestamp(now)

def ts_gmt7_without_colon(dt: datetime) -> str:
    return _service.ts_gmt7_without_colon(dt)

def ax_api_signature(api_key: str, ts_for_sign: str, contact: str, code: str, contact_type: str) -> str:
    # `api_key` diabaikan, fungsi sebenarnya menggunakan konstanta dari env
    return make_ax_api_signature(ts_for_sign, contact, code, contact_type)

def encryptsign_xdata(api_key: str, method: str, path: str, id_token: str, payload: dict) -> dict:
    # `api_key` diabaikan
    return _service.encrypt_and_sign_xdata(method, path, id_token, payload)

def decrypt_xdata(api_key: str, encrypted_payload: dict) -> dict:
    # `api_key` diabaikan
    return _service.decrypt_xdata_payload(encrypted_payload)

# FIX CRITICAL: Kembalikan perilaku original (abaikan api_key di argumen helper)
def encrypt_circle_msisdn(api_key: str, msisdn: str) -> str:
    # `api_key` diabaikan, fungsi helper menggunakan ENCRYPTED_FIELD_KEY dari env
    return helper_enc_msisdn(msisdn) 

# FIX CRITICAL: Kembalikan perilaku original (abaikan api_key di argumen helper)
def decrypt_circle_msisdn(api_key: str, encrypted_msisdn_b64: str) -> str:
    # `api_key` diabaikan, fungsi helper menggunakan ENCRYPTED_FIELD_KEY dari env
    return helper_dec_msisdn(encrypted_msisdn_b64)

# --- Signature Wrappers ---

def get_x_signature_payment(
    api_key: str,
    access_token: str,
    sig_time_sec: int,
    package_code: str,
    token_payment: str,
    payment_method: str,
    payment_for: str,
    path: str,
) -> str:
    # `api_key` diabaikan
    return make_x_signature_payment(
        access_token, sig_time_sec, package_code, token_payment, payment_method, payment_for, path
    )

def get_x_signature_bounty(
    api_key: str,
    access_token: str,
    sig_time_sec: int,
    package_code: str,
    token_payment: str
) -> str:
    # `api_key` diabaikan
    return make_x_signature_bounty(
        access_token, sig_time_sec, package_code, token_payment
    )

def get_x_signature_loyalty(
    api_key: str,
    sig_time_sec: int,
    package_code: str,
    token_confirmation: str,
    path: str
) -> str:
    # `api_key` diabaikan
    return make_x_signature_loyalty(
        sig_time_sec, package_code, token_confirmation, path
    )

def get_x_signature_bounty_allotment(
    api_key: str,
    sig_time_sec: int,
    package_code: str,
    token_confirmation: str,
    destination_msisdn: str,
    path: str
) -> str:
    # `api_key` diabaikan
    return make_x_signature_bounty_allotment(
        sig_time_sec, package_code, token_confirmation, path, destination_msisdn
    )
