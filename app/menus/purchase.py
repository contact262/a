import requests, time
from random import randint
from app.client.engsel import get_family, get_package_details, get_package
from app.client.purchase.redeem import settlement_bounty, settlement_loyalty # IMPORT PENTING UNTUK REDEEM
from app.menus.util import pause
from app.service.auth import AuthInstance
from app.service.decoy import DecoyInstance
from app.type_dict import PaymentItem
from app.client.purchase.balance import settlement_balance

# =============================================================================
# KONFIGURASI AUTO REFRESH (Khusus Menu 7 - Pembelian Biasa)
# =============================================================================
REFRESH_INTERVAL_SEC = 20   # Refresh token setiap 20 detik
REFRESH_BATCH_COUNT = 5     # Refresh token setiap 5 kali percobaan

# =============================================================================
# 1. PURCHASE BY FAMILY (MENU 7)
# =============================================================================
def purchase_by_family(
    family_code: str,
    use_decoy: bool,
    pause_on_success: bool = True,
    delay_seconds: int = 0,
    start_from_option: int = 1,
):
    active_user = AuthInstance.get_active_user()
    
    api_key = AuthInstance.api_key
    tokens: dict = AuthInstance.get_active_tokens() or {}
    
    decoy_package_detail = None 

    # --- 1. INITIAL LOAD DECOY ---
    if use_decoy:
        print("⏳ Memuat data Decoy awal...")
        decoy = DecoyInstance.get_decoy("balance")
        
        decoy_package_detail = get_package(
            api_key,
            tokens,
            decoy["option_code"],
        )
        
        if not decoy_package_detail:
            print("❌ Gagal memuat detail paket Decoy.")
            pause()
            return False
        
        balance_treshold = decoy_package_detail["package_option"]["price"]
        print(f"⚠️  Pastikan sisa pulsa KURANG DARI Rp{balance_treshold}!!!")
        balance_answer = input("Yakin ingin melanjutkan? (y/n): ")
        if balance_answer.lower() != "y":
            print("Pembelian dibatalkan.")
            pause()
            return None
    
    # --- 2. LOAD FAMILY DATA ---
    family_data = get_family(api_key, tokens, family_code)
    if not family_data:
        print(f"Failed to get family data for code: {family_code}.")
        pause()
        return None
    
    family_name = family_data["package_family"]["name"]
    variants = family_data["package_variants"]
    
    print("-------------------------------------------------------")
    successful_purchases = []
    packages_count = 0
    for variant in variants:
        packages_count += len(variant["package_options"])
    
    purchase_count = 0
    start_buying = False
    if start_from_option <= 1:
        start_buying = True

    # --- VARS UNTUK AUTO REFRESH ---
    last_refresh_time = time.time()
    batch_counter = 0

    for variant in variants:
        variant_name = variant["name"]
        for option in variant["package_options"]:
            
            option_order = option["order"]
            if not start_buying and option_order == start_from_option:
                start_buying = True
            if not start_buying:
                print(f"Skipping option {option_order}. {option['name']}")
                continue
            
            # --- LOGIKA REFRESH TOKEN & DECOY (20 Detik / 5x Beli) ---
            current_time = time.time()
            time_diff = current_time - last_refresh_time
            
            if batch_counter >= REFRESH_BATCH_COUNT or time_diff >= REFRESH_INTERVAL_SEC:
                print(f"\n🔄 Refreshing Session & Decoy Token...")
                
                tokens = AuthInstance.get_active_tokens()
                
                if use_decoy:
                    try:
                        decoy = DecoyInstance.get_decoy("balance")
                        fresh_decoy = get_package(api_key, tokens, decoy["option_code"])
                        if fresh_decoy:
                            decoy_package_detail = fresh_decoy
                            print("   ✅ Decoy Token Refreshed!")
                    except Exception as e:
                        print(f"   ⚠️ Error refreshing decoy: {e}")

                last_refresh_time = time.time()
                batch_counter = 0
                print("-" * 55)
            # ---------------------------------------------------------

            option_name = option["name"]
            option_price = option["price"]
            
            purchase_count += 1
            batch_counter += 1

            print(f"Purchase {purchase_count} of {packages_count}...")
            print(f"Target: {variant_name} - {option_order}. {option_name} - {option_price}")
            
            payment_items = []
            
            try:
                target_package_detail = get_package_details(
                    api_key, tokens, family_code,
                    variant["package_variant_code"], option["order"], None, None,
                )
                
                payment_items.append(
                    PaymentItem(
                        item_code=target_package_detail["package_option"]["package_option_code"],
                        product_type="",
                        item_price=target_package_detail["package_option"]["price"],
                        item_name=str(randint(1000, 9999)) + " " + target_package_detail["package_option"]["name"],
                        tax=0,
                        token_confirmation=target_package_detail["token_confirmation"],
                    )
                )
                
                if use_decoy and decoy_package_detail:
                    payment_items.append(
                        PaymentItem(
                            item_code=decoy_package_detail["package_option"]["package_option_code"],
                            product_type="",
                            item_price=decoy_package_detail["package_option"]["price"],
                            item_name=str(randint(1000, 9999)) + " " + decoy_package_detail["package_option"]["name"],
                            tax=0,
                            token_confirmation=decoy_package_detail["token_confirmation"],
                        )
                    )
            
                overwrite_amount = target_package_detail["package_option"]["price"]
                if use_decoy and decoy_package_detail:
                    overwrite_amount += decoy_package_detail["package_option"]["price"]
                
                res = None
                error_msg = ""

                try:
                    res = settlement_balance(
                        api_key, tokens, payment_items, "頂", False,
                        overwrite_amount=overwrite_amount,
                        token_confirmation_idx=1 if use_decoy else 0
                    )
                    
                    if res and res.get("status", "") != "SUCCESS":
                        error_msg = res.get("message", "")
                        if "Bizz-err.Amount.Total" in error_msg:
                            try:
                                error_msg_arr = error_msg.split("=")
                                valid_amount = int(error_msg_arr[1].strip())
                                print(f"   ⚠️ Price adjustment: {valid_amount}")
                                res = settlement_balance(
                                    api_key, tokens, payment_items, "SHARE_PACKAGE", False,
                                    overwrite_amount=valid_amount, token_confirmation_idx=-1
                                )
                                if res and res.get("status", "") == "SUCCESS":
                                    error_msg = ""
                                    successful_purchases.append(f"{variant_name}|{option_order}. {option_name} - {option_price}")
                                    print("   ✅ Purchase successful (After Retry)!")
                                    if pause_on_success: pause()
                                else:
                                    error_msg = res.get("message", "")
                            except Exception: pass 
                    else:
                        successful_purchases.append(f"{variant_name}|{option_order}. {option_name} - {option_price}")
                        print("   ✅ Purchase successful!")
                        if pause_on_success: pause()

                except Exception as e:
                    print(f"Exception occurred while creating order: {e}")
                    res = None
                
                if error_msg:
                    print(f"   ❌ Failed: {error_msg}")

            except Exception as e:
                print(f"Exception occurred while fetching details: {e}")
                continue
            
            print("-------------------------------------------------------")
            
            should_delay = error_msg == "" or "Failed call ipaas purchase" in error_msg
            if delay_seconds > 0 and should_delay:
                print(f"Waiting for {delay_seconds} seconds...")
                time.sleep(delay_seconds)
                
    print(f"Family: {family_name}\nSuccessful: {len(successful_purchases)}")
    if len(successful_purchases) > 0:
        print("-" * 55)
        print("Successful purchases:")
        for purchase in successful_purchases:
            print(f"- {purchase}")
    print("-" * 55)
    pause()

