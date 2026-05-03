import anthropic
import requests
from datetime import datetime, timedelta
import os
import json

# ─── CONFIG ───────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY  = os.environ["ANTHROPIC_API_KEY"]
SENDGRID_API_KEY   = os.environ["SENDGRID_API_KEY"]
TO_EMAIL           = "lucasfearn1@gmail.com"
FROM_EMAIL         = os.environ["FROM_EMAIL"]  # must be verified in SendGrid
# ──────────────────────────────────────────────────────────────────────────────

def get_week_range():
    today = datetime.now()
    days_until_monday = (7 - today.weekday()) % 7 or 7
    next_monday = today + timedelta(days=days_until_monday)
    next_sunday = next_monday + timedelta(days=6)
    return next_monday.strftime("%B %d"), next_sunday.strftime("%B %d, %Y")

def fetch_concerts_ticketmaster():
    """Fetch from Ticketmaster Discovery API (free, no auth needed for basic search)."""
    results = []
    today = datetime.now()
    week_end = today + timedelta(days=8)

    url = "https://app.ticketmaster.com/discovery/v2/events.json"
    params = {
        "apikey": "DpFbPSHQFJNsUFVb7FxJKZRXrKOHDYfR",  # public demo key
        "city": "New York",
        "stateCode": "NY",
        "classificationName": "music",
        "startDateTime": today.strftime("%Y-%m-%dT00:00:00Z"),
        "endDateTime": week_end.strftime("%Y-%m-%dT23:59:59Z"),
        "size": 200,
        "sort": "date,asc"
    }

    try:
        resp = requests.get(url, params=params, timeout=15)
        data = resp.json()
        events = data.get("_embedded", {}).get("events", [])

        for e in events:
            name = e.get("name", "")
            dates = e.get("dates", {}).get("start", {})
            date_str = dates.get("localDate", "")
            time_str = dates.get("localTime", "")
            venue_list = e.get("_embedded", {}).get("venues", [{}])
            venue = venue_list[0] if venue_list else {}
            venue_name = venue.get("name", "")
            city = venue.get("city", {}).get("name", "")
            state = venue.get("state", {}).get("stateCode", "")
            price_ranges = e.get("priceRanges", [])
            price = f"From ${int(price_ranges[0]['min'])}" if price_ranges else "Check site"
            url_link = e.get("url", "")
            genre = e.get("classifications", [{}])[0].get("genre", {}).get("name", "")
            subgenre = e.get("classifications", [{}])[0].get("subGenre", {}).get("name", "")

            # Format date
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                formatted_date = dt.strftime("%a %b %d")
            except:
                formatted_date = date_str

            # Format time
            try:
                t = datetime.strptime(time_str, "%H:%M:%S")
                formatted_time = t.strftime("%-I:%M %p")
            except:
                formatted_time = ""

            results.append({
                "name": name,
                "venue": venue_name,
                "city": city,
                "state": state,
                "date": formatted_date,
                "time": formatted_time,
                "price": price,
                "url": url_link,
                "genre": genre,
                "subgenre": subgenre
            })

    except Exception as ex:
        print(f"Ticketmaster error: {ex}")

    return results

def fetch_concerts_songkick():
    """Fetch from Songkick (scrape public listings)."""
    results = []
    try:
        today = datetime.now()
        week_end = today + timedelta(days=8)
        url = f"https://www.songkick.com/metro-areas/7644-us-new-york-nyc/calendar"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        resp = requests.get(url, headers=headers, timeout=15)
        # Basic extraction - Claude will handle the heavy lifting
        if resp.status_code == 200:
            results.append({"source": "songkick", "raw": resp.text[:5000]})
    except Exception as ex:
        print(f"Songkick error: {ex}")
    return results

def build_digest_with_claude(events, week_start, week_end):
    """Send event data to Claude to filter, format, and write the digest."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    if not events:
        events_text = "No events found from API. Please note this and generate a message telling Lucas to check back next week."
    else:
        events_text = "\n".join([
            f"- {e['name']} | {e['venue']} | {e['city']}, {e['state']} | {e['date']} {e['time']} | {e['price']} | Genre: {e['genre']}/{e['subgenre']} | {e['url']}"
            for e in events
        ])

    prompt = f"""You are compiling the weekly NYC live music digest for Lucas, a 19-year-old NYU student who loves DJs, EDM, hip-hop, rap, and big-name artists.

