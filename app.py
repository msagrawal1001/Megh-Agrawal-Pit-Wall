"""
F1 Pit Wall Dashboard - Backend Server
Uses Fast-F1 to fetch real Formula 1 data and serves it via REST API
"""

from flask import Flask, jsonify, render_template, send_from_directory
from flask_cors import CORS
import fastf1
import fastf1.api as api
from fastf1._api import SessionNotAvailableError
from datetime import datetime, timedelta, timezone
import pandas as pd
import logging
import requests
import re
from html import unescape
from xml.etree import ElementTree as ET

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Enable caching for faster subsequent requests
fastf1.Cache.enable_cache('cache')

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)

# Team color mapping
TEAM_COLORS = {
    'mercedes': '#27F4D2',
    'ferrari': '#E8002D',
    'mclaren': '#FF8000',
    'red_bull': '#3671C6',
    'williams': '#64C4FF',
    'haas': '#B6BABD',
    'alpine': '#0093CC',
    'audi': '#00877C',
    'racing_bulls': '#6692FF',
    'aston_martin': '#229971',
    'cadillac': '#8A9099',
    'sauber': '#00E701',
}

# Driver number to team mapping (2026 season)
DRIVER_TEAMS = {
    # Mercedes
    '12': 'mercedes',  # Antonelli
    '63': 'mercedes',  # Russell
    # Ferrari
    '16': 'ferrari',   # Leclerc
    '44': 'ferrari',   # Hamilton
    # McLaren
    '4': 'mclaren',    # Norris
    '81': 'mclaren',   # Piastri
    # Red Bull
    '1': 'red_bull',   # Verstappen
    '30': 'red_bull',  # Liam Lawson (promoted)
    # Williams
    '2': 'williams',   # Sargeant
    '43': 'williams',  # Franco Colapinto
    # Haas
    '87': 'haas',      # Bearman
    '27': 'haas',      # Hulkenberg
    # Alpine
    '10': 'alpine',    # Gasly
    '31': 'alpine',    # Ocon
    # Audi (Sauber rebranded)
    '24': 'audi',      # Zhou
    '77': 'audi',      # Bottas
    # Racing Bulls
    '22': 'racing_bulls',  # Tsunoda
    '30': 'racing_bulls',  # Lawson (if not at RB)
    # Aston Martin
    '14': 'aston_martin',  # Alonso
    '18': 'aston_martin',  # Stroll
    # Cadillac
    '21': 'cadillac',  # De Vries?
    'XX': 'cadillac',  # Herta (reserve)
}


def get_current_season():
    """Get the current F1 season year"""
    return 2026


def get_next_race():
    """Get information about the next race"""
    try:
        # ---> FIX: Delete the (2026) part and just use the season variable! <---
        season = 2026  # Explicitly lock to current target season
        schedule = fastf1.get_event_schedule(season)
        now = datetime.now()

        for _, race in schedule.iterrows():
            race_date = race['EventDate']
            if hasattr(race_date, 'to_pydatetime'):
                race_date = race_date.to_pydatetime()
            if race_date > now:
                return race
        return None
    except Exception as e:
        logger.error(f"Error getting next race: {e}")
        return None


