"""Time-based edits of a VTL gestural score (.ges).

VTL builds the score from a segment sequence with German-oriented rules.
Japanese needs a few changes that the seg format cannot express, so the
score is rewritten tier by tier: each tier is a sequence of gestures laid
end to end, and `paint` overwrites the interval [t0, t1) of a tier.
"""
import xml.etree.ElementTree as ET


class Tier:
    def __init__(self, node):
        self.node = node
        self.items, t = [], 0.0
        for g in node.findall("gesture"):
            d = float(g.get("duration_s"))
            self.items.append([t, t + d, dict(g.attrib)])
            t += d

    def end(self):
        return self.items[-1][1] if self.items else 0.0

    def paint(self, t0, t1, value, neutral=False, tau=None):
        """Overwrite [t0, t1) with one gesture, splitting neighbours."""
        t0, t1 = max(t0, 0.0), min(t1, self.end())
        if t1 <= t0:
            return
        out = []
        template = None
        for s, e, a in self.items:
            if e <= t0 or s >= t1:
                out.append([s, e, a])
                continue
            template = template or a
            if s < t0:
                out.append([s, t0, dict(a)])
            if e > t1:
                out.append([t1, e, dict(a)])
        a = dict(template or {"slope": "0.000000", "time_constant_s": "0.010000"})
        a["value"] = value
        a["neutral"] = "1" if neutral else "0"
        if tau is not None:
            a["time_constant_s"] = f"{tau:.6f}"
        out.append([t0, t1, a])
        self.items = sorted([x for x in out if x[1] > x[0]], key=lambda x: x[0])

    def map_values(self, t0, t1, fn):
        """Apply fn to the value of gestures whose midpoint lies in [t0, t1)."""
        for s, e, a in self.items:
            if t0 <= (s + e) / 2 < t1:
                a["value"] = fn(a["value"])

    def write(self):
        for g in list(self.node):
            self.node.remove(g)
        for s, e, a in self.items:
            a = dict(a)
            a["duration_s"] = f"{e - s:.6f}"
            ET.SubElement(self.node, "gesture", a)


class Score:
    def __init__(self, path):
        self.path = path
        self.tree = ET.parse(path)
        self.tiers = {n.get("type"): Tier(n) for n in self.tree.getroot().findall("gesture_sequence")}

    def __getitem__(self, name):
        return self.tiers[name]

    def save(self, path=None):
        for t in self.tiers.values():
            t.write()
        self.tree.write(path or self.path)
