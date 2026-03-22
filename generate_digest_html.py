#!/usr/bin/env python3
"""
Generate the Daily Digest PWA index.html from a JSON data file.

Usage:
    python3 generate_digest_html.py data.json
    python3 generate_digest_html.py --sample   # Generate with sample data for testing

The JSON should contain keys matching the sections of the digest.
Output: index.html in the same directory as this script.
"""

import json
import sys
import os
import subprocess
import shutil
from datetime import datetime

import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "index.html")
ARCHIVE_DIR = os.path.join(SCRIPT_DIR, "archive")

# --- Weather ---
def fetch_weather():
    """Fetch Sydney weather from Open-Meteo (free, no API key)."""
    try:
        resp = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": -33.8688,
            "longitude": 151.2093,
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode,uv_index_max",
            "hourly": "temperature_2m,precipitation_probability",
            "timezone": "Australia/Sydney",
            "forecast_days": 1
        }, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        daily = data.get("daily", {})
        hourly = data.get("hourly", {})
        max_temp = daily.get("temperature_2m_max", [None])[0]
        min_temp = daily.get("temperature_2m_min", [None])[0]
        precip = daily.get("precipitation_sum", [0])[0]
        weathercode = daily.get("weathercode", [0])[0]
        uv = daily.get("uv_index_max", [None])[0]
        rain_probs = hourly.get("precipitation_probability", [])
        max_rain_prob = max(rain_probs) if rain_probs else 0
        return {
            "max_temp": max_temp,
            "min_temp": min_temp,
            "precip_mm": precip,
            "weathercode": weathercode,
            "uv_index": uv,
            "rain_prob": max_rain_prob,
            "description": wmo_description(weathercode),
            "icon": wmo_icon(weathercode)
        }
    except Exception as e:
        return {"error": str(e), "description": "Weather unavailable", "icon": "?",
                "max_temp": "?", "min_temp": "?", "rain_prob": "?", "uv_index": "?"}


def wmo_description(code):
    """Convert WMO weather code to human description."""
    descriptions = {
        0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
        45: "Foggy", 48: "Depositing rime fog",
        51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
        61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
        71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
        80: "Slight showers", 81: "Moderate showers", 82: "Violent showers",
        95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Thunderstorm with heavy hail",
    }
    return descriptions.get(code, "Unknown")


def wmo_icon(code):
    """Convert WMO weather code to emoji."""
    if code == 0: return "\u2600\ufe0f"      # sun
    if code in (1, 2): return "\u26c5"         # sun behind cloud
    if code == 3: return "\u2601\ufe0f"        # cloud
    if code in (45, 48): return "\U0001f32b\ufe0f"  # fog
    if code in (51, 53, 55, 61, 63, 65, 80, 81, 82): return "\U0001f327\ufe0f"  # rain
    if code in (71, 73, 75): return "\u2744\ufe0f"   # snow
    if code in (95, 96, 99): return "\u26a1"          # lightning
    return "\U0001f324\ufe0f"                          # sun behind small cloud


# --- Calendar ---
def fetch_calendar():
    """Read today's events from Calendar.app via osascript."""
    script = '''
    tell application "Calendar"
        set today to current date
        set time of today to 0
        set todayEnd to today + 86400
        set output to ""
        repeat with c in calendars
            set calName to name of c
            try
                repeat with e in (events of c whose start date >= today and start date < todayEnd)
                    set evtTitle to summary of e
                    set evtStart to start date of e
                    set evtLoc to ""
                    try
                        set evtLoc to location of e
                    end try
                    set h to hours of evtStart
                    set m to minutes of evtStart
                    if h < 10 then
                        set hStr to "0" & h
                    else
                        set hStr to h as text
                    end if
                    if m < 10 then
                        set mStr to "0" & m
                    else
                        set mStr to m as text
                    end if
                    set timeStr to hStr & ":" & mStr
                    set output to output & timeStr & " | " & evtTitle & " | " & evtLoc & " | " & calName & linefeed
                end repeat
            end try
        end repeat
        return output
    end tell
    '''
    try:
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
        events = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 2:
                events.append({
                    "time": parts[0],
                    "title": parts[1],
                    "location": parts[2] if len(parts) > 2 else "",
                    "calendar": parts[3] if len(parts) > 3 else ""
                })
        events.sort(key=lambda e: e["time"])
        return events
    except Exception:
        return []  # Empty list — template shows "No events today" gracefully


# --- HTML Generation ---
def escape_html(text):
    """Escape HTML special characters."""
    if not isinstance(text, str):
        text = str(text)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def signal_class(signal):
    """Return CSS class for a market signal."""
    s = signal.upper() if signal else ""
    if s in ("BULLISH", "RECOVERING", "SURGING", "RISING"):
        return "signal-bullish"
    if s in ("PULLBACK", "DRAWDOWN", "SLIDING", "FALLING"):
        return "signal-bearish"
    return "signal-neutral"


