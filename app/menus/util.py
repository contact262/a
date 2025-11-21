import os
import re
import sys
import platform
import logging
import html
import shutil
import textwrap
from html.parser import HTMLParser
from typing import Optional, Union

# Load environment variables otomatis saat module diimport
from dotenv import load_dotenv
load_dotenv()

# Setup Logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("MyXL_Utils")

# =============================================================================
# TERMINAL UTILITIES
# =============================================================================

def get_terminal_width(default: int = 60) -> int:
    """Mendapatkan lebar terminal saat ini."""
    try:
        columns, _ = shutil.get_terminal_size(fallback=(default, 24))
        return max(40, min(columns - 2, 100)) # Batasi max 100 chars agar enak dibaca
    except Exception:
        return default

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

def format_quota_byte(size: Union[int, float, str, None]) -> str:
    """
    Mengubah angka bytes menjadi format yang mudah dibaca (GB, MB, KB).
    Mendukung input berupa string, int, float, atau None.
    Contoh: 1073741824 -> '1.00 GB'
    """
    if size is None:
        return "0 KB"
        
    try:
        # Handle input string/float
        size = float(size)
        
        if size <= 0:
            return "0 KB"
        
        power = 2**10 # 1024
        n = 0
        power_labels = {0 : 'B', 1: 'KB', 2: 'MB', 3: 'GB', 4: 'TB'}
        
        while size >= power and n < 4:
            size /= power
            n += 1
            
        return f"{size:.2f} {power_labels[n]}"
    except (ValueError, TypeError):
        return "0 KB"

# =============================================================================
# HTML PARSING UTILITIES
# =============================================================================

class HTMLToText(HTMLParser):
    """
    Parser HTML Custom untuk merapikan output deskripsi paket.
    """
    def __init__(self):
        super().__init__()
        self.text_parts = []
        self.in_list = False

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in ['br', 'p', 'div']:
            self.text_parts.append('\n')
        elif tag == 'li':
            self.in_list = True
            self.text_parts.append('\n • ')

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in ['p', 'div']:
            self.text_parts.append('\n')
        elif tag == 'li':
            self.in_list = False

    def handle_data(self, data):
        # Bersihkan whitespace berlebih tapi pertahankan kata
        clean_data = data.strip()
        if clean_data:
            # Unescape HTML entities (contoh: &amp; -> &)
            decoded_data = html.unescape(clean_data)
            self.text_parts.append(decoded_data + ' ')

    def get_clean_text(self) -> str:
        raw_text = "".join(self.text_parts)
        # Ganti multiple newlines menjadi max 2
        cleaned = re.sub(r'\n\s*\n\s*\n', '\n\n', raw_text)
        return cleaned.strip()

def display_html(raw_html: str, width: int = 0) -> str:
    """
    Membersihkan tag HTML dari string dan merapikan formatnya untuk terminal.
    """
    if not raw_html:
        return "Tidak ada deskripsi."

    try:
        # 1. Parse HTML Structure
        parser = HTMLToText()
        parser.feed(raw_html)
        parser.close()
        text = parser.get_clean_text()

        # 2. Wrap Text agar rapi di terminal
        if width == 0:
            width = get_terminal_width()
            
        wrapper = textwrap.TextWrapper(width=width, replace_whitespace=False)
        
        lines = []
        for paragraph in text.splitlines():
            # Handle bullet points agar indentasinya rapi
            if paragraph.strip().startswith('•'):
                lines.extend(textwrap.wrap(paragraph, width=width, subsequent_indent='   '))
            else:
                lines.extend(textwrap.wrap(paragraph, width=width))
        
        return "\n".join(lines)

    except Exception as e:
        logger.error(f"Error parsing HTML: {e}")
        # Fallback: Regex cleaning sederhana jika parser gagal
        text = re.sub(r'<[^>]+>', ' ', raw_html)
        return html.unescape(text).strip()
