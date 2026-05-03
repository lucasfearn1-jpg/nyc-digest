import anthropic
import requests
import json
import os
from datetime import datetime, timedelta

# ─── CONFIG ───────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
SENDGRID_API_KEY  = os.environ["SENDGRID_API_KEY"]
FROM_EMAIL        = os.environ["FROM_EMAIL"]
TO_EMAIL          = "lucasfearn1@gmail.com"
# ──────────────────────────────────────────────────────────────────────────────

def get_week_range():
    today = datetime.now()
    days_until_monday = (7 - today.weekday()) % 7 or 7
    next_monday = today + timedelta(days=days_until_monday)
    next_sunday = next_monday + timedelta(days=6)
    return next_monday, next_sunday

def format_date(dt):
    return dt.strftime("%a %b %d")

# ─── SOURCE 1: RESIDENT ADVISOR (DJ/Club/Electronic) ─────────────────────────
def fetch_resident_advisor(start, end):
    results = []
    try:
        url = "https://ra.co/graphql"
        query = """
        query GET_LISTINGS($filters: FilterInputDtoInput, $pageSize: Int) {
          eventListings(filters: $filters, pageSize: $pageSize) {
            data {
              id
              event {
                title
                date
                startTime
                venue { name area { name } }
              }
            }
          }
        }
        """
        variables = {
            "filters": {
                "areas": {"eq": 8},  # NYC = 8
                "listingDate": {
                    "gte": start.strftime("%Y-%m-%d"),
                    "lte": end.strftime("%Y-%m-%d")
                }
            },
            "pageSize": 200
        }
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://ra.co"
        }
        resp = requests.post(url, json={"query": query, "variables": variables}, headers=headers, timeout=20)
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
            results.append({
                "name": e.get("title", ""),
                "venue": venue.get("name", ""),
                "city": area,
                "date": date_str,
                "time": e.get("startTime", ""),
                "price": "Check ra.co",
                "url": f"https://ra.co/events/{item.get('id', '')}",
                "genre": "DJ/Electronic/Club",
                "source": "Resident Advisor"
            })
    except Exception as ex:
        print(f"   Resident Advisor error: {ex}")
    return results

# ─── SOURCE 2: CLAUDE WEB SEARCH (Big Concerts/Rap/Pop/Arena Shows) ──────────
def fetch_big_shows_via_claude(start, end):
    """Use Claude with web search to find major NYC concerts that week."""
    results = []
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        start_str = start.strftime("%B %d")
        end_str = end.strftime("%B %d, %Y")

        search_prompt = f"""Search for all major concerts and shows happening in New York City from {start_str} to {end_str}, 2026.

Search these sources:
- ticketmaster.com NYC concerts
- seatgeek.com NYC concerts  
- brooklynparamount.com schedule
- barclayscenter.com events
- msg.com (Madison Square Garden) events
- boweryballroom.com
- websterhall.com
- terminalfive.net
- Irving Plaza NYC
- Brooklyn Steel NYC

Focus on: rappers, hip-hop artists, R&B artists, pop stars, big name artists, DJs performing at major venues.

For each show found, return ONLY a JSON array like this (no other text):
[
  {{"name": "Artist Name - Tour Name", "venue": "Venue Name", "city": "Brooklyn", "date": "Mon May 04", "time": "8:00 PM", "price": "From $X", "url": "ticketlink", "genre": "Hip-Hop", "source": "Ticketmaster"}},
  ...
]

Return only the JSON array, nothing else."""

        message = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=3000,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": search_prompt}]
        )

        # Extract text from response
        for block in message.content:
            if hasattr(block, 'text') and block.text:
                text = block.text.strip()
                # Find JSON array in response
                start_idx = text.find('[')
                end_idx = text.rfind(']') + 1
                if start_idx != -1 and end_idx > start_idx:
                    json_str = text[start_idx:end_idx]
                    events = json.loads(json_str)
                    print(f"   Web search (big shows): {len(events)} events")
                    results.extend(events)
                    break

    except Exception as ex:
        print(f"   Web search error: {ex}")
    return results

