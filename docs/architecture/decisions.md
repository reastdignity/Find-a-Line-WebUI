# The decisions a search makes

The decision trees inside a search ([search.md](search.md)): which source, one grid or tiles, where
the sea is, what is filled and from where, and what is an obstacle. Each tree names the option that
sets it and the constant that decides a branch.

## In plain words

Before it searches, the program decides where to take the height map from (the country's own survey
if there is one, else a world-wide model), whether the area is small enough for one piece, where the
sea and the lakes are (so a line over water is found), how to fill the holes in the data, and which
raised things in the surface map are trees and roofs rather than the rock itself.

## Which source

`--source auto` picks by the country of the centre; a named source or an elevation file skips the
lookup. Offline, `OFFLINE_BOXES` stand in for the lookup.

```mermaid
flowchart TD
    start["choose_source"] --> f{"--elevation-file<br/>or --source files?"}
    f -- "yes" --> files["FileLayer<br/>the user's raster, its CRS and resolution"]
    f -- "no" --> named{"--source named?"}
    named -- "yes" --> un1{"source_unavailable?<br/>a layer's keys or mirror missing"}
    un1 -- "no" --> chosen["that Source"]
    un1 -- "yes" --> err["refused with the reason"]
    named -- "auto" --> code["country_code<br/>Nominatim reverse at zoom 3"]
    code --> found{"a Source with that country<br/>and covers(lat, lon)?"}
    found -- "none" --> europe["SOURCES europe<br/>FABDEM + Copernicus"]
    found -- "some" --> reg{"one of them has regions?"}
    reg -- "yes" --> rcode["region_codes<br/>Nominatim at REGION_ZOOM = 8;<br/>a region's source wins"]
    reg -- "no" --> pick["the first in SOURCES order"]
    rcode --> pick
    pick --> un2{"source_unavailable?"}
    un2 -- "yes" --> europe
    un2 -- "no" --> nodata{"instead_without_data and<br/>nmt.has_data_near is False?"}
    nodata -- "yes" --> instead["the source named instead<br/>alaska → alaska_ifsar"]
    nodata -- "no" --> chosen
    classDef step fill:#e1e8fa,stroke:#2350c8,color:#17201c
    classDef q fill:#fbefd9,stroke:#995500,color:#17201c
    classDef file fill:#e0f1e6,stroke:#1d7a47,color:#17201c
    classDef actor fill:#e9eee9,stroke:#45524b,color:#17201c
    class start,code,rcode,pick,instead,chosen,europe,files step
    class f,named,un1,found,reg,un2,nodata q
    class err file
```

## One grid or tiles

Only a drawn area (`area.Polygon`) is tiled; a circle is always one grid. The core of a tile comes
from `--tile-size` or from the memory: a compute slot's budget on the public site, the free memory
locally, at most `TILE_PX_MAX` pixels with the overlap.

```mermaid
flowchart TD
    plan["plan_search"] --> kind{"a drawn area?"}
    kind -- "a circle" --> one["one grid<br/>profiles of every line"]
    kind -- "a Polygon" --> core["tile_core_size<br/>--tile-size, or sqrt(memory × TILE_MEMORY_SHARE / PIXEL_BYTES)<br/>in steps of 500 m, at most TILE_PX_MAX"]
    core --> fits{"the area's grid without its margin<br/>within one core?"}
    fits -- "yes" --> one
    fits -- "no" --> tiles["_tiles<br/>cores over the area, each grid with the overlap<br/>max_length + _margin + 2 px"]
    tiles --> check{"grid_mpx_max of the site?"}
    check -- "a tile over it" --> smaller["refused: too many pixels<br/>(or smaller tiles to fit)"]
    check -- "fits" --> tiled["a tiled search<br/>step 1 once in strips, steps 2 to 4 per tile"]
    classDef step fill:#e1e8fa,stroke:#2350c8,color:#17201c
    classDef q fill:#fbefd9,stroke:#995500,color:#17201c
    classDef file fill:#e0f1e6,stroke:#1d7a47,color:#17201c
    classDef actor fill:#e9eee9,stroke:#45524b,color:#17201c
    class plan,one,core,tiles,tiled step
    class kind,fits,check q
    class smaller file
```