def build_section(section_id, title, body_html, collapsed=False):
    """Build a collapsible section card."""
    cls = "section collapsed" if collapsed else "section"
    return f'''
    <div class="{cls}" id="{section_id}">
      <div class="section-header" onclick="this.parentElement.classList.toggle('collapsed')">
        <span class="section-title">{escape_html(title)}</span>
        <span class="section-chevron">&#9662;</span>
      </div>
      <div class="section-body">{body_html}</div>
    </div>'''


def build_weather_card(weather):
    """Build the weather card HTML."""
    uv = weather.get("uv_index", "?")
    if isinstance(uv, (int, float)):
        if uv >= 8: uv_label = f"{uv:.0f} (Very High)"
        elif uv >= 6: uv_label = f"{uv:.0f} (High)"
        elif uv >= 3: uv_label = f"{uv:.0f} (Moderate)"
        else: uv_label = f"{uv:.0f} (Low)"
    else:
        uv_label = str(uv)

    return f'''
    <div class="weather-card">
      <div class="weather-icon">{weather.get("icon", "?")}</div>
      <div class="weather-details">
        <div class="weather-temp">{weather.get("min_temp", "?")}&#8211;{weather.get("max_temp", "?")}&#176;C</div>
        <div class="weather-desc">{escape_html(weather.get("description", ""))}</div>
        <div class="weather-meta">
          <span>Rain {weather.get("rain_prob", "?")}%</span>
          <span>UV {uv_label}</span>
        </div>
      </div>
    </div>'''


def build_calendar_section(events):
    """Build the calendar events HTML."""
    if not events:
        return '<div class="text-secondary" style="padding:8px 0;">No events today</div>'
    html = ""
    for e in events:
        loc_html = f'<div class="cal-location">{escape_html(e["location"])}</div>' if e.get("location") else ""
        html += f'''
        <div class="cal-event">
          <div class="cal-time">{escape_html(e["time"])}</div>
          <div>
            <div class="cal-title">{escape_html(e["title"])}</div>
            {loc_html}
          </div>
        </div>'''
    return html


def build_portfolio_table(assets):
    """Build the portfolio watchlist table."""
    rows = ""
    for a in assets:
        if isinstance(a, list):
            name, price, change, signal = a[0], a[1], a[2], a[3]
            outlook = a[4] if len(a) > 4 else ""
        else:
            name = a.get("name", "")
            price = a.get("price", "")
            change = a.get("change", "")
            signal = a.get("signal", "")
            outlook = a.get("outlook", "")
        cls = signal_class(signal)
        rows += f'''
          <tr>
            <td>{escape_html(name)}</td>
            <td>{escape_html(price)}</td>
            <td>{escape_html(change)}</td>
            <td class="{cls}">{escape_html(signal)}</td>
            <td>{escape_html(outlook)}</td>
          </tr>'''
    return f'''
    <div class="table-wrapper">
      <table class="portfolio-table">
        <thead><tr><th>Asset</th><th>Price</th><th>Change</th><th>Signal</th><th>Outlook</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>'''


def build_news_section(stories):
    """Build a news section with expandable story cards."""
    html = ""
    for i, s in enumerate(stories):
        headline = s.get("headline", "")
        body = s.get("body", "")
        why = s.get("why", "")
        extended = s.get("extended", "")
        why_html = f'<div class="story-why">{escape_html(why)}</div>' if why else ""
        extended_html = f'<div class="story-extended">{extended}</div>' if extended else ""
        html += f'''
        <div class="story">
          <div class="story-headline" onclick="this.parentElement.classList.toggle(\'expanded\')">{escape_html(headline)} <span class="story-expand-hint">&#8250;</span></div>
          <div class="story-body">{escape_html(body)}</div>
          {why_html}
          {extended_html}
        </div>'''
    return html


