import base64
import logging
import os
import uuid
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Union

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Pastikan path import ini sesuai
from app.client.encrypt import (
    java_like_timestamp,
    ts_gmt7_without_colon,
    ax_api_signature,
    load_ax_fp,
    ax_device_id
)

# Setup Logger
logger = logging.getLogger(__name__)

@dataclass
class CiamConfig:
    """Konfigurasi terpusat untuk CIAM Client"""
    base_url: str = field(default_factory=lambda: os.getenv("BASE_CIAM_URL", "https://api.xl.co.id"))
    basic_auth: str = field(default_factory=lambda: os.getenv("BASIC_AUTH", ""))
    user_agent: str = field(default_factory=lambda: os.getenv("UA", "Mozilla/5.0"))
    device_id: str = field(default_factory=ax_device_id)
    fingerprint: str = field(default_factory=load_ax_fp)
    timeout: int = 30

class CiamClient:
    """
    Klien modern untuk berinteraksi dengan XL CIAM.
    """

    def __init__(self, config: Optional[CiamConfig] = None):
        self.config = config or CiamConfig()
        if not self.config.basic_auth:
            logger.warning("BASIC_AUTH environment variable is not set!")
            
        self._session = self._init_session()
        
        # Static headers yang jarang berubah
        self._static_headers = {
            "Accept-Encoding": "gzip, deflate, br",
            "Authorization": f"Basic {self.config.basic_auth}",
            "Ax-Device-Id": self.config.device_id,
            "Ax-Fingerprint": self.config.fingerprint,
            "Ax-Request-Device": "samsung", # Disarankan tetap samsung agar tidak memicu fraud detection baru
            "Ax-Request-Device-Model": "SM-N935F",
            "Ax-Substype": "PREPAID",
            "User-Agent": self.config.user_agent,
        }

    def _init_session(self) -> requests.Session:
        session = requests.Session()
        retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
        session.mount('https://', HTTPAdapter(max_retries=retries))
        return session

    def _get_gmt7_now(self) -> datetime:
        return datetime.now(timezone(timedelta(hours=7)))

    def _get_dynamic_headers(self) -> Dict[str, str]:
        now = self._get_gmt7_now()
        # Membersihkan protocol dari host header
        host = self.config.base_url.replace("https://", "").replace("http://", "")
        if "/" in host: 
            host = host.split("/")[0]

        return {
            "Ax-Request-At": java_like_timestamp(now),
            "Ax-Request-Id": str(uuid.uuid4()),
            "Host": host,
        }

    def _make_request(
        self, 
        method: str, 
        endpoint: str, 
        headers: Optional[Dict] = None,
        return_full_response: bool = False,
        **kwargs
    ) -> Union[Optional[Dict[str, Any]], requests.Response]:
        
        url = f"{self.config.base_url}{endpoint}"
        
        # Merge headers: Static -> Dynamic -> Custom Overrides
        final_headers = self._static_headers.copy()
        final_headers.update(self._get_dynamic_headers())
        if headers:
            final_headers.update(headers)

        try:
            response = self._session.request(
                method=method, 
                url=url, 
                headers=final_headers, 
                timeout=self.config.timeout, 
                **kwargs
            )
            
            # Untuk debugging jika diperlukan
            if response.status_code >= 500:
                logger.error(f"Server Error {response.status_code}: {response.text}")
                response.raise_for_status()

            if return_full_response:
                return response

            try:
                json_data = response.json()
            except ValueError:
                logger.error(f"Response invalid JSON: {response.text[:100]}")
                return None

            # Inject status code untuk handling logic di caller
            if isinstance(json_data, dict):
                json_data["_status_code"] = response.status_code
            
            return json_data

        except Exception as e:
            logger.error(f"Request Error {endpoint}: {e}")
            return None

    def validate_contact(self, contact: str) -> bool:
        if not contact or not contact.startswith("628") or not (10 <= len(contact) <= 14):
            logger.error(f"Invalid contact format: {contact}")
            return False
        return True

    def request_otp(self, contact: str) -> Optional[str]:
        if not self.validate_contact(contact): return None
        
        # Note: Original script sends data="" (empty string) implicitly via requests logic
        # but here strictly following params pattern is cleaner.
        resp = self._make_request(
            "GET", "/realms/xl-ciam/auth/otp",
            params={"contact": contact, "contactType": "SMS", "alternateContact": "false"},
            headers={"Content-Type": "application/json"}
        )
        
        if resp and "subscriber_id" in resp:
            return resp["subscriber_id"]
            
        logger.error(f"Failed requesting OTP: {resp}")
        return None

    def extend_session(self, subscriber_id: str) -> Optional[str]:
        try:
            if not subscriber_id: return None
            b64_id = base64.b64encode(subscriber_id.encode()).decode()
            
            resp = self._make_request(
                "GET", "/realms/xl-ciam/auth/extend-session",
                params={"contact": b64_id, "contactType": "DEVICEID"},
                headers={"Content-Type": "application/json"}
            )
            
            if resp and resp.get("_status_code") == 200:
                return resp.get("data", {}).get("exchange_code")
                
            logger.warning(f"Failed extend session: {resp}")
            return None
        except Exception as e:
            logger.error(f"Error in extend_session: {e}")
            return None

    def submit_otp(self, api_key: str, contact_type: str, contact: str, code: str) -> Optional[Dict]:
        """
        FIX: Menggunakan payload string manual.
        Menggunakan dictionary pada requests.post(data=dict) akan memicu URL-Encoding otomatis 
        (misal '=' jadi '%3D') yang menyebabkan Signature Mismatch pada beberapa server CIAM.
        """
        if contact_type == "SMS" and not self.validate_contact(contact): 
            print("Invalid number")
            return None
        
        final_contact = ""
        if contact_type == "DEVICEID":
            final_contact = base64.b64encode(contact.encode()).decode()
        else:
            final_contact = contact
        
        now = self._get_gmt7_now()
        # Original script logic: Sign using NOW, but Header uses NOW - 5 MINS
        ts_sign = ts_gmt7_without_colon(now)
        ts_head = ts_gmt7_without_colon(now - timedelta(minutes=5))
        
        sig = ax_api_signature(api_key, ts_sign, final_contact, code, contact_type)
        if not sig: return None

        # Construct Payload String manually to avoid requests auto-encoding issues
        payload_str = f"contactType={contact_type}&code={code}&grant_type=password&contact={final_contact}&scope=openid"

        headers = {
            "Ax-Api-Signature": sig,
            "Ax-Request-At": ts_head, # Override dynamic time
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        logger.info("Submitting OTP...")
        resp = self._make_request("POST", "/realms/xl-ciam/protocol/openid-connect/token", data=payload_str, headers=headers)
        
        if resp and "error" not in resp:
            logger.info("Login successful.")
            return resp
        
        logger.error(f"Login failed: {resp}")
        return None

    def refresh_token(self, api_key: str, refresh_token: str, subscriber_id: str) -> Optional[Dict]:
        # Gunakan return_full_response=True karena kita butuh check status code dan text raw
        response = self._make_request(
            "POST", "/realms/xl-ciam/protocol/openid-connect/token",
            data={"grant_type": "refresh_token", "refresh_token": refresh_token},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            return_full_response=True
        )
        
        if response is None: return None

        # Handle Success
        if response.status_code == 200:
            return response.json()

        # Handle 400 Error Logic (Session Not Active Recovery)
        if response.status_code == 400:
            resp_json = {}
            try:
                resp_json = response.json()
            except: pass
            
            # Cek pesan error spesifik
            if resp_json.get("error_description") == "Session not active":
                logger.warning("Session expired, attempting auto-extension...")
                
                if not subscriber_id:
                    raise ValueError("Subscriber ID is missing for session extension")

                exch_code = self.extend_session(subscriber_id)
                if not exch_code:
                    raise ValueError("Failed to get exchange code")
                
                extend_result = self.submit_otp(api_key, "DEVICEID", subscriber_id, exch_code)
                if not extend_result:
                    # Logic asli: Cek teks response untuk validasi akhir
                    if "Invalid refresh token" in response.text:
                        raise ValueError("Refresh token is invalid or expired. Please login again.")
                    raise ValueError("Failed to submit OTP after extending session")
                
                return extend_result
            
            logger.error(f"Failed to refresh token: {response.text}")
            return None

        return None

    def get_auth_code(self, tokens: Union[Dict, str], pin: str, msisdn: str) -> Optional[str]:
        try:
            access_token = tokens.get("access_token") if isinstance(tokens, dict) else tokens
            pin_b64 = base64.b64encode(pin.encode("utf-8")).decode("utf-8")
            
            # Endpoint ini menggunakan JSON body
            resp = self._make_request(
                "POST", "/ciam/auth/authorization-token/generate",
                json={"pin": pin_b64, "transaction_type": "SHARE_BALANCE", "receiver_msisdn": msisdn},
                headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
            )
            
            if resp and resp.get("status") == "Success":
                return resp.get("data", {}).get("authorization_code")
            
            logger.error(f"Failed getting auth code: {resp}")
            return None
        except Exception as e:
            logger.error(f"Exception in get_auth_code: {e}")
            return None

# =============================================================================
# COMPATIBILITY LAYER (Backward Compatibility)
# =============================================================================

_global_client = CiamClient()

def get_new_token(api_key: str, refresh_token: str, subscriber_id: str) -> Optional[dict]:
    return _global_client.refresh_token(api_key, refresh_token, subscriber_id)

def get_otp(contact: str) -> Optional[str]:
    return _global_client.request_otp(contact)

def submit_otp(api_key: str, contact_type: str, contact: str, code: str):
    return _global_client.submit_otp(api_key, contact_type, contact, code)

def extend_session(subscriber_id: str) -> Optional[str]:
    return _global_client.extend_session(subscriber_id)

def get_auth_code(tokens: dict, pin: str, msisdn: str):
    return _global_client.get_auth_code(tokens, pin, msisdn)

def validate_contact(contact: str) -> bool:
    return _global_client.validate_contact(contact)
