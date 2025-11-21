import logging
import sys

# Import Dependencies
from app.menus.package import show_package_details
from app.service.auth import AuthInstance
from app.menus.util import clear_screen, pause
from app.service.bookmark import BookmarkInstance
from app.client.engsel import get_family

# Setup Logger
logger = logging.getLogger(__name__)

def _find_option_code_in_family(family_data: dict, variant_name: str, order: int):
    """
    Helper function untuk mencari option_code di dalam struktur data family
    berdasarkan nama variant dan urutan (order).
    """
    try:
        if not family_data or "package_variants" not in family_data:
            return None

        for variant in family_data["package_variants"]:
            # Pencocokan nama variant (Case insensitive agar lebih robust)
            if variant.get("name", "").lower() == variant_name.lower():
                for option in variant.get("package_options", []):
                    if option.get("order") == order:
                        return option.get("package_option_code")
    except Exception as e:
        logger.error(f"Error parsing family data: {e}")
        return None
    return None

def show_bookmark_menu():
    """
    Menampilkan menu bookmark dengan UI modern dan command-line style inputs.
    """
    # Pastikan Auth Valid
    api_key = AuthInstance.api_key
    tokens = AuthInstance.get_active_tokens()
    
    if not tokens:
        print("⚠️  Sesi tidak valid. Silahkan login kembali.")
        pause()
        return

    while True:
        clear_screen()
        bookmarks = BookmarkInstance.get_bookmarks()
        
        print("=" * 60)
        print("🔖  BOOKMARK / PAKET TERSIMPAN".center(60))
        print("=" * 60)

        if not bookmarks:
            print("\n   [ 📭 Tidak ada bookmark tersimpan ]\n")
            print("   Tips: Anda bisa menyimpan paket favorit saat")
            print("   menjelajahi menu paket beli.")
            print("-" * 60)
            print("[00] Kembali")
            choice = input("\n>> ").strip()
            if choice == "00":
                return
            continue

        # Render Table Header
        print(f"{'NO':<4} | {'FAMILY / KATEGORI':<20} | {'NAMA PAKET'}")
        print("-" * 60)

        # Render Items
        for idx, bm in enumerate(bookmarks):
            fam = bm.get('family_name', 'Unknown')[:18]
            var = bm.get('variant_name', '-')
            opt = bm.get('option_name', '-')
            
            # Format nama paket gabungan
            pkg_name = f"{var} {opt}"[:30]
            print(f"{idx + 1:<4} | {fam:<20} | {pkg_name}")

        print("-" * 60)
        print("COMMANDS:")
        print(" [No]     Pilih nomor untuk beli/lihat detail")
        print(" [del No] Hapus bookmark (contoh: del 1)")
        print(" [00]     Kembali ke Menu Utama")
        print("=" * 60)

        choice = input("Pilihan >> ").strip().lower()

        # --- LOGIC HANDLING ---

        # 1. Back
        if choice in ["00", "back", "exit", "q"]:
            return

        # 2. Delete Command (Format: del <no> atau rm <no>)
        elif choice.startswith(("del ", "rm ")):
            try:
                idx = int(choice.split()[1]) - 1
                if 0 <= idx < len(bookmarks):
                    target = bookmarks[idx]
                    confirm = input(f"❓ Hapus bookmark '{target.get('variant_name')}'? (y/n): ").lower()
                    if confirm == 'y':
                        BookmarkInstance.remove_bookmark(
                            target["family_code"],
                            target["is_enterprise"],
                            target["variant_name"],
                            target["order"],
                        )
                        print("🗑️  Bookmark berhasil dihapus.")
                        pause()
                else:
                    print("❌ Nomor tidak valid.")
                    pause()
            except (IndexError, ValueError):
                print("❌ Format salah. Gunakan: del <nomor>")
                pause()

        # 3. Select Bookmark
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(bookmarks):
                selected_bm = bookmarks[idx]
                
                print(f"\n🔄 Mengambil detail paket terbaru untuk '{selected_bm['variant_name']}'...")
                
                # Fetch fresh data from API to ensure validity
                family_data = get_family(
                    api_key, 
                    tokens, 
                    selected_bm["family_code"], 
                    selected_bm["is_enterprise"]
                )

                if not family_data:
                    print("❌ Gagal mengambil data paket dari server.")
                    print("   Paket mungkin sudah tidak tersedia atau koneksi bermasalah.")
                    pause()
                    continue

                # Find Option Code
                option_code = _find_option_code_in_family(
                    family_data, 
                    selected_bm["variant_name"], 
                    selected_bm["order"]
                )

                if option_code:
                    # Proceed to Package Details
                    show_package_details(
                        api_key, 
                        tokens, 
                        option_code, 
                        selected_bm["is_enterprise"]
                    )
                else:
                    print("\n⚠️  PAKET TIDAK DITEMUKAN / KADALUARSA")
                    print("   Paket ini tampaknya sudah dihapus oleh XL atau strukturnya berubah.")
                    print("   Disarankan untuk menghapus bookmark ini.")
                    
                    ask_del = input("   Hapus bookmark ini sekarang? (y/n): ").lower()
                    if ask_del == 'y':
                        BookmarkInstance.remove_bookmark(
                            selected_bm["family_code"],
                            selected_bm["is_enterprise"],
                            selected_bm["variant_name"],
                            selected_bm["order"],
                        )
                        print("🗑️  Bookmark dihapus.")
                    pause()
            else:
                print("❌ Nomor tidak ada dalam daftar.")
                pause()
        
        else:
            print("❌ Perintah tidak dikenali.")
            pause()
