import json
import sys
import time
import traceback  # MODULE WAJIB UNTUK MENCEGAH FORCE CLOSE
import logging

# Setup Logger Sederhana
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("PackageMenu")

from datetime import datetime
from random import randint

from app.service.auth import AuthInstance
from app.client.engsel import get_family, get_package, get_addons, get_package_details, send_api_request, unsubscribe
from app.service.bookmark import BookmarkInstance
from app.client.purchase.redeem import settlement_bounty, settlement_loyalty, bounty_allotment
from app.menus.util import clear_screen, pause, display_html, format_quota_byte
from app.client.purchase.qris import show_qris_payment
from app.client.purchase.ewallet import show_multipayment
from app.client.purchase.balance import settlement_balance
from app.type_dict import PaymentItem
from app.menus.purchase import purchase_n_times_by_option_code
from app.service.decoy import DecoyInstance

WIDTH = 60

def _print_kv(key, value):
    """Helper untuk print key-value yang rapi."""
    print(f"{key:<25}: {value}")

def _prepare_decoy_items(main_payment_items, decoy_type="balance"):
    """Helper cerdas untuk menyiapkan item pembayaran dengan decoy."""
    try:
        decoy = DecoyInstance.get_decoy(decoy_type)
        api_key = AuthInstance.api_key
        tokens = AuthInstance.get_active_tokens()
        
        if not decoy or "option_code" not in decoy:
            print("❌ Konfigurasi decoy tidak valid.")
            return None, 0

        decoy_pkg = get_package(api_key, tokens, decoy["option_code"])
        
        if not decoy_pkg:
            print("❌ Gagal memuat paket decoy. Pastikan konfigurasi benar.")
            return None, 0

        pkg_opt = decoy_pkg.get("package_option", {})
        decoy_item = PaymentItem(
            item_code=pkg_opt.get("package_option_code", ""),
            product_type="",
            item_price=pkg_opt.get("price", 0),
            item_name=pkg_opt.get("name", "Decoy Item"),
            tax=0,
            token_confirmation=decoy_pkg.get("token_confirmation", ""),
        )
        
        new_items = main_payment_items.copy()
        new_items.append(decoy_item)
        
        return new_items, pkg_opt.get("price", 0)
    except Exception as e:
        logger.error(f"Error preparing decoy: {e}")
        return None, 0