## Where the sea is

`--coastline overpass|world|copernicus` (step 1, `coast.sea_mask`). The Copernicus water body mask
marks the sea coarsely (30 m); the OpenStreetMap coastline gives the exact shore.

```mermaid
flowchart TD
    start["coast.sea_mask"] --> any{"any sea in the area<br/>by the Copernicus mask?"}
    any -- "no" --> none["no sea: the mask stays empty"]
    any -- "yes" --> mode{"--coastline?"}
    mode -- "world, or overpass with<br/>the world file cached" --> world["OpenStreetMap water polygons<br/>cache/osm/water-polygons/, read once per box"]
    mode -- "overpass" --> ovp["osm.theme coastline<br/>Overpass or the Geofabrik extracts, 0.25° tiles"]
    ovp --> ok{"fetched?"}
    ok -- "an error, or OVERPASS_DAY_MAX reached" --> fb["Copernicus mask with a warning<br/>coast_fallback"]
    ok -- "no coastline near the area" --> cop["Copernicus mask as it is"]
    ok -- "yes" --> faces["_sea_from_coastline<br/>the mask's sea on the sea side of the line"]
    mode -- "copernicus" --> cop
    classDef step fill:#e1e8fa,stroke:#2350c8,color:#17201c
    classDef q fill:#fbefd9,stroke:#995500,color:#17201c
    classDef file fill:#e0f1e6,stroke:#1d7a47,color:#17201c
    classDef actor fill:#e9eee9,stroke:#45524b,color:#17201c
    class start,world,ovp,faces,cop,fb,none step
    class any,mode,ok q
```

## What is filled, and from where

The order of step 1 (`prepare_data`): the sea zone first, then the gaps on land, then a sea cliff's
face from the surface model, then the water. Pixels from a neighbour are a seam (no anchors on its
edge), never "filled"; a filling layer that filled no pixel is not credited.

```mermaid
flowchart TD
    water{"--water fill?"} -- "yes" --> wbm["water_body_mask + sea mask<br/>the sea zone, the lakes"]
    water -- "off" --> gaps
    wbm --> gaps{"--fill-gaps on and the source<br/>has a fallback or neighbours?"}
    gaps -- "no" --> shore
    gaps -- "yes" --> border{"border_gaps on land reaching the footprint's edge,<br/>at least NEIGHBOUR_MIN_GAP_M2 = 2500 m²,<br/>inside a neighbour's offline box?"}
    border -- "yes" --> nb["fill_from_neighbours<br/>the neighbour's data on a sub-grid around the gaps;<br/>joined.npy marks the seam"]
    border -- "no" --> chain
    nb --> chain["fill_gaps_chain<br/>fallback, then more_fallbacks in turn;<br/>offsets matched on gentle slopes, within ±3 m;<br/>filled.npy marks the pixels"]
    chain --> shore{"a surface model and the sea zone?"}
    shore -- "yes" --> face["fill_shore_from_surface<br/>a cliff's face the terrain lacks takes the DSM,<br/>each pixel at most FACE_TOLERANCE = 1.5 m<br/>above the one it is reached from"]
    shore -- "no" --> fw
    face --> fw["fill_water<br/>the sea at 0 m where its data are at most SEA_LEVEL_TOLERANCE = 1 m<br/>(or Source.sea_fill), lakes at their shore level;<br/>bare.npy: water the terrain lacked"]
    fw --> obs
    water -- "off" --> obs{"a surface model and<br/>--nmpt mark or reject?"}
    obs -- "yes" --> rule["obstacle_surface<br/>the surface only where it stands more than MIN_HEIGHT = 1 m<br/>above the terrain's envelope of RADIUS = 2 px;<br/>never on bare pixels"]
    obs -- "no" --> plain["the terrain alone"]
    classDef step fill:#e1e8fa,stroke:#2350c8,color:#17201c
    classDef q fill:#fbefd9,stroke:#995500,color:#17201c
    classDef file fill:#e0f1e6,stroke:#1d7a47,color:#17201c
    classDef actor fill:#e9eee9,stroke:#45524b,color:#17201c
    class wbm,nb,chain,face,fw,rule,plain step
    class water,gaps,border,shore,obs q
```

