// k6 load profile — realistic traffic for a URL shortener.
//
// The shape matters more than the volume. A shortener is read-heavy: links are
// created once and followed many times. Driving 50/50 creates-to-redirects
// would produce a dashboard that looks nothing like production and would hide
// the cache behaviour entirely, since every request would be a miss.
//
// Run:
//   k6 run load/baseline.js
//   k6 run -e BASE_URL=http://shrt.localhost load/baseline.js

import http from "k6/http";
import { check, sleep } from "k6";
import { Counter, Rate } from "k6/metrics";

const BASE = __ENV.BASE_URL || "http://shrt.localhost";

// Custom metrics, so k6's summary reports the things we actually care about
// rather than only HTTP aggregates.
const createdLinks = new Counter("links_created");
const redirectSuccess = new Rate("redirect_success");

export const options = {
  stages: [
    { duration: "20s", target: 10 }, // ramp up
    { duration: "60s", target: 10 }, // steady state — this is the interesting part
    { duration: "10s", target: 0 }, // ramp down
  ],
  thresholds: {
    // Thresholds are assertions. A failing threshold exits non-zero, which is
    // what lets this run in CI as a performance gate rather than a vanity
    // exercise that nobody reads.
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<500", "p(99)<1500"],
    redirect_success: ["rate>0.99"],
  },
};

// Seeded during setup so every VU shares a pool of codes to follow — which is
// what produces cache hits. Each VU creating and following only its own link
// would give a 100% miss rate and a meaningless cache panel.
export function setup() {
  const codes = [];
  for (let i = 0; i < 20; i++) {
    const res = http.post(
      `${BASE}/api/links`,
      JSON.stringify({ target_url: `https://example.com/seed/${i}` }),
      { headers: { "Content-Type": "application/json" } },
    );
    if (res.status === 201) codes.push(res.json("code"));
  }
  return { codes };
}

export default function (data) {
  // ~10% writes, ~90% reads.
  if (Math.random() < 0.1) {
    const res = http.post(
      `${BASE}/api/links`,
      JSON.stringify({ target_url: `https://example.com/vu/${__VU}/${__ITER}` }),
      { headers: { "Content-Type": "application/json" }, tags: { name: "create" } },
    );
    check(res, { "create returned 201": (r) => r.status === 201 });
    if (res.status === 201) createdLinks.add(1);
  } else {
    const code = data.codes[Math.floor(Math.random() * data.codes.length)];
    // redirects: false — we want to measure OUR service, not example.com.
    // Following the redirect would add an internet round trip to every sample
    // and make the latency numbers meaningless.
    const res = http.get(`${BASE}/${code}`, {
      redirects: 0,
      tags: { name: "redirect" },
    });
    const ok = res.status === 307;
    check(res, { "redirect returned 307": () => ok });
    redirectSuccess.add(ok);
  }

  // Think time. Without it, 10 VUs hammer as fast as the network allows, which
  // measures your laptop's loopback rather than the application.
  sleep(Math.random() * 0.5 + 0.1);
}
