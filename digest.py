import json
import os
import re
import requests
import time
from datetime import datetime, timedelta

# ─── CONFIG ───────────────────────────────────────────────────────────────────
SENDGRID_API_KEY = os.environ["SENDGRID_API_KEY"]
FROM_EMAIL       = os.environ["FROM_EMAIL"]
TO_EMAIL         = "lucasfearn1@gmail.com"
# ──────────────────────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Only show events at these major NYC venues
SKIP_VENUES = [
    "lucinda", "birdland", "blue note", "carnegie", "lincoln center",
    "9 bob note", "cutting room", "rough trade", "nebula", "marquee",
    "church", "synagogue", "comedy", "stand up", "open mic", "rehearsal"
]

NYC_CITIES = ["New York", "Brooklyn", "Manhattan", "Queens", "Bronx", "New York City"]

def get_week_range():
    today = datetime.now()
    days_until_monday = (7 - today.weekday()) % 7 or 7
    next_monday = today + timedelta(days=days_until_monday)
    next_sunday = next_monday + timedelta(days=6)
    return next_monday, next_sunday

def get_borough(venue_name, city):
    vl = (venue_name or "").lower()
    cl = (city or "").lower()
    brooklyn_kw = ["brooklyn", "bossa nova", "h0l0", "elsewhere", "williamsburg",
                   "market hotel", "tv eye", "good room", "nowadays", "house of yes",
                   "avant gardner", "mirage", "warsaw", "kings theatre", "brooklyn bowl",
                   "sultan room", "under the k", "pier 4", "navy yard", "storehouse",
                   "brooklyn steel", "baby's all right", "rough trade"]
    bronx_kw = ["bronx", "yankee"]
    if any(k in vl for k in brooklyn_kw) or cl == "brooklyn":
        return "Brooklyn"
    if any(k in vl for k in bronx_kw) or cl == "bronx":
        return "Bronx"
    return "Manhattan"

def should_skip(venue_name):
    vl = (venue_name or "").lower()
    return any(s in vl for s in SKIP_VENUES)

