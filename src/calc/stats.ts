export function finite(xs: (number | null | undefined)[]): number[] {
  return xs.filter((x): x is number => typeof x === "number" && Number.isFinite(x));
}

export function mean(xs: number[]): number {
  return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : NaN;
}

/** Quantile with linear interpolation (type 7, same as numpy default). */
export function quantile(xs: number[], q: number): number {
  if (!xs.length) return NaN;
  const s = [...xs].sort((a, b) => a - b);
  const h = (s.length - 1) * q;
  const lo = Math.floor(h);
  const hi = Math.ceil(h);
  return s[lo] + (h - lo) * (s[hi] - s[lo]);
}

export function median(xs: number[]): number {
  return quantile(xs, 0.5);
}

/** Percentile rank of x within sample (0-100), mid-rank for ties. */
export function percentileRank(sample: number[], x: number): number {
  if (!sample.length) return NaN;
  let below = 0;
  let equal = 0;
  for (const v of sample) {
    if (v < x) below++;
    else if (v === x) equal++;
  }
  return (100 * (below + 0.5 * equal)) / sample.length;
}

/** Residuals of y after removing an ordinary least-squares linear trend in x. */
export function detrend(x: number[], y: number[]): number[] {
  const mx = mean(x);
  const my = mean(y);
  let sxy = 0;
  let sxx = 0;
  for (let i = 0; i < x.length; i++) {
    sxy += (x[i] - mx) * (y[i] - my);
    sxx += (x[i] - mx) ** 2;
  }
  const b = sxx > 0 ? sxy / sxx : 0;
  return y.map((v, i) => v - (my + b * (x[i] - mx)));
}

/** Deterministic PRNG so the reported p-value is reproducible. */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * Two-sided permutation test for a difference in means between groups a and b.
 * Returns the p-value with the +1 correction (Phipson & Smyth 2010).
 */
export function permutationTest(a: number[], b: number[], n = 10_000, seed = 42): number {
  if (a.length < 2 || b.length < 2) return NaN;
  const obs = Math.abs(mean(a) - mean(b));
  const pooled = [...a, ...b];
  const rand = mulberry32(seed);
  let extreme = 0;
  for (let k = 0; k < n; k++) {
    // Fisher-Yates partial shuffle for the first a.length elements
    const p = pooled.slice();
    for (let i = 0; i < a.length; i++) {
      const j = i + Math.floor(rand() * (p.length - i));
      [p[i], p[j]] = [p[j], p[i]];
    }
    let sa = 0;
    for (let i = 0; i < a.length; i++) sa += p[i];
    let sb = 0;
    for (let i = a.length; i < p.length; i++) sb += p[i];
    if (Math.abs(sa / a.length - sb / b.length) >= obs - 1e-12) extreme++;
  }
  return (extreme + 1) / (n + 1);
}
