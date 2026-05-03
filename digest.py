import json
import os
import re
import requests
import time
import anthropic
from datetime import datetime, timedelta

# ─── CONFIG ───────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
SENDGRID_API_KEY  = os.environ["SENDGRID_API_KEY"]
FROM_EMAIL        = os.environ["FROM_EMAIL"]
TO_EMAIL          = "lucasfearn1@gmail.com"
# ──────────────────────────────────────────────────────────────────────────────

# Only include events at these major NYC venues
MAJOR_VENUES = [
    "brooklyn paramount", "barclays center", "madison square garden", "msg",
    "radio city", "beacon theatre", "webster hall", "terminal 5", "irving plaza",
    "bowery ballroom", "brooklyn steel", "house of yes", "elsewhere",
    "baby's all right", "s.o.b", "sobs", "le poisson rouge", "lpr",
    "music hall of williamsburg", "warsaw", "kings theatre", "apollo theater",
    "united palace", "hammerstein", "playstation theater", "pier 17",
    "avant gardner", "brooklyn mirage", "knockdown center", "avant",
    "capital one theater", "gramercy theatre", "sultan room", "public arts",
    "bossa nova civic club", "h0l0", "analog", "market hotel", "tv eye",
    "paradise club", "good room", "nowadays", "forest hills stadium",
    "citi field", "yankee stadium", "jones beach", "pnc bank arts"
]

def get_week_range():
    today = datetime.now()
    days_until_monday = (7 - today.weekday()) % 7 or 7
    next_monday = today + timedelta(days=days_until_monday)
    next_sunday = next_monday + timedelta(days=6)
    return next_monday, next_sunday

def is_major_venue(venue_name):
    vl = (venue_name or "").lower()
    return any(mv in vl for mv in MAJOR_VENUES)

def fetch_big_shows_web_search(week_start, week_end):
    """Use Claude with web search to find top NYC concerts this week."""
    results = []
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        start_str = week_start.strftime("%B %d")
        end_str = week_end.strftime("%B %d, %Y")

        prompt = f"""Search for the biggest, most popular concerts and events happening in New York City from {start_str} to {end_str}, 2026.

Search ticketmaster.com, seatgeek.com, barclayscenter.com, brooklynparamount.com, msg.com, websterhall.com, boweryballroom.com, brooklynsteel.com, elsewhere.nyc, houseofyes.org, avantgardner.com.

I want ONLY the major, well-known events — big name rappers, DJs, pop artists, R&B singers, EDM acts performing at real venues. No open mic nights, no "open decks", no random underground events nobody has heard of.

Focus on: artists with real fanbases, shows at major venues (Barclays, MSG, Brooklyn Paramount, Webster Hall, Terminal 5, Irving Plaza, Bowery Ballroom, Brooklyn Steel, House of Yes, Avant Gardner/Brooklyn Mirage, Elsewhere, etc.)

Return ONLY a valid JSON array, no other text, no markdown:
[
  {{"name": "Artist Name", "show": "Tour or Show Name", "venue": "Venue Name", "borough": "Brooklyn", "date": "Mon May 04", "date_sort": "2026-05-04", "time": "8:00 PM", "price": "From $X", "url": "https://ticketmaster.com/..."}},
  ...
]

Return the top 40-50 most notable events only. Quality over quantity."""

        # Retry up to 3 times with backoff
        for attempt in range(3):
            try:
                message = client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=4000,
                    tools=[{"type": "web_search_20250305", "name": "web_search"}],
                    messages=[{"role": "user", "content": prompt}]
                )
                # Extract JSON from response
                for block in message.content:
                    if hasattr(block, "text") and block.text:
                        text = block.text.strip()
                        start_idx = text.find("[")
                        end_idx = text.rfind("]") + 1
                        if start_idx != -1 and end_idx > start_idx:
                            json_str = text[start_idx:end_idx]
                            events = json.loads(json_str)
                            print(f"   Web search: {len(events)} major events found")
                            results.extend(events)
                            break
                break
            except Exception as ex:
                print(f"   Web search attempt {attempt+1} failed: {ex}")
                if attempt < 2:
                    print(f"   Waiting 30s...")
                    time.sleep(30)

    except Exception as ex:
        print(f"   Web search error: {ex}")
    return results

