"""Who is around: presence dots and the short status line (PHP: pres, stxt, MQ_AWAY)."""
import time

AWAY = 900  # a page only checks in while it is on screen; for 15 minutes after the last check-in someone shows as idle, then offline
STATUS_SECS = 86400  # a status line disappears after 24 hours


class Presence:
    """la = last check-in, idl = the page said the person is quiet, pst = their own choice ('' auto, online, idle, lurk, off)."""

    @staticmethod
    def state(row) -> str:
        row = row or {}
        pst = row.get("pst") or ""
        ago = int(time.time()) - int(row.get("la") or 0)
        if pst == "off" or ago > AWAY:
            return "off"
        if ago > 45:
            return "idle"
        if pst == "lurk":
            return "lurk"
        if pst == "idle":
            return "idle"
        if pst == "online":
            return "on"
        return "idle" if row.get("idl") else "on"

    @staticmethod
    def status_text(row) -> str:
        t = str(row.get("stx") or "")
        return t if t != "" and int(row.get("stts") or 0) > int(time.time()) - STATUS_SECS else ""
