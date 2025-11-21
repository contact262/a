import sys
import json
import logging
import traceback
from datetime import datetime
from dotenv import load_dotenv

# Load Environment Variables
load_dotenv()

# Import Internal Modules
from app.service.git import check_for_updates
from app.menus.util import clear_screen, pause
from app.client.engsel import get_balance, get_tiering_info
from app.client.famplan import validate_msisdn
from app.menus.payment import show_transaction_history
from app.service.auth import AuthInstance
from app.menus.bookmark import show_bookmark_menu
from app.menus.account import show_account_menu
from app.menus.package import fetch_my_packages, get_packages_by_family, show_package_details
from app.menus.hot import show_hot_menu, show_hot_menu2
from app.service.sentry import enter_sentry_mode
from app.menus.purchase import purchase_by_family
from app.menus.famplan import show_family_info
from app.menus.circle import show_circle_info
from app.menus.notification import show_notification_menu
from app.menus.store.segments import show_store_segments_menu
from app.menus.store.search import show_family_list_menu, show_store_packages_menu
from app.menus.store.redemables import show_redeemables_menu
from app.client.registration import dukcapil

# Import Modul Baru
from app.menus.custom_loop import show_custom_loop_menu

# =============================================================================
# CONFIGURATION & LOGGING
# =============================================================================

WIDTH = 60
VERSION = "2.6.0-Stable"

# Setup Logging (File & Stream)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler("app.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("MainApp")

# =============================================================================
# HELPER FUNCTIONS (INPUT & UI)
# =============================================================================

def get_input_str(prompt: str) -> str:
    """Mendapatkan input string yang sudah dibersihkan."""
    return input(prompt).strip()

def get_input_int(prompt: str, default: int = None) -> int:
    """Mendapatkan input integer dengan error handling."""
    while True:
        raw = input(prompt).strip()
        if not raw and default is not None:
            return default
        if raw.lower() == 'q': return -1 # Escape code
        try:
            return int(raw)
        except ValueError:
            print("❌ Input harus berupa angka.")

def get_input_bool(prompt: str) -> bool:
    """Mendapatkan input boolean (y/n)."""
    return input(prompt).strip().lower() == 'y'

def show_header(profile: dict):
    """Menampilkan header dashboard user."""
    clear_screen()
    print("=" * WIDTH)
    print(f"MYXL TERMINAL v{VERSION}".center(WIDTH))
    print("=" * WIDTH)
    
    # Format Tanggal Expired
    exp_date = "Unknown"
    if profile.get("balance_expired_at"):
        try:
            ts = float(profile["balance_expired_at"])
            if ts > 1000000000000: ts /= 1000 # Handle millis
            exp_date = datetime.fromtimestamp(ts).strftime("%d %b %Y")
        except: pass

    # Baris 1: Identitas
    print(f" 📱 {profile['number']} ({profile['subscription_type']})".center(WIDTH))
    
    # Baris 2: Keuangan
    bal_str = f"Rp {profile['balance']:,}" if isinstance(profile['balance'], (int, float)) else str(profile['balance'])
    print(f" 💰 {bal_str} | Exp: {exp_date}".center(WIDTH))
    
    # Baris 3: Loyalty
    print(f" 🌟 {profile['point_info']}".center(WIDTH))
    print("=" * WIDTH)

def print_menu():
    """Menampilkan daftar menu."""
    menu_items = [
        ("1", "Login / Ganti Akun"),
        ("2", "Lihat Paket Saya"),
        ("3", "Beli Paket 🔥 HOT 🔥"),
        ("4", "Beli Paket 🔥 HOT-2 🔥"),
        ("5", "Beli Paket (Option Code)"),
        ("6", "Lihat Family (Family Code)"),
        ("7", "Beli Semua di Family (Loop)"),
        ("8", "Riwayat Transaksi"),
        ("9", "Family Plan Organizer"),
        ("10", "Circle Organizer"),
        ("11", "Store Segments"),
        ("12", "Store Family List"),
        ("13", "Store Packages (Cari Paket)"),
        ("14", "Redeemables (Voucher/Bonus)"),
        ("15", "Custom Loop / Bomber (Menu Baru) 🔥"), # NEW FEATURE
        ("R", "Registrasi Kartu (Dukcapil)"),
        ("N", "Notifikasi"),
        ("V", "Validasi MSISDN"),
        ("S", "Sentry Mode (Monitoring)"),
        ("00", "Bookmark Paket"),
        ("99", "Keluar")
    ]
    
    print("MENU UTAMA:")
    # Tampilkan 2 kolom agar hemat tempat
    half = (len(menu_items) + 1) // 2
    for i in range(half):
        col1 = menu_items[i]
        print(f" [{col1[0]:>2}] {col1[1]:<30}", end="")
        
        if i + half < len(menu_items):
            col2 = menu_items[i + half]
            print(f"| [{col2[0]:>2}] {col2[1]}")
        else:
            print()
    print("-" * WIDTH)

# =============================================================================
# CORE LOGIC
# =============================================================================

