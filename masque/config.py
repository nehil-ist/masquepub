"""All server settings, read once from environment variables (same names as the PHP version)."""
import os
from dataclasses import dataclass, field
from pathlib import Path


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def ascii_lower(s: str) -> str:
    """PHP's strtolower(): only A-Z change."""
    return "".join(chr(ord(c) + 32) if "A" <= c <= "Z" else c for c in s)


@dataclass(frozen=True)
class Config:
    root: Path
    data_dir: Path
    port: int = 8080
    post_max: int = 6 * 1024 * 1024  # same as php -d post_max_size=6M
    admin_users: tuple = field(default_factory=tuple)
    mail_key: str = ""               # MAIL_KEY: encrypts the stored recovery emails (same secret as PHP)
    newacct_secs: int = 86400        # NEWACCT_SECS: how long an account counts as "new"
    admin_user: str = ""             # ADMIN_USER exactly as typed (admin_users above is lower-cased)
    admin_password: str = ""         # ADMIN_PASSWORD
    ip_header: str = ""              # IP_HEADER / IP_HOPS: which header holds the visitor IP behind a proxy
    ip_hops: int = 1
    site_url: str = ""               # SITE_URL, BREVO_API_KEY, MAIL_FROM, MAIL_NAME, MAIL_DAILY_MAX, BREVO_URL: recovery email
    brevo_key: str = ""
    mail_from: str = ""
    mail_name: str = "Masque"
    mail_daily_max: int = 250
    brevo_url: str = ""
    contact: str = ""                # CONTACT: shown on the privacy and terms pages
    csp_off: bool = False            # CSP=off turns the page's Content-Security-Policy header off
    backup_keep: int = 7             # BACKUP_KEEP: how many automatic database copies to keep (0 = no automatic backups)
    backup_hours: int = 24           # BACKUP_HOURS: hours between automatic copies
    background: bool = True          # BACKGROUND=off turns the background jobs off (backups, expiry, tidy, reminders)

    @classmethod
    def from_env(cls) -> "Config":
        root = Path(__file__).resolve().parent.parent
        data = Path(os.environ.get("DATA_DIR") or root / "data")
        admins = [ascii_lower(a.strip()) for a in (os.environ.get("ADMIN_USERS") or "").split(",")]
        single = ascii_lower((os.environ.get("ADMIN_USER") or "").strip())
        if single:
            admins.append(single)
        return cls(
            root=root,
            data_dir=data,
            port=_int("PORT", 8080),
            post_max=_int("POST_MAX", 6 * 1024 * 1024),
            admin_users=tuple(a for a in admins if a),
            mail_key=os.environ.get("MAIL_KEY", ""),
            newacct_secs=max(0, _int("NEWACCT_SECS", 86400)),
            admin_user=(os.environ.get("ADMIN_USER") or "").strip(" \t\n\r\0\x0b"),
            admin_password=os.environ.get("ADMIN_PASSWORD", ""),
            ip_header=(os.environ.get("IP_HEADER") or "").strip(),
            ip_hops=max(1, _int("IP_HOPS", 1)),
            site_url=os.environ.get("SITE_URL", "").rstrip("/"),
            brevo_key=os.environ.get("BREVO_API_KEY", ""),
            mail_from=os.environ.get("MAIL_FROM", ""),
            mail_name=os.environ.get("MAIL_NAME") or "Masque",
            mail_daily_max=max(1, _int("MAIL_DAILY_MAX", 250)),
            brevo_url=os.environ.get("BREVO_URL", ""),
            contact=(os.environ.get("CONTACT") or "").strip(" \t\n\r\0\x0b"),
            csp_off=os.environ.get("CSP") == "off",
            backup_keep=max(0, _int("BACKUP_KEEP", 7)),
            backup_hours=max(1, _int("BACKUP_HOURS", 24) or 24),
            background=os.environ.get("BACKGROUND") != "off",
        )

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"

    def ensure_folders(self) -> None:
        """The folders PHP made at start-up: database/photos (up), stickers (stk), link thumbnails (lp), sessions."""
        for name in ("up", "stk", "lp", "sessions"):
            (self.data_dir / name).mkdir(parents=True, exist_ok=True)

    @property
    def session_dir(self) -> Path:
        return self.data_dir / "sessions"
