import json
import os
from datetime import datetime
from anthropic import Anthropic

client = Anthropic()

SYSTEM_PROMPT = """You are a date and time extractor. Given messages (emails and texts), extract ANYTHING that mentions a specific date or time — not just traditional events. This includes:

- Meetings, appointments, calls, and events
- Package and delivery arrivals ("your order arrives Friday")
- Bill and payment due dates ("payment due June 1st")
- Subscription renewals ("renews on the 15th")
- Reminders and tasks with a date/time ("call dentist Monday")
- Reservations and bookings (restaurants, hotels, flights)
- Medication or scheduled reminders ("take at 8pm")
- Ride and service schedules ("your driver arrives at 3pm")
- Deadlines of any kind ("submit by Thursday")
- Any other message where a date or time is mentioned and worth tracking

For each item found, return a JSON object with:
- title: concise descriptive name (string)
- date: ISO date YYYY-MM-DD (string, required)
- start_time: HH:MM 24h format (string or null)
- end_time: HH:MM 24h format (string or null)
- duration_minutes: integer, default 60
- location: location string or null
- description: 1-2 sentence description
- source: "email" or "imessage"
- confidence: "high" | "medium" | "low"
- original_text: the key phrase or sentence that referenced this item

Extraction rules:
- Only extract CONFIRMED events — the message must state or confirm something is happening, not ask about it.
- SKIP messages that are questions, suggestions, or proposals (e.g. "Are we meeting at 3?", "Want to hang out Friday?", "Do you want to do something at 5?").
- INCLUDE messages that confirm a plan (e.g. "See you at 3", "Reservation is Tuesday at 7pm", "Meeting confirmed for 10am").
- Convert relative dates (tomorrow, next Tuesday) to absolute dates using today's date.
- If only a date is mentioned with no time, set start_time to null.
- Return a valid JSON array only. Return [] if nothing confirmed with a date or time is found.
- Do not include duplicate items.

IGNORE these entirely — extract nothing from them:
- Promotional emails (sales, discounts, deals, "limited time offer", "% off", newsletters, unsubscribe)
- Marketing of any kind (product launches, brand announcements, advertising)
- Social media notifications (likes, follows, comments, friend requests)
- Password resets and account verification emails
- Messages with NO date or time mentioned at all"""


class EventParser:
    def extract_events(self, messages):
        if not messages:
            return []

        today = datetime.now().strftime("%Y-%m-%d (%A)")

        blocks = []
        for i, msg in enumerate(messages[:25]):
            if msg['source'] == 'email':
                block = (
                    f"[Email {i+1}]\n"
                    f"From: {msg.get('from', '')}\n"
                    f"Subject: {msg.get('subject', '')}\n"
                    f"{msg.get('body', '')[:800]}"
                )
            else:
                block = (
                    f"[iMessage {i+1} — {msg.get('date', '')}]\n"
                    f"From: {msg.get('from', '')}\n"
                    f"{msg.get('body', '')}"
                )
            blocks.append(block)

        combined = "\n\n---\n\n".join(blocks)

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2048,
            system=[{
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"}
            }],
            messages=[{
                "role": "user",
                "content": (
                    f"Today is {today}.\n\n"
                    f"Messages to analyze:\n\n{combined}\n\n"
                    "Return only a valid JSON array."
                )
            }]
        )

        text = response.content[0].text.strip()

        if "```json" in text:
            text = text.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in text:
            text = text.split("```", 1)[1].split("```", 1)[0].strip()

        try:
            events = json.loads(text)
            return events if isinstance(events, list) else []
        except json.JSONDecodeError:
            return []
