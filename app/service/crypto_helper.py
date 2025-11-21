import hashlib
import os
import hmac
import base64
import logging
from typing import Union

# Dependencies Kriptografi
from base64 import urlsafe_b64encode, urlsafe_b64decode
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

# Setup Logger
logger = logging.getLogger(__name__)

# Load Env dengan Fallback Empty String (Mencegah NoneType Error)
XDATA_KEY = os.getenv("XDATA_KEY", "")
AX_API_SIG_KEY = os.getenv("AX_API_SIG_KEY", "")
X_API_BASE_SECRET = os.getenv("X_API_BASE_SECRET", "")
ENCRYPTED_FIELD_KEY = os.getenv("ENCRYPTED_FIELD_KEY", "")

def derive_iv(xtime_ms: int) -> bytes:
    """
    Membuat IV dinamis berdasarkan timestamp server.
    """
    try:
        # Pastikan input valid
        sha = hashlib.sha256(str(xtime_ms).encode()).hexdigest()
        return sha[:16].encode()
    except Exception as e:
        logger.error(f"Error deriving IV: {e}")
        # Fallback IV (Sangat jarang terjadi, tapi mencegah crash)
        return b'0' * 16

def encrypt_xdata(plaintext: str, xtime_ms: int) -> str:
    """
    Enkripsi payload XDATA (AES-CBC-PKCS7).
    """
    try:
        if not plaintext:
            return ""
            
        if not XDATA_KEY:
            logger.error("XDATA_KEY is missing in .env")
            return ""

        iv = derive_iv(xtime_ms)
        key_bytes = XDATA_KEY.encode()
        
        cipher = AES.new(key_bytes, AES.MODE_CBC, iv)
        # Encode ke bytes, pad, encrypt, lalu encode base64 urlsafe
        encrypted_bytes = cipher.encrypt(pad(plaintext.encode('utf-8'), 16, style="pkcs7"))
        return urlsafe_b64encode(encrypted_bytes).decode('ascii')
    except Exception as e:
        logger.error(f"Encrypt XData Failed: {e}")
        return ""

def decrypt_xdata(xdata: str, xtime_ms: int) -> str:
    """
    Dekripsi payload XDATA dengan handling padding otomatis.
    """
    try:
        if not xdata:
            return "{}"
            
        if not XDATA_KEY:
            return "{}"

        iv = derive_iv(xtime_ms)
        key_bytes = XDATA_KEY.encode()
        
        # Fix Padding Base64 (Python strict soal padding)
        padding_needed = len(xdata) % 4
        if padding_needed:
            xdata += "=" * (4 - padding_needed)
            
        ct = urlsafe_b64decode(xdata)
        
        cipher = AES.new(key_bytes, AES.MODE_CBC, iv)
        pt = unpad(cipher.decrypt(ct), 16, style="pkcs7")
        return pt.decode('utf-8')
    except ValueError:
        # Sering terjadi jika key salah atau padding rusak
        logger.warning("Decrypt XData: Invalid Padding or Key mismatch.")
        return "{}"
    except Exception as e:
        logger.error(f"Decrypt XData Failed: {e}")
        return "{}"

# =============================================================================
# SIGNATURE GENERATORS (HMAC)
# =============================================================================

def _hmac_sha512(key_str: str, msg_str: str) -> str:
    """Internal helper untuk HMAC-SHA512 yang aman."""
    try:
        key_bytes = key_str.encode("utf-8")
        msg_bytes = msg_str.encode("utf-8")
        return hmac.new(key_bytes, msg_bytes, hashlib.sha512).hexdigest()
    except Exception as e:
        logger.error(f"HMAC Generation Failed: {e}")
        return ""

def make_x_signature(
    id_token: str,
    method: str,
    path: str,
    sig_time_sec: int
) -> str:
    """Signature untuk General Request"""
    key_str = f"{X_API_BASE_SECRET};{id_token};{method};{path};{sig_time_sec}"
    msg_str = f"{id_token};{sig_time_sec};"
    return _hmac_sha512(key_str, msg_str)

def make_x_signature_payment(
    access_token: str,
    sig_time_sec: int,
    package_code: str,
    token_payment: str,
    payment_method: str,
    payment_for: str,
    path: str,
) -> str:
    """Signature Khusus Pembayaran (Balance, Ewallet, dll)"""
    key_str = f"{X_API_BASE_SECRET};{sig_time_sec}#ae-hei_9Tee6he+Ik3Gais5=;POST;{path};{sig_time_sec}"
    msg_str = f"{access_token};{token_payment};{sig_time_sec};{payment_for};{payment_method};{package_code};"
    return _hmac_sha512(key_str, msg_str)

