"""Virtual-demold order search with a pluggable collision check (pure Python, no adsk).

An order is a permutation of the piece ids. At step k piece order[k] moves along its pull and is
tested against the cast and every piece not yet removed (order[k+1:]). The cast leaves last; its
release from the last piece is the last piece's test against {cast}.

Collision callback (set level): check(piece, against) -> result dict, where `against` is a tuple
(cast id first, then the remaining piece ids in input order). Result:
  {"status": "clean" | "collision" | "unknown", "against": id or None, "stepMm": float or None,
   "volumeMm3": float or None, "error": str or None}
Missing keys default to None; a bare bool is accepted (True = collision, False = clean) and None
means unknown. Results are cached per (piece, frozenset(against)).
"""
import itertools

CAST = "cast"


def _norm_result(r):
    if r is None:
        return {"status": "unknown", "against": None, "stepMm": None, "volumeMm3": None,
                "error": "no result"}
    if r is True or r is False:
        r = {"status": "collision" if r else "clean"}
    out = {"status": r.get("status", "unknown"), "against": r.get("against"),
           "stepMm": r.get("stepMm"), "volumeMm3": r.get("volumeMm3"), "error": r.get("error")}
    if out["status"] not in ("clean", "collision", "unknown"):
        out["status"] = "unknown"
    return out


def pairwise(check_pair):
    """Wrap a pair-level check(piece, other) -> result into a set-level check with its own pair cache.

    The set result is the first collision in `against` order; any unknown (with no collision) makes
    the set result unknown. Returns the wrapped function; its .pair_calls attribute counts calls.
    """
    cache = {}

    def check(piece, against):
        unknown = None
        for other in against:
            key = (piece, other)
            if key not in cache:
                wrapped.pair_calls += 1
                r = _norm_result(check_pair(piece, other))
                if r["against"] is None:
                    r["against"] = other
                cache[key] = r
            r = cache[key]
            if r["status"] == "collision":
                return r
            if r["status"] == "unknown" and unknown is None:
                unknown = r
        return unknown or {"status": "clean", "against": None, "stepMm": None, "volumeMm3": None,
                           "error": None}

    wrapped = check
    wrapped.pair_calls = 0
    return wrapped


def evaluate_order(order, check, cache=None, cast=CAST, stats=None):
    """Evaluate one removal order. Returns {"order", "status": feasible|blocked|unknown,
    "firstCollision": {"piece", "against", "step", "stepMm", "volumeMm3"} or None,
    "unknown": {"piece", "against", "step", "error"} or None}. Stops at the first collision."""
    cache = {} if cache is None else cache
    pieces = list(order)
    first_unknown = None
    for k, piece in enumerate(pieces):
        against = (cast,) + tuple(pieces[k + 1:])
        key = (piece, frozenset(against))
        if key in cache:
            if stats is not None:
                stats["cacheHits"] += 1
        else:
            if stats is not None:
                stats["calls"] += 1
            cache[key] = _norm_result(check(piece, against))
        r = cache[key]
        if r["status"] == "collision":
            return {"order": pieces, "status": "blocked",
                    "firstCollision": {"piece": piece, "against": r["against"], "step": k,
                                       "stepMm": r["stepMm"], "volumeMm3": r["volumeMm3"]},
                    "unknown": first_unknown}
        if r["status"] == "unknown" and first_unknown is None:
            first_unknown = {"piece": piece, "against": r["against"], "step": k, "error": r["error"]}
    return {"order": pieces, "status": "unknown" if first_unknown else "feasible",
            "firstCollision": None, "unknown": first_unknown}


def search_orders(pieces, check, planned=None, cast=CAST, max_pieces=5):
    """Evaluate every removal order (n! <= 120 for 5 pieces) with a shared cache.

    pieces: list of ids (input order sets the permutation order). planned: optional order to report.
    Returns {"orders": [evaluate_order results], "feasible": [[ids]], "blocked": int, "unknown": int,
             "planned": result or None, "plannedOrderOk": bool or None, "calls": int, "cacheHits": int}.
    """
    pieces = list(pieces)
    if len(pieces) > max_pieces:
        raise ValueError("too many pieces for an exhaustive search: %d > %d" % (len(pieces), max_pieces))
    if len(set(pieces)) != len(pieces) or cast in pieces:
        raise ValueError("piece ids must be unique and differ from the cast id")
    cache, stats = {}, {"calls": 0, "cacheHits": 0}
    results = [evaluate_order(p, check, cache, cast, stats) for p in itertools.permutations(pieces)]
    planned_res = None
    if planned is not None:
        if sorted(planned) != sorted(pieces):
            raise ValueError("planned order must be a permutation of the pieces")
        planned_res = next(r for r in results if r["order"] == list(planned))
    return {
        "orders": results,
        "feasible": [r["order"] for r in results if r["status"] == "feasible"],
        "blocked": sum(1 for r in results if r["status"] == "blocked"),
        "unknown": sum(1 for r in results if r["status"] == "unknown"),
        "planned": planned_res,
        "plannedOrderOk": None if planned_res is None else planned_res["status"] == "feasible",
        "calls": stats["calls"],
        "cacheHits": stats["cacheHits"],
    }


def first_collisions(search):
    """Compact per-order report lines for infeasible orders: [{order, status, piece, against, step,
    stepMm, volumeMm3}] (unknown orders carry the unknown step instead)."""
    out = []
    for r in search["orders"]:
        if r["status"] == "feasible":
            continue
        d = r["firstCollision"] or r["unknown"] or {}
        out.append({"order": r["order"], "status": r["status"], "piece": d.get("piece"),
                    "against": d.get("against"), "step": d.get("step"), "stepMm": d.get("stepMm"),
                    "volumeMm3": d.get("volumeMm3")})
    return out
