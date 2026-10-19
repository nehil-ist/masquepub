"""Small helpers that behave like the PHP functions the old code leaned on (so answers stay the same)."""
import re
import unicodedata

_INT_RE = re.compile(r"^[ \t\n\r\v\f]*([+-]?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?|[+-]?\.\d+(?:[eE][+-]?\d+)?)")


def empty(v) -> bool:
    """PHP empty(): '', '0', 0, None, False and empty lists are empty."""
    return v is None or v is False or v == "" or v == "0" or v == 0 or v == [] or v == {}


def intval(v, default: int = 0) -> int:
    """PHP (int)$x for request values: '12abc' is 12, 'abc' is 0, '1e3' is 1000."""
    if v is None:
        return default
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        try:
            return int(v)
        except (ValueError, OverflowError):
            return 0
    m = _INT_RE.match(str(v))
    if not m:
        return 0
    tok = m.group(1)
    try:
        if re.fullmatch(r"[+-]?\d+", tok):
            return max(-9223372036854775808, min(9223372036854775807, int(tok)))
        return int(float(tok))
    except (ValueError, OverflowError):
        return 0


def clamp_int(v, lo: int, hi: int) -> int:
    return max(lo, min(hi, intval(v)))


def strip_controls(s: str) -> str:
    """preg_replace('/[\\x00-\\x08\\x0B\\x0C\\x0E-\\x1F]/', '', $s)"""
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", s)


def collapse_space(s: str) -> str:
    """preg_replace('/\\s+/u', ' ', $s)"""
    return re.sub(r"\s+", " ", s)


def strip_invisible(s: str) -> str:
    """preg_replace('/[\\p{C}\\p{Zl}\\p{Zp}]/u', '', $s): control, format, private, unassigned characters and line/paragraph separators."""
    return "".join(c for c in s if unicodedata.category(c)[0] != "C" and unicodedata.category(c) not in ("Zl", "Zp"))


def php_trim(s) -> str:
    return str(s).strip(" \t\n\r\0\x0b")


def like_escape(s: str) -> str:
    """Escapes a value for LIKE ... ESCAPE '\\'."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def in_marks(n: int) -> str:
    return ",".join("?" * n)


def ids_sql(ids) -> str:
    """A safe 'IN (...)' list from integers (like implode(',', array_map('intval', ...)))."""
    return ",".join(str(int(i)) for i in ids)
