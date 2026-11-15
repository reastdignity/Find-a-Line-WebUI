// Grouping of near-identical lines: the same greedy algorithm as mapping.group_lines
// (keep both in sync; tests/test_viewer.py compares them). Written for runs of millions of lines: the
// algorithm (groupIndices) works on indices and typed arrays, not on objects, sets and string keys; the
// result's model hands it its columns (result/model.ts), groupLines the values of objects.

export interface Groupable {
  x1: number; y1: number; x2: number; y2: number;
  len: number; clr: number; over: boolean;
  hmax: number;  // largest height above the terrain (by "height")
}

export interface Group<T> {
  rep: T;
  members: T[];
}

/** The values groupIndices reads of each of n lines (null and undefined stored as a Float64Array stores them). */
export interface GroupInput {
  x1: Float64Array; y1: Float64Array; x2: Float64Array; y2: Float64Array;
  len: Float64Array; clr: Float64Array; hmax: Float64Array;
  over: Uint8Array;  // 1: over trees/buildings
}

/** The groups of groupIndices, clear groups first: group g's representative is reps[g] and its members (indices
 *  into the input, in their order: the representative first) are members[starts[g]] .. members[starts[g + 1] - 1]. */
export interface Grouped {
  reps: Int32Array;
  members: Int32Array;
  starts: Int32Array;
}

/** Best first, compared as mapping._rank (on the values in typed arrays: the same numbers, as
 * a subtraction converts null and undefined just as a Float64Array does). */
function compare(by: string, len: Float64Array, clr: Float64Array, hmax: Float64Array) {
  if (by === "longest") return (a: number, b: number) => (len[b] - len[a]) || (clr[b] - clr[a]);
  if (by === "height") return (a: number, b: number) => (hmax[b] - hmax[a]) || (clr[b] - clr[a]);
  return (a: number, b: number) => (clr[b] - clr[a]) || (len[b] - len[a]);
}

function sq(ax: number, ay: number, bx: number, by: number): number {
  const dx = bx - ax, dy = by - ay;
  return dx * dx + dy * dy;
}

// Cells of the grid in a hash table of linked lists (head and next in typed arrays): a cell's
// lines lie in the list of its bucket. Cells sharing a bucket merely add candidates (and so do
// cells whose numbers wrap in 32 bits): membership is decided by the distances.
const bucket = (cx: number, cy: number, mask: number) => (Math.imul(cx | 0, 73856093) ^ Math.imul(cy | 0, 19349663)) & mask;

/** Groups of lines whose anchors are both within `distance` of the representative's,
 * clear lines first (then lines over trees/buildings), best representative first. */
export function groupIndices(input: GroupInput, distance: number, by: string): Grouped {
  const total = input.len.length, d2 = distance * distance;
  const out = new Int32Array(total), starts: number[] = [], reps: number[] = [];
  let filled = 0;
  for (const over of [0, 1]) {
    // The lines' indices in their order (a stable sort of the same comparisons as on the lines)
    const sorted: number[] = [];
    for (let k = 0; k < total; k++) if (input.over[k] === over) sorted.push(k);
    sorted.sort(compare(by, input.len, input.clr, input.hmax));
    const n = sorted.length;
    const x1 = new Float64Array(n), y1 = new Float64Array(n), x2 = new Float64Array(n), y2 = new Float64Array(n);
    // Lines by the cell (of size `distance`) of their first anchor: a member's first
    // anchor lies within `distance` of one of the representative's anchors
    const mask = 2 ** Math.ceil(Math.log2(2 * n + 1)) - 1;
    const head = new Int32Array(mask + 1).fill(-1), next = new Int32Array(n);
    for (let k = 0; k < n; k++) {
      const s = sorted[k];
      x1[k] = input.x1[s]; y1[k] = input.y1[s]; x2[k] = input.x2[s]; y2[k] = input.y2[s];
      const b = bucket(Math.floor(x1[k] / distance), Math.floor(y1[k] / distance), mask);
      next[k] = head[b];
      head[b] = k;
    }
    const used = new Uint8Array(n), seen = new Int32Array(n).fill(-1), candidates = new Int32Array(n);
    let found = 0;
    // The free lines in the 3 x 3 cells around a point, each once per representative i; the lines
    // grouped already leave the lists, so dense cells are not read again and again
    const near = (x: number, y: number, i: number) => {
      const cx = Math.floor(x / distance), cy = Math.floor(y / distance);
      for (let dx = -1; dx <= 1; dx++) {
        for (let dy = -1; dy <= 1; dy++) {
          const b = bucket(cx + dx, cy + dy, mask);
          let before = -1;
          for (let k = head[b]; k !== -1; k = next[k]) {
            if (used[k]) {
              if (before < 0) head[b] = next[k]; else next[before] = next[k];
              continue;
            }
            before = k;
            if (seen[k] !== i) { seen[k] = i; candidates[found++] = k; }
          }
        }
      }
    };
    for (let i = 0; i < n; i++) {
      if (used[i]) continue;
      found = 0;
      near(x1[i], y1[i], i);
      near(x2[i], y2[i], i);
      const ax = x1[i], ay = y1[i], bx = x2[i], by_ = y2[i];
      starts.push(filled);
      reps.push(sorted[i]);
      for (const k of candidates.subarray(0, found).sort()) {  // in their order (a typed array sorts numbers)
        const same = sq(ax, ay, x1[k], y1[k]) <= d2 && sq(bx, by_, x2[k], y2[k]) <= d2;
        const flipped = sq(bx, by_, x1[k], y1[k]) <= d2 && sq(ax, ay, x2[k], y2[k]) <= d2;
        if (same || flipped) {
          used[k] = 1;
          out[filled++] = sorted[k];
        }
      }
    }
  }
  starts.push(filled);
  return {reps: Int32Array.from(reps), members: out, starts: Int32Array.from(starts)};
}

/** groupIndices over objects: their groups, each with its representative and members (the representative first). */
export function groupLines<T extends Groupable>(lines: T[], distance: number, by: string): Group<T>[] {
  const n = lines.length;
  const input: GroupInput = {x1: new Float64Array(n), y1: new Float64Array(n), x2: new Float64Array(n),
                             y2: new Float64Array(n), len: new Float64Array(n), clr: new Float64Array(n),
                             hmax: new Float64Array(n), over: new Uint8Array(n)};
  lines.forEach((l, k) => {
    input.x1[k] = l.x1; input.y1[k] = l.y1; input.x2[k] = l.x2; input.y2[k] = l.y2;
    input.len[k] = l.len; input.clr[k] = l.clr; input.hmax[k] = l.hmax; input.over[k] = l.over ? 1 : 0;
  });
  const {reps, members, starts} = groupIndices(input, distance, by), groups: Group<T>[] = [];
  reps.forEach((rep, g) => {
    groups.push({rep: lines[rep], members: Array.from(members.subarray(starts[g], starts[g + 1]), (k) => lines[k])});
  });
  return groups;
}
