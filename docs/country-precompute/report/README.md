# Building the report

`docs/country-precompute.md` and its page (`report.html`, published as an artifact) are made from the
estimate, so that both show the same numbers. With `uv run` (or the project's Python) from the root:

```bash
SP=<scratch folder with samples/samples.json>
R=docs/country-precompute
uv run tools/perf_country.py relief --inputs $R/inputs.json --samples $SP/samples/samples.json \
    --data-dir $SP/data --out $R/relief.json
uv run tools/perf_country.py estimate --inputs $R/inputs.json --samples $SP/samples/samples.json \
    --json $R/estimate.json
uv run $R/report/sanitize_samples.py $SP/samples/samples.json $R/samples.json   # without local paths
uv run $R/report/report_tables.py $R/estimate.json > $SP/tables.md
uv run $R/report/sample_table.py $SP/samples/samples.json > $SP/samples.md
uv run $R/report/assemble.py $R/report/template.md $SP/tables.md $SP/samples.md docs/country-precompute.md
uv run $R/report/build_artifact.py docs/country-precompute.md $R/estimate.json $R/report/shell.html \
    $R/report/app.js $R/report.html $R/samples.json
uv run $R/report/samples_sh.py $SP/samples/samples.json $R/samples.sh
```

- `template.md`: the report's text; `<!-- TABLE:NAME -->` lines are replaced by the blocks of
  `report_tables.py` (SUMMARY, DATATABLE, COMPUTE PL/CH/UT, STRATA, MODELS) and the samples' table.
- `build_artifact.py`: the page. The overview (country cards, the numbers by country, length variant
  and DSM, the chart of computing time by grid strategy, the strata) is drawn by `app.js` from the
  estimate embedded in the page; the sections after it are the report's own text, converted from the
  Markdown (headings, paragraphs, lists, tables, bold, code and links: the subset the report uses).
- `shell.html`: the page's title, fonts and styles (light and dark).
- Run the searches of `samples.sh` one at a time under the exclusive test lock: their times are
  measured.
