"""Vertices and triangles of an RTIN mesh (the algorithm of @mapbox/martini, re-implemented here)
of a DEM patch at several maximum errors, against the full grid.
Usage: python -I rtin_count.py <patch.npy> [grid_size=1025]"""
import sys

import numpy as np
from numba import njit


@njit(cache=False)
def coords_of(tile):
    n = tile * tile * 2 - 2
    coords = np.zeros((n, 4), np.int32)
    for i in range(n):
        tid = i + 2
        ax = ay = bx = by = cx = cy = 0
        if tid & 1:
            bx = by = cx = tile
        else:
            ax = ay = cy = tile
        tid >>= 1
        while tid > 1:
            mx = (ax + bx) >> 1
            my = (ay + by) >> 1
            if tid & 1:
                bx, by = ax, ay
                ax, ay = cx, cy
            else:
                ax, ay = bx, by
                bx, by = cx, cy
            cx, cy = mx, my
            tid >>= 1
        coords[i, 0], coords[i, 1], coords[i, 2], coords[i, 3] = ax, ay, bx, by
    return coords


@njit(cache=False)
def errors_of(z, coords, tile):
    size = tile + 1
    n = coords.shape[0]
    parents = n - tile * tile
    err = np.zeros((size, size), np.float32)
    for i in range(n - 1, -1, -1):
        ax, ay, bx, by = coords[i, 0], coords[i, 1], coords[i, 2], coords[i, 3]
        mx = (ax + bx) >> 1
        my = (ay + by) >> 1
        cx = mx + my - ay
        cy = my + ax - mx
        e = abs((z[ay, ax] + z[by, bx]) / 2 - z[my, mx])
        if e > err[my, mx]:
            err[my, mx] = e
        if i < parents:
            l = err[(ay + cy) >> 1, (ax + cx) >> 1]
            r = err[(by + cy) >> 1, (bx + cx) >> 1]
            if l > err[my, mx]:
                err[my, mx] = l
            if r > err[my, mx]:
                err[my, mx] = r
    return err


@njit(cache=False)
def push(stack, top, a, b, c, d, e, f):
    stack[top, 0] = a
    stack[top, 1] = b
    stack[top, 2] = c
    stack[top, 3] = d
    stack[top, 4] = e
    stack[top, 5] = f
    return top + 1


@njit(cache=False)
def count(err, tile, max_error):
    size = tile + 1
    used = np.zeros((size, size), np.uint8)
    stack = np.zeros((4 * 64 * tile, 6), np.int32)
    top = 0
    top = push(stack, top, 0, 0, tile, tile, tile, 0)
    top = push(stack, top, tile, tile, 0, 0, 0, tile)
    verts = 0
    tris = 0
    while top > 0:
        top -= 1
        ax = stack[top, 0]; ay = stack[top, 1]; bx = stack[top, 2]
        by = stack[top, 3]; cx = stack[top, 4]; cy = stack[top, 5]
        mx = (ax + bx) >> 1
        my = (ay + by) >> 1
        if abs(ax - cx) + abs(ay - cy) > 1 and err[my, mx] > max_error:
            top = push(stack, top, cx, cy, ax, ay, mx, my)
            top = push(stack, top, bx, by, cx, cy, mx, my)
        else:
            if used[ay, ax] == 0:
                used[ay, ax] = 1
                verts += 1
            if used[by, bx] == 0:
                used[by, bx] = 1
                verts += 1
            if used[cy, cx] == 0:
                used[cy, cx] = 1
                verts += 1
            tris += 1
    return verts, tris


z = np.load(sys.argv[1]).astype(np.float32)
size = int(sys.argv[2]) if len(sys.argv) > 2 else 1025
tile = size - 1
r0 = (z.shape[0] - size) // 2
c0 = (z.shape[1] - size) // 2
patch = np.ascontiguousarray(z[r0:r0 + size, c0:c0 + size])
coords = coords_of(tile)
err = errors_of(patch, coords, tile)
print(f"{sys.argv[1]}: {size} x {size} px at 1 m, relief {patch.max() - patch.min():.0f} m; "
      f"full grid {size * size} vertices, {2 * tile * tile} triangles")
for e in (0.05, 0.1, 0.25, 0.5, 1.0, 2.0):
    v, t = count(err, tile, e)
    print(f"  max error {e:4.2f} m: {v:8d} vertices ({v / size / size:5.1%}), {t:8d} triangles")
