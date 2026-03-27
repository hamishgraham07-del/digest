#!/usr/bin/env python3
"""Generate mobile-first PWA digest HTML from JSON."""
import json, sys, os
from datetime import datetime
from pathlib import Path

def get_weather_emoji(code):
    code = int(code)
    if code in [0, 1]: return "☀️"
    if code in [2, 3]: return "⛅"
    if code in [45, 48]: return "🌫️"
    if code in [51, 53, 55, 61, 63, 65, 67]: return "🌧️"
    if code in [71, 73, 75, 77, 80, 81, 82]: return "❄️"
    if code in [95, 96, 99]: return "⛈️"
    return "🌤️"

def esc(text):
    if not text: return ""
    s = str(text)
    s = s.replace("&", "&amp;")
    s = s.replace("<", "&lt;")
    s = s.replace(">", "&gt;")
    s = s.replace('"', "&quot;")
    s = s.replace("'", "&#39;")
    return s

def gen_html(data):
    d = data
    w = d.get("weather", {})
    h = get_weather_emoji(w.get("weathercode", 1))
    
    a_h = ""
    for a in d.get("assets", []):
        if len(a) >= 5:
            change_val = float(str(a[2]).replace('%','').replace('+','').strip()) if a[2] else 0
            change_color = "#10b981" if change_val >= 0 else "#ef4444"
            change_sign = "+" if change_val >= 0 else ""
            signal_lower = str(a[3]).lower()
            color = "#10b981" if "bullish" in signal_lower else "#ef4444" if "pullback" in signal_lower else "#6b7280"
            a_h += '<tr><td style="padding:8px 12px;border-bottom:1px solid #1e293b">' + esc(a[0]) + '</td><td style="padding:8px 12px;border-bottom:1px solid #1e293b;text-align:right">' + esc(a[1]) + '</td><td style="padding:8px 12px;border-bottom:1px solid #1e293b;text-align:right;color:' + change_color + '">' + esc(a[2]) + '</td><td style="padding:8px 12px;border-bottom:1px solid #1e293b;text-align:center"><span style="display:inline-block;padding:4px 8px;background-color:' + color + ';color:white;border-radius:4px;font-size:11px;font-weight:600">' + esc(str(a[3])[:3].upper()) + '</span></td></tr>'
    
    def n_h(l):
        h = ""
        for i in l:
            h += '<article style="margin-bottom:24px;padding-bottom:20px;border-bottom:1px solid #1e293b"><h3 style="margin:0 0 12px 0;font-size:16px;font-weight:600;color:white">' + esc(i.get("headline", "")) + '</h3><p style="margin:0 0 12px 0;font-size:14px;color:#cbd5e1">' + esc(i.get("body", "")) + '</p><div style="padding:12px;background-color:#1e293b;border-left:3px solid #f59e0b;border-radius:4px"><p style="margin:0;font-size:13px;color:#e2e8f0"><strong style="color:#f59e0b">Why it matters:</strong> ' + esc(i.get("why", "")) + '</p></div></article>'
        return h
    
    html_body = '<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#0a0a0f"><title>Daily Digest</title><link rel="manifest" href="manifest.json"><meta name="apple-mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-status-bar-style" content="black-translucent"><style>*{margin:0;padding:0;box-sizing:border-box}html{scroll-behavior:smooth}body{font-family:-apple-system,system-ui,-webkit-system-font,BlinkMacSystemFont,"Segoe UI",sans-serif;background-color:#0a0a0f;color:#e2e8f0;line-height:1.6;overflow-x:hidden}header{position:sticky;top:0;z-index:50;background:linear-gradient(180deg,rgba(10,10,15,0.98),rgba(10,10,15,0.8));backdrop-filter:blur(10px);border-bottom:1px solid #1e293b;padding:max(12px,env(safe-area-inset-top)) 16px 12px}header>div:first-child{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}.date-time{font-size:18px;font-weight:700;color:#f59e0b}.time{font-size:13px;color:#64748b}.weather-widget{display:flex;align-items:center;gap:8px;font-size:13px}.weather-emoji{font-size:28px}.weather-temp{display:flex;flex-direction:column;gap:2px}.weather-desc{color:#cbd5e1;font-size:12px}.weather-stats{display:flex;gap:16px;margin-top:8px;font-size:12px;color:#cbd5e1}main{padding:0 16px 120px;max-width:800px;margin:0 auto}section{margin-top:40px;padding-top:20px;scroll-margin-top:80px}h2{font-size:28px;font-weight:700;color:#f59e0b;margin-bottom:20px;padding-bottom:12px;border-bottom:2px solid #f59e0b}h3{font-size:18px;font-weight:600;color:white}p{margin-bottom:12px;color:#cbd5e1;line-height:1.7}.content-block{background-color:#0f1419;padding:16px;border-radius:8px;border-left:3px solid #f59e0b}.assets-table{width:100%;border-collapse:collapse;margin-top:16px;font-size:13px;background-color:#0f1419;border-radius:8px;overflow:hidden}.assets-table thead{background-color:#1e293b}.assets-table th{padding:12px;text-align:left;font-weight:600;color:#f59e0b;border-bottom:2px solid #334155}.assets-table td{padding:10px 12px;border-bottom:1px solid #1e293b}.pitch-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:16px}.pitch-item{background-color:#1e293b;padding:12px;border-radius:6px;border-left:2px solid #f59e0b}.pitch-label{font-size:11px;color:#64748b;font-weight:600;text-transform:uppercase;margin-bottom:4px}.pitch-value{font-size:14px;font-weight:600;color:white}.calendar-widget{background-color:#0f1419;border-radius:8px;overflow:hidden;margin-top:16px}.sources-section{background-color:#0f1419;padding:16px;border-radius:8px;margin-top:16px;font-size:13px;line-height:1.8}footer{text-align:center;padding:20px 16px;color:#64748b;font-size:12px;margin-top:40px}@media(max-width:480px){main{padding:0 12px 120px}h2{font-size:24px}}.installable{position:fixed;bottom:80px;left:50%;transform:translateX(-50%);background-color:#f59e0b;color:#0a0a0f;padding:12px 24px;border-radius:24px;font-weight:600;cursor:pointer;display:none;z-index:35;border:none;box-shadow:0 4px 12px rgba(245,158,11,0.3)}@keyframes slideUp{from{transform:translateX(-50%) translateY(20px);opacity:0}to{transform:translateX(-50%) translateY(0);opacity:1}}</style></head><body><header><div><div><div class="date-time">' + esc(d.get("date_str", "")) + '</div><div class="time">' + esc(d.get("time_str", "")) + '</div></div><div class="weather-widget"><span class="weather-emoji">' + h + '</span><div class="weather-temp"><div><span style="color:#f59e0b;font-weight:600">' + str(w.get("max_temp", "--")) + '°</span><span style="color:#64748b">/ ' + str(w.get("min_temp", "--")) + '°</span></div><div class="weather-desc">' + esc(w.get("description", "Clear")) + '</div></div></div></div><div class="weather-stats"><span>💧 ' + str(w.get("rain_prob", 0)) + '%</span><span>☀️ UV ' + str(w.get("uv_index", "-")) + '</span></div></header><main>'
    
    if d.get("calendar"):
        html_body += '<section id="calendar" style="margin-top:24px"><h2 style="font-size:20px;margin-bottom:16px">📅 Today</h2><div class="calendar-widget">'
        for e in d.get("calendar", []):
            html_body += '<div style="padding:12px;border-bottom:1px solid #1e293b;display:flex;gap:12px"><div style="color:#f59e0b;font-weight:600;font-size:13px;min-width:60px">' + esc(e.get("time", "")) + '</div><div style="flex:1"><div style="font-weight:600;color:white;font-size:14px">' + esc(e.get("title", "")) + '</div>'
            if e.get("location"):
                html_body += '<div style="font-size:12px;color:#cbd5e1">' + esc(e.get("location", "")) + '</div>'
            html_body += '<div style="font-size:11px;color:#64748b;margin-top:2px">' + esc(e.get("calendar", "")) + '</div></div></div>'
        html_body += '</div></section>'
    
    html_body += '<section id="big-picture"><h2>🎯 Big Picture</h2><div class="content-block" style="border:none;background:transparent;padding:0">' + d.get("big_picture", "") + '</div></section><section id="strategy"><h2>📈 Market Strategy</h2><div class="content-block" style="border:none;background:transparent;padding:0">' + d.get("strategy", "") + '</div></section><section id="assets"><h2>💰 Market Watch (16 Assets)</h2><div style="overflow-x:auto"><table class="assets-table"><thead><tr><th>Asset</th><th style="text-align:right">Price</th><th style="text-align:right">Change</th><th style="text-align:center">Signal</th></tr></thead><tbody>' + a_h + '</tbody></table></div></section><section id="world-news"><h2>🌍 World News</h2>' + n_h(d.get("world_news", [])) + '</section><section id="au-news"><h2>🇦🇺 Australia News</h2>' + n_h(d.get("au_news", [])) + '</section><section id="ai-tech"><h2>🤖 AI & Tech</h2>' + n_h(d.get("ai_tech", [])) + '</section><section id="pitch"><h2>💡 Startup Pitch</h2>'
    
    pitch = d.get("pitch", {})
    if pitch:
        html_body += '<div class="content-block" style="border:none;background:transparent;padding:0;margin-bottom:16px"><p style="font-size:15px;color:#e2e8f0;line-height:1.7">' + esc(pitch.get("intro", "")) + '</p></div><div class="pitch-grid"><div class="pitch-item"><div class="pitch-label">Sector</div><div class="pitch-value">' + esc(pitch.get("sector", "")) + '</div></div><div class="pitch-item"><div class="pitch-label">Why Now</div><div class="pitch-value">' + esc(pitch.get("why_now", "")) + '</div></div><div class="pitch-item"><div class="pitch-label">Build</div><div class="pitch-value">' + esc(pitch.get("what_youd_build", "")) + '</div></div><div class="pitch-item"><div class="pitch-label">Revenue</div><div class="pitch-value">' + esc(pitch.get("revenue_model", "")) + '</div></div><div class="pitch-item"><div class="pitch-label">Risk</div><div class="pitch-value">' + esc(pitch.get("risk_level", "")) + '</div></div><div class="pitch-item"><div class="pitch-label">Capital</div><div class="pitch-value">' + esc(pitch.get("capital_needed", "")) + '</div></div></div><div style="margin-top:16px;padding:12px;background-color:#1e293b;border-radius:6px;border-left:3px solid #f59e0b"><div style="font-size:12px;color:#64748b;font-weight:600;margin-bottom:4px">TIME TO REVENUE</div><div style="font-size:15px;font-weight:600;color:#f59e0b">' + esc(pitch.get("time_to_revenue", "")) + '</div></div>'
    
    html_body += '</section>'
    
    if d.get("sports"):
        html_body += '<section id="sports"><h2>🏆 Sports</h2>'
        for sport in d.get("sports", []):
            html_body += '<div><h3 style="margin:20px 0 16px 0;font-size:18px;font-weight:700;color:#f59e0b">' + esc(sport.get("name", "")) + '</h3>'
            for match in sport.get("matches", []):
                html_body += '<div style="padding:10px;background-color:#1e293b;border-radius:4px;margin-bottom:8px;font-size:13px"><div style="color:#cbd5e1">' + esc(match.get("teams", "")) + '</div><div style="color:#f59e0b;font-weight:600">' + esc(match.get("score", "")) + '</div><div style="color:#64748b;font-size:12px">' + esc(match.get("time", "")) + '</div></div>'
            if sport.get("standings"):
                html_body += '<table style="width:100%;font-size:12px;border-collapse:collapse">'
                for idx, row in enumerate(sport.get("standings", [])):
                    bg = "#0f1419" if idx % 2 == 0 else "#1e293b"
                    html_body += '<tr style="background-color:' + bg + '"><td style="padding:8px;border-right:1px solid #334155">' + esc(str(row.get("pos", ""))) + '</td><td style="padding:8px;border-right:1px solid #334155">' + esc(str(row.get("team", ""))) + '</td><td style="padding:8px;border-right:1px solid #334155;text-align:center">' + esc(str(row.get("w", ""))) + '</td><td style="padding:8px;border-right:1px solid #334155;text-align:center">' + esc(str(row.get("l", ""))) + '</td><td style="padding:8px;border-right:1px solid #334155;text-align:center">' + esc(str(row.get("d", ""))) + '</td><td style="padding:8px;border-right:1px solid #334155;text-align:center">' + esc(str(row.get("pts", ""))) + '</td><td style="padding:8px;text-align:center">' + esc(str(row.get("pct_or_gd", ""))) + '</td></tr>'
                html_body += '</table>'
            html_body += '</div>'
        html_body += '</section>'
    
    if d.get("events"):
        html_body += '<section id="events"><h2>📢 Events</h2>'
        for event in d.get("events", []):
            html_body += '<div style="padding:16px;background-color:#1e293b;border-radius:6px;margin-bottom:12px;border-left:3px solid #f59e0b"><h4 style="margin:0 0 6px 0;font-size:15px;font-weight:600;color:white">' + esc(event.get("name", "")) + '</h4><p style="margin:0 0 6px 0;font-size:13px;color:#cbd5e1">' + esc(event.get("details", "")) + '</p><p style="margin:0;font-size:12px;color:#64748b">' + esc(event.get("pub", "")) + '</p></div>'
        html_body += '</section>'
    
    html_body += '<section id="worth-knowing"><h2>💭 Things Worth Knowing</h2><div class="content-block" style="border:none;background:transparent;padding:0">' + d.get("things_worth_knowing", "") + '</div></section><section id="sources"><h2>📚 Sources</h2><div class="sources-section">' + d.get("sources", "") + '</div></section></main><div id="section-nav" style="position:fixed;bottom:20px;left:50%;transform:translateX(-50%);display:flex;gap:6px;background-color:rgba(10,10,15,0.95);padding:8px 12px;border-radius:20px;z-index:40;backdrop-filter:blur(10px)"><button onclick="scrollToSection(\'big-picture\')" class="nav-dot" data-section="big-picture" style="width:8px;height:8px;border-radius:50%;background-color:#f59e0b;border:none;cursor:pointer"></button><button onclick="scrollToSection(\'strategy\')" class="nav-dot" data-section="strategy" style="width:8px;height:8px;border-radius:50%;background-color:#64748b;border:none;cursor:pointer"></button><button onclick="scrollToSection(\'assets\')" class="nav-dot" data-section="assets" style="width:8px;height:8px;border-radius:50%;background-color:#64748b;border:none;cursor:pointer"></button><button onclick="scrollToSection(\'world-news\')" class="nav-dot" data-section="world-news" style="width:8px;height:8px;border-radius:50%;background-color:#64748b;border:none;cursor:pointer"></button><button onclick="scrollToSection(\'au-news\')" class="nav-dot" data-section="au-news" style="width:8px;height:8px;border-radius:50%;background-color:#64748b;border:none;cursor:pointer"></button><button onclick="scrollToSection(\'ai-tech\')" class="nav-dot" data-section="ai-tech" style="width:8px;height:8px;border-radius:50%;background-color:#64748b;border:none;cursor:pointer"></button><button onclick="scrollToSection(\'pitch\')" class="nav-dot" data-section="pitch" style="width:8px;height:8px;border-radius:50%;background-color:#64748b;border:none;cursor:pointer"></button><button onclick="scrollToSection(\'sports\')" class="nav-dot" data-section="sports" style="width:8px;height:8px;border-radius:50%;background-color:#64748b;border:none;cursor:pointer"></button><button onclick="scrollToSection(\'events\')" class="nav-dot" data-section="events" style="width:8px;height:8px;border-radius:50%;background-color:#64748b;border:none;cursor:pointer"></button><button onclick="scrollToSection(\'worth-knowing\')" class="nav-dot" data-section="worth-knowing" style="width:8px;height:8px;border-radius:50%;background-color:#64748b;border:none;cursor:pointer"></button></div><footer><p>Generated on ' + esc(d.get("date_iso", "")) + '</p></footer><button id="install-btn" class="installable">Install App</button><script>if("serviceWorker"in navigator)navigator.serviceWorker.register("sw.js");let dP;window.addEventListener("beforeinstallprompt",(e)=>{e.preventDefault();dP=e;document.getElementById("install-btn").classList.add("show")});document.getElementById("install-btn").addEventListener("click",async()=>{if(dP){dP.prompt();const outcome=await dP.userChoice;dP=null;document.getElementById("install-btn").classList.remove("show")}});function scrollToSection(id){const s=document.getElementById(id);if(s){s.scrollIntoView({behavior:"smooth"})}}const o=new IntersectionObserver((e)=>{e.forEach(x=>{if(x.isIntersecting){document.querySelectorAll(".nav-dot").forEach(d=>{d.style.backgroundColor=d.dataset.section===x.target.id?"#f59e0b":"#64748b"})}}})},threshold:0.5});document.querySelectorAll("section").forEach(s=>{if(s.id)o.observe(s)});</script></body></html>'
    
    return html_body

