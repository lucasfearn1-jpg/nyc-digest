import anthropic
import requests
import json
import os
from datetime import datetime, timedelta

# ─── CONFIG ───────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY    = os.environ["ANTHROPIC_API_KEY"]
SENDGRID_API_KEY     = os.environ["SENDGRID_API_KEY"]
TICKETMASTER_API_KEY = os.environ["TICKETMASTER_API_KEY"]
FROM_EMAIL           = os.environ["FROM_EMAIL"]
TO_EMAIL             = "lucasfearn1@gmail.com"
# ──────────────────────────────────────────────────────────────────────────────

def get_week_range():
    today = datetime.now()
    days_until_monday = (7 - today.weekday()) % 7 or 7
    next_monday = today + timedelta(days=days_until_monday)
    next_sunday = next_monday + timedelta(days=6)
    return next_monday, next_sunday

def format_date(dt):
    return dt.strftime("%a %b %d")

def format_time(t_str):
    try:
        t = datetime.strptime(t_str, "%H:%M:%S")
        return t.strftime("%-I:%M %p")
    except:
        return ""

# ─── SOURCE 1: TICKETMASTER ───────────────────────────────────────────────────
def fetch_ticketmaster(start, end):
    results = []
    try:
        url = "https://app.ticketmaster.com/discovery/v2/events.json"
        params = {
            "apikey": TICKETMASTER_API_KEY,
            "city": "New York",
            "stateCode": "NY",
            "classificationName": "music",
            "startDateTime": start.strftime("%Y-%m-%dT00:00:00Z"),
            "endDateTime": end.strftime("%Y-%m-%dT23:59:59Z"),
            "size": 200,
            "sort": "date,asc"
        }
        resp = requests.get(url, params=params, timeout=15)
        data = resp.json()
        events = data.get("_embedded", {}).get("events", [])
        print(f"   Ticketmaster: {len(events)} events")
        for e in events:
            venue = e.get("_embedded", {}).get("venues", [{}])[0]
            price_ranges = e.get("priceRanges", [])
            price = f"From ${int(price_ranges[0]['min'])}" if price_ranges else "Check site"
            dates = e.get("dates", {}).get("start", {})
            try:
                dt = datetime.strptime(dates.get("localDate", ""), "%Y-%m-%d")
                date_str = format_date(dt)
            except:
                date_str = dates.get("localDate", "")
            genre = e.get("classifications", [{}])[0].get("genre", {}).get("name", "")
            subgenre = e.get("classifications", [{}])[0].get("subGenre", {}).get("name", "")
            results.append({
                "name": e.get("name", ""),
                "venue": venue.get("name", ""),
                "city": venue.get("city", {}).get("name", ""),
                "date": date_str,
                "time": format_time(dates.get("localTime", "")),
                "price": price,
                "url": e.get("url", ""),
                "genre": f"{genre}/{subgenre}",
                "source": "Ticketmaster"
            })
    except Exception as ex:
        print(f"   Ticketmaster error: {ex}")
    return results

# ─── SOURCE 2: SEATGEEK ───────────────────────────────────────────────────────
def fetch_seatgeek(start, end):
    results = []
    try:
        url = "https://api.seatgeek.com/2/events"
        params = {
            "venue.city": "New York",
            "venue.state": "NY",
            "taxonomies.name": "concert",
            "datetime_local.gte": start.strftime("%Y-%m-%dT00:00:00"),
            "datetime_local.lte": end.strftime("%Y-%m-%dT23:59:59"),
            "per_page": 200,
            "sort": "datetime_local.asc",
            "client_id": "MjE0NzQ5NDF8MTY5NTIyNzE2My4xMzA1NzM2"
        }
        resp = requests.get(url, params=params, timeout=15)
        data = resp.json()
        events = data.get("events", [])
        print(f"   SeatGeek: {len(events)} events")
        for e in events:
            venue = e.get("venue", {})
            stats = e.get("stats", {})
            lowest = stats.get("lowest_price")
            price = f"From ${lowest}" if lowest else "Check site"
            try:
                dt = datetime.fromisoformat(e.get("datetime_local", ""))
                date_str = format_date(dt)
                time_str = dt.strftime("%-I:%M %p")
            except:
                date_str = ""
                time_str = ""
            results.append({
                "name": e.get("title", ""),
                "venue": venue.get("name", ""),
                "city": venue.get("city", ""),
                "date": date_str,
                "time": time_str,
                "price": price,
                "url": e.get("url", ""),
                "genre": "/".join([t.get("name","") for t in e.get("taxonomies", [])]),
                "source": "SeatGeek"
            })
    except Exception as ex:
        print(f"   SeatGeek error: {ex}")
    return results

