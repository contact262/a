import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

# Import Internal Modules
from app.menus.package import get_packages_by_family, show_package_details
from app.menus.util import pause, clear_screen, format_quota_byte
from app.client.circle import (
    get_group_data,
    get_group_members,
    create_circle,
    validate_circle_member,
    invite_circle_member,
    remove_circle_member,
    accept_circle_invitation,
    spending_tracker,
    get_bonus_data,
)
from app.service.auth import AuthInstance
from app.client.encrypt import decrypt_circle_msisdn

# Setup Logger
logger = logging.getLogger(__name__)

WIDTH = 65

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _format_date(ts: int) -> str:
    """Helper format tanggal aman."""
    try:
        if not ts: return "N/A"
        if ts > 1000000000000: ts /= 1000
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
    except: return "N/A"

def _decrypt_msisdn(api_key: str, encrypted: str) -> str:
    """Helper dekripsi nomor dengan fallback."""
    try:
        if not encrypted: return "<Empty>"
        return decrypt_circle_msisdn(api_key, encrypted) or "<Hidden>"
    except Exception:
        return "<Error>"

# =============================================================================
# CORE MENUS
# =============================================================================

def show_circle_creation(api_key: str, tokens: dict):
    """Menu pembuatan Circle baru."""
    clear_screen()
    print("=" * WIDTH)
    print("🛠️  BUAT CIRCLE BARU".center(WIDTH))
    print("=" * WIDTH)
    
    try:
        parent_name = input("Nama Anda (Owner): ").strip()
        group_name = input("Nama Circle: ").strip()
        member_msisdn = input("Nomor Anggota Pertama (628...): ").strip()
        member_name = input("Nama Anggota Pertama: ").strip()
        
        if not (parent_name and group_name and member_msisdn):
            print("❌ Data tidak boleh kosong.")
            pause()
            return

        print("\n⏳ Membuat Circle...")
        res = create_circle(api_key, tokens, parent_name, group_name, member_msisdn, member_name)
        
        if res.get("status") == "SUCCESS":
            print("✅ Circle berhasil dibuat!")
            print(json.dumps(res, indent=2))
        else:
            print(f"❌ Gagal membuat Circle: {res.get('message')}")
            
    except Exception as e:
        logger.error(f"Create circle error: {e}")
        print(f"❌ Error: {e}")
    
    pause()

def show_bonus_list(api_key: str, tokens: dict, parent_subs_id: str, family_id: str):
    """Menu daftar bonus Circle."""
    while True:
        clear_screen()
        print("=" * WIDTH)
        print("🎁  CIRCLE BONUS".center(WIDTH))
        print("=" * WIDTH)
        print("⏳ Mengambil data bonus...", end="\r")
        
        res = get_bonus_data(api_key, tokens, parent_subs_id, family_id)
        
        if res.get("status") != "SUCCESS":
            print(" " * WIDTH, end="\r")
            print("❌ Gagal mengambil data bonus.")
            pause()
            return
        
        bonuses = res.get("data", {}).get("bonuses", [])
        if not bonuses:
            print(" " * WIDTH, end="\r")
            print("📭 Tidak ada bonus tersedia.")
            pause()
            return
        
        print(" " * WIDTH, end="\r")
        
        selection_map = {}
        
        for idx, bonus in enumerate(bonuses, 1):
            name = bonus.get("name", "Bonus")[:30]
            b_type = bonus.get("bonus_type", "General")
            act_type = bonus.get("action_type", "UNK")
            
            selection_map[idx] = bonus
            
            print(f"{idx:<2}. {name:<32} | {b_type:<10}")
            
        print("-" * WIDTH)
        print("[No] Pilih Bonus")
        print("[00] Kembali")
        print("=" * WIDTH)
        
        choice = input("Pilihan >> ").strip()
        
        if choice == "00":
            return
            
        if choice.isdigit():
            idx = int(choice)
            if idx in selection_map:
                bonus = selection_map[idx]
                act_type = bonus.get("action_type")
                act_param = bonus.get("action_param")
                
                if act_type == "PLP":
                    get_packages_by_family(act_param)
                elif act_type == "PDP":
                    show_package_details(api_key, tokens, act_param, False)
                else:
                    print(f"⚠️ Tipe aksi tidak didukung: {act_type}")
                    pause()
            else:
                print("⚠️ Nomor tidak valid.")
                pause()
        else:
            print("⚠️ Input salah.")
            pause()

