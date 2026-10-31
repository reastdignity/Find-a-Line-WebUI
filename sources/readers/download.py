"""Download: a tile that is a whole file at a URL, saved as it comes (checked against its sha256 if known)."""

import hashlib
import os
from typing import Callable, Optional, Sequence

from .. import net
from ..net import RETRIES, _part
from ..layer import Fetched
from ..composed import Reader


class Download(Reader):
    """One GET per tile (net._get, with its retries), the answer saved as the tile; a tile the
    service does not have (404) is missing. With sha256 (of a tile: the digest its index
    gives, or None), a file that does not match is asked again (RETRIES times, with backoff)
    and never kept.

    url_of gives a tile's URL; label names it in messages ("tile 50,19")."""

    def __init__(self, description: str, url_of: Callable[[object], str], label: Callable[[object], str],
                 binary_types: Optional[Sequence[str]] = None,
                 sha256: Optional[Callable[[object], Optional[str]]] = None):
        self.description, self.url_of, self.label = description, url_of, label
        self.binary_types, self.sha256 = binary_types, sha256

    def url(self, tile) -> Optional[str]:
        return self.url_of(tile)

    def fetch(self, tile, path: str) -> Fetched:
        url = self.url_of(tile)
        expected = self.sha256(tile) if self.sha256 else None
        for attempt in range(RETRIES):
            try:
                response = net._get(url) if self.binary_types is None else \
                    net._get(url, binary_types=tuple(self.binary_types))
            except RuntimeError as e:
                raise RuntimeError(f"Could not download {self.description} {self.label(tile)}: {e}")
            if response is None:  # no tile there (sea)
                return Fetched(0, url)
            if not expected or hashlib.sha256(response.content).hexdigest() == expected:
                break
            net._sleep(attempt)
        else:
            raise RuntimeError(f"{self.description} {self.label(tile)}: wrong checksum")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = _part(path)
        with open(tmp, "wb") as f:
            f.write(response.content)
        os.replace(tmp, path)
        return Fetched.of(response, url)
