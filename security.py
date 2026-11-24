#!/usr/bin/env python3
"""
Security & Input Validation Module for KuroAnime Backend.
Provides:
- Cryptographic session token generation and verification.
- Origin & Referer header validation (prevents DNS rebinding and cross-site request attacks).
- SSRF prevention (strict domain whitelisting and URL validation for wallpaper downloads).
- Input sanitization (regex ID, enum, and payload length checks).
- Standardized structured JSON error formatting.
"""

import re
import secrets
import urllib.parse
from typing import Optional, Dict, Any, Tuple, Set, List

# Allowed domains for external wallpaper downloads (SSRF protection)
ALLOWED_WALLPAPER_DOMAINS: Set[str] = {
    "w.wallhaven.cc",
    "th.wallhaven.cc",
    "wallhaven.cc",
    "127.0.0.1",
    "localhost"
}

# Regex for strict identifier validation (alphanumeric, underscore, hyphen)
RE_IDENTIFIER = re.compile(r"^[a-zA-Z0-9_\-\.]{1,80}$")
RE_TOKEN = re.compile(r"^[a-zA-Z0-9_\-]{8,128}$")

# Maximum permitted POST payload size in bytes (1 Megabyte)
MAX_CONTENT_LENGTH = 1024 * 1024

class SecurityManager:
    def __init__(self):
        # Generate a high-entropy 256-bit server session token on boot
        self.session_token = secrets.token_hex(32)

    def verify_session_token(self, token: Optional[str]) -> bool:
        """
        Constant-time comparison to verify local session token.
        Protects against timing attacks and CSRF from external websites.
        """
        if not token or not isinstance(token, str):
            return False
        return secrets.compare_digest(self.session_token, token.strip())

    @staticmethod
    def is_trusted_origin(origin_or_referer: Optional[str], server_port: int) -> bool:
        """
        Validates that incoming Origin or Referer matches localhost / 127.0.0.1.
        Null/empty origin is trusted (native WebView, direct CLI, file:// wrappers, curl).
        External web domains (e.g. http://evil.com) are strictly rejected.
        """
        if not origin_or_referer:
            return True  # Direct request, same-origin without Origin header, or WebView

        try:
            parsed = urllib.parse.urlparse(origin_or_referer)
            hostname = (parsed.hostname or "").lower()
            if hostname in ("127.0.0.1", "localhost", "::1"):
                return True
            # Reject any other origin (prevents CSRF and DNS rebinding)
            return False
        except Exception:
            return False

    @staticmethod
    def validate_id(identifier: Optional[str]) -> bool:
        """Validates that an ID contains only safe alphanumeric/hyphen/underscore chars."""
        if not identifier or not isinstance(identifier, str):
            return False
        if ".." in identifier or "/" in identifier or "\\" in identifier:
            return False
        return bool(RE_IDENTIFIER.match(identifier))

    @staticmethod
    def validate_token_format(token_str: Optional[str]) -> bool:
        """Validates general token format (UUID or hex string)."""
        if not token_str or not isinstance(token_str, str):
            return False
        return bool(RE_TOKEN.match(token_str))

    @staticmethod
    def validate_download_url(url: Optional[str], known_url: Optional[str] = None) -> bool:
        """
        SSRF Guard: Verifies that a wallpaper URL is safe to download.
        1. If it matches a URL already verified and stored in the database for that ID -> safe.
        2. Otherwise, must use HTTPS (or HTTP for localhost), have an allowed domain, and safe path.
        Arbitrary IP addresses, cloud metadata endpoints, and internal subnets are blocked.
        """
        if not url or not isinstance(url, str):
            return False

        # If it exactly matches the URL previously verified and committed to SQLite
        if known_url and url.strip() == known_url.strip():
            return True

        # Localhost relative API paths are safe
        if url.startswith("/api/image/") or url.startswith("/curated_wallpapers/"):
            return True

        try:
            parsed = urllib.parse.urlparse(url)
            scheme = (parsed.scheme or "").lower()
            hostname = (parsed.hostname or "").lower()

            if scheme not in ("https", "http"):
                return False

            # Disallow private IPs and loopback in remote URL downloads unless specifically localhost
            if hostname in ("169.254.169.254", "0.0.0.0", "metadata.google.internal"):
                return False

            if hostname not in ALLOWED_WALLPAPER_DOMAINS:
                return False

            # Require HTTPS for external domains
            if hostname not in ("127.0.0.1", "localhost") and scheme != "https":
                return False

            return True
        except Exception:
            return False

    @staticmethod
    def sanitize_string(val: Optional[str], max_len: int = 80, default: str = "") -> str:
        """Sanitizes text inputs, trims whitespace, and enforces maximum length."""
        if not val or not isinstance(val, str):
            return default
        cleaned = "".join(ch for ch in val.strip() if ch.isalnum() or ch in " _-().,'+:@")
        return cleaned[:max_len] if cleaned else default

    @staticmethod
    def json_error(code: str, message: str, status: int = 400, details: Any = None) -> Tuple[Dict[str, Any], int]:
        """Generates standard production-grade structured JSON error response."""
        payload = {
            "success": False,
            "error": {
                "code": code,
                "message": message,
                "status": status
            }
        }
        if details is not None:
            payload["error"]["details"] = details
        return payload, status
