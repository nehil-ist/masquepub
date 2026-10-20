"""Actions: one class per ?a=<name> endpoint of the old index.php.

To migrate an action: write a class in this package, decorate it with @registry.register, and import its
module in `load_all()`. Anything not registered keeps going to PHP.
"""
from .base import Abort, Action, ActionRegistry, Context, Reply, registry


def load_all():
    from . import site, account, mail, posts, links, asks, notifs, admin, people, profile, live, unlocks, chats, masques, stickers, groups, groupmanage, rooms, sigils, gifts, manage  # noqa: F401  (importing registers the actions)
    return registry
