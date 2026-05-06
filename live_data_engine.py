"""
Real-Time F1 Live Data Engine
Polls fastf1.livedata every 500ms and broadcasts via WebSocket/Polling
Checks session status and manages live vs replay modes
"""

import threading
import time
import json
import logging
import os
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from queue import Queue
import math

import fastf1
import fastf1.api
import numpy as np
from scipy.spatial import cKDTree

logger = logging.getLogger(__name__)

class LiveDataEngine:
    """
    Background thread that polls F1 live telemetry and maintains:
    - Current driver positions (X, Y coordinates)
    - Track boundaries (inner/outer lines)
    - Coordinate transformation (world → canvas pixels)
    - Session status (live, completed, upcoming)
    """
    
    def __init__(self, poll_interval=0.5):
        self.poll_interval = poll_interval  # Now 500ms
        self.running = False
        self.thread = None
        
        # Live data cache
        self.current_positions = {}  # {driver_number: {"x": float, "y": float, "lap": int, "speed": float}}
        self.track_data = None  # Circuit track points
        self.session = None
        self.season = 2026
        self.session_status = "offline"  # "live", "offline", "upcoming"
        self.current_session_info = {}
        
        # Coordinate transformation parameters
        self.world_scale = 1.0
        self.tx = 0  # translation x
        self.ty = 0  # translation y
        self.x_min, self.x_max = 0, 100
        self.y_min, self.y_max = 0, 100
        
        # Track reference polyline (for mapping x,y → along-track distance)
        self._ref_xs = np.array([])
        self._ref_ys = np.array([])
        self._ref_cumdist = np.array([])
        self.track_tree = None
        
        # Broadcast queue for WebSocket clients
        self.broadcast_queue = Queue()
        
        # Circuit rotation (degrees)
        self.circuit_rotation = 0.0
        self._rot_rad = 0.0
        self._cos_rot = 1.0
        self._sin_rot = 0.0
        
        # Session state tracking
        self.last_session_check = 0
        self.session_check_interval = 30  # Check every 30 seconds
        
        # Replay mode state
        self.mode = 'live'  # 'live' or 'replay'
        self.playback_speed = 5.0
        self.replay_start_time = None
        self.replay_frames = []
        self.replay_duration = 0.0
        self.replay_track = None
        self.replay_weather = None
        self.replay_event_name = ''
        self.replay_ready = False
        
    def start(self):
        """Start the background polling thread"""
        if self.running:
            logger.warning("LiveDataEngine already running")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._poll_loop, daemon=True)
        self.thread.start()
        logger.info("✓ LiveDataEngine started (polling every 500ms)")
    
    def stop(self):
        """Stop the background thread"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("✓ LiveDataEngine stopped")
    
    def _poll_loop(self):
        """Main polling loop - runs every 500ms"""
        while self.running:
            try:
                # Check session status periodically (every 30 seconds)
                if time.time() - self.last_session_check > self.session_check_interval:
                    self._check_session_status()
                    self.last_session_check = time.time()
                
                # Fetch live data if session is active
                if self.session_status == "live":
                    self._fetch_live_data()
                
                self._broadcast_positions()
            except Exception as e:
                logger.error(f"Error in live data poll: {e}")
            
            time.sleep(self.poll_interval)
    
    def _check_session_status(self):
        """Check if F1 session is currently live"""
        try:
            schedule = fastf1.get_event_schedule(self.season)
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            
            for _, event in schedule.iterrows():
                # Check all session times
                for session_num in range(1, 6):
                    session_name = event.get(f'Session{session_num}')
                    session_datetime = event.get(f'Session{session_num}DateUtc')
                    
                    if not session_name or session_datetime is None:
                        continue
                    
                    if hasattr(session_datetime, 'to_pydatetime'):
                        session_datetime = session_datetime.to_pydatetime()
                    
                    session_datetime = session_datetime.replace(tzinfo=None)
                    
                    # Check if session is currently happening (started <3 hours ago, ends in future)
                    session_end = session_datetime + timedelta(hours=3)
                    
                    if session_datetime <= now <= session_end:
                        # Session is LIVE
                        self.session_status = "live"
                        self.current_session_info = {
                            'name': session_name,
                            'event': event.get('EventName'),
                            'round': int(event.get('RoundNumber', 0) or 0),
                            'datetime': str(session_datetime)
                        }
                        logger.info(f"✓ LIVE SESSION DETECTED: {session_name} at {event.get('EventName')}")
                        return
            
            # No live session found
            self.session_status = "offline"
            logger.debug("No live session currently active")
            
        except Exception as e:
            logger.error(f"Error checking session status: {e}")
            self.session_status = "offline"
    
    def get_session_status(self):
        """Return current session status for frontend"""
        return {
            'status': self.session_status,
            'session_info': self.current_session_info
        }
    
    def start_replay(self, year, round_num, speed=5.0):
        """Load pre-computed replay data from JSON file.
        
        Run precompute_replay.py first to generate the data file.
        This is instant - no FastF1 calls during Flask request.
        """
        self.playback_speed = float(speed)
        
        replay_path = os.path.join(
            os.path.dirname(__file__), 'replay_data', f'replay_{year}_R{round_num}.json'
        )
        
        if not os.path.exists(replay_path):
            logger.error(f"Replay file not found: {replay_path}")
            return {'success': False, 'error': f'Replay data not found. Run: python precompute_replay.py {year} {round_num}'}
        
        try:
            logger.info(f"Loading replay from {replay_path}...")
            with open(replay_path, 'r') as f:
                data = json.load(f)
            
            self.replay_frames = data['frames']
            self.replay_duration = data['duration']
            self.replay_track = data.get('track')
            self.replay_weather = data.get('weather')
            self.replay_event_name = data.get('event_name', '')
            self.replay_start_time = datetime.now()
            self.mode = 'replay'
            self.replay_ready = True
            
            # Set track bounds from replay track data
            if self.replay_track:
                xs = self.replay_track['x']
                ys = self.replay_track['y']
                self.x_min = min(xs)
                self.x_max = max(xs)
                self.y_min = min(ys)
                self.y_max = max(ys)
                
                # Build track data for rendering
                self.track_data = {
                    'x': np.array(xs),
                    'y': np.array(ys),
                }
                self._build_reference_polyline()
            
            logger.info(f"✓ Replay loaded: {self.replay_event_name}, {len(self.replay_frames)} frames, {self.replay_duration:.0f}s")
            return {'success': True, 'event_name': self.replay_event_name, 'duration': self.replay_duration, 'frames': len(self.replay_frames)}
            
        except Exception as e:
            logger.error(f"Failed to load replay: {e}")
            return {'success': False, 'error': str(e)}
    
    def stop_replay(self):
        """Switch back to live mode"""
        self.mode = 'live'
        self.replay_frames = []
        self.replay_ready = False
        self.replay_start_time = None

    def _fetch_live_data(self):
        """Fetch current telemetry from FastF1 livedata"""
        try:
            # Get current session
            schedule = fastf1.get_event_schedule(self.season)
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            
            active_event = None
            for _, event in schedule.iterrows():
                race_date = event.get('EventDate')
                if hasattr(race_date, 'to_pydatetime'):
                    race_date = race_date.to_pydatetime()
                
                # Check if we're within ±24 hours of the race
                if race_date and abs((race_date - now).total_seconds()) < 86400:
                    active_event = event
                    break
            
            if active_event is None:
                return
            
            round_number = int(active_event.get('RoundNumber', 0))
            
            # Attempt to get live session data
            try:
                session = fastf1.get_session(self.season, round_number, 'Race')
                session.load(telemetry=True, weather=False, laps=False)
                
                if session.livedata is None or session.livedata.telemetry is None:
                    logger.warning("No livedata available")
                    return
                
                # Extract driver positions
                livedata = session.livedata.telemetry
                for driver_num, driver_data in livedata.items():
                    if isinstance(driver_data, dict):
                        self.current_positions[str(driver_num)] = {
                            "driver_number": driver_num,
                            "x": driver_data.get("X", 0.0),
                            "y": driver_data.get("Y", 0.0),
                            "z": driver_data.get("Z", 0.0),
                            "lap": driver_data.get("Lap", 1),
                            "speed": driver_data.get("Speed", 0.0),
                            "throttle": driver_data.get("Throttle", 0),
                            "brake": driver_data.get("Brake", 0),
                            "drs": driver_data.get("DRS", 0),
                            "timestamp": datetime.utcnow().isoformat()
                        }
                
                # Initialize track bounds on first run
                if self.track_data is None and self.current_positions:
                    self._initialize_track_data(session)
                
                logger.debug(f"✓ Fetched {len(self.current_positions)} driver positions")
                
            except fastf1.api.SessionNotAvailableError:
                logger.info("Session not yet available")
            
        except Exception as e:
            logger.error(f"Error fetching live data: {e}")
    
    def _initialize_track_data(self, session):
        """Build track reference line from a sample lap"""
        try:
            laps = session.laps
            if laps is None or laps.empty:
                return
            
            # Get telemetry from first completed lap
            fastest_lap = laps.pick_fastest()
            if fastest_lap is None or fastest_lap.telemetry is None:
                return
            
            telemetry = fastest_lap.telemetry
            self.track_data = {
                "x": telemetry['X'].values,
                "y": telemetry['Y'].values,
                "z": telemetry['Z'].values,
            }
            
            # Set track bounds
            self.x_min, self.x_max = float(telemetry['X'].min()), float(telemetry['X'].max())
            self.y_min, self.y_max = float(telemetry['Y'].min()), float(telemetry['Y'].max())
            
            # Build reference polyline (dense interpolation)
            self._build_reference_polyline()
            
            logger.info(f"✓ Track data initialized: X=[{self.x_min:.1f}, {self.x_max:.1f}], Y=[{self.y_min:.1f}, {self.y_max:.1f}]")
            
        except Exception as e:
            logger.error(f"Error initializing track data: {e}")
    
    def _build_reference_polyline(self):
        """Interpolate track points to create a dense reference line for coordinate mapping"""
        if self.track_data is None:
            return
        
        xs = self.track_data['x']
        ys = self.track_data['y']
        
        # Interpolate to 4000 points for high precision
        interp_points = 4000
        t_old = np.linspace(0, 1, len(xs))
        t_new = np.linspace(0, 1, interp_points)
        
        xs_interp = np.interp(t_new, t_old, xs)
        ys_interp = np.interp(t_new, t_old, ys)
        
        # Store reference coordinates
        self._ref_xs = xs_interp
        self._ref_ys = ys_interp
        
        # Compute cumulative distance along the track
        diffs = np.sqrt(np.diff(xs_interp)**2 + np.diff(ys_interp)**2)
        self._ref_cumdist = np.concatenate([[0], np.cumsum(diffs)])
        
        # Build KD-Tree for fast nearest-point lookup
        self.track_tree = cKDTree(np.column_stack((xs_interp, ys_interp)))
        
        logger.debug(f"✓ Reference polyline built: {interp_points} points, total length {self._ref_cumdist[-1]:.1f}m")
    
    def set_canvas_dimensions(self, canvas_width, canvas_height, left_margin=0, right_margin=0):
        """
        Recalculate world → screen transformation
        Called when canvas resizes or on page load
        
        Based on IAmTomShaw/f1-race-replay coordinate transformation
        """
        if self.track_data is None:
            return
        
        padding = 0.05
        
        # Usable canvas area
        usable_width = max(1.0, canvas_width - left_margin - right_margin)
        usable_height = max(1.0, canvas_height)
        
        # World bounds
        world_width = max(1.0, self.x_max - self.x_min)
        world_height = max(1.0, self.y_max - self.y_min)
        
        # Calculate scale to fit both dimensions
        scale_x = (usable_width * (1 - 2 * padding)) / world_width
        scale_y = (usable_height * (1 - 2 * padding)) / world_height
        self.world_scale = min(scale_x, scale_y)
        
        # Center position
        world_cx = (self.x_min + self.x_max) / 2.0
        world_cy = (self.y_min + self.y_max) / 2.0
        
        screen_cx = left_margin + usable_width / 2.0
        screen_cy = canvas_height / 2.0
        
        # Translation to center
        self.tx = screen_cx - self.world_scale * world_cx
        self.ty = screen_cy - self.world_scale * world_cy
        
        logger.info(f"✓ Canvas scaling set: scale={self.world_scale:.3f}, translate=({self.tx:.1f}, {self.ty:.1f})")
    
    def set_circuit_rotation(self, degrees):
        """Set circuit rotation angle (for certain tracks)"""
        self.circuit_rotation = degrees
        self._rot_rad = math.radians(degrees)
        self._cos_rot = math.cos(self._rot_rad)
        self._sin_rot = math.sin(self._rot_rad)
    
    def world_to_screen(self, x, y):
        """
        Transform world coordinates (X, Y telemetry) → canvas pixels
        
        Transformation steps:
        1. Rotate around track center (if circuit_rotation is set)
        2. Scale by world_scale
        3. Translate by (tx, ty)
        """
        world_cx = (self.x_min + self.x_max) / 2.0
        world_cy = (self.y_min + self.y_max) / 2.0
        
        # Step 1: Rotate if needed
        if self._rot_rad:
            tx = x - world_cx
            ty = y - world_cy
            rx = tx * self._cos_rot - ty * self._sin_rot
            ry = tx * self._sin_rot + ty * self._cos_rot
            x, y = rx + world_cx, ry + world_cy
        
        # Step 2 & 3: Scale + Translate
        sx = self.world_scale * x + self.tx
        sy = self.world_scale * y + self.ty
        
        return sx, sy
    
    def _project_to_reference(self, x, y):
        """
        Project (x, y) telemetry onto the reference line.
        Returns cumulative distance along track (in meters)
        
        Used for: leaderboard ordering, progress calculation
        """
        if self.track_tree is None or len(self._ref_xs) == 0:
            return 0.0
        
        try:
            # Find nearest point on reference line
            dist, idx = self.track_tree.query([x, y])
            idx = int(idx)
            
            # Optionally project onto adjacent segment for better accuracy
            if idx < len(self._ref_xs) - 1:
                x1, y1 = self._ref_xs[idx], self._ref_ys[idx]
                x2, y2 = self._ref_xs[idx + 1], self._ref_ys[idx + 1]
                
                vx, vy = x2 - x1, y2 - y1
                seg_len2 = vx*vx + vy*vy
                
                if seg_len2 > 0:
                    t = max(0, min(1, ((x - x1) * vx + (y - y1) * vy) / seg_len2))
                    proj_x = x1 + t * vx
                    proj_y = y1 + t * vy
                    seg_dist = math.sqrt((proj_x - x1)**2 + (proj_y - y1)**2)
                    return float(self._ref_cumdist[idx] + seg_dist)
            
            return float(self._ref_cumdist[idx])
        except Exception as e:
            logger.warning(f"Error projecting point: {e}")
            return 0.0
    
    def get_driver_screen_positions(self):
        """
        Get all driver positions transformed to screen coordinates.
        Returns list of dicts ready for canvas rendering.
        In replay mode, returns (positions, weather) tuple.
        """
        positions = []
        
        # === REPLAY MODE ===
        if self.mode == 'replay' and self.replay_ready and self.replay_frames:
            elapsed = (datetime.now() - self.replay_start_time).total_seconds() * self.playback_speed
            
            # Loop replay
            if elapsed > self.replay_duration:
                self.replay_start_time = datetime.now()
                elapsed = 0
            
            # Binary search for closest frame
            lo, hi = 0, len(self.replay_frames) - 1
            while lo < hi:
                mid = (lo + hi) // 2
                if self.replay_frames[mid]['t'] < elapsed:
                    lo = mid + 1
                else:
                    hi = mid
            frame = self.replay_frames[lo]
            
            for code, data in frame['drivers'].items():
                x, y = data['x'], data['y']
                sx, sy = self.world_to_screen(x, y)
                progress_m = self._project_to_reference(x, y)
                
                positions.append({
                    "driver_number": code,
                    "screen_x": round(sx, 2),
                    "screen_y": round(sy, 2),
                    "world_x": round(x, 2),
                    "world_y": round(y, 2),
                    "lap": 1,  # Can extract lap later if needed
                    "speed": round(data.get('speed', 0), 1),
                    "throttle": 0,
                    "brake": 0,
                    "drs": 0,
                    "progress_m": round(progress_m, 1),
                    "total_progress": round(progress_m, 1),
                    "timestamp": datetime.utcnow().isoformat()
                })
            
            return positions, self.replay_weather
        
        # === LIVE MODE ===
        for driver_num, telemetry in self.current_positions.items():
            x, y = telemetry.get('x', 0), telemetry.get('y', 0)
            
            # Skip invalid coordinates
            if x == 0 and y == 0:
                continue
            
            # Transform to screen
            sx, sy = self.world_to_screen(x, y)
            
            # Project onto reference for leaderboard
            progress_m = self._project_to_reference(x, y)
            lap = telemetry.get('lap', 1)
            total_progress = (max(lap, 1) - 1) * self._ref_cumdist[-1] + progress_m if len(self._ref_cumdist) > 0 else 0
            
            positions.append({
                "driver_number": str(driver_num),
                "screen_x": round(sx, 2),
                "screen_y": round(sy, 2),
                "world_x": round(x, 2),
                "world_y": round(y, 2),
                "lap": lap,
                "speed": round(telemetry.get('speed', 0), 1),
                "throttle": telemetry.get('throttle', 0),
                "brake": telemetry.get('brake', 0),
                "drs": telemetry.get('drs', 0),
                "progress_m": round(progress_m, 1),
                "total_progress": round(total_progress, 1),
                "timestamp": telemetry.get('timestamp', '')
            })
        
        return positions
    
    def _broadcast_positions(self):
        """Place current positions into broadcast queue for WebSocket clients"""
        result = self.get_driver_screen_positions()
        
        weather = None
        if isinstance(result, tuple):
            positions, weather = result
        else:
            positions = result
        
        message = {
            "type": "positions",
            "timestamp": datetime.utcnow().isoformat(),
            "positions": positions,
            "weather": weather,
            "track_bounds": {
                "x_min": self.x_min,
                "x_max": self.x_max,
                "y_min": self.y_min,
                "y_max": self.y_max,
            }
        }
        
        try:
            self.broadcast_queue.put_nowait(message)
        except:
            pass  # Queue full, skip this broadcast

# Global instance
live_engine = LiveDataEngine(poll_interval=2.0)