def fetch_ra_major_venues(week_start, week_end):
    """Pull RA events but ONLY from major known venues."""
    all_events = []
    start_str = week_start.strftime("%Y-%m-%d")
    end_str = week_end.strftime("%Y-%m-%d")

    for page in range(1, 4):
        try:
            resp = requests.post(
                "https://ra.co/graphql",
                json={"query": f"query{{eventListings(filters:{{areas:{{eq:8}},listingDate:{{gte:\"{start_str}\",lte:\"{end_str}\"}}}},pageSize:100,page:{page}){{data{{id event{{title date startTime venue{{name}}}}}}}}}}"},
                headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0", "Referer": "https://ra.co"},
                timeout=20
            )
            data = resp.json()
            listings = ((data.get("data") or {}).get("eventListings") or {}).get("data") or []
            if not listings:
                break
            for item in listings:
                if not item:
                    continue
                e = item.get("event") or {}
                v = e.get("venue") or {}
                venue_name = v.get("name", "")
                date = (e.get("date") or "")[:10]

                # ONLY include major venues
                if not is_major_venue(venue_name):
                    continue
                if not (start_str <= date <= end_str):
                    continue

                raw_time = e.get("startTime") or ""
                if "T" in raw_time:
                    try:
                        t = datetime.fromisoformat(raw_time.replace("Z", ""))
                        raw_time = t.strftime("%-I:%M %p")
                    except:
                        raw_time = ""

                all_events.append({
                    "name": e.get("title", ""),
                    "show": "",
                    "venue": venue_name,
                    "borough": get_borough(venue_name),
                    "date": datetime.strptime(date, "%Y-%m-%d").strftime("%a %b %d") if date else date,
                    "date_sort": date,
                    "time": raw_time,
                    "price": "Check ra.co",
                    "url": f"https://ra.co/events/{item.get('id', '')}"
                })
        except Exception as ex:
            print(f"   RA page {page} error: {ex}")
            break

    print(f"   RA (major venues only): {len(all_events)} events")
    return all_events

def get_borough(venue_name):
    vl = (venue_name or "").lower()
    brooklyn_kw = ["brooklyn", "bossa nova", "h0l0", "silo", "elsewhere", "bushwick",
                   "williamsburg", "market hotel", "tv eye", "good room", "nowadays",
                   "house of yes", "avant gardner", "mirage", "warsaw", "kings theatre"]
    manhattan_kw = ["manhattan", "webster", "terminal 5", "irving", "bowery", "mercury",
                    "msg", "madison square", "radio city", "beacon", "gramercy", "sultan",
                    "public arts", "le poisson", "lpr", "sobs", "s.o.b", "apollo",
                    "united palace", "hammerstein", "pier 17", "capital one"]
    bronx_kw = ["bronx", "yankee"]

    if any(k in vl for k in brooklyn_kw):
        return "Brooklyn"
    if any(k in vl for k in bronx_kw):
        return "Bronx"
    return "Manhattan"

def deduplicate(events):
    seen = set()
    unique = []
    for e in events:
        key = ((e.get("name") or "").lower().strip()[:40], e.get("date_sort", e.get("date", "")))
        if key not in seen:
            seen.add(key)
            unique.append(e)
    return unique

def is_priority(name, show=""):
    keywords = ["dj", "edm", "electronic", "house", "techno", "rap", "hip-hop", "hip hop",
                "r&b", "reggaeton", "latin", "afrobeat", "dancehall", "bass", "rave",
                "club night", "dance"]
    combined = f"{name} {show}".lower()
    return any(k in combined for k in keywords)

