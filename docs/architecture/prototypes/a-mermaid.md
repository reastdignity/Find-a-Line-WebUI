# Prototype A: Mermaid in Markdown

One Markdown file per level, the diagrams as Mermaid blocks. GitHub renders them in README, issues and
wikis without any tool; a diff shows what changed; a test can read every block and check that the names
in it exist in the code. The same slice of the system is drawn in prototypes B and C in other forms.

## 1. A search, in plain words

Every search answers one question: where could a highline go? The steps are the same whether you
start it from the command line, in the browser, or over a whole country.

```mermaid
flowchart LR
    place["A place and a radius<br/>(or a drawn area)"] --> heights["Fetch the height map:<br/>the ground, and the treetops and roofs"]
    heights --> steep["Mark the steep pixels:<br/>the possible anchors"]
    steep --> pairs["For every pair of anchors:<br/>does the line clear the ground<br/>and the trees everywhere?"]
    pairs --> lines["The lines that pass:<br/>map coordinates, nearby ones grouped,<br/>a profile for each"]
    lines --> map["A map and a list,<br/>saved with the data credits"]
    pairs -. "a whole country:<br/>count the lines per km²<br/>instead of keeping them" .-> layer["A map layer<br/>of counts"]
    classDef plain fill:#e1e8fa,stroke:#2350c8,color:#17201c
    classDef fork fill:#fbefd9,stroke:#995500,color:#17201c
    class place,heights,steep,pairs,lines,map plain
    class layer fork
```

## 2. A search, step by step

The five steps are the ones printed as `Step n/5` (`search._step`). The download phase and the compute
phase are the two processes of a web job; the command line runs them one after the other in one process.

```mermaid
flowchart TD
    subgraph plan["Planning"]
        P1["plan_search<br/>area, source (choose_source), grid, tiles?"] --> P2["estimate_search<br/>tiles to download, Mpx, memory"]
        P2 --> Q{"over CONFIRM_MINUTES?"}
        Q -- "yes: ask (confirm)" --> P3["go on or stop"]
    end
    subgraph download["Download phase"]
        D1["download_data<br/>download_layers: terrain, surface, water mask tiles<br/>+ coastline theme tiles, place name"]
    end
    subgraph compute["Compute phase: search_lines"]
        S1["Step 1/5 downloading elevation data<br/>prepare_data: mosaics, sea mask, shore from the surface,<br/>water and gaps filled, obstacles, terrain statistics"]
        T{"one grid or tiles?<br/>(tile_core_size from the memory budget)"}
        S2["Step 2/5 finding significant slopes<br/>_anchors: slope ≥ threshold (60°), elevation band,<br/>prominence and drop, ANCHORS_MAX"]
        S3["Step 3/5 evaluating anchor pairs<br/>find_valid_lines: free directions → pairs →<br/>_line_ok → _evaluate; early check at lines_max / memory"]
        S4["Step 4/5 coordinates, groups and profiles<br/>line_coordinates, group_lines, line_profiles"]
        TL["per tile: _tile_data → _lines(core) → tiles/k.npz<br/>then LineTable.join, groups of all tiles,<br/>profiles at tile edges"]
    end
    subgraph save["Step 5/5 saving the run and the map"]
        S5["save_run → runs/&lt;run&gt;/<br/>lines.csv, lines.geojson, run.json, ATTRIBUTION.txt,<br/>map.html + data.js + lines.js (saving.py children ≥ 100 000 lines)"]
        O["download_orthophoto<br/>the best groups' tiles, after done"]
    end
    P1 --> P2
    Q -- no --> D1
    P3 --> D1
    D1 --> S1
    S1 --> T
    T -- "one grid" --> S2 --> S3 --> S4 --> S5
    T -- "tiles: prepare_data(strips=True) once" --> TL --> S5
    S5 --> O
    classDef step fill:#e1e8fa,stroke:#2350c8,color:#17201c
    classDef q fill:#fbefd9,stroke:#995500,color:#17201c
    classDef file fill:#e0f1e6,stroke:#1d7a47,color:#17201c
    class P1,P2,P3,D1,S1,S2,S3,S4,TL step
    class Q,T q
    class S5,O file
```

