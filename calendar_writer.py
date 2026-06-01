import os
import subprocess
import tempfile
from datetime import datetime, timedelta


class CalendarWriter:
    def get_calendars(self):
        script = '''tell application "Calendar"
    set output to ""
    repeat with c in calendars
        if output is "" then
            set output to name of c
        else
            set output to output & "|||" & name of c
        end if
    end repeat
    return output
end tell'''
        result = self._run_applescript(script)
        if result and result.strip():
            return [c.strip() for c in result.split('|||') if c.strip()]
        return ["Home"]

    def add_event(self, event, calendar_name="Home"):
        title = self._sanitize(event.get('title') or 'Untitled Event')
        date = event.get('date')
        start_time = event.get('start_time') or '09:00'
        end_time = event.get('end_time')
        duration = int(event.get('duration_minutes') or 60)
        location = self._sanitize(event.get('location') or '')
        description = self._sanitize(event.get('description') or '')
        cal_name = self._sanitize(calendar_name)

        if not date:
            return False

        try:
            start_dt = datetime.strptime(f"{date} {start_time}", "%Y-%m-%d %H:%M")
        except ValueError:
            try:
                start_dt = datetime.strptime(date, "%Y-%m-%d").replace(hour=9, minute=0)
            except ValueError:
                return False

        if end_time:
            try:
                end_dt = datetime.strptime(f"{date} {end_time}", "%Y-%m-%d %H:%M")
            except ValueError:
                end_dt = start_dt + timedelta(minutes=duration)
        else:
            end_dt = start_dt + timedelta(minutes=duration)

        script = f'''tell application "Calendar"
    set targetCal to missing value
    repeat with c in calendars
        if name of c is "{cal_name}" then
            set targetCal to c
            exit repeat
        end if
    end repeat
    if targetCal is missing value then set targetCal to first calendar
    tell targetCal
        set sDate to current date
        set year of sDate to {start_dt.year}
        set month of sDate to {start_dt.month}
        set day of sDate to {start_dt.day}
        set hours of sDate to {start_dt.hour}
        set minutes of sDate to {start_dt.minute}
        set seconds of sDate to 0
        set eDate to current date
        set year of eDate to {end_dt.year}
        set month of eDate to {end_dt.month}
        set day of eDate to {end_dt.day}
        set hours of eDate to {end_dt.hour}
        set minutes of eDate to {end_dt.minute}
        set seconds of eDate to 0
        make new event at end of events with properties {{summary:"{title}", start date:sDate, end date:eDate, location:"{location}", description:"{description}"}}
    end tell
end tell'''

        return self._run_applescript(script) is not None

    def _sanitize(self, s):
        if not s:
            return ''
        return str(s).replace('"', "'").replace('\\', '').replace('\n', ' ').replace('\r', ' ')

    def _run_applescript(self, script):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.applescript', delete=False, encoding='utf-8') as f:
            f.write(script)
            fname = f.name
        try:
            result = subprocess.run(['osascript', fname], capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip() or ''
            print(f"AppleScript error: {result.stderr.strip()}")
            return None
        finally:
            os.unlink(fname)
