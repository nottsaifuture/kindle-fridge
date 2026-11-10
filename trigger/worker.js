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

export default {
  async scheduled(event, env, ctx) {
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