# =============================================================================
# 2. REDEEM LOOP (FIX UNTUK MENU 15)
# =============================================================================
def redeem_n_times(
    n: int,
    option_code: str,
    redeem_type: str = "BOUNTY", # "BOUNTY" (Voucher) atau "LOYALTY" (Poin)
    delay_seconds: int = 0
):
    """
    Melakukan Redeem berkali-kali dengan Refresh Token SETIAP putaran.
    Wajib refresh per putaran karena token redeem bersifat One-Time-Use.
    """
    api_key = AuthInstance.api_key
    
    print(f"\n🚀 Memulai Redeem Loop ({redeem_type}) sebanyak {n}x")
    print(f"📦 Target: {option_code}")
    print("-------------------------------------------------------")
    
    success_count = 0
    
    for i in range(n):
        print(f"🔄 Redeem {i + 1} of {n}...")
        
        # 1. Refresh Token Auth (Jaga-jaga session mati)
        tokens = AuthInstance.get_active_tokens()
        if not tokens:
            print("❌ Session Invalid.")
            break

        try:
            # 2. REFRESH DATA PAKET (WAJIB SETIAP LOOP UNTUK REDEEM)
            pkg_detail = get_package(api_key, tokens, option_code)
            
            if not pkg_detail:
                print(f"❌ Gagal mengambil detail paket/voucher.")
                time.sleep(1) 
                continue

            pkg_opt = pkg_detail.get("package_option", {})
            token_conf = pkg_detail.get("token_confirmation")
            ts_sign = pkg_detail.get("timestamp")
            price = pkg_opt.get("price", 0)
            name = pkg_opt.get("name", "Unknown Item")
            
            if not token_conf:
                print("❌ Token Confirmation habis/invalid.")
                time.sleep(1)
                continue

            print(f"   Item: {name} | Price: {price}")

            # 3. EKSEKUSI REDEEM
            res = None
            if redeem_type == "BOUNTY": # Redeem Voucher
                res = settlement_bounty(
                    api_key=api_key, tokens=tokens, token_confirmation=token_conf,
                    ts_to_sign=ts_sign, payment_target=option_code,
                    price=price, item_name=name
                )
            elif redeem_type == "LOYALTY": # Tukar Poin
                res = settlement_loyalty(
                    api_key=api_key, tokens=tokens, token_confirmation=token_conf,
                    ts_to_sign=ts_sign, payment_target=option_code,
                    price=price
                )
            
            # 4. CEK HASIL
            if res and res.get("status") == "SUCCESS":
                print("   ✅ REDEEM SUCCESS!")
                success_count += 1
            else:
                msg = res.get("message") if res else "No Response"
                print(f"   ❌ GAGAL: {msg}")

        except Exception as e:
            print(f"   ⚠️ Exception: {e}")
        
        print("-------------------------------------------------------")
        
        if delay_seconds > 0 and i < n - 1:
            print(f"⏳ Waiting {delay_seconds}s...")
            time.sleep(delay_seconds)

    print(f"\n🏁 Selesai! Berhasil: {success_count}/{n}")
    pause()

