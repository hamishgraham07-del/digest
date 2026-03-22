#!/usr/bin/env python3
"""
Lightweight local stock data API server for the Daily Digest PWA.
Runs on port 8093. Fetches stock data from Yahoo Finance (server-side, no CORS issues)
and serves it to the PWA's search page.

Usage:
    python3 stock_api.py

Endpoints:
    GET /api/stock/<ticker>  — Returns full stock evaluation JSON
"""

import json
import http.server
import urllib.request
import urllib.parse
import ssl
import math
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

PORT = 8093

# SSL context for Yahoo Finance
ctx = ssl.create_default_context()


def fetch_chart(ticker):
    """Fetch 3-month daily chart data from Yahoo Finance."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ticker)}?range=3mo&interval=1d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
        data = json.loads(resp.read())
    result = data.get("chart", {}).get("result", [None])[0]
    if not result:
        return None

    meta = result.get("meta", {})
    closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
    valid = [c for c in closes if c is not None]

    if len(valid) < 2:
        return None

    latest = valid[-1]
    prev = valid[-2]
    change = (latest - prev) / prev * 100

    high3m = max(valid)
    low3m = min(valid)

    # Trend: 5-day avg vs 20-day avg
    avg5 = sum(valid[-5:]) / len(valid[-5:])
    avg20 = sum(valid[-20:]) / len(valid[-20:]) if len(valid) >= 20 else sum(valid) / len(valid)
    if avg5 > avg20 * 1.02:
        trend = "UPTREND"
    elif avg5 < avg20 * 0.98:
        trend = "DOWNTREND"
    else:
        trend = "SIDEWAYS"

    # Volatility
    returns = [(valid[i] - valid[i - 1]) / valid[i - 1] for i in range(1, len(valid))]
    avg_ret = sum(returns) / len(returns)
    variance = sum((r - avg_ret) ** 2 for r in returns) / len(returns)
    daily_vol = math.sqrt(variance)
    annual_vol = daily_vol * math.sqrt(252)

    return {
        "name": meta.get("shortName") or meta.get("symbol", ticker),
        "exchange": meta.get("exchangeName", ""),
        "currency": meta.get("currency", "USD"),
        "price": round(latest, 2),
        "prevClose": round(prev, 2),
        "change": round(change, 2),
        "high3m": round(high3m, 2),
        "low3m": round(low3m, 2),
        "trend": trend,
        "annualVol": round(annual_vol * 100, 1),
        "fiftyTwoWeekHigh": meta.get("fiftyTwoWeekHigh"),
        "fiftyTwoWeekLow": meta.get("fiftyTwoWeekLow"),
        "volume": meta.get("regularMarketVolume"),
        "closes": [round(c, 2) for c in valid],
    }


def fetch_fundamentals(ticker):
    """Fetch company fundamentals from Yahoo Finance quoteSummary."""
    mods = "summaryProfile,financialData,defaultKeyStatistics,recommendationTrend"
    url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{urllib.parse.quote(ticker)}?modules={mods}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
            data = json.loads(resp.read())
        result = data.get("quoteSummary", {}).get("result", [None])[0]
        if not result:
            return None

        profile = result.get("summaryProfile", {})
        fin = result.get("financialData", {})
        stats = result.get("defaultKeyStatistics", {})
        rec_trends = result.get("recommendationTrend", {}).get("trend", [])
        rec = rec_trends[0] if rec_trends else {}

        def fmt(obj, key="fmt"):
            return obj.get(key) if isinstance(obj, dict) else None

        return {
            "sector": profile.get("sector"),
            "industry": profile.get("industry"),
            "summary": profile.get("longBusinessSummary", "")[:600],
            "website": profile.get("website"),
            "marketCap": fmt(fin.get("marketCap", {})),
            "revenueGrowth": fmt(fin.get("revenueGrowth", {})),
            "profitMargin": fmt(fin.get("profitMargins", {})),
            "targetPrice": fmt(fin.get("targetMeanPrice", {})),
            "targetHigh": fmt(fin.get("targetHighPrice", {})),
            "targetLow": fmt(fin.get("targetLowPrice", {})),
            "recommendation": fin.get("recommendationKey"),
            "pe": fmt(stats.get("forwardPE", {})) or fmt(stats.get("trailingPE", {})),
            "pb": fmt(stats.get("priceToBook", {})),
            "dividendYield": fmt(stats.get("dividendYield", {})),
            "beta": fmt(stats.get("beta", {})),
            "analystBuy": (rec.get("strongBuy", 0) or 0) + (rec.get("buy", 0) or 0),
            "analystHold": rec.get("hold", 0) or 0,
            "analystSell": (rec.get("sell", 0) or 0) + (rec.get("strongSell", 0) or 0),
        }
    except Exception:
        return None


# Sentiment keyword lists
POSITIVE_WORDS = {
    "surge", "surges", "surging", "rally", "rallies", "rallying", "soar", "soars",
    "soaring", "jump", "jumps", "gain", "gains", "rise", "rises", "rising",
    "bullish", "upgrade", "upgrades", "upgraded", "outperform", "beat", "beats",
    "record", "high", "boost", "boosts", "strong", "growth", "profit", "profits",
    "dividend", "buyback", "innovation", "breakthrough", "opportunity", "upside",
    "buy", "overweight", "positive", "optimistic", "expand", "expansion",
    "recover", "recovery", "accelerate", "momentum", "winner", "boom",
}

NEGATIVE_WORDS = {
    "crash", "crashes", "plunge", "plunges", "plunging", "tumble", "tumbles",
    "drop", "drops", "fall", "falls", "falling", "decline", "declines",
    "bearish", "downgrade", "downgrades", "downgraded", "underperform",
    "miss", "misses", "missed", "low", "loss", "losses", "risk", "risks",
    "sell", "underweight", "negative", "pessimistic", "cut", "cuts",
    "layoff", "layoffs", "warning", "warn", "debt", "recession", "slump",
    "bankrupt", "bankruptcy", "fraud", "investigation", "lawsuit", "fine",
    "weak", "weakness", "concern", "fears", "fear", "volatile", "trouble",
}


def analyze_sentiment(text):
    """Score a headline from -1 (very negative) to +1 (very positive)."""
    words = set(re.findall(r'\w+', text.lower()))
    pos = len(words & POSITIVE_WORDS)
    neg = len(words & NEGATIVE_WORDS)
    total = pos + neg
    if total == 0:
        return 0
    return (pos - neg) / total


def fetch_news(ticker, company_name=None):
    """Fetch recent news from Google News RSS and Yahoo Finance."""
    articles = []

    # Google News RSS — search by ticker and company name
    queries = [ticker]
    if company_name and company_name != ticker:
        queries.append(f"{company_name} stock")

    for query in queries:
        try:
            encoded = urllib.parse.quote(query)
            url = f"https://news.google.com/rss/search?q={encoded}+stock&hl=en&gl=US&ceid=US:en"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, context=ctx, timeout=8) as resp:
                xml_data = resp.read()
            root = ET.fromstring(xml_data)
            for item in root.findall(".//item")[:8]:
                title = item.findtext("title", "")
                source = item.findtext("source", "")
                pub_date = item.findtext("pubDate", "")
                if title:
                    articles.append({
                        "title": title,
                        "source": source,
                        "date": pub_date,
                        "origin": "Google News",
                    })
        except Exception:
            pass

    # Deduplicate by title similarity
    seen_titles = set()
    unique = []
    for a in articles:
        # Simple dedup: normalize and check
        norm = re.sub(r'\W+', ' ', a["title"].lower()).strip()
        if norm not in seen_titles:
            seen_titles.add(norm)
            unique.append(a)

    # Score each article
    for a in unique:
        a["sentiment"] = analyze_sentiment(a["title"])

    # Sort by sentiment strength (most opinionated first)
    unique.sort(key=lambda a: abs(a["sentiment"]), reverse=True)

    return unique[:12]


def build_sentiment_summary(articles):
    """Aggregate sentiment across all articles."""
    if not articles:
        return {"score": 0, "label": "No Data", "positive": 0, "negative": 0, "neutral": 0, "articles": []}

    scores = [a["sentiment"] for a in articles]
    avg = sum(scores) / len(scores)

    positive = sum(1 for s in scores if s > 0.1)
    negative = sum(1 for s in scores if s < -0.1)
    neutral = len(scores) - positive - negative

    if avg > 0.25:
        label = "Very Positive"
    elif avg > 0.1:
        label = "Positive"
    elif avg > -0.1:
        label = "Mixed"
    elif avg > -0.25:
        label = "Negative"
    else:
        label = "Very Negative"

    return {
        "score": round(avg, 3),
        "label": label,
        "positive": positive,
        "negative": negative,
        "neutral": neutral,
        "total": len(articles),
        "articles": [
            {"title": a["title"], "source": a["source"], "sentiment": round(a["sentiment"], 2)}
            for a in articles
        ],
    }


def build_verdict(chart, fundamentals, sentiment=None):
    """Determine overall verdict with a 0-100 confidence score."""
    score = 50  # Start neutral
    signals = []

    if chart:
        # Trend signal (+/- 15)
        if chart["trend"] == "UPTREND":
            score += 15
            signals.append("3M trend is upward")
        elif chart["trend"] == "DOWNTREND":
            score -= 15
            signals.append("3M trend is downward")
        else:
            signals.append("3M trend is sideways")

        # Recent momentum (+/- 10)
        change = chart.get("change", 0)
        if change > 1:
            score += 10
            signals.append(f"Strong recent momentum (+{change:.1f}%)")
        elif change > 0:
            score += 5
            signals.append(f"Slight positive momentum (+{change:.1f}%)")
        elif change < -1:
            score -= 10
            signals.append(f"Negative momentum ({change:.1f}%)")
        elif change < 0:
            score -= 5
            signals.append(f"Slight negative momentum ({change:.1f}%)")

        # Volatility risk (+/- 5)
        vol = chart.get("annualVol", 0)
        if vol > 40:
            score -= 5
            signals.append(f"High volatility ({vol:.0f}%) — higher risk")
        elif vol < 20:
            score += 5
            signals.append(f"Low volatility ({vol:.0f}%) — more stable")

        # Price vs 52W range
        if chart.get("fiftyTwoWeekHigh") and chart.get("fiftyTwoWeekLow"):
            price = chart["price"]
            high = chart["fiftyTwoWeekHigh"]
            low = chart["fiftyTwoWeekLow"]
            range52 = high - low
            if range52 > 0:
                position = (price - low) / range52
                if position > 0.9:
                    score -= 5
                    signals.append("Trading near 52W high — limited upside")
                elif position < 0.3:
                    score += 5
                    signals.append("Trading near 52W low — potential value")

    if fundamentals:
        # Analyst consensus (+/- 15)
        rec = fundamentals.get("recommendation")
        if rec in ("buy", "strong_buy"):
            score += 15
            signals.append(f"Analyst consensus: {rec.upper()}")
        elif rec == "hold":
            signals.append("Analyst consensus: HOLD")
        elif rec in ("sell", "strong_sell"):
            score -= 15
            signals.append(f"Analyst consensus: {rec.upper()}")

        # Target price vs current (+/- 10)
        target = fundamentals.get("targetPrice")
        if target and chart:
            try:
                target_val = float(target.replace(",", ""))
                upside = (target_val - chart["price"]) / chart["price"] * 100
                if upside > 15:
                    score += 10
                    signals.append(f"Target price implies +{upside:.0f}% upside")
                elif upside > 5:
                    score += 5
                    signals.append(f"Target price implies +{upside:.0f}% upside")
                elif upside < -10:
                    score -= 10
                    signals.append(f"Target price implies {upside:.0f}% downside")
            except (ValueError, TypeError):
                pass

        # Analyst buy/sell ratio
        buy = fundamentals.get("analystBuy", 0) or 0
        sell = fundamentals.get("analystSell", 0) or 0
        if buy + sell > 0:
            ratio = buy / (buy + sell)
            if ratio > 0.7:
                score += 5
                signals.append(f"{buy} buy vs {sell} sell ratings")
            elif ratio < 0.3:
                score -= 5
                signals.append(f"Only {buy} buy vs {sell} sell ratings")

    # News sentiment (+/- 10)
    if sentiment and sentiment.get("total", 0) > 0:
        sent_score = sentiment["score"]  # -1 to +1
        pos = sentiment["positive"]
        neg = sentiment["negative"]
        total = sentiment["total"]
        if sent_score > 0.2:
            score += 10
            signals.append(f"News sentiment is positive ({pos}/{total} articles bullish)")
        elif sent_score > 0.05:
            score += 5
            signals.append(f"News sentiment leans positive ({pos}/{total} articles bullish)")
        elif sent_score < -0.2:
            score -= 10
            signals.append(f"News sentiment is negative ({neg}/{total} articles bearish)")
        elif sent_score < -0.05:
            score -= 5
            signals.append(f"News sentiment leans negative ({neg}/{total} articles bearish)")
        else:
            signals.append(f"News sentiment is mixed ({pos} positive, {neg} negative, {total - pos - neg} neutral)")

    # Clamp score
    score = max(0, min(100, score))

    # Determine verdict label
    if score >= 75:
        verdict = "bullish"
        label = "STRONG BUY"
    elif score >= 60:
        verdict = "bullish"
        label = "BUY"
    elif score >= 45:
        verdict = "neutral"
        label = "HOLD"
    elif score >= 30:
        verdict = "bearish"
        label = "UNDERPERFORM"
    else:
        verdict = "bearish"
        label = "SELL"

    text = f"{label} — Score: {score}/100"

    return {
        "verdict": verdict,
        "label": label,
        "score": score,
        "text": text,
        "signals": signals,
    }


class StockHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        # CORS headers
        if self.path.startswith("/api/stock/"):
            path_and_query = self.path.split("/api/stock/")[1]
            ticker = urllib.parse.unquote(path_and_query.split("?")[0]).strip().upper()
            if not ticker:
                self.send_error(400, "Missing ticker")
                return

            # ?quick=1 skips news/sentiment (used by markets page for speed)
            quick = "quick=1" in path_and_query

            chart = None
            fundamentals = None
            news_articles = []

            if quick:
                # Fast path: only fetch chart data (no fundamentals, no news)
                try:
                    chart = fetch_chart(ticker)
                except Exception:
                    pass
            else:
                # Full path: fetch chart, fundamentals, and news in parallel
                with ThreadPoolExecutor(max_workers=3) as pool:
                    chart_future = pool.submit(fetch_chart, ticker)
                    fund_future = pool.submit(fetch_fundamentals, ticker)
                    news_future = pool.submit(fetch_news, ticker)

                    try:
                        chart = chart_future.result(timeout=15)
                    except Exception:
                        pass
                    try:
                        fundamentals = fund_future.result(timeout=15)
                    except Exception:
                        pass
                    try:
                        news_articles = news_future.result(timeout=15)
                    except Exception:
                        news_articles = []

            if not chart and not fundamentals:
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"error": f"No data found for {ticker}"}).encode())
                return

            # If we got a company name, re-fetch news with it for better coverage
            company_name = None
            if chart and chart.get("name"):
                company_name = chart["name"]
            if company_name and company_name != ticker and len(news_articles) < 4:
                try:
                    extra = fetch_news(ticker, company_name)
                    # Merge, deduplicate
                    seen = {re.sub(r'\W+', ' ', a["title"].lower()).strip() for a in news_articles}
                    for a in extra:
                        norm = re.sub(r'\W+', ' ', a["title"].lower()).strip()
                        if norm not in seen:
                            news_articles.append(a)
                            seen.add(norm)
                except Exception:
                    pass

            sentiment = build_sentiment_summary(news_articles)
            verdict = build_verdict(chart, fundamentals, sentiment)

            result = {
                "ticker": ticker,
                "timestamp": datetime.now().isoformat(),
                "chart": chart,
                "fundamentals": fundamentals,
                "sentiment": sentiment,
                "verdict": verdict,
            }

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
        else:
            self.send_error(404, "Not found. Use /api/stock/<TICKER>")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format, *args):
        print(f"[stock-api] {args[0]}")


if __name__ == "__main__":
    server = http.server.HTTPServer(("127.0.0.1", PORT), StockHandler)
    print(f"Stock API running on http://localhost:{PORT}")
    print("Example: http://localhost:{PORT}/api/stock/AAPL")
    server.serve_forever()
