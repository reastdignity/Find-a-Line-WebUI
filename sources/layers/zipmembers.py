"""ZipMemberTiles: square tiles that are members of remote ZIP archives, read one member at a time by HTTP Range
(LVGL Saarland's district archives of the DGM1 and DOM1)."""

import glob
import os
import threading
from typing import Optional, Sequence

import requests

import cache

from ..indexes.metalink import MetalinkIndex
from ..indexes.zipdir import ZipDirectories, ZipPerTile, ZipTile
from ..readers.zipmember import ZipMember
from .indexed import IndexedTiles
from .metalink import MetalinkTiles


class ZipMemberTiles(MetalinkTiles):
    """Square tiles of tile_m on a metric grid, each a member (a GeoTIFF) of one of the remote ZIP archives
    that hold the region: archives, their URLs in the order of their precedence ("{token}" where share's token
    goes: ZipDirectories), name, a regular expression of the members' names with the groups east and north (in
    tile_m units of crs) and year if they carry one. The archives' central directories are read by Range once
    per TTL and kept (ZipDirectories); a member is known by its CRC-32 (ZipPerTile: a changed member is read
    again) and read by one Range of its local header and data (ZipMember). Cached in
    <folder>/<east // 10>_<north // 10>/<east>_<north>[_<year>]_<crc8>.tif.

    floor and ring are ZipMember's: pixels below floor, and those within ring pixels of one, made no data when
    the tile is written (a survey's artifact; the source's gap filler fills them). A 404 of an archive or a
    member not where its directory said makes the directories be read again (the share's token resolved again)
    and the member tried once more from there; the 0.25° answers are forgotten then, so they are made again from
    the new directories."""

    def __init__(self, description: str, archives: Sequence[str], name: str, folder: str, crs: str, prefix: str,
                 share: Optional[str] = None, native_res: float = 1.0, tile_m: float = 1000,
                 bytes_per_tile: float = 2e6, floor: Optional[float] = None, ring: int = 0):
        IndexedTiles.__init__(self, description, share or archives[0], prefix, folder, native_res=native_res,
                              bytes_per_tile=bytes_per_tile)
        self.metalinks, self.name, self.index_crs, self.crs, self.tile_m = tuple(archives), name, crs, crs, tile_m
        self.average, self.force_crs, self.share, self.floor, self.ring = 1, None, share, floor, ring
        top = folder.split("/")[0]
        self.listing = ZipDirectories(archives, name, crs, native_res, top, prefix, tile_m, share)
        self.index = MetalinkIndex(description, self.listing, ZipPerTile(folder, crs, tile_m), prefix, top)
        self.reader = ZipMember(description, crs=crs, floor=floor, ring=ring, renew=self._renew)
        self._renew_lock = threading.Lock()

    def _current(self, tile: ZipTile) -> Optional[ZipTile]:
        """The tile's member as the kept directories list it now (the same CRC-32), or None."""
        for item in self.listing.table():
            if item["godlo"] == tile.godlo and item["year"] == tile.year:
                found = ZipPerTile.tile(item)
                return found if found.key == tile.key else None
        return None

    def _renew(self, tile: ZipTile) -> Optional[ZipTile]:
        """After a 404 or a moved member: the member where the directories, read again, say it is now (None
        when they say the same, or list it no more). The 0.25° answers are forgotten, so the next ones are made
        from the new directories."""
        cache_dir = self.index.cache_dir
        if not cache_dir:
            return None
        with self._renew_lock:
            try:
                current = self._current(tile)
                if current is None or (current.url, current.offset) == (tile.url, tile.offset):
                    answers = glob.glob(os.path.join(cache_dir, self.listing.top, "sheet-index", self.prefix,
                                                     "*.json"))
                    try:
                        cache.forget(cache_dir, answers)
                    except OSError:  # another process forgot them now
                        pass
                    self.index._listed.clear()
                    self.listing.table(force=True)
                    current = self._current(tile)
            except requests.RequestException as e:
                print(f"{self.description}: the archives' directories cannot be read again ({type(e).__name__})")
                return None
        if current is None or (current.url, current.offset) == (tile.url, tile.offset):
            return None
        return current
