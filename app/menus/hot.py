import json
import os
from app.client.engsel import get_family, get_package_details, get_package
from app.menus.package import show_package_details
from app.service.auth import AuthInstance
from app.menus.util import clear_screen, pause, display_html, format_quota_byte
from app.client.purchase.ewallet import show_multipayment
from app.client.purchase.qris import show_qris_payment
from app.client.purchase.balance import settlement_balance
from app.type_dict import PaymentItem

WIDTH = 60

def _load_json_safe(filepath):
    """Helper untuk memuat file JSON dengan aman."""
    if not os.path.exists(filepath):
        print(f"❌ File data tidak ditemukan: {filepath}")
        return []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        print(f"❌ File rusak/bukan JSON valid: {filepath}")
        return []
    except Exception as e:
        print(f"❌ Error membaca file: {e}")
        return []

def show_hot_menu():
    """Menu untuk paket Hot (Versi 1)."""
    api_key = AuthInstance.api_key
    tokens = AuthInstance.get_active_tokens()
    
    while True:
        clear_screen()
        print("=" * WIDTH)
        print("🔥 PAKET HOT & PROMO 🔥".center(WIDTH))
        print("=" * WIDTH)
        
        hot_packages = _load_json_safe("hot_data/hot.json")
        if not hot_packages:
            print("  [Data paket kosong]")
            pause()
            return

        for idx, p in enumerate(hot_packages):
            print(f"{idx + 1}. {p.get('family_name', '?')} - {p.get('option_name', '?')}")
        
        print("-" * WIDTH)
        print("[00] Kembali")
        
        choice = input("Pilih Paket >> ").strip()
        if choice == "00":
            return
            
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(hot_packages):
                selected = hot_packages[idx]
                _process_hot_package(api_key, tokens, selected)
            else:
                print("⚠️ Nomor tidak valid.")
                pause()
        else:
            print("⚠️ Input harus angka.")
            pause()

def _process_hot_package(api_key, tokens, selected_bm):
    """Memproses pemilihan paket dari menu Hot 1."""
    print("⏳ Mengambil detail paket...")
    
    family_code = selected_bm.get("family_code")
    is_enterprise = selected_bm.get("is_enterprise", False)
    
    family_data = get_family(api_key, tokens, family_code, is_enterprise)
    if not family_data:
        print("❌ Gagal mengambil data family.")
        pause()
        return

    # Cari option code berdasarkan nama varian dan order
    target_variant = selected_bm.get("variant_name")
    target_order = selected_bm.get("order")
    
    found_code = None
    
    for variant in family_data.get("package_variants", []):
        if variant.get("name") == target_variant or not target_variant: 
            for opt in variant.get("package_options", []):
                if opt.get("order") == target_order:
                    found_code = opt.get("package_option_code")
                    break
        if found_code: break
    
    if found_code:
        show_package_details(api_key, tokens, found_code, is_enterprise)
    else:
        print(f"❌ Paket spesifik tidak ditemukan dalam family {family_code}.")
        print(f"   Target: {target_variant} | Order: {target_order}")
        pause()

def show_hot_menu2():
    """Menu untuk paket Hot V2 (Advanced Config)."""
    api_key = AuthInstance.api_key
    tokens = AuthInstance.get_active_tokens()
    
    while True:
        clear_screen()
        print("=" * WIDTH)
        print("🔥 PAKET HOT V2 (BUNDLING/CUSTOM) 🔥".center(WIDTH))
        print("=" * WIDTH)
        
        hot_packages = _load_json_safe("hot_data/hot2.json")
        if not hot_packages:
            print("  [Data paket kosong]")
            pause()
            return

        for idx, p in enumerate(hot_packages):
            print(f"{idx + 1}. {p.get('name', 'Unnamed')}")
            print(f"   🏷️  {p.get('price', 'N/A')}")
            print("-" * WIDTH)
        
        print("[00] Kembali")
        
        choice = input("Pilih Paket >> ").strip()
        if choice == "00":
            return
            
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(hot_packages):
                _process_hot2_package(api_key, tokens, hot_packages[idx])
            else:
                print("⚠️ Nomor tidak valid.")
                pause()
        else:
            print("⚠️ Input harus angka.")
            pause()