## Anchors and lines: the thresholds that cut

| Decision | Option or constant | Where |
| --- | --- | --- |
| a pixel is an anchor | slope ≥ `slope_threshold` (45° by default; the country layer 60°, 45° at 5 m) | `helpers.find_significant_slopes` |
| an anchor is kept | within `--min-elevation`/`--max-elevation`; not at a seam of filled or joined pixels; at most `ANCHORS_MAX` | `search._anchors`, `at_seams` |
| a pair is a candidate | `min_length` ≤ length ≤ `max_length`; the anchors' height difference at most 5 % and 50 m; both open towards each other; the wall angle under `--max-wall-angle` within EPS | `linesearch._pairs` |
| a line is valid | every pixel under `helpers.max_safe_elevation` (the formula, or the sag table of `--model sag`) | `linesearch._line_ok`, then `_evaluate` |
| a line over trees | fails the same test against the obstacle surface: kept and marked (`--nmpt mark`) or dropped (`reject`) | `linesearch._evaluate` |
| too many lines | over `lines_max` (a site's limit) or the memory: stopped early (`lines_early_stop`) or refused at the end | `search._early_check`, `_check_lines` |

## Where in the code

| Node | File | Function or name |
| --- | --- | --- |
| choose_source | [sources/choose.py](../../sources/choose.py) | `choose_source`, `country_code`, `region_codes`, `REGION_ZOOM`, `source_unavailable`, `OFFLINE_BOXES` |
| FileLayer | [sources/layers/files.py](../../sources/layers/files.py) | `FileLayer` |
| SOURCES europe | [sources/catalogue/__init__.py](../../sources/catalogue/__init__.py), [sources/catalogue/world.py](../../sources/catalogue/world.py) | `SOURCES`, `FAMILIES` |
| instead_without_data, covers, has_data_near | [sources/source.py](../../sources/source.py), [sources/composed.py](../../sources/composed.py) | `Source.instead_without_data`, `Source.covers`, `Index.has_data_near` |
| tile_core_size, _tiles | [search.py](../../search.py) | `tile_core_size`, `_tiles`, `_margin`, `_overlap`, `TILE_MEMORY_SHARE`, `TILE_PX_MAX`, `PIXEL_BYTES`, `_check_tiles` |
| grid_mpx_max | [settings.py](../../settings.py) | `Limits.grid_mpx_max` |
| coast.sea_mask | [coast.py](../../coast.py) | `sea_mask`, `sea_mask_rows`, `world_polygons`, `_sea_from_coastline` |
| osm.theme coastline | [osm.py](../../osm.py) | `theme`, `fetch_tile`, `OVERPASS_DAY_MAX`, `OverpassDayMax` |
| water_body_mask, fill_water | [sources/filling.py](../../sources/filling.py) | `water_body_mask`, `fill_water`, `water_with_data`, `SEA_LEVEL_TOLERANCE`, `Source.sea_fill` |
| border_gaps, fill_from_neighbours | [sources/filling.py](../../sources/filling.py) | `border_gaps`, `NEIGHBOUR_MIN_GAP_M2`, `fill_from_neighbours`, `neighbour_window` |
| fill_gaps_chain | [sources/filling.py](../../sources/filling.py) | `fill_gaps_chain`, `fill_gaps`, `_fill` |
| fill_shore_from_surface | [sources/filling.py](../../sources/filling.py) | `fill_shore_from_surface`, `FACE_TOLERANCE` |
| obstacle_surface | [obstacles.py](../../obstacles.py) | `obstacle_surface`, `RULE`, `MIN_HEIGHT`, `RADIUS` |
| the thresholds | [helpers.py](../../helpers.py), [linesearch.py](../../linesearch.py), [search.py](../../search.py) | `find_significant_slopes`, `max_safe_elevation`, `_pairs`, `_line_ok`, `_evaluate`, `_anchors`, `_early_check`, `_check_lines` |
