// Minimal in-memory fixed-window rate limiter. No dependency, single process —
// good enough to blunt scripted abuse of auth and crown-action endpoints.

const buckets = new Map();

export function rateLimit(key, { limit, windowMs }) {
  const now = Date.now();
  let bucket = buckets.get(key);
  if (!bucket || now - bucket.start > windowMs) {
    bucket = { start: now, count: 0 };
    buckets.set(key, bucket);
  }
  bucket.count += 1;
  return bucket.count <= limit;
}

// Sweep stale buckets so the map doesn't grow unbounded.
setInterval(() => {
  const now = Date.now();
  for (const [key, bucket] of buckets) {
    if (now - bucket.start > 3600000) buckets.delete(key);
  }
}, 600000).unref?.();
