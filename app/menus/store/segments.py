import logging
from typing import Dict, Any, Optional

# Import Internal Modules
from app.client.store.segments import get_segments
from app.menus.util import clear_screen, pause
from app.service.auth import AuthInstance
from app.menus.package import show_package_details

# Setup Logger
logger = logging.getLogger(__name__)

WIDTH = 65

def _handle_action(api_key: str, tokens: dict, item: dict, is_enterprise: bool):
    """
    Menangani logika navigasi berdasarkan tipe aksi pada banner.
    """
    action_type = item.get("action_type", "UNKNOWN")
    action_param = item.get("action_param", "")
    title = item.get("title", "Unknown Item")

    print(f"\n🔄 Memproses: {title}...")

    try:
        if action_type == "PDP":
            # Product Detail Page -> Buka detail paket
            if action_param:
                show_package_details(api_key, tokens, action_param, is_enterprise)
            else:
                print("❌ Parameter paket (Option Code) kosong.")
                pause()
        
        elif action_type == "WEBVIEW":
            # Menangani link eksternal (jika ada)
            print(f"ℹ️  Item ini membuka link web: {action_param}")
            print("   Fitur browser belum tersedia di CLI.")
            pause()

        else:
            print(f"⚠️  Tipe aksi tidak didukung: {action_type}")
            print(f"   Param: {action_param}")
            pause()

    except Exception as e:
        logger.error(f"Error handling action {action_type}: {e}")
        print(f"❌ Terjadi kesalahan: {e}")
        pause()

def show_store_segments_menu(is_enterprise: bool = False):
    """
    Menampilkan menu Store Segments (Banner Promo) dengan UI modern.
    """
    while True:
        # 1. Validasi Sesi
        api_key = AuthInstance.api_key
        tokens = AuthInstance.get_active_tokens()
        
        if not tokens:
            print("❌ Sesi berakhir. Silahkan login kembali.")
            pause()
            return

        clear_screen()
        print("=" * WIDTH)
        print("🛍️  XL STORE - SEGMENTS & PROMO".center(WIDTH))
        print("=" * WIDTH)
        print("⏳ Mengambil data promo...", end="\r")

        # 2. Fetch Data
        try:
            res = get_segments(api_key, tokens, is_enterprise)
        except Exception as e:
            logger.error(f"Fetch segments failed: {e}")
            res = None

        if not res or "data" not in res:
            print(" " * WIDTH, end="\r")
            print("❌ Gagal mengambil data segments/promo.")
            pause()
            return

        segments = res.get("data", {}).get("store_segments", [])
        if not segments:
            print(" " * WIDTH, end="\r")
            print("📭 Tidak ada promo tersedia saat ini.")
            pause()
            return

        # 3. Render Menu
        print(" " * WIDTH, end="\r") # Clear loading text
        selection_map = {} # Map 'a1' -> data

        for i, segment in enumerate(segments):
            seg_title = segment.get("title", "Promo Lainnya")
            banners = segment.get("banners", [])
            
            if not banners:
                continue

            # Header Segment (A, B, C...)
            seg_letter = chr(65 + i)
            print(f"\n[{seg_letter}] {seg_title.upper()}")
            print("-" * WIDTH)

            for j, banner in enumerate(banners):
                # Data Parsing
                title = banner.get("title", "No Name")[:30] # Truncate
                fam_name = banner.get("family_name", "")[:15]
                price = banner.get("discounted_price", "N/A")
                validity = banner.get("validity", "-")
                
                # Formatting Price
                price_str = f"Rp{price}" if isinstance(price, (int, float)) else str(price)
                
                # Mapping Key (A1, A2, B1...)
                key = f"{seg_letter}{j+1}".lower()
                
                # Simpan data penting untuk aksi nanti
                selection_map[key] = {
                    "title": f"{fam_name} - {title}",
                    "action_type": banner.get("action_type"),
                    "action_param": banner.get("action_param")
                }

                # Print Row
                # Format: A1. Nama Paket | Harga | Masa Aktif
                row_prefix = f" {seg_letter}{j+1}"
                print(f"{row_prefix:<4} {title:<32} | {price_str:<10} | {validity}")

        print("\n" + "=" * WIDTH)
        print("[Kode]  Lihat Detail Promo (Contoh: A1)")
        print("[00]    Kembali ke Menu Utama")
        print("-" * WIDTH)

        # 4. User Input
        choice = input("Pilihan >> ").strip().lower()

        if choice == "00":
            return

        if choice in selection_map:
            selected_item = selection_map[choice]
            _handle_action(api_key, tokens, selected_item, is_enterprise)
        else:
            print("⚠️  Kode pilihan tidak valid.")
            pause()
