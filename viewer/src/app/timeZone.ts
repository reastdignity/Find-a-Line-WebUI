// The browser's time zone, sent once per browser session on the public site: the server keeps the
// account's country from it (POST /api/me/time-zone, docs/monitoring.md "Users by country").

import { api, user } from "./api";

/** The window event sent when the server has taken the time zone (detail: {country}): the usage is asked for again. */
export const COUNTRY_EVENT = "findaline-country";
const SENT = "findaline.time-zone";  // sessionStorage: sent in this browser session

/** Sends the browser's time zone once per browser session (the public site's signed-in user only);
 *  failures are silent, and the next page load tries again. */
export function sendTimeZone() {
  if (user.local) return;
  try {
    if (sessionStorage.getItem(SENT)) return;
  } catch { /* no storage: send it with every page load */ }
  let zone = "";
  try { zone = Intl.DateTimeFormat().resolvedOptions().timeZone || ""; } catch { /* none */ }
  if (!zone) return;
  api.timeZone(zone).then((answer) => {
    try { sessionStorage.setItem(SENT, "1"); } catch { /* none */ }
    window.dispatchEvent(new CustomEvent(COUNTRY_EVENT, {detail: answer}));
  }, () => {});
}