def clean_name(name):
    """Remove date/time artifacts from event names."""
    name = re.sub(r'\w+ \w+, \w+ \d+, \d{4} @ \d+:\d+:\d+,?\s*', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name

def scrape_concerts50(start, end):
    """Scrape concerts50.com which has real structured data for NYC events."""
    all_events = []
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")

    pages = [
        "https://concerts50.com/upcoming-concerts-in-new-york",
        "https://concerts50.com/upcoming-concerts-in-new-york/brooklyn",
        "https://concerts50.com/upcoming-concerts-in-new-york/manhattan",
    ]

    for page_url in pages:
        try:
            resp = requests.get(page_url, headers=HEADERS, timeout=20)
            content = resp.text
            ld_blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', content, re.DOTALL)

            for b in ld_blocks:
                try:
                    d = json.loads(b.strip())
                    items = d if isinstance(d, list) else [d]
                    for item in items:
                        if "MusicEvent" not in str(item.get("@type", "")):
                            continue

                        date = item.get("startDate", "")[:10]
                        if not (start_str <= date <= end_str):
                            continue

                        name = clean_name(item.get("name", ""))
                        location = item.get("location") or {}
                        venue = location.get("name", "")
                        address = location.get("address") or {}
                        city = address.get("addressLocality", "")

                        if city and city not in NYC_CITIES:
                            continue
                        if should_skip(venue):
                            continue

                        offers = item.get("offers") or {}
                        price_raw = offers.get("price", "") if isinstance(offers, dict) else ""
                        url = offers.get("url", item.get("url", "")) if isinstance(offers, dict) else item.get("url", "")

                        try:
                            dt = datetime.fromisoformat(item.get("startDate", ""))
                            date_fmt = dt.strftime("%a %b %d")
                            time_fmt = dt.strftime("%-I:%M %p")
                            date_sort = dt.strftime("%Y-%m-%d")
                        except:
                            date_fmt = date
                            time_fmt = ""
                            date_sort = date

                        price = f"From ${int(float(price_raw))}" if price_raw else "Check site"
                        borough = get_borough(venue, city)

                        all_events.append({
                            "name": name,
                            "venue": venue,
                            "borough": borough,
                            "date": date_fmt,
                            "date_sort": date_sort,
                            "time": time_fmt,
                            "price": price,
                            "url": url,
                            "source": "Ticketmaster"
                        })
                except:
                    pass
            time.sleep(0.5)
        except Exception as ex:
            print(f"   Error scraping {page_url}: {ex}")

    # Deduplicate
    seen = set()
    unique = []
    for e in all_events:
        key = (e["name"].lower().strip()[:40], e["date_sort"])
        if key not in seen and e["name"]:
            seen.add(key)
            unique.append(e)

    # Sort by date then time
    unique.sort(key=lambda e: (e["date_sort"], e["time"]))
    print(f"   concerts50: {len(unique)} unique NYC events")
    return unique[:30]

def is_priority(name):
    keywords = ["dj", "edm", "electronic", "house", "techno", "rap", "hip-hop",
                "hip hop", "r&b", "reggaeton", "latin", "afrobeat", "dancehall",
                "bass", "rave", "club", "trap", "drill", "bounce"]
    return any(k in (name or "").lower() for k in keywords)

def build_html_email(events, start_str, end_str):
    brooklyn = [e for e in events if e.get("borough") == "Brooklyn"]
    manhattan = [e for e in events if e.get("borough") == "Manhattan"]
    bronx = [e for e in events if e.get("borough") == "Bronx"]

    def card(e):
        name = e.get("name", "")
        venue = e.get("venue", "")
        date = e.get("date", "")
        time_s = e.get("time", "")
        price = e.get("price", "Check site")
        url = e.get("url", "#")
        source = e.get("source", "")
        star = "⭐" if is_priority(name) else "🎵"
        date_time = f"{date}{' · ' + time_s if time_s else ''}"

        return f"""
        <div style="background:#111;border:1px solid #1e1e1e;border-radius:10px;padding:16px 18px;margin-bottom:10px;">
          <p style="margin:0 0 6px 0;font-size:15px;font-weight:700;color:#fff;line-height:1.3;">{star} {name}</p>
          <p style="margin:0 0 2px 0;color:#555;font-size:12px;">📍 {venue}</p>
          <p style="margin:0 0 8px 0;color:#555;font-size:12px;">📅 {date_time}</p>
          <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;">
            <span style="color:#f0a500;font-size:13px;font-weight:700;">💰 {price}</span>
            <a href="{url}" style="background:#fff;color:#000;font-size:11px;font-weight:800;padding:7px 16px;border-radius:20px;text-decoration:none;letter-spacing:0.5px;">GET TICKETS ↗</a>
          </div>
        </div>"""

    def section(title, color, evts):
        if not evts:
            return ""
        cards = "".join([card(e) for e in evts])
        return f"""
        <div style="margin-bottom:32px;">
          <div style="margin-bottom:14px;">
            <span style="background:{color};color:#fff;font-size:10px;font-weight:800;padding:5px 12px;border-radius:4px;letter-spacing:2px;">{title}</span>
          </div>
          {cards}
        </div>"""

    bk = section("BROOKLYN", "#e85d04", brooklyn)
    mn = section("MANHATTAN", "#1d4ed8", manhattan)
    bx = section("BRONX", "#b91c1c", bronx)

    return f"""<!DOCTYPE html>
<html><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@700&family=DM+Sans:ital,wght@0,400;0,500;0,700;0,800&display=swap" rel="stylesheet">
</head>
<body style="margin:0;padding:0;background:#000;font-family:'DM Sans',Arial,sans-serif;">
<div style="max-width:600px;margin:0 auto;">

  <div style="padding:32px 24px 24px;border-bottom:1px solid #1a1a1a;">
    <p style="margin:0 0 6px 0;font-family:'Space Mono',monospace;font-size:10px;color:#444;letter-spacing:3px;">EVERY SUNDAY · 7PM ET</p>
    <h1 style="margin:0;font-size:32px;font-weight:800;color:#fff;line-height:1.1;">NYC LIVE</h1>
    <h1 style="margin:0 0 16px 0;font-size:32px;font-weight:800;color:#f0a500;line-height:1.1;">MUSIC WEEKLY</h1>
    <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;">
      <span style="font-family:'Space Mono',monospace;font-size:11px;color:#555;">{start_str} – {end_str}</span>
      <span style="background:#111;border:1px solid #222;color:#555;font-size:10px;padding:3px 8px;border-radius:4px;">{len(events)} SHOWS</span>
    </div>
  </div>

  <div style="padding:24px;">
    {bk}{mn}{bx}
  </div>

  <div style="padding:16px 24px 32px;border-top:1px solid #111;text-align:center;">
    <p style="margin:0;font-family:'Space Mono',monospace;font-size:9px;color:#2a2a2a;letter-spacing:2px;">POWERED BY CLAUDE × LUCAS</p>
    <p style="margin:6px 0 0;font-size:11px;color:#222;">Next digest drops Sunday at 7PM ET</p>
  </div>

</div>
</body></html>"""

def build_plain(events, start_str, end_str):
    lines = [f"🎵 NYC LIVE MUSIC WEEKLY | {start_str} – {end_str}", f"📊 {len(events)} shows this week\n"]
    for borough_name, label in [("Brooklyn", "🟠 BROOKLYN"), ("Manhattan", "🔵 MANHATTAN"), ("Bronx", "🔴 BRONX")]:
        section = [e for e in events if e.get("borough") == borough_name]
        if not section:
            continue
        lines.append(f"\n{label}")
        lines.append("─" * 30)
        for e in section:
            time_part = f" · {e['time']}" if e.get("time") else ""
            lines.append(f"\n{e['name']}")
            lines.append(f"📍 {e['venue']}")
            lines.append(f"📅 {e['date']}{time_part}")
            lines.append(f"💰 {e.get('price', 'Check site')}")
            lines.append(f"🎟  {e.get('url', '')}")
    lines += ["\n———", "Powered by Claude x Lucas | Next digest drops Sunday at 7PM ET."]
    return "\n".join(lines)

def send_email(events, start_str, end_str):
    html = build_html_email(events, start_str, end_str)
    plain = build_plain(events, start_str, end_str)
    payload = {
        "personalizations": [{"to": [{"email": TO_EMAIL}]}],
        "from": {"email": FROM_EMAIL, "name": "NYC Live Music Weekly"},
        "subject": f"🎵 NYC Live Music Weekly | {start_str} – {end_str}",
        "content": [
            {"type": "text/plain", "value": plain},
            {"type": "text/html", "value": html}
        ]
    }
    resp = requests.post(
        "https://api.sendgrid.com/v3/mail/send",
        headers={"Authorization": f"Bearer {SENDGRID_API_KEY}", "Content-Type": "application/json"},
        json=payload, timeout=15
    )
    if resp.status_code in [200, 202]:
        print(f"✅ Email sent to {TO_EMAIL}")
    else:
        raise Exception(f"SendGrid error {resp.status_code}: {resp.text}")

def main():
    print("🔍 Fetching top NYC shows...")
    week_start, week_end = get_week_range()
    start_str = week_start.strftime("%B %d")
    end_str = week_end.strftime("%B %d, %Y")

    events = scrape_concerts50(week_start, week_end)
    print(f"   Final: {len(events)} events")

    print("📧 Sending via SendGrid...")
    send_email(events, start_str, end_str)

if __name__ == "__main__":
    main()
