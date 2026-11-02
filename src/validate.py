"""
Stage 0: Data Quality Validation.
Runs BEFORE process mining. Flags bad data so you don't mine garbage.

Checks:
  1. Missing values (null case_id, activity, timestamp)
  2. Timestamp monotonicity (events within a case must be chronological)
  3. Impossible sequences (activity B appears before activity A when A→B is required)
  4. PSI drift (activity distribution shift between two time windows)

Usage:
    python src/validate.py --input data/loan_approval.xes
    # or import into pipeline.py and call validate(log) before mining
"""
import argparse
import os
import logging
from dataclasses import dataclass, field
from typing import Optional

import pm4py
import pandas as pd
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class ValidationReport:
    """Structured result of all validation checks."""
    total_events: int = 0
    total_cases: int = 0
    missing_values: dict = field(default_factory=dict)
    non_monotonic_cases: list = field(default_factory=list)
    impossible_sequences: list = field(default_factory=list)
    psi_scores: dict = field(default_factory=dict)
    passed: bool = True
    warnings: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    def summary(self) -> str:
        status = "✅ PASSED" if self.passed else "❌ FAILED"
        lines = [
            f"Validation Report: {status}",
            f"  Events: {self.total_events:,} | Cases: {self.total_cases:,}",
            f"  Missing values: {self.missing_values}",
            f"  Non-monotonic cases: {len(self.non_monotonic_cases)}",
            f"  Impossible sequences: {len(self.impossible_sequences)}",
            f"  PSI drift: {self.psi_scores}",
            f"  Warnings: {len(self.warnings)}",
            f"  Errors: {len(self.errors)}",
        ]
        for w in self.warnings:
            lines.append(f"    ⚠️  {w}")
        for e in self.errors:
            lines.append(f"    🚨 {e}")
        return "\n".join(lines)


def check_missing_values(log: pd.DataFrame) -> dict:
    """Check for null/empty values in critical columns."""
    critical_cols = ['case:concept:name', 'concept:name', 'time:timestamp', 'org:resource']
    results = {}
    for col in critical_cols:
        if col in log.columns:
            n_null = log[col].isna().sum()
            n_empty = (log[col].astype(str).str.strip() == '').sum() if n_null == 0 else 0
            results[col] = {"null": int(n_null), "empty": int(n_empty)}
        else:
            results[col] = {"null": -1, "empty": 0, "note": "column missing"}
    return results


def check_timestamp_monotonicity(log: pd.DataFrame, sample: int = 500) -> list:
    """
    Check that events within each case are in chronological order.
    If a case has event at 10:00 followed by event at 09:00, that's non-monotonic.
    Samples up to `sample` cases for speed on large logs.
    """
    log = log.copy()
    log['time:timestamp'] = pd.to_datetime(log['time:timestamp'])

    case_ids = log['case:concept:name'].unique()
    if len(case_ids) > sample:
        np.random.seed(42)
        case_ids = np.random.choice(case_ids, size=sample, replace=False)

    non_monotonic = []
    for case_id in case_ids:
        trace = log[log['case:concept:name'] == case_id].sort_index()
        timestamps = trace['time:timestamp'].values
        # Check if any timestamp is earlier than the previous one
        diffs = np.diff(timestamps.astype(np.int64))
        if (diffs < 0).any():
            n_violations = (diffs < 0).sum()
            non_monotonic.append({
                "case_id": case_id,
                "violations": int(n_violations),
                "first_bad_index": int(np.argmax(diffs < 0)),
            })

    return non_monotonic


def check_impossible_sequences(log: pd.DataFrame, required_order: list[list[str]]) -> list:
    """
    Check for impossible activity sequences.
    required_order: list of [activity_a, activity_b] pairs where A must come before B.
    Example: [["Approve Loan", "Disburse Funds"]] means Disburse must come AFTER Approve.
    """
    impossible = []
    for case_id, group in log.groupby('case:concept:name'):
        activities = group.sort_values('time:timestamp')['concept:name'].tolist()
        for a, b in required_order:
            if a in activities and b in activities:
                if activities.index(b) < activities.index(a):
                    impossible.append({
                        "case_id": case_id,
                        "violation": f"'{b}' appears before '{a}'",
                        "sequence": activities,
                    })
                    break  # one violation per case is enough

    return impossible


def compute_psi(expected: np.ndarray, actual: np.ndarray, bins: int = 10) -> float:
    """
    Population Stability Index.
    - 0.1: no significant change
    - 0.2: moderate change
    - >0.25: significant drift
    """
    # Create bin edges from expected distribution
    breakpoints = np.linspace(0, 1, bins + 1)
    # Handle edge case where all values are the same
    #if expected.max() == expected.min() and actual.max() == actual.min():
       #return 0.0   

    # Proportions in each bin
    exp_counts, _ = np.histogram(expected, bins=breakpoints)
    act_counts, _ = np.histogram(actual, bins=breakpoints)

    # Avoid division by zero
    exp_pct = np.where(exp_counts == 0, 0.0001, exp_counts / len(expected))
    act_pct = np.where(act_counts == 0, 0.0001, act_counts / len(actual))

    psi = np.sum((act_pct - exp_pct) * np.log(act_pct / exp_pct))
    return float(psi)


