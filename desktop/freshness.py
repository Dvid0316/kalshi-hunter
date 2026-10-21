"""Data freshness and connection-state model (Phase 5 groundwork, no network).

Two independent questions the UI must always answer honestly:

1. How old is the data on screen?          -> ``classify``
2. Where does the data come from and is
   that source reachable?                  -> ``ConnectionState`` / ``next_state``

Today the only source is an *archived offline snapshot*, so ``source='archive'`` is
never labelled LIVE no matter how recent it is. A live feed (Phase 5, needs approval)
would use ``source='feed'`` and the same policy. Pure functions only so everything is
unit-testable with an injected clock.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .formatting import age_text

# Thresholds (seconds). Chosen to mirror OPERATIONS.md: the cloud scanner cycles every
# 300 s and is "unhealthy" after 15 min without a successful scan.
SCAN_INTERVAL_S = 300
FRESH_MAX_S = 2 * SCAN_INTERVAL_S      # up to two missed cycles is still current
STALE_MAX_S = 3 * 900                  # 45 min: past this a feed is considered dead, not merely late
QUOTE_EXECUTABLE_MAX_S = 60            # a quote older than this is not presented as executable
MARK_MAX_S = 5 * 60                    # unrealised P&L marks require a quote no older than this


class Level(str, Enum):
    LIVE = 'live'            # feed source, within FRESH_MAX_S
    DELAYED = 'delayed'      # feed source, late but not dead
    STALE = 'stale'          # feed source, older than STALE_MAX_S
    ARCHIVED = 'archived'    # offline snapshot: never live regardless of age
    UNAVAILABLE = 'unavailable'


@dataclass(frozen=True)
class Freshness:
    level: Level
    age_s: float | None
    label: str       # short badge text
    detail: str      # one-sentence explanation
    warn: bool       # True when the user should not treat the data as current


def classify(asof_ts, now, source: str = 'archive') -> Freshness:
    if asof_ts is None:
        return Freshness(Level.UNAVAILABLE, None, 'NO DATA', 'No timestamp is available for this data.', True)
    age = max(0.0, float(now) - float(asof_ts))
    text = age_text(age)
    if source == 'archive':
        return Freshness(Level.ARCHIVED, age, f'ARCHIVED · {text} old',
                         f'Offline snapshot captured {text} ago. It is not a live feed and does not update.',
                         True)
    if age <= FRESH_MAX_S:
        return Freshness(Level.LIVE, age, f'LIVE · {text}', f'Last update {text} ago.', False)
    if age <= STALE_MAX_S:
        return Freshness(Level.DELAYED, age, f'DELAYED · {text}', f'No update for {text}; the source may be lagging.', True)
    return Freshness(Level.STALE, age, f'STALE · {text}', f'No update for {text}. Treat prices as historical.', True)


def quote_executable(quote_ts, now, source: str = 'archive') -> bool:
    """May this quote be presented as currently executable? Archived quotes never are."""
    if source == 'archive' or quote_ts is None:
        return False
    return 0 <= now - quote_ts <= QUOTE_EXECUTABLE_MAX_S


def mark_usable(quote_ts, now, source: str = 'archive') -> bool:
    """May this quote mark an open position for *unrealised* P&L? Fail closed."""
    if source == 'archive' or quote_ts is None:
        return False
    return 0 <= now - quote_ts <= MARK_MAX_S


# --------------------------------------------------------------------------------------
# Connection state machine (consumer side of a future read-only feed)

class ConnectionState(str, Enum):
    NOT_CONFIGURED = 'not_configured'   # today's state: no feed exists
    CONNECTING = 'connecting'
    CONNECTED = 'connected'
    RECONNECTING = 'reconnecting'
    STALE = 'stale'                     # connected but silent for too long
    ERROR = 'error'                     # permanent failure, needs the user


class Event(str, Enum):
    CONFIGURE = 'configure'
    CONNECT_OK = 'connect_ok'
    CONNECT_FAIL = 'connect_fail'
    DATA = 'data'
    TIMEOUT = 'timeout'                 # silence exceeded STALE_MAX_S
    DISCONNECT = 'disconnect'
    FATAL = 'fatal'                     # e.g. bad credentials/schema: do not retry blindly
    RESET = 'reset'


_TRANSITIONS = {
    (ConnectionState.NOT_CONFIGURED, Event.CONFIGURE): ConnectionState.CONNECTING,
    (ConnectionState.CONNECTING, Event.CONNECT_OK): ConnectionState.CONNECTED,
    (ConnectionState.CONNECTING, Event.CONNECT_FAIL): ConnectionState.RECONNECTING,
    (ConnectionState.RECONNECTING, Event.CONNECT_OK): ConnectionState.CONNECTED,
    (ConnectionState.RECONNECTING, Event.CONNECT_FAIL): ConnectionState.RECONNECTING,
    (ConnectionState.CONNECTED, Event.DATA): ConnectionState.CONNECTED,
    (ConnectionState.CONNECTED, Event.TIMEOUT): ConnectionState.STALE,
    (ConnectionState.CONNECTED, Event.DISCONNECT): ConnectionState.RECONNECTING,
    (ConnectionState.STALE, Event.DATA): ConnectionState.CONNECTED,
    (ConnectionState.STALE, Event.DISCONNECT): ConnectionState.RECONNECTING,
}


def next_state(state: ConnectionState, event: Event) -> ConnectionState:
    """Pure transition. Unknown pairs keep the state (never raise inside a UI path)."""
    if event is Event.FATAL:
        return ConnectionState.ERROR
    if event is Event.RESET:
        return ConnectionState.NOT_CONFIGURED
    return _TRANSITIONS.get((state, event), state)


def backoff_seconds(attempt: int, *, base: float = 2.0, cap: float = 300.0) -> float:
    """Exponential reconnect delay without jitter (caller adds jitter). attempt starts at 1."""
    if attempt < 1:
        return 0.0
    return float(min(cap, base * (2 ** (attempt - 1))))


STATE_TEXT = {
    ConnectionState.NOT_CONFIGURED: ('NO LIVE FEED', 'No live research feed is configured. The app shows an archived snapshot only.'),
    ConnectionState.CONNECTING: ('CONNECTING', 'Opening the read-only research feed.'),
    ConnectionState.CONNECTED: ('CONNECTED', 'Receiving the read-only research feed.'),
    ConnectionState.RECONNECTING: ('RECONNECTING', 'Connection lost; retrying with backoff. Showing the last received data.'),
    ConnectionState.STALE: ('STALE', 'Connected but silent. Treat displayed data as historical.'),
    ConnectionState.ERROR: ('ERROR', 'The feed reported a permanent error. Automatic retries are paused.'),
}
