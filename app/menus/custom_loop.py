import time
import logging
import traceback
from datetime import datetime

# Import Dependencies
from app.client.engsel import get_family, get_package
from app.client.purchase.redeem import settlement_bounty
from app.service.auth import AuthInstance
from app.menus.util import clear_screen, pause

# Setup Logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("CustomLoop")

WIDTH = 60

def show_custom_loop_menu():
    """
    Menu looping kustom: Pilih paket -> Redeem Voucher (Bounty) selamanya.
    Dilengkapi dengan fitur SMART COOLDOWN untuk menghindari blokir server.
    """
    api_key = AuthInstance.api_key
    
    clear_screen()
    print("=" * WIDTH)
    print("♾️  INFINITE REDEEM LOOPER (SMART COOLDOWN)".center(WIDTH))
    print("=" * WIDTH)
    family_code = input("Masukkan Family Code: ").strip()
    if not family_code: return

    print("⏳ Mengambil daftar paket...", end="\r")
    tokens = AuthInstance.get_active_tokens()
    if not tokens:
        print("❌ Sesi habis. Login ulang."); pause(); return

    data = get_family(api_key, tokens, family_code)
    if not data:
        print("❌ Gagal mengambil data family."); pause(); return

    # --- Display Variants ---
    variants = data.get("package_variants", [])
    flattened_opts = []
    counter = 1

    clear_screen()
    print("=" * WIDTH)
    print(f"FAMILY: {family_code}".center(WIDTH))
    print("=" * WIDTH)
    print(f"{'NO':<4} | {'NAMA PAKET':<35} | {'HARGA'}")
    print("-" * WIDTH)

    for var in variants:
        for opt in var.get("package_options", []):
            price = opt.get("price", 0)
            name = opt.get("name", "Unknown")[:35]
            print(f" {counter:<3} | {name:<35} | Rp {price:,}")
            flattened_opts.append({
                "id": counter, "code": opt["package_option_code"],
                "price": price, "name": name
            })
            counter += 1

    print("=" * WIDTH)
    print("INSTRUKSI:")
    print(" - Contoh input: 1, 3")
    print("-" * WIDTH)

    targets = []
    choice = input("Pilihan >> ").strip().lower()
    if choice == '0': return
    elif choice == 'all': targets = flattened_opts
    else:
        try:
            indices = [int(x.strip()) for x in choice.split(",") if x.strip().isdigit()]
            for idx in indices:
                found = next((x for x in flattened_opts if x["id"] == idx), None)
                if found: targets.append(found)
        except: print("❌ Input invalid."); pause(); return

    if not targets: print("❌ Tidak ada paket."); pause(); return

    # --- KONFIGURASI LOOP ---
    try:
        delay_normal = int(input("Delay normal antar paket (detik) [Saran: 2-5]: ").strip())
        
        print("\n--- PENGATURAN ANTI-SPAM ---")
        cooldown_trigger = int(input("Istirahat panjang setiap berapa kali SUKSES? [Saran: 3]: ").strip())
        cooldown_duration = int(input("Durasi istirahat panjang (detik) [Saran: 60-300]: ").strip())
    except ValueError:
        print("❌ Input harus angka."); pause(); return

    # --- EXECUTION LOOP ---
    clear_screen()
    print("=" * WIDTH)
    print("🚀 MEMULAI REDEEM LOOP".center(WIDTH))
    print(f"ℹ️  Mode: Istirahat {cooldown_duration}s setiap {cooldown_trigger}x Sukses")
    print("=" * WIDTH)
    
    total_success = 0
    consecutive_success = 0
    iteration = 1

    try:
        while True:
            # Cek Cooldown
            if consecutive_success >= cooldown_trigger:
                print(f"\n☕ [ANTI-SPAM] Sudah {consecutive_success}x sukses berturut-turut.")
                print(f"💤 Istirahat panjang selama {cooldown_duration} detik agar aman...")
                
                # Hitung mundur visual
                for rem in range(cooldown_duration, 0, -1):
                    print(f"   Lanjut dalam {rem}s... ", end="\r")
                    time.sleep(1)
                
                print(f"   Lanjut! {' '*20}")
                consecutive_success = 0 # Reset counter
            
            print(f"\n🔄 [Putaran ke-{iteration}] {datetime.now().strftime('%H:%M:%S')}")
            print("-" * WIDTH)
            
            # Refresh Token Auth
            current_tokens = AuthInstance.get_active_tokens()
            if not current_tokens:
                print("⚠️ Token invalid, mencoba refresh...")
                current_tokens = AuthInstance.get_active_tokens()
                if not current_tokens: break

            for target in targets:
                code = target["code"]
                pkg_name = target["name"]
                price = target["price"]
                
                print(f"🎁 Redeem: {pkg_name}...")

                try:
                    # 1. Refresh Data Paket (Wajib)
                    pkg_detail = get_package(api_key, current_tokens, code)
                    if not pkg_detail:
                        print("   ⚠️ Gagal ambil detail paket (Skip).")
                        continue
                        
                    real_token = pkg_detail.get("token_confirmation")
                    real_ts = pkg_detail.get("timestamp")
                    
                    if not real_token:
                        print("   ⚠️ Token konfirmasi kosong (Stok habis/Limit).")
                        continue

                    # 2. Eksekusi Redeem
                    res = settlement_bounty(
                        api_key=api_key,
                        tokens=current_tokens,
                        token_confirmation=real_token,
                        ts_to_sign=real_ts,
                        payment_target=code,
                        price=price,
                        item_name=pkg_name
                    )
                    
                    if res and res.get("status") == "SUCCESS":
                        print(f"   ✅ SUKSES REDEEM!")
                        total_success += 1
                        consecutive_success += 1
                    else:
                        msg = res.get("message", "Unknown Error") if res else "No Response"
                        print(f"   ❌ GAGAL: {msg}")
                        # Opsional: Jika gagal, apakah reset consecutive_success?
                        # Biasanya tidak perlu, karena limit dihitung dari transaksi sukses.
                        
                except Exception as e:
                    print(f"   ❌ ERROR: {e}")

                # Jeda normal antar paket
                if delay_normal > 0:
                    time.sleep(delay_normal)

            iteration += 1
            
            # Jeda antar putaran (jika paket habis diloop)
            # Jika delay_normal sudah cukup, ini bisa dinolkan atau kecil saja
            if delay_normal > 0:
                print(f"⏳ Jeda putaran {delay_normal}s...")
                time.sleep(delay_normal)

    except KeyboardInterrupt:
        print(f"\n\n🛑 BERHENTI. Total Sukses: {total_success}")
        pause()
    except Exception as e:
        print(f"\n❌ CRITICAL ERROR: {e}")
        traceback.print_exc()
        pause()
