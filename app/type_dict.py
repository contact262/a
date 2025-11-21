from typing import TypedDict, Optional, Dict, Any, List, Union, cast

# =============================================================================
# TYPE DEFINITIONS (Interface)
# =============================================================================

class PaymentItem(TypedDict):
    """
    Struktur item untuk pembayaran/checkout.
    """
    item_code: str
    product_type: str  # Contoh: "DATA", "VOICE", dll
    item_price: int
    item_name: str
    tax: int
    token_confirmation: Optional[str]  # Bisa None jika tidak butuh konfirmasi token

class PackageToBuy(TypedDict):
    """
    Payload minimal untuk membeli sebuah paket.
    """
    family_code: str
    is_enterprise: bool
    variant_name: str
    order: int

class UserToken(TypedDict):
    """
    Struktur token autentikasi lengkap.
    """
    access_token: str
    refresh_token: str
    id_token: str
    token_type: str
    expires_in: int
    scope: str

class UserProfile(TypedDict, total=False):
    """
    Profil pengguna (total=False artinya field boleh tidak lengkap).
    """
    number: str
    subscriber_id: str
    subscription_type: str
    balance: int
    balance_expired_at: int
    point_info: str

# =============================================================================
# RUNTIME VALIDATORS (Safety Net)
# =============================================================================

def validate_payment_item(data: Dict[str, Any]) -> PaymentItem:
    """
    Memastikan dictionary memiliki field wajib PaymentItem.
    Mencegah KeyError saat runtime.
    """
    required_keys = {"item_code", "item_price", "item_name"}
    if not isinstance(data, dict):
        raise ValueError(f"PaymentItem must be dict, got {type(data)}")
    
    missing = required_keys - data.keys()
    if missing:
        raise ValueError(f"Invalid PaymentItem. Missing keys: {missing}")
        
    # Type casting safe karena sudah divalidasi
    return cast(PaymentItem, {
        "item_code": str(data.get("item_code", "")),
        "product_type": str(data.get("product_type", "")),
        "item_price": int(data.get("item_price", 0)),
        "item_name": str(data.get("item_name", "Unknown Item")),
        "tax": int(data.get("tax", 0)),
        "token_confirmation": data.get("token_confirmation") # Bisa None
    })

def create_payment_item(
    code: str, 
    price: int, 
    name: str, 
    token: str = "", 
    p_type: str = ""
) -> PaymentItem:
    """
    Factory helper untuk membuat object PaymentItem dengan cepat dan aman.
    """
    return {
        "item_code": code,
        "item_price": price,
        "item_name": name,
        "product_type": p_type,
        "tax": 0,
        "token_confirmation": token
    }