def build_digest(events, week_start, week_end):
    start_str = week_start.strftime("%B %d")
    end_str = week_end.strftime("%B %d, %Y")

    # Sort by date
    events.sort(key=lambda e: e.get("date_sort", e.get("date", "")))

    # Group by borough (no Queens)
    groups = {"🟠 BROOKLYN": [], "🔵 MANHATTAN": [], "🔴 BRONX": []}

    for e in events:
        borough = e.get("borough", "Manhattan")
        if "Brooklyn" in borough:
            key = "🟠 BROOKLYN"
        elif "Bronx" in borough:
            key = "🔴 BRONX"
        else:
            key = "🔵 MANHATTAN"

        star = "⭐ " if is_priority(e.get("name",""), e.get("show","")) else ""
        name = e.get("name", "")
        show = e.get("show", "")
        venue = e.get("venue", "")
        date = e.get("date", "")
        time_str = f" | {e['time']}" if e.get("time") else ""
        price = e.get("price", "Check site")
        url = e.get("url", "")
        show_line = f" — {show}" if show else ""
        url_line = f"\n🎟  {url}" if url else ""

        card = f"{star}{name}{show_line}\n📍 {venue}, {borough}\n📅 {date}{time_str}\n💰 {price}{url_line}"
        groups[key].append(card)

    sections = []
    for header, cards in groups.items():
        if cards:
            sections.append(f"{header}\n\n" + "\n\n".join(cards))

    digest = f"🎵 NYC LIVE MUSIC WEEKLY | {start_str} – {end_str}\n"
    digest += f"📊 {len(events)} major shows this week\n\n"
    digest += "\n\n".join(sections)
    digest += "\n\n———\nPowered by Claude x Lucas | Next digest drops Sunday at 7PM ET."
    return digest, start_str, end_str

def send_email(digest, start_str, end_str):
    lines = digest.split("\n")
    html_lines = []
    for line in lines:
        if line.startswith("🎵"):
            html_lines.append(f'<h1 style="font-size:22px;color:#111;margin:0 0 2px 0;">{line}</h1>')
        elif line.startswith("📊"):
            html_lines.append(f'<p style="color:#999;font-size:12px;margin:0 0 24px 0;">{line}</p>')
        elif any(line.startswith(x) for x in ["🟠","🔵","🔴"]):
            html_lines.append(f'<h2 style="font-size:15px;font-weight:700;color:#222;margin:28px 0 10px 0;padding-bottom:6px;border-bottom:2px solid #f5f5f5;">{line}</h2>')
        elif line.startswith("⭐"):
            html_lines.append(f'<p style="font-weight:800;font-size:14px;margin:18px 0 2px 0;color:#000;">{line}</p>')
        elif any(line.startswith(x) for x in ["📍","📅","💰","🎟"]):
            html_lines.append(f'<p style="margin:2px 0;color:#555;font-size:13px;">{line}</p>')
        elif line.startswith("———"):
            html_lines.append('<hr style="margin:32px 0 12px 0;border:none;border-top:1px solid #eee;">')
        elif line.strip():
            html_lines.append(f'<p style="font-weight:700;font-size:14px;margin:18px 0 2px 0;">{line}</p>')

    html = f'<html><body style="font-family:-apple-system,BlinkMacSystemFont,Arial,sans-serif;max-width:620px;margin:auto;padding:24px 20px;background:#fff;">{"".join(html_lines)}</body></html>'

    payload = {
        "personalizations": [{"to": [{"email": TO_EMAIL}]}],
        "from": {"email": FROM_EMAIL, "name": "NYC Live Music Weekly"},
        "subject": f"🎵 NYC Live Music Weekly | {start_str} – {end_str}",
        "content": [
            {"type": "text/plain", "value": digest},
            {"type": "text/html", "value": html}
        ]
    }

    resp = requests.post(
        "https://api.sendgrid.com/v3/mail/send",
        headers={"Authorization": f"Bearer {SENDGRID_API_KEY}", "Content-Type": "application/json"},
        json=payload,
        timeout=15
    )

    if resp.status_code in [200, 202]:
        print(f"✅ Email sent to {TO_EMAIL}")
    else:
        raise Exception(f"SendGrid error {resp.status_code}: {resp.text}")

def main():
    print("🔍 Fetching top NYC shows...")
    week_start, week_end = get_week_range()

    all_events = []

    # Web search for big mainstream shows
    all_events += fetch_big_shows_web_search(week_start, week_end)

    # RA but ONLY major venues
    all_events += fetch_ra_major_venues(week_start, week_end)

    unique = deduplicate(all_events)
    print(f"   Total: {len(unique)} major events")

    print("📝 Building digest...")
    digest, start_str, end_str = build_digest(unique, week_start, week_end)

    print("📧 Sending via SendGrid...")
    send_email(digest, start_str, end_str)

if __name__ == "__main__":
    main()