def main():
    if len(sys.argv) < 2:
        print("Usage: python generate_digest_html.py <json_file_path>")
        sys.exit(1)
    
    json_path = sys.argv[1]
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: File '{json_path}' not found")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON: {e}")
        sys.exit(1)
    
    html = gen_html(data)
    script_dir = Path(os.environ.get("DIGEST_OUTPUT_DIR", str(Path(__file__).resolve().parent)))
    
    # Write index.html
    index_path = script_dir / "index.html"
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"Generated: {index_path}")
    
    # Archive version
    archive_dir = script_dir / "archive"
    archive_dir.mkdir(exist_ok=True)
    date_iso = data.get("date_iso", "unknown")
    archive_path = archive_dir / f"{date_iso}.html"
    with open(archive_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"Archived: {archive_path}")
    
    # Generate manifest
    manifest = {"name":"Daily Digest","short_name":"Digest","description":"Beautiful daily digest","start_url":"./index.html","scope":"./","display":"standalone","orientation":"portrait-primary","background_color":"#0a0a0f","theme_color":"#f59e0b","icons":[{"src":"data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 192 192'><rect fill='%230a0a0f' width='192' height='192'/><circle cx='96' cy='96' r='80' fill='%23f59e0b'/><text x='96' y='110' font-size='60' fill='%230a0a0f' text-anchor='middle' font-weight='bold'>D</text></svg>","sizes":"192x192","type":"image/svg+xml","purpose":"any"},{"src":"data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 192 192'><rect fill='%230a0a0f' width='192' height='192'/><circle cx='96' cy='96' r='80' fill='%23f59e0b'/><text x='96' y='110' font-size='60' fill='%230a0a0f' text-anchor='middle' font-weight='bold'>D</text></svg>","sizes":"192x192","type":"image/svg+xml","purpose":"maskable"}]}
    manifest_path = script_dir / "manifest.json"
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)
    print(f"Generated: {manifest_path}")
    
    # Generate service worker
    sw_code = "const CACHE_NAME='digest-v1';const assets=['index.html','manifest.json'];self.addEventListener('install',(event)=>{event.waitUntil(caches.open(CACHE_NAME).then((cache)=>{return cache.addAll(assets).catch(()=>console.log('Cache error'))}));self.skipWaiting()});self.addEventListener('activate',(event)=>{event.waitUntil(caches.keys().then((cacheNames)=>{return Promise.all(cacheNames.filter((name)=>name!==CACHE_NAME).map((name)=>caches.delete(name)))}));self.clients.claim()});self.addEventListener('fetch',(event)=>{if(event.request.method!=='GET')return;event.respondWith(caches.match(event.request).then((response)=>{return response||fetch(event.request).then((res)=>{return caches.open(CACHE_NAME).then((cache)=>{cache.put(event.request,res.clone());return res})}).catch(()=>caches.match('index.html'))}))});"
    sw_path = script_dir / "sw.js"
    with open(sw_path, 'w', encoding='utf-8') as f:
        f.write(sw_code)
    print(f"Generated: {sw_path}")
    
    print("\nSuccess! PWA digest generated.")
    print(f"Open {index_path} in a browser to view the digest.")

if __name__ == "__main__":
    main()
