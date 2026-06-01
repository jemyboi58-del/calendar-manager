import os
import json
import re
import base64
import hashlib
import secrets
from datetime import datetime, timedelta
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

# Patterns that indicate a specific date is mentioned
DATE_PATTERNS = [
    r'\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}\b',  # May 24
    r'\b\d{1,2}[\/\-]\d{1,2}([\/\-]\d{2,4})?\b',           # 05/24, 05-24-2026
    r'\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b',  # day of week
    r'\btomorrow\b',                                           # tomorrow
    r'\bnext\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday|week)\b',  # next Monday
    r'\b\d{4}-\d{2}-\d{2}\b',                                # 2026-05-24
]
DATE_REGEX = re.compile('|'.join(DATE_PATTERNS), re.IGNORECASE)

def has_specific_date(text):
    return bool(DATE_REGEX.search(text))

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
TOKEN_FILE = 'gmail_token.json'
CREDENTIALS_FILE = 'gmail_credentials.json'
REDIRECT_URI = 'http://localhost:8000/auth/gmail/callback'


class GmailReader:
    def __init__(self):
        self.creds = self._load_credentials()

    def _load_credentials(self):
        if not os.path.exists(TOKEN_FILE):
            return None
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                self._save_credentials(creds)
            return creds if creds and creds.valid else None
        except Exception:
            return None

    def _save_credentials(self, creds):
        with open(TOKEN_FILE, 'w') as f:
            f.write(creds.to_json())

    def is_authenticated(self):
        return self.creds is not None and self.creds.valid

    def get_auth_url(self):
        os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

        # Generate PKCE code verifier and challenge manually
        code_verifier = secrets.token_urlsafe(96)
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode()).digest()
        ).rstrip(b'=').decode()

        flow = Flow.from_client_secrets_file(CREDENTIALS_FILE, scopes=SCOPES, redirect_uri=REDIRECT_URI)
        auth_url, state = flow.authorization_url(
            prompt='consent',
            access_type='offline',
            code_challenge=code_challenge,
            code_challenge_method='S256'
        )

        # Save state and code_verifier so they survive across the two requests
        with open('.oauth_state', 'w') as f:
            json.dump({'state': state, 'code_verifier': code_verifier}, f)
        return auth_url

    def exchange_code(self, authorization_response_url):
        os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
        state = None
        code_verifier = None
        if os.path.exists('.oauth_state'):
            with open('.oauth_state') as f:
                saved = json.load(f)
                state = saved.get('state')
                code_verifier = saved.get('code_verifier')
            os.remove('.oauth_state')

        flow = Flow.from_client_secrets_file(
            CREDENTIALS_FILE,
            scopes=SCOPES,
            redirect_uri=REDIRECT_URI,
            state=state
        )
        # Pass the saved code_verifier so Google can verify the PKCE challenge
        flow.fetch_token(
            authorization_response=authorization_response_url,
            code_verifier=code_verifier
        )
        self._save_credentials(flow.credentials)
        self.creds = flow.credentials

    def get_recent_emails(self, hours=24):
        service = build('gmail', 'v1', credentials=self.creds)
        after_ts = int((datetime.now() - timedelta(hours=hours)).timestamp())

        # Include To, CC, and BCC emails — exclude promotions/social/forums
        results = service.users().messages().list(
            userId='me',
            q=f'after:{after_ts} -category:promotions -category:social -category:forums',
            maxResults=50
        ).execute()

        # Labels to skip
        SKIP_LABELS = {'CATEGORY_PROMOTIONS', 'CATEGORY_SOCIAL', 'CATEGORY_FORUMS', 'CATEGORY_UPDATES'}

        # Headers that indicate bulk/promotional email (NOT regular group/CC emails)
        PROMO_HEADERS = {'list-unsubscribe', 'list-id', 'list-post', 'list-help', 'x-mailchimp', 'x-campaign'}

        # Promotional keywords in subject lines
        PROMO_SUBJECTS = [
            'unsubscribe', '% off', 'sale', 'deal', 'offer', 'discount', 'promo',
            'newsletter', 'coupon', 'free shipping', 'limited time', 'act now',
            'don\'t miss', 'click here', 'buy now', 'shop now', 'exclusive',
            'save big', 'special offer', 'flash sale', 'clearance'
        ]

        messages = []
        for msg_ref in results.get('messages', []):
            try:
                msg = service.users().messages().get(
                    userId='me', id=msg_ref['id'], format='full'
                ).execute()

                # Skip by Gmail label
                msg_labels = set(msg.get('labelIds', []))
                if msg_labels & SKIP_LABELS:
                    continue

                headers = {h['name'].lower(): h['value'] for h in msg['payload'].get('headers', [])}

                # Skip if any promotional headers are present
                if any(h in headers for h in PROMO_HEADERS):
                    continue

                # Skip if Precedence is bulk or list
                precedence = headers.get('precedence', '').lower()
                if precedence in ('bulk', 'list', 'junk'):
                    continue

                # Skip if subject contains promotional keywords
                subject = headers.get('subject', '').lower()
                if any(kw in subject for kw in PROMO_SUBJECTS):
                    continue

                # Only include emails that mention a specific date
                body_text = self._extract_body(msg['payload'])
                full_text = subject + ' ' + body_text
                if not has_specific_date(full_text):
                    continue

                cc = headers.get('cc', '')
                to = headers.get('to', '')
                is_group = cc or (to and ',' in to)
                group_label = ' (Group Email)' if is_group else ''

                messages.append({
                    'source': 'email',
                    'from': headers.get('from', '') + group_label,
                    'subject': headers.get('subject', '(no subject)'),
                    'body': body_text[:1500]
                })
            except Exception:
                continue

        return messages

    def _extract_body(self, payload):
        data = payload.get('body', {}).get('data', '')
        if data:
            return base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
        for part in payload.get('parts', []):
            if part.get('mimeType') == 'text/plain':
                d = part.get('body', {}).get('data', '')
                if d:
                    return base64.urlsafe_b64decode(d).decode('utf-8', errors='ignore')
            if part.get('parts'):
                result = self._extract_body(part)
                if result:
                    return result
        return ''
