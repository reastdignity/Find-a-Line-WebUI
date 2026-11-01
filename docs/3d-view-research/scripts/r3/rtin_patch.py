import re, sys
p = sys.argv[1]
s = open(p, encoding="utf-8").read()
s = s.replace("""@njit(cache=False)
def count(err, tile, max_error):""", """@njit(cache=False)
def push(stack, top, a, b, c, d, e, f):
    stack[top, 0] = a
    stack[top, 1] = b
    stack[top, 2] = c
    stack[top, 3] = d
    stack[top, 4] = e
    stack[top, 5] = f
    return top + 1


@njit(cache=False)
def count(err, tile, max_error):""")
s = s.replace("stack[top] = (0, 0, tile, tile, tile, 0); top += 1", "top = push(stack, top, 0, 0, tile, tile, tile, 0)")
s = s.replace("stack[top] = (tile, tile, 0, 0, 0, tile); top += 1", "top = push(stack, top, tile, tile, 0, 0, 0, tile)")
s = s.replace("stack[top] = (cx, cy, ax, ay, mx, my); top += 1", "top = push(stack, top, cx, cy, ax, ay, mx, my)")
s = s.replace("stack[top] = (bx, by, cx, cy, mx, my); top += 1", "top = push(stack, top, bx, by, cx, cy, mx, my)")
s = s.replace("""        ax, ay, bx, by, cx, cy = stack[top]
""", """        ax = stack[top, 0]; ay = stack[top, 1]; bx = stack[top, 2]
        by = stack[top, 3]; cx = stack[top, 4]; cy = stack[top, 5]
""")
s = s.replace("""            for px, py in ((ax, ay), (bx, by), (cx, cy)):
                if used[py, px] == 0:
                    used[py, px] = 1
                    verts += 1
""", """            if used[ay, ax] == 0:
                used[ay, ax] = 1
                verts += 1
            if used[by, bx] == 0:
                used[by, bx] = 1
                verts += 1
            if used[cy, cx] == 0:
                used[cy, cx] = 1
                verts += 1
""")
open(p, "w", encoding="utf-8").write(s)
