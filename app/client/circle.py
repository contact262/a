import logging
from typing import Dict, Any, Optional

from app.client.engsel import send_api_request
from app.client.encrypt import encrypt_circle_msisdn

# Setup Logger
logger = logging.getLogger(__name__)

# Type Alias
TokenDict = Dict[str, str]
ApiResponse = Dict[str, Any]

class CircleClient:
    """
    Client untuk mengelola fitur Family Circle / Family Hub XL.
    Centralized logic untuk validasi, invite, dan management grup.
    """

    def __init__(self, api_key: str):
        self.api_key = api_key

    def _encrypt(self, msisdn: str) -> str:
        """Wrapper enkripsi MSISDN khusus Circle"""
        return encrypt_circle_msisdn(self.api_key, msisdn)

    def _send_request(
        self, 
        path: str, 
        payload: Dict[str, Any], 
        id_token: str,
        description: str = ""
    ) -> ApiResponse:
        """
        Internal wrapper untuk mengirim request.
        Otomatis menyisipkan default payload (lang, is_enterprise).
        """
        # Default payload standar
        final_payload = {
            "is_enterprise": False,
            "lang": "en",
            **payload  # Merge dengan payload spesifik
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
            # Kembalikan format error yang konsisten agar caller tidak crash
            return {"status": "Failed", "message": str(e), "data": None}

    def get_group_data(self, tokens: TokenDict) -> ApiResponse:
        """Mengambil status dan detail grup"""
        return self._send_request(
            path="family-hub/api/v8/groups/status",
            payload={},
            id_token=tokens.get("id_token", ""),
            description="Fetching group detail..."
        )

    def get_group_members(self, tokens: TokenDict, group_id: str) -> ApiResponse:
        """Mengambil daftar anggota grup"""
        return self._send_request(
            path="family-hub/api/v8/members/info",
            payload={"group_id": group_id},
            id_token=tokens.get("id_token", ""),
            description="Fetching group members..."
        )

    def validate_member(self, tokens: TokenDict, msisdn: str) -> ApiResponse:
        """Validasi apakah nomor eligible masuk circle"""
        encrypted_msisdn = self._encrypt(msisdn)
        return self._send_request(
            path="family-hub/api/v8/members/validate",
            payload={"msisdn": encrypted_msisdn},
            id_token=tokens.get("id_token", ""),
            description=f"Validating member {msisdn}..."
        )

    def invite_member(
        self,
        tokens: TokenDict,
        msisdn: str,
        name: str,
        group_id: str,
        member_id_parent: str,
    ) -> ApiResponse:
        """Mengundang anggota baru ke circle"""
        encrypted_msisdn = self._encrypt(msisdn)
        # Menggunakan debug untuk log sensitif, bukan info/print
        logger.debug(f"Encrypted MSISDN for invite: {encrypted_msisdn}")

        payload = {
            "access_token": tokens.get("access_token", ""),
            "group_id": group_id,
            "members": [{"msisdn": encrypted_msisdn, "name": name}],
            "member_id_parent": member_id_parent
        }

        return self._send_request(
            path="family-hub/api/v8/members/invite",
            payload=payload,
            id_token=tokens.get("id_token", ""),
            description=f"Inviting {msisdn} to circle..."
        )

    def remove_member(
        self,
        tokens: TokenDict,
        member_id: str,
        group_id: str,
        member_id_parent: str,
        is_last_member: bool = False,
    ) -> ApiResponse:
        """Menghapus anggota dari circle"""
        payload = {
            "member_id": member_id,
            "group_id": group_id,
            "is_last_member": is_last_member,
            "member_id_parent": member_id_parent
        }

        return self._send_request(
            path="family-hub/api/v8/members/remove",
            payload=payload,
            id_token=tokens.get("id_token", ""),
            description=f"Removing member ID {member_id}..."
        )

    def accept_invitation(
        self,
        tokens: TokenDict,
        group_id: str,
        member_id: str,
    ) -> ApiResponse:
        """Menerima undangan masuk circle"""
        payload = {
            "access_token": tokens.get("access_token", ""),
            "group_id": group_id,
            "member_id": member_id
        }

        return self._send_request(
            path="family-hub/api/v8/groups/accept-invitation",
            payload=payload,
            id_token=tokens.get("id_token", ""),
            description=f"Accepting invitation for group {group_id}..."
        )

    def create_circle(
        self,
        tokens: TokenDict,
        parent_name: str,
        group_name: str,
        member_msisdn: str,
        member_name: str,
    ) -> ApiResponse:
        """Membuat Circle baru"""
        encrypted_msisdn = self._encrypt(member_msisdn)
        
        payload = {
            "access_token": tokens.get("access_token", ""),
            "parent_name": parent_name,
            "group_name": group_name,
            "members": [{"msisdn": encrypted_msisdn, "name": member_name}],
        }

        return self._send_request(
            path="family-hub/api/v8/groups/create",
            payload=payload,
            id_token=tokens.get("id_token", ""),
            description=f"Creating Circle '{group_name}' with member {member_msisdn}..."
        )

    def get_spending_tracker(
        self,
        tokens: TokenDict,
        parent_subs_id: str,
        family_id: str
    ) -> ApiResponse:
        """Mengambil data spending tracker (Gamification)"""
        return self._send_request(
            path="gamification/api/v8/family-hub/spending-tracker",
            payload={"parent_subs_id": parent_subs_id, "family_id": family_id},
            id_token=tokens.get("id_token", ""),
            description="Fetching spending tracker..."
        )

    def get_bonus_data(
        self,
        tokens: TokenDict,
        parent_subs_id: str,
        family_id: str
    ) -> ApiResponse:
        """Mengambil list bonus kuota/hadiah"""
        return self._send_request(
            path="gamification/api/v8/family-hub/bonus/list",
            payload={"parent_subs_id": parent_subs_id, "family_id": family_id},
            id_token=tokens.get("id_token", ""),
            description="Fetching bonus data..."
        )


# =============================================================================
# COMPATIBILITY LAYER (Backward Compatibility)
# Memastikan kode legacy tetap berjalan tanpa perubahan.
# =============================================================================

def get_group_data(api_key: str, tokens: dict) -> dict:
    return CircleClient(api_key).get_group_data(tokens)

def get_group_members(api_key: str, tokens: dict, group_id: str) -> dict:
    return CircleClient(api_key).get_group_members(tokens, group_id)

def validate_circle_member(api_key: str, tokens: dict, msisdn: str) -> dict:
    return CircleClient(api_key).validate_member(tokens, msisdn)

def invite_circle_member(
    api_key: str, tokens: dict, msisdn: str, name: str, group_id: str, member_id_parent: str
) -> dict:
    return CircleClient(api_key).invite_member(tokens, msisdn, name, group_id, member_id_parent)

def remove_circle_member(
    api_key: str, tokens: dict, member_id: str, group_id: str, member_id_parent: str, is_last_member: bool = False
) -> dict:
    return CircleClient(api_key).remove_member(tokens, member_id, group_id, member_id_parent, is_last_member)

def accept_circle_invitation(api_key: str, tokens: dict, group_id: str, member_id: str) -> dict:
    return CircleClient(api_key).accept_invitation(tokens, group_id, member_id)

def create_circle(
    api_key: str, tokens: dict, parent_name: str, group_name: str, member_msisdn: str, member_name: str
) -> dict:
    return CircleClient(api_key).create_circle(tokens, parent_name, group_name, member_msisdn, member_name)

def spending_tracker(api_key: str, tokens: dict, parent_subs_id: str, family_id: str) -> dict:
    return CircleClient(api_key).get_spending_tracker(tokens, parent_subs_id, family_id)

def get_bonus_data(api_key: str, tokens: dict, parent_subs_id: str, family_id: str) -> dict:
    return CircleClient(api_key).get_bonus_data(tokens, parent_subs_id, family_id)