def show_package_details(api_key, tokens, package_option_code, is_enterprise, option_order = -1):
    """Menampilkan detail paket dengan tampilan yang profesional dan opsi lengkap."""
    try:
        clear_screen()
        print("⏳ Memuat detail paket...")
        package = get_package(api_key, tokens, package_option_code)
        
        if not package:
            print("❌ Gagal mengambil data paket (Mungkin paket Bonus/Legacy).")
            pause()
            return False

        pkg_opt = package.get("package_option", {})
        pkg_fam = package.get("package_family", {})
        pkg_var = package.get("package_detail_variant", {})
        pkg_addon = package.get("package_addon", {})
        
        price = pkg_opt.get("price", 0)
        validity = pkg_opt.get("validity", "N/A")
        option_name = pkg_opt.get("name", "N/A")
        family_name = pkg_fam.get("name", "N/A")
        variant_name = pkg_var.get("name", "N/A")
        
        family_code = pkg_fam.get("package_family_code", "N/A")
        parent_code = pkg_addon.get("parent_code") if pkg_addon.get("parent_code") else "N/A"
        
        full_title = f"{family_name} - {variant_name} - {option_name}"
        
        main_item = PaymentItem(
            item_code=package_option_code,
            product_type="",
            item_price=price,
            item_name=f"{variant_name} {option_name}".strip(),
            tax=0,
            token_confirmation=package.get("token_confirmation", ""),
        )
        payment_items = [main_item]
        payment_for = pkg_fam.get("payment_for", "BUY_PACKAGE") or "BUY_PACKAGE"

        clear_screen()
        print("=" * WIDTH)
        print(full_title.center(WIDTH))
        print("=" * WIDTH)
        
        _print_kv("Harga", f"Rp {price:,}")
        _print_kv("Masa Aktif", validity)
        _print_kv("Tipe Pembayaran", payment_for)
        _print_kv("Plan Type", pkg_fam.get("plan_type", "N/A"))
        print("-" * WIDTH)
        _print_kv("Family Code", family_code)
        _print_kv("Parent Code", parent_code)
        print("-" * WIDTH)
        
        benefits = pkg_opt.get("benefits", [])
        if benefits:
            print("KEUNTUNGAN PAKET:")
            for b in benefits:
                b_name = b.get('name', 'Benefit')
                b_type = b.get('data_type', 'OTHER')
                b_total = b.get('total', 0)
                
                name_lower = b_name.lower()
                info_str = ""
                
                if b_type == "DATA" or "kuota" in name_lower or "internet" in name_lower:
                    info_str = format_quota_byte(b_total)
                elif b_type == "VOICE":
                    info_str = f"{b_total/60:.1f} Menit"
                elif b_type == "TEXT":
                    info_str = f"{b_total} SMS"
                else:
                    if isinstance(b_total, (int, float)) and b_total > 1048576:
                        info_str = format_quota_byte(b_total)
                    else:
                        info_str = f"{b_total}"
                    
                unlimited_tag = " [UNLIMITED]" if b.get("is_unlimited") else ""
                print(f" • {b_name:<25} : {info_str}{unlimited_tag}")
        
        print("-" * WIDTH)
        addons = get_addons(api_key, tokens, package_option_code)
        if addons and (addons.get("bonuses") or addons.get("addons")):
             print(" (Tersedia Bonus/Addons tambahan)")
             print("-" * WIDTH)

        # --- FIX S&K TERPOTONG ---
        tnc = display_html(pkg_opt.get("tnc", ""))
        print("Syarat & Ketentuan:")
        # Tidak lagi dipotong dengan [:300]
        print(tnc if tnc else "(Tidak ada deskripsi.)")
        print("=" * WIDTH)

        while True:
            print("\nMETODE PEMBELIAN:")
            print(" [1] Pulsa (Normal)")
            print(" [2] E-Wallet (DANA, OVO, Shopee, GoPay)")
            print(" [3] QRIS (Scan)")
            print("-" * 20 + " ADVANCED / TRICK " + "-" * 20)
            print(" [4] Pulsa + Decoy (Bypass Limit)")
            print(" [5] Pulsa + Decoy V2 (Ghost Mode)")
            print(" [6] QRIS + Decoy (Custom Amount)")
            print(" [7] QRIS + Decoy V2 (Rp 0)")
            print(" [8] Bom Pembelian (N kali)")
            
            if option_order != -1:
                print(" [B] Bookmark Paket Ini")
                
            if payment_for == "REDEEM_VOUCHER":
                print(" [R] Redeem Voucher")
                print(" [S] Kirim Bonus (Gift)")
                print(" [L] Beli dengan Poin")
                
            print(" [0] Kembali")
            
            choice = input("\nPilihan >> ").strip().upper()
            
            # --- ANTI CRASH BLOCK ---
            try:
                if choice == "0":
                    return False
                    
                elif choice == "B" and option_order != -1:
                    success = BookmarkInstance.add_bookmark(
                        family_code=pkg_fam.get("package_family_code", ""),
                        family_name=family_name,
                        is_enterprise=is_enterprise,
                        variant_name=variant_name,
                        option_name=option_name,
                        order=option_order,
                    )
                    print("✅ Bookmark tersimpan!" if success else "⚠️ Sudah ada di bookmark.")
                    pause()

                elif choice == "1":
                    settlement_balance(api_key, tokens, payment_items, payment_for, True)
                    pause()
                    return True
                elif choice == "2":
                    show_multipayment(api_key, tokens, payment_items, payment_for, True)
                    pause()
                    return True
                elif choice == "3":
                    show_qris_payment(api_key, tokens, payment_items, payment_for, True)
                    pause()
                    return True
                
                # DECOY LOGIC START
                elif choice == "4":
                    items, decoy_price = _prepare_decoy_items(payment_items, "balance")
                    if not items: continue
                    total_overwrite = price + decoy_price
                    res = settlement_balance(api_key, tokens, items, payment_for, False, overwrite_amount=total_overwrite)
                    _handle_purchase_response(res, api_key, tokens, items, payment_for)
                    return True
                    
                elif choice == "5": # Ghost Mode
                    items, decoy_price = _prepare_decoy_items(payment_items, "balance")
                    if not items: 
                        print("❌ Gagal menyiapkan Item Decoy.")
                        pause()
                        continue
                    
                    total_overwrite = price + decoy_price
                    print(f"👻 Executing Ghost Mode (Decoy V2)...")
                    
                    # Explicitly call balance with protection
                    res = settlement_balance(
                        api_key, tokens, items, "🤫", False, 
                        overwrite_amount=total_overwrite, 
                        token_confirmation_idx=1 # Target Decoy sebagai confirmation
                    )
                    
                    # Handle result carefully
                    if res:
                        _handle_purchase_response(res, api_key, tokens, items, "🤫", token_confirmation_idx=1)
                    else:
                        print("❌ Transaksi Gagal (Return None dari Settlement).")
                        pause()
                    return True

                elif choice == "6":
                    items, decoy_price = _prepare_decoy_items(payment_items, "qris")
                    if not items: continue
                    print(f"Harga Asli: {price} | Decoy: {decoy_price}")
                    show_qris_payment(api_key, tokens, items, "SHARE_PACKAGE", True, token_confirmation_idx=1)
                    pause()
                    return True
                elif choice == "7":
                    items, decoy_price = _prepare_decoy_items(payment_items, "qris0")
                    if not items: continue
                    show_qris_payment(api_key, tokens, items, "SHARE_PACKAGE", True, token_confirmation_idx=1)
                    pause()
                    return True
                # DECOY LOGIC END

                elif choice == "8":
                    _handle_bomb_purchase(package_option_code)
                    
                elif choice == "R" and payment_for == "REDEEM_VOUCHER":
                    settlement_bounty(api_key=api_key, tokens=tokens, token_confirmation=package.get("token_confirmation"), ts_to_sign=package.get("timestamp"), payment_target=package_option_code, price=price, item_name=variant_name)
                    pause()
                    return True
                elif choice == "S" and payment_for == "REDEEM_VOUCHER":
                    dest = input("Nomor Tujuan (62...): ").strip()
                    if dest: bounty_allotment(api_key=api_key, tokens=tokens, ts_to_sign=package.get("timestamp"), destination_msisdn=dest, item_name=option_name, item_code=package_option_code, token_confirmation=package.get("token_confirmation"))
                    pause()
                    return True
                elif choice == "L" and payment_for == "REDEEM_VOUCHER":
                    settlement_loyalty(api_key=api_key, tokens=tokens, token_confirmation=package.get("token_confirmation"), ts_to_sign=package.get("timestamp"), payment_target=package_option_code, price=price)
                    pause()
                    return True
                else:
                    print("⚠️ Pilihan tidak valid.")
                    pause()
                    
            except Exception as e:
                # INI YANG MENCEGAH KEPENTAL
                print("\n" + "!"*50)
                print("💥 ERROR TERJADI SAAT EKSEKUSI MENU 💥")
                print(f"Pesan Error: {str(e)}")
                print("-" * 50)
                traceback.print_exc() # Cetak detail error
                print("!"*50)
                print("Sistem tidak akan keluar. Silahkan coba lagi atau kembali.")
                pause()

    except Exception as main_e:
        print(f"Fatal Error di Package Menu: {main_e}")
        traceback.print_exc()
        pause()
        return False