def build_sports_section(leagues):
    """Build sports section from league data with matches and standings."""
    html = ""
    for league in leagues:
        html += f'<div class="sport-league">{escape_html(league.get("name", ""))}</div>'
        for match in league.get("matches", []):
            teams = match.get("teams", "")
            score = match.get("score", "")
            time_str = match.get("time", "")
            if score:
                html += f'''
                <div class="match">
                  <span class="match-teams">{escape_html(teams)}</span>
                  <span class="match-score">{escape_html(score)}</span>
                </div>'''
            else:
                html += f'''
                <div class="match">
                  <span class="match-teams">{escape_html(teams)}</span>
                  <span class="match-time">{escape_html(time_str)}</span>
                </div>'''
        # League standings/ladder
        standings = league.get("standings", [])
        if standings:
            # Detect columns from first row
            first = standings[0] if standings else {}
            has_d = "d" in first
            has_pct = "pct_or_gd" in first
            header = "<th>#</th><th>Team</th><th>W</th><th>L</th>"
            if has_d:
                header += "<th>D</th>"
            header += "<th>Pts</th>"
            if has_pct:
                header += "<th>%/GD</th>"
            rows = ""
            for s in standings:
                pos = s.get("pos", "")
                team = s.get("team", "")
                w = s.get("w", "")
                l = s.get("l", "")
                d = s.get("d", "")
                pts = s.get("pts", "")
                pct = s.get("pct_or_gd", "")
                row = f"<td>{escape_html(str(pos))}</td><td>{escape_html(str(team))}</td><td>{escape_html(str(w))}</td><td>{escape_html(str(l))}</td>"
                if has_d:
                    row += f"<td>{escape_html(str(d))}</td>"
                row += f"<td>{escape_html(str(pts))}</td>"
                if has_pct:
                    row += f"<td>{escape_html(str(pct))}</td>"
                rows += f"<tr>{row}</tr>"
            html += f'''
            <div class="table-wrapper" style="margin-top:8px;">
              <table class="league-table">
                <thead><tr>{header}</tr></thead>
                <tbody>{rows}</tbody>
              </table>
            </div>'''
    return html


def build_events_section(events):
    """Build Sydney events section."""
    html = ""
    for e in events:
        pub = e.get("pub", "")
        pub_html = f'<div class="event-pub">Nearby: {escape_html(pub)}</div>' if pub else ""
        html += f'''
        <div class="event">
          <div class="event-name">{escape_html(e.get("name", ""))}</div>
          <div class="event-details">{escape_html(e.get("details", ""))}</div>
          {pub_html}
        </div>'''
    return html


def build_pitch_section(pitch):
    """Build entrepreneurial opportunity pitch card."""
    fields = ["sector", "why_now", "what_youd_build", "revenue_model", "risk_level", "capital_needed", "time_to_revenue"]
    labels = {"sector": "Sector", "why_now": "Why Now", "what_youd_build": "What You'd Build",
              "revenue_model": "Revenue Model", "risk_level": "Risk Level",
              "capital_needed": "Capital Needed", "time_to_revenue": "Time to Revenue"}
    html = ""
    for f in fields:
        val = pitch.get(f, "")
        if val:
            html += f'''
            <div class="pitch-field">
              <span class="pitch-label">{labels.get(f, f)}</span>
              <span class="pitch-value">{escape_html(val)}</span>
            </div>'''
    intro = pitch.get("intro", "")
    if intro:
        html = f'<div class="narrative"><p>{escape_html(intro)}</p></div>' + html
    return html


def generate_html(data):
    """Generate the full index.html from structured data."""
    now = datetime.now()
    date_str = data.get("date_str", now.strftime("%A, %d %B %Y"))
    time_str = data.get("time_str", now.strftime("%I:%M %p AEST"))
    date_iso = data.get("date_iso", now.strftime("%Y-%m-%d"))

    weather = data.get("weather", fetch_weather())
    calendar_events = data.get("calendar", fetch_calendar())

    # Build each section
    weather_html = build_weather_card(weather)
    calendar_html = build_section("calendar", "Today's Calendar", build_calendar_section(calendar_events))
    big_picture_html = build_section("big-picture", "The Big Picture", f'<div class="narrative">{data.get("big_picture", "")}</div>')
    portfolio_html = build_section("portfolio", "Portfolio Watchlist", build_portfolio_table(data.get("assets", [])))
    strategy_html = build_section("strategy", "Strategy & Cash Position", f'<div class="narrative">{data.get("strategy", "")}</div>')
    world_news_html = build_section("world-news", "World News", build_news_section(data.get("world_news", [])))
    au_news_html = build_section("au-news", "Australia News", build_news_section(data.get("au_news", [])))
    ai_tech_html = build_section("ai-tech", "AI & Technology", build_news_section(data.get("ai_tech", [])))
    sports_html = build_section("sports", "Sports", build_sports_section(data.get("sports", [])))
    events_html = build_section("events", "Sydney & Surrounds", build_events_section(data.get("events", [])))
    twk_html = build_section("twk", "Things Worth Knowing", f'<div class="narrative">{data.get("things_worth_knowing", "")}</div>')

    sources = escape_html(data.get("sources", ""))

    # Section IDs for nav dots
    section_ids = ["weather", "calendar", "big-picture", "portfolio", "strategy",
                   "world-news", "au-news", "ai-tech", "sports", "events", "twk"]
    nav_dots = "\n".join(f'    <div class="nav-dot" data-section="{sid}"></div>' for sid in section_ids)

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="default">
  <meta name="apple-mobile-web-app-title" content="Briefing">
  <meta name="theme-color" content="#FFFFFF">
  <link rel="manifest" href="manifest.json">
  <link rel="apple-touch-icon" href="icon-192.png">
  <link rel="stylesheet" href="style.css">
  <title>Morning Briefing — {escape_html(date_str)}</title>
