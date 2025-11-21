import json
import os
import sys
import time
import threading
import logging
from datetime import datetime
from typing import Dict, Any

# Import dependencies
from app.client.engsel import send_api_request
from app.menus.util import clear_screen, pause
from app.service.auth import AuthInstance

# Setup Logger khusus untuk file (agar tidak bentrok dengan stdout)
# Kita pakai logging manual ke file di dalam loop agar lebih terkontrol

class SentryMonitor:
    """
    Class untuk menjalankan Sentry Mode (Monitoring Kuota Real-time).
    """
    
    def __init__(self):
        self.stop_event = threading.Event()
        self.log_dir = "sentry_logs"
        
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)

    def _input_listener(self):
        """Background thread menunggu tombol ENTER."""
        try:
            input()
            self.stop_event.set()
        except (EOFError, KeyboardInterrupt):
            self.stop_event.set()

    def run(self):
        # 1. Auth Check
        user = AuthInstance.get_active_user()
        if not user:
            print("❌ Harap login terlebih dahulu.")
            pause()
            return

        api_key = AuthInstance.api_key
        tokens = user.get("tokens", {})
        if not tokens.get("id_token"):
            print("❌ Token tidak valid. Silahkan relogin.")
            pause()
            return

        # 2. Setup Log File
        timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_filename = f"sentry_{user['number']}_{timestamp_str}.jsonl"
        log_path = os.path.join(self.log_dir, log_filename)

        # 3. UI Init
        clear_screen()
        print("=" * 60)
        print("👁️  SENTRY MODE - REALTIME MONITORING".center(60))
        print("=" * 60)
        print(f" Target   : {user['number']}")
        print(f" Log File : {log_path}")
        print(f" Interval : 1 Detik")
        print("-" * 60)
        print(" [ INFO ] Tekan [ENTER] untuk menghentikan monitoring.")
        print("=" * 60)

        # 4. Start Listener Thread
        listener_t = threading.Thread(target=self._input_listener, daemon=True)
        listener_t.start()

        # 5. Main Loop
        path_api = "api/v8/packages/quota-details"
        payload = {"is_enterprise": False, "lang": "en", "family_member_id": ""}
        
        counter = 0
        error_count = 0
        
        try:
            with open(log_path, 'a', encoding='utf-8') as f:
                while not self.stop_event.is_set():
                    now_ts = datetime.now().strftime('%H:%M:%S')
                    counter += 1
                    
                    # Visual Indicator (Overwrite line)
                    sys.stdout.write(f"\r⏳ [{now_ts}] Fetch #{counter} | Errors: {error_count}")
                    sys.stdout.flush()

                    try:
                        # Fetch Data
                        res = send_api_request(
                            api_key, path_api, payload, tokens["id_token"], 
                            "POST", timeout=15
                        )

                        if res.get("status") == "SUCCESS":
                            record = {
                                "ts": datetime.now().isoformat(),
                                "data": res.get("data", {}).get("quotas", [])
                            }
                            f.write(json.dumps(record) + "\n")
                            f.flush() # Pastikan tertulis ke disk
                        else:
                            error_count += 1
                            # Log error response to debug separately if needed
                            
                    except Exception as e:
                        error_count += 1
                        # Silent error di UI agar rapi, tapi tercatat di counter
                    
                    # Sleep dengan interrupt check
                    # Loop kecil 10x0.1s agar respon stop lebih cepat
                    for _ in range(10):
                        if self.stop_event.is_set(): break
                        time.sleep(0.1)

        except KeyboardInterrupt:
            print("\n\n🛑 Monitoring dihentikan paksa (Ctrl+C).")
        except Exception as e:
            print(f"\n\n❌ Critical Error: {e}")
        finally:
            print(f"\n\n✅ Monitoring Selesai.")
            print(f"   Total Data: {counter} | Errors: {error_count}")
            print(f"   File: {log_path}")
            pause()

# =============================================================================
# COMPATIBILITY LAYER
# =============================================================================

def enter_sentry_mode():
    """Wrapper function untuk dipanggil dari menu utama."""
    monitor = SentryMonitor()
    monitor.run()
