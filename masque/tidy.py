"""Removes rows that point at things that no longer exist (PHP: tidy() and rxtidy())."""

_STEPS = (
    "DELETE FROM mreact WHERE (k='d' AND mid NOT IN (SELECT id FROM messages)) OR (k='g' AND mid NOT IN (SELECT id FROM gmessages)) OR uid NOT IN (SELECT id FROM users)",
    "DELETE FROM saves WHERE pid NOT IN (SELECT id FROM posts)",
    "DELETE FROM postviews WHERE pid NOT IN (SELECT id FROM posts)",
    "DELETE FROM pstreak WHERE uid NOT IN (SELECT id FROM users)",
    "DELETE FROM sfreeze WHERE uid NOT IN (SELECT id FROM users)",
    "DELETE FROM polls WHERE pid NOT IN (SELECT id FROM posts)",
    "DELETE FROM pollrx WHERE pid NOT IN (SELECT id FROM posts)",
    "DELETE FROM pollmeta WHERE pid NOT IN (SELECT id FROM posts)",
    "DELETE FROM pushsubs WHERE uid NOT IN (SELECT id FROM users)",
    "DELETE FROM pedits WHERE pid NOT IN (SELECT id FROM posts)",
    "DELETE FROM pollvoted WHERE pid NOT IN (SELECT id FROM posts) OR uid NOT IN (SELECT id FROM users)",
    "DELETE FROM mreveals WHERE uid NOT IN (SELECT id FROM users) OR fid NOT IN (SELECT id FROM users) OR uid NOT IN (SELECT uid FROM masks)",
    "DELETE FROM mblocks WHERE a NOT IN (SELECT id FROM users) OR kid NOT IN (SELECT id FROM masks)",
    "DELETE FROM postimgs WHERE pid NOT IN (SELECT id FROM posts)",
    "DELETE FROM comments WHERE par>0 AND par NOT IN (SELECT id FROM comments)",
    "DELETE FROM clikes WHERE cid NOT IN (SELECT id FROM comments)",
    "DELETE FROM dislikes WHERE pid NOT IN (SELECT id FROM posts) OR uid NOT IN (SELECT id FROM users)",
    "DELETE FROM cdislikes WHERE cid NOT IN (SELECT id FROM comments) OR uid NOT IN (SELECT id FROM users)",
    "DELETE FROM posttags WHERE pid NOT IN (SELECT id FROM posts)",
    "DELETE FROM notifs WHERE kind NOT IN ('gift','gment','gall') AND pid>0 AND pid NOT IN (SELECT id FROM posts)",
    "DELETE FROM notifs WHERE kind IN ('gment','gall') AND pid NOT IN (SELECT id FROM gchats)",
    "DELETE FROM reports WHERE kind='post' AND tid NOT IN (SELECT id FROM posts)",
    "DELETE FROM reports WHERE kind='comment' AND tid NOT IN (SELECT id FROM comments)",
    "DELETE FROM reports WHERE kind='ask' AND tid NOT IN (SELECT id FROM asks)",
    "DELETE FROM reports WHERE kind='mask' AND tid NOT IN (SELECT id FROM masks)",
    "DELETE FROM asks WHERE hid=1 AND id NOT IN (SELECT tid FROM reports WHERE kind='ask')",
    "DELETE FROM stkfav WHERE uid NOT IN (SELECT id FROM users)",
)


class Tidy:
    def __init__(self, db):
        self.db = db

    def reactions(self):
        """PHP rxtidy(): only the reaction clean-up (after a group is deleted)."""
        self.db.execute(_STEPS[0])

    def run(self):
        for sql in _STEPS:
            self.db.execute(sql)
