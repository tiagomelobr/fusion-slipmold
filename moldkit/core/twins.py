"""Twin pieces, T1 (pure Python, no adsk): plaster pieces that a half turn about the mold axis maps onto each
other share one casing.

S5 (mold_twinPieces 'auto') lays the natches out so side2 is side1 turned half a turn, compares the finished
pieces and then writes mold.json pieces[].twinOf on the copy ("side2" -> "side1") and "twins" (status, the
measured differences). Downstream a copy gets no casing, clips or print files of its own: S7 builds the master's
casing, labels it "x2", and the process sheet says to cast it once per piece (or to print the set twice to pour
both at once). The plaster pieces themselves are all still there (S6 demolds them, the batch counts them).
"""


def copies(mold):
    """{copy id: master id} from mold.json pieces; none after a failed S5 run (its pieces are not trusted)."""
    if (mold or {}).get("s5Status") not in (None, "pass", "warn"):
        return {}
    return {q["id"]: q["twinOf"] for q in (mold or {}).get("pieces") or [] if q.get("id") and q.get("twinOf")}


def casing_pieces(mold):
    """Ids of the pieces that get a casing, in mold.json order: every piece but the twin copies."""
    tw = copies(mold)
    return [q["id"] for q in (mold or {}).get("pieces") or [] if q.get("id") and q["id"] not in tw]


def casts(mold):
    """{casing piece id: [piece ids its casing casts, itself first]} for every casing piece."""
    out = {pid: [pid] for pid in casing_pieces(mold)}
    for c, m in copies(mold).items():
        if m in out:
            out[m].append(c)
    return out


def shared(mold):
    """{master id: [master, copies...]} for the casings that cast more than one piece."""
    return {k: v for k, v in casts(mold).items() if len(v) > 1}


def label_id(part_id, n):
    """Part name for the engraved label: a casing that casts n > 1 pieces gets " x<n>" ("side1 core x2")."""
    return part_id if n <= 1 else "%s x%d" % (part_id, n)


def describe(mold):
    """One line for reports: "side2 = side1 turned 180 deg: one casing casts both", or None without twins."""
    sh = shared(mold)
    if not sh:
        return None
    return "; ".join("%s = %s turned 180 deg: one casing casts %s" % (
        " and ".join(v[1:]), k, "both" if len(v) == 2 else "all %d" % len(v)) for k, v in sh.items())