# =============================================================================
# 3. STANDARD LOOP FUNCTIONS (TIDAK DIUBAH, AGAR FITUR ASLI TETAP ADA)
# =============================================================================

def purchase_n_times(
    n: int,
    family_code: str,
    variant_code: str,
    option_order: int,
    use_decoy: bool,
    delay_seconds: int = 0,
    pause_on_success: bool = False,
    token_confirmation_idx: int = 0,
):
    active_user = AuthInstance.get_active_user()
    api_key = AuthInstance.api_key
    tokens: dict = AuthInstance.get_active_tokens() or {}
    
    decoy_package_detail = None

    if use_decoy:
        decoy = DecoyInstance.get_decoy("balance")
        decoy_package_detail = get_package(api_key, tokens, decoy["option_code"])
        if not decoy_package_detail:
            print("Failed to load decoy package details.")
            pause()
            return False
        
        balance_treshold = decoy_package_detail["package_option"]["price"]
        print(f"Pastikan sisa balance KURANG DARI Rp{balance_treshold}!!!")
        if input("Lanjut? (y/n): ").lower() != 'y': return None
    
    family_data = get_family(api_key, tokens, family_code)
    if not family_data:
        print(f"Failed to get family data."); pause(); return None

    target_variant = next((v for v in family_data["package_variants"] if v["package_variant_code"] == variant_code), None)
    if not target_variant: return None
    target_option = next((o for o in target_variant["package_options"] if o["order"] == option_order), None)
    if not target_option: return None

    print("-------------------------------------------------------")
    successful_purchases = []
    
    for i in range(n):
        print(f"Purchase {i + 1} of {n}...")
        tokens = AuthInstance.get_active_tokens() or {}
        payment_items = []
        
        try:
            target_package_detail = get_package_details(
                api_key, tokens, family_code, target_variant["package_variant_code"], target_option["order"], None, None,
            )
            
            payment_items.append(PaymentItem(
                item_code=target_package_detail["package_option"]["package_option_code"],
                product_type="",
                item_price=target_package_detail["package_option"]["price"],
                item_name=str(randint(1000, 9999)) + " " + target_package_detail["package_option"]["name"],
                tax=0,
                token_confirmation=target_package_detail["token_confirmation"],
            ))
            
            if use_decoy and decoy_package_detail:
                payment_items.append(PaymentItem(
                    item_code=decoy_package_detail["package_option"]["package_option_code"],
                    product_type="",
                    item_price=decoy_package_detail["package_option"]["price"],
                    item_name=str(randint(1000, 9999)) + " " + decoy_package_detail["package_option"]["name"],
                    tax=0,
                    token_confirmation=decoy_package_detail["token_confirmation"],
                ))
            
            overwrite_amount = target_package_detail["package_option"]["price"]
            if use_decoy and decoy_package_detail:
                overwrite_amount += decoy_package_detail["package_option"]["price"]

            res = settlement_balance(
                api_key, tokens, payment_items, "💰", False,
                overwrite_amount=overwrite_amount, token_confirmation_idx=token_confirmation_idx
            )
            
            if res and res.get("status", "") == "SUCCESS":
                successful_purchases.append(f"Purchase {i + 1}")
                print("Purchase successful!")
                if pause_on_success: pause()
            else:
                print(f"Failed: {res.get('message')}")
        except Exception as e:
            print(f"Exception: {e}")
        
        print("-------------------------------------------------------")
        if delay_seconds > 0 and i < n - 1: time.sleep(delay_seconds)

    print(f"Total successful purchases {len(successful_purchases)}/{n}")
    pause()
    return True

