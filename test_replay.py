import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'temp_f1_race_replay'))

from src.f1_data import get_race_telemetry, load_session, enable_cache
import fastf1

def test():
    enable_cache()
    # Loading 2024 Round 1 just to see if the function works
    # Using 2024 since 2026 data does not exist in fastf1
    session = load_session(2024, 1, 'R')
    
    # We will test if get_race_telemetry works.
    # It might take a long time to compute. Let's see.
    # Actually, let's just see if the import works.
    print(f"Successfully loaded session: {session.event['EventName']}")
    # frames = get_race_telemetry(session, "R")
    # print(f"Computed {len(frames)} frames")

if __name__ == '__main__':
    test()