def _handle_purchase_response(res, api_key, tokens, items, payment_for, token_confirmation_idx=0):
    """Menangani respon pembelian dengan logika retry jika harga berubah."""
    if not res:
        print("❌ Tidak ada respon dari server.")
        pause()
        return

    if res.get("status") != "SUCCESS":
        msg = res.get("message", "")
        # Handle Error Spesifik XL: Harga berubah (Dynamic Pricing)
        if "Bizz-err.Amount.Total" in msg:
            try:
                # Format pesan biasanya: "Total amount mismatch... expected=1000"
                valid_amt = int(msg.split("=")[1].strip())
                print(f"🔄 Auto-adjust harga ke: Rp {valid_amt:,}")
                res_retry = settlement_balance(
                    api_key, tokens, items, payment_for, False, 
                    overwrite_amount=valid_amt, 
                    token_confirmation_idx=token_confirmation_idx
                )
                if res_retry.get("status") == "SUCCESS": 
                    print("✅ Pembelian Berhasil (Setelah retry)!")
                else: 
                    print(f"❌ Masih gagal: {res_retry.get('message')}")
            except: 
                print(f"❌ Gagal parsing error amount: {msg}")
        else:
             print(f"❌ Pembelian Gagal: {msg}")
             # Jika ada raw data, tampilkan
             if "data" in res:
                 print(json.dumps(res["data"], indent=2))
    else: 
        print("✅ Pembelian Berhasil!")
        
    pause()

