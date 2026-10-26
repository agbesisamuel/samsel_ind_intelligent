"""Pure event-time threshold state machine; no network, wall clock, ORM or safety decisions.

Each direction independently requires consecutive evidence across the full sustained
window. Missing intervals reset candidates. Hysteresis and recovery windows produce
evidence only; callers must never interpret a recovered action as human closure.
"""

import copy
import math
from datetime import datetime
from decimal import Decimal


def step(config, previous, observed_at, value, interval, grace):
    """Return new JSON-safe cursor and actions; late observations never rewind the cursor.

    Inputs are an immutable approved configuration, prior cursor, aware source time,
    finite Decimal value and approved cadence/grace. Actions contain direction-specific
    breach/recovery transitions. A gap discards candidate/recovery duration, not an
    already observed breach episode.
    """
    state = copy.deepcopy(previous)
    last = datetime.fromisoformat(state["last_at"]) if state.get("last_at") else None
    if last and observed_at <= last:
        return state, [], "late"
    gap = last is not None and (observed_at - last).total_seconds() > interval + grace
    lower, upper, hysteresis = (
        Decimal(str(config[key])) for key in ["lower_bound", "upper_bound", "hysteresis"]
    )
    actions = []
    for kind, breached in [("too_warm", value > upper), ("too_cold", value < lower)]:
        cursor = state.setdefault(kind, {"breached": False})
        if gap:
            cursor.pop("candidate_at", None)
            cursor.pop("recovery_at", None)
            cursor["candidate_count"] = cursor["recovery_count"] = 0
        if not cursor["breached"]:
            if breached:
                cursor.setdefault("candidate_at", observed_at.isoformat())
                cursor["candidate_count"] = cursor.get("candidate_count", 0) + 1
                duration = (
                    observed_at - datetime.fromisoformat(cursor["candidate_at"])
                ).total_seconds()
                if (
                    duration >= config["sustained_sec"]
                    and cursor["candidate_count"]
                    >= math.ceil(config["sustained_sec"] / interval) + 1
                ):
                    cursor["breached"] = True
                    actions.append(
                        {"kind": kind, "transition": "breached", "since": cursor["candidate_at"]}
                    )
            else:
                cursor.pop("candidate_at", None)
                cursor["candidate_count"] = 0
        elif lower + hysteresis <= value <= upper - hysteresis:
            cursor.setdefault("recovery_at", observed_at.isoformat())
            cursor["recovery_count"] = cursor.get("recovery_count", 0) + 1
            duration = (observed_at - datetime.fromisoformat(cursor["recovery_at"])).total_seconds()
            if (
                duration >= config["recovery_sec"]
                and cursor["recovery_count"] >= math.ceil(config["recovery_sec"] / interval) + 1
            ):
                actions.append(
                    {"kind": kind, "transition": "recovered", "since": cursor["recovery_at"]}
                )
                cursor.clear()
                cursor["breached"] = False
        else:
            cursor.pop("recovery_at", None)
            cursor["recovery_count"] = 0
    state["last_at"] = observed_at.isoformat()
    return state, actions, "gap_reset" if gap else "evaluated"