def check_psi_drift(log: pd.DataFrame, split_fraction: float = 0.5) -> dict:
    """
    Compare activity distribution between first and second half of the log
    (by timestamp). High PSI = the process changed over time.
    """
    log = log.copy()
    log['time:timestamp'] = pd.to_datetime(log['time:timestamp'])
    log = log.sort_values('time:timestamp')

    # Split by time
    cutoff = log['time:timestamp'].quantile(split_fraction)
    first_half = log[log['time:timestamp'] <= cutoff]
    second_half = log[log['time:timestamp'] > cutoff]

    # Get activity distributions as numeric (use activity index)
    activities = sorted(log['concept:name'].unique())
    activity_to_idx = {a: i for i, a in enumerate(activities)}

    first_dist = first_half['concept:name'].map(activity_to_idx).values
    second_dist = second_half['concept:name'].map(activity_to_idx).values

    psi = compute_psi(first_dist.astype(float), second_dist.astype(float), bins=min(len(activities), 10))

    # Also check resource distribution
    resources = sorted(log['org:resource'].unique())
    resource_to_idx = {r: i for i, r in enumerate(resources)}
    first_res = first_half['org:resource'].map(resource_to_idx).values
    second_res = second_half['org:resource'].map(resource_to_idx).values
    psi_res = compute_psi(first_res.astype(float), second_res.astype(float), bins=min(len(resources), 10))

    return {
        "activity_psi": round(psi, 4),
        "resource_psi": round(psi_res, 4),
        "split_cutoff": str(cutoff),
        "first_half_cases": first_half['case:concept:name'].nunique(),
        "second_half_cases": second_half['case:concept:name'].nunique(),
    }


def validate(log: pd.DataFrame,
             required_order: Optional[list[list[str]]] = None,
             sample: int = 500) -> ValidationReport:
    """
    Run all validation checks. Returns a structured report.
    """
    report = ValidationReport(
        total_events=len(log),
        total_cases=log['case:concept:name'].nunique(),
    )

    # 1. Missing values
    logger.info("Check 1/4: Missing values...")
    report.missing_values = check_missing_values(log)
    for col, counts in report.missing_values.items():
        if counts.get("null", 0) > 0:
            severity = "error" if counts["null"] > len(log) * 0.01 else "warning"
            msg = f"Column '{col}' has {counts['null']} null values"
            if severity == "error":
                report.errors.append(msg)
                report.passed = False
            else:
                report.warnings.append(msg)

    # 2. Timestamp monotonicity
    logger.info("Check 2/4: Timestamp monotonicity...")
    report.non_monotonic_cases = check_timestamp_monotonicity(log, sample=sample)
    if report.non_monotonic_cases:
        pct = len(report.non_monotonic_cases) / sample * 100
        msg = f"{len(report.non_monotonic_cases)}/{sample} sampled cases have non-monotonic timestamps ({pct:.1f}%)"
        if pct > 5:
            report.errors.append(msg)
            report.passed = False
        else:
            report.warnings.append(msg)

    # 3. Impossible sequences
    logger.info("Check 3/4: Impossible sequences...")
    if required_order:
        report.impossible_sequences = check_impossible_sequences(log, required_order)
        if report.impossible_sequences:
            msg = f"{len(report.impossible_sequences)} cases have impossible sequences"
            report.errors.append(msg)
            report.passed = False
    else:
        logger.info("  Skipped (no required_order specified)")

    # 4. PSI drift
    logger.info("Check 4/4: PSI drift...")
    report.psi_scores = check_psi_drift(log)
    if report.psi_scores["activity_psi"] > 0.25:
        report.warnings.append(
            f"Activity distribution drift detected (PSI={report.psi_scores['activity_psi']}). "
            f"Process may have changed between time windows."
        )

    logger.info(f"\n{report.summary()}")
    return report


def main():
    parser = argparse.ArgumentParser(description="Data Quality Validation (Stage 0)")
    parser.add_argument("--input", required=True, help="Path to XES file")
    parser.add_argument("--sample", type=int, default=500, help="Sample size for monotonicity check")
    args = parser.parse_args()

    log = pm4py.read_xes(args.input)
    logger.info(f"Loaded {len(log)} events, {log['case:concept:name'].nunique()} cases")

    # Define domain-specific ordering constraints
    required_order = [
        ["Submit Loan Application", "Review Application"],
        ["Review Application", "Credit Check"],
        ["Credit Check", "Approve Loan"],
        ["Credit Check", "Reject Loan"],
        ["Approve Loan", "Disburse Funds"],
    ]

    report = validate(log, required_order=required_order, sample=args.sample)
    print(f"\n{report.summary()}")


if __name__ == "__main__":
    main()   
