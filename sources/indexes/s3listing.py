"""S3Objects: the keys of an anonymously listable Amazon S3 bucket under prefixes (ListObjectsV2 over plain
HTTP), as cached by CachedIndex."""

import xml.etree.ElementTree as ET
from typing import Callable, Dict, List, NamedTuple, Optional, Sequence

import requests

import cache
import servicecounts

from .. import net
from ..net import RETRIES
from .cached import IndexUnavailable, Listing

# Amazon S3 API Reference, ListObjectsV2 (https://docs.aws.amazon.com/AmazonS3/latest/API/API_ListObjectsV2.html):
# GET /?list-type=2&prefix=<p>&max-keys=<n> answers a ListBucketResult in this namespace, with a Contents per key
# (Key, LastModified, ETag, Size), IsTruncated and, while truncated, the NextContinuationToken the next page is
# asked with (continuation-token); at most 1000 keys a page. Errors are an <Error> with Code and Message
# (https://docs.aws.amazon.com/AmazonS3/latest/API/ErrorResponses.html); 500 and 503 (SlowDown) are to be retried
S3_NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"
MAX_KEYS = 1000
MAX_PAGES = 1000  # a listing that never ends is an error (every waiting loop has a deadline)


class S3Object(NamedTuple):
    """One listed key: its size in bytes, LastModified (ISO 8601, as S3 gives it) and ETag (without quotes)."""
    key: str
    size: int
    last_modified: str
    etag: str


def _error(body: bytes) -> Optional[str]:
    """Code and message of an S3 <Error> answer (None if body is none)."""
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return None
    if root.tag.split("}")[-1] != "Error":
        return None
    return f"{root.findtext('Code') or '?'}: {root.findtext('Message') or ''}".strip()


def _page(bucket: str, params: Dict[str, str]) -> bytes:
    """One answer of ListObjectsV2 with HTTP 200; server errors (5xx, the connection) asked again up to
    RETRIES times; IndexUnavailable for anything else, an <Error> with HTTP 200 too."""
    url = bucket.rstrip("/") + "/"
    for attempt in range(RETRIES):
        net.rate_turn(url)
        try:
            response = servicecounts.get(url, params=params, timeout=120, headers=cache.http_headers())
        except requests.RequestException as e:
            if attempt == RETRIES - 1:
                raise IndexUnavailable(f"S3 ListObjectsV2: {cache.clean_error(e)}") from e
        else:
            error = _error(response.content)
            if response.status_code == 200 and error is None:
                return response.content
            if response.status_code < 500 or attempt == RETRIES - 1:
                raise IndexUnavailable(f"S3 ListObjectsV2: HTTP {response.status_code} {error or ''}".strip())
        net._sleep(attempt)
    raise AssertionError("unreachable")


def list_objects(bucket: str, prefix: str, max_keys: int = MAX_KEYS) -> List[S3Object]:
    """Every key of bucket (its address, e.g. https://<name>.s3.<region>.amazonaws.com) starting with prefix,
    in S3's order (UTF-8 binary), page by page (max_keys a page) following the continuation tokens.
    IndexUnavailable for an error answer, an answer that is no ListBucketResult, a truncated page without
    a token, a token given twice or more than MAX_PAGES pages: never a shorter listing."""
    found: List[S3Object] = []
    token, seen = None, set()
    for _ in range(MAX_PAGES):
        params = {"list-type": "2", "prefix": prefix, "max-keys": str(max_keys)}
        if token is not None:
            params["continuation-token"] = token
        try:
            root = ET.fromstring(_page(bucket, params))
        except ET.ParseError as e:
            raise IndexUnavailable(f"S3 ListObjectsV2: not XML ({e})") from e
        if root.tag != S3_NS + "ListBucketResult":
            raise IndexUnavailable(f"S3 ListObjectsV2: {root.tag.split('}')[-1]} instead of ListBucketResult")
        for item in root.iter(S3_NS + "Contents"):
            found.append(S3Object(item.findtext(S3_NS + "Key") or "", int(item.findtext(S3_NS + "Size") or 0),
                                  item.findtext(S3_NS + "LastModified") or "",
                                  (item.findtext(S3_NS + "ETag") or "").strip('"')))
        if root.findtext(S3_NS + "IsTruncated") != "true":
            return found
        token = root.findtext(S3_NS + "NextContinuationToken")
        if not token or token in seen:
            raise IndexUnavailable("S3 ListObjectsV2: a truncated page without a new continuation token")
        seen.add(token)
    raise IndexUnavailable(f"S3 ListObjectsV2: more than {MAX_PAGES} pages under {prefix}")


class S3Objects(Listing):
    """The objects of an S3 bucket in one 0.25° tile: the keys under every prefix of prefixes(lat, lon) (the
    caller knows how the keys name places), each made an item by item(object, lat, lon) (None: not used, e.g.
    outside the tile), once per URL, in the order listed."""

    def __init__(self, bucket: str, prefixes: Callable[[float, float], Sequence[str]],
                 item: Callable[[S3Object, float, float], Optional[Dict]], max_keys: int = MAX_KEYS):
        self.url, self.prefixes, self.item, self.max_keys = bucket, prefixes, item, max_keys

    def fetch(self, lat: float, lon: float) -> Dict:
        items: Dict[str, Dict] = {}
        for prefix in self.prefixes(lat, lon):
            for obj in list_objects(self.url, prefix, self.max_keys):
                item = self.item(obj, lat, lon)
                if item is not None:
                    items.setdefault(item["url"], item)
        return {"sheets": list(items.values())}
