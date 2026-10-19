"""All query-key routes, in the order index.php checked them (manifest, page, sw, ogdiag, ogp, og, stk, lpi, img)."""
from .base import FileBody, Route, RouteTable
from .cards import CardDiagnosticsRoute, PostCardRoute, ProfileCardRoute
from .pages import LegalRoute, ManifestRoute, ServiceWorkerRoute, ShellRoute
from .files import LinkThumbRoute, StickerRoute, UploadRoute


def load_routes() -> RouteTable:
    table = RouteTable()
    for cls in (ManifestRoute, LegalRoute, ServiceWorkerRoute, CardDiagnosticsRoute, PostCardRoute, ProfileCardRoute, StickerRoute, LinkThumbRoute, UploadRoute):
        table.add(cls())
    return table
