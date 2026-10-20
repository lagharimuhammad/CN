# Assignment 2 - GBN vs SR 
Muhammad Baqar Laghari | Roll No: 24K-0006 | BAI-5A | Seed = 6 (last four digits of roll number: 0006)

## Files
- `task3.py` - GBN and SR sender/receiver, simulated unreliable channel, logging (Python, standard library only)
- `task4.py` - runs the three experiments and writes the table and graph into `results/`
- `results/results_table.xlsx` - results table; `results/gbn_vs_sr.png` - GBN vs SR graph
- `results/results_multiseed.md` - supplementary 30-seed average; `results/sample_log_*.txt` - sample logs
- `Report.pdf` - typed report; `Handwritten_Tasks_1_2_5.pdf` - handwritten answers to Tasks 1, 2 and 5

## Requirements
Python 3.8+. `task4.py` also needs `matplotlib`.

## How to run
One simulation with the full log:
    python task3.py --protocol sr --packets 20 --window 4 --seqBits 3 --loss 0.1 --corrupt 0.05 --delay 0.1 --timeout 1.2 --seed 6

All experiments (table, csv, graph; seed 6):
    python task4.py

## Parameters (task3.py)
| Parameter | Meaning | Default |
|---|---|---|
| --protocol | gbn or sr | gbn |
| --packets | number of data packets | 20 |
| --window | window size N | 4 |
| --seqBits | k; sequence numbers wrap modulo 2^k | 3 |
| --loss / --corrupt / --delay | probabilities, applied to data packets and ACKs | 0.0 |
| --timeout | retransmission timeout in seconds | 1.2 |
| --seed | random seed | 1 (use 6) |

Window limits: GBN needs N <= 2^k - 1; SR needs N <= 2^(k-1). Larger values are rejected.

## Log terminology
`base`, `nextseqnum`, sender window [base, base+N-1]; GBN receiver `expectedseqnum` with cumulative ACKs; SR receiver window starting at `rcv_base` with individual ACKs.

## Assumptions
- 2 Mbps link, 1000-byte packets (4 ms transmission time), one-way propagation 250 ms (RTT 500 ms).
- A delayed packet gets an extra 0.05-0.30 s; checksum is 16-bit; data flows one way only.
- Timeout 1.2 s, above the maximum RTT (2 x 0.55 s + 4 ms = 1.104 s), so delay alone never triggers a spurious timeout.
- Throughput = delivered x 1000 x 8 / completion time (completion = last ACK received).
