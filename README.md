# Process Mining Pipeline

End-to-end process mining: discovery, variant analysis, conformance checking,
and performance analysis on enterprise event logs.

## Architecture

XES Event Log
│
▼
┌─────────────────────┐
│ 1. Load & Validate │
└─────────┬───────────┘
▼
┌─────────────────────┐
│ 2. Process Discovery│ → Petri Net + DFG (Inductive Miner)
└─────────┬───────────┘
▼
┌─────────────────────┐
│ 3. Variant Analysis │ → Top-N paths with frequencies
└─────────┬───────────┘
▼
┌─────────────────────┐
│ 4. Conformance │ → Token-based replay fitness
└─────────┬───────────┘
▼
┌─────────────────────┐
│ 5. Performance │ → Mean elapsed time per transition
└─────────────────────┘



## Quick Start

```bash
conda create -n pm4py python=3.11 -y
conda activate pm4py
pip install -r requirements.txt

#### Generate synthetic data (or point to your own XES file)

python src/generate_data.py

#### Run the pipeline

python src/pipeline.py --input data/loan_approval.xes --output output/

#### Run tests

pytest tests/ -v   

## Key Findings (Synthetic Loan Approval, 5000 cases)

| Metric              | Value                                 |
| ------------------- | ------------------------------------- |
| Unique variants     | 6                                     |
| Happy path coverage | 60%                                   |
| Log fitness         | 1.000                                 |
| Top bottleneck      | Review → Place on Hold (8.2 days avg) |
| Second bottleneck   | Reject → Resubmit (4.0 days avg)      |