def get_driver_standings():
    """Get current driver standings"""
    try:
        season = get_current_season()

        def _fetch_standings(round_num=None):
            url = f"https://api.jolpi.ca/ergast/f1/{season}"
            if round_num is not None:
                url += f"/{round_num}"
            url += "/driverStandings.json"

            response = requests.get(url, timeout=10)
            data = response.json()
            standings_lists = data.get('MRData', {}).get('StandingsTable', {}).get('StandingsLists', [])
            return standings_lists[0] if standings_lists else None

        current_list = _fetch_standings()
        if not current_list:
            return []

        current_round = int(current_list.get('round', '0') or '0')
        prev_round = current_round - 1 if current_round > 1 else None
        prev_list = _fetch_standings(prev_round) if prev_round else None

        previous_points = {}
        if prev_list:
            for prev_entry in prev_list.get('DriverStandings', []):
                prev_driver = prev_entry.get('Driver', {})
                prev_code = prev_driver.get('driverId', '').upper()[:3]
                previous_points[prev_code] = float(prev_entry.get('points', '0') or '0')

        standings = []
        for s in current_list.get('DriverStandings', []):
            driver = s.get('Driver', {})
            constructor = s.get('Constructors', [{}])[0] if s.get('Constructors') else {}
            driver_code = driver.get('driverId', '').upper()[:3]
            current_points = float(s.get('points', '0') or '0')
            gained = current_points - previous_points.get(driver_code, 0.0)

            standings.append({
                'position': int(s.get('position', '0')),
                'points': int(current_points) if current_points.is_integer() else round(current_points, 1),
                'wins': int(s.get('wins', '0')),
                'driver_code': driver_code,
                'first_name': driver.get('givenName', ''),
                'last_name': driver.get('familyName', ''),
                'number': driver.get('permanentNumber', ''),
                'team': constructor.get('constructorId', ''),
                'team_name': constructor.get('name', ''),
                'nationality': driver.get('nationality', ''),
                'points_gained': int(gained) if float(gained).is_integer() else round(gained, 1),
            })

        return standings
    except Exception as e:
        logger.error(f"Error getting driver standings: {e}")
        return []


def get_constructor_standings():
    """Get current constructor standings"""
    try:
        import requests
        url = f"https://api.jolpi.ca/ergast/f1/{get_current_season()}/constructorStandings.json"
        response = requests.get(url, timeout=10)
        data = response.json()

        standings = []
        standings_list = data.get('MRData', {}).get('StandingsTable', {}).get('StandingsLists', [])

        if standings_list:
            for s in standings_list[0].get('ConstructorStandings', []):
                constructor = s.get('Constructor', {})
                standings.append({
                    'position': int(s.get('position', '0')),
                    'points': int(s.get('points', '0')),
                    'wins': int(s.get('wins', '0')),
                    'team_id': constructor.get('constructorId', ''),
                    'team_name': constructor.get('name', ''),
                    'nationality': constructor.get('nationality', ''),
                })

        return standings
    except Exception as e:
        logger.error(f"Error getting constructor standings: {e}")
        return []


def get_race_results(round_num=None):
    """Get race results for a specific round or the last completed race"""
    try:
        import requests
        url = f"https://api.jolpi.ca/ergast/f1/{get_current_season()}"
        if round_num:
            url += f"/{round_num}"
        url += "/results.json"

        response = requests.get(url, timeout=10)
        data = response.json()

        races = data.get('MRData', {}).get('RaceTable', {}).get('Races', [])
        if not races:
            return None, []

        race = races[-1]  # Get last race
        results = []

        for r in race.get('Results', []):
            driver = r.get('Driver', {})
            constructor = r.get('Constructor', {})
            results.append({
                'position': int(r.get('position', '0')),
                'points': float(r.get('points', '0')) if r.get('points') else 0,
                'driver_code': driver.get('driverId', '').upper()[:3],
                'first_name': driver.get('givenName', ''),
                'last_name': driver.get('familyName', ''),
                'number': driver.get('permanentNumber', ''),
                'team': constructor.get('constructorId', ''),
                'team_name': constructor.get('name', ''),
                'time': r.get('Time', {}).get('time', r.get('status', '')),
                'grid': int(r.get('grid', '0')),
            })

        return race, results
    except Exception as e:
        logger.error(f"Error getting race results: {e}")
        return None, []


