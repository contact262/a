# --- SKRIP UPDATE CHECKER (DIMATIKAN) ---
# Logika pengecekan update telah dihapus agar skrip ini tidak berjalan.
# Fungsi tetap ada untuk mencegah error "ImportError" pada file utama.

OWNER = "a"
REPO  = "a"
BRANCH = "main"

def get_local_commit():
    """Fungsi dimatikan."""
    return None

def get_latest_commit_atom():
    """Fungsi dimatikan."""
    return None

def check_for_updates():
    """
    Langsung return False agar program utama menganggap 
    tidak ada update dan lanjut berjalan normal.
    """
    return False
