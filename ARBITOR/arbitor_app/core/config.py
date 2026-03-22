import os
import socket
from datetime import datetime
from urllib.parse import urlparse

PREDEFINED_CREDENTIALS = {
    "Ronit": "Ronit@789",
    "Rishabh": "Baka_555",
    "Ganesh": "Ganesh@123",
    "Ansh": "Ansh_123",
    "1": "1",
}

BLOCKED_KEYWORDS = {
    "facebook.com",
    "instagram.com",
    "youtube.com",
    "tiktok.com",
    "netflix.com",
    "x.com",
    "torrent",
    "1337x",
    "thepiratebay",
    "fitgirl",
    "steamunlocked",
    "freegames",
    "miniclip",
    "adult",
    "porn",
    "xvideos",
    "xnxx",
    "vpn",
    "proxy",
}


def now_iso():
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def stamp():
    return datetime.now().strftime("%H:%M:%S")

def resolve_pc_id():
    configured = os.getenv("ARBITOR_PC_ID", "").strip()
    if configured:
        return configured.upper()
    return socket.gethostname().upper()

def resolve_lab_id():
    configured = os.getenv("ARBITOR_LAB_ID", "").strip()
    if configured:
        return configured.upper()
    return "LAB-1"

def domain_of(value):
    raw = value.strip().lower()
    if not raw:
        return ""
    if "://" not in raw:
        raw = "https://" + raw
    parsed = urlparse(raw)
    host = parsed.netloc.strip().split("@")[-1]
    host = host.split(":")[0].strip().lower()
    if host.startswith("www."):
        host = host[4:]
    return host
