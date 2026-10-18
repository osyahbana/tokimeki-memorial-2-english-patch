"""Snapshot private overlay evidence for an offline static compilation experiment.

Capture-derived coverage is limited to observed paths, not a release inventory.
Different byte variants remain separate; identical images retain unioned evidence.
"""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from probe_set import REVISION


def read_records(paths):
    records = {}
    evidence_fields = ("executed_pcs", "dispatch_entry_pcs", "function_entry_pcs",
                       "seeds", "static_discovery_entry_pcs")
    allowed = set(evidence_fields) | {"schema", "load_addr", "size", "guard_bytes",
                                      "bytes_b64", "dispatch_entry_segments"}
    for path in paths:
        items = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(items, list):
            raise ValueError(f"{path.name}: expected a list of capture records")
        for item in items:
            if not isinstance(item, dict):
                raise ValueError(f"{path.name}: expected an object")
            if set(item) - allowed:
                raise ValueError(f"{path.name}: unsupported evidence fields; review before merging")
            data = base64.b64decode(item["bytes_b64"], validate=True)
            size = int(item["size"])
            addr = int(item["load_addr"], 16)
            guard = item.get("guard_bytes")
            if (size != len(data) or size < 8 or size % 4 or addr % 4
                    or guard not in (0, 4) or size <= guard
                    or (addr & 0x1fffffff) + size - guard > 0x200000):
                raise ValueError(f"{path.name}: invalid image extent or guard declaration")
            for field in evidence_fields:
                values = item.get(field, [])
                if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
                    raise ValueError(f"{path.name}: invalid {field}")
            segments_in = item.get("dispatch_entry_segments", {})
            if not isinstance(segments_in, dict):
                raise ValueError(f"{path.name}: invalid segment evidence")
            for segment, entries in segments_in.items():
                if (segment not in ("kuseg", "kseg0", "kseg1")
                        or not isinstance(entries, list)
                        or not all(isinstance(v, str) for v in entries)):
                    raise ValueError(f"{path.name}: invalid dispatch segment evidence")
            # The static emitter namespaces symbols by image identity. Repeated
            # observations must be unioned or the linker gets duplicate symbols.
            identity = (addr, size, data)
            if identity not in records:
                records[identity] = item
                continue
            prior = records[identity]
            if prior["guard_bytes"] != guard or prior["schema"] != item["schema"]:
                raise ValueError("Identical image has conflicting schema or guard evidence")
            for field in evidence_fields:
                if field in prior or field in item:
                    prior[field] = sorted(set(prior.get(field, [])) | set(item.get(field, [])))
            segments = prior.setdefault("dispatch_entry_segments", {})
            for segment, entries in item.get("dispatch_entry_segments", {}).items():
                if segment not in ("kuseg", "kseg0", "kseg1"):
                    raise ValueError(f"Unknown dispatch segment: {segment}")
                segments[segment] = sorted(set(segments.get(segment, [])) | set(entries))
    if not records:
        raise ValueError("No overlay records found")
    return list(records.values())


