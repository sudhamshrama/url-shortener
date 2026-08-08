# ADR 0001: Loki instead of the ELK stack

**Status:** Accepted
**Date:** 2026-08-07

## Context

We need centralised logging: all logs from all pods, searchable in one place.

The default answer in most job postings is **ELK** — Elasticsearch to store and
index, Logstash to parse, Kibana to query. It is mature, ubiquitous, and the
phrase hiring managers recognise.

The constraint is that this runs on a 3-node kind cluster inside a Docker VM
with 8 GB of RAM total, shared with Prometheus, Grafana, Jaeger, and the
application itself.

## Decision

Use **Grafana Loki** with Promtail, not ELK.

## Why

**The architectural difference is the whole argument.** Elasticsearch builds a
full inverted index of every term in every log line — that is what makes
arbitrary full-text search fast, and it is why a useful deployment wants 2–4 GB
of JVM heap minimum.

Loki indexes only the **labels** (namespace, pod, container) and stores the log
text as compressed chunks, brute-forcing the content at query time. That runs in
roughly 200 MB.

For our workload the trade is favourable:

- Log volume is small, so brute-force scanning is fast enough.
- Queries during an incident are almost always label-scoped first
  (`{namespace="url-shortener-dev"}`), then filtered — which is exactly Loki's
  strength.
- One Grafana serves both metrics and logs, so there is no context-switch to a
  separate Kibana.

## Consequences

**Good:** the entire observability stack fits in ~1 GB. Loki's query language
(LogQL) is deliberately similar to PromQL, so there is one syntax to learn
rather than two. The `derivedFields` feature turns a `trace_id` in a log line
into a clickable link to Jaeger — the single most useful thing in our incident
workflow.

**Bad:** unbounded full-text search across a long time range is genuinely slower
than Elasticsearch. At significantly larger scale, or with a real need for
analytics over log *content*, this choice would be wrong.

**On the resume:** "Grafana + Loki" rather than "ELK". Both are recognised in
2026, and Loki is increasingly the cloud-native default. If a specific role
names ELK, the concepts transfer directly — log shipping, label design,
retention, and cardinality are the same problems either way.

## What we would do differently at scale

Loki's weak point is high-cardinality labels: a label with unbounded values
(a user ID, a request ID, a short code) creates a separate stream per value and
degrades badly. The same discipline that applies to Prometheus metrics applies
here — high-cardinality data belongs in the log *line*, never in a label.