# ─── SOURCE 3: RESIDENT ADVISOR (EDM/DJ focused) ──────────────────────────────
def fetch_resident_advisor(start, end):
    results = []
    try:
        url = "https://ra.co/graphql"
        query = """
        query GET_EVENT_LISTINGS($filters: FilterInputDtoInput, $pageSize: Int) {
          eventListings(filters: $filters, pageSize: $pageSize) {
            data {
              id
              event {
                title
                date
                startTime
                venue { name area { name } }
                images { filename }
                tickets { onSaleFrom }
              }
            }
          }
        }
        """
        variables = {
            "filters": {
                "areas": {"eq": 8},  # New York City area ID
                "listingDate": {
                    "gte": start.strftime("%Y-%m-%d"),
                    "lte": end.strftime("%Y-%m-%d")
                }
            },
            "pageSize": 100
        }
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://ra.co"
        }
        resp = requests.post(url, json={"query": query, "variables": variables}, headers=headers, timeout=15)
        data = resp.json()
        listings = data.get("data", {}).get("eventListings", {}).get("data", [])
        print(f"   Resident Advisor: {len(listings)} events")
        for item in listings:
            e = item.get("event", {})
            venue = e.get("venue", {})
            area = venue.get("area", {}).get("name", "New York")
            try:
                dt = datetime.fromisoformat(e.get("date", "").replace("Z", ""))
                date_str = format_date(dt)
            except:
                date_str = e.get("date", "")[:10]
            start_time = e.get("startTime", "")
            results.append({
                "name": e.get("title", ""),
                "venue": venue.get("name", ""),
                "city": area,
                "date": date_str,
                "time": start_time,
                "price": "Check site",
                "url": f"https://ra.co/events/{item.get('id','')}",
                "genre": "DJ/Electronic",
                "source": "Resident Advisor"
            })
    except Exception as ex:
        print(f"   Resident Advisor error: {ex}")
    return results

# ─── SOURCE 4: DICE.FM ────────────────────────────────────────────────────────
def fetch_dice(start, end):
    results = []
    try:
        url = "https://api.dice.fm/api/v1/events"
        params = {
            "country_code": "US",
            "city": "New York",
            "start_date": start.strftime("%Y-%m-%d"),
            "end_date": end.strftime("%Y-%m-%d"),
            "page[size]": 100
        }
        headers = {
            "User-Agent": "Mozilla/5.0",
            "x-api-key": "dice"
        }
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            events = data.get("data", [])
            print(f"   Dice.fm: {len(events)} events")
            for e in events:
                venue = e.get("venue", {})
                try:
                    dt = datetime.fromisoformat(e.get("date", "").replace("Z", ""))
                    date_str = format_date(dt)
                    time_str = dt.strftime("%-I:%M %p")
                except:
                    date_str = ""
                    time_str = ""
                results.append({
                    "name": e.get("name", ""),
                    "venue": venue.get("name", ""),
                    "city": "New York",
                    "date": date_str,
                    "time": time_str,
                    "price": "Check site",
                    "url": f"https://dice.fm/event/{e.get('id','')}",
                    "genre": "Electronic/Club",
                    "source": "Dice.fm"
                })
        else:
            print(f"   Dice.fm: status {resp.status_code}")
    except Exception as ex:
        print(f"   Dice.fm error: {ex}")
    return results

# ─── DEDUPLICATE ──────────────────────────────────────────────────────────────
def deduplicate(all_events):
    seen = set()
    unique = []
    for e in all_events:
        key = (e["name"].lower().strip()[:40], e["date"])
        if key not in seen:
            seen.add(key)
            unique.append(e)
    return unique

