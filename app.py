import os
import json
from typing import Optional
from datetime import datetime

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

load_dotenv()

from calendar_writer import CalendarWriter
from event_parser import EventParser
from gmail_reader import GmailReader
from imessage_reader import IMessageReader

app = FastAPI(title="AutoCal")
templates = Jinja2Templates(directory="templates")

HISTORY_FILE = "event_history.json"


def load_history():
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE) as f:
            return json.load(f)
    except Exception:
        return []


def save_history(entry: dict):
    history = load_history()
    history.insert(0, entry)
    history = history[:200]  # keep last 200
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


class ScanRequest(BaseModel):
    hours: int = 24
    calendar: str = "Home"


class AddEventRequest(BaseModel):
    title: str
    date: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_minutes: int = 60
    location: Optional[str] = None
    description: Optional[str] = None
    calendar: str = "Home"


class ParseMessageRequest(BaseModel):
    source: str
    from_: Optional[str] = None
    subject: Optional[str] = None
    body: str
    date: Optional[str] = None


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/status")
def status():
    gmail = GmailReader()
    imessage = IMessageReader()
    writer = CalendarWriter()
    return {
        "gmail_connected": gmail.is_authenticated(),
        "gmail_credentials_exist": os.path.exists("gmail_credentials.json"),
        "imessage_available": imessage.is_available(),
        "calendars": writer.get_calendars(),
        "anthropic_key_set": bool(os.getenv("ANTHROPIC_API_KEY")),
    }


@app.get("/auth/gmail")
def gmail_auth():
    if not os.path.exists("gmail_credentials.json"):
        return JSONResponse(
            {"error": "gmail_credentials.json not found. See setup instructions."},
            status_code=400,
        )
    reader = GmailReader()
    return RedirectResponse(reader.get_auth_url())


@app.get("/auth/gmail/callback")
def gmail_callback(request: Request, code: str, state: str = None):
    try:
        reader = GmailReader()
        reader.exchange_code(str(request.url))
        return RedirectResponse("/?connected=gmail")
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({"error": str(e), "detail": traceback.format_exc()}, status_code=500)


@app.post("/scan")
def scan(body: ScanRequest):
    messages = []
    errors = []

    gmail = GmailReader()
    if gmail.is_authenticated():
        try:
            messages.extend(gmail.get_recent_emails(hours=body.hours))
        except Exception as e:
            errors.append(f"Gmail: {e}")

    imessage = IMessageReader()
    if imessage.is_available():
        try:
            messages.extend(imessage.get_recent_messages(hours=body.hours))
        except Exception as e:
            errors.append(f"iMessage: {e}")

    if not messages:
        return {"events": [], "messages_scanned": 0, "errors": errors, "messages": []}

    parser = EventParser()
    try:
        events = parser.extract_events(messages)
    except Exception as e:
        errors.append(f"AI parsing: {e}")
        events = []

    return {"events": events, "messages_scanned": len(messages), "errors": errors, "messages": messages}


@app.post("/parse-message")
def parse_message(body: ParseMessageRequest):
    msg = {
        "source": body.source,
        "from": body.from_ or "",
        "subject": body.subject or "",
        "body": body.body,
        "date": body.date or "",
    }
    parser = EventParser()
    events = parser.extract_events([msg])
    if events:
        return {"event": events[0]}
    return {"event": {
        "title": "",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "start_time": None,
        "end_time": None,
        "duration_minutes": 60,
        "location": None,
        "description": body.body[:100],
    }}


@app.post("/add-event")
def add_event(body: AddEventRequest):
    writer = CalendarWriter()
    event = {
        "title": body.title,
        "date": body.date,
        "start_time": body.start_time,
        "end_time": body.end_time,
        "duration_minutes": body.duration_minutes,
        "location": body.location,
        "description": body.description,
    }
    success = writer.add_event(event, calendar_name=body.calendar)
    if success:
        save_history({
            "title": body.title,
            "date": body.date,
            "start_time": body.start_time,
            "end_time": body.end_time,
            "location": body.location,
            "description": body.description,
            "calendar": body.calendar,
            "added_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        })
    return {"success": success}


@app.get("/history")
def get_history():
    return load_history()


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    print(f"Starting AutoCal at http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
