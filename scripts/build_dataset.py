#!/usr/bin/env python3
# -*- coding: ascii -*-
"""C6A dataset builder.

Reads the raw platform exports (list-challenges / list-my-submissions),
normalises them into a clean dataset, and recomputes every metric that the
dashboard displays. Nothing is hard-coded: all numbers come from the exports.

Usage:
    python scripts/build_dataset.py --src <dir with audit_*.json> --out data

Design notes
------------
* Pure ASCII source (this machine's Python console crashes on non-ASCII source
  literals). Chinese text is only ever read from the JSON inputs and written
  back out as UTF-8 data.
* Only ASCII status lines are printed to stdout; details are in the JSON files.
"""

import argparse
import datetime as dt
import json
import os
import sys

IGNORE_CHALLENGE_IDS = {"ch-20260904104535-14aac163"}  # T0 publish-flow test
SNAPSHOT_DATE = dt.date(2026, 11, 23)
STUDENT_ID = "2023108610260"  # platform identity, echoed in payload.meta for provenance
SIX_DAY_FLOOR = SNAPSHOT_DATE - dt.timedelta(days=5)  # window = snapshot + 5 prior days


def first_json_line(path):
    """The exports wrap JSON on line 1 followed by '--- STDERR ---' notes."""
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line.startswith("{"):
                return json.loads(line)
    raise SystemExit("no json found in %s" % path)


def parse_iso(value):
    if not value:
        return None
    v = value.replace("Z", "+00:00")
    try:
        return dt.datetime.fromisoformat(v)
    except ValueError:
        return None