def make_ax_api_signature(
    ts_for_sign: str,
    contact: str,
    code: str,
    contact_type: str
) -> str:
    """Signature untuk Login/OTP (HMAC-SHA256)"""
    try:
        if not AX_API_SIG_KEY:
            logger.error("AX_API_SIG_KEY is missing")
            return ""

        key_bytes = AX_API_SIG_KEY.encode("ascii")
        preimage = f"{ts_for_sign}password{contact_type}{contact}{code}openid"
        
        digest = hmac.new(key_bytes, preimage.encode("utf-8"), hashlib.sha256).digest()
        return base64.b64encode(digest).decode("ascii")
    except Exception as e:
        logger.error(f"AX Signature Failed: {e}")
        return ""

def make_x_signature_bounty(
    access_token: str,
    sig_time_sec: int,
    package_code: str,
    token_payment: str,
) -> str:
    """Signature untuk Redeem Voucher"""
    path = "api/v8/personalization/bounties-exchange"
    key_str = f"{X_API_BASE_SECRET};{access_token};{sig_time_sec}#ae-hei_9Tee6he+Ik3Gais5=;POST;{path};{sig_time_sec}"
    msg_str = f"{access_token};{token_payment};{sig_time_sec};{package_code};"
    return _hmac_sha512(key_str, msg_str)

def make_x_signature_loyalty(
    sig_time_sec: int,
    package_code: str,
    token_confirmation: str,
    path: str,
) -> str:
    """Signature untuk Redeem Poin"""
    key_str = f"{X_API_BASE_SECRET};{sig_time_sec}#ae-hei_9Tee6he+Ik3Gais5=;POST;{path};{sig_time_sec}"
    msg_str = f"{token_confirmation};{sig_time_sec};{package_code};"
    return _hmac_sha512(key_str, msg_str)

def make_x_signature_bounty_allotment(
    sig_time_sec: int,
    package_code: str,
    token_confirmation: str,
    path: str,
    destination_msisdn: str,
) -> str:
    """Signature untuk Gift Bonus"""
    key_str = f"{X_API_BASE_SECRET};{sig_time_sec}#ae-hei_9Tee6he+Ik3Gais5=;{destination_msisdn};POST;{path};{sig_time_sec}"
    msg_str = f"{token_confirmation};{sig_time_sec};{destination_msisdn};{package_code};"
    return _hmac_sha512(key_str, msg_str)

def make_x_signature_basic(
    method: str,
    path: str,
    sig_time_sec: int,
) -> str:
    """Signature Basic (Jarang dipakai tapi perlu ada)"""
    key_str = f"{X_API_BASE_SECRET};{method};{path};{sig_time_sec}"
    msg_str = f"{sig_time_sec};en;"
    return _hmac_sha512(key_str, msg_str)

# =============================================================================
# FAMILY / CIRCLE ENCRYPTION
# =============================================================================

def encrypt_circle_msisdn(msisdn: str) -> str:
    """
    Enkripsi MSISDN untuk Family Plan.
    Menggunakan IV Hex yang ditempel di akhir string Base64.
    """
    try:
        if not ENCRYPTED_FIELD_KEY:
            return ""
            
        key = ENCRYPTED_FIELD_KEY.encode('ascii')
        # Generate random IV 8 bytes, convert to 16 hex chars
        iv_hex = os.urandom(8).hex() 
        iv = iv_hex.encode('ascii') # IV yang dipakai AES adalah 16 bytes (dari hex string)

        cipher = AES.new(key, AES.MODE_CBC, iv)
        ct = cipher.encrypt(pad(msisdn.encode('utf-8'), 16))
        
        ct_b64 = urlsafe_b64encode(ct).decode('ascii')
        return ct_b64 + iv_hex
    except Exception as e:
        logger.error(f"Encrypt Circle MSISDN Failed: {e}")
        return ""

def decrypt_circle_msisdn(encrypted_msisdn_b64: str) -> str:
    """
    Dekripsi MSISDN Family Plan.
    """
    try:
        if not encrypted_msisdn_b64 or len(encrypted_msisdn_b64) < 16:
            return ""
            
        if not ENCRYPTED_FIELD_KEY:
            return ""

        # Extract IV (16 karakter terakhir adalah Hex IV)
        iv_ascii = encrypted_msisdn_b64[-16:]
        b64_part = encrypted_msisdn_b64[:-16]
        
        key = ENCRYPTED_FIELD_KEY.encode('ascii')
        iv = iv_ascii.encode('ascii')
        
        # Fix padding
        padding = len(b64_part) % 4
        if padding:
            b64_part += '=' * (4 - padding)
            
        ct = urlsafe_b64decode(b64_part)
        
        cipher = AES.new(key, AES.MODE_CBC, iv)
        pt = unpad(cipher.decrypt(ct), 16, style='pkcs7')
        return pt.decode('utf-8')
    except Exception as e:
        logger.error(f"Decrypt Circle MSISDN Failed: {e}")
        return ""
