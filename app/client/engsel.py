import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Union
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Pastikan path import ini sesuai dengan project Anda
from app.client.encrypt import (
    encryptsign_xdata,
    java_like_timestamp,
    decrypt_xdata,
    API_KEY, 
)

# Setup Logger
logger = logging.getLogger(__name__)

# =============================================================================
# GLOBAL VARIABLES (Legacy Compatibility)
# Dipertahankan agar script lain yang import variable ini tidak error
# =============================================================================
BASE_API_URL = os.getenv("BASE_API_URL")
UA = os.getenv("UA")

@dataclass
class EngselConfig:
    """Konfigurasi terpusat untuk Client Engsel"""
    base_url: str = field(default_factory=lambda: BASE_API_URL or os.getenv("BASE_API_URL", "https://api.xl.co.id"))
    api_key: str = field(default_factory=lambda: API_KEY or os.getenv("API_KEY", ""))
    user_agent: str = field(default_factory=lambda: UA or os.getenv("UA", "Mozilla/5.0"))
    timeout: int = 30
    app_version: str = "8.9.1"  # Centralized versioning

    def __post_init__(self):
        # Fallback safety jika env var ada tapi string kosong
        if not self.base_url:
            self.base_url = "https://api.xl.co.id" 

class EngselClient:
    """
    Client utama untuk interaksi dengan XL API (Engsel).
    Menggunakan Session persistence dan Automatic Retry.
    """
    
    def __init__(self, config: Optional[EngselConfig] = None):
        self.config = config or EngselConfig()
        self._session = self._init_session()

    def _init_session(self) -> requests.Session:
        session = requests.Session()
        # Retry logic: 3x percobaan ulang untuk status code 5xx (Server Error)
        retries = Retry(
            total=3, 
            backoff_factor=0.5, 
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["POST", "GET"]
        )
        session.mount('https://', HTTPAdapter(max_retries=retries))
        return session

    def _get_clean_host(self) -> str:
        """Ekstrak hostname bersih dari URL untuk header Host"""
        try:
            parsed = urlparse(self.config.base_url)
            return parsed.netloc or self.config.base_url.replace("https://", "").replace("http://", "").split("/")[0]
        except Exception:
            return "api.xl.co.id"

    def _send_request(
        self,
        path: str,
        payload: Dict[str, Any],
        id_token: str,
        method: str = "POST"
    ) -> Optional[Dict[str, Any]]:
        """
        Core function untuk mengirim request:
        1. Encrypt Payload
        2. Kirim Request (Retry handled by Session)
        3. Decrypt Response
        4. Handle Error (JSONDecode, Network)
        """
        # Safety Check
        if not self.config.api_key:
            logger.error("API Key is missing.")
            return {"status": "ERROR", "message": "Missing API Key"}
        
        # 1. Encryption
        try:
            encrypted_data = encryptsign_xdata(
                api_key=self.config.api_key,
                method=method,
                path=path,
                id_token=id_token,
                payload=payload
            )
            
            if not encrypted_data:
                raise ValueError("Encryption returned empty data")

        except Exception as e:
            logger.error(f"Encryption failed for {path}: {e}")
            return {"status": "ERROR", "message": f"Encryption failed: {str(e)}"}

        # Prepare Headers
        xtime = int(encrypted_data["encrypted_body"]["xtime"])
        sig_time_sec = str(xtime // 1000)
        now = datetime.now(timezone.utc).astimezone()
        
        headers = {
            "host": self._get_clean_host(),
            "content-type": "application/json; charset=utf-8",
            "user-agent": self.config.user_agent,
            "x-api-key": self.config.api_key,
            "authorization": f"Bearer {id_token}",
            "x-hv": "v3",
            "x-signature-time": sig_time_sec,
            "x-signature": encrypted_data["x_signature"],
            "x-request-id": str(uuid.uuid4()),
            "x-request-at": java_like_timestamp(now),
            "x-version-app": self.config.app_version,
        }

        url = f"{self.config.base_url}/{path}"
        body = encrypted_data["encrypted_body"]

        # 2. Network Request
        try:
            if method.upper() == "POST":
                resp = self._session.post(url, headers=headers, json=body, timeout=self.config.timeout)
            else:
                resp = self._session.get(url, headers=headers, timeout=self.config.timeout)

            # Raise error untuk 4xx/5xx agar masuk ke block except
            resp.raise_for_status()

            # 3. Decryption
            try:
                response_json = resp.json()
                
                # Coba decrypt
                decrypted = decrypt_xdata(self.config.api_key, response_json)
                return decrypted if decrypted else response_json

            except json.JSONDecodeError:
                # Terjadi jika server return HTML (misal: 502 Bad Gateway Nginx page)
                logger.error(f"Invalid JSON response from {path}")
                return {"status": "ERROR", "message": "Invalid JSON response", "raw": resp.text[:100]}
            except Exception as e:
                # Decryption error fallback
                logger.warning(f"Decryption warning on {path}: {e}")
                return response_json

        except requests.exceptions.Timeout:
            logger.error(f"Timeout connecting to {path}")
            return {"status": "ERROR", "message": "Request Timed Out"}
        except requests.RequestException as e:
            logger.error(f"Network Error [{path}]: {e}")
            return {"status": "ERROR", "message": f"Network error: {str(e)}"}
        except Exception as e:
            logger.error(f"Unexpected Error [{path}]: {e}")
            return {"status": "ERROR", "message": f"System error: {str(e)}"}

    # =========================================================================
    # BUSINESS LOGIC METHODS
    # =========================================================================

    def get_balance(self, id_token: str) -> Optional[Any]:
        logger.info("Fetching balance...")
        res = self._send_request(
            "api/v8/packages/balance-and-credit",
            {"is_enterprise": False, "lang": "en"},
            id_token
        )
        return res.get("data", {}).get("balance") if res else None

    def get_family(
        self, 
        tokens: Dict, 
        family_code: str, 
        is_enterprise: Optional[bool] = None, 
        migration_type: Optional[str] = None
    ) -> Optional[Dict]:
        if not family_code: return None
        id_token = tokens.get("id_token")
        if not id_token: return None

        ent_opts = [is_enterprise] if is_enterprise is not None else [False, True]
        mig_opts = [migration_type] if migration_type is not None else ["NONE", "PRE_TO_PRIOH", "PRIOH_TO_PRIO", "PRIO_TO_PRIOH"]

        for mt in mig_opts:
            for ie in ent_opts:
                payload = {
                    "is_show_tagging_tab": True, "is_dedicated_event": True,
                    "is_transaction_routine": False, "migration_type": mt,
                    "package_family_code": family_code, "is_autobuy": False,
                    "is_enterprise": ie, "is_pdlp": True, "referral_code": "",
                    "is_migration": False, "lang": "en"
                }
                
                res = self._send_request("api/v8/xl-stores/options/list", payload, id_token)
                
                if res and res.get("status") == "SUCCESS" and "data" in res:
                    pf = res["data"].get("package_family", {})
                    if pf.get("name"):
                        logger.info(f"Family found: {pf['name']} (Ent:{ie}, Mig:{mt})")
                        return res["data"]
        return None

    def get_package_detail(self, tokens: Dict, option_code: str, family_code: str = "", variant_code: str = "") -> Optional[Dict]:
        if not option_code: return None
        payload = {
            "is_transaction_routine": False, "migration_type": "NONE",
            "package_family_code": family_code, "family_role_hub": "",
            "is_autobuy": False, "is_enterprise": False, "is_shareable": False,
            "is_migration": False, "lang": "en", "package_option_code": option_code,
            "is_upsell_pdp": False, "package_variant_code": variant_code
        }
        res = self._send_request("api/v8/xl-stores/options/detail", payload, tokens["id_token"])
        return res.get("data") if res else None

    def get_addons(self, tokens: Dict, option_code: str) -> Dict:
        if not option_code: return {}
        payload = {"is_enterprise": False, "lang": "en", "package_option_code": option_code}
        res = self._send_request("api/v8/xl-stores/options/addons-pinky-box", payload, tokens["id_token"])
        return res.get("data", {}) if res else {}

    def intercept_page(self, tokens: Dict, option_code: str, is_enterprise: bool = False) -> Dict:
        payload = {"is_enterprise": is_enterprise, "lang": "en", "package_option_code": option_code}
        return self._send_request("misc/api/v8/utility/intercept-page", payload, tokens["id_token"]) or {}

    def login_info(self, tokens: Dict, is_enterprise: bool = False) -> Optional[Dict]:
        payload = {"access_token": tokens["access_token"], "is_enterprise": is_enterprise, "lang": "en"}
        res = self._send_request("api/v8/auth/login", payload, tokens["id_token"])
        return res.get("data") if res else None

    def get_package_by_order(self, tokens: Dict, family_code: str, variant_code: str, order: int) -> Optional[Dict]:
        family_data = self.get_family(tokens, family_code)
        if not family_data: return None

        option_code = None
        for variant in family_data.get("package_variants", []):
            if variant.get("package_variant_code") == variant_code:
                for option in variant.get("package_options", []):
                    if option.get("order") == order:
                        option_code = option.get("package_option_code")
                        break
                break
        
        if option_code:
            return self.get_package_detail(tokens, option_code, family_code, variant_code)
        return None

    def get_notifications(self, tokens: Dict) -> Optional[Dict]:
        return self._send_request("api/v8/notification-non-grouping", {"is_enterprise": False, "lang": "en"}, tokens["id_token"])

    def get_notification_detail(self, tokens: Dict, notif_id: str) -> Optional[Dict]:
        return self._send_request("api/v8/notification/detail", {"is_enterprise": False, "lang": "en", "notification_id": notif_id}, tokens["id_token"])

    def get_pending_transaction(self, tokens: Dict) -> Dict:
        res = self._send_request("api/v8/profile", {"is_enterprise": False, "lang": "en"}, tokens["id_token"])
        return res.get("data", {}) if res else {}

    def get_transaction_history(self, tokens: Dict) -> Dict:
        res = self._send_request("payments/api/v8/transaction-history", {"is_enterprise": False, "lang": "en"}, tokens["id_token"])
        return res.get("data", {"list": []}) if res else {"list": []}

    def get_tiering_info(self, tokens: Dict) -> Dict:
        res = self._send_request("gamification/api/v8/loyalties/tiering/info", {"is_enterprise": False, "lang": "en"}, tokens["id_token"])
        return res.get("data", {}) if res else {}

    def unsubscribe(self, tokens: Dict, quota_code: str, domain: str, subtype: str) -> bool:
        payload = {
            "product_subscription_type": subtype, "quota_code": quota_code,
            "product_domain": domain, "is_enterprise": False,
            "unsubscribe_reason_code": "", "lang": "en", "family_member_id": ""
        }
        res = self._send_request("api/v8/packages/unsubscribe", payload, tokens["id_token"])
        return res is not None and res.get("code") == "000"

    def dashboard_segments(self, tokens: Dict) -> Dict:
        return self._send_request("dashboard/api/v8/segments", {"access_token": tokens["access_token"]}, tokens["id_token"]) or {}

    def get_profile(self, access_token: str, id_token: str) -> Dict:
        payload = {"access_token": access_token, "app_version": self.config.app_version, "is_enterprise": False, "lang": "en"}
        res = self._send_request("api/v8/profile", payload, id_token)
        return res.get("data", {}) if res else {}

    def get_families_by_category(self, tokens: Dict, category_code: str) -> Optional[Dict]:
        payload = {
            "migration_type": "", "is_enterprise": False, "is_shareable": False,
            "package_category_code": category_code, "with_icon_url": True,
            "is_migration": False, "lang": "en"
        }
        res = self._send_request("api/v8/xl-stores/families", payload, tokens["id_token"])
        return res.get("data") if res and res.get("status") == "SUCCESS" else None

    def validate_puk(self, tokens: Dict, msisdn: str, puk: str) -> Dict:
        payload = {"is_enterprise": False, "puk": puk, "is_enc": False, "msisdn": msisdn, "lang": "en"}
        return self._send_request("api/v8/infos/validate-puk", payload, tokens["id_token"]) or {}

    def get_quota_details(self, tokens: Dict) -> Dict:
        res = self._send_request("api/v8/packages/quota-details", {"is_enterprise": False, "lang": "en", "family_member_id": ""}, tokens["id_token"])
        return res.get("data", {"quotas": []}) if res else {"quotas": []}


# =============================================================================
# COMPATIBILITY LAYER (Backward Compatibility)
# Wrapper functions agar script lama (legacy) tidak perlu diubah pemanggilannya.
# * Mengganti 'type union operator' (|) menjadi 'Optional[...]'
# =============================================================================

# Singleton instance untuk legacy calls
_client = EngselClient()

def _ensure_api_key(api_key: str):
    """Helper untuk update API Key di singleton instance jika berbeda"""
    if api_key and api_key != _client.config.api_key:
        _client.config.api_key = api_key

def send_api_request(api_key: str, path: str, payload_dict: dict, id_token: str, method: str = "POST", timeout: int = 30):
    _ensure_api_key(api_key)
    return _client._send_request(path, payload_dict, id_token, method)

def get_balance(api_key: str, id_token: str):
    _ensure_api_key(api_key)
    return _client.get_balance(id_token)

# PERBAIKAN: bool | None -> Optional[bool] dan str | None -> Optional[str]
def get_family(api_key: str, tokens: dict, family_code: str, is_enterprise: Optional[bool] = None, migration_type: Optional[str] = None):
    _ensure_api_key(api_key)
    return _client.get_family(tokens, family_code, is_enterprise, migration_type)

def get_package(api_key: str, tokens: dict, package_option_code: str, package_family_code: str = "", package_variant_code: str = ""):
    _ensure_api_key(api_key)
    return _client.get_package_detail(tokens, package_option_code, package_family_code, package_variant_code)

def get_addons(api_key: str, tokens: dict, package_option_code: str):
    _ensure_api_key(api_key)
    return _client.get_addons(tokens, package_option_code)

def intercept_page(api_key: str, tokens: dict, option_code: str, is_enterprise: bool = False):
    _ensure_api_key(api_key)
    return _client.intercept_page(tokens, option_code, is_enterprise)

def login_info(api_key: str, tokens: dict, is_enterprise: bool = False):
    _ensure_api_key(api_key)
    return _client.login_info(tokens, is_enterprise)

# PERBAIKAN: bool | None -> Optional[bool] dan str | None -> Optional[str]
def get_package_details(api_key: str, tokens: dict, family_code: str, variant_code: str, option_order: int, is_enterprise: Optional[bool] = None, migration_type: Optional[str] = None):
    _ensure_api_key(api_key)
    return _client.get_package_by_order(tokens, family_code, variant_code, option_order)

def get_notifications(api_key: str, tokens: dict):
    _ensure_api_key(api_key)
    return _client.get_notifications(tokens)

def get_notification_detail(api_key: str, tokens: dict, notification_id: str):
    _ensure_api_key(api_key)
    return _client.get_notification_detail(tokens, notification_id)

def get_pending_transaction(api_key: str, tokens: dict):
    _ensure_api_key(api_key)
    return _client.get_pending_transaction(tokens)

def get_transaction_history(api_key: str, tokens: dict):
    _ensure_api_key(api_key)
    return _client.get_transaction_history(tokens)

def get_tiering_info(api_key: str, tokens: dict):
    _ensure_api_key(api_key)
    return _client.get_tiering_info(tokens)

def unsubscribe(api_key: str, tokens: dict, quota_code: str, product_domain: str, product_subscription_type: str):
    _ensure_api_key(api_key)
    return _client.unsubscribe(tokens, quota_code, product_domain, product_subscription_type)

def dashboard_segments(api_key: str, tokens: dict):
    _ensure_api_key(api_key)
    return _client.dashboard_segments(tokens)

def get_profile(api_key: str, access_token: str, id_token: str):
    _ensure_api_key(api_key)
    return _client.get_profile(access_token, id_token)

def get_families(api_key: str, tokens: dict, package_category_code: str):
    _ensure_api_key(api_key)
    return _client.get_families_by_category(tokens, package_category_code)

def validate_puk(api_key: str, tokens: dict, msisdn: str, puk: str):
    _ensure_api_key(api_key)
    return _client.validate_puk(tokens, msisdn, puk)

def get_quota_details(api_key: str, tokens: dict):
    _ensure_api_key(api_key)
    return _client.get_quota_details(tokens)

# Extra utility functions (Modern additions)
def check_service_availability(api_key: str, tokens: dict) -> bool:
    _ensure_api_key(api_key)
    balance = _client.get_balance(tokens.get("id_token", ""))
    return balance is not None

def get_api_status(api_key: str, tokens: dict) -> dict:
    _ensure_api_key(api_key)
    status = {"auth": False, "balance": False, "packages": False, "timestamp": datetime.now().isoformat()}
    try:
        if "access_token" in tokens and "id_token" in tokens:
            prof = _client.get_profile(tokens["access_token"], tokens["id_token"])
            status["auth"] = bool(prof and prof.get("profile"))
            
            bal = _client.get_balance(tokens["id_token"])
            status["balance"] = bal is not None
            
            quota = _client.get_quota_details(tokens)
            status["packages"] = bool(quota and "quotas" in quota)
    except Exception as e:
        status["error"] = str(e)
    return status