Week: {week_start} - {week_end}

Raw event data from Ticketmaster:
{events_text}

Your job:
1. Include ALL events — do not skip any. Every single show gets a card.
2. Prioritize and mark with ⭐ any: DJs, EDM artists, rappers, hip-hop artists, R&B artists, and big-name/popular artists.
3. Format EVERY event exactly like this:

ARTIST NAME — Tour/Show Name
📍 Venue, Borough/Area
📅 Day Month Date | Time
💰 Price
🎟 ticketlink.com

4. Group under borough headers:
🟠 BROOKLYN
🔵 MANHATTAN  
🟢 QUEENS
🔴 BRONX
⚪ OTHER NYC AREA

5. Start with this header:
🎵 NYC LIVE MUSIC WEEKLY | {week_start} - {week_end}

6. End with:
———
Powered by Claude x Lucas | Reply to this email with any requests for next week.

Be thorough. List every single event. DJs and rappers get ⭐. Do not summarize or combine events."""

    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}]
    )

    return message.content[0].text

def send_email_sendgrid(digest_text, week_start, week_end):
    """Send via SendGrid API (no SMTP, no port blocking)."""
    
    # Convert plain text to clean HTML
    html_lines = []
    for line in digest_text.split("\n"):
        if line.startswith("🎵"):
            html_lines.append(f'<h1 style="color:#1a1a1a;font-size:22px;margin-bottom:4px;">{line}</h1>')
        elif line in ["🟠 BROOKLYN", "🔵 MANHATTAN", "🟢 QUEENS", "🔴 BRONX", "⚪ OTHER NYC AREA"]:
            html_lines.append(f'<h2 style="color:#333;font-size:16px;margin-top:28px;margin-bottom:8px;border-bottom:1px solid #eee;padding-bottom:4px;">{line}</h2>')
        elif line.startswith("⭐") or (line and line[0].isalpha() and "—" in line):
            html_lines.append(f'<p style="font-weight:bold;margin:12px 0 2px 0;">{line}</p>')
        elif line.startswith("📍") or line.startswith("📅") or line.startswith("💰") or line.startswith("🎟"):
            html_lines.append(f'<p style="margin:1px 0 1px 12px;color:#444;">{line}</p>')
        elif line.startswith("———"):
            html_lines.append('<hr style="margin-top:32px;border:none;border-top:1px solid #eee;">')
        elif line.strip():
            html_lines.append(f'<p style="color:#666;font-size:12px;">{line}</p>')

    html_body = f"""
    <html><body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;
    max-width:600px;margin:auto;padding:24px;background:#fff;color:#111;line-height:1.6;">
    {"".join(html_lines)}
    </body></html>
    """

    payload = {
        "personalizations": [{"to": [{"email": TO_EMAIL}]}],
        "from": {"email": FROM_EMAIL, "name": "NYC Live Music Weekly"},
        "subject": f"🎵 NYC Live Music Weekly | {week_start} – {week_end}",
        "content": [
            {"type": "text/plain", "value": digest_text},
            {"type": "text/html", "value": html_body}
        ]
    }

    headers = {
        "Authorization": f"Bearer {SENDGRID_API_KEY}",
        "Content-Type": "application/json"
    }

    resp = requests.post(
        "https://api.sendgrid.com/v3/mail/send",
        headers=headers,
        data=json.dumps(payload),
        timeout=15
    )

    if resp.status_code in [200, 202]:
        print(f"✅ Email sent to {TO_EMAIL}")
    else:
        print(f"❌ SendGrid error {resp.status_code}: {resp.text}")
        raise Exception(f"SendGrid failed: {resp.status_code} {resp.text}")

def main():
    print("🔍 Fetching NYC concert data...")
    week_start, week_end = get_week_range()
    
    events = fetch_concerts_ticketmaster()
    print(f"   Ticketmaster: {len(events)} events found")

    print("🤖 Building digest with Claude...")
    digest = build_digest_with_claude(events, week_start, week_end)
    print("   Digest ready")

    print("📧 Sending email via SendGrid...")
    send_email_sendgrid(digest, week_start, week_end)

if __name__ == "__main__":
    main()
