"""Usernames: what is allowed, what looks too much like someone else's, what is reserved (PHP: nameok, skel, nameclash, oldcut)."""
import hashlib
import re
import time
import unicodedata

from .config import ascii_lower

# Look-alike letters (Cyrillic / Greek / Latin variants) folded to the plain Latin letter.
_FOLD = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "i", "ј": "j", "ѕ": "s", "ԁ": "d",
    "һ": "h", "ԛ": "q", "ԝ": "w", "к": "k", "м": "m", "н": "h", "т": "t", "в": "b", "ο": "o", "α": "a", "ν": "v",
    "ι": "i", "ρ": "p", "τ": "t", "υ": "u", "κ": "k", "ε": "e", "β": "b", "η": "n", "χ": "x", "ɑ": "a", "ɡ": "g",
    "ǀ": "l",
})


class NameRules:
    RESERVE_SECS = 30 * 86400  # a name someone changed away from stays theirs for 30 days

    def __init__(self, db, admin_names=()):
        self.db = db
        self.admin_names = tuple(admin_names)

    @staticmethod
    def valid(name: str) -> bool:
        return re.fullmatch(r"[A-Za-z0-9_]{3,20}", name) is not None

    @staticmethod
    def skeleton(s: str) -> str:
        """Lower-case, look-alikes folded, everything but letters and digits removed."""
        s = unicodedata.normalize("NFKC", str(s).lower()).translate(_FOLD)
        return "".join(c for c in s if unicodedata.category(c)[0] in "LN")

    @staticmethod
    def digest(name: str) -> str:
        return hashlib.sha256(ascii_lower(name).encode()).hexdigest()

    def reserved(self, name: str) -> bool:
        """Deleted accounts (forever) and names changed away from in the last 30 days."""
        h = self.digest(name)
        if self.db.value("SELECT 1 FROM gone WHERE h=?", (h,)):
            return True
        return bool(self.db.value("SELECT 1 FROM oldnames WHERE ts>? AND h=?", (int(time.time()) - self.RESERVE_SECS, h)))

    def clash(self, candidate: str, self_id: int, include_admins: bool = False) -> bool:
        """True when it looks the same as another user's username or display name, or a Masque name."""
        k = self.skeleton(candidate)
        if k == "":
            return False
        for r in self.db.all("SELECT name,nick FROM users WHERE id!=?", (self_id,)):
            if self.skeleton(r["name"]) == k or (str(r["nick"] or "") != "" and self.skeleton(r["nick"]) == k):
                return True
        for r in self.db.all("SELECT name FROM masks"):
            if self.skeleton(r["name"]) == k:
                return True
        return include_admins and any(self.skeleton(a) == k for a in self.admin_names)


class TextCleaner:
    """Display names and status lines: no control, invisible or bidi characters (they can fake other names), one space between words."""
    NICK_MAX = 24
    STATUS_MAX = 100

    @staticmethod
    def _clean(raw, limit: int):
        s = str(raw)
        if "�" in s:  # PHP's preg_replace(/u) gives null on invalid UTF-8; the web layer shows broken bytes as U+FFFD
            return None
        from .php import collapse_space, php_trim, strip_invisible
        return php_trim(collapse_space(strip_invisible(s)))[:limit]

    @classmethod
    def nick(cls, raw):
        """None when the text is not valid UTF-8."""
        return cls._clean(raw, cls.NICK_MAX)

    @classmethod
    def status(cls, raw):
        return cls._clean(raw, cls.STATUS_MAX)
