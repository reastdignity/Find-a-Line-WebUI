# Product: who Find-a-Line is for and what its interface aims at

**Status: a draft (2026-11-16), not in force.** Written for the UX and UI design task from the user's recorded
answers of 2026-11-16, quoted as given. A sentence marked *proposed* has no source in those answers: it is the
draft's reading and waits for the user's word. Its companion, [DESIGN.md](DESIGN.md), describes the look as the code
has it and proposes rules; neither file sets a colour or a font.

## Who uses it, and where

- **The experienced rigger at a desk** (the main user). *Proposed* description: runs many searches, edits and
  repeats them, compares lines, saves and shares them; works with a mouse and a keyboard.
- **The first-timer on a phone** (the guard). *Proposed* description: signs in for the first time, runs a first
  search and tries to understand the result, without knowing yet what the app's words mean.
- The user's decision when their needs conflict: "Aim is to be good tool for 3. but also not scare 1." (3 = the
  rigger at a desk, 1 = the first-timer on a phone.) Being outdoors at the spot was offered and not picked.

## What the app is for

Finding possible highlines in elevation data: anchors on steep ground, every pair checked for clearance under the
webbing, the results on a map with a list, a profile and a 3D view, for the athlete to judge and then check on the
spot. The search's results are not a design matter: the interface shows them, it never changes them.

## The aims, most important first (the user's words)

1. "Improve ease of use - the more natural to use - the better"
2. "Improve UI on phones"
3. "Improve design languege"
4. "make the UI less Claude Code style"

## The three tells to remove (aim 4)

The user's words for what makes the interface look "Claude Code style": "Same grey box everywhere, Long explaining
texts, Symbols and dense strings". A fourth tell was offered and not picked, monospace capital labels; outdoor
legibility, offered as a part of visibility, was not picked either. On those two the user said: "They are not main
target, might be done addiotionally".

## What stays

"Keep anchors, open the rest". The option the user picked named the anchors: the logo, the Barlow Condensed
headings, the magenta line colour and the accepted layouts (the C frame of list, map and details, the phone's sheet,
the Basic form); the result view of mock-up 2, version 7, accepted on 2026-11-14 (docs/roadmap.md, "Decisions"), is
one of them too. Open, and settled on mock-ups the user accepts, not here: the body font, the accent and surface
colours, shapes, spacing and the label style.

## Principles

Each traced to its source. *Proposed* marks a reading with no source in the user's answers.

1. **A working tool for the rigger first.** Density, speed and depth stay; the desktop is where the work is done.
   Source: "Aim is to be good tool for 3."
2. **Depth moves, it is not removed.** What a first-timer does not need yet sits one step away (a fold, a second
   tab, a "?"), never deleted. Source: "but also not scare 1."; the step-away form is *proposed*.
3. **Calm first screens.** A first-timer's way to a first search and a first result shows few choices at once and
   few words before the first action. Source: "not scare 1", "Long explaining texts".
4. **Natural before clever.** A control does what it looks like; the words are the ones a highliner uses.
   Source: "the more natural to use - the better". The wording rule already in force (docs/roadmap.md, UI texts,
   2026-10-30: simplified technical English with highliners' words, a "?" on every setting) is an earlier decision
   of the user, not of this task.
5. **Phones are not a shrunk desktop.** Every flow works with a thumb, on a small screen, with nothing cut off.
   Source: "Improve UI on phones".
6. **Importance decides the container.** Not every group gets the same raised grey box; what matters most is set
   apart, the rest sits on the page. Source: "Same grey box everywhere".
7. **Short texts, explanation on demand.** A text says what the user needs at that moment; the longer story is
   behind a link or a "?". Source: "Long explaining texts".
8. **Words and labelled values, not symbols.** A value is written with its label and unit; characters do not stand
   in for words or icons. Source: "Symbols and dense strings".
9. **Visible means four things**: "Important things stand out, Readable text, Lines on the map, Avoid such things
   as labels overlapping etc." (the user's definition of visibility).
10. **Measure before a rule.** A threshold is picked by the user from measured alternatives, never guessed.
    Source: docs/agent-workflow.md, "Measure before a rule" (the user's standing rule, not an answer of this task).

## Three kinds of surface (*proposed*)

- **The sign-in page persuades**: it shows what the app finds before it asks for an account.
- **The app is a tool** (home, search, result, 3D view, favourites, account): scannable, familiar, consistent,
  fast to repeat.
- **Privacy, about and the intros are for reading**: a comfortable line length and size, read once.

## Accessibility bar (*an assumption the user has not confirmed*)

WCAG 2.2 level AA on the main flows (sign-in, search, result), checked with an automated scan on the rendered pages
and a keyboard pass. The map canvas is a named exception: the list of lines is its accessible alternative.

## Not targets

- Outdoor legibility and monospace capital labels: secondary ("They are not main target, might be done
  addiotionally"): measured, improved where a round touches them anyway, never the reason for a round.
- A new visual identity: the anchors above stay.
- The search, its results, its stored data: untouched by design work.
- New tracking of visitors for measuring ease of use (*proposed*: none without privacy wording the user approves
  first).
