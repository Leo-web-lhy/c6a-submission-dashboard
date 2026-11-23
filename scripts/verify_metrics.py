#!/usr/bin/env python3
"""C6A metric verifier.

Recomputes every headline metric straight from the shipped inputs
(data/challenges.json + data/submissions.json) with its own arithmetic, then
diffs the result against data/derived.json and data/payload.json.

Purpose: a dashboard whose numbers are pasted in cannot be audited. This script
is the audit. Any drift exits non-zero.

Usage:
  python scripts/verify_metrics.py --data data

Exit codes:
  0  all recomputed metrics match the shipped derived/payload files
  2  inputs unreadable
  7  metric mismatch (drift) or structural inconsistency
"""

import argparse
import datetime as dt
import io
import json
import os
import sys

FAILS = []


def load(path):
    try:
        with io.open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("FAIL cannot read %s: %s\n" % (path, exc))
        sys.exit(2)


def d(s):
    return dt.date(int(s[0:4]), int(s[5:7]), int(s[8:10]))


def check(name, got, want):
    ok = got == want
    print("%s %-34s got=%s want=%s" % ("OK  " if ok else "DIFF", name, got, want))
    if not ok:
        FAILS.append(name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data")
    args = ap.parse_args()

    ch = load(os.path.join(args.data, "challenges.json"))
    sb = load(os.path.join(args.data, "submissions.json"))
    dv = load(os.path.join(args.data, "derived.json"))
    pl = load(os.path.join(args.data, "payload.json"))

    snap_s = ch["snapshot_date"]
    check("snapshot_date", snap_s, sb["snapshot_date"])
    snap = d(snap_s)

    items = ch["items"]
    subs = sb["items"]

    active = [c for c in items if not c.get("is_test")]
    tests = [c for c in items if c.get("is_test")]
    subs_of = {}
    for s in subs:
        subs_of.setdefault(s["challenge_id"], []).append(s)

    # duplicate submissions for one challenge would silently inflate coverage
    dup = {k: len(v) for k, v in subs_of.items() if len(v) > 1}
    check("challenges_per_submission_max", max([len(v) for v in subs_of.values()] or [0]), 1)
    unknown = [c for c in subs_of if c not in {x["id"] for x in items}]
    check("submissions_with_unknown_challenge", len(unknown), 0)

    check("total_challenges", len(items), dv["total_challenges"])
    check("ignored_test_challenges", len(tests), dv["ignored_test_challenges"])
    check("active_challenges", len(active), dv["active_challenges"])
    check("submitted_challenges", len(subs_of), dv["submitted_challenges"])
    cov = round(100.0 * len(subs_of) / len(active), 1)
    check("coverage_pct", cov, dv["coverage_pct"])

    miss = sorted(c["code"] for c in active if c["id"] not in subs_of)
    check("not_submitted_codes", miss, sorted(dv["not_submitted_codes"]))

    n_rec = len(subs)
    check("submission_records", n_rec, dv["submission_records"])
    check("distinct_challenges_in_records", len(subs_of), dv["distinct_challenges_in_records"])
    check("records_per_challenge", round(n_rec / len(subs_of), 1), dv["records_per_challenge"])

    # Platform sends task_state=null for needs_revision records. Both the
    # builder and this verifier use the same explicit marker "(null)"; neither
    # may substitute status, which would fabricate a server field.
    def ts_key(v):
        return v if v else "(null)"

    st = {}
    ts = {}
    for s in subs:
        st[s["status"]] = st.get(s["status"], 0) + 1
        ts[ts_key(s["task_state"])] = ts.get(ts_key(s["task_state"]), 0) + 1
    check("status_distribution", st, dv["status_distribution"])
    check("task_state_distribution", ts, dv["task_state_distribution"])
    check("pending_teacher_review", st.get("checked", 0), dv["pending_teacher_review"])
    check("teacher_review_completed", st.get("completed", 0), dv["teacher_review_completed"])
    check("needs_revision", st.get("needs_revision", 0), dv["needs_revision"])

    # a challenge is only "teacher-reviewed" if it left pending_teacher_review
    pend = [s for s in subs if s["status"] == "checked"]
    ages = {s["code"]: (snap - d(s["submitted_date"])).days for s in pend}
    oldest = max(ages.values()) if ages else 0
    check("oldest_pending_age_days", oldest, dv["oldest_pending_age_days"])
    oldest_code = [k for k, v in ages.items() if v == oldest][0] if ages else None
    dv_oldest = max(dv["pending_queue"], key=lambda x: x["age_days"])
    check("oldest_pending_code", oldest_code, dv_oldest["code"])

    # each queue row must be re-derivable from the raw record
    okl = 0
    by_code = {s["code"]: s for s in subs}
    for row in dv["pending_queue"]:
        s = by_code.get(row["code"])
        if s and s["submitted_date"] == row["submitted_date"] and (
                snap - d(s["submitted_date"])).days == row["age_days"]:
            okl += 1
    check("pending_queue_rows_reverified", okl, len(dv["pending_queue"]))
    check("pending_queue_len", len(dv["pending_queue"]), len(pend))

    wk = {}
    for s in subs:
        wk[s["week_start"]] = wk.get(s["week_start"], 0) + 1
    dv_wk = {w["week_start"]: w["count"] for w in dv["weekly_buckets"]}
    check("weekly_bucket_counts", wk, dv_wk)
    check("weekly_bucket_total", sum(wk.values()), n_rec)

    day = {}
    for s in subs:
        day[s["submitted_date"]] = day.get(s["submitted_date"], 0) + 1
    bd = sorted(day.items(), key=lambda kv: (-kv[1], kv[0]))[0]
    check("busiest_day", bd[0], dv["busiest_day"])
    check("busiest_day_count", bd[1], dv["busiest_day_count"])

    n6 = sum(1 for s in subs if (snap - d(s["submitted_date"])).days <= 5)
    check("last_six_days_count", n6, dv["last_six_days_count"])

    dl = min((d(c["deadline"][:10]), c["code"]) for c in active)
    check("nearest_deadline", dl[0].isoformat(), dv["nearest_deadline"])
    check("deadline_remaining_days", (dl[0] - snap).days, dv["deadline_remaining_days"])

    # payload must agree with the same inputs (dashboard reads payload, not derived)
    check("payload_submissions_len", len(pl["submissions"]), n_rec)
    check("payload_challenges_len", len(pl["challenges"]), len(items))
    check("payload_snapshot", pl["meta"]["snapshot"], snap_s)
    pl_codes = sorted({s["code"] for s in pl["submissions"]})
    check("payload_codes", pl_codes, sorted(s["code"] for s in subs))
    # payload carries every challenge including the test one; derived's
    # not_submitted_codes is active-only, so compare on the same basis.
    pl_miss = sorted(c["code"] for c in pl["challenges"] if not c["test"] and c["id"] not in
                     {s["cid"] for s in pl["submissions"]})
    check("payload_not_submitted", pl_miss, miss)

    if dup:
        print("NOTE challenges with >1 submission record: %s" % sorted(dup))
    print("---")
    if FAILS:
        sys.stderr.write("FAIL drift in %d metric(s): %s\n" % (len(FAILS), ",".join(FAILS)))
        return 7
    print("OK all metrics recomputed and matched (%d checks)" % CHECKS[0])
    return 0


CHECKS = [0]

if __name__ == "__main__":
    # count checks by wrapping print of OK/DIFF lines
    _orig = check

    def check(name, got, want, _c=[0]):
        _c[0] += 1
        CHECKS[0] = _c[0]
        return _orig(name, got, want)

    sys.exit(main())