def _handle_bomb_purchase(option_code):
    try:
        n = int(input("Jumlah pembelian: "))
        use_decoy = input("Gunakan Decoy? (y/n): ").lower() == 'y'
        delay = input("Delay (detik, default 0): ").strip()
        delay = int(delay) if delay.isdigit() else 0
        purchase_n_times_by_option_code(n, option_code, use_decoy, delay_seconds=delay, pause_on_success=False, token_confirmation_idx=1)
    except ValueError: print("Input angka tidak valid.")

def get_packages_by_family(family_code, is_enterprise=None, migration_type=None):
    api_key = AuthInstance.api_key
    tokens = AuthInstance.get_active_tokens()
    if not tokens: print("❌ Session expired."); pause(); return

    data = get_family(api_key, tokens, family_code, is_enterprise, migration_type)
    if not data: print("❌ Paket family tidak ditemukan / kosong."); pause(); return

    fam_info = data.get("package_family", {})
    variants = data.get("package_variants", [])
    price_currency = "Rp"
    if fam_info.get("rc_bonus_type") == "MYREWARDS": price_currency = "Poin"
    
    while True:
        clear_screen()
        print("=" * WIDTH)
        print(f"FAMILY: {fam_info.get('name', 'Unknown')}".center(WIDTH))
        print(f"Code: {family_code}".center(WIDTH))
        print("=" * WIDTH)
        flattened_opts = []
        opt_counter = 1
        for var in variants:
            print(f"\n[ {var['name']} ]")
            print(f" Code: {var['package_variant_code']}") 
            for opt in var.get("package_options", []):
                curr_num = opt_counter
                price_tag = f"{price_currency} {opt['price']:,}"
                print(f"  {curr_num:2}. {opt['name']:<35} {price_tag:>15}")
                flattened_opts.append({"num": curr_num, "code": opt["package_option_code"], "order": opt["order"]})
                opt_counter += 1
        print("\n" + "-" * WIDTH)
        print("[0] Kembali")
        choice = input("Pilih Paket >> ").strip()
        if choice == "0": return
        if choice.isdigit():
            sel_num = int(choice)
            selected = next((x for x in flattened_opts if x["num"] == sel_num), None)
            if selected: show_package_details(api_key, tokens, selected["code"], is_enterprise, option_order=selected["order"])
            else: print("⚠️ Nomor paket tidak ada."); pause()
        else: print("⚠️ Input harus angka."); pause()

