import json
import logging
from datetime import datetime
from typing import Dict, Any, List

# Import Dependencies
from app.menus.util import pause, clear_screen, format_quota_byte
from app.client.famplan import (
    get_family_data, 
    change_member, 
    remove_member, 
    set_quota_limit, 
    validate_msisdn
)

# Setup Logger
logger = logging.getLogger(__name__)

WIDTH = 65

def _format_date(timestamp: Any) -> str:
    """Helper format tanggal."""
    try:
        if not timestamp: return "-"
        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime("%d %b %Y")
    except: return "-"

def _get_slot_status(member: dict) -> str:
    """Mendapatkan status slot (Empty/Occupied)."""
    return "🟢 TERISI" if member.get("msisdn") else "⚪ KOSONG"

def _handle_change_member(api_key, tokens, members):
    """Logika tambah/ganti anggota."""
    try:
        slot_idx = int(input("\nMasukkan Nomor Slot: "))
        if not (1 <= slot_idx <= len(members)):
            print("❌ Nomor slot tidak valid.")
            return

        member = members[slot_idx - 1]
        if member.get("msisdn"):
            print("⚠️  Slot ini sudah terisi. Hapus anggota dulu jika ingin mengganti.")
            return

        target_msisdn = input("Masukkan Nomor Baru (628...): ").strip()
        parent_alias = input("Alias Anda (Parent): ").strip() or "Admin"
        child_alias = input("Alias Anggota Baru: ").strip() or "Member"

        # Validasi MSISDN
        print("⏳ Memvalidasi nomor...")
        val_res = validate_msisdn(api_key, tokens, target_msisdn)
        
        if val_res.get("status", "").lower() != "success":
            print(f"❌ Nomor tidak valid: {val_res.get('message')}")
            return

        role = val_res["data"].get("family_plan_role", "")
        if role != "NO_ROLE":
            print(f"⚠️  Nomor ini sudah terdaftar di paket keluarga lain (Role: {role}).")
            return

        confirm = input(f"❓ Tambahkan {target_msisdn} ke Slot {slot_idx}? (y/n): ").lower()
        if confirm != 'y': return

        print("⏳ Memproses penambahan...")
        res = change_member(
            api_key, tokens, parent_alias, child_alias,
            member["slot_id"], member["family_member_id"], target_msisdn
        )

        if res.get("status") == "SUCCESS":
            print("✅ Berhasil menambahkan anggota!")
        else:
            print(f"❌ Gagal: {res.get('message')}")

    except ValueError:
        print("❌ Input harus angka.")
    except Exception as e:
        logger.error(f"Change member error: {e}")
        print(f"❌ Terjadi kesalahan: {e}")

def _handle_remove_member(api_key, tokens, members):
    """Logika hapus anggota."""
    try:
        slot_idx = int(input("\nMasukkan Nomor Slot yang akan DIHAPUS: "))
        if not (1 <= slot_idx <= len(members)):
            print("❌ Nomor slot tidak valid.")
            return

        member = members[slot_idx - 1]
        if not member.get("msisdn"):
            print("⚠️  Slot ini sudah kosong.")
            return

        confirm = input(f"❓ Yakin HAPUS {member['msisdn']} dari Slot {slot_idx}? (y/n): ").lower()
        if confirm != 'y': return

        print("⏳ Memproses penghapusan...")
        res = remove_member(api_key, tokens, member["family_member_id"])

        if res.get("status") == "SUCCESS":
            print("✅ Anggota berhasil dihapus.")
        else:
            print(f"❌ Gagal: {res.get('message')}")

    except ValueError:
        print("❌ Input harus angka.")
    except Exception as e:
        print(f"❌ Error: {e}")

