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

def get_week_range():
    today = datetime.now()
    days_until_monday = (7 - today.weekday()) % 7 or 7
    next_monday = today + timedelta(days=days_until_monday)
    next_sunday = next_monday + timedelta(days=6)
    return next_monday, next_sunday

def fetch_top_shows(week_start, week_end):
    """Use Claude with web search to find top 30 NYC shows from real ticketing sites."""
    results = []
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        start_str = week_start.strftime("%B %d")
        end_str = week_end.strftime("%B %d, %Y")

        prompt = f"""Search Ticketmaster, SeatGeek, AXS, and Dice.fm for the top concerts and shows in New York City from {start_str} to {end_str}, 2026.

Search these specific URLs:
- ticketmaster.com/discover/concerts/new-york
- seatgeek.com/new-york-ny/concerts
- axs.com/events (New York)
- dice.fm/browse/new-york

I want ONLY the 30 most popular, well-known events. Think: artists that would trend on social media, fill a major venue, have real ticket demand. Big rappers, DJs with real followings, pop stars, R&B artists, major EDM acts. Shows at Brooklyn Paramount, Barclays Center, MSG, Webster Hall, Terminal 5, Irving Plaza, Bowery Ballroom, Brooklyn Steel, House of Yes, Avant Gardner, Elsewhere.

NO: open mics, open decks, random underground artists nobody knows, comedy shows, classical music, Broadway.

For each event get the ACTUAL ticket link from ticketmaster.com, seatgeek.com, or axs.com — not ra.co.

Return ONLY valid JSON array, no markdown, no explanation:
[
  {{
    "name": "Artist Name",
    "show": "Tour Name or empty string",
    "venue": "Venue Name",
    "borough": "Brooklyn or Manhattan or Bronx",
    "date": "Mon May 05",
    "date_sort": "2026-05-05",
    "time": "8:00 PM",
    "price": "From $45",
    "url": "https://www.ticketmaster.com/event/actual-link",
    "source": "Ticketmaster"
  }}
]

Return exactly 30 events max, ranked by popularity/hype. Real links only."""

        for attempt in range(3):
            try:
                message = client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=4000,
                    tools=[{"type": "web_search_20250305", "name": "web_search"}],
                    messages=[{"role": "user", "content": prompt}]
                )
                for block in message.content:
                    if hasattr(block, "text") and block.text:
                        text = block.text.strip()
                        start_idx = text.find("[")
                        end_idx = text.rfind("]") + 1
                        if start_idx != -1 and end_idx > start_idx:
                            events = json.loads(text[start_idx:end_idx])
                            print(f"   Found {len(events)} top shows")
                            results.extend(events)
                            break
                break
            except Exception as ex:
                print(f"   Attempt {attempt+1} failed: {ex}")
                if attempt < 2:
                    time.sleep(30)

    except Exception as ex:
        print(f"   Web search error: {ex}")
    return results[:30]

def build_html_email(events, start_str, end_str):
    """Build a dark, sleek, music-forward HTML email."""

    def is_priority(name, show=""):
        keywords = ["dj", "edm", "electronic", "house", "techno", "rap", "hip-hop",
                    "hip hop", "r&b", "reggaeton", "latin", "afrobeat", "dancehall", "bass"]
        return any(k in f"{name} {show}".lower() for k in keywords)

    # Group by borough
    brooklyn = [e for e in events if e.get("borough","").lower() == "brooklyn"]
    manhattan = [e for e in events if e.get("borough","").lower() == "manhattan"]
    bronx = [e for e in events if e.get("borough","").lower() == "bronx"]

    def render_card(e):
        name = e.get("name","")
        show = e.get("show","")
        venue = e.get("venue","")
        date = e.get("date","")
        time_str = e.get("time","")
        price = e.get("price","Check site")
        url = e.get("url","#")
        source = e.get("source","")
        priority = is_priority(name, show)

        star = "⭐" if priority else "🎵"
        show_line = f"<span style='color:#888;font-size:12px;display:block;margin-top:2px;'>{show}</span>" if show else ""
        source_badge = f"<span style='background:#222;color:#aaa;font-size:10px;padding:2px 6px;border-radius:3px;margin-left:6px;'>{source}</span>" if source else ""

        return f"""
        <div style="background:#111;border:1px solid #222;border-radius:12px;padding:16px 18px;margin-bottom:12px;">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;">
            <div style="flex:1;">
              <p style="margin:0 0 2px 0;font-size:15px;font-weight:700;color:#fff;">{star} {name}</p>
              {show_line}
              <p style="margin:8px 0 2px 0;color:#888;font-size:12px;">📍 {venue}</p>
              <p style="margin:0 0 2px 0;color:#888;font-size:12px;">📅 {date}{' · ' + time_str if time_str else ''}</p>
              <p style="margin:0;color:#f0a500;font-size:12px;font-weight:600;">💰 {price}</p>
            </div>
          </div>
          <div style="margin-top:12px;">
            <a href="{url}" style="display:inline-block;background:#fff;color:#000;font-size:12px;font-weight:700;padding:7px 16px;border-radius:20px;text-decoration:none;">GET TICKETS {source_badge}</a>
          </div>
        </div>"""

    def render_section(title, emoji, color, events_list):
        if not events_list:
            return ""
        cards = "".join([render_card(e) for e in events_list])
        return f"""
        <div style="margin-bottom:32px;">
          <div style="display:flex;align-items:center;margin-bottom:16px;">
            <span style="background:{color};color:#fff;font-size:11px;font-weight:800;padding:4px 10px;border-radius:4px;letter-spacing:1px;">{title}</span>
          </div>
          {cards}
        </div>"""

    brooklyn_section = render_section("BROOKLYN", "🟠", "#e85d04", brooklyn)
    manhattan_section = render_section("MANHATTAN", "🔵", "#1d4ed8", manhattan)
    bronx_section = render_section("BRONX", "🔴", "#b91c1c", bronx)

    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@400;500;700&display=swap" rel="stylesheet">
