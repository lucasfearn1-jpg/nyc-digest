import anthropic
import smtplib
import requests
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta
import os

# ─── CONFIG ───────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GMAIL_ADDRESS     = os.environ["GMAIL_ADDRESS"]       # your Gmail you send FROM
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"] # Gmail App Password (not your login password)
TO_EMAIL          = "lucasfearn1@gmail.com"
# ──────────────────────────────────────────────────────────────────────────────

def get_week_range():
    today = datetime.now()
    # Next Monday through Sunday
    days_until_monday = (7 - today.weekday()) % 7 or 7
    next_monday = today + timedelta(days=days_until_monday)
    next_sunday = next_monday + timedelta(days=6)
    return next_monday.strftime("%B %d"), next_sunday.strftime("%B %d, %Y")

def fetch_concert_data():
    """Pull raw concert listings from SeatGeek public API (no key needed for basic search)."""
    results = []
    
    base_url = "https://api.seatgeek.com/2/events"
    today = datetime.now()
    week_start = today + timedelta(days=1)
    week_end = today + timedelta(days=8)

    params = {
        "venue.city": "New York",
        "venue.state": "NY",
        "datetime_local.gte": week_start.strftime("%Y-%m-%dT00:00:00"),
        "datetime_local.lte": week_end.strftime("%Y-%m-%dT23:59:59"),
        "taxonomies.name": "concert",
        "per_page": 100,
        "sort": "datetime_local.asc",
        "client_id": "MjE0NzQ5NDF8MTY5NTIyNzE2My4xMzA1NzM2"  # SeatGeek public demo client_id
    }

    try:
        resp = requests.get(base_url, params=params, timeout=15)
        data = resp.json()
        events = data.get("events", [])
        
        for e in events:
            title = e.get("title", "")
            venue = e.get("venue", {})
            venue_name = venue.get("name", "")
            venue_city = venue.get("city", "")
            venue_state = venue.get("state", "")
            dt_local = e.get("datetime_local", "")
            stats = e.get("stats", {})
            lowest = stats.get("lowest_price")
            avg = stats.get("average_price")
            url = e.get("url", "")

            # Parse date/time
            try:
                dt = datetime.fromisoformat(dt_local)
                date_str = dt.strftime("%a %b %d")
                time_str = dt.strftime("%-I:%M %p")
            except Exception:
                date_str = dt_local[:10]
                time_str = ""

            price_str = f"From ${lowest}" if lowest else ("~$" + str(avg) if avg else "Check site")

            results.append({
                "title": title,
                "venue": venue_name,
                "location": f"{venue_city}, {venue_state}",
                "date": date_str,
                "time": time_str,
                "price": price_str,
                "url": url,
            })
    except Exception as ex:
        results.append({"error": str(ex)})

    return results

def build_digest_with_claude(raw_events, week_start, week_end):
    """Send raw event data to Claude to format into a clean digest."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    events_text = "\n".join([
        f"- {e.get('title','?')} | {e.get('venue','?')} | {e.get('location','?')} | {e.get('date','?')} {e.get('time','?')} | {e.get('price','?')} | {e.get('url','')}"
        for e in raw_events if "error" not in e
    ])

    prompt = f"""You are compiling the weekly NYC live music digest for Lucas, a college student at NYU.
Week: {week_start} – {week_end}

Here is the raw event data pulled from SeatGeek for NYC this week:
{events_text}

Your job:
1. Filter and highlight: DJs, EDM artists, rappers, hip-hop artists, and any big-name/popular artists. Include ALL of them — do not skip any.
2. Also include any other notable concerts worth knowing about.
3. Format each entry EXACTLY like this (one per line, grouped by borough):

ARTIST NAME — Show/Tour Name
📍 Venue Name, Borough
📅 Day Month Date | Time
💰 Price Range
🎟 [ticket link if available]

Group events under headers: 🟠 BROOKLYN | 🔵 MANHATTAN | 🟢 QUEENS | 🔴 BRONX | ⚪ OTHER NYC

4. At the top, add a bold intro line: "🎵 NYC Live Music Weekly | {week_start} – {week_end}"
5. At the bottom add: "Pull from Claude — message back with any artists you want more info on."

Be thorough. Do not summarize or cut events. Every DJ, every rapper, every big artist gets a card."""

    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}]
    )

    return message.content[0].text

def send_email(digest_text, week_start, week_end):
    """Send the digest to Lucas's Gmail."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🎵 NYC Live Music Weekly | {week_start} – {week_end}"
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = TO_EMAIL

    # Plain text version
    plain = digest_text

    # Simple HTML version
    html_body = digest_text.replace("\n", "<br>").replace("🟠", "<b>🟠").replace("🔵", "<b>🔵").replace("🟢", "<b>🟢").replace("🔴", "<b>🔴").replace("⚪", "<b>⚪")
    html = f"""
    <html><body style="font-family: Arial, sans-serif; font-size: 14px; line-height: 1.8; color: #111; max-width: 640px; margin: auto; padding: 20px;">
    {html_body}
    </body></html>
    """

    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, TO_EMAIL, msg.as_string())

    print(f"✅ Digest sent to {TO_EMAIL}")

def main():
    print("🔍 Fetching NYC concert data...")
    week_start, week_end = get_week_range()
    raw_events = fetch_concert_data()
    print(f"   Found {len(raw_events)} events")

    print("🤖 Building digest with Claude...")
    digest = build_digest_with_claude(raw_events, week_start, week_end)

    print("📧 Sending email...")
    send_email(digest, week_start, week_end)

if __name__ == "__main__":
    main()
