"""?a=lpv: the preview of a link posted in a chat."""
from ..linkpreview import LinkPreviews
from ..ogcard import pillow_ready
from .base import Action, Context, Reply, registry


@registry.register
class LinkPreview(Action):
    """PHP: case 'lpv'"""
    name = "lpv"
    fetcher = None  # tests swap in a fake fetcher here

    def handle(self, ctx: Context) -> Reply:
        m = ctx.users.need()
        url = ctx.arg("lu").strip(" \t\n\r\0\x0b")
        if url == "" or len(url.encode()) > 600 or not url.lower().startswith(("http://", "https://")):
            return Reply({"none": 1})
        return Reply(LinkPreviews(ctx, self.fetcher, pillow_ready()).lookup(m, url))
