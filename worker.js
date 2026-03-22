/**
 * Cloudflare Worker — Stock API proxy for the Daily Digest PWA.
 * Proxies Yahoo Finance requests and adds scoring/sentiment analysis.
 *
 * Deploy: Cloudflare Dashboard → Workers & Pages → Create → paste this code → Deploy
 *
 * Endpoints:
 *   GET /api/stock/<TICKER>          — Full stock evaluation (chart + fundamentals + news + verdict)
 *   GET /api/stock/<TICKER>?quick=1  — Quick mode (chart only, for markets page)
 */

const YAHOO_HEADERS = { "User-Agent": "Mozilla/5.0" };

// --- Fetch helpers ---

async function fetchChart(ticker) {
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(ticker)}?range=3mo&interval=1d`;
  const resp = await fetch(url, { headers: YAHOO_HEADERS });
  if (!resp.ok) return null;
  const data = await resp.json();
  const result = data?.chart?.result?.[0];
  if (!result) return null;

  const meta = result.meta || {};
  const closes = (result.indicators?.quote?.[0]?.close || []).filter(c => c != null);
  if (closes.length < 2) return null;

  const latest = closes[closes.length - 1];
  const prev = closes[closes.length - 2];
  const change = ((latest - prev) / prev) * 100;
  const high3m = Math.max(...closes);
  const low3m = Math.min(...closes);

  // Trend
  const avg5 = closes.slice(-5).reduce((a, b) => a + b, 0) / Math.min(closes.length, 5);
  const slice20 = closes.slice(-20);
  const avg20 = slice20.reduce((a, b) => a + b, 0) / slice20.length;
  let trend = "SIDEWAYS";
  if (avg5 > avg20 * 1.02) trend = "UPTREND";
  else if (avg5 < avg20 * 0.98) trend = "DOWNTREND";

  // Volatility
  const returns = [];
  for (let i = 1; i < closes.length; i++) {
    returns.push((closes[i] - closes[i - 1]) / closes[i - 1]);
  }
  const avgRet = returns.reduce((a, b) => a + b, 0) / returns.length;
  const variance = returns.reduce((a, r) => a + (r - avgRet) ** 2, 0) / returns.length;
  const annualVol = Math.sqrt(variance) * Math.sqrt(252) * 100;

  return {
    name: meta.shortName || meta.symbol || ticker,
    exchange: meta.exchangeName || "",
    currency: meta.currency || "USD",
    price: Math.round(latest * 100) / 100,
    prevClose: Math.round(prev * 100) / 100,
    change: Math.round(change * 100) / 100,
    high3m: Math.round(high3m * 100) / 100,
    low3m: Math.round(low3m * 100) / 100,
    trend,
    annualVol: Math.round(annualVol * 10) / 10,
    fiftyTwoWeekHigh: meta.fiftyTwoWeekHigh || null,
    fiftyTwoWeekLow: meta.fiftyTwoWeekLow || null,
    volume: meta.regularMarketVolume || null,
    closes: closes.map(c => Math.round(c * 100) / 100),
  };
}

async function fetchFundamentals(ticker) {
  const mods = "summaryProfile,financialData,defaultKeyStatistics,recommendationTrend";
  const url = `https://query1.finance.yahoo.com/v10/finance/quoteSummary/${encodeURIComponent(ticker)}?modules=${mods}`;
  try {
    const resp = await fetch(url, { headers: YAHOO_HEADERS });
    if (!resp.ok) return null;
    const data = await resp.json();
    const result = data?.quoteSummary?.result?.[0];
    if (!result) return null;

    const profile = result.summaryProfile || {};
    const fin = result.financialData || {};
    const stats = result.defaultKeyStatistics || {};
    const recTrends = result.recommendationTrend?.trend || [];
    const rec = recTrends[0] || {};

    const fmt = (obj) => (obj && typeof obj === "object" ? obj.fmt : null);

    return {
      sector: profile.sector || null,
      industry: profile.industry || null,
      summary: (profile.longBusinessSummary || "").slice(0, 600),
      website: profile.website || null,
      marketCap: fmt(fin.marketCap),
      revenueGrowth: fmt(fin.revenueGrowth),
      profitMargin: fmt(fin.profitMargins),
      targetPrice: fmt(fin.targetMeanPrice),
      targetHigh: fmt(fin.targetHighPrice),
      targetLow: fmt(fin.targetLowPrice),
      recommendation: fin.recommendationKey || null,
      pe: fmt(stats.forwardPE) || fmt(stats.trailingPE),
      pb: fmt(stats.priceToBook),
      dividendYield: fmt(stats.dividendYield),
      beta: fmt(stats.beta),
      analystBuy: (rec.strongBuy || 0) + (rec.buy || 0),
      analystHold: rec.hold || 0,
      analystSell: (rec.sell || 0) + (rec.strongSell || 0),
    };
  } catch {
    return null;
  }
}

// --- Sentiment ---