def get_schedule():
    """Get the full race schedule for the season"""
    try:
        import requests
        url = f"https://api.jolpi.ca/ergast/f1/{get_current_season()}.json"
        response = requests.get(url, timeout=10)
        data = response.json()

        races = data.get('MRData', {}).get('RaceTable', {}).get('Races', [])
        schedule = []

        for race in races:
            schedule.append({
                'round': int(race.get('round', '0')),
                'race_name': race.get('raceName', ''),
                'circuit_name': race.get('Circuit', {}).get('circuitName', ''),
                'location': race.get('Circuit', {}).get('Location', {}).get('locality', ''),
                'country': race.get('Circuit', {}).get('Location', {}).get('country', ''),
                'date': race.get('date', ''),
                'time': race.get('time', ''),
            })

        return schedule
    except Exception as e:
        logger.error(f"Error getting schedule: {e}")
        return []


def get_recent_news():
    """Get recent F1 news from public RSS feeds with fallback."""
    fallback_news = [
        {
            'category': 'The Story',
            'headline': 'Championship battle intensifies as season progresses',
            'summary': 'The fight for the title is heating up with multiple contenders in the mix.',
            'url': 'https://www.formula1.com/en/latest.html'
        },
        {
            'category': 'Technical',
            'headline': 'New regulations continue to tighten the field',
            'summary': 'Teams are adapting quickly, and race pace differences remain close.',
            'url': 'https://www.formula1.com/en/latest.html'
        },
        {
            'category': 'Team News',
            'headline': 'Pit stop execution remains a race-defining factor',
            'summary': 'Margins are tiny and operational consistency is making the difference.',
            'url': 'https://www.formula1.com/en/latest.html'
        }
    ]

    def _clean_text(value):
        text = re.sub(r'<[^>]+>', '', unescape(value or ''))
        return re.sub(r'\s+', ' ', text).strip()

    def _to_category(title, summary):
        text = f"{title} {summary}".lower()
        if any(k in text for k in ['upgrade', 'aero', 'floor', 'engine', 'power unit', 'regulation', 'technical']):
            return 'Technical'
        if any(k in text for k in ['mercedes', 'ferrari', 'mclaren', 'red bull', 'aston', 'alpine', 'haas', 'williams', 'sauber', 'audi']):
            return 'Team News'
        if any(k in text for k in ['verstappen', 'hamilton', 'leclerc', 'norris', 'piastri', 'russell', 'alonso']):
            return 'Driver Focus'
        return 'The Story'

    feed_urls = [
        "https://www.formula1.com/en/latest/all.xml",
        "https://www.motorsport.com/rss/f1/news/",
    ]

    for url in feed_urls:
        try:
            response = requests.get(url, timeout=8)
            response.raise_for_status()
            root = ET.fromstring(response.content)
            items = root.findall('.//item')
            news_items = []

            for item in items[:6]:
                title = _clean_text(item.findtext('title', default=''))
                summary = _clean_text(item.findtext('description', default=''))
                if not title:
                    continue
                if not summary:
                    summary = "Tap in for the latest paddock update."
                summary = summary[:180].rstrip() + ('...' if len(summary) > 180 else '')
                news_items.append({
                    'category': _to_category(title, summary),
                    'headline': title,
                    'summary': summary,
                    'url': item.findtext('link', default='').strip()
                })

            if news_items:
                return news_items[:3]
        except Exception as e:
            logger.warning(f"Could not load news feed {url}: {e}")

    return fallback_news


def _as_utc_datetime(value):
    """Convert pandas/timestamp values to UTC naive datetime."""
    if value is None or pd.isna(value):
        return None

    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()

    if isinstance(value, datetime):
        # FastF1 UTC columns are tz-aware; convert to UTC-naive.
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    return None