</head>
<body>

  <div class="header">
    <div>
      <div class="header-title">Morning Briefing</div>
      <div class="header-date">{escape_html(date_str)} &middot; {escape_html(time_str)}</div>
    </div>
    <button class="theme-toggle" onclick="toggleTheme()">Dark</button>
  </div>

  <div class="nav-dots" id="navDots">
{nav_dots}
  </div>

  <div id="weather">
{weather_html}
  </div>

{calendar_html}
{big_picture_html}
{portfolio_html}
{strategy_html}
{world_news_html}
{au_news_html}
{ai_tech_html}
{sports_html}
{events_html}
{twk_html}

  <div class="footer" style="padding-bottom:80px;">
    {sources}<br>
    Generated {escape_html(time_str)}
  </div>

  <!-- Bottom Navigation -->
  <div class="bottom-nav">
    <a href="index.html" class="nav-btn active">
      <span class="nav-btn-icon">&#9783;</span>
      <span>Digest</span>
    </a>
    <a href="markets.html" class="nav-btn">
      <span class="nav-btn-icon">&#128200;</span>
      <span>Markets</span>
    </a>
    <a href="search.html" class="nav-btn">
      <span class="nav-btn-icon">&#128270;</span>
      <span>Stocks</span>
    </a>
  </div>

  <script>
    // Theme toggle
    function toggleTheme() {{
      const body = document.body;
      const btn = document.querySelector('.theme-toggle');
      const meta = document.querySelector('meta[name="theme-color"]');
      if (body.getAttribute('data-theme') === 'dark') {{
        body.removeAttribute('data-theme');
        btn.textContent = 'Dark';
        meta.content = '#FFFFFF';
      }} else {{
        body.setAttribute('data-theme', 'dark');
        btn.textContent = 'Light';
        meta.content = '#1A1A1A';
      }}
      localStorage.setItem('theme', body.getAttribute('data-theme') || 'light');
    }}

    // Restore theme preference
    if (localStorage.getItem('theme') === 'dark') {{
      document.body.setAttribute('data-theme', 'dark');
      document.querySelector('.theme-toggle').textContent = 'Light';
      document.querySelector('meta[name="theme-color"]').content = '#1A1A1A';
    }}

    // Nav dots — highlight active section on scroll
    const sections = document.querySelectorAll('.section, #weather');
    const dots = document.querySelectorAll('.nav-dot');
    const observer = new IntersectionObserver(entries => {{
      entries.forEach(entry => {{
        if (entry.isIntersecting) {{
          const id = entry.target.id;
          dots.forEach(d => d.classList.toggle('active', d.dataset.section === id));
        }}
      }});
    }}, {{ threshold: 0.3 }});
    sections.forEach(s => observer.observe(s));

    // Service worker registration
    if ('serviceWorker' in navigator) {{
      navigator.serviceWorker.register('sw.js');
    }}
  </script>