def purchase_n_times_by_option_code(
    n: int,
    option_code: str,
    use_decoy: bool,
    delay_seconds: int = 0,
    pause_on_success: bool = False,
    token_confirmation_idx: int = 0,
):
    active_user = AuthInstance.get_active_user()
    api_key = AuthInstance.api_key
    tokens: dict = AuthInstance.get_active_tokens() or {}
    
    decoy_package_detail = None
    if use_decoy:
        decoy = DecoyInstance.get_decoy("balance")
        decoy_package_detail = get_package(api_key, tokens, decoy["option_code"])
        if not decoy_package_detail: return False
        if input("Lanjut? (y/n): ").lower() != 'y': return None
    
    print("-------------------------------------------------------")
    successful_purchases = []
    
    for i in range(n):
        print(f"Purchase {i + 1} of {n}...")
        tokens = AuthInstance.get_active_tokens() or {}
        payment_items = []
        
        try:
            target_package_detail = get_package(api_key, tokens, option_code)
            
            payment_items.append(PaymentItem(
                item_code=target_package_detail["package_option"]["package_option_code"],
                product_type="",
                item_price=target_package_detail["package_option"]["price"],
                item_name=str(randint(1000, 9999)) + " " + target_package_detail["package_option"]["name"],
                tax=0,
                token_confirmation=target_package_detail["token_confirmation"],
            ))
            
            if use_decoy and decoy_package_detail:
                payment_items.append(PaymentItem(
                    item_code=decoy_package_detail["package_option"]["package_option_code"],
                    product_type="",
                    item_price=decoy_package_detail["package_option"]["price"],
                    item_name=str(randint(1000, 9999)) + " " + decoy_package_detail["package_option"]["name"],
                    tax=0,
                    token_confirmation=decoy_package_detail["token_confirmation"],
                ))
            
            overwrite_amount = target_package_detail["package_option"]["price"]
            if use_decoy and decoy_package_detail:
                overwrite_amount += decoy_package_detail["package_option"]["price"]

            res = settlement_balance(
                api_key, tokens, payment_items, "💰", False,
                overwrite_amount=overwrite_amount, token_confirmation_idx=token_confirmation_idx
            )
            
            if res and res.get("status", "") == "SUCCESS":
                successful_purchases.append(f"Purchase {i + 1}")
                print("Purchase successful!")
                if pause_on_success: pause()
        except Exception as e:
            print(f"Error: {e}")
        
        print("-------------------------------------------------------")
        if delay_seconds > 0 and i < n - 1: time.sleep(delay_seconds)

    print(f"Total successful purchases {len(successful_purchases)}/{n}")
    pause()
    return True