def handle_menu_selection(choice: str, active_user: dict):
    """Menangani logika pemilihan menu."""
    api_key = AuthInstance.api_key
    tokens = active_user["tokens"]
    
    try:
        if choice == "1":
            selected = show_account_menu()
            if selected: AuthInstance.set_active_user(selected)
            
        elif choice == "2":
            fetch_my_packages()
            
        elif choice == "3":
            show_hot_menu()
            
        elif choice == "4":
            show_hot_menu2()
            
        elif choice == "5":
            code = get_input_str("Masukkan Option Code: ")
            if code: show_package_details(api_key, tokens, code, False)
            
        elif choice == "6":
            code = get_input_str("Masukkan Family Code: ")
            if code: get_packages_by_family(code)
            
        elif choice == "7":
            fam_code = get_input_str("Masukkan Family Code: ")
            if fam_code:
                start_opt = get_input_int("Mulai dari urutan ke (default 1): ", 1)
                use_decoy = get_input_bool("Gunakan Decoy/Pancingan? (y/n): ")
                pause_ok = get_input_bool("Pause jika sukses? (y/n): ")
                delay = get_input_int("Delay (detik): ", 0)
                
                purchase_by_family(fam_code, use_decoy, pause_ok, delay, start_opt)
                
        elif choice == "8":
            show_transaction_history(api_key, tokens)
            
        elif choice == "9":
            show_family_info(api_key, tokens)
            
        elif choice == "10":
            show_circle_info(api_key, tokens)
            
        elif choice == "11":
            is_ent = get_input_bool("Is Enterprise? (y/n): ")
            show_store_segments_menu(is_ent)
            
        elif choice == "12":
            is_ent = get_input_bool("Is Enterprise? (y/n): ")
            show_family_list_menu(active_user['subscription_type'], is_ent)
            
        elif choice == "13":
            is_ent = get_input_bool("Is Enterprise? (y/n): ")
            show_store_packages_menu(active_user['subscription_type'], is_ent)
            
        elif choice == "14":
            is_ent = get_input_bool("Is Enterprise? (y/n): ")
            show_redeemables_menu(is_ent)

        elif choice == "15":
            # FITUR BARU: CUSTOM LOOP
            show_custom_loop_menu()
            
        elif choice == "00":
            show_bookmark_menu()
            
        elif choice == "99":
            print("👋 Sampai Jumpa!")
            sys.exit(0)
            
        elif choice.lower() == "r":
            msisdn = get_input_str("MSISDN (628...): ")
            nik = get_input_str("NIK: ")
            kk = get_input_str("KK: ")
            if msisdn and nik and kk:
                res = dukcapil(api_key, msisdn, kk, nik)
                print(json.dumps(res, indent=2))
                pause()
                
        elif choice.lower() == "v":
            msisdn = get_input_str("MSISDN Target: ")
            if msisdn:
                res = validate_msisdn(api_key, tokens, msisdn)
                print(json.dumps(res, indent=2))
                pause()
                
        elif choice.lower() == "n":
            show_notification_menu()
            
        elif choice.lower() == "s":
            enter_sentry_mode()
            
        elif choice.lower() == "t": # Test shortcut
            pause()
            
        else:
            print("⚠️ Pilihan tidak valid.")
            pause()
            
    except Exception as e:
        logger.error(f"Error in menu handler: {e}")
        print(f"\n❌ Terjadi kesalahan pada menu: {e}")
        traceback.print_exc()
        pause()

def main():
    while True:
        try:
            active_user = AuthInstance.get_active_user()

            # --- STATE: LOGGED OUT ---
            if not active_user:
                clear_screen()
                print("=" * WIDTH)
                print("MYXL TERMINAL - SILAHKAN LOGIN".center(WIDTH))
                print("=" * WIDTH)
                selected = show_account_menu()
                if selected:
                    AuthInstance.set_active_user(selected)
                else:
                    # Jika user membatalkan/keluar dari menu akun tanpa login
                    print("Tidak ada user dipilih.")
                    retry = input("Coba lagi? (y/n): ").lower()
                    if retry != 'y':
                        sys.exit(0)
                continue

            # --- STATE: LOGGED IN ---
            
            # 1. Fetch Data (Fail-Safe)
            balance_val = "N/A"
            expired_val = None
            point_str = "Points: - | Tier: -"
            
            try:
                bal_data = get_balance(AuthInstance.api_key, active_user["tokens"]["id_token"])
                if bal_data:
                    balance_val = bal_data.get("remaining", 0)
                    expired_val = bal_data.get("expired_at")
            except Exception as e:
                logger.warning(f"Failed fetch balance: {e}")

            if active_user.get("subscription_type") == "PREPAID":
                try:
                    tier_data = get_tiering_info(AuthInstance.api_key, active_user["tokens"])
                    if tier_data:
                        point_str = f"Points: {tier_data.get('current_point',0)} | Tier: {tier_data.get('tier',0)}"
                except Exception as e:
                    logger.warning(f"Failed fetch tier: {e}")

            # 2. Build Profile Data
            profile = {
                "number": active_user["number"],
                "subscriber_id": active_user.get("subscriber_id", "-"),
                "subscription_type": active_user.get("subscription_type", "UNKNOWN"),
                "balance": balance_val,
                "balance_expired_at": expired_val,
                "point_info": point_str
            }

            # 3. Render & Interact
            show_header(profile)
            print_menu()
            
            choice = input("Pilihan >> ").strip()
            handle_menu_selection(choice, active_user)

        except KeyboardInterrupt:
            print("\n\n🛑 Aplikasi dihentikan pengguna.")
            sys.exit(0)
        except Exception as e:
            logger.critical(f"Critical Loop Error: {e}")
            print(f"Critical Error: {e}")
            pause()

if __name__ == "__main__":
    try:
        print("🔍 Memeriksa pembaruan script...")
        if check_for_updates():
            print("Update ditemukan. Silahkan restart jika diperlukan.")
            pause()
        main()
    except Exception as e:
        print(f"Fatal Boot Error: {e}")