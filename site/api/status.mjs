// Is the MI300X on? The site says "live now" or the next window: the council's live reviews turn on when its
// server answers.
import { council, handle, json } from "../lib/common.mjs";

async function health(call) {
  try {
    const r = await call("/health", { seconds: 4 });
    if (r.ok) return await r.json();
  } catch {
    // off, unreachable or not configured: for the judge it is the same thing
  }
  return null;
}

export default {
  fetch: handle("GET", async () => {
    const c = await health(council);
    return json({ council: { live: c?.live === true, busy: c?.review_in_progress === true } });
  }),
};
