"""T22 — canvas scene-graph serialization: diagram -> structured text.

Input: the shape list posted by the frontend in canvas_snapshot events
(tldraw-derived: {id, kind, label, x, y} boxes/shapes and
{id, kind:'arrow', from, to, label} edges). Output: the @canvas_observation
block — the model discusses the diagram with zero vision cost.
"""

from typing import Any


def serialize_scene(shapes: list[dict[str, Any]]) -> dict[str, Any]:
    nodes, edges, unlabeled = [], [], 0
    by_id = {s.get("id"): s for s in shapes}
    for s in shapes:
        kind = s.get("kind", "shape")
        if kind == "arrow":
            src = by_id.get(s.get("from"), {}).get("label") or s.get("from") or "?"
            dst = by_id.get(s.get("to"), {}).get("label") or s.get("to") or "?"
            edges.append({"from": src, "to": dst, "label": s.get("label") or ""})
        else:
            label = (s.get("label") or "").strip()
            if not label:
                unlabeled += 1
            nodes.append({"id": s.get("id"), "kind": kind, "label": label or "(unlabeled)"})
    return {"nodes": nodes, "edges": edges, "unlabeled": unlabeled}


def labels(shapes: list[dict[str, Any]]) -> list[str]:
    return [
        (s.get("label") or "").strip()
        for s in shapes
        if s.get("kind") != "arrow" and (s.get("label") or "").strip()
    ]


def scene_diff(old: list[dict[str, Any]], new: list[dict[str, Any]]) -> str:
    old_by_id = {s.get("id"): s for s in old}
    new_by_id = {s.get("id"): s for s in new}
    parts = []
    for sid in new_by_id.keys() - old_by_id.keys():
        parts.append(f"+ {new_by_id[sid].get('label') or new_by_id[sid].get('kind')}")
    for sid in old_by_id.keys() - new_by_id.keys():
        parts.append(f"- {old_by_id[sid].get('label') or old_by_id[sid].get('kind')}")
    for sid in new_by_id.keys() & old_by_id.keys():
        o, n = old_by_id[sid].get("label"), new_by_id[sid].get("label")
        if o != n:
            parts.append(f"relabeled {o!r} -> {n!r}")
    return "; ".join(parts)


def observation_block(
    shapes: list[dict[str, Any]], prev_shapes: list[dict[str, Any]] | None = None
) -> str:
    scene = serialize_scene(shapes)
    lines = ["@canvas_observation"]
    if scene["nodes"]:
        lines.append(
            "nodes: "
            + ", ".join(f"[{n['kind']}] {n['label']}" for n in scene["nodes"][:30])
        )
    else:
        lines.append("nodes: (canvas is empty)")
    if scene["edges"]:
        lines.append(
            "edges: "
            + ", ".join(
                f"{e['from']} -> {e['to']}" + (f" ({e['label']})" if e["label"] else "")
                for e in scene["edges"][:30]
            )
        )
    if scene["unlabeled"]:
        lines.append(f"unlabeled_shapes: {scene['unlabeled']}")
    if prev_shapes is not None:
        diff = scene_diff(prev_shapes, shapes)
        if diff:
            lines.append("diff_since_last: " + diff)
    return "\n".join(lines)
