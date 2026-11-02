"""
Generate a synthetic process mining event log.
Simulates a loan approval process with 5000 cases, multiple variants,
realistic timestamps, resources, and noise.

Usage: python src/generate_data.py
Output: data/loan_approval.xes
"""
import os
import random
from datetime import datetime, timedelta
from collections import defaultdict

import pandas as pd
import pm4py

random.seed(42)

# ──────────────────────────────────────────────
# Process definition
# ──────────────────────────────────────────────
# Main path: Submit → Review → Credit Check → Approve → Disburse
# Variants:
#   - 60%: happy path (Submit → Review → Credit Check → Approve → Disburse)
#   - 15%: rejected (Submit → Review → Credit Check → Reject)
#   - 10%: rework (Submit → Review → Credit Check → Reject → Resubmit → Review → Credit Check → Approve → Disburse)
#   - 8%:  expedited (Submit → Review → Approve → Disburse)  [skips Credit Check]
#   - 5%:  on-hold (Submit → Review → Hold → Review → Credit Check → Approve → Disburse)
#   - 2%:  escalated (Submit → Review → Credit Check → Escalate → Senior Review → Approve → Disburse)

RESOURCES = [
    "agent_001", "agent_002", "agent_003", "agent_004", "agent_005",
    "supervisor_01", "supervisor_02", "system_auto"
]

# Time between steps (in hours): (min, max)
STEP_DURATIONS = {
    "Submit Loan Application":   (1, 24),
    "Review Application":        (2, 48),
    "Credit Check":              (1, 72),
    "Approve Loan":              (1, 12),
    "Disburse Funds":            (1, 24),
    "Reject Loan":               (1, 8),
    "Resubmit Application":      (24, 168),   # 1-7 days
    "Place on Hold":             (48, 336),   # 2-14 days
    "Escalate":                  (1, 24),
    "Senior Review":             (24, 72),
}

def random_duration(step: str) -> float:
    lo, hi = STEP_DURATIONS.get(step, (1, 24))
    return random.uniform(lo, hi)

def pick_resources(step: str) -> str:
    if step == "Submit Loan Application":
        return "system_auto"
    if step == "Disburse Funds":
        return "system_auto"
    if step == "Senior Review":
        return random.choice(["supervisor_01", "supervisor_02"])
    return random.choice(RESOURCES[:6])

def generate_case(case_id: str, start_time: datetime) -> list[dict]:
    """Generate one case (one loan application) with its full event sequence."""
    r = random.random()
    
    if r < 0.60:
        steps = ["Submit Loan Application", "Review Application", "Credit Check", "Approve Loan", "Disburse Funds"]
    elif r < 0.75:
        steps = ["Submit Loan Application", "Review Application", "Credit Check", "Reject Loan"]
    elif r < 0.85:
        steps = ["Submit Loan Application", "Review Application", "Credit Check", "Reject Loan",
                 "Resubmit Application", "Review Application", "Credit Check", "Approve Loan", "Disburse Funds"]
    elif r < 0.93:
        steps = ["Submit Loan Application", "Review Application", "Approve Loan", "Disburse Funds"]
    elif r < 0.98:
        steps = ["Submit Loan Application", "Review Application", "Place on Hold", "Review Application",
                 "Credit Check", "Approve Loan", "Disburse Funds"]
    else:
        steps = ["Submit Loan Application", "Review Application", "Credit Check", "Escalate",
                 "Senior Review", "Approve Loan", "Disburse Funds"]

    events = []
    t = start_time
    for step in steps:
        duration = random_duration(step)
        t = t + timedelta(hours=duration)
        events.append({
            "case:concept:name": case_id,
            "concept:name": step,
            "time:timestamp": t.strftime("%Y-%m-%dT%H:%M:%S"),
            "org:resource": pick_resources(step),
        })
    return events

def main():
    n_cases = 5000
    start_date = datetime(2025, 1, 1)
    
    all_events = []
    for i in range(n_cases):
        case_id = f"LOAN-{i:05d}"
        # Spread start times across 6 months
        case_start = start_date + timedelta(hours=random.uniform(0, 4320))
        all_events.extend(generate_case(case_id, case_start))
    
    # Build DataFrame
    df = pd.DataFrame(all_events)
    df["time:timestamp"] = pd.to_datetime(df["time:timestamp"])
    df = df.sort_values("time:timestamp").reset_index(drop=True)
    
    print(f"Generated: {len(df)} events, {n_cases} cases, {df['concept:name'].nunique()} activities")
    print(f"\nActivity distribution:")
    print(df["concept:name"].value_counts().to_string())
    
    # Convert to PM4Py event log
    event_log = pm4py.convert_to_event_log(df)
    
    # Save as XES
    os.makedirs("data", exist_ok=True)
    output_path = "data/loan_approval.xes"
    pm4py.write_xes(event_log, output_path)
    print(f"\nSaved to: {output_path}")
    print(f"File size: {os.path.getsize(output_path) / 1024 / 1024:.1f} MB")

if __name__ == "__main__":
    main()   
