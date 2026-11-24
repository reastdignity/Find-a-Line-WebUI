"""A run's record of the data it read (`identity`: run.json's data entries, its area and its top level; the
checksums from the cache's index), offline: the merge of a layer's entries, the one exit that drops the key, the
coastline's and the area's inputs, local files, a resumed tiled search."""

import search
import sources as src

A, B, C = "a" * 64, "b" * 64, "c" * 64


def _merged(entries, monkeypatch):
    monkeypatch.setattr(src.mosaic, "used_data", entries)
    monkeypatch.setattr(src, "used_data", entries)
    return search._merged_data()


def test_merging_keeps_the_checksums_in_step(monkeypatch):
    """search._merged_data unites the paths of a layer's entries and keeps `identity.sha256` parallel to them: a
    path met with two different checksums gets null, also when a third entry knows one of them; a checksum one
    entry knows and the other does not (null) is kept; an entry of before without `identity` counts as not
    known; entries without paths and without `identity` merge as before."""
    first = {"layer": "T", "folder": "f", "files": 2, "paths": ["f/1", "f/2"], "identity": {"sha256": [A, None]}}
    second = {"layer": "T", "folder": "f", "files": 2, "paths": ["f/2", "f/3"], "identity": {"sha256": [B, C]}}
    third = {"layer": "T", "folder": "f", "files": 1, "paths": ["f/3"], "identity": {"sha256": [A]}}
    again = {"layer": "T", "folder": "f", "files": 1, "paths": ["f/3"], "identity": {"sha256": [C]}}
    (merged,) = _merged([first, second], monkeypatch)
    assert merged["paths"] == ["f/1", "f/2", "f/3"] and merged["files"] == 3
    assert merged["identity"] == {"sha256": [A, B, C]}
    (merged,) = _merged([first, second, third, again], monkeypatch)
    assert merged["identity"] == {"sha256": [A, B, None]}  # f/3 met with C and A: changed in the run
    old = {"layer": "T", "folder": "f", "files": 1, "paths": ["f/0"]}
    (merged,) = _merged([old, second], monkeypatch)
    assert merged["paths"] == ["f/0", "f/2", "f/3"] and merged["identity"] == {"sha256": [None, B, C]}
    plain = [{"layer": "T", "folder": "f", "files": 1, "paths": ["f/0"]},
             {"layer": "T", "folder": "f", "files": 1, "paths": ["f/1"]}]
    assert _merged(plain, monkeypatch) == [{"layer": "T", "folder": "f", "files": 2, "paths": ["f/0", "f/1"]}]
    coast = {"layer": "OSM", "credit": {"data": "OSM"}, "identity": {"edition": "2026-10-23"}}
    assert _merged([coast, dict(coast)], monkeypatch) == [coast]
    assert first["identity"] == {"sha256": [A, None]}  # the record itself is never changed
