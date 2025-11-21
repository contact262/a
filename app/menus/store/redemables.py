import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional

# Import Internal Modules
from app.client.store.redeemables import get_redeemables
from app.service.auth import AuthInstance
from app.menus.util import clear_screen, pause
from app.menus.package import show_package_details, get_packages_by_family

# Setup Logger
logger = logging.getLogger(__name__)

WIDTH = 60

def _format_expiry(timestamp: int) -> str:
    """Helper untuk memformat tanggal kadaluarsa dengan aman."""
    try:
        if not timestamp:
            return "Selamanya"
        
        # Handle millis vs seconds
        if timestamp > 1000000000000:
            timestamp = timestamp / 1000
            
        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime("%d %b %Y")
    except Exception:
        return "Unknown Date"

def _handle_action(api_key: str, tokens: dict, pkg: dict, is_enterprise: bool):
    """Menangani logika navigasi berdasarkan action_type."""
    action_type = pkg.get("action_type", "")
    action_param = pkg.get("action_param", "")
    name = pkg.get("name", "Unknown")

    print(f"\n🔄 Memproses: {name}...")
    
    try:
        if action_type == "PLP":
            # Product List Page -> Menampilkan list paket dalam family
            # Parameter biasanya berupa Family Code
            get_packages_by_family(action_param, is_enterprise, "")
            
        elif action_type == "PDP":
            # Product Detail Page -> Menampilkan detail satu paket
            # Parameter biasanya berupa Option Code
            show_package_details(
                api_key,
                tokens,
                action_param,
                is_enterprise,
            )
            
        elif action_type == "WEBVIEW":
            print(f"ℹ️  Item ini adalah link web: {action_param}")
            print("   Fitur browser belum tersedia di CLI.")
            pause()
            
        else:
            print(f"⚠️  Tipe aksi tidak dikenal: {action_type}")
            print(f"   Param: {action_param}")
            pause()
            
    except Exception as e:
        logger.error(f"Error handling action {action_type}: {e}")
        print(f"❌ Terjadi kesalahan saat membuka item: {e}")
        pause()

def show_redeemables_menu(is_enterprise: bool = False):
    """
    Menampilkan menu Redeemables (Voucher/Bonus) dengan UI modern.
    """
    while True:
        # 1. Validasi Auth
        api_key = AuthInstance.api_key
        tokens = AuthInstance.get_active_tokens()
        
        if not tokens:
            print("❌ Sesi kadaluarsa. Silahkan login kembali.")
            pause()
            return

        # 2. Fetch Data
        clear_screen()
        print("=" * WIDTH)
        print("🎁  XL STORE - REDEEMABLES & PROMO".center(WIDTH))
        print("=" * WIDTH)
        print("⏳ Sedang mengambil data promo terbaru...", end="\r")
        
        try:
            res = get_redeemables(api_key, tokens, is_enterprise)
        except Exception as e:
            logger.error(f"Fetch redeemables failed: {e}")
            res = None

        if not res or "data" not in res:
            print(" " * WIDTH, end="\r") # Clear loading line
            print("\n❌ Gagal mengambil data redeemables.")
            print("   Kemungkinan tidak ada promo tersedia saat ini.")
            pause()
            return

        categories = res.get("data", {}).get("categories", [])
        if not categories:
            print("\n📭 Tidak ada kategori promo ditemukan.")
            pause()
            return

        # 3. Render Menu & Build Map
        selection_map = {} # Map 'a1' -> package_data
        
        print(" " * WIDTH, end="\r") # Clear loading line
        
        for i, category in enumerate(categories):
            cat_name = category.get("category_name", "Unknown Category")
            items = category.get("redeemables", [])
            
            if not items:
                continue

            cat_letter = chr(65 + i) # A, B, C...
            print(f"\n[{cat_letter}] {cat_name.upper()}")
            print("-" * WIDTH)
            
            for j, item in enumerate(items):
                key = f"{cat_letter}{j+1}".lower()
                
                # Store data for selection
                selection_map[key] = item
                
                # Data Display
                name = item.get("name", "No Name")[:40]
                valid_date = _format_expiry(item.get("valid_until", 0))
                act_type = item.get("action_type", "UNK")
                
                # Icon based on type
                icon = "📦" if act_type == "PDP" else "📂" if act_type == "PLP" else "🔗"
                
                print(f" {cat_letter}{j+1:<2} {icon} {name:<35}")
                print(f"        Exp: {valid_date} | Tipe: {act_type}")

        print("\n" + "=" * WIDTH)
        print("[Kode]  Pilih Promo (Contoh: A1)")
        print("[00]    Kembali ke Menu Utama")
        print("-" * WIDTH)
        
        # 4. Input Loop
        choice = input("Pilihan >> ").strip().lower()
        
        if choice == "00":
            return
            
        if choice in selection_map:
            selected_item = selection_map[choice]
            _handle_action(api_key, tokens, selected_item, is_enterprise)
        else:
            print("⚠️  Kode pilihan tidak valid.")
            pause()
