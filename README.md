# Process Mining Pipeline

End-to-end process mining: discovery, variant analysis, conformance checking,
and performance analysis on enterprise event logs.

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
```

## The Story

Imagine you run a bank's loan approval department. Every day, hundreds of loan applications come in. Each one goes through a series of steps: someone submits it, a reviewer looks at it, a credit check runs, a manager approves or rejects it, and finally the money gets disbursed.

**But here's the problem:** nobody actually *knows* what the process looks like in practice.

The official SOP says: *Submit → Review → Credit Check → Approve → Disburse.* But in reality? Some applications get rejected and resubmitted. Some get put on hold for weeks. Some skip the credit check entirely because the amount is small. Some get escalated to a senior manager. The actual process is a **mess of paths**, and the only people who "know" the full picture are the ones who've been doing it for 10 years and are about to retire.

**This pipeline is how you find out what the process *actually* is.**

---

### Step 1: Collect the evidence

Every step in the system leaves a digital footprint: *"At 9:42 AM, agent_003 completed 'Credit Check' for case LOAN-04422."* Collect all those footprints from every case, and you have an **event log** — a giant table where each row is one action that happened, and each case is one loan's journey through the system.

We generated a synthetic version of this: 5,000 loan cases, 26,583 events, 10 different activities, 8 people (or systems) doing the work.

---

### Step 2: Check the evidence isn't broken

Before you trust any analysis, you need to make sure the data isn't garbage. What if timestamps are out of order? What if a "Disburse" event appears *before* the "Approve" event? What if the process changed halfway through the year (new rules, new people) and you're comparing apples to oranges?

**Stage 0 (Validation)** runs four checks:

- Are there missing values? (No case ID? No timestamp?)

- Do events within each case happen in chronological order?

- Are there impossible sequences? (Disburse before Approve? That's a data bug.)

- Has the process *drifted* over time? (PSI score: is the mix of activities in the second half of the year very different from the first half?)

If validation fails, the pipeline **stops**. You don't mine a model from broken data.

---

### Step 3: Discover the process

This is the magic step. Feed the event log into the **Inductive Miner** — an algorithm that recursively finds patterns in the sequence of activities. It looks for:

- **Sequences:** "A always comes before B"

- **Choices:** "After C, either D or E happens"

- **Loops:** "Sometimes you go back and redo B"

- **Parallelism:** "D and E can happen at the same time"

The output is a **Petri Net** — a visual map of the process. Boxes are activities, arrows are transitions, diamonds are decision points. You can *see* the process. Not the one someone drew on a whiteboard in 2019, but the one that's *actually happening right now.*

We also build a **Directly-Follows Graph (DFG)**: a simpler view where each arrow is labeled with how many times that transition happened. Thick arrows = the happy path. Thin arrows = rare exceptions.

---

### Step 4: Find the paths (variants)

A **variant** is a unique path through the process. Our pipeline found exactly 6:

| #   | Path                                                                                            | % of cases |
| --- | ----------------------------------------------------------------------------------------------- | ---------- |
| 1   | Submit → Review → Credit Check → Approve → Disburse                                             | 60%        |
| 2   | Submit → Review → Credit Check → Reject                                                         | 15%        |
| 3   | Submit → Review → Credit Check → Reject → Resubmit → Review → Credit Check → Approve → Disburse | 10%        |
| 4   | Submit → Review → Approve → Disburse *(skips credit check!)*                                    | 8%         |
| 5   | Submit → Review → Hold → Review → Credit Check → Approve → Disburse                             | 5%         |
| 6   | Submit → Review → Credit Check → Escalate → Senior Review → Approve → Disburse                  | 2%         |

**This is the insight no one had.** The "expedited" path (variant 4) skips credit check — is that intentional policy or a bug? The rework loop (variant 3) means 10% of rejected applications come back and eventually get approved. The hold (variant 5) is eating 8 days of cycle time.
<img width="2389" height="395" alt="dfg" src="https://github.com/user-attachments/assets/2ba606e6-3c63-4b90-85bb-3907f4ee044a" />
<img width="3384" height="551" alt="process_model" src="https://github.com/user-attachments/assets/4e551739-6481-4a57-974e-02c69e6d0cb7" />
<img width="1867" height="444" alt="performance_dfg" src="https://github.com/user-attachments/assets/11feddc2-5bb2-4fd5-944e-f9c3cefe6abd" />

---

### Step 5: Check if the model fits

We replay every case against the discovered model. If the model was mined from the same data, it fits perfectly (fitness = 1.0). But in production, you'd mine from last year's data and check *this month's* cases against it. If fitness drops below 0.9, something changed — a new step was added, a rule was removed, or the data is corrupted.

---

### Step 6: Find the bottlenecks

Each transition has a **mean elapsed time**. The numbers tell you where time is going:

| Transition               | Mean time    |
| ------------------------ | ------------ |
| Review → Place on Hold   | **8.2 days** |
| Reject → Resubmit        | **4.0 days** |
| Escalate → Senior Review | **2.0 days** |
| Everything else          | < 25 hours   |

**The business finding:** 80% of total cycle time is spent in just two steps — the hold and the rework. If you can reduce the average hold from 8 days to 2 days, you improve throughput for every case that hits that path. That's a **concrete, defensible recommendation** you can take to the operations director.
<img width="946" height="566" alt="performance" src="https://github.com/user-attachments/assets/74425233-4873-4f35-b8c9-9bacc32fa2ce" />

---

### The whole pipeline in one sentence

> **Take raw event data → verify it's clean → discover the process → find all the paths → check the model fits → measure where time is lost → tell the business what to fix.**



https://github.com/user-attachments/assets/8bac8066-1e96-4be9-b838-7e57f29ed2ff

