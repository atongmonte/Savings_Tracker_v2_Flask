"""
Timezone utilities. All application timestamps use US Eastern time.
"""
try:
    from zoneinfo import ZoneInfo  # Python 3.9+
    _EASTERN = ZoneInfo('America/New_York')
except ImportError:
    import pytz
    _EASTERN = pytz.timezone('America/New_York')

from datetime import datetime


def now_eastern() -> datetime:
    """Return the current time in US Eastern (America/New_York), timezone-aware."""
    return datetime.now(_EASTERN)
