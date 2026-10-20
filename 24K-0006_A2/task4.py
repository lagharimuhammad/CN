import csv
import os
import statistics
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from task3 import Config, runSimulation

PACKETS, WINDOW, SEQ_BITS = 200, 4, 3
MAIN_SEED = 6
SEED_LIST = [MAIN_SEED + i for i in range(30)]
OUT_DIR = "results"
scenarioList = [
    ("A: Reliable", dict(loss=0.0, corrupt=0.0, delay=0.0)),
    ("B: Loss 0.10", dict(loss=0.10, corrupt=0.0, delay=0.0)),
    ("C: Mixed", dict(loss=0.05, corrupt=0.05, delay=0.10)),
]


def runOnce(proto, seed, channel):
    cfg = Config(protocol=proto, packets=PACKETS, window=WINDOW,
                 seqBits=SEQ_BITS, seed=seed, **channel)
    return runSimulation(cfg, verbose=False)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    tableRows = []
    for name, channel in scenarioList:
        for proto in ("gbn", "sr"):
            r = runOnce(proto, MAIN_SEED, channel)
            assert r["completed"] and r["integrityErrors"] == 0, (name, proto)
            tableRows.append({
                "scenario": name, "protocol": r["protocol"],
                "transmitted": r["transmitted"],
                "retransmissions": r["retransmissions"],
                "delivered": r["delivered"],
                "timeS": round(r["simTimeS"], 2),
                "throughputKbps": round(r["throughputKbps"], 1),
                "execMs": round(r["wallMs"], 1),
            })

    with open(f"{OUT_DIR}/results.csv", "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(tableRows[0].keys()))
        wr.writeheader()
        wr.writerows(tableRows)

    header = ("| Scenario | Protocol | Transmitted | Retransmissions | Delivered | "
              "Time (s) | Throughput (kbps) | Exec (ms) |\n"
              "|---|---|---|---|---|---|---|---|\n")
    body = "".join(
        f"| {r['scenario']} | {r['protocol']} | {r['transmitted']} | "
        f"{r['retransmissions']} | {r['delivered']}/{PACKETS} | {r['timeS']} | "
        f"{r['throughputKbps']} | {r['execMs']} |\n" for r in tableRows)
    title = f"Results: {PACKETS} packets, N={WINDOW}, k={SEQ_BITS}, seed={MAIN_SEED}\n\n"
    with open(f"{OUT_DIR}/results_table.md", "w") as f:
        f.write(title + header + body)
    print(title + header + body)

    names = [s[0] for s in scenarioList]

    def pick(proto, key):
        return [next(r[key] for r in tableRows
                     if r["scenario"] == n and r["protocol"] == proto) for n in names]

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.6))
    panels = [("transmitted", "Data packets transmitted"),
              ("retransmissions", "Retransmissions"),
              ("throughputKbps", "Throughput (kbps)")]
    pos = list(range(len(names)))
    w = 0.38
    for ax, (key, ttl) in zip(axes, panels):
        gbnVals, srVals = pick("GBN", key), pick("SR", key)
        barsG = ax.bar([p - w / 2 for p in pos], gbnVals, w, label="GBN", color="#c0392b")
        barsS = ax.bar([p + w / 2 for p in pos], srVals, w, label="SR", color="#2980b9")
        for group in (barsG, barsS):
            for b in group:
                ax.annotate(f"{b.get_height():g}",
                            (b.get_x() + b.get_width() / 2, b.get_height()),
                            ha="center", va="bottom", fontsize=9)
        ax.set_xticks(pos)
        ax.set_xticklabels(names, fontsize=9)
        ax.set_title(ttl)
        ax.margins(y=0.15)
        ax.grid(axis="y", alpha=0.3)
        ax.legend()
    fig.suptitle(f"GBN vs SR ({PACKETS} packets, N={WINDOW}, k={SEQ_BITS}, "
                 f"seed={MAIN_SEED})")
    fig.tight_layout()
    fig.savefig(f"{OUT_DIR}/gbn_vs_sr.png", dpi=160)

    lines = [f"Mean over {len(SEED_LIST)} seeds ({SEED_LIST[0]}..{SEED_LIST[-1]})\n",
             "| Scenario | Protocol | Transmitted | Retransmissions | Throughput (kbps) |",
             "|---|---|---|---|---|"]
    for name, channel in scenarioList:
        for proto in ("gbn", "sr"):
            runs = [runOnce(proto, s, channel) for s in SEED_LIST]
            failed = sum(1 for r in runs if not r["completed"] or r["integrityErrors"])
            avg = lambda k: statistics.mean(r[k] for r in runs)
            lines.append(f"| {name} | {proto.upper()} | {avg('transmitted'):.1f} | "
                         f"{avg('retransmissions'):.1f} | {avg('throughputKbps'):.1f} |"
                         + (f" ({failed} failed)" if failed else ""))
    with open(f"{OUT_DIR}/results_multiseed.md", "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
