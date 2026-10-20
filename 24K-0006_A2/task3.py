import argparse
import heapq
import random
import time
from dataclasses import dataclass

PKT_BYTES = 1000
LINK_BPS = 2_000_000
ONE_WAY = 0.25
EXTRA_LAG = (0.05, 0.30)


@dataclass
class Config:
    protocol: str = "gbn"
    packets: int = 20
    window: int = 4
    seqBits: int = 3
    loss: float = 0.0
    corrupt: float = 0.0
    delay: float = 0.0
    timeout: float = 1.2
    seed: int = 1


def makeChecksum(field, payload=b""):
    return (-(field + sum(payload))) & 0xFFFF


def makeData(seq, payload):
    return {"kind": "data", "seq": seq, "payload": payload,
            "csum": makeChecksum(seq, payload)}


def makeAck(seq):
    return {"kind": "ack", "seq": seq, "csum": makeChecksum(seq)}


def isIntact(pkt):
    return pkt["csum"] == makeChecksum(pkt["seq"], pkt.get("payload", b""))


class Simulator:
    def __init__(self, myConfig, verbose=True):
        self.cfg = myConfig
        self.verbose = verbose
        self.rng = random.Random(myConfig.seed)
        self.modulus = 2 ** myConfig.seqBits
        self.isGbn = myConfig.protocol == "gbn"
        limit = self.modulus - 1 if self.isGbn else self.modulus // 2
        if myConfig.window > limit:
            raise ValueError(f"window {myConfig.window} too large for "
                             f"{myConfig.protocol} with k={myConfig.seqBits}")
        self.clock = 0.0
        self.events = []
        self.tick = 0
        self.linkFree = 0.0
        self.txTime = PKT_BYTES * 8 / LINK_BPS
        self.payloads = [f"DATA-{i:05d}".encode() for i in range(myConfig.packets)]

        self.base = 0              # oldest unACKed packet (sender window start)
        self.nextseqnum = 0        # next packet to send; window = [base, base+N-1]
        self.seen = set()
        self.timerToken = 0
        self.srTokens = {}
        self.ackedSet = set()

        self.expectedseqnum = 0
        self.rcv_base = 0          # SR receiver window start
        self.rcvBuffer = {}
        self.delivered = []

        self.transmitted = 0
        self.retransmissions = 0
        self.integrityErrors = 0
        self.finished = False
        self.endTime = 0.0

    def log(self, who, text):
        if self.verbose:
            print(f"[{self.clock:9.4f}s] {who:<8} {text}")

    def schedule(self, when, kind, data):
        self.tick += 1
        heapq.heappush(self.events, (when, self.tick, kind, data))

    def passChannel(self, pkt, departAt, kind):
        tag = "DATA" if kind == "data" else "ACK"
        if self.rng.random() < self.cfg.loss:
            self.log("CHANNEL", f"{tag} seq={pkt['seq']} LOST")
            return
        pkt = dict(pkt)
        if self.rng.random() < self.cfg.corrupt:
            if kind == "data":
                body = bytearray(pkt["payload"])
                body[0] ^= 0x5A
                pkt["payload"] = bytes(body)
            else:
                pkt["seq"] = (pkt["seq"] + 1) % self.modulus
            self.log("CHANNEL", f"{tag} seq={pkt['seq']} CORRUPTED")
        lag = ONE_WAY
        if self.rng.random() < self.cfg.delay:
            extra = self.rng.uniform(*EXTRA_LAG)
            lag += extra
            self.log("CHANNEL", f"{tag} seq={pkt['seq']} DELAYED +{extra:.3f}s")
        self.schedule(departAt + lag, kind + "Arrive", pkt)

    def sendData(self, n):
        again = n in self.seen
        self.seen.add(n)
        self.transmitted += 1
        if again:
            self.retransmissions += 1
        seq = n % self.modulus
        self.log("SENDER", f"{'RETRANSMIT' if again else 'SEND'} pkt#{n} seq={seq}  "
                           f"(base={self.base}, nextseqnum={self.nextseqnum})")
        start = max(self.clock, self.linkFree)
        self.linkFree = start + self.txTime
        self.passChannel(makeData(seq, self.payloads[n]), self.linkFree, "data")

    def sendAck(self, seq):
        self.log("RECEIVER", f"SEND {'cumulative ' if self.isGbn else 'individual '}ACK {seq}")
        self.passChannel(makeAck(seq), self.clock, "ack")

    def startGbnTimer(self):
        self.timerToken += 1
        self.schedule(self.clock + self.cfg.timeout, "timeout", self.timerToken)

    def stopGbnTimer(self):
        self.timerToken += 1

    def startSrTimer(self, n):
        self.srTokens[n] = self.srTokens.get(n, 0) + 1
        self.schedule(self.clock + self.cfg.timeout, "timeout", (n, self.srTokens[n]))

    def deliver(self, n, payload):
        if payload != self.payloads[n]:
            self.integrityErrors += 1
        self.delivered.append(payload)
        self.log("RECEIVER", f"DELIVER pkt#{n} to application")

    def pump(self):
        top = min(self.base + self.cfg.window, self.cfg.packets)
        while self.nextseqnum < top:
            n = self.nextseqnum
            if self.isGbn and self.base == n:
                self.startGbnTimer()
            self.sendData(n)
            if not self.isGbn:
                self.startSrTimer(n)
            self.nextseqnum += 1

    def checkDone(self):
        if self.base >= self.cfg.packets and not self.finished:
            self.finished = True
            self.endTime = self.clock

    def onDataArrive(self, pkt):
        seq = pkt["seq"]
        if not isIntact(pkt):
            self.log("RECEIVER", f"RECV DATA seq={seq} checksum FAIL, discarded")
            if self.isGbn and self.expectedseqnum > 0:
                self.sendAck((self.expectedseqnum - 1) % self.modulus)
            return
        self.log("RECEIVER", f"RECV DATA seq={seq} ok")
        if self.isGbn:
            self.gbnReceive(pkt)
        else:
            self.srReceive(pkt)

    def gbnReceive(self, pkt):
        if pkt["seq"] == self.expectedseqnum % self.modulus:
            self.deliver(self.expectedseqnum, pkt["payload"])
            self.expectedseqnum += 1
            self.log("RECEIVER", f"expectedseqnum={self.expectedseqnum}")
            self.sendAck(pkt["seq"])
        else:
            self.log("RECEIVER", f"out-of-order seq={pkt['seq']} (expectedseqnum="
                                 f"{self.expectedseqnum % self.modulus}), discarded")
            if self.expectedseqnum > 0:
                self.sendAck((self.expectedseqnum - 1) % self.modulus)

    def srReceive(self, pkt):
        s, w = pkt["seq"], self.cfg.window
        for n in range(self.rcv_base, min(self.rcv_base + w, self.cfg.packets)):
            if n % self.modulus == s:
                if n not in self.rcvBuffer:
                    self.rcvBuffer[n] = pkt["payload"]
                    if n != self.rcv_base:
                        self.log("RECEIVER", f"buffered out-of-order pkt#{n}")
                self.sendAck(s)
                while self.rcv_base in self.rcvBuffer:
                    self.deliver(self.rcv_base, self.rcvBuffer.pop(self.rcv_base))
                    self.rcv_base += 1
                self.log("RECEIVER", f"receiver window [{self.rcv_base}, "
                                     f"{self.rcv_base + w - 1}]  rcv_base={self.rcv_base}")
                return
        for n in range(max(0, self.rcv_base - w), self.rcv_base):
            if n % self.modulus == s:
                self.log("RECEIVER", f"duplicate seq={s}, re-ACK")
                self.sendAck(s)
                return
        self.log("RECEIVER", f"seq={s} outside window, ignored")

    def onAckArrive(self, pkt):
        a = pkt["seq"]
        if not isIntact(pkt):
            self.log("SENDER", f"RECV ACK {a} checksum FAIL, ignored")
            return
        self.log("SENDER", f"RECV {'cumulative ' if self.isGbn else ''}ACK {a}")
        if self.isGbn:
            for n in range(self.base, self.nextseqnum):
                if n % self.modulus == a:
                    self.base = n + 1
                    if self.base == self.nextseqnum:
                        self.stopGbnTimer()
                    else:
                        self.startGbnTimer()
                    break
        else:
            for n in range(self.base, self.nextseqnum):
                if n % self.modulus == a:
                    self.ackedSet.add(n)
                    break
            while self.base in self.ackedSet:
                self.base += 1
        self.log("SENDER", f"sender window [{self.base}, {self.base + self.cfg.window - 1}]"
                           f"  base={self.base}")
        self.checkDone()
        self.pump()

    def onTimeout(self, data):
        if self.isGbn:
            if data != self.timerToken or self.base >= self.nextseqnum:
                return
            self.log("SENDER", f"TIMEOUT base={self.base}, resending "
                               f"{self.base}..{self.nextseqnum - 1}")
            self.startGbnTimer()
            for n in range(self.base, self.nextseqnum):
                self.sendData(n)
        else:
            n, tok = data
            if self.srTokens.get(n) != tok or n in self.ackedSet:
                return
            self.log("SENDER", f"TIMEOUT pkt#{n}")
            self.sendData(n)
            self.startSrTimer(n)

    def run(self):
        t0 = time.perf_counter()
        self.pump()
        while self.events and not self.finished:
            when, _, kind, data = heapq.heappop(self.events)
            if when > 1e5:
                break
            self.clock = when
            if kind == "dataArrive":
                self.onDataArrive(data)
            elif kind == "ackArrive":
                self.onAckArrive(data)
            else:
                self.onTimeout(data)
        wallMs = (time.perf_counter() - t0) * 1000
        simTime = self.endTime if self.finished else self.clock
        count = len(self.delivered)
        return {
            "protocol": self.cfg.protocol.upper(),
            "transmitted": self.transmitted,
            "retransmissions": self.retransmissions,
            "delivered": count,
            "integrityErrors": self.integrityErrors,
            "completed": self.finished and count == self.cfg.packets,
            "simTimeS": simTime,
            "throughputKbps": count * PKT_BYTES * 8 / simTime / 1000 if simTime else 0.0,
            "wallMs": wallMs,
        }


def runSimulation(myConfig, verbose=True):
    return Simulator(myConfig, verbose).run()


def main():
    ap = argparse.ArgumentParser(description="GBN / SR simulator")
    ap.add_argument("--protocol", choices=["gbn", "sr"], default="gbn")
    ap.add_argument("--packets", type=int, default=20)
    ap.add_argument("--window", type=int, default=4)
    ap.add_argument("--seqBits", type=int, default=3)
    ap.add_argument("--loss", type=float, default=0.0)
    ap.add_argument("--corrupt", type=float, default=0.0)
    ap.add_argument("--delay", type=float, default=0.0)
    ap.add_argument("--timeout", type=float, default=1.2)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    res = runSimulation(Config(a.protocol, a.packets, a.window, a.seqBits, a.loss,
                               a.corrupt, a.delay, a.timeout, a.seed))
    print("\nSummary:", res)


if __name__ == "__main__":
    main()