def fetch_my_packages():
    """Menampilkan paket aktif dengan Smart Date Detection & Family Code"""
    api_key = AuthInstance.api_key
    tokens = AuthInstance.get_active_tokens()
    if not tokens: return
    
    print("⏳ Mengambil list paket aktif...")
    res = send_api_request(api_key, "api/v8/packages/quota-details", {"is_enterprise": False, "lang": "en"}, tokens.get("id_token"), "POST")
    if res.get("status") != "SUCCESS": print("❌ Gagal mengambil data."); pause(); return

    quotas = res.get("data", {}).get("quotas", [])
    
    while True:
        clear_screen()
        print("=" * WIDTH)
        print("PAKET SAYA".center(WIDTH))
        print("=" * WIDTH)
        mapped_pkgs = []
        if not quotas: print("  [Tidak ada paket aktif]")
        
        for idx, q in enumerate(quotas, 1):
            exp_str = q.get('expiry_date')
            if not exp_str or exp_str == "N/A":
                ts = q.get('expired_at')
                if ts and isinstance(ts, (int, float)):
                    final_ts = float(ts)
                    if final_ts > 100_000_000_000: final_ts = final_ts / 1000
                    if final_ts < 1000000: exp_str = "Unlimited / Seumur Hidup"
                    else:
                        try: 
                            dt = datetime.fromtimestamp(final_ts)
                            if dt.year < 2020: exp_str = "Unlimited / Unknown"
                            else: exp_str = dt.strftime("%d-%m-%Y %H:%M")
                        except: exp_str = "Invalid Date"
                else: exp_str = "Unlimited / Unknown"
            
            if "1970" in str(exp_str): exp_str = "Unlimited / Unknown"

            pkg_name = q.get('name', 'Unknown Package')
            quota_code = q.get('quota_code', '-') 
            
            family_code = "Loading..."
            real_option_code = quota_code 
            try:
                pkg_detail = get_package(api_key, tokens, quota_code)
                if pkg_detail:
                    family_code = pkg_detail.get("package_family", {}).get("package_family_code", "N/A")
                    real_option_code = pkg_detail.get("package_option", {}).get("package_option_code", quota_code)
                else: family_code = "Failed to fetch (Bonus/Legacy)"
            except: family_code = "Error"
            
            print(f"{idx}. {pkg_name}")
            print(f"   Fam Code : {family_code}")
            print(f"   ID/Code  : {quota_code}")
            print(f"   Exp      : {exp_str}")
            
            benefits = q.get("benefits", [])
            if not benefits: print("   • (Tidak ada detail kuota)")
            for b in benefits:
                b_type = b.get('data_type')
                b_name = b.get('name', 'Quota')
                b_rem, b_tot = b.get('remaining', 0), b.get('total', 0)
                if b_type == 'DATA': print(f"   • {b_name:<25}: {format_quota_byte(b_rem)} / {format_quota_byte(b_tot)}")
                elif b_type == 'VOICE': print(f"   • {b_name:<25}: {b_rem//60} / {b_tot//60} Min")
                elif b_type == 'TEXT': print(f"   • {b_name:<25}: {b_rem} / {b_tot} SMS")
                else: print(f"   • {b_name:<25}: {format_quota_byte(b_rem) if b_tot > 10000 else b_rem}")

            mapped_pkgs.append({"quota": q, "real_option_code": real_option_code})
            print("-" * WIDTH)
            
        print("[Nomor] Lihat Detail & Beli Lagi")
        print("[del No] Unsubscribe Paket (Contoh: del 1)")
        print("[0] Kembali")
        
        choice = input(">> ").strip()
        if choice == "0": return
        
        if choice.startswith("del ") and len(choice.split()) == 2:
            try:
                idx = int(choice.split()[1]) - 1
                if 0 <= idx < len(mapped_pkgs):
                    pkg = mapped_pkgs[idx]["quota"]
                    conf = input(f"Yakin STOP paket {pkg['name']}? (y/n): ")
                    if conf.lower() == 'y':
                        ok = unsubscribe(api_key, tokens, pkg['quota_code'], pkg.get('product_subscription_type', 'PREPAID'), pkg.get('product_domain', 'PACKAGES'))
                        print("✅ Berhenti berlangganan berhasil." if ok else "❌ Gagal.")
                        return fetch_my_packages() 
            except Exception as e: print(f"Error: {e}"); pause()
            
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(mapped_pkgs):
                show_package_details(api_key, tokens, mapped_pkgs[idx]['real_option_code'], False)