## 3. Where the country layer forks off

The country layer (`findaline.py country run <id>`) shares steps 1 to 3 with a search and replaces
steps 4 and 5 by counting. Each band (S 1 m, M 2 m, L 5 m) is its own plan over fixed tiles.

```mermaid
flowchart LR
    subgraph shared["Shared by both"]
        A1["prepare_data<br/>Step 1"] --> A2["_anchors<br/>Step 2"] --> A3["_pair_search<br/>the arguments of find_valid_lines"]
    end
    subgraph search["A search: _lines"]
        B1["find_valid_lines<br/>lines kept as a LineTable"] --> B2["Step 4: coordinates,<br/>groups, profiles"] --> B3["Step 5: save_run<br/>runs/&lt;run&gt;/"]
    end
    subgraph country["The country layer: count_tile"]
        C1["find_valid_lines(sink=TileCounter)<br/>every part counted, then dropped"] --> C2["save_tile<br/>countries/&lt;id&gt;/tiles/&lt;band&gt;/&lt;name&gt;.npz"]
        C2 --> C3["countcube.build<br/>lines summed, spots merged,<br/>levels 1/2/4/8 km → cube/cube.json"]
        C3 --> C4["/api/countries/&lt;id&gt;/cells<br/>the page #layer"]
    end
    A3 --> B1
    A3 --> C1
    classDef shared fill:#e1e8fa,stroke:#2350c8,color:#17201c
    classDef s fill:#e0f1e6,stroke:#1d7a47,color:#17201c
    classDef c fill:#fbefd9,stroke:#995500,color:#17201c
    class A1,A2,A3 shared
    class B1,B2,B3 s
    class C1,C2,C3,C4 c
```

| | A search | The country layer |
| --- | --- | --- |
| Area | a circle or a drawn area | a country's OSM outline, in fixed tiles named `E<left>_N<bottom>` |
| Grids | one, or tiles sized by the memory budget | one per band: S 1 m (30–300 m), M 2 m (300–1000 m), L 5 m (1000–5000 m) |
| Step 3 | lines kept (`LineTable`), stopped early over `lines_max` | lines counted in a `TileCounter` and dropped |
| Steps 4–5 | coordinates, groups, profiles, the run's files | none: `save_tile`, then `countcube.build` |
| Result | `runs/<run>/` with a map | `countries/<id>/cube/` shown as the layer `#layer` |
| Resumes | a tiled search on the next start | the manifest's pending tiles (`manifest.sqlite`) |

## 4. A web job's states

The statuses of `jobs.sqlite` (`jobs.ACTIVE`, `WAITING`, `FINISHED`) and who moves a job between them.

```mermaid
stateDiagram-v2
    [*] --> queued: POST /api/jobs (Jobs.add, admission)
    queued --> downloading: Scheduler claim, a download slot
    downloading --> ready: run_phase download done
    ready --> computing: Scheduler claim, a compute slot
    computing --> done: save_run, add_run
    done --> done: orthophoto after done (no slot)
    queued --> cancelled: cancel at once
    ready --> cancelled: cancel at once
    downloading --> cancelled: cancel, kill_tree
    computing --> cancelled: cancel, kill_tree
    downloading --> failed: error, time limit, lease expired
    computing --> failed: error, time limit, lease expired
    done --> [*]
    failed --> [*]
    cancelled --> [*]
```

## For and against

- **For**: no tool to install, GitHub renders it, a diff in a pull request shows the change, a test can
  read every block and check the names against the code.
- **Against**: the automatic layout gets crowded above about 20 nodes, so a level is several diagrams
  with links between files; no zoom, the "general to detailed" path is a link.
