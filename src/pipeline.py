"""
End-to-end process mining pipeline.

Usage:
    python src/pipeline.py --input data/loan_approval.xes --output output/
"""
import argparse
import os
import logging
from pathlib import Path

import pm4py
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def load_log(path: str) -> pd.DataFrame:
    """Load an XES event log into a DataFrame."""
    logger.info(f"Loading log: {path}")
    log = pm4py.read_xes(path)
    n_cases = log['case:concept:name'].nunique()
    logger.info(f"Loaded {len(log)} events, {n_cases} cases")
    return log


def discover_model(log: pd.DataFrame, output_dir: str):
    """Discover process model (Petri Net + DFG) and save visualizations."""
    # Petri Net via Inductive Miner
    process_tree = pm4py.discover_process_tree_inductive(log)
    net, im, fm = pm4py.convert_to_petri_net(process_tree)
    pm4py.save_vis_petri_net(net, im, fm,
        os.path.join(output_dir, "process_model.svg"),
        graph_title="Discovered Process Model")
    logger.info("Saved process model (Petri Net)")

    # DFG
    dfg, start_acts, end_acts = pm4py.discover_dfg(log)
    pm4py.save_vis_dfg(dfg, start_acts, end_acts,
        os.path.join(output_dir, "dfg.svg"))
    logger.info("Saved DFG")

    return process_tree, net, im, fm


def extract_variants(log: pd.DataFrame, top_n: int = 10) -> dict:
    """Extract and log top process variants."""
    variants = pm4py.get_variants(log,
        activity_key='concept:name',
        case_id_key='case:concept:name',
        timestamp_key='time:timestamp')

    total = log['case:concept:name'].nunique()
    logger.info(f"Total unique variants: {len(variants)}")

    top = sorted(variants.items(), key=lambda x: x[1], reverse=True)[:top_n]
    for i, (variant, count) in enumerate(top):
        logger.info(f"  Variant {i+1}: {count} cases ({count/total*100:.1f}%) → {' → '.join(variant)}")

    return variants


def check_conformance(log: pd.DataFrame, net, im, fm) -> dict:
    """Token-based replay conformance checking."""
    fitness = pm4py.fitness_token_based_replay(
        log, net, im, fm,
        activity_key='concept:name',
        case_id_key='case:concept:name',
        timestamp_key='time:timestamp'
    )
    logger.info(f"Log fitness: {fitness['log_fitness']:.4f}")
    logger.info(f"Average trace fitness: {fitness['average_trace_fitness']:.4f}")
    logger.info(f"% fit traces: {fitness['percentage_of_fitting_traces']:.1f}%")
    return fitness


def analyze_performance(log: pd.DataFrame, output_dir: str) -> pd.DataFrame:
    """Performance DFG: mean elapsed time between activities."""
    perf_dfg, start_acts, end_acts = pm4py.discover_performance_dfg(
        log,
        case_id_key='case:concept:name',
        activity_key='concept:name',
        timestamp_key='time:timestamp'
    )

    # Save visualization
    pm4py.save_vis_performance_dfg(
        perf_dfg, start_acts, end_acts,
        os.path.join(output_dir, "performance_dfg.svg"),
        graph_title="Mean Elapsed Time Between Activities"
    )
    logger.info("Saved performance DFG")

    # Extract edge times
    edge_times = [(src, tgt, v['mean']) for (src, tgt), v in perf_dfg.items()]
    edge_df = pd.DataFrame(edge_times, columns=["from", "to", "mean_seconds"])
    edge_df["mean_hours"] = edge_df["mean_seconds"] / 3600
    edge_df = edge_df.sort_values("mean_hours", ascending=False).reset_index(drop=True)

    logger.info("Top 5 slowest transitions:")
    for _, row in edge_df.head(5).iterrows():
        logger.info(f"  {row['from']} → {row['to']}: {row['mean_hours']:.1f}h")

    return edge_df


def main():
    parser = argparse.ArgumentParser(description="Process Mining Pipeline")
    parser.add_argument("--input", required=True, help="Path to XES file")
    parser.add_argument("--output", default="output/", help="Output directory")
    parser.add_argument("--top-n", type=int, default=10, help="Top N variants to report")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    # Pipeline
    log = load_log(args.input)
    model = discover_model(log, args.output)
    variants = extract_variants(log, top_n=args.top_n)
    fitness = check_conformance(log, *model[1:])
    perf_df = analyze_performance(log, args.output)

    # Save performance table
    perf_df.to_csv(os.path.join(args.output, "performance.csv"), index=False)
    logger.info(f"Saved performance table: {args.output}/performance.csv")

    logger.info("Pipeline complete.")


if __name__ == "__main__":
    main()   
