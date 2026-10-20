Results: 200 packets, N=4, k=3, seed=6

| Scenario | Protocol | Transmitted | Retransmissions | Delivered | Time (s) | Throughput (kbps) | Exec (ms) |
|---|---|---|---|---|---|---|---|
| A: Reliable | GBN | 200 | 0 | 200/200 | 25.21 | 63.5 | 2.2 |
| A: Reliable | SR | 200 | 0 | 200/200 | 25.21 | 63.5 | 6.5 |
| B: Loss 0.10 | GBN | 285 | 85 | 200/200 | 55.85 | 28.6 | 3.1 |
| B: Loss 0.10 | SR | 254 | 54 | 200/200 | 65.42 | 24.5 | 3.3 |
| C: Mixed | GBN | 350 | 150 | 200/200 | 82.52 | 19.4 | 3.6 |
| C: Mixed | SR | 269 | 69 | 200/200 | 75.51 | 21.2 | 6.3 |