# ─── BUILD DIGEST WITH CLAUDE ─────────────────────────────────────────────────
def build_digest(events, week_start, week_end):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    start_str = week_start.strftime("%B %d")
    end_str = week_end.strftime("%B %d, %Y")

    if not events:
        events_text = "No events returned from any source this week."
    else:
        events_text = "\n".join([
            f"- {e['name']} | {e['venue']} | {e['city']} | {e['date']} {e['time']} | {e['price']} | {e['genre']} | {e['source']} | {e['url']}"
            for e in events
        ])

    prompt = f"""You are compiling the weekly NYC live music digest for Lucas, a 19-year-old NYU student.
He wants EVERY single show listed — DJs, EDM, rap, hip-hop, R&B, pop, rock, everything.
Week: {start_str} – {end_str}

Raw data from Ticketmaster, SeatGeek, Resident Advisor, and Dice.fm:
{events_text}

Rules:
1. List EVERY single event. Do not skip or combine any.
2. Mark with ⭐ any DJ, EDM, rap, hip-hop, R&B, or big-name artist.
3. Format each event EXACTLY like this:

⭐ ARTIST NAME — Tour/Show Name
📍 Venue Name, Borough
📅 Day Mon DD | Time
💰 Price
🎟 URL

(remove ⭐ for non-priority genres like classical/country)

4. Group by borough:
🟠 BROOKLYN
🔵 MANHATTAN
🟢 QUEENS
🔴 BRONX
⚪ OTHER / TBD

5. Header (first line):
🎵 NYC LIVE MUSIC WEEKLY | {start_str} – {end_str}
📊 {len(events)} shows pulled from Ticketmaster · SeatGeek · Resident Advisor · Dice.fm

6. Footer:
———
Powered by Claude x Lucas | Next digest drops Sunday at 7PM ET."""

    msg = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=6000,
        messages=[{"role": "user", "content": prompt}]
    )
    return msg.content[0].text, start_str, end_str

# ─── SEND VIA SENDGRID ────────────────────────────────────────────────────────
def send_email(digest_text, start_str, end_str):
    lines = digest_text.split("\n")
    html_lines = []
    for line in lines:
        if line.startswith("🎵"):
            html_lines.append(f'<h1 style="font-size:20px;color:#111;margin-bottom:2px;">{line}</h1>')
        elif line.startswith("📊"):
            html_lines.append(f'<p style="color:#888;font-size:12px;margin-top:0;">{line}</p>')
        elif any(line.startswith(x) for x in ["🟠","🔵","🟢","🔴","⚪"]):
            html_lines.append(f'<h2 style="font-size:15px;color:#333;margin-top:24px;border-bottom:1px solid #eee;padding-bottom:4px;">{line}</h2>')
        elif line.startswith("⭐") or (line and not line.startswith("📍") and not line.startswith("📅") and not line.startswith("💰") and not line.startswith("🎟") and not line.startswith("—") and len(line) > 2 and line[0].isalpha()):
            html_lines.append(f'<p style="font-weight:600;margin:14px 0 2px 0;">{line}</p>')
        elif any(line.startswith(x) for x in ["📍","📅","💰","🎟"]):
            html_lines.append(f'<p style="margin:1px 0 1px 10px;color:#555;font-size:13px;">{line}</p>')
        elif line.startswith("———"):
            html_lines.append('<hr style="margin-top:28px;border:none;border-top:1px solid #eee;">')
        elif line.strip():
            html_lines.append(f'<p style="color:#777;font-size:12px;">{line}</p>')

    html = f"""<html><body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;
    max-width:600px;margin:auto;padding:24px 20px;background:#fff;color:#111;line-height:1.5;">
    {"".join(html_lines)}</body></html>"""

    payload = {
        "personalizations": [{"to": [{"email": TO_EMAIL}]}],
        "from": {"email": FROM_EMAIL, "name": "NYC Live Music Weekly"},
        "subject": f"🎵 NYC Live Music Weekly | {start_str} – {end_str}",
        "content": [
            {"type": "text/plain", "value": digest_text},
            {"type": "text/html", "value": html}
        ]
    }

    resp = requests.post(
        "https://api.sendgrid.com/v3/mail/send",
        headers={"Authorization": f"Bearer {SENDGRID_API_KEY}", "Content-Type": "application/json"},
        data=json.dumps(payload),
        timeout=15
    )

    if resp.status_code in [200, 202]:
        print(f"✅ Email sent to {TO_EMAIL}")
    else:
        raise Exception(f"SendGrid error {resp.status_code}: {resp.text}")

# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    print("🔍 Fetching NYC concert data from all sources...")
    week_start, week_end = get_week_range()

    all_events = []
    all_events += fetch_ticketmaster(week_start, week_end)
    all_events += fetch_seatgeek(week_start, week_end)
    all_events += fetch_resident_advisor(week_start, week_end)
    all_events += fetch_dice(week_start, week_end)

    unique_events = deduplicate(all_events)
    print(f"   Total unique events: {len(unique_events)}")

    print("🤖 Building digest with Claude...")
    digest, start_str, end_str = build_digest(unique_events, week_start, week_end)

    print("📧 Sending via SendGrid...")
    send_email(digest, start_str, end_str)

if __name__ == "__main__":
    main()
