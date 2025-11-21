import os
import re
import sys
import platform
import logging
import html
from typing import Optional, Union

# Load environment variables otomatis saat module diimport
from dotenv import load_dotenv
load_dotenv()

# Setup Logger
logger = logging.getLogger(__name__)

# =============================================================================
# TERMINAL UTILITIES
# =============================================================================

def clear_screen():
    """Membersihkan layar terminal (Cross-platform)."""
    try:
        command = 'cls' if platform.system() == 'Windows' else 'clear'
        os.system(command)
    except Exception:
        # Fallback jika command gagal (misal di IDE console tertentu)
        print("\n" * 50)

def pause(message: str = "Tekan [Enter] untuk melanjutkan..."):
    """Menahan eksekusi program."""
    try:
        print("")
        input(message)
    except (KeyboardInterrupt, EOFError):
        pass

# =============================================================================
# FORMATTING UTILITIES
# =============================================================================

def format_quota_byte(size: Union[int, float, str]) -> str:
    """
    Mengubah angka bytes menjadi format yang mudah dibaca (GB, MB, KB).
    Contoh: 1048576 -> '1.00 MB'
    """
    try:
        # Handle input string/float
        size = float(size)
        
        power = 2**10 # 1024
        n = 0
        power_labels = {0 : '', 1: 'KB', 2: 'MB', 3: 'GB', 4: 'TB'}
        
        while size >= power and n < 4:
            size /= power
            n += 1
            
        return f"{size:.2f} {power_labels[n]}"
    except (ValueError, TypeError):
        return "0 KB"

def display_html(raw_html: str) -> str:
    """
    Membersihkan tag HTML dari string dan merapikan formatnya untuk terminal.
    Mengubah <br> jadi newline, <li> jadi bullet point, dll.
    """
    if not raw_html:
        return "Tidak ada deskripsi."

    try:
        # 1. Unescape HTML entities (&amp; -> &, &gt; -> >)
        text = html.unescape(raw_html)

        # 2. Ganti tag baris baru dengan newline asli
        text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</p>', '\n\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</div>', '\n', text, flags=re.IGNORECASE)

        # 3. Ganti list item dengan bullet point
        text = re.sub(r'<li.*?>', '\n • ', text, flags=re.IGNORECASE)

        # 4. Hapus semua tag HTML sisanya (<b >, </span>, dll)
        clean_text = re.sub(r'<[^>]+>', '', text)

        # 5. Rapikan spasi berlebih (Multiple newlines jadi max 2)
        clean_text = re.sub(r'\n\s*\n', '\n\n', clean_text)
        
        return clean_text.strip()
    except Exception as e:
        logger.error(f"Error parsing HTML: {e}")
        return raw_html # Return raw jika gagal

# =============================================================================
# CONFIGURATION UTILITIES
# =============================================================================

def ensure_api_key() -> str:
    """
    Memastikan API Key tersedia dari environment variable.
    """
    api_key = os.getenv("API_KEY")
    if not api_key:
        # Fallback support untuk nama variabel lain
        api_key = os.getenv("XL_API_KEY")
        
    if not api_key:
        # Jika masih kosong, kembalikan string kosong (nanti dihandle auth service)
        logger.warning("API KEY tidak ditemukan di .env")
        return ""
        
    return api_key.strip()

def verify_api_key(api_key: str) -> bool:
    """Validasi format dasar API Key."""
    return bool(api_key and len(api_key) > 5)
