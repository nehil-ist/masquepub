"""Comments on your own posts that you hid: by person (kind 'u') or by word (kind 'w') (PHP: muteHit)."""
import re


class MuteList:
    def __init__(self, db):
        self.db = db
        self._cache = {}

    def _load(self, owner: int):
        if owner not in self._cache:
            users, words = set(), []
            for r in self.db.all("SELECT kind,val FROM mutes WHERE uid=?", (owner,)):
                if r["kind"] == "u":
                    try:
                        users.add(int(r["val"]))
                    except ValueError:
                        users.add(0)
                else:
                    words.append(str(r["val"]))
            self._cache[owner] = (users, words)
        return self._cache[owner]

    def hits(self, owner, commenter, text) -> bool:
        """True when `owner` muted this commenter, or a word in the text."""
        users, words = self._load(int(owner))
        if int(commenter) in users:
            return True
        for w in words:
            if re.search(r"(?<![^\W_])%s(?![^\W_])" % re.escape(w), str(text), re.I):
                return True
        return False
