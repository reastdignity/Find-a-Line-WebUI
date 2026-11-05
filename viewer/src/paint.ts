// A wait until the page has painted, so a message set just before a long synchronous step (parsing a run,
// grouping its lines, building the 3D mesh) shows during it. requestAnimationFrame does not fire in a hidden
// tab (nor exists under Node, where the model's tests run): a timeout goes on there.

/** Resolves after the next frame was drawn, or after `timeout` ms without one. */
export function nextPaint(timeout = 100): Promise<void> {
  return new Promise((done) => {
    let finished = false;
    const finish = () => { if (!finished) { finished = true; done(); } };
    const timer = setTimeout(finish, timeout);
    if (typeof requestAnimationFrame === "function") {
      requestAnimationFrame(() => { clearTimeout(timer); setTimeout(finish, 0); });
    }
  });
}