def week_start(d):
    return d - dt.timedelta(days=d.weekday())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    chal_raw = first_json_line(os.path.join(args.src, "audit_challenges.json"))
    subs_raw = first_json_line(os.path.join(args.src, "audit_subs.json"))

    challenges = []
    for c in chal_raw["challenges"]:
        cid = c["challenge_id"]
        code = c["title"].split(" ")[0]
        challenges.append({
            "id": cid,
            "code": code,
            "title": c["title"],
            "status": c["status"],
            "deadline": c.get("deadline", ""),
            "required_deliverables": c.get("required_deliverables", ""),
            "is_test": cid in IGNORE_CHALLENGE_IDS,
        })

    submissions = []
    for s in subs_raw["submissions"]:
        ts = parse_iso(s.get("submitted_at"))
        submissions.append({
            "submission_id": s["submission_id"],
            "challenge_id": s["challenge_id"],
            "project_title": s.get("project_title", ""),
            "github_repo_url": s.get("github_repo_url", ""),
            "status": s.get("status", ""),
            "task_state": s.get("task_state", ""),
            "submitted_at": s.get("submitted_at", ""),
            "submitted_date": ts.date().isoformat() if ts else "",
            "week_start": week_start(ts.date()).isoformat() if ts else "",
        })

    by_cid = {c["id"]: c for c in challenges}
    for s in submissions:
        c = by_cid.get(s["challenge_id"], {})
        s["code"] = c.get("code", "?")

    active = [c for c in challenges if not c["is_test"]]
    ignored = [c for c in challenges if c["is_test"]]
    submitted_ids = {s["challenge_id"] for s in submissions}
    submitted_active = [c for c in active if c["id"] in submitted_ids]
    not_submitted = [c for c in active if c["id"] not in submitted_ids]

    status_dist = {}
    for s in submissions:
        status_dist[s["status"]] = status_dist.get(s["status"], 0) + 1
    # The platform returns task_state=null on needs_revision records (verified
    # in the raw export). Do NOT fall back to status here: that would invent a
    # task_state the server never sent. Null is recorded explicitly so the gap
    # stays visible in the dashboard instead of being papered over.
    task_state_dist = {}
    for s in submissions:
        key = s["task_state"] if s["task_state"] else "(null)"
        task_state_dist[key] = task_state_dist.get(key, 0) + 1

    pending = []
    for s in submissions:
        if s["status"] == "checked":
            d = dt.date.fromisoformat(s["submitted_date"]) if s["submitted_date"] else None
            age = (SNAPSHOT_DATE - d).days if d else None
            pending.append({
                "code": s["code"],
                "submission_id": s["submission_id"],
                "submitted_date": s["submitted_date"],
                "age_days": age,
            })
    pending.sort(key=lambda x: -(x["age_days"] or 0))

    weekly = {}
    for s in submissions:
        if not s["week_start"]:
            continue
        weekly.setdefault(s["week_start"], []).append(s["code"])
    weekly_buckets = [
        {"week_start": k, "count": len(v), "codes": sorted(v)}
        for k, v in sorted(weekly.items())
    ]

    by_day = {}
    for s in submissions:
        if s["submitted_date"]:
            by_day[s["submitted_date"]] = by_day.get(s["submitted_date"], 0) + 1

    deadlines = [c["deadline"][:10] for c in active if c["deadline"]]
    nearest_deadline = min(deadlines) if deadlines else ""
    remaining_days = None
    if nearest_deadline:
        remaining_days = (dt.date.fromisoformat(nearest_deadline) - SNAPSHOT_DATE).days

    total_subs = len(submissions)
    derived = {
        "snapshot_date": SNAPSHOT_DATE.isoformat(),
        "total_challenges": len(challenges),
        "ignored_test_challenges": len(ignored),
        "active_challenges": len(active),
        "submitted_challenges": len(submitted_active),
        "coverage_pct": round(100.0 * len(submitted_active) / len(active), 1) if active else 0.0,
        "not_submitted_codes": [c["code"] for c in not_submitted],
        "not_submitted_titles": [c["title"] for c in not_submitted],
        "submission_records": total_subs,
        "distinct_challenges_in_records": len(submitted_ids),
        "records_per_challenge": round(total_subs / len(submitted_ids), 2) if submitted_ids else 0.0,
        "status_distribution": status_dist,
        "task_state_distribution": task_state_dist,
        "pending_teacher_review": len(pending),
        "teacher_review_completed": status_dist.get("completed", 0),
        "needs_revision": status_dist.get("needs_revision", 0),
        "oldest_pending_age_days": pending[0]["age_days"] if pending else None,
        "pending_queue": pending,
        "weekly_buckets": weekly_buckets,
        "busiest_day": max(by_day.items(), key=lambda kv: kv[1])[0] if by_day else "",
        "busiest_day_count": max(by_day.values()) if by_day else 0,
        "last_six_days_count": sum(v for k, v in by_day.items() if k >= SIX_DAY_FLOOR.isoformat()),
        "nearest_deadline": nearest_deadline,
        "deadline_remaining_days": remaining_days,
    }

    os.makedirs(args.out, exist_ok=True)

    def dump(name, obj):
        path = os.path.join(args.out, name)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(obj, fh, ensure_ascii=False, indent=2, sort_keys=False)
            fh.write("\n")
        return path

    dump("challenges.json", {"snapshot_date": SNAPSHOT_DATE.isoformat(),
                             "source": "list-challenges", "items": challenges})
    dump("submissions.json", {"snapshot_date": SNAPSHOT_DATE.isoformat(),
                              "source": "list-my-submissions", "items": submissions})
    dump("derived.json", derived)
    dump("payload.json", {
        "meta": {
            "snapshot": SNAPSHOT_DATE.isoformat(),
            "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
            "student_id": STUDENT_ID,
            "sources": ["list-challenges", "list-my-submissions"],
            "note": "null task_state is preserved as an empty value in "
                    "payload.submissions[].state; the dashboard renders it as "
                    "\u672a\u56de\u586b instead of substituting status.",
        },
        "challenges": [{"id": c["id"], "code": c["code"], "title": c["title"],
                        "deadline": c["deadline"], "req": c["required_deliverables"],
                        "test": c["is_test"]} for c in challenges],
        "submissions": [{"code": s["code"], "cid": s["challenge_id"],
                         "sid": s["submission_id"], "status": s["status"],
                         "state": s["task_state"], "day": s["submitted_date"],
                         "week": s["week_start"], "repo": s["github_repo_url"]}
                        for s in submissions],
    })

    print("OK total_challenges=%d active=%d submitted=%d coverage=%.1f%%"
          % (len(challenges), len(active), len(submitted_active), derived["coverage_pct"]))
    print("OK records=%d pending=%d needs_revision=%d oldest_pending_days=%s"
          % (total_subs, derived["pending_teacher_review"], derived["needs_revision"],
             derived["oldest_pending_age_days"]))
    print("OK weeks=%d busiest_day=%s(%d) last6=%d"
          % (len(weekly_buckets), derived["busiest_day"], derived["busiest_day_count"],
             derived["last_six_days_count"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
