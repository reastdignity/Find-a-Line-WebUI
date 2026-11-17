// The first module of a run's map (map/main.tsx imports it before any other): over http(s) it marks the page served
// (`fal-served` on <html>), under which map/notice.css hides the disk notice (mapping.MAP_HTML), before the parser
// reaches the notice. First, so that a module after it that throws while loading still leaves the notice hidden.

/** Whether the page came from a server (http or https), not from disk. */
export const served = location.protocol === "http:" || location.protocol === "https:";

if (served) document.documentElement.classList.add("fal-served");
