"""Readers: how one tile, file or block is fetched into the cache (see sources/composed.py), a module each."""

# The first bytes of a TIFF (little- or big-endian; BigTIFF too): an answer of a service that makes rasters
# (WMS-R, ImageServer) is data only when it starts with one of them
TIFF_MAGIC = (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+")