def contextualize_entries(records):
    """Derive guarded entry candidates in byte-identical containing images.

    This is conditional code-entry reuse, not evidence that the whole containing
    variant was observed at the same time. Raw captures remain unchanged.
    """
    derived = copy.deepcopy(records)
    blobs = [base64.b64decode(r["bytes_b64"], validate=True) for r in records]
    provenance = []

    def normalized(values):
        return {f"0x{int(pc, 16):08X}" for pc in values}

    for result in derived:
        original = normalized(result.get("dispatch_entry_pcs", []))
        segments = {name: sorted(normalized(pcs))
                    for name, pcs in result.get("dispatch_entry_segments", {}).items()}
        labelled = {int(pc, 16) & 0x1fffffff for pcs in segments.values() for pc in pcs}
        implicit = {pc for pc in original if (int(pc, 16) & 0x1fffffff) not in labelled}
        if implicit:
            segments["kseg0"] = sorted(set(segments.get("kseg0", [])) | implicit)
        result["dispatch_entry_pcs"] = sorted(original)
        result["dispatch_entry_segments"] = segments
    for source_index, source in enumerate(records):
        lo = int(source["load_addr"], 16)
        hi = lo + source["size"] - source["guard_bytes"]
        entries = {pc for pc in normalized(source.get("dispatch_entry_pcs", []))
                   if lo <= int(pc, 16) < hi and int(pc, 16) % 4 == 0}
        if not entries:
            continue
        entry_phys = {int(pc, 16) & 0x1fffffff for pc in entries}
        for target_index, target in enumerate(records):
            offset = lo - int(target["load_addr"], 16)
            if (source["schema"] != target["schema"] or source["size"] >= target["size"]
                    or offset < 0 or offset + source["size"] > target["size"]
                    or hi > int(target["load_addr"], 16) + target["size"] - target["guard_bytes"]
                    or blobs[target_index][offset:offset + source["size"]] != blobs[source_index]):
                continue
            result = derived[target_index]
            before = set(result.get("dispatch_entry_pcs", []))
            segments = result.setdefault("dispatch_entry_segments", {})
            additions = {}
            # Preserve each observed segment; unlabelled entries keep the
            # compiler's documented KSEG0 interpretation. Never add aliases.
            labelled = set()
            for segment, pcs in source.get("dispatch_entry_segments", {}).items():
                keep = {pc for pc in normalized(pcs) if (int(pc, 16) & 0x1fffffff) in entry_phys}
                labelled |= {int(pc, 16) & 0x1fffffff for pc in keep}
                added = keep - set(segments.get(segment, []))
                if added:
                    additions[segment] = sorted(added)
                    segments[segment] = sorted(set(segments.get(segment, [])) | added)
            unlabelled = {pc for pc in entries if (int(pc, 16) & 0x1fffffff) not in labelled}
            added = unlabelled - set(segments.get("kseg0", []))
            if added:
                additions.setdefault("kseg0", []).extend(sorted(added))
                segments["kseg0"] = sorted(set(segments.get("kseg0", [])) | added)
            result["dispatch_entry_pcs"] = sorted(before | entries)
            if entries - before or additions:
                provenance.append({
                    "source_sha256": hashlib.sha256(blobs[source_index]).hexdigest(),
                    "source_load_addr": source["load_addr"],
                    "target_sha256": hashlib.sha256(blobs[target_index]).hexdigest(),
                    "target_load_addr": target["load_addr"],
                    "added_dispatch_entries": sorted(entries - before),
                    "added_segments": additions,
                    "basis": "Exact containment including guard bytes; conditional entry candidates only"})
    return derived, provenance


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--framework", required=True, type=Path)
    ap.add_argument("--captures", required=True, type=Path, nargs="+",
                    help="One or more private capture snapshots to merge")
    ap.add_argument("--include-history", action="store_true",
                    help="Include the adjacent .d directory after the runtime has stopped")
    ap.add_argument("--contextual-entries", action="store_true",
                    help="Derive entry candidates in byte-identical containing images")
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()
    framework, out = args.framework.resolve(), args.output.resolve()
    repo = Path(__file__).resolve().parents[2]
    if out.exists() or out.is_relative_to(repo) or repo.is_relative_to(out):
        ap.error("Choose a fresh private output directory outside the source repository")
    revision = subprocess.check_output(
        ["git", "-C", str(framework), "rev-parse", "HEAD"], text=True).strip()
    if revision != REVISION:
        ap.error("Framework revision differs from the pinned assessment")
    paths = [path.resolve() for path in args.captures]
    if args.include_history:
        for snapshot in list(paths):
            history = Path(str(snapshot) + ".d")
            if not history.is_dir():
                ap.error(f"Capture history directory is missing: {history}")
            paths.extend(sorted(history.glob("*.json")))
    try:
        records = read_records(paths)
    except (KeyError, ValueError, OSError, TypeError) as error:
        ap.error(str(error))
    out.mkdir(parents=True)
    merged = out / "captures.json"
    merged.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    compilation_input = merged
    if args.contextual_entries:
        contextual, provenance = contextualize_entries(records)
        compilation_input = out / "contextual-captures.json"
        compilation_input.write_text(json.dumps(contextual, indent=2) + "\n", encoding="utf-8")
        (out / "entry-context.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    subprocess.run([sys.executable, str(framework / "tools/enrich_overlay_captures.py"),
                    "--captures", str(compilation_input), "--out", str(out / "enriched.json")], check=True)
    summary = [{"load_addr": r["load_addr"], "size": r["size"],
                "sha256": hashlib.sha256(base64.b64decode(r["bytes_b64"])).hexdigest(),
                "dispatch_entries": len(r.get("dispatch_entry_pcs", []))} for r in records]
    inventory = {
        "framework_revision": revision,
        "scope": "Observed runtime code variants; not complete disc coverage",
        "records": summary}
    if args.contextual_entries:
        inventory["entry_context"] = {
            "mode": "conditional exact containment", "links": len(provenance),
            "added_dispatch_entries": sum(len(link["added_dispatch_entries"]) for link in provenance),
            "raw_capture_file": "captures.json", "derived_capture_file": "contextual-captures.json"}
    (out / "inventory.json").write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared {len(records)} records in {out}")


if __name__ == "__main__":
    main()