def _format_timedelta(value, with_sign=False):
    """Format timedelta values to motorsport-style timing strings."""
    if value is None or pd.isna(value):
        return ""

    if hasattr(value, "to_pytimedelta"):
        value = value.to_pytimedelta()

    if not isinstance(value, timedelta):
        return str(value)

    total_ms = int(round(value.total_seconds() * 1000))
    sign = ""
    if total_ms < 0:
        sign = "-"
        total_ms = abs(total_ms)
    elif with_sign:
        sign = "+"

    minutes, rem_ms = divmod(total_ms, 60_000)
    seconds, millis = divmod(rem_ms, 1000)
    return f"{sign}{minutes}:{seconds:02d}.{millis:03d}" if minutes > 0 else f"{sign}{seconds}.{millis:03d}"


def _get_jolpi_session_classification(round_number, event_name, session_name):
    """Fallback classification from Jolpi/Ergast when FastF1 lacks official positions."""
    try:
        season = 2026
        session_key = (session_name or "").strip().lower()

        if session_key == "sprint":
            attempts = [("sprint.json", "SprintResults"), ("results.json", "Results")]
        elif session_key == "race":
            attempts = [("results.json", "Results")]
        elif session_key in {"qualifying", "sprint qualifying", "sprint shootout"}:
            attempts = [("qualifying.json", "QualifyingResults")]
        else:
            attempts = []

        race = None
        rows = []
        results_key = ""
        for endpoint, key in attempts:
            url = f"https://api.jolpi.ca/ergast/f1/{season}/{round_number}/{endpoint}"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            payload = response.json()
            races = payload.get("MRData", {}).get("RaceTable", {}).get("Races", [])
            if not races:
                continue
            probe_race = races[0]
            probe_rows = probe_race.get(key, [])
            if probe_rows:
                race = probe_race
                rows = probe_rows
                results_key = key
                break

        if not race or not rows:
            return None

        def _pos_num(item):
            try:
                return int(item.get("position", "9999"))
            except Exception:
                return 9999

        rows = sorted(rows, key=_pos_num)
        classification = []

        for row in rows:
            driver = row.get("Driver", {})
            constructor = row.get("Constructor", {})
            pos = _pos_num(row)
            if pos == 9999:
                continue

            if results_key == "QualifyingResults":
                q3 = row.get("Q3", "")
                q2 = row.get("Q2", "")
                q1 = row.get("Q1", "")
                result_text = q3 or q2 or q1 or "—"
                gap = ""
                time_val = result_text
                status_text = ""
            else:
                time_val = row.get("Time", {}).get("time", "") or ""
                status_text = row.get("status", "") or ""
                gap = ""
                if pos > 1 and time_val.startswith("+"):
                    gap = time_val
                result_text = gap or time_val or status_text or "—"

            classification.append({
                "position": pos,
                "driver_code": driver.get("driverId", "").upper()[:3],
                "first_name": driver.get("givenName", ""),
                "last_name": driver.get("familyName", ""),
                "team_name": constructor.get("name", ""),
                "time": time_val,
                "gap": gap,
                "status": status_text,
                "result_text": result_text,
            })

        if not classification:
            return None

        return {
            "round": int(round_number),
            "event_name": race.get("raceName", event_name or ""),
            "session_name": session_name,
            "session_datetime_utc": "",
            "classification": classification
        }
    except Exception as e:
        logger.info(f"Jolpi fallback failed for round {round_number} {session_name}: {e}")
        return None


def calculate_session_points(classification, session_name):
    """Calculate points for a session classification."""
    if 'race' in session_name.lower():
        points = [25, 18, 15, 12, 10, 8, 6, 4, 2, 1]
    elif 'sprint' in session_name.lower():
        points = [8, 7, 6, 5, 4, 3, 2, 1]
    else:
        return {}

    driver_points = {}
    for i, driver in enumerate(classification):
        if i < len(points):
            driver_points[driver['driver_code']] = points[i]
    return driver_points


