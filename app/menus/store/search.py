import logging
from typing import Dict, Any, Optional

# Import Internal Modules
from app.client.store.search import get_family_list, get_store_packages
from app.menus.package import get_packages_by_family, show_package_details
from app.menus.util import clear_screen, pause
from app.service.auth import AuthInstance

# Setup Logger
logger = logging.getLogger(__name__)

WIDTH = 65

def _handle_action(api_key: str, tokens: dict, item: dict, is_enterprise: bool):
    """Menangani logika navigasi berdasarkan tipe aksi paket."""
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
                print("❌ Parameter paket kosong.")
                pause()

        elif action_type == "PLP":
            # Product List Page -> Buka list paket dalam family
            if action_param:
                get_packages_by_family(action_param, is_enterprise, "")
            else:
                print("❌ Parameter family kosong.")
                pause()
        
        else:
            print(f"⚠️  Tipe aksi tidak didukung: {action_type}")
            print(f"   Param: {action_param}")
            pause()

    except Exception as e:
        logger.error(f"Error handling action {action_type}: {e}")
        print(f"❌ Terjadi kesalahan: {e}")
        pause()

def show_family_list_menu(
    subs_type: str = "PREPAID",
    is_enterprise: bool = False,
):
    """
    Menampilkan daftar Kategori Family (Group Paket).
    """
    while True:
        api_key = AuthInstance.api_key
        tokens = AuthInstance.get_active_tokens()
        
        if not tokens:
            print("❌ Sesi berakhir.")
            pause()
            return

        clear_screen()
        print("=" * WIDTH)
        print("📂  XL STORE - FAMILY LIST".center(WIDTH))
        print("=" * WIDTH)
        print("⏳ Mengambil daftar kategori...", end="\r")

        try:
            res = get_family_list(api_key, tokens, subs_type, is_enterprise)
        except Exception as e:
            logger.error(f"Fetch family failed: {e}")
            res = None

        if not res or "data" not in res:
            print(" " * WIDTH, end="\r")
            print("❌ Gagal mengambil daftar family.")
            pause()
            return

        family_list = res.get("data", {}).get("results", [])
        
        if not family_list:
            print(" " * WIDTH, end="\r")
            print("📭 Tidak ada kategori ditemukan.")
            pause()
            return

        # Render Table
        print(" " * WIDTH, end="\r")
        print(f"{'NO':<4} | {'NAMA KATEGORI':<35} | {'KODE FAMILY'}")
        print("-" * WIDTH)

        for i, fam in enumerate(family_list):
            name = fam.get("label", "Unknown")[:35]
            code = fam.get("id", "-")
            print(f" {i + 1:<3} | {name:<35} | {code}")

        print("-" * WIDTH)
        print("[No]  Pilih Kategori")
        print("[00]  Kembali")
        print("=" * WIDTH)

        choice = input("Pilihan >> ").strip()

        if choice == "00":
            return

        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(family_list):
                selected = family_list[idx]
                fam_id = selected.get("id")
                if fam_id:
                    get_packages_by_family(fam_id, is_enterprise)
                else:
                    print("⚠️ ID Family tidak valid.")
                    pause()
            else:
                print("⚠️ Nomor tidak ada.")
                pause()
        else:
            print("⚠️ Input tidak valid.")
            pause()

def show_store_packages_menu(
    subs_type: str = "PREPAID",
    is_enterprise: bool = False,
):
    """
    Menampilkan daftar Paket Rekomendasi Store.
    """
    while True:
        api_key = AuthInstance.api_key
        tokens = AuthInstance.get_active_tokens()
        
        if not tokens: return

        clear_screen()
        print("=" * WIDTH)
        print("📦  XL STORE - RECOMMENDED PACKAGES".center(WIDTH))
        print("=" * WIDTH)
        print("⏳ Mengambil paket rekomendasi...", end="\r")

        try:
            res = get_store_packages(api_key, tokens, subs_type, is_enterprise)
        except Exception as e:
            logger.error(f"Fetch store packages failed: {e}")
            res = None

        if not res or "data" not in res:
            print(" " * WIDTH, end="\r")
            print("❌ Gagal mengambil paket.")
            pause()
            return

        # Normalisasi Data (Handle list vs dict)
        raw_data = res.get("data", {})
        
        # Coba cari list di berbagai key
        pkg_list = []
        if "results_price_only" in raw_data:
            pkg_list = raw_data["results_price_only"]
        elif "packages" in raw_data:
            pkg_list = raw_data["packages"]
        elif "results" in raw_data:
            pkg_list = raw_data["results"]
        elif isinstance(raw_data, list):
            pkg_list = raw_data

        if not pkg_list:
            print(" " * WIDTH, end="\r")
            print("📭 Tidak ada paket ditemukan.")
            pause()
            return

        # Render Table
        print(" " * WIDTH, end="\r")
        print(f"{'NO':<4} | {'NAMA PAKET':<30} | {'HARGA':<12} | {'MASA AKTIF'}")
        print("-" * WIDTH)

        selection_map = {}

        for i, pkg in enumerate(pkg_list):
            title = pkg.get("title") or pkg.get("name") or "Unknown"
            title = title[:30]
            
            # Price Logic
            orig_price = pkg.get("original_price", 0)
            disc_price = pkg.get("discounted_price", 0)
            final_price = disc_price if disc_price > 0 else orig_price
            
            price_str = f"{final_price:,}"
            validity = pkg.get("validity", "-")
            
            # Map for selection
            selection_map[i + 1] = {
                "title": title,
                "action_type": pkg.get("action_type", "PDP"),
                "action_param": pkg.get("action_param", "") or pkg.get("package_code", "")
            }

            print(f" {i + 1:<3} | {title:<30} | {price_str:<12} | {validity}")

        print("-" * WIDTH)
        print("[No]  Lihat Detail Paket")
        print("[00]  Kembali")
        print("=" * WIDTH)

        choice = input("Pilihan >> ").strip()

        if choice == "00":
            return

        if choice.isdigit():
            idx = int(choice)
            if idx in selection_map:
                selected = selection_map[idx]
                _handle_action(api_key, tokens, selected, is_enterprise)
            else:
                print("⚠️ Nomor tidak ada.")
                pause()
        else:
            print("⚠️ Input tidak valid.")
            pause()