</body>
</html>'''

    return html, date_iso


def get_sample_data():
    """Return sample data for testing the digest layout."""
    return {
        "date_str": "Saturday, 22 March 2026",
        "time_str": "6:00 AM AEST",
        "date_iso": "2026-03-22",
        "big_picture": "<p>Oil is the story today. Brent crude surged 7.4% overnight after reports of vessels struck near the Strait of Hormuz &mdash; the chokepoint for roughly 20% of the world's petroleum. That's dragged the ASX 200 down nearly 1% as the RBA rate hike narrative gathers steam, with CBA, Westpac and NAB all now forecasting a 25bp move at next week's meeting.</p><p>Your cash position looks increasingly smart right now. The pullback across WDS, STO and NDQ ETF is creating entry points, but there's no rush &mdash; let the dust settle on the Hormuz situation first. Patience is a legitimate strategy when the macro picture is this uncertain.</p>",
        "strategy": "<p>The current pullback offers potential entry points for NDQ (now $51.41). With your cash position, there's no rush to deploy &mdash; maintain gold exposure as a geopolitical hedge while monitoring the RBA decision on March 24. High yields favour cash positioning for now, so sitting tight earns decent returns with zero risk.</p>",
        "assets": [
            ["S&P 500", "6,752.50", "-0.43%", "PULLBACK", "Tech profit-taking amid rising yields"],
            ["NASDAQ", "19,250.40", "+0.30%", "NEUTRAL", "Consolidation after record run"],
            ["Dow Jones", "39,100.00", "-0.65%", "PULLBACK", "Industrials dragged by oil spike"],
            ["FTSE 100", "10,284.75", "-1.24%", "PULLBACK", "Energy majors volatile"],
            ["Nikkei 225", "55,025.37", "+1.40%", "BULLISH", "Yen weakness boosting exporters"],
            ["ASX 200", "8,851.00", "-0.99%", "PULLBACK", "RBA hike fears hitting materials"],
            ["Gold USD/oz", "3,045.00", "+0.35%", "NEUTRAL", "Safe-haven demand steady"],
            ["Gold AUD/oz", "4,267.00", "-0.47%", "NEUTRAL", "AUD weakness offsetting"],
            ["Brent Crude", "$98.79", "+7.41%", "SURGING", "Hormuz supply disruption fears"],
            ["Iron Ore", "$103.53", "+0.30%", "NEUTRAL", "Steady China demand"],
            ["Copper", "$12,888", "+0.01%", "NEUTRAL", "Industrial demand balanced"],
            ["AUD/USD", "0.7138", "-0.19%", "NEUTRAL", "USD safe-haven flows"],
            ["Bitcoin AUD", "$98,790", "+0.53%", "NEUTRAL", "Holding key support"],
            ["WDS", "$30.18", "-3.76%", "PULLBACK", "Post-dividend sell-off"],
            ["STO", "$7.37", "-3.50%", "PULLBACK", "Energy sector weakness"],
            ["NDQ ETF", "$51.41", "-2.17%", "PULLBACK", "Tracking US tech volatility"],
        ],
        "world_news": [
            {"headline": "Strait of Hormuz tensions escalate",
             "body": "Multiple vessels were reported struck near the Persian Gulf chokepoint overnight, triggering the biggest single-day oil price surge since 2023. The Strait of Hormuz carries roughly 20% of the world's daily petroleum consumption, making it the most critical chokepoint in global energy supply chains. The US Navy has dispatched two additional carrier groups to the region, while Iran has denied involvement but warned against 'provocative' Western naval buildups. Energy analysts are split on whether this represents a genuine escalation or posturing ahead of nuclear talks, but markets aren't waiting to find out \u2014 Brent crude jumped 7.4% and shipping insurers have already hiked transit premiums.",
             "why": "Direct impact on Brent Crude (+7.4%), flows through to WDS/STO and broader energy sector. If sustained, expect petrol prices at the bowser to jump within 2-3 weeks."},
            {"headline": "China posts double-digit trade growth",
             "body": "China's February trade data came in well above consensus, with exports surging 12.4% year-on-year against expectations of 7.8%. The beat was driven primarily by electronics and machinery shipments to Southeast Asia and the Middle East, suggesting Chinese manufacturers are successfully diversifying away from Western markets amid ongoing trade tensions. Imports also surprised to the upside at +5.2%, indicating domestic demand is firmer than the property sector doom narrative would suggest. The data sent the yuan higher and lifted iron ore futures in Singapore by 1.8%, with commodity traders interpreting the strong import figure as a signal that China's infrastructure spending is holding up.",
             "why": "Positive for iron ore and copper demand \u2014 supports the ASX materials sector and underpins the watchlist positions in resource-exposed names."},
            {"headline": "Fed signals patience on rate cuts",
             "body": "The latest Federal Reserve minutes revealed a committee firmly in 'wait and see' mode, with multiple officials explicitly stating they need 'several more months' of favourable inflation data before considering rate cuts. Core PCE remains sticky at 2.8%, well above the 2% target, and the labour market shows no signs of cracking with jobless claims holding near historic lows. Markets have now pushed the expected first cut to September, a significant shift from the six cuts priced in at the start of the year. The hawkish tone sent the US dollar index to a three-week high and pushed Treasury yields back above 4.3%, creating headwinds for rate-sensitive growth stocks.",
             "why": "Keeps USD strong, pressures AUD/USD. Cash continues to earn solid yields, so there's no penalty for patience on the watchlist."},
        ],
        "au_news": [
            {"headline": "RBA rate hike now consensus among Big 4 banks",
             "body": "In a significant shift in market expectations, CBA, NAB, and Westpac have all moved to forecast a 25bp rate hike at next week's RBA meeting, with ANZ expected to update its call on Monday. The pivot comes after last week's employment data showed 65,000 jobs added in February \u2014 more than triple consensus \u2014 and the trimmed mean CPI print that refused to budge from 3.5%. If the RBA does hike, it would be the first increase since November 2023 and would take the cash rate to 4.60%, putting further pressure on the roughly 800,000 households already in mortgage stress. Bond markets are pricing a 78% probability of a hike.",
             "why": "Rising rates make cash more attractive and put pressure on property prices \u2014 reinforces the case for staying patient with the watchlist."},
            {"headline": "Sydney auction clearance rate dips to 62%",
             "body": "Weekend clearance rates across Sydney fell to 62.1%, slipping below the 65% threshold that property analysts typically view as the dividing line between a rising and falling market. The weakness was concentrated in the outer western suburbs where median prices have already dropped 4-6% from their 2025 peaks, while the eastern suburbs and lower north shore held relatively firm. Total auction volumes were also down 15% compared to the same weekend last year, suggesting vendors are pulling listings rather than accepting lower prices. CoreLogic's Tim Lawless noted that if clearance rates remain below 65% for another 3-4 weeks, it could signal a broader correction is underway.",
             "why": "Housing market cooling could influence the RBA's decision and create future buying opportunities \u2014 worth watching closely."},
        ],
        "ai_tech": [
            {"headline": "Synopsys launches agentic engineering tools",
             "body": "Synopsys has unveiled what it calls 'the first agentic AI capabilities for system-level chip design', a suite of tools that can autonomously plan, execute and verify complex semiconductor design tasks that previously required teams of engineers working for months. The tools use a multi-agent architecture where specialised AI agents handle different aspects of the design process \u2014 from RTL synthesis to timing closure \u2014 and coordinate through a central orchestration layer. In internal benchmarks, the system completed a full SoC floorplan in 72 hours that would typically take a team of six engineers 8-12 weeks. The announcement sent Synopsys shares up 4.2% and sparked a broader rally in EDA (electronic design automation) stocks.",
             "why": "NDQ ETF exposure captures this trend. Also a Purpletag consulting angle \u2014 companies will need help integrating these tools into existing workflows."},
            {"headline": "Tencent unveils text-to-3D engine at GDC",
             "body": "At the Game Developers Conference in San Francisco, Tencent demonstrated a new AI-powered engine that generates production-ready 3D assets from text descriptions in under 5 minutes \u2014 a process that currently takes a skilled 3D artist anywhere from 2-8 hours per asset. The engine handles everything from mesh generation to UV mapping and texturing, producing assets that can be dropped directly into Unreal Engine or Unity without manual cleanup. Early access partners including Ubisoft and Electronic Arts reported 60-80% reductions in environment art production time during pilot programs. The tool is expected to launch commercially in Q3 2026 with a per-seat SaaS pricing model.",
             "why": "Massive productivity boost for game studios and a signal that AI content creation tools are reaching production quality. Worth monitoring for content creation automation opportunities at Purpletag."},
        ],
        "sports": [
            {"name": "AFL \u2014 Round 2", "matches": [
                {"teams": "Melbourne vs Sydney Swans", "score": "88-102", "time": "Final"},
                {"teams": "Collingwood vs Brisbane", "score": "76-91", "time": "Final"},
                {"teams": "Carlton vs Essendon", "score": "", "time": "Tonight 7:30pm AEST"},
                {"teams": "Hawthorn vs Richmond", "score": "95-64", "time": "Final"},
                {"teams": "Fremantle vs West Coast", "score": "", "time": "Tomorrow 5:40pm AEST"},
                {"teams": "GWS vs Port Adelaide", "score": "", "time": "Tomorrow 3:20pm AEST"},
            ], "standings": [
                {"pos": 1, "team": "Sydney Swans", "w": 2, "l": 0, "d": 0, "pts": 8, "pct_or_gd": "142.3%"},
                {"pos": 2, "team": "Brisbane", "w": 2, "l": 0, "d": 0, "pts": 8, "pct_or_gd": "131.7%"},
                {"pos": 3, "team": "Hawthorn", "w": 2, "l": 0, "d": 0, "pts": 8, "pct_or_gd": "126.1%"},
                {"pos": 4, "team": "Geelong", "w": 1, "l": 0, "d": 1, "pts": 6, "pct_or_gd": "118.5%"},
                {"pos": 5, "team": "Western Bulldogs", "w": 1, "l": 0, "d": 1, "pts": 6, "pct_or_gd": "112.0%"},
                {"pos": 6, "team": "Port Adelaide", "w": 1, "l": 0, "d": 0, "pts": 4, "pct_or_gd": "115.4%"},
                {"pos": 7, "team": "Fremantle", "w": 1, "l": 0, "d": 0, "pts": 4, "pct_or_gd": "110.8%"},
                {"pos": 8, "team": "Carlton", "w": 1, "l": 1, "d": 0, "pts": 4, "pct_or_gd": "98.5%"},
                {"pos": 9, "team": "Collingwood", "w": 1, "l": 1, "d": 0, "pts": 4, "pct_or_gd": "96.2%"},
                {"pos": 10, "team": "GWS Giants", "w": 1, "l": 1, "d": 0, "pts": 4, "pct_or_gd": "93.7%"},
                {"pos": 11, "team": "St Kilda", "w": 1, "l": 1, "d": 0, "pts": 4, "pct_or_gd": "91.3%"},
                {"pos": 12, "team": "Gold Coast", "w": 1, "l": 1, "d": 0, "pts": 4, "pct_or_gd": "88.4%"},
                {"pos": 13, "team": "Adelaide", "w": 0, "l": 1, "d": 1, "pts": 2, "pct_or_gd": "95.1%"},
                {"pos": 14, "team": "Melbourne", "w": 0, "l": 1, "d": 1, "pts": 2, "pct_or_gd": "90.6%"},
                {"pos": 15, "team": "Essendon", "w": 0, "l": 1, "d": 0, "pts": 0, "pct_or_gd": "85.2%"},
                {"pos": 16, "team": "North Melbourne", "w": 0, "l": 2, "d": 0, "pts": 0, "pct_or_gd": "72.8%"},
                {"pos": 17, "team": "West Coast", "w": 0, "l": 2, "d": 0, "pts": 0, "pct_or_gd": "68.4%"},
                {"pos": 18, "team": "Richmond", "w": 0, "l": 2, "d": 0, "pts": 0, "pct_or_gd": "62.1%"},
            ]},
            {"name": "NRL \u2014 Round 4", "matches": [
                {"teams": "Penrith Panthers vs Cronulla Sharks", "score": "22-18", "time": "Final"},
                {"teams": "Melbourne Storm vs Canterbury", "score": "34-12", "time": "Final"},
                {"teams": "Sydney Roosters vs Brisbane Broncos", "score": "", "time": "Tonight 7:55pm AEST"},
                {"teams": "Parramatta vs South Sydney", "score": "", "time": "Tomorrow 4:05pm AEST"},
                {"teams": "Manly vs Canberra", "score": "26-20", "time": "Final"},
                {"teams": "Newcastle vs Gold Coast", "score": "", "time": "Tomorrow 2:00pm AEST"},
            ], "standings": [
                {"pos": 1, "team": "Penrith Panthers", "w": 4, "l": 0, "d": 0, "pts": 8, "pct_or_gd": "+82"},
                {"pos": 2, "team": "Melbourne Storm", "w": 3, "l": 1, "d": 0, "pts": 6, "pct_or_gd": "+64"},
                {"pos": 3, "team": "Cronulla Sharks", "w": 3, "l": 1, "d": 0, "pts": 6, "pct_or_gd": "+38"},
                {"pos": 4, "team": "Sydney Roosters", "w": 3, "l": 0, "d": 0, "pts": 6, "pct_or_gd": "+52"},
                {"pos": 5, "team": "Manly Sea Eagles", "w": 3, "l": 1, "d": 0, "pts": 6, "pct_or_gd": "+30"},
                {"pos": 6, "team": "Canterbury", "w": 2, "l": 1, "d": 0, "pts": 4, "pct_or_gd": "+18"},
                {"pos": 7, "team": "North Queensland", "w": 2, "l": 2, "d": 0, "pts": 4, "pct_or_gd": "+6"},
                {"pos": 8, "team": "St George Illa.", "w": 2, "l": 2, "d": 0, "pts": 4, "pct_or_gd": "-4"},
                {"pos": 9, "team": "Newcastle", "w": 2, "l": 1, "d": 0, "pts": 4, "pct_or_gd": "+12"},
                {"pos": 10, "team": "Dolphins", "w": 1, "l": 2, "d": 0, "pts": 2, "pct_or_gd": "-14"},
                {"pos": 11, "team": "Brisbane Broncos", "w": 1, "l": 3, "d": 0, "pts": 2, "pct_or_gd": "-28"},
                {"pos": 12, "team": "Canberra Raiders", "w": 1, "l": 3, "d": 0, "pts": 2, "pct_or_gd": "-36"},
                {"pos": 13, "team": "Wests Tigers", "w": 1, "l": 3, "d": 0, "pts": 2, "pct_or_gd": "-42"},
                {"pos": 14, "team": "Gold Coast Titans", "w": 1, "l": 2, "d": 0, "pts": 2, "pct_or_gd": "-20"},
                {"pos": 15, "team": "South Sydney", "w": 0, "l": 3, "d": 0, "pts": 0, "pct_or_gd": "-58"},
                {"pos": 16, "team": "Parramatta Eels", "w": 0, "l": 4, "d": 0, "pts": 0, "pct_or_gd": "-72"},
                {"pos": 17, "team": "New Zealand", "w": 0, "l": 3, "d": 0, "pts": 0, "pct_or_gd": "-48"},
            ]},
            {"name": "Premier League \u2014 MW29", "matches": [
                {"teams": "Liverpool vs Man Utd", "score": "3-0", "time": "Final"},
                {"teams": "Arsenal vs Brighton", "score": "2-0", "time": "Final"},
                {"teams": "Chelsea vs Wolves", "score": "4-1", "time": "Final"},
                {"teams": "Man City vs Tottenham", "score": "", "time": "Tomorrow 3:00am AEST"},
                {"teams": "Aston Villa vs Newcastle", "score": "1-1", "time": "Final"},
            ], "standings": [
                {"pos": 1, "team": "Liverpool", "w": 22, "l": 3, "d": 4, "pts": 70, "pct_or_gd": "+42"},
                {"pos": 2, "team": "Arsenal", "w": 20, "l": 4, "d": 5, "pts": 65, "pct_or_gd": "+38"},
                {"pos": 3, "team": "Chelsea", "w": 17, "l": 5, "d": 7, "pts": 58, "pct_or_gd": "+24"},
                {"pos": 4, "team": "Man City", "w": 16, "l": 7, "d": 5, "pts": 53, "pct_or_gd": "+20"},
                {"pos": 5, "team": "Nottm Forest", "w": 16, "l": 7, "d": 6, "pts": 54, "pct_or_gd": "+14"},
                {"pos": 6, "team": "Aston Villa", "w": 14, "l": 8, "d": 7, "pts": 49, "pct_or_gd": "+10"},
                {"pos": 7, "team": "Newcastle", "w": 13, "l": 8, "d": 8, "pts": 47, "pct_or_gd": "+12"},
                {"pos": 8, "team": "Brighton", "w": 12, "l": 9, "d": 8, "pts": 44, "pct_or_gd": "+6"},
                {"pos": 9, "team": "Bournemouth", "w": 12, "l": 10, "d": 7, "pts": 43, "pct_or_gd": "+4"},
                {"pos": 10, "team": "Man Utd", "w": 10, "l": 10, "d": 9, "pts": 39, "pct_or_gd": "-2"},
                {"pos": 11, "team": "Fulham", "w": 10, "l": 11, "d": 8, "pts": 38, "pct_or_gd": "-4"},
                {"pos": 12, "team": "Tottenham", "w": 10, "l": 10, "d": 8, "pts": 38, "pct_or_gd": "-1"},
                {"pos": 13, "team": "Brentford", "w": 10, "l": 12, "d": 7, "pts": 37, "pct_or_gd": "-6"},
                {"pos": 14, "team": "West Ham", "w": 9, "l": 12, "d": 8, "pts": 35, "pct_or_gd": "-10"},
                {"pos": 15, "team": "Crystal Palace", "w": 7, "l": 13, "d": 9, "pts": 30, "pct_or_gd": "-14"},
                {"pos": 16, "team": "Everton", "w": 7, "l": 14, "d": 8, "pts": 29, "pct_or_gd": "-16"},
                {"pos": 17, "team": "Wolves", "w": 7, "l": 16, "d": 6, "pts": 27, "pct_or_gd": "-24"},
                {"pos": 18, "team": "Leicester", "w": 5, "l": 17, "d": 7, "pts": 22, "pct_or_gd": "-30"},
                {"pos": 19, "team": "Ipswich", "w": 4, "l": 19, "d": 6, "pts": 18, "pct_or_gd": "-36"},
                {"pos": 20, "team": "Southampton", "w": 2, "l": 21, "d": 6, "pts": 12, "pct_or_gd": "-48"},
            ]},
        ],
        "events": [
            {"name": "Sydney Royal Easter Show", "details": "Mar 20 \u2013 Apr 2 \u2022 Sydney Olympic Park \u2022 From $35", "pub": "Olympic Park Hotel \u2014 $8 schooners during show"},
            {"name": "Vivid Preview Night", "details": "Tonight 6:30pm \u2022 Circular Quay \u2022 Free", "pub": "Opera Bar \u2014 harbour views with the light show"},
            {"name": "NRL Fan Day", "details": "Tomorrow 10am-2pm \u2022 Moore Park \u2022 Free", "pub": "The Bat & Ball \u2014 classic pub across the road"},
            {"name": "Newtown Festival Street Market", "details": "Sunday 10am-4pm \u2022 King Street, Newtown \u2022 Free", "pub": "The Courthouse Hotel \u2014 great beer garden"},
        ],
        "things_worth_knowing": "<p>The Strait of Hormuz handles ~20% of the world's petroleum consumption daily. Current tensions are the highest since the 2019 tanker attacks. If sustained, expect petrol prices at the bowser to jump within 2-3 weeks.</p><p>The AFL season opener is tonight \u2014 perfect excuse to hit the pub with mates. Swans are $1.55 favourites against Carlton.</p>",
        "sources": "Sources: Google Finance, Trading Economics, Reuters, ABC News, AFL.com.au, NRL.com, PremierLeague.com, TimeOut Sydney, Open-Meteo"
    }


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--sample":
        data = get_sample_data()
    elif len(sys.argv) > 1:
        with open(sys.argv[1], "r") as f:
            data = json.load(f)
    else:
        data = json.load(sys.stdin)

    html, date_iso = generate_html(data)

    with open(OUTPUT_PATH, "w") as f:
        f.write(html)
    print(f"Generated: {OUTPUT_PATH}")

    # Archive a copy
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    archive_path = os.path.join(ARCHIVE_DIR, f"{date_iso}.html")
    shutil.copy2(OUTPUT_PATH, archive_path)
    print(f"Archived:  {archive_path}")


if __name__ == "__main__":
    main()