def get_current_weekend_session_classification():
    """
    Get the latest completed session classification for the currently active GP weekend.
    Returns session metadata and full classification (position, driver, time/gap).
    """
    try:
        season = 2026  # Explicitly use 2026 season data for weekend session lookup
        schedule = fastf1.get_event_schedule(season)
        if schedule is None or schedule.empty:
            return None

        now_utc = datetime.utcnow()
        active_candidates = []

        for _, event in schedule.iterrows():
            round_number = int(event.get("RoundNumber", 0) or 0)
            if round_number <= 0:
                continue

            session_slots = []
            for i in range(1, 6):
                session_name = event.get(f"Session{i}")
                session_dt = _as_utc_datetime(event.get(f"Session{i}DateUtc")) or _as_utc_datetime(event.get(f"Session{i}Date"))
                if session_name:
                    session_slots.append({"name": session_name, "dt": session_dt})

            if not session_slots:
                continue

            dated_slots = [s["dt"] for s in session_slots if s["dt"] is not None]
            if not dated_slots:
                continue

            weekend_start = min(dated_slots) - timedelta(hours=18)
            weekend_end = max(dated_slots) + timedelta(hours=18)
            event_date = _as_utc_datetime(event.get("EventDate")) or max(dated_slots)
            distance = abs((event_date - now_utc).total_seconds())

            if weekend_start <= now_utc <= weekend_end:
                active_candidates.append((distance, event, session_slots))

        if not active_candidates:
            return None

        active_candidates.sort(key=lambda x: x[0])
        _, active_event, session_slots = active_candidates[0]
        round_number = int(active_event.get("RoundNumber", 0) or 0)

        session_map = {}
        for s in session_slots:
            if s["name"] not in session_map:
                session_map[s["name"]] = s

        # FORCE SESSION TYPE: Prioritize race session only
        if "Sprint" in session_map:
            probe_names = ["Sprint"]
        else:
            probe_names = ["Race"]

        probe_sessions = [session_map[name] for name in probe_names if name in session_map]

        chosen_session_name = None
        chosen_session_dt = None
        chosen_results = None

        # 1. FORCE SESSION TYPE: Try race session first
        for candidate in probe_sessions:
            try:
                session = fastf1.get_session(season, round_number, candidate["name"])
                session.load(laps=False, telemetry=False, weather=False)
                results = session.results
                if results is not None and not results.empty:
                    # 2. STOP FASTEST LAP SORTING: Check official classification columns
                    pos_cols = ['Position', 'ClassifiedPosition', 'GridPosition']
                    has_ordering = any(results[col].notna().any() for col in pos_cols if col in results.columns)
                    if has_ordering:
                        chosen_session_name = candidate["name"]
                        chosen_session_dt = candidate["dt"]
                        chosen_results = results.copy()
                        break
                    else:
                        # 3. FASTF1 TIMING FALLBACK: Use provisional order from telemetry
                        chosen_session_name = candidate["name"]
                        chosen_session_dt = candidate["dt"]
                        chosen_results = results.copy()
                        break
            except SessionNotAvailableError:
                # 7. ERROR HANDLING: Session not available, skip to fallback
                continue
            except Exception as e:
                logger.info(f"Failed to load {candidate['name']}: {e}")
                continue

        # 7. ERROR HANDLING: If race not available, fall back to most recent completed session
        if chosen_results is None:
            quali_candidates = ["Sprint Qualifying", "Qualifying", "Sprint Shootout"]
            for quali in quali_candidates:
                if quali in session_map:
                    try:
                        session = fastf1.get_session(season, round_number, quali)
                        session.load(laps=False, telemetry=False, weather=False)
                        results = session.results
                        if results is not None and not results.empty:
                            chosen_session_name = f"{quali} (QUALIFYING RESULTS)"
                            chosen_session_dt = session_map[quali]["dt"]
                            chosen_results = results.copy()
                            break
                    except Exception as e:
                        logger.info(f"Failed to load fallback {quali}: {e}")
                        continue

        # 4. HANDLE MISSING DATA: If still no data, return awaiting message
        if chosen_results is None:
            return {
                "status": "awaiting_results",
                "message": "FIA Official Classification Pending..."
            }

        # 2. STOP FASTEST LAP SORTING: Use official classification columns
        pos_col = None
        for col in ['Position', 'ClassifiedPosition', 'GridPosition']:
            if col in chosen_results.columns and chosen_results[col].notna().any():
                pos_col = col
                break

        if pos_col:
            chosen_results["PositionNum"] = pd.to_numeric(chosen_results[pos_col], errors="coerce")
            valid_results = chosen_results[chosen_results["PositionNum"].notna()].copy()
            if not valid_results.empty:
                chosen_results = valid_results.sort_values("PositionNum", na_position="last")
            else:
                # Fallback to sorting
                chosen_results["PositionNum"] = range(1, len(chosen_results) + 1)
        else:
            # 3. FASTF1 TIMING FALLBACK: No official positions, sort by fastest lap or driver number
            if "FastestLapTime" in chosen_results.columns:
                chosen_results = chosen_results.sort_values("FastestLapTime", na_position="last")
            else:
                chosen_results = chosen_results.sort_values("DriverNumber", na_position="last")
            chosen_results["PositionNum"] = range(1, len(chosen_results) + 1)

        leader_time = None
        if "Time" in chosen_results.columns:
            leader_rows = chosen_results[chosen_results["PositionNum"] == 1]
            if not leader_rows.empty and pd.notna(leader_rows.iloc[0].get("Time")):
                leader_time = leader_rows.iloc[0].get("Time")

        classification = []
        for _, row in chosen_results.iterrows():
            pos_num = row.get("PositionNum")
            pos = int(pos_num) if pd.notna(pos_num) else None
            first_name = row.get("FirstName", "") or ""
            last_name = row.get("LastName", "") or ""
            if (not first_name and not last_name) and row.get("FullName"):
                split_name = str(row.get("FullName", "")).split(" ", 1)
                first_name = split_name[0]
                last_name = split_name[1] if len(split_name) > 1 else ""

            session_time = row.get("Time")
            time_display = _format_timedelta(session_time)
            status_text = str(row.get("Status", "") or "").strip()

            gap_display = ""
            if pos and pos > 1:
                if pd.notna(row.get("GapToLeader")):
                    gap_display = str(row.get("GapToLeader"))
                    if gap_display and not gap_display.startswith("+"):
                        gap_display = f"+{gap_display}"
                elif pd.notna(session_time) and leader_time is not None:
                    gap_display = _format_timedelta(session_time - leader_time, with_sign=True)

            result_text = gap_display or time_display or status_text
            if not result_text:
                result_text = "—"

            classification.append({
                "position": pos,
                "driver_code": row.get("Abbreviation", "") or "",
                "first_name": first_name,
                "last_name": last_name,
                "team_name": row.get("TeamName", "") or "",
                "time": time_display,
                "gap": gap_display,
                "status": status_text,
                "result_text": result_text,
            })

        session_dt_text = chosen_session_dt.isoformat() if chosen_session_dt else ""
        return {
            "round": round_number,
            "event_name": active_event.get("EventName", ""),
            "session_name": chosen_session_name,
            "session_datetime_utc": session_dt_text,
            "classification": classification
        }
    except Exception as e:
        logger.warning(f"Could not load current weekend session classification: {e}")
        return None


