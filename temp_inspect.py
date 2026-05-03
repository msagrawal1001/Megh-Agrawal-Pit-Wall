import fastf1
from fastf1._api import SessionNotAvailableError
season = 2026
schedule = fastf1.get_event_schedule(season)
miami = schedule[schedule['EventName'] == 'United States Grand Prix'] if 'United States Grand Prix' in schedule['EventName'].values else schedule[schedule['EventName'].str.contains('Miami', na=False)]
print(miami[['RoundNumber','EventName']].to_dict('records'))
if not miami.empty:
    round_num = int(miami.iloc[0]['RoundNumber'])
    print('round', round_num)
    try:
        s = fastf1.get_session(season, round_num, 'Sprint')
        s.load(laps=True, telemetry=True, weather=False)
        print('results cols', s.results.columns.tolist())
        print('results head', s.results.head(3).to_dict('records'))
        print('lap cols', s.laps.columns.tolist()[:20])
        print('laps head', s.laps.head(3).to_dict('records'))
        if hasattr(s, 'telemetry'):
            print('telemetry cols', list(s.telemetry.columns)[:20])
    except Exception as e:
        print('ERR', e)
