// Cloudflare Worker that asks GitHub to redraw the Kindle dashboard.
//
// GitHub's own `schedule` trigger proved unreliable for this repo (hours
// without a run), while Cloudflare cron triggers fire on time. On each cron
// tick this calls the workflow_dispatch API for render.yml.
//
// Secret: GITHUB_TOKEN — a fine-grained token limited to the kindle-fridge
// repository with "Actions: Read and write" only. Set it with:
//   npx wrangler secret put GITHUB_TOKEN

const REPO = "nottsaifuture/kindle-fridge";
const WORKFLOW = "render.yml";

// Only draw while the Kindle is updating (04:05 to 20:05 London time). The
// first draw at 03:50 makes sure the 04:05 wake-up shows today's date.
// Cron runs in UTC, so London summer/winter time is worked out here.
const FIRST = 3 * 60 + 45; // 03:45
const LAST = 21 * 60; // up to 21:00

export function londonMinutes(date) {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/London",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const get = (type) => Number(parts.find((p) => p.type === type).value);
  return get("hour") * 60 + get("minute");
}

export default {
  async scheduled(event, env, ctx) {
    const minutes = londonMinutes(new Date(event.scheduledTime));
    if (minutes < FIRST || minutes >= LAST) return; // night: Kindle isn't updating

    const response = await fetch(
      `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${env.GITHUB_TOKEN}`,
          Accept: "application/vnd.github+json",
          "X-GitHub-Api-Version": "2022-11-28",
          "User-Agent": "kindle-fridge-trigger",
        },
        body: JSON.stringify({ ref: "main" }),
      },
    );
    if (!response.ok) {
      // Shows up as a failed invocation in the Cloudflare dashboard.
      throw new Error(`GitHub answered ${response.status}: ${await response.text()}`);
    }
  },

  // No public endpoint: the Worker only runs on its timer.
  async fetch() {
    return new Response("Not found", { status: 404 });
  },
};
