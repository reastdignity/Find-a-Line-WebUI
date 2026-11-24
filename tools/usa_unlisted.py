"""The copy shipped with the code of the list of the USA's 1 m DEM files that USGS's bucket holds and the TNM index
does not list (sources/catalogue/usa_unlisted_1m.json): made by the same function as a renewal makes the cached list
(sources.layers.tnmbucket.make_unlisted), so a machine that never renewed the list (a fresh install, the public
site before its first `cache update usa`) still sees those files.

One run lists the bucket's 1 m projects (about 990 requests), the TNM index over the USA and its territories (about
420 requests, about 620 MB of answers) and reads the header of each unlisted file whose name carries no UTM zone
and whose project does not tell it (about 300 small reads), each part 4 requests at a time (tnmbucket.REQUESTS_AT_ONCE:
481 s on 2026-11-23, the bucket 196 s and 53 MB, the index 250 s and 620 MB, the headers 35 s; one at a time it took
1947 s). Every request has the app's User-Agent and a slot of its host (the
locks of the cache folder given). Nothing is written when a step fails. It refuses a list when the index lists
clearly fewer files than the list before (tnmbucket.MAX_LISTED_DROP): check the index, then --allow-drop (a
renewal also accepts it by itself when a listing a day later agrees). With --cached it renews the list of the cache
folder given instead (its usa/sheet-index/bucket1m/unlisted.json, with its row) through the renewal's own step
(sources.renewal.renew_list, forced: what left the list is decided, files the index lists now carried; a failure
record of an earlier try is cleared first, a person asked): the way to accept
a real shrink at once on an installed machine (--cached --allow-drop --cache <its cache folder>); without a shrink
`findaline.py cache update --all usa` does the same. Like every renewal it makes nothing while
FINDALINE_USA_UNLISTED_RENEW is off. It prints
what it did, the projects whose files took their upload year (no year in their folders, no listed file) and the
files left out. Run it again before a release (the copy goes stale between releases), check its counts against the
last run and commit the file.

    uv run tools/usa_unlisted.py [--cache <cache folder for the host slots>]
                                 [--out sources/catalogue/usa_unlisted_1m.json | --cached] [--allow-drop]
                                 [--bucket <URL> --api <URL>: another bucket and index, e.g. a stand-in of the tests]
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)


def main(argv=None) -> int:
    from sources.layers import tnmbucket
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cache", default=os.path.join(HERE, "cache"),
                        help="the cache folder whose locks hold the host slots (default: the repository's cache)")
    parser.add_argument("--out", default=tnmbucket.SHIPPED, help="the file written (default: the shipped copy)")
    parser.add_argument("--cached", action="store_true",
                        help="write the cache folder's own list (with its row) instead of --out")
    parser.add_argument("--allow-drop", action="store_true",
                        help="write the list also when the index lists clearly fewer files than the list before")
    parser.add_argument("--bucket", default=tnmbucket.BUCKET, help="the bucket's address")
    parser.add_argument("--api", default=tnmbucket.TNM_API, help="the TNM Access API's products address")
    args = parser.parse_args(argv)
    if args.cached:
        return _cached(args)
    done = tnmbucket.make_unlisted(args.cache, out=args.out, bucket=args.bucket, api=args.api,
                                   allow_drop=args.allow_drop)
    print(json.dumps({k: v for k, v in done.items() if k not in ("left_out", "upload_year_projects")}, indent=1))
    print(f"dated by their upload ({done['year_from_upload']} files):",
          ", ".join(done["upload_year_projects"]) or "-")
    print(f"left out ({len(done['left_out'])}):", ", ".join(done["left_out"]) or "-")
    return 0


def _cached(args) -> int:
    """--cached: the cache folder's list renewed by the renewal's list step (forced), never written past it: a list
    written straight in place would skip the departures and the carried files."""
    import sources as src
    from sources import renewal
    from sources.layers import tnmbucket
    layer = src.SOURCES["usa"].nmt
    if args.api != layer.index.listing.url or args.bucket != tnmbucket.BUCKET:  # a stand-in: a layer of its own
        layer = src.Usgs1mBlocks(layer.description, layer.dataset, layer.prefix, layer.folder, layer.native_res,
                                 layer.block_m, layer._bytes, api=args.api)
        layer.index.bucket = args.bucket
    tnmbucket.clear_failed(args.cache)
    done = renewal.renew_list(layer, args.cache, print, force=True, allow_drop=args.allow_drop)
    print(json.dumps(done.as_dict(), indent=1))
    return 0 if done.list == "made" else 1


if __name__ == "__main__":
    from progress import utf8_output
    utf8_output()
    sys.exit(main())
