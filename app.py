"""
F1 Pit Wall Dashboard - Backend Server
Uses Fast-F1 to fetch real Formula 1 data and serves it via REST API
"""

from flask import Flask, jsonify, render_template, send_from_directory
from flask_cors import CORS
import fastf1
import fastf1.api as api
from datetime import datetime, timedelta
import pandas as pd
import logging

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
        schedule = fastf1.get_event_schedule(get_current_season())
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
        # Use Ergast API through FastF1 for standings
        import requests
        url = f"https://api.jolpi.ca/ergast/f1/{get_current_season()}/driverStandings.json"
        response = requests.get(url, timeout=10)
        data = response.json()

        standings = []
        standings_list = data.get('MRData', {}).get('StandingsTable', {}).get('StandingsLists', [])

        if standings_list:
            for s in standings_list[0].get('DriverStandings', []):
                driver = s.get('Driver', {})
                constructor = s.get('Constructors', [{}])[0] if s.get('Constructors') else {}
                standings.append({
                    'position': int(s.get('position', '0')),
                    'points': int(s.get('points', '0')),
                    'wins': int(s.get('wins', '0')),
                    'driver_code': driver.get('driverId', '').upper()[:3],
                    'first_name': driver.get('givenName', ''),
                    'last_name': driver.get('familyName', ''),
                    'number': driver.get('permanentNumber', ''),
                    'team': constructor.get('constructorId', ''),
                    'team_name': constructor.get('name', ''),
                    'nationality': driver.get('nationality', ''),
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
    """Get recent F1 news (simulated for now)"""
    # In production, this would fetch from an F1 news API
    return [
        {
            'category': 'The Story',
            'headline': 'Championship battle intensifies as season progresses',
            'summary': 'The fight for the 2026 championship is heating up with multiple contenders.'
        },
        {
            'category': 'Technical',
            'headline': 'New regulations show competitive racing',
            'summary': 'The 2026 technical regulations are delivering on the promise of closer racing.'
        },
        {
            'category': 'Team News',
            'headline': 'Pit stop performance becomes key differentiator',
            'summary': 'Teams are finding marginal gains through optimized pit stop strategies.'
        }
    ]


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
            }
        })
    except Exception as e:
        logger.error(f"Error getting dashboard data: {e}")
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
