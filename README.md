# NYC Live Music Weekly Digest — Setup Guide

Every Sunday at 7PM ET, this script:
1. Pulls all NYC concert data from SeatGeek
2. Sends it to Claude to filter and format
3. Emails a clean digest to lucasfearn1@gmail.com

---

## Step 1 — Get your Anthropic API Key

1. Go to https://console.anthropic.com
2. Sign in or create an account
3. Click "API Keys" → "Create Key"
4. Copy the key — save it somewhere safe

---

## Step 2 — Set up Gmail App Password

You need a special password so the script can send email FROM your Gmail.

1. Go to https://myaccount.google.com/security
2. Make sure 2-Step Verification is ON
3. Search "App Passwords" at the top
4. Select app: "Mail" → Select device: "Other" → name it "NYC Digest"
5. Copy the 16-character password it gives you

---

## Step 3 — Deploy on Railway (free)

1. Go to https://railway.app and sign up with GitHub
2. Click "New Project" → "Deploy from GitHub repo"
   - If you don't have this on GitHub yet, create a free GitHub account,
     make a new repo called "nyc-digest", and upload these 3 files:
     - digest.py
     - requirements.txt
     - railway.toml
3. Once deployed, go to your project → "Variables" tab
4. Add these 3 environment variables:

   ANTHROPIC_API_KEY   = sk-ant-... (your key from Step 1)
   GMAIL_ADDRESS       = your.gmail@gmail.com (the Gmail you send FROM)
   GMAIL_APP_PASSWORD  = xxxx xxxx xxxx xxxx (from Step 2)

5. Railway will automatically run the script every Sunday at 7PM ET
   (the railway.toml cron "0 23 * * 0" = 11PM UTC = 7PM ET)

---

## Step 4 — Test it manually

In Railway, go to your project → click "Deploy" → "Trigger Deploy"
Check lucasfearn1@gmail.com — digest should arrive within 60 seconds.

---

## Cost estimate

- Railway: Free tier covers this easily (~$0/month)
- Anthropic API: ~$0.05–0.10 per weekly run (~$0.25/month)
- Total: essentially free

---

## Troubleshooting

- No email received? Check spam folder first
- Gmail auth error? Make sure App Password is correct and 2FA is on
- No events showing? SeatGeek API occasionally rate-limits — just re-run