@app.route('/')
def index():
    """Serve the main dashboard"""
    return send_from_directory('.', 'index.html')


@app.route('/api/dashboard')
def get_dashboard_data():
    """Get all dashboard data in one call"""
    try:
        next_race = get_next_race()
        driver_standings = get_driver_standings()
        constructor_standings = get_constructor_standings()
        last_race, race_results = get_race_results()
        schedule = get_schedule()
        news = get_recent_news()
        current_weekend_grid = get_current_weekend_session_classification()

        # Add session points to driver standings if session is completed
        if current_weekend_grid and current_weekend_grid.get('classification'):
            session_points = calculate_session_points(current_weekend_grid['classification'], current_weekend_grid['session_name'])
            for standing in driver_standings:
                code = standing['driver_code']
                if code in session_points:
                    standing['points'] += session_points[code]
                    standing['points_gained'] = session_points[code]
            # Sort by updated points
            driver_standings.sort(key=lambda x: x['points'], reverse=True)
            # Reassign positions
            for i, standing in enumerate(driver_standings, 1):
                standing['position'] = i

        # Calculate countdown to next race
        countdown = None
        if next_race is not None:
            try:
                race_date = next_race.get('EventDate')
                if hasattr(race_date, 'to_pydatetime'):
                    race_date = race_date.to_pydatetime()
                diff = race_date - datetime.now()
                if diff.total_seconds() > 0:
                    countdown = {
                        'days': diff.days,
                        'hours': diff.seconds // 3600,
                        'minutes': (diff.seconds % 3600) // 60,
                        'seconds': diff.seconds % 60
                    }
            except:
                pass

        has_next_race = next_race is not None

        return jsonify({
            'success': True,
            'data': {
                'next_race': {
                    'round': next_race.get('EventFormat', '4') if has_next_race else '4',
                    'name': next_race.get('EventName', 'Miami Grand Prix') if has_next_race else 'Miami Grand Prix',
                    'circuit': next_race.get('CircuitName', 'Miami International Autodrome') if has_next_race else 'Miami International Autodrome',
                    'location': next_race.get('Location', 'Miami') if has_next_race else 'Miami',
                    'date': next_race.get('EventDate', '2026-05-03') if has_next_race else '2026-05-03',
                } if has_next_race else {},
                'countdown': countdown,
                'driver_standings': driver_standings[:10],  # Top 10
                'constructor_standings': constructor_standings,
                'race_results': race_results[:3],  # Podium
                'last_race': last_race,
                'schedule': schedule,
                'news': news,
                'current_weekend_grid': current_weekend_grid,
            }
        })
    except Exception as e:
        logger.error(f"Error getting dashboard data: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/full_results')
def get_full_results():
    """Get complete finishing order with gaps and points"""
    try:
        grid = get_current_weekend_session_classification()
        if not grid:
            return jsonify({'success': False, 'message': 'No data available'})

        classification = grid['classification']
        session_points = calculate_session_points(classification, grid['session_name'])

        # Add points to each driver
        for driver in classification:
            driver['points'] = session_points.get(driver['driver_code'], 0)

        return jsonify({
            'success': True,
            'data': grid
        })
    except Exception as e:
        logger.error(f"Error getting full results: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/drivers')
def api_drivers():
    """Get driver standings"""
    return jsonify(get_driver_standings())


@app.route('/api/constructors')
def api_constructors():
    """Get constructor standings"""
    return jsonify(get_constructor_standings())


@app.route('/api/schedule')
def api_schedule():
    """Get race schedule"""
    return jsonify(get_schedule())


@app.route('/api/results/<int:round_num>')
def api_results(round_num):
    """Get race results for specific round"""
    race, results = get_race_results(round_num)
    return jsonify({'race': race, 'results': results})


@app.route('/api/next-race')
def api_next_race():
    """Get next race information"""
    return jsonify(get_next_race())


if __name__ == '__main__':
    print("=" * 50)
    print("F1 Pit Wall Dashboard Server")
    print("=" * 50)
    print("Starting server on http://localhost:5000")
    print("API endpoints:")
    print("  GET /api/dashboard    - All dashboard data")
    print("  GET /api/drivers      - Driver standings")
    print("  GET /api/constructors - Constructor standings")
    print("  GET /api/schedule     - Race schedule")
    print("  GET /api/results/<n>  - Race results for round n")
    print("  GET /api/next-race    - Next race info")
    print("=" * 50)
    app.run(debug=True, host='0.0.0.0', port=5000)