const POSITIVE = new Set([
  "surge","surges","surging","rally","rallies","rallying","soar","soars","soaring",
  "jump","jumps","gain","gains","rise","rises","rising","bullish","upgrade","upgrades",
  "upgraded","outperform","beat","beats","record","high","boost","boosts","strong",
  "growth","profit","profits","dividend","buyback","innovation","breakthrough",
  "opportunity","upside","buy","overweight","positive","optimistic","expand","expansion",
  "recover","recovery","accelerate","momentum","winner","boom",
]);

const NEGATIVE = new Set([
  "crash","crashes","plunge","plunges","plunging","tumble","tumbles","drop","drops",
  "fall","falls","falling","decline","declines","bearish","downgrade","downgrades",
  "downgraded","underperform","miss","misses","missed","low","loss","losses","risk",
  "risks","sell","underweight","negative","pessimistic","cut","cuts","layoff","layoffs",
  "warning","warn","debt","recession","slump","bankrupt","bankruptcy","fraud",
  "investigation","lawsuit","fine","weak","weakness","concern","fears","fear","volatile","trouble",
]);

function analyzeSentiment(text) {
  const words = new Set(text.toLowerCase().match(/\w+/g) || []);
  let pos = 0, neg = 0;
  for (const w of words) {
    if (POSITIVE.has(w)) pos++;
    if (NEGATIVE.has(w)) neg++;
  }
  const total = pos + neg;
  return total === 0 ? 0 : (pos - neg) / total;
}

async function fetchNews(ticker) {
  try {
    const url = `https://news.google.com/rss/search?q=${encodeURIComponent(ticker)}+stock&hl=en&gl=US&ceid=US:en`;
    const resp = await fetch(url, { headers: { "User-Agent": "Mozilla/5.0" } });
    if (!resp.ok) return [];
    const xml = await resp.text();

    // Parse RSS XML (simple regex approach for Worker environment)
    const items = [];
    const itemRegex = /<item>([\s\S]*?)<\/item>/g;
    let match;
    while ((match = itemRegex.exec(xml)) !== null && items.length < 12) {
      const itemXml = match[1];
      const title = (itemXml.match(/<title>([\s\S]*?)<\/title>/) || [])[1] || "";
      const source = (itemXml.match(/<source[^>]*>([\s\S]*?)<\/source>/) || [])[1] || "";
      const cleanTitle = title.replace(/<!\[CDATA\[|\]\]>/g, "").trim();
      if (cleanTitle) {
        const sentiment = analyzeSentiment(cleanTitle);
        items.push({ title: cleanTitle, source, sentiment: Math.round(sentiment * 100) / 100 });
      }
    }

    // Deduplicate
    const seen = new Set();
    const unique = items.filter(a => {
      const norm = a.title.toLowerCase().replace(/\W+/g, " ").trim();
      if (seen.has(norm)) return false;
      seen.add(norm);
      return true;
    });

    // Sort by sentiment strength
    unique.sort((a, b) => Math.abs(b.sentiment) - Math.abs(a.sentiment));
    return unique.slice(0, 12);
  } catch {
    return [];
  }
}

function buildSentimentSummary(articles) {
  if (!articles.length) return { score: 0, label: "No Data", positive: 0, negative: 0, neutral: 0, total: 0, articles: [] };
  const scores = articles.map(a => a.sentiment);
  const avg = scores.reduce((a, b) => a + b, 0) / scores.length;
  const positive = scores.filter(s => s > 0.1).length;
  const negative = scores.filter(s => s < -0.1).length;
  const neutral = scores.length - positive - negative;

  let label = "Mixed";
  if (avg > 0.25) label = "Very Positive";
  else if (avg > 0.1) label = "Positive";
  else if (avg < -0.25) label = "Very Negative";
  else if (avg < -0.1) label = "Negative";

  return {
    score: Math.round(avg * 1000) / 1000,
    label, positive, negative, neutral,
    total: articles.length,
    articles: articles.map(a => ({ title: a.title, source: a.source, sentiment: a.sentiment })),
  };
}

// --- Verdict ---

