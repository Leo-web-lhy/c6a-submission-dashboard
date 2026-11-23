#!/usr/bin/env python3
# -*- coding: ascii -*-
"""C6A dashboard renderer.

Inlines data/payload.json into template/dashboard.template.html and writes a
single self-contained HTML file (no network, no CDN, no build step).

Usage:
  python scripts/render_dashboard.py --data data --out output/dashboard.html

Exit codes:
  0  rendered and self-checks passed
  2  input missing / unreadable
  7  output failed content checks (placeholder left, too small, data absent)
"""

import argparse
import io
import json
import os
import re
import sys

PLACEHOLDER = "/*__DATA__*/"
MIN_BYTES = 20000
MIN_RECORDS = 1


def die(code, msg):
    sys.stderr.write("FAIL " + msg + "\n")
    sys.exit(code)


def load_json(path):
    try:
        with io.open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:  # noqa: BLE001
        die(2, "cannot read %s: %s" % (path, exc))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", default=os.path.join("template", "dashboard.template.html"))
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default=os.path.join("output", "dashboard.html"))
    args = ap.parse_args()

    payload_path = os.path.join(args.data, "payload.json")
    if not os.path.isfile(args.template):
        die(2, "template not found: " + args.template)
    if not os.path.isfile(payload_path):
        die(2, "payload not found: " + payload_path)

    payload = load_json(payload_path)
    if not isinstance(payload, dict) or "submissions" not in payload or "challenges" not in payload:
        die(2, "payload missing submissions/challenges keys")
    if len(payload["submissions"]) < MIN_RECORDS:
        die(7, "payload submissions empty")

    with io.open(args.template, "r", encoding="utf-8") as fh:
        tpl = fh.read()
    if PLACEHOLDER not in tpl:
        die(7, "template placeholder missing: " + PLACEHOLDER)

    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    blob = blob.replace("</", "<\\/")  # never allow a stray </script>
    html = tpl.replace(PLACEHOLDER, "const DATA = " + blob + ";")

    out_dir = os.path.dirname(args.out)
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    with io.open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(html)

    # ---- content self-checks (a green exit code alone proves nothing) ----
    with io.open(args.out, "r", encoding="utf-8") as fh:
        back = fh.read()
    size = os.path.getsize(args.out)
    problems = []
    if PLACEHOLDER in back:
        problems.append("placeholder still present")
    if size < MIN_BYTES:
        problems.append("output too small: %d bytes" % size)
    if "const DATA = " not in back:
        problems.append("data not inlined")
    # every challenge code the dataset knows about must appear in the payload
    codes = set()
    for s in payload["submissions"]:
        if s.get("code"):
            codes.add(s["code"])
    missing = [c for c in codes if c not in blob]
    if missing:
        problems.append("codes missing from payload: " + ",".join(sorted(missing)))
    # the runtime render entry point must be reachable
    if "render()" not in back:
        problems.append("render() call missing")
    # no external resource references (single-file guarantee)
    ext = re.findall(r'(?:src|href)\s*=\s*["\'](?:https?:)?//', back)
    if ext:
        problems.append("external resource reference found: %d" % len(ext))

    if problems:
        die(7, "; ".join(problems))

    print("OK rendered %s bytes=%d submissions=%d challenges=%d"
          % (args.out, size, len(payload["submissions"]), len(payload["challenges"])))
    print("OK inline_data codes=%d external_refs=0" % len(codes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
