"""The interface's words against docs/DESIGN.md's R9 and R10 (step 3d, group G5: the user's answers of 2026-11-21 on
the wording review, docs/DESIGN.md choices 92 to 94).

- R10: no catalogue text over its kind's limit (a help text 40 words, an intro paragraph 30, a hint 25, an error 30,
  words split on spaces), by its key's kind (tools/ui_metrics.py `text_group`) and, for the texts whose key does not
  say their kind, by their role (BY_ROLE); today's result page keeps its intro (LEFT).
"""

import json
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))
import ui_metrics  # noqa: E402


def catalogue(rel: str = "locales/en.json") -> dict:
    with open(os.path.join(REPO, rel), encoding="utf-8") as f:
        return json.load(f)


LIMITS = {"help": 40, "intro": 30, "hint": 25, "error": 30}
# Texts whose key does not say their kind: (catalogue, key) -> the limit of their role
BY_ROLE = {
    ("locales/en.json", "ui.search.draw_hint"): 25,          # a hint under the drawing tools
    ("locales/en.json", "ui.osm.intro"): 30,                  # the OSM page's intro paragraph
    ("locales/en.json", "ui.access.easy_means"): 40,          # rows of the access key's "?"
    ("locales/en.json", "ui.access.cannot_tell_means"): 40,
    ("locales/en.json", "ui.access.hard_means"): 40,
    ("locales/en.json", "ui.layer.scale_fit_note"): 25,       # the layer's notes
    ("locales/en.json", "ui.layer.scale_fixed_note"): 25,
    ("locales/en.json", "ui.layer.hist.strip_note"): 25,
    ("locales/en.json", "ui.layer.search_border"): 25,
    ("locales/en.json", "ui.layer.search_border_any"): 25,
    ("locales/en.json", "ui.layer.search_partner"): 25,
    ("locales/en.json", "ui.layer.search_partner_any"): 25,
    ("locales/coverage/en.json", "page.lead"): 30,            # the coverage page's lead
    ("locales/coverage/pl.json", "page.lead"): 30,
}
# Over a limit on purpose: {key: why}
LEFT = {"intro.result.spots": "today's result page (the user, 2026-11-19: it goes with line volume's round 6)",
        "intro.result.filters": "today's result page (as above)",
        "intro.result.check": "today's result page (as above)"}


def test_catalogue_texts_within_their_limit():
    over = [(k, ui_metrics.text_group(k), len(v.split())) for k, v in catalogue().items()
            if ui_metrics.text_group(k) in LIMITS and k not in LEFT and len(v.split()) > LIMITS[ui_metrics.text_group(k)]]
    assert over == [], over
    assert all(ui_metrics.text_group(k) in LIMITS for k in LEFT)  # a key named here is one the rule reads


@pytest.mark.parametrize("rel,key", sorted(BY_ROLE))
def test_texts_by_role_within_their_limit(rel, key):
    text = catalogue(rel)[key]
    assert len(text.split()) <= BY_ROLE[(rel, key)], (key, len(text.split()), text)
