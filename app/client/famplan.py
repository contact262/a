import logging
from typing import Dict, Any, List, Optional, Union

# Import dependencies
from app.client.engsel import send_api_request
from app.menus.util import format_quota_byte

# Setup Logger
logger = logging.getLogger(__name__)

# Type definition
TokenDict = Dict[str, str]
ApiResponse = Dict[str, Any]

class FamilyPlanClient:
    """
    Client khusus untuk manajemen XL Family Plan.
    Menangani member, kuota sharing, dan validasi nomor.
    """

    def __init__(self, api_key: str):
        self.api_key = api_key

    def _send_request(
        self, 
        path: str, 
        payload: Dict[str, Any], 
        id_token: str, 
        description: str = ""
    ) -> ApiResponse:
        """
        Wrapper internal untuk mengirim request dengan standar payload Family Plan.
        """
        # Default payload attributes
        final_payload = {
            "is_enterprise": False,
            "lang": "en",
            **payload
        }

        if description:
            logger.info(description)

        try:
            return send_api_request(
                self.api_key, 
                path, 
                final_payload, 
                id_token, 
                "POST"
            )
        except Exception as e:
            logger.error(f"Error executing {path}: {e}")
            return {"status": "Failed", "message": str(e), "data": None}

    def get_family_data(self, tokens: TokenDict) -> ApiResponse:
        """Mengambil data dashboard family plan (slot & member)"""
        return self._send_request(
            path="sharings/api/v8/family-plan/member-info",
            payload={"group_id": 0},
            id_token=tokens.get("id_token", ""),
            description="Fetching family plan data..."
        )

    def validate_msisdn(self, tokens: TokenDict, msisdn: str) -> ApiResponse:
        """
        Cek apakah nomor valid untuk ditambahkan (menggunakan endpoint check-dukcapil).
        """
        payload = {
            "msisdn": msisdn,
            "with_bizon": True,
            "with_family_plan": True,
            "with_optimus": True,
            "with_regist_status": True,
            "with_enterprise": True
        }
        
        return self._send_request(
            path="api/v8/auth/check-dukcapil",
            payload=payload,
            id_token=tokens.get("id_token", ""),
            description=f"Validating MSISDN candidate {msisdn}..."
        )

    def change_member(
        self,
        tokens: TokenDict,
        parent_alias: str,
        alias: str,
        slot_id: int,
        family_member_id: str,
        new_msisdn: str,
    ) -> ApiResponse:
        """
        Menambahkan atau mengganti member pada slot tertentu.
        """
        payload = {
            "parent_alias": parent_alias,
            "slot_id": slot_id,
            "alias": alias,
            "msisdn": new_msisdn,
            "family_member_id": family_member_id
        }

        return self._send_request(
            path="sharings/api/v8/family-plan/change-member",
            payload=payload,
            id_token=tokens.get("id_token", ""),
            description=f"Assigning {new_msisdn} to slot {slot_id}..."
        )

    def remove_member(self, tokens: TokenDict, family_member_id: str) -> ApiResponse:
        """Menghapus member dari Family Plan"""
        return self._send_request(
            path="sharings/api/v8/family-plan/remove-member",
            payload={"family_member_id": family_member_id},
            id_token=tokens.get("id_token", ""),
            description=f"Removing family member ID {family_member_id}..."
        )

    def set_quota_limit(
        self,
        tokens: TokenDict,
        original_allocation: int,
        new_allocation: int,
        family_member_id: str,
    ) -> ApiResponse:
        """Mengatur batas penggunaan kuota member"""
        formatted_quota = format_quota_byte(new_allocation)
        
        payload = {
            "member_allocations": [{
                "family_member_id": family_member_id,
                "original_allocation": original_allocation,
                "new_allocation": new_allocation,
                # Field default yg dibutuhkan API
                "new_text_allocation": 0,
                "original_text_allocation": 0,
                "original_voice_allocation": 0,
                "new_voice_allocation": 0,
                "message": "",
                "status": ""
            }]
        }

        return self._send_request(
            path="sharings/api/v8/family-plan/allocate-quota",
            payload=payload,
            id_token=tokens.get("id_token", ""),
            description=f"Setting quota limit for {family_member_id} to {formatted_quota}..."
        )


# =============================================================================
# COMPATIBILITY LAYER (Backward Compatibility)
# Wrapper functions agar kode lama tetap jalan tanpa error.
# =============================================================================

def get_family_data(api_key: str, tokens: dict) -> dict:
    return FamilyPlanClient(api_key).get_family_data(tokens)

def validate_msisdn(api_key: str, tokens: dict, msisdn: str) -> dict:
    return FamilyPlanClient(api_key).validate_msisdn(tokens, msisdn)

def change_member(
    api_key: str,
    tokens: dict,
    parent_alias: str,
    alias: str,
    slot_id: int,
    family_member_id: str,
    new_msisdn: str,
) -> dict:
    return FamilyPlanClient(api_key).change_member(
        tokens, parent_alias, alias, slot_id, family_member_id, new_msisdn
    )

def remove_member(api_key: str, tokens: dict, family_member_id: str) -> dict:
    return FamilyPlanClient(api_key).remove_member(tokens, family_member_id)

def set_quota_limit(
    api_key: str,
    tokens: dict,
    original_allocation: int,
    new_allocation: int,
    family_member_id: str,
) -> dict:
    return FamilyPlanClient(api_key).set_quota_limit(
        tokens, original_allocation, new_allocation, family_member_id
    )
