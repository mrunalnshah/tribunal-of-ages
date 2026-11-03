// Where the API lives: uvicorn on your machine during development, your Space in production.
window.TRIBUNAL_API = ["localhost", "127.0.0.1"].includes(location.hostname)
  ? "http://localhost:8000"
  : "https://tribunal-api.happycliff-260cf674.northcentralus.azurecontainerapps.io";

// Visitor analytics (Step 16): paste your PostHog project key to turn them on. Empty means off.
window.TRIBUNAL_ANALYTICS = { key: "phc_wmKfGyUX9sMHA8muAh5ZySZGbjWi7Sr6BUFuzJVS3JLn", host: "https://us.i.posthog.com" };

// The uptime history (Step 18): uptime.json on this repository's status branch, updated every
// 30 minutes. Worked out from the GitHub Pages address; set it yourself on a custom domain.
// Empty means no uptime card.
window.TRIBUNAL_UPTIME = location.hostname.endsWith(".github.io")
  ? `https://raw.githubusercontent.com/${location.hostname.split(".")[0]}/${location.pathname.split("/")[1]}/status/uptime.json`
  : "";