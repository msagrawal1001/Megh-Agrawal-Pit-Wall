import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'temp_f1_race_replay'))

from src.f1_data import get_race_telemetry, load_session, enable_cache
from datetime import datetime

def test():
    enable_cache()
    session = load_session(2024, 1, 'R')
    frames = get_race_telemetry(session, 'R')
    if frames:
        print(f"Frames length: {len(frames)}")
        print(f"Last frame keys: {frames[-1].keys()}")
        print(f"Last frame 't': {frames[-1]['t']}")
        print(f"Can set datetime: {datetime.now()}")
    else:
        print("Frames is empty")

if __name__ == '__main__':
    test()
