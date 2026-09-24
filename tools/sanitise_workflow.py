#!/usr/bin/env python3
"""
Strip instance identifiers from an n8n workflow export before publishing it.

WHY THIS IS A SCRIPT AND NOT A CAREFUL READ-THROUGH
---------------------------------------------------
An n8n export carries more than the workflow. It also carries a fingerprint of
the machine that made it, the internal id of every credential the nodes use,
and - the dangerous one - `pinData`, which stores the captured output of any
pinned node verbatim. On a workflow that has touched real mail or real customer
records, pinned data is the actual content, sitting in a file that looks like
configuration.

What gets removed, and why:

    meta.instanceId   a stable fingerprint of this n8n install
    versionId         internal revision pointer, useless outside the instance
    id                the workflow's id on this instance, plus node-level ids
    tags              local organisation, sometimes named after clients
    pinData           captured node output - the one that leaks real data
    credentials[].id  the credential's internal id; the NAME is kept, because
                      whoever imports this needs to know what to create

An API key should never appear in an export in the first place: it belongs in a
credential, and a credential's secret is not part of the export. But a key typed
directly into a header field WOULD appear here, and this script cannot know
that - it only removes the fields it was written to remove. So the rule that
matters is the one this script does not enforce:

    READ THE EXPORTED FILE IN FULL BEFORE COMMITTING IT.

That habit is what caught `05b · Human review` shipping with no fields set - a
node that looked correct on the canvas, ran green, and did nothing.

Usage:
    python3 tools/sanitise_workflow.py "~/Downloads/My Workflow.json" \\
        workflows/jev-triage-benchmark.json
"""

import argparse
import json
import sys
from pathlib import Path

STRIP_TOP = ("id", "versionId", "meta", "tags", "pinData")
STRIP_NODE = ("id",)


def scrub(workflow):
    removed = []

    for key in STRIP_TOP:
        if key in workflow:
            # pinData is kept as an empty object rather than deleted: its
            # absence and its emptiness look the same to a reader, and an
            # explicit {} says "checked, nothing pinned".
            if key == "pinData":
                if workflow[key]:
                    removed.append(f"pinData ({len(workflow[key])} pinned node(s))")
                workflow[key] = {}
            else:
                workflow.pop(key)
                removed.append(key)

    for node in workflow.get("nodes", []):
        for key in STRIP_NODE:
            node.pop(key, None)
        for cred in (node.get("credentials") or {}).values():
            if cred.pop("id", None):
                removed.append(f"credential id on {node.get('name')}")

    return workflow, removed


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source")
    ap.add_argument("dest")
    args = ap.parse_args()

    src = Path(args.source).expanduser()
    if not src.exists():
        sys.exit(f"{src} not found")

    workflow = json.loads(src.read_text(encoding="utf-8"))
    workflow, removed = scrub(workflow)

    dest = Path(args.dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(workflow, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"{src.name}  ->  {dest}")
    for item in removed:
        print(f"  removed  {item}")
    print(f"\n  credentials still referenced by name (expected):")
    for node in workflow.get("nodes", []):
        for kind, cred in (node.get("credentials") or {}).items():
            print(f"    {node['name']}  ->  {kind}: {cred.get('name')!r}")
    print("\nNow read the output file in full before committing it.")


if __name__ == "__main__":
    main()
