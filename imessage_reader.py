import sqlite3
import subprocess
import os
import re
from datetime import datetime, timedelta

# Only numerical times like 3pm, 10:30am, 3:30, 3 o'clock
TIME_PATTERNS = [
    r'\b\d{1,2}:\d{2}\s*(am|pm)?\b',  # 10:30, 3:30am, 10:30 PM
    r'\b\d{1,2}\s*(am|pm)\b',          # 3pm, 10am, 3 PM
    r'\b\d{1,2}\s*o\'?clock\b',        # 3 o'clock
]
TIME_REGEX = re.compile('|'.join(TIME_PATTERNS), re.IGNORECASE)

# Cache phone -> contact name lookups
_contact_cache = {}

QUESTION_STARTERS = re.compile(
    r'^\s*(are|do|does|did|can|could|will|would|should|is|was|were|have|has|'
    r'what|when|where|who|why|how|wanna|want to|wanna|wyd|you free|you around|'
    r'you down|you up|you good|you want|you wanna)\b',
    re.IGNORECASE
)

def has_specific_time(text):
    return bool(TIME_REGEX.search(text))

def is_affirmative(text):
    """Return True only if the message confirms/states an event, not asks about one."""
    text = text.strip()
    # Skip messages that are questions
    if text.endswith('?'):
        return False
    if QUESTION_STARTERS.match(text):
        return False
    return True

def get_contact_name(phone_number):
    if not phone_number or phone_number == 'Me':
        return phone_number
    if phone_number in _contact_cache:
        return _contact_cache[phone_number]

    # Try multiple number formats to maximize contact matches
    digits = re.sub(r'\D', '', phone_number)
    formats_to_try = list({
        phone_number,                          # +19175175817
        f'+{digits}',                          # +19175175817
        digits,                                # 19175175817
        digits[-10:] if len(digits) >= 10 else digits,  # 9175175817
    })

    try:
        for fmt in formats_to_try:
            script = f'''
            tell application "Contacts"
                set matches to (every person whose value of phones contains "{fmt}")
                if length of matches > 0 then
                    return name of item 1 of matches
                end if
                return ""
            end tell
            '''
            result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=3)
            name = result.stdout.strip()
            if name:
                _contact_cache[phone_number] = name
                return name
    except Exception:
        pass

    # Not in contacts — show shortened number
    digits_only = re.sub(r'\D', '', phone_number)
    short = f"({digits_only[-10:-7]}) {digits_only[-7:-4]}-{digits_only[-4:]}" if len(digits_only) >= 10 else phone_number
    _contact_cache[phone_number] = short
    return short

DB_PATH = os.path.expanduser("~/Library/Messages/chat.db")
APPLE_EPOCH_OFFSET = 978307200  # seconds between Unix epoch (1970) and Apple epoch (2001)


class IMessageReader:
    def is_available(self):
        return os.path.exists(DB_PATH)

    def get_recent_messages(self, hours=24):
        if not self.is_available():
            return []

        cutoff_unix = (datetime.now() - timedelta(hours=hours)).timestamp()
        cutoff_apple_ns = (cutoff_unix - APPLE_EPOCH_OFFSET) * 1e9

        try:
            conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
            cursor = conn.cursor()
            # Include both 1-on-1 and group messages via chat join
            cursor.execute("""
                SELECT m.text, m.is_from_me, m.date, h.id,
                       c.display_name, c.chat_identifier
                FROM message m
                LEFT JOIN handle h ON m.handle_id = h.rowid
                LEFT JOIN chat_message_join cmj ON m.rowid = cmj.message_id
                LEFT JOIN chat c ON cmj.chat_id = c.rowid
                WHERE m.date > ?
                  AND m.text IS NOT NULL
                  AND trim(m.text) != ''
                ORDER BY m.date DESC
                LIMIT 200
            """, (cutoff_apple_ns,))

            seen = set()
            messages = []
            for text, is_from_me, date_val, contact, chat_name, chat_id in cursor.fetchall():
                # Deduplicate (same message can appear via multiple chat joins)
                if text in seen:
                    continue
                seen.add(text)

                # Only include messages with numerical times AND affirmative tone
                if not has_specific_time(text) or not is_affirmative(text):
                    continue

                unix_ts = (date_val / 1e9) + APPLE_EPOCH_OFFSET
                dt = datetime.fromtimestamp(unix_ts)

                # Determine sender display name
                if is_from_me:
                    sender = 'Me'
                else:
                    sender = get_contact_name(contact or 'Unknown')

                # Label group chats
                is_group = chat_name or (chat_id and ',' in str(chat_id))
                group_label = f' (Group: {chat_name})' if chat_name else ' (Group Chat)' if is_group else ''

                messages.append({
                    'source': 'imessage',
                    'from': sender + group_label,
                    'body': text,
                    'date': dt.strftime('%Y-%m-%d %H:%M')
                })
            conn.close()
            return messages

        except PermissionError:
            raise Exception(
                "Cannot read iMessage database. Grant Full Disk Access to Terminal in "
                "System Settings > Privacy & Security > Full Disk Access."
            )
        except Exception as e:
            raise Exception(f"iMessage read error: {e}")
