import logging
import re
from typing import Optional, Tuple

# Import dependencies internal
from app.client.ciam import get_otp, submit_otp
from app.menus.util import clear_screen, pause
from app.service.auth import AuthInstance

# Setup Logger
logger = logging.getLogger(__name__)

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def validate_phone_number(phone_input: str) -> Optional[str]:
    """
    Membersihkan dan menormalisasi nomor telepon ke format 628xxx.
    Menerima: 0812..., 62812..., +62 812...
    """
    # Hapus semua karakter non-digit
    clean_number = re.sub(r'\D', '', phone_input)
    
    # Normalisasi awalan
    if clean_number.startswith("08"):
        clean_number = "62" + clean_number[1:]
    elif clean_number.startswith("8"):
        clean_number = "62" + clean_number
        
    # Validasi format akhir
    if not clean_number.startswith("628"):
        return None
    
    if len(clean_number) < 10 or len(clean_number) > 15:
        return None
        
    return clean_number

# =============================================================================
# CORE FUNCTIONS
# =============================================================================

def login_prompt(api_key: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Menangani alur login lengkap: Input Nomor -> Request OTP -> Submit OTP.
    """
    clear_screen()
    print("=" * 50)
    print("LOGIN SYSTEM - MYXL".center(50))
    print("=" * 50)
    
    try:
        # 1. Input Nomor
        raw_number = input("Masukkan Nomor XL (misal: 0812...): ").strip()
        phone_number = validate_phone_number(raw_number)

        if not phone_number:
            print("❌ Format nomor tidak valid.")
            return None, None

        # 2. Request OTP
        print(f"\n🔄 Meminta kode OTP untuk {phone_number}...")
        try:
            subscriber_id = get_otp(phone_number)
            if not subscriber_id:
                print("❌ Gagal meminta OTP. Coba lagi nanti.")
                return None, None
        except Exception as e:
            logger.error(f"Error requesting OTP: {e}")
            print("❌ Terjadi kesalahan koneksi.")
            return None, None
            
        print("✅ OTP Berhasil dikirim via SMS.")
        print("-" * 50)
        
        # 3. Submit OTP (Retry Loop)
        max_retries = 3
        for i in range(max_retries):
            otp = input(f"Masukkan 6 digit OTP ({max_retries - i} kesempatan): ").strip()
            
            if not otp.isdigit() or len(otp) != 6:
                print("⚠️ OTP harus berupa 6 digit angka.")
                continue
            
            print("🔄 Memverifikasi...")
            tokens = submit_otp(api_key, "SMS", phone_number, otp)
            
            if tokens:
                print("\n✅ LOGIN BERHASIL!")
                return phone_number, tokens.get("refresh_token")
            
            print("❌ Kode OTP salah.")

        print("\n⛔ Gagal login: Kesempatan habis.")
        return None, None
        
    except KeyboardInterrupt:
        print("\n⚠️ Login dibatalkan.")
        return None, None
    except Exception as e:
        logger.error(f"Critical Login Error: {e}")
        print("\n❌ Sistem Error.")
        return None, None

def show_account_menu():
    """
    Menu Manajemen Akun Interaktif.
    """
    # Initial Load
    AuthInstance.load_tokens()
    
    while True:
        clear_screen()
        # Refresh state setiap kali render menu
        users = AuthInstance.refresh_tokens
        active_user = AuthInstance.get_active_user()
        active_number = str(active_user["number"]) if active_user else ""

        print("=" * 55)
        print("MANAJEMEN AKUN".center(55))
        print("=" * 55)
        
        if not users:
            print("   [ ⚠️  BELUM ADA AKUN TERSIMPAN ]")
            print("   Silahkan tambah akun terlebih dahulu.")
        else:
            print(f"{'NO':<4} | {'NOMOR':<16} | {'STATUS':<10} | {'TIPE'}")
            print("-" * 55)
            
            for idx, user in enumerate(users):
                u_num = str(user.get("number", ""))
                is_active = (u_num == active_number)
                
                # Visual Indicators
                marker = "🟢 AKTIF" if is_active else "⚪"
                sub_type = user.get("subscription_type", "PREPAID")[:8]
                
                print(f"{idx + 1:<4} | {u_num:<16} | {marker:<10} | {sub_type}")
        
        print("=" * 55)
        print("PERINTAH:")
        print(" [0]      Tambah Akun Baru")
        print(" [1-9]    Pilih/Ganti Akun (sesuai nomor urut)")
        print(" [del X]  Hapus Akun nomor urut X (contoh: del 1)")
        print(" [00]     Kembali ke Menu Utama")
        print("-" * 55)
        
        choice = input("Pilihan >> ").strip().lower()
        
        # --- LOGIC HANDLER ---
        
        if choice == "00":
            return active_number if active_number else None
            
        elif choice == "0":
            # Add New Account
            res_number, res_token = login_prompt(AuthInstance.api_key)
            if res_number and res_token:
                AuthInstance.add_refresh_token(int(res_number), res_token)
                AuthInstance.set_active_user(int(res_number)) # Auto switch ke yg baru
                print(f"✅ Akun {res_number} berhasil ditambahkan dan diaktifkan.")
                pause()
            else:
                pause()
                
        elif choice.startswith("del"):
            # Delete Account
            try:
                parts = choice.split()
                if len(parts) != 2 or not parts[1].isdigit():
                    raise ValueError
                
                idx = int(parts[1]) - 1
                if idx < 0 or idx >= len(users):
                    print("❌ Nomor urut tidak valid.")
                    pause()
                    continue
                
                target_user = users[idx]
                target_num = target_user['number']
                
                # Prevent deleting active user
                if str(target_num) == active_number:
                    print("⚠️  TIDAK BISA MENGHAPUS AKUN YANG SEDANG AKTIF!")
                    print("    Silahkan ganti ke akun lain terlebih dahulu.")
                else:
                    confirm = input(f"❓ Hapus akun {target_num}? (y/n): ").lower()
                    if confirm == 'y':
                        AuthInstance.remove_refresh_token(target_num)
                        print("🗑️  Akun berhasil dihapus.")
                    else:
                        print("Pembatalan.")
                        
            except ValueError:
                print("❌ Format salah. Gunakan: del <nomor_urut>")
            pause()
            
        elif choice.isdigit():
            # Switch Account
            idx = int(choice) - 1
            if 0 <= idx < len(users):
                target_user = users[idx]
                target_num = target_user['number']
                
                if str(target_num) == active_number:
                    print("ℹ️  Akun ini sudah aktif.")
                else:
                    success = AuthInstance.set_active_user(target_num)
                    if success:
                        print(f"✅ Berhasil beralih ke akun {target_num}")
                    else:
                        print("❌ Gagal beralih akun. Coba login ulang.")
            else:
                print("❌ Nomor urut tidak ditemukan.")
            pause()
            
        else:
            print("❌ Perintah tidak dikenali.")
            pause()

# =============================================================================
# LEGACY COMPATIBILITY
# =============================================================================
def show_login_menu():
    """Wrapper untuk kompatibilitas jika masih ada yang memanggil fungsi ini"""
    login_prompt(AuthInstance.api_key)
