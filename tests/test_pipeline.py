import pytest
import pm4py
import pandas as pd
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from pipeline import load_log, discover_model, extract_variants, check_conformance, analyze_performance

XES_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "loan_approval.xes")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")


@pytest.fixture(scope="module")
def log():
    return load_log(XES_PATH)


@pytest.fixture(scope="module")
def model(log):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    return discover_model(log, OUTPUT_DIR)


def test_log_loads(log):
    assert len(log) > 20000
    assert log['case:concept:name'].nunique() == 5000


def test_activities_exist(log):
    activities = log['concept:name'].unique()
    assert "Submit Loan Application" in activities
    assert "Approve Loan" in activities
    assert "Reject Loan" in activities


def test_discovery_produces_model(model):
    process_tree, net, im, fm = model
    assert process_tree is not None
    assert net is not None


def test_variants_found(log):
    variants = extract_variants(log, top_n=5)
    assert len(variants) >= 5  # Should find at least 5 variants


def test_conformance_high(log, model):
    _, net, im, fm = model
    fitness = check_conformance(log, net, im, fm)
    assert fitness['log_fitness'] > 0.95


def test_performance_identifies_bottleneck(log):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    perf_df = analyze_performance(log, OUTPUT_DIR)
    # The slowest transition should involve "Place on Hold" or "Resubmit"
    top_transition = f"{perf_df.iloc[0]['from']} → {perf_df.iloc[0]['to']}"
    assert "Place on Hold" in top_transition or "Resubmit" in top_transition   