function buildVerdict(chart, fundamentals, sentiment) {
  let score = 50;
  const signals = [];

  if (chart) {
    if (chart.trend === "UPTREND") { score += 15; signals.push("3M trend is upward"); }
    else if (chart.trend === "DOWNTREND") { score -= 15; signals.push("3M trend is downward"); }
    else { signals.push("3M trend is sideways"); }

    const change = chart.change || 0;
    if (change > 1) { score += 10; signals.push(`Strong recent momentum (+${change.toFixed(1)}%)`); }
    else if (change > 0) { score += 5; signals.push(`Slight positive momentum (+${change.toFixed(1)}%)`); }
    else if (change < -1) { score -= 10; signals.push(`Negative momentum (${change.toFixed(1)}%)`); }
    else if (change < 0) { score -= 5; signals.push(`Slight negative momentum (${change.toFixed(1)}%)`); }

    const vol = chart.annualVol || 0;
    if (vol > 40) { score -= 5; signals.push(`High volatility (${vol.toFixed(0)}%) — higher risk`); }
    else if (vol < 20) { score += 5; signals.push(`Low volatility (${vol.toFixed(0)}%) — more stable`); }

    if (chart.fiftyTwoWeekHigh && chart.fiftyTwoWeekLow) {
      const range52 = chart.fiftyTwoWeekHigh - chart.fiftyTwoWeekLow;
      if (range52 > 0) {
        const position = (chart.price - chart.fiftyTwoWeekLow) / range52;
        if (position > 0.9) { score -= 5; signals.push("Trading near 52W high — limited upside"); }
        else if (position < 0.3) { score += 5; signals.push("Trading near 52W low — potential value"); }
      }
    }
  }

  if (fundamentals) {
    const rec = fundamentals.recommendation;
    if (rec === "buy" || rec === "strong_buy") { score += 15; signals.push(`Analyst consensus: ${rec.toUpperCase()}`); }
    else if (rec === "hold") { signals.push("Analyst consensus: HOLD"); }
    else if (rec === "sell" || rec === "strong_sell") { score -= 15; signals.push(`Analyst consensus: ${rec.toUpperCase()}`); }

    const target = fundamentals.targetPrice;
    if (target && chart) {
      try {
        const targetVal = parseFloat(String(target).replace(/,/g, ""));
        const upside = ((targetVal - chart.price) / chart.price) * 100;
        if (upside > 15) { score += 10; signals.push(`Target price implies +${upside.toFixed(0)}% upside`); }
        else if (upside > 5) { score += 5; signals.push(`Target price implies +${upside.toFixed(0)}% upside`); }
        else if (upside < -10) { score -= 10; signals.push(`Target price implies ${upside.toFixed(0)}% downside`); }
      } catch {}
    }

    const buy = fundamentals.analystBuy || 0;
    const sell = fundamentals.analystSell || 0;
    if (buy + sell > 0) {
      const ratio = buy / (buy + sell);
      if (ratio > 0.7) { score += 5; signals.push(`${buy} buy vs ${sell} sell ratings`); }
      else if (ratio < 0.3) { score -= 5; signals.push(`Only ${buy} buy vs ${sell} sell ratings`); }
    }
  }

  if (sentiment && sentiment.total > 0) {
    const sentScore = sentiment.score;
    const pos = sentiment.positive;
    const neg = sentiment.negative;
    const total = sentiment.total;
    if (sentScore > 0.2) { score += 10; signals.push(`News sentiment is positive (${pos}/${total} articles bullish)`); }
    else if (sentScore > 0.05) { score += 5; signals.push(`News sentiment leans positive (${pos}/${total} articles bullish)`); }
    else if (sentScore < -0.2) { score -= 10; signals.push(`News sentiment is negative (${neg}/${total} articles bearish)`); }
    else if (sentScore < -0.05) { score -= 5; signals.push(`News sentiment leans negative (${neg}/${total} articles bearish)`); }
    else { signals.push(`News sentiment is mixed (${pos} positive, ${neg} negative, ${total - pos - neg} neutral)`); }
  }

  score = Math.max(0, Math.min(100, score));

  let verdict, label;
  if (score >= 75) { verdict = "bullish"; label = "STRONG BUY"; }
  else if (score >= 60) { verdict = "bullish"; label = "BUY"; }
  else if (score >= 45) { verdict = "neutral"; label = "HOLD"; }
  else if (score >= 30) { verdict = "bearish"; label = "UNDERPERFORM"; }
  else { verdict = "bearish"; label = "SELL"; }

  return { verdict, label, score, text: `${label} — Score: ${score}/100`, signals };
}

// --- Request handler ---

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

export default {
  async fetch(request) {
    const url = new URL(request.url);

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: CORS_HEADERS });
    }

    const match = url.pathname.match(/^\/api\/stock\/(.+)$/);
    if (!match) {
      return new Response(JSON.stringify({ error: "Use /api/stock/<TICKER>" }), {
        status: 404,
        headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
      });
    }

    const ticker = decodeURIComponent(match[1]).trim().toUpperCase();
    if (!ticker) {
      return new Response(JSON.stringify({ error: "Missing ticker" }), {
        status: 400,
        headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
      });
    }

    const quick = url.searchParams.get("quick") === "1";

    let chart = null, fundamentals = null, newsArticles = [];

    if (quick) {
      chart = await fetchChart(ticker);
    } else {
      [chart, fundamentals, newsArticles] = await Promise.all([
        fetchChart(ticker),
        fetchFundamentals(ticker),
        fetchNews(ticker),
      ]);
    }

    if (!chart && !fundamentals) {
      return new Response(JSON.stringify({ error: `No data found for ${ticker}` }), {
        status: 404,
        headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
      });
    }

    const sentiment = buildSentimentSummary(newsArticles);
    const verdict = buildVerdict(chart, fundamentals, sentiment);

    const result = {
      ticker,
      timestamp: new Date().toISOString(),
      chart,
      fundamentals: quick ? null : fundamentals,
      sentiment: quick ? null : sentiment,
      verdict: quick ? null : verdict,
    };

    return new Response(JSON.stringify(result), {
      status: 200,
      headers: { ...CORS_HEADERS, "Content-Type": "application/json", "Cache-Control": "public, max-age=60" },
    });
  },
};
