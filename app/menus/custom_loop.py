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
    Tanpa Decoy. Murni Redeem.
    """
    api_key = AuthInstance.api_key
    
    # 1. Input Family Code
    clear_screen()
    print("=" * WIDTH)
    print("♾️  INFINITE REDEEM LOOPER (NO DECOY)".center(WIDTH))
    print("=" * WIDTH)
    family_code = input("Masukkan Family Code: ").strip()
    
    if not family_code:
        return

    # 2. Fetch Data
    print("⏳ Mengambil daftar paket...", end="\r")
    tokens = AuthInstance.get_active_tokens()
    if not tokens:
        print("❌ Sesi habis. Login ulang.")
        pause()
        return

    data = get_family(api_key, tokens, family_code)
    if not data:
        print("❌ Gagal mengambil data family.")
        pause()
        return

    # 3. Tampilkan Daftar Paket
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
                "id": counter,
                "code": opt["package_option_code"],
                "price": price,
                "name": name
            })
            counter += 1

    print("=" * WIDTH)
    print("INSTRUKSI:")
    print(" - Pilih nomor paket untuk di-redeem terus menerus.")
    print(" - Contoh input: 1, 3 (untuk redeem paket no 1 dan 3)")
    print(" - Ketik '0' untuk batal.")
    print("-" * WIDTH)

    # 4. Seleksi Paket
    targets = []
    choice = input("Pilihan >> ").strip().lower()

    if choice == '0':
        return
    elif choice == 'all':
        targets = flattened_opts
    else:
        try:
            indices = [int(x.strip()) for x in choice.split(",") if x.strip().isdigit()]
            for idx in indices:
                found = next((x for x in flattened_opts if x["id"] == idx), None)
                if found:
                    targets.append(found)
        except Exception:
            print("❌ Input tidak valid.")
            pause()
            return

    if not targets:
        print("❌ Tidak ada paket yang dipilih.")
        pause()
        return

    print(f"\n✅ {len(targets)} paket terpilih untuk di-redeem.")
    
    # 5. Konfigurasi Loop
    try:
        delay = int(input("Delay antar redeem (detik): ").strip())
    except ValueError:
        print("❌ Input harus angka.")
        pause()
        return

    # 6. EXECUTION LOOP (REDEEM MODE)
    clear_screen()
    print("=" * WIDTH)
    print("🚀 MEMULAI REDEEM LOOP (Tekan Ctrl+C untuk stop)".center(WIDTH))
    print("=" * WIDTH)
    
    iteration = 1
    try:
        while True:
            print(f"\n🔄 [Putaran ke-{iteration}] {datetime.now().strftime('%H:%M:%S')}")
            print("-" * WIDTH)
            
            # Auto-Refresh Token
            current_tokens = AuthInstance.get_active_tokens()
            if not current_tokens:
                print("⚠️  Token invalid, mencoba refresh...")
                current_tokens = AuthInstance.get_active_tokens()
                if not current_tokens:
                    print("❌ Gagal refresh token. Berhenti.")
                    break

            for target in targets:
                code = target["code"]
                pkg_name = target["name"]
                price = target["price"]
                
                print(f"🎁 Redeem: {pkg_name}...")

                # PENTING: Fetch detail paket dulu untuk dapat token_confirmation & timestamp terbaru
                # Tanpa ini, redeem looping akan gagal di putaran kedua karena token expired.
                try:
                    pkg_detail = get_package(api_key, current_tokens, code)
                    if not pkg_detail:
                        print("   ⚠️ Gagal ambil detail paket (Skip).")
                        continue
                        
                    real_token = pkg_detail.get("token_confirmation")
                    real_ts = pkg_detail.get("timestamp")
                    
                    # Eksekusi Redeem (Settlement Bounty)
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
                    else:
                        msg = res.get("message", "Unknown Error") if res else "No Response"
                        print(f"   ❌ GAGAL: {msg}")
                        
                except Exception as e:
                    print(f"   ❌ ERROR: {e}")

                # Jeda kecil antar paket agar tidak flood
                time.sleep(1) 

            print("-" * WIDTH)
            print(f"💤 Istirahat {delay} detik...")
            time.sleep(delay)
            iteration += 1

    except KeyboardInterrupt:
        print("\n\n🛑 LOOP DIHENTIKAN PENGGUNA.")
        pause()
    except Exception as e:
        print(f"\n❌ CRITICAL ERROR: {e}")
        traceback.print_exc()
        pause()