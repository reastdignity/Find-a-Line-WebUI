"""docs/country-precompute.md from the template: each "<!-- TABLE:NAME -->" line replaced by the block
NAME of tables.md (the lines after "<!-- NAME -->" up to the next block) or, for SAMPLES, the table of
sample_table.py. Usage: python assemble.py <template> <tables.md> <samples table.md> <out.md>"""
import re
import sys

for stream in (sys.stdout, sys.stderr):  # UTF-8 when redirected (progress.utf8_output, inline)
    stream.reconfigure(encoding="utf-8", errors="replace")

template, tables_path, samples_path, out_path = sys.argv[1:5]
blocks, name = {}, None
for line in open(tables_path, encoding="utf-8").read().splitlines():
    m = re.fullmatch(r"<!-- ([A-Z]+(?: [A-Z]+)*) -->", line)
    if m:
        name = m.group(1)
        blocks[name] = []
    elif name:
        blocks[name].append(line)
blocks["SAMPLES"] = open(samples_path, encoding="utf-8").read().splitlines()
out, missing = [], []
for line in open(template, encoding="utf-8").read().splitlines():
    m = re.fullmatch(r"<!-- TABLE:(.+) -->", line.strip())
    if m:
        block = blocks.get(m.group(1))
        if block is None:
            missing.append(m.group(1))
            out.append(line)
            continue
        while block and not block[-1].strip():
            block = block[:-1]
        out.extend(block)
    else:
        out.append(line)
text = "\n".join(out) + "\n"
open(out_path, "w", encoding="utf-8", newline="\n").write(text)
left = re.findall(r"<!-- (?:TABLE|L):[^>]*-->", text)
print("missing blocks:", missing, "| markers left:", left)
