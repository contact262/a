import subprocess
import requests
import xml.etree.ElementTree as ET
from requests.exceptions import RequestException

OWNER = "a"
REPO  = "a"
BRANCH = "main"

def get_local_commit():
    """Ambil hash commit git lokal."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL
        ).decode().strip()
    except:
        return None

def get_latest_commit_atom():
    """Ambil hash commit terbaru dari GitHub Atom Feed (Tanpa Auth)."""
    url = f"https://github.com/{OWNER}/{REPO}/commits/{BRANCH}.atom"
    try:
        r = requests.get(url, timeout=3) # Timeout pendek agar tidak blocking lama
        if r.status_code != 200: return None
        
        root = ET.fromstring(r.text)
        ns = {"a": "http://www.w3.org/2005/Atom"}
        entry = root.find("a:entry", ns)
        if entry is None: return None
        
        entry_id = entry.find("a:id", ns)
        if entry_id is None or not entry_id.text: return None
        
        return entry_id.text.rsplit("/", 1)[-1]
    except Exception:
        return None

def check_for_updates():
    """Cek update secara silent."""
    print("🔍 Mengecek pembaruan aplikasi...")
    
    local = get_local_commit()
    if not local:
        # Bukan repo git
        return False

    remote = get_latest_commit_atom()
    if not remote:
        # Gagal connect ke github
        return False

    if local != remote:
        print("\n" + "!"*50)
        print(f"🚀 UPDATE TERSEDIA!")
        print(f"Lokal : {local[:7]}")
        print(f"Remote: {remote[:7]}")
        print("Silahkan jalankan: git pull --rebase")
        print("!"*50 + "\n")
        return True
    
    return False