def _process_hot2_package(api_key, tokens, package_config):
    """Memproses logika pembelian kompleks Hot V2."""
    packages_list = package_config.get("packages", [])
    if not packages_list:
        print("⚠️ Konfigurasi paket ini kosong.")
        pause()
        return

    print("⏳ Menyiapkan item pembayaran...")
    payment_items = []
    
    # Kita ambil detail paket pertama untuk ditampilkan sebagai "Info Utama"
    main_detail = None
    # Simpan family code dari config untuk ditampilkan
    fam_code_display = packages_list[0]["family_code"]
    
    try:
        for pkg_cfg in packages_list:
            detail = get_package_details(
                api_key, tokens,
                pkg_cfg["family_code"], pkg_cfg["variant_code"], pkg_cfg["order"],
                pkg_cfg["is_enterprise"], pkg_cfg["migration_type"]
            )
            
            if not detail:
                raise Exception(f"Gagal ambil detail: {pkg_cfg['family_code']}")
                
            if not main_detail:
                main_detail = detail
                
            payment_items.append(PaymentItem(
                item_code=detail["package_option"]["package_option_code"],
                product_type="",
                item_price=detail["package_option"]["price"],
                item_name=detail["package_option"]["name"],
                tax=0,
                token_confirmation=detail["token_confirmation"]
            ))
    except Exception as e:
        print(f"❌ Error saat persiapan: {e}")
        pause()
        return

    # Tampilkan Info Paket
    clear_screen()
    print("=" * WIDTH)
    print(f"📦 {package_config.get('name')}".center(WIDTH))
    print("=" * WIDTH)
    print(f"📝 Deskripsi:\n{package_config.get('detail')}")
    print("-" * WIDTH)
    
    # Tampilkan info teknis dari paket utama
    pkg_opt = main_detail.get("package_option", {})
    
    # --- FIX: Tampilkan Code Teknis ---
    print(f"Family Code : {fam_code_display}")
    print(f"Option Code : {pkg_opt.get('package_option_code')}")
    print(f"Masa Aktif  : {pkg_opt.get('validity')}")
    print(f"Total Harga : {package_config.get('price')} (Estimasi)")
    
    print("\nBenefits Lengkap:")
    # --- FIX: Hapus Limit [:3] & Format Quota ---
    for b in pkg_opt.get("benefits", []): 
        b_name = b.get('name', 'Benefit')
        b_type = b.get('data_type', 'OTHER')
        b_total = b.get('total', 0)
        
        info_str = ""
        if b_type == "DATA":
            info_str = format_quota_byte(b_total) # Fix Quota Byte
        elif b_type == "VOICE":
            info_str = f"{b_total/60:.1f} Menit"
        elif b_type == "TEXT":
            info_str = f"{b_total} SMS"
        else:
            info_str = f"{b_total}" # Apps/Unit lain
            
        unlimited_tag = " [UNLIMITED]" if b.get("is_unlimited") else ""
        print(f" • {b_name:<25} : {info_str}{unlimited_tag}")
        
    print("=" * WIDTH)
    
    # Konfigurasi Pembayaran
    payment_for = package_config.get("payment_for", "BUY_PACKAGE")
    overwrite_amt = package_config.get("overwrite_amount", -1)
    ask_overwrite = package_config.get("ask_overwrite", False)
    
    while True:
        print("\nMETODE PEMBAYARAN:")
        print(" [1] Pulsa Utama")
        print(" [2] E-Wallet")
        print(" [3] QRIS")
        print(" [0] Batal")
        
        method = input(">> ").strip()
        
        if method == "0":
            return
        elif method == "1":
            if overwrite_amt == -1 and not ask_overwrite:
                # Safety check untuk pulsa
                print("⚠️ PERINGATAN: Pastikan pulsa cukup!")
                if input("Lanjut? (y/n): ").lower() != 'y': continue
            
            settlement_balance(
                api_key, tokens, payment_items, payment_for,
                ask_overwrite, overwrite_amount=overwrite_amt,
                token_confirmation_idx=package_config.get("token_confirmation_idx", 0),
                amount_idx=package_config.get("amount_idx", -1)
            )
            pause()
            return
        elif method == "2":
            show_multipayment(
                api_key, tokens, payment_items, payment_for,
                ask_overwrite, overwrite_amount=overwrite_amt,
                token_confirmation_idx=package_config.get("token_confirmation_idx", 0),
                amount_idx=package_config.get("amount_idx", -1)
            )
            pause()
            return
        elif method == "3":
            show_qris_payment(
                api_key, tokens, payment_items, payment_for,
                ask_overwrite, overwrite_amount=overwrite_amt,
                token_confirmation_idx=package_config.get("token_confirmation_idx", 0),
                amount_idx=package_config.get("amount_idx", -1)
            )
            pause()
            return
        else:
            print("⚠️ Pilihan salah.")