</head>
<body style="margin:0;padding:0;background:#000;font-family:'DM Sans',Arial,sans-serif;">
  <div style="max-width:600px;margin:0 auto;padding:0 0 40px 0;">

    <!-- HEADER -->
    <div style="padding:32px 24px 24px 24px;border-bottom:1px solid #1a1a1a;">
      <p style="margin:0 0 4px 0;font-family:'Space Mono',monospace;font-size:11px;color:#555;letter-spacing:3px;text-transform:uppercase;">Every Sunday · 7PM ET</p>
      <h1 style="margin:0 0 4px 0;font-size:28px;font-weight:800;color:#fff;line-height:1.1;">NYC LIVE MUSIC</h1>
      <h1 style="margin:0 0 16px 0;font-size:28px;font-weight:800;color:#f0a500;line-height:1.1;">WEEKLY</h1>
      <div style="display:flex;align-items:center;gap:12px;">
        <span style="font-family:'Space Mono',monospace;font-size:12px;color:#666;">{start_str} – {end_str}</span>
        <span style="background:#1a1a1a;color:#888;font-size:11px;padding:3px 8px;border-radius:4px;">{len(events)} SHOWS</span>
      </div>
    </div>

    <!-- BODY -->
    <div style="padding:24px;">
      {brooklyn_section}
      {manhattan_section}
      {bronx_section}
    </div>

    <!-- FOOTER -->
    <div style="padding:20px 24px;border-top:1px solid #1a1a1a;text-align:center;">
      <p style="margin:0;font-family:'Space Mono',monospace;font-size:10px;color:#444;letter-spacing:2px;">POWERED BY CLAUDE × LUCAS</p>
      <p style="margin:6px 0 0 0;font-size:11px;color:#333;">Next digest drops Sunday at 7PM ET</p>
    </div>

  </div>
</body>
</html>"""

    return html

def build_plain_text(events, start_str, end_str):
    lines = [f"🎵 NYC LIVE MUSIC WEEKLY | {start_str} – {end_str}", f"📊 {len(events)} top shows\n"]

    brooklyn = [e for e in events if e.get("borough","").lower() == "brooklyn"]
    manhattan = [e for e in events if e.get("borough","").lower() == "manhattan"]
    bronx = [e for e in events if e.get("borough","").lower() == "bronx"]

    for section_name, section_events in [("🟠 BROOKLYN", brooklyn), ("🔵 MANHATTAN", manhattan), ("🔴 BRONX", bronx)]:
        if not section_events:
            continue
        lines.append(f"\n{section_name}")
        lines.append("─" * 30)
        for e in section_events:
            show = f" — {e['show']}" if e.get("show") else ""
            lines.append(f"\n{e['name']}{show}")
            lines.append(f"📍 {e['venue']}")
            lines.append(f"📅 {e['date']}{' · ' + e['time'] if e.get('time') else ''}")
            lines.append(f"💰 {e.get('price','Check site')}")
            lines.append(f"🎟  {e.get('url','')}")

    lines.append("\n———")
    lines.append("Powered by Claude x Lucas | Next digest drops Sunday at 7PM ET.")
    return "\n".join(lines)

def send_email(events, start_str, end_str):
    html = build_html_email(events, start_str, end_str)
    plain = build_plain_text(events, start_str, end_str)

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
        json=payload,
        timeout=15
    )

    if resp.status_code in [200, 202]:
        print(f"✅ Email sent to {TO_EMAIL}")
    else:
        raise Exception(f"SendGrid error {resp.status_code}: {resp.text}")

def main():
    print("🔍 Searching top NYC shows from Ticketmaster, SeatGeek, AXS, Dice...")
    week_start, week_end = get_week_range()
    start_str = week_start.strftime("%B %d")
    end_str = week_end.strftime("%B %d, %Y")

    events = fetch_top_shows(week_start, week_end)
    print(f"   Total: {len(events)} events")

    print("📧 Sending via SendGrid...")
    send_email(events, start_str, end_str)

if __name__ == "__main__":
    main()
