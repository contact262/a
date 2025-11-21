import logging
from typing import Dict, Any, List, Optional, Union

# Import core client yang sudah stable (dengan auto-retry)
from app.client.engsel import send_api_request

# Setup Logger
logger = logging.getLogger(__name__)

# Type definitions
TokenDict = Dict[str, str]
ApiResponse = Dict[str, Any]

class SegmentsClient:
    """
    Client khusus untuk mengambil konfigurasi Store Segments (Kategori Paket).
    Menyediakan helper untuk mengekstrak Slug dan Label kategori.
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

    def get_segments(self, tokens: TokenDict, is_enterprise: bool = False) -> Optional[ApiResponse]:
        """
        Mengambil raw response dari endpoint segments.
        Berisi struktur menu toko (Store Menu Structure).
        """
        if not tokens.get("id_token"):
            logger.error("Missing ID Token for fetching segments.")
            return None

        response = self._send_request(
            path="api/v8/configs/store/segments",
            payload={"is_enterprise": is_enterprise},
            id_token=tokens["id_token"],
            description="📊 Fetching Store Segments..."
        )

        if response and response.get("status") == "SUCCESS":
            data = response.get("data", [])
            count = len(data) if isinstance(data, list) else 0
            logger.info(f"✅ Retrieved {count} segment groups.")
            return response
        
        logger.error(f"❌ Failed to fetch segments. Status: {response.get('status')}")
        return None

    def get_segment_slugs(self, tokens: TokenDict) -> List[Dict[str, str]]:
        """
        [NEW CAPABILITY]
        Mengambil daftar 'slug' dan 'label' yang bersih.
        Sangat berguna untuk bot navigasi menu tanpa parsing JSON yang dalam.
        
        Returns:
            List of dict: [{'label': 'Paket Utama', 'slug': 'main-package'}, ...]
        """
        raw_res = self.get_segments(tokens)
        if not raw_res or "data" not in raw_res:
            return []

        clean_list = []
        raw_data = raw_res["data"]
        
        # Parsing recursive sederhana karena struktur segment bisa nested
        if isinstance(raw_data, list):
            for item in raw_data:
                slug = item.get("slug")
                label = item.get("label") or item.get("name")
                if slug:
                    clean_list.append({"label": label, "slug": slug})
                    
        # Logging hasil parsing untuk debugging
        if clean_list:
            logger.info("📑 Available Segments:")
            for item in clean_list:
                logger.info(f"   - {item['label']:<20} (Slug: {item['slug']})")
                
        return clean_list


# =============================================================================
# COMPATIBILITY LAYER (Legacy Support)
# =============================================================================

def get_segments(
    api_key: str,
    tokens: dict,
    is_enterprise: bool = False,
    logger: Optional[Any] = None # Parameter logger diabaikan agar backward compatible
) -> Optional[Dict]:
    """Legacy wrapper for get_segments"""
    return SegmentsClient(api_key).get_segments(tokens, is_enterprise)

# Helper function baru yang bisa dipanggil langsung
def get_available_slugs(api_key: str, tokens: dict) -> List[Dict[str, str]]:
    """Helper wrapper for get_segment_slugs"""
    return SegmentsClient(api_key).get_segment_slugs(tokens)
