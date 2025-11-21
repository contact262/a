import logging
import time
from datetime import datetime
from typing import List, Dict, Any

# Import Internal Modules
from app.menus.util import clear_screen, pause
from app.client.engsel import get_notification_detail, dashboard_segments
from app.service.auth import AuthInstance

# Setup Logger
logger = logging.getLogger(__name__)

WIDTH = 60

def _format_timestamp(ts: Any) -> str:
    """
    Mengubah timestamp (int/str) menjadi format tanggal yang mudah dibaca.
    """
    try:
        if not ts: return "-"
        
        # Deteksi jika milidetik
        timestamp = float(ts)
        if timestamp > 1000000000000:
            timestamp /= 1000
            
        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime("%d %b %H:%M")
    except Exception:
        return str(ts)

def _mark_as_read(api_key: str, tokens: dict, notif_id: str) -> bool:
    """Helper untuk menandai notifikasi sudah dibaca."""
    try:
        res = get_notification_detail(api_key, tokens, notif_id)
        # Asumsi API sukses jika mengembalikan dict valid
        return isinstance(res, dict) and res.get("status") == "SUCCESS"
    except Exception as e:
        logger.error(f"Gagal mark read {notif_id}: {e}")
        return False

def show_notification_menu():
    """
    Menu Notifikasi dengan UI Modern dan Error Handling.
    """
    while True:
        # 1. Validasi Auth
        api_key = AuthInstance.api_key
        tokens = AuthInstance.get_active_tokens()
        
        if not tokens:
            print("❌ Sesi berakhir. Silahkan login kembali.")
            pause()
            return

        # 2. Fetch Data
        clear_screen()
        print("=" * WIDTH)
        print("📩  PUSAT NOTIFIKASI".center(WIDTH))
        print("=" * WIDTH)
        print("⏳ Mengambil pesan terbaru...", end="\r")

        try:
            res = dashboard_segments(api_key, tokens)
        except Exception as e:
            logger.error(f"Fetch notification failed: {e}")
            res = None

        if not res or "data" not in res:
            print(" " * WIDTH, end="\r")
            print("\n❌ Gagal mengambil data notifikasi.")
            pause()
            return

        # Parsing Data yang aman (Safe Navigation)
        notifications = res.get("data", {}).get("notification", {}).get("data", [])
        
        if not notifications:
            print(" " * WIDTH, end="\r")
            print("\n📭 Tidak ada notifikasi baru.")
            pause()
            return

        # 3. Render List
        print(" " * WIDTH, end="\r") # Clear loading text
        
        unread_ids = []
        selection_map = {}

        for i, notif in enumerate(notifications):
            is_read = notif.get("is_read", False)
            notif_id = notif.get("notification_id")
            
            # Ikon Status
            icon = "✅" if is_read else "📩"
            status_txt = "READ" if is_read else "NEW"
            
            # Kumpulkan unread untuk fitur 'Mark All'
            if not is_read and notif_id:
                unread_ids.append(notif_id)

            # Content
            brief = notif.get("brief_message", "Pesan Sistem")[:45]
            ts_str = _format_timestamp(notif.get("timestamp"))
            
            # Mapping nomor urut ke data notifikasi
            selection_map[i + 1] = notif

            # Print Baris
            print(f"{i + 1:<2} {icon} [{ts_str}] {brief}")

        # Footer Stats
        print("-" * WIDTH)
        print(f"Total: {len(notifications)} | Belum Dibaca: {len(unread_ids)}")
        print("=" * WIDTH)
        
        print("COMMANDS:")
        print(" [No]     Baca Detail Pesan (Contoh: 1)")
        print(" [R]      Tandai Semua Sudah Dibaca (Mark All Read)")
        print(" [00]     Kembali")
        print("-" * WIDTH)

        choice = input("Pilihan >> ").strip().upper()

        # --- LOGIC ---

        if choice == "00":
            return

        elif choice == "R":
            if not unread_ids:
                print("\n✅ Semua pesan sudah terbaca.")
                pause()
                continue
            
            print(f"\n🔄 Memproses {len(unread_ids)} pesan...")
            success_count = 0
            for nid in unread_ids:
                if _mark_as_read(api_key, tokens, nid):
                    success_count += 1
                    print(f"   ✓ Pesan {nid[:8]}... ok")
                else:
                    print(f"   ✗ Pesan {nid[:8]}... gagal")
            
            print(f"\nSelesai! {success_count}/{len(unread_ids)} pesan ditandai.")
            pause()

        elif choice.isdigit():
            idx = int(choice)
            if idx in selection_map:
                target = selection_map[idx]
                nid = target.get("notification_id")
                
                # Tandai baca dulu jika belum
                if not target.get("is_read") and nid:
                    _mark_as_read(api_key, tokens, nid)
                
                # Tampilkan Detail Full
                full_msg = target.get("full_message", "")
                brief_msg = target.get("brief_message", "")
                date_str = _format_timestamp(target.get("timestamp"))
                img_url = target.get("image_url", "")

                clear_screen()
                print("=" * WIDTH)
                print(f"DETAIL PESAN #{idx}".center(WIDTH))
                print("=" * WIDTH)
                print(f"📅 Waktu : {date_str}")
                print(f"📌 Judul : {brief_msg}")
                print("-" * WIDTH)
                print(f"\n{full_msg}\n")
                
                if img_url:
                    print(f"[Gambar]: {img_url}")
                
                print("=" * WIDTH)
                pause("Tekan Enter untuk kembali...")
            else:
                print("⚠️ Nomor tidak valid.")
                pause()
        else:
            print("⚠️ Perintah tidak dikenal.")
            pause()
