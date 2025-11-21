import logging
from typing import Dict, Any, List, Optional

# Import core client
from app.client.engsel import send_api_request

# Setup Logger
logger = logging.getLogger(__name__)

# Type definitions
TokenDict = Dict[str, str]
ApiResponse = Dict[str, Any]

class RedeemableClient:
    """
    Client khusus untuk menangani Personalization & Redeemables.
    Fokus pada pengambilan dan penyaringan hadiah/penawaran.
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
        """Wrapper internal dengan error handling terpusat."""
        final_payload = {
            "is_enterprise": False,
            "lang": "en",
            **payload
        }

        if description:
            logger.info(description)

        try:
            response = send_api_request(
                self.api_key, 
                path, 
                final_payload, 
                id_token, 
                "POST"
            )
            
            # Validasi struktur dasar response XL
            if not response:
                logger.warning(f"Empty response from {path}")
                return {"status": "FAILED", "message": "Empty response"}
            
            return response

        except Exception as e:
            logger.error(f"Error on {path}: {e}")
            return {"status": "ERROR", "message": str(e)}

    def get_redeemables(self, tokens: TokenDict, is_enterprise: bool = False) -> Optional[ApiResponse]:
        """
        Mengambil daftar item yang bisa diklaim (Redeemables).
        """
        if not tokens.get("id_token"):
            logger.error("Missing ID Token for fetching redeemables.")
            return None

        response = self._send_request(
            path="api/v8/personalization/redeemables",
            payload={"is_enterprise": is_enterprise},
            id_token=tokens["id_token"],
            description="🎁 Fetching Redeemable items..."
        )

        # Analisis hasil response untuk logging yang lebih informatif
        if response and response.get("status") == "SUCCESS":
            data = response.get("data", {})
            categories = data.get("categories", [])
            logger.info(f"✅ Found {len(categories)} categories of redeemables.")
            return response
        
        logger.error(f"❌ Failed to fetch redeemables. Status: {response.get('status')}")
        return None

    def find_redeemable_by_keyword(
        self, 
        tokens: TokenDict, 
        keyword: str, 
        category_name: str = "INTERNET"
    ) -> List[Dict[str, Any]]:
        """
        [NEW FEATURE] Mencari item redeemable spesifik berdasarkan kata kunci.
        Berguna untuk automation (misal: cari 'Unlimited YouTube').
        """
        raw_data = self.get_redeemables(tokens)
        if not raw_data or "data" not in raw_data:
            return []

        found_items = []
        categories = raw_data["data"].get("categories", [])
        
        for cat in categories:
            # Filter kategori jika diminta (opsional)
            if category_name and category_name.upper() not in cat.get("name", "").upper():
                continue

            packages = cat.get("packages", [])
            for pkg in packages:
                name = pkg.get("name", "").lower()
                desc = pkg.get("description", "").lower()
                
                if keyword.lower() in name or keyword.lower() in desc:
                    found_items.append(pkg)
                    logger.debug(f"🔍 Match found: {pkg.get('name')}")

        logger.info(f"🔎 Search '{keyword}': Found {len(found_items)} items.")
        return found_items


# =============================================================================
# COMPATIBILITY LAYER (Legacy Support)
# =============================================================================

def get_redeemables(
    api_key: str,
    tokens: dict,
    is_enterprise: bool = False,
) -> dict:
    """Legacy wrapper for get_redeemables"""
    client = RedeemableClient(api_key)
    return client.get_redeemables(tokens, is_enterprise)