# ─── DEDUPLICATE ──────────────────────────────────────────────────────────────
def deduplicate(all_events):
    seen = set()
    unique = []
    for e in all_events:
        key = (e.get("name", "").lower().strip()[:40], e.get("date", ""))
        if key not in seen:
            seen.add(key)
            unique.append(e)
    return unique

# ─── BUILD DIGEST WITH CLAUDE ─────────────────────────────────────────────────
def build_digest(events, start, end):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    start_str = start.strftime("%B %d")
    end_str = end.strftime("%B %d, %Y")

    if not events:
        events_text = "No events found this week."
    else:
        events_text = "\n".join([
            f"- {e.get('name','')} | {e.get('venue','')} | {e.get('city','')} | {e.get('date','')} {e.get('time','')} | {e.get('price','')} | {e.get('genre','')} | {e.get('source','')} | {e.get('url','')}"
            for e in events
        ])

    prompt = f"""You are compiling the weekly NYC live music digest for Lucas, a 19-year-old NYU student.
He wants EVERY single show listed — DJs, EDM, rap, hip-hop, R&B, pop, everything.
Week: {start_str} – {end_str}
Total events: {len(events)}

Data from Resident Advisor + web search:
{events_text}

Rules:
1. List EVERY single event. Do not skip or combine any.
2. Mark with ⭐ any: DJ sets, EDM, rap, hip-hop, R&B, or big-name/popular artists.
3. Format each event EXACTLY like this:

⭐ ARTIST/EVENT NAME — Tour or Show Name
📍 Venue Name, Borough
📅 Day Mon DD | Time
💰 Price
🎟 URL

4. Group by borough header:
🟠 BROOKLYN
🔵 MANHATTAN
🟢 QUEENS
🔴 BRONX
⚪ OTHER / TBD

5. First line must be:
🎵 NYC LIVE MUSIC WEEKLY | {start_str} – {end_str}
📊 {len(events)} shows · Resident Advisor · Ticketmaster · SeatGeek · Brooklyn Paramount · Barclays · MSG

6. Last line:
———
Powered by Claude x Lucas | Next digest drops Sunday at 7PM ET.

Be thorough. List every single event. No skipping."""

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
            html_lines.append(f'<p style="color:#888;font-size:12px;margin-top:0;margin-bottom:20px;">{line}</p>')
        elif any(line.startswith(x) for x in ["🟠","🔵","🟢","🔴","⚪"]):
            html_lines.append(f'<h2 style="font-size:15px;color:#333;margin-top:28px;border-bottom:2px solid #f0f0f0;padding-bottom:6px;">{line}</h2>')
        elif line.startswith("⭐") or (line and not any(line.startswith(x) for x in ["📍","📅","💰","🎟","———","📊","🎵"]) and len(line) > 3):
            html_lines.append(f'<p style="font-weight:700;margin:16px 0 3px 0;font-size:14px;">{line}</p>')
        elif any(line.startswith(x) for x in ["📍","📅","💰","🎟"]):
            html_lines.append(f'<p style="margin:2px 0 2px 10px;color:#555;font-size:13px;">{line}</p>')
        elif line.startswith("———"):
            html_lines.append('<hr style="margin-top:32px;border:none;border-top:1px solid #eee;">')
        elif line.strip():
            html_lines.append(f'<p style="color:#777;font-size:12px;">{line}</p>')

    html = f"""<html><body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;
    max-width:620px;margin:auto;padding:28px 20px;background:#fff;color:#111;line-height:1.5;">
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
    print("🔍 Fetching NYC concert data...")
    week_start, week_end = get_week_range()

    all_events = []

    # RA for DJ/club/electronic
    all_events += fetch_resident_advisor(week_start, week_end)

    # Claude web search for big concerts/rappers/arena shows
    all_events += fetch_big_shows_via_claude(week_start, week_end)

    unique = deduplicate(all_events)
    print(f"   Total unique events: {len(unique)}")

    print("🤖 Building digest with Claude...")
    digest, start_str, end_str = build_digest(unique, week_start, week_end)

    print("📧 Sending via SendGrid...")
    send_email(digest, start_str, end_str)

if __name__ == "__main__":
    main()
