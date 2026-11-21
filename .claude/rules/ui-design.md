---
paths:
  - "viewer/src/**/*.tsx"
  - "viewer/src/**/*.css"
  - "locales/en.json"
  - "docs/DESIGN.md"
  - "docs/PRODUCT.md"
  - "docs/design-review.md"
---
# UI design: who the interface is for, its rules, its review

- Before changing a screen, a text the user reads or a style: read docs/PRODUCT.md (the users, the aims, the
  principles), docs/DESIGN.md (part 1: the tokens and the kit as built; part 2: the rules the user picked) and
  docs/design-review.md (what the design reviewer checks).
- Only the rules DESIGN.md marks in force bind. They bind new and changed screens; today's screens are brought to
  them in the improvement rounds. Never set or move a threshold yourself: measure, show the alternatives, the user
  picks.
- Colours and other values come from viewer/src/ui/tokens.css; font sizes, radii and spacing from DESIGN.md's
  scales where a rule in force names one (R5 to R7); a value off them needs a reason in a comment.
- The anchors stay: the logo, Barlow Condensed headings, the magenta line, the accepted layouts. The rest of the
  look changes only through a mock-up the user accepted; its decisions go into DESIGN.md in the same branch.
- Words: docs/wording.md (the words to use and not to use, the characters written out, the style rules by link);
  a word changes only with the user's yes, as a row with its source; `tests/test_words.py` reads its "Not" column.
- A screen's change goes to the design reviewer with the numbers of tools/ui_metrics.py and tools/ui_walks.py
  before and after and its screenshots on the desktop and both phones, light and dark (DESIGN.md, R12).
