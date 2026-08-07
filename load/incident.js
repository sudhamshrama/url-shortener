// Deliberate incident injection.
//
// This exists to prove the alerting actually works. An alert rule that has
// never fired is a hypothesis, not a control — the thresholds could be wrong,
// the PromQL could reference a label that does not exist, and you would find
// out during a real outage.
//
// The failure injected here is a PARTIAL one: roughly 12% of requests error,
// and some are slow. That is deliberate. Total outages are easy to detect and
// rarely what actually happens; the interesting question is whether a 12% error
// rate crosses your 5% threshold and pages someone, which is exactly the case
// real thresholds are tuned for.
//
// Run:
//   k6 run -e BASE_URL=http://shrt.localhost load/incident.js

import http from "k6/http";
import { sleep } from "k6";

const BASE = __ENV.BASE_URL || "http://shrt.localhost";

export const options = {
  // Long enough to satisfy the alert rule's `for: 5m` clause. A shorter run
  // would raise the error rate without ever firing the alert, and would prove
  // nothing.
  stages: [
    { duration: "30s", target: 8 },
    { duration: "6m", target: 8 },
    { duration: "15s", target: 0 },
  ],
  // No thresholds. This run is SUPPOSED to fail — asserting otherwise would
  // just produce a red exit code with no information.
  thresholds: {},
};

export function setup() {
  const res = http.post(
    `${BASE}/api/links`,
    JSON.stringify({ target_url: "https://example.com/incident-baseline" }),
    { headers: { "Content-Type": "application/json" } },
  );
  return { code: res.status === 201 ? res.json("code") : "kdocs" };
}

export default function (data) {
  const roll = Math.random();

  if (roll < 0.12) {
    // ~12% errors — comfortably above the 5% alert threshold, but nowhere near
    // an outage. The service is still mostly working, which is what makes this
    // the realistic case.
    http.get(`${BASE}/debug/error`, { tags: { name: "injected-error" } });
  } else if (roll < 0.2) {
    // ~8% slow requests, to drag p95 above the 500ms latency threshold while
    // p50 stays healthy. This is the scenario where an average would show
    // nothing at all and a percentile shows the problem clearly.
    http.get(`${BASE}/debug/slow?seconds=1.5`, {
      tags: { name: "injected-slow" },
      timeout: "10s",
    });
  } else {
    http.get(`${BASE}/${data.code}`, { redirects: 0, tags: { name: "redirect" } });
  }

  sleep(Math.random() * 0.4 + 0.1);
}