def _handle_set_limit(api_key, tokens, members):
    """Logika atur limit kuota."""
    try:
        slot_idx = int(input("\nMasukkan Nomor Slot: "))
        if not (1 <= slot_idx <= len(members)):
            print("❌ Nomor slot tidak valid.")
            return

        member = members[slot_idx - 1]
        if not member.get("msisdn"):
            print("⚠️  Slot kosong, tidak bisa atur limit.")
            return

        limit_mb = int(input("Masukkan Batas Kuota (MB): "))
        limit_bytes = limit_mb * 1024 * 1024
        current_alloc = member.get("usage", {}).get("quota_allocated", 0)

        print(f"⏳ Mengubah limit dari {format_quota_byte(current_alloc)} ke {format_quota_byte(limit_bytes)}...")
        
        res = set_quota_limit(
            api_key, tokens, current_alloc, limit_bytes, member["family_member_id"]
        )

        if res.get("status") == "SUCCESS":
            print("✅ Limit kuota berhasil diubah.")
        else:
            print(f"❌ Gagal: {res.get('message')}")

    except ValueError:
        print("❌ Input harus angka.")
    except Exception as e:
        print(f"❌ Error: {e}")

def show_family_info(api_key: str, tokens: dict):
    """
    Menu Manajemen Family Plan / Akrab.
    """
    while True:
        clear_screen()
        print("=" * WIDTH)
        print("👨‍👩‍👧‍👦  FAMILY PLAN MANAGER".center(WIDTH))
        print("=" * WIDTH)
        print("⏳ Mengambil data paket keluarga...", end="\r")

        res = get_family_data(api_key, tokens)
        
        if not res or not res.get("data"):
            print(" " * WIDTH, end="\r")
            print("❌ Gagal mengambil data family plan.")
            print("   Pastikan Anda sudah berlangganan paket Akrab.")
            pause()
            return

        info = res["data"]["member_info"]
        if not info["plan_type"]:
            print(" " * WIDTH, end="\r")
            print("🚫 Anda bukan pengelola (Organizer) paket keluarga.")
            pause()
            return

        # Header Info
        plan_name = info.get("plan_type", "Unknown Plan")
        parent = info.get("parent_msisdn", "-")
        total_q = format_quota_byte(info.get("total_quota", 0))
        rem_q = format_quota_byte(info.get("remaining_quota", 0))
        exp_date = _format_date(info.get("end_date", 0))

        print(" " * WIDTH, end="\r")
        print(f" 📦 Paket   : {plan_name}")
        print(f" 👑 Parent  : {parent}")
        print(f" 📊 Kuota   : {rem_q} / {total_q}")
        print(f" 📅 Expired : {exp_date}")
        print("-" * WIDTH)

        # Member List
        members = info.get("members", [])
        
        print(f"{'NO':<3} | {'NOMOR':<14} | {'STATUS':<9} | {'PEMAKAIAN':<18}")
        print("-" * WIDTH)

        for i, m in enumerate(members):
            num = m.get("msisdn") or "KOSONG"
            alias = m.get("alias", "-")[:8]
            status = "✅" if m.get("msisdn") else "⚪"
            
            usage = m.get("usage", {})
            used = format_quota_byte(usage.get("quota_used", 0))
            alloc = format_quota_byte(usage.get("quota_allocated", 0))
            
            # Format baris
            print(f" {i+1:<2} | {num:<14} | {status} {alias:<6} | {used} / {alloc}")

        print("-" * WIDTH)
        print("PERINTAH:")
        print(" [1] Tambah Anggota Baru")
        print(" [2] Hapus Anggota")
        print(" [3] Atur Batas Kuota (Limit)")
        print(" [0] Kembali")
        print("=" * WIDTH)

        choice = input("Pilihan >> ").strip()

        if choice == "0":
            return
        elif choice == "1":
            _handle_change_member(api_key, tokens, members)
            pause()
        elif choice == "2":
            _handle_remove_member(api_key, tokens, members)
            pause()
        elif choice == "3":
            _handle_set_limit(api_key, tokens, members)
            pause()
        else:
            print("⚠️  Pilihan tidak valid.")
            pause()
