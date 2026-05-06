"""
Simple replay data extractor - bypasses the complex f1_data.py pipeline.
Uses FastF1 directly to extract position data for all drivers.
Saves lightweight JSON for instant loading in app.py.

Usage: python precompute_replay.py [year] [round]
"""

import sys
import os
import json
import time
import numpy as np
import fastf1

fastf1.Cache.enable_cache('cache')

def precompute(year=2024, round_num=1):
    print(f"=== Pre-computing replay: {year} Round {round_num} ===")
    start = time.time()
    
    print("Loading session...")
    session = fastf1.get_session(year, round_num, 'R')
    session.load(telemetry=True, weather=True, messages=True)
    
    event_name = str(session.event['EventName'])
    print(f"Session: {event_name}")
    
    laps = session.laps
    drivers = session.drivers
    print(f"Found {len(drivers)} drivers")
    
    # Get the fastest lap to extract track shape
    fastest = laps.pick_fastest()
    track_tel = fastest.get_telemetry()
    track_x = track_tel['X'].values.tolist()
    track_y = track_tel['Y'].values.tolist()
    
    # Determine race duration from laps
    all_times = []
    driver_telemetry = {}
    
    for drv in drivers:
        drv_laps = laps.pick_drivers(drv)
        if drv_laps.empty:
            continue
        
        try:
            tel = drv_laps.get_telemetry()
        except Exception as e:
            print(f"  Skipping driver {drv}: {e}")
            continue
        
        if tel.empty or 'X' not in tel.columns:
            continue
        
        # Get driver code
        drv_info = session.get_driver(drv)
        code = drv_info.get('Abbreviation', str(drv)) if isinstance(drv_info, dict) else getattr(drv_info, 'Abbreviation', str(drv))
        
        # Convert SessionTime to seconds
        times = tel['SessionTime'].dt.total_seconds().values
        xs = tel['X'].values
        ys = tel['Y'].values
        speeds = tel['Speed'].values if 'Speed' in tel.columns else np.zeros(len(times))
        
        driver_telemetry[code] = {
            'times': times,
            'x': xs,
            'y': ys,
            'speed': speeds,
        }
        all_times.extend(times.tolist())
        print(f"  Driver {code}: {len(times)} telemetry points")
    
    if not driver_telemetry:
        print("ERROR: No driver telemetry extracted!")
        return
    
    # Create a common timeline at 2 FPS
    t_min = min(all_times)
    t_max = max(all_times)
    fps = 2
    timeline = np.arange(t_min, t_max, 1.0 / fps)
    print(f"Timeline: {t_min:.0f}s to {t_max:.0f}s, {len(timeline)} frames at {fps} FPS")
    
    # Resample each driver onto the timeline
    frames = []
    for i, t in enumerate(timeline):
        frame_drivers = {}
        for code, data in driver_telemetry.items():
            # Find closest time index
            idx = np.searchsorted(data['times'], t)
            if idx >= len(data['times']):
                idx = len(data['times']) - 1
            if idx < 0:
                idx = 0
            
            frame_drivers[code] = {
                'x': float(data['x'][idx]),
                'y': float(data['y'][idx]),
                'speed': float(data['speed'][idx]),
            }
        
        frames.append({
            't': round(float(t - t_min), 3),
            'drivers': frame_drivers,
        })
        
        if i % 500 == 0:
            print(f"  Frame {i}/{len(timeline)}...")
    
    # Extract weather data
    weather_data = None
    try:
        weather = session.weather_data
        if weather is not None and not weather.empty:
            # Just take the last known weather
            last_w = weather.iloc[-1]
            weather_data = {
                'track_temp': float(last_w.get('TrackTemp', 0)),
                'air_temp': float(last_w.get('AirTemp', 0)),
                'humidity': float(last_w.get('Humidity', 0)),
                'wind_speed': float(last_w.get('WindSpeed', 0)),
                'rain_state': 'DRY',
            }
    except Exception as e:
        print(f"Weather extraction failed: {e}")
    
    # Build output
    output = {
        'year': year,
        'round': round_num,
        'event_name': event_name,
        'total_frames': len(frames),
        'duration': frames[-1]['t'],
        'track': {'x': track_x, 'y': track_y},
        'weather': weather_data,
        'frames': frames,
    }
    
    out_dir = os.path.join(os.path.dirname(__file__), 'replay_data')
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f'replay_{year}_R{round_num}.json')
    
    print(f"Saving to {out_path}...")
    with open(out_path, 'w') as f:
        json.dump(output, f)
    
    file_size_mb = os.path.getsize(out_path) / (1024 * 1024)
    elapsed = time.time() - start
    print(f"=== Done! {file_size_mb:.1f} MB, {len(frames)} frames, took {elapsed:.1f}s ===")

if __name__ == '__main__':
    year = int(sys.argv[1]) if len(sys.argv) > 1 else 2024
    round_num = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    precompute(year, round_num)
