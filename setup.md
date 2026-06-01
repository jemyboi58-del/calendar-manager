# Calendar Manager — Setup

## Requirements
- macOS (iMessage + Apple Calendar only work on Mac)
- Python 3.11+
- An Anthropic API key

## 1. Install dependencies

```bash
cd ~/calendar-manager
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 2. Set your Anthropic API key

```bash
cp .env.example .env
```

Edit `.env` and paste your key:
```
ANTHROPIC_API_KEY=sk-ant-...
```

## 3. Set up Gmail access

1. Go to https://console.cloud.google.com/ and create a project (or use an existing one)
2. Enable the Gmail API: **APIs & Services → Library → Gmail API → Enable**
3. Create OAuth credentials: **APIs & Services → Credentials → Create Credentials → OAuth Client ID**
   - Application type: **Web application**
   - Authorized redirect URI: `http://localhost:8000/auth/gmail/callback`
4. Download the JSON file and save it as **`gmail_credentials.json`** in this folder
5. Run the app and click **Connect Gmail**

## 4. Grant iMessage access (Full Disk Access)

1. Open **System Settings → Privacy & Security → Full Disk Access**
2. Click **+** and add your **Terminal** app (or iTerm2, or whichever terminal you use)
3. Restart Terminal

## 5. Run the app

```bash
source venv/bin/activate
python app.py
```

Open http://localhost:8000 in your browser.

---

## Security

This project uses a `.gitignore` to prevent sensitive files from being committed to git:

- `.env` — contains your Anthropic API key
- `gmail_credentials.json` — contains your Google OAuth client secret
- `gmail_token.json` — contains your Gmail access token

**Never share or commit these files.** If you accidentally push them, rotate your keys immediately.

---

## Troubleshooting

**"gmail_credentials.json not found"** — follow step 3 above.

**"Full Disk Access needed"** — follow step 4. The terminal process needs it, not just the app.

**"ANTHROPIC_API_KEY missing"** — check your `.env` file has the key and the file is saved.

**Event not added to Calendar** — make sure Calendar.app is running and not in a restricted sandbox mode. If you see a permission dialog, click Allow.
