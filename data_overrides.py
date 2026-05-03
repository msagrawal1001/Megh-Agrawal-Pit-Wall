"""
Manual override registry for 2026 simulated/delayed data.
Use when FastF1/Jolpi returns incorrect results (e.g., data delay, simulation mismatch).
Format: {(season, round, session_name): classification_list}
"""

RESULT_OVERRIDES = {
    # Example: Miami 2026 Sprint
    # (2026, 5, "Sprint"): [
    #     {
    #         "position": 1,
    #         "driver_code": "NOR",
    #         "first_name": "Lando",
    #         "last_name": "Norris",
    #         "team_name": "McLaren",
    #         "time": "",
    #         "gap": "",
    #         "status": "",
    #         "result_text": "WINNER",
    #     },
    #     # ... rest of field
    # ]
}

def get_override(season, round_num, session_name):
    """Fetch manual override if available."""
    key = (season, round_num, session_name)
    return RESULT_OVERRIDES.get(key)

def apply_override(classification, season, round_num, session_name):
    """Apply override to classification list."""
    override = get_override(season, round_num, session_name)
    if override:
        logger.warning(f"⚠️  USING MANUAL OVERRIDE for {season} R{round_num} {session_name}")
        return override
    return classification