def show_circle_info(api_key: str, tokens: dict):
    """
    Menu Utama Manajemen Circle.
    """
    user = AuthInstance.get_active_user()
    my_msisdn = user.get("number", "")

    while True:
        clear_screen()
        print("=" * WIDTH)
        print("⭕  CIRCLE MANAGER".center(WIDTH))
        print("=" * WIDTH)
        print("⏳ Mengambil data circle...", end="\r")

        # 1. Fetch Group Data
        group_res = get_group_data(api_key, tokens)
        if group_res.get("status") != "SUCCESS":
            print("\n❌ Gagal mengambil data Circle.")
            pause()
            return
        
        group_data = group_res.get("data", {})
        group_id = group_data.get("group_id", "")

        # Case: No Circle
        if not group_id:
            print(" " * WIDTH, end="\r")
            print("\n   [ Anda belum tergabung dalam Circle ]")
            print("\n   1. Buat Circle Baru")
            print("   0. Kembali")
            
            ch = input("\n   Pilihan >> ").strip()
            if ch == "1":
                show_circle_creation(api_key, tokens)
                continue
            else:
                return

        # Case: Blocked
        if group_data.get("group_status") == "BLOCKED":
            print("\n⛔ Circle ini sedang DIBLOKIR.")
            pause()
            return

        # 2. Fetch Members & Spending
        members_res = get_group_members(api_key, tokens, group_id)
        members = members_res.get("data", {}).get("members", [])
        package_info = members_res.get("data", {}).get("package", {})
        
        # Cari Parent ID
        parent_info = next((m for m in members if m.get("member_role") == "PARENT"), {})
        parent_subs_id = parent_info.get("subscriber_number", "")
        parent_msisdn = _decrypt_msisdn(api_key, parent_info.get("msisdn", ""))
        parent_member_id = parent_info.get("member_id", "")

        # Spending
        spend_res = spending_tracker(api_key, tokens, parent_subs_id, group_id)
        spend_data = spend_res.get("data", {})
        
        # Render Header
        print(" " * WIDTH, end="\r")
        
        g_name = group_data.get("group_name", "Unknown")
        pkg_name = package_info.get("name", "No Package")
        
        ben = package_info.get("benefit", {})
        rem_q = format_quota_byte(ben.get("remaining", 0))
        tot_q = format_quota_byte(ben.get("allocation", 0))
        
        spend_curr = spend_data.get("spend", 0)
        spend_tgt = spend_data.get("target", 0)
        
        print(f" Nama Circle : {g_name}")
        print(f" Owner       : {parent_msisdn}")
        print(f" Paket       : {pkg_name}")
        print(f" Sisa Kuota  : {rem_q} / {tot_q}")
        print(f" Spending    : Rp {spend_curr:,} / Rp {spend_tgt:,}")
        print("-" * WIDTH)
        
        # Render Members
        print(f"{'NO':<3} | {'NOMOR':<14} | {'ROLE':<8} | {'STATUS'}")
        print("-" * WIDTH)
        
        for i, m in enumerate(members, 1):
            num = _decrypt_msisdn(api_key, m.get("msisdn", ""))
            role = "👑 OWNER" if m.get("member_role") == "PARENT" else "👤 MEMBER"
            status = m.get("status", "ACTIVE")
            
            # Highlight myself
            if num == str(my_msisdn):
                role += " (You)"
            
            print(f" {i:<2} | {num:<14} | {role:<8} | {status}")

        print("=" * WIDTH)
        print("COMMANDS:")
        print(" [1]      Undang Anggota (Invite)")
        print(" [2]      Lihat Bonus Circle")
        print(" [del X]  Hapus Anggota No. X")
        print(" [acc X]  Terima Undangan Anggota No. X")
        print(" [00]     Kembali")
        print("-" * WIDTH)
        
        choice = input("Pilihan >> ").strip()
        
        if choice == "00":
            return
            
        elif choice == "1":
            _handle_invite(api_key, tokens, group_id, parent_member_id)
            
        elif choice == "2":
            show_bonus_list(api_key, tokens, parent_subs_id, group_id)
            
        elif choice.startswith("del "):
            _handle_remove(api_key, tokens, members, group_id, parent_member_id, choice)
            
        elif choice.startswith("acc "):
            _handle_accept(api_key, tokens, members, group_id, choice)
            
        else:
            print("⚠️ Perintah tidak valid.")
            pause()

# =============================================================================
# ACTION HANDLERS
# =============================================================================

def _handle_invite(api_key, tokens, group_id, parent_id):
    target = input("Nomor Tujuan (628...): ").strip()
    name = input("Nama Anggota: ").strip()
    
    if not target: return
    
    print("⏳ Memvalidasi...")
    val = validate_circle_member(api_key, tokens, target)
    
    # Cek eligibility
    if val.get("data", {}).get("response_code") != "200-2001":
        msg = val.get("data", {}).get("message", "Tidak memenuhi syarat")
        print(f"❌ Gagal: {msg}")
        pause()
        return

    print("⏳ Mengirim undangan...")
    res = invite_circle_member(api_key, tokens, target, name, group_id, parent_id)
    
    if res.get("status") == "SUCCESS":
        print("✅ Undangan terkirim!")
    else:
        print(f"❌ Gagal: {res.get('message')}")
    pause()

def _handle_remove(api_key, tokens, members, group_id, parent_id, cmd):
    try:
        idx = int(cmd.split()[1]) - 1
        if not (0 <= idx < len(members)): raise ValueError
        
        target = members[idx]
        num = _decrypt_msisdn(api_key, target.get("msisdn", ""))
        
        if target.get("member_role") == "PARENT":
            print("❌ Tidak bisa menghapus Owner.")
            pause()
            return
            
        if len(members) <= 2:
            print("❌ Minimal 2 anggota dalam Circle.")
            pause()
            return

        if input(f"❓ Hapus {num}? (y/n): ").lower() == 'y':
            res = remove_circle_member(
                api_key, tokens, target["member_id"], 
                group_id, parent_id, False
            )
            if res.get("status") == "SUCCESS":
                print("✅ Anggota dihapus.")
            else:
                print(f"❌ Gagal: {res.get('message')}")
            pause()
            
    except (ValueError, IndexError):
        print("❌ Format salah. Gunakan: del <nomor_urut>")
        pause()

def _handle_accept(api_key, tokens, members, group_id, cmd):
    try:
        idx = int(cmd.split()[1]) - 1
        target = members[idx]
        
        if target.get("status") != "INVITED":
            print("⚠️ Member ini sudah aktif atau tidak dalam status invited.")
            pause()
            return

        if input("❓ Terima undangan ini? (y/n): ").lower() == 'y':
            res = accept_circle_invitation(
                api_key, tokens, group_id, target["member_id"]
            )
            if res.get("status") == "SUCCESS":
                print("✅ Undangan diterima.")
            else:
                print(f"❌ Gagal: {res.get('message')}")
            pause()
            
    except (ValueError, IndexError):
        print("❌ Format salah.")
        pause()
