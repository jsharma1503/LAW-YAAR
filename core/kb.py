"""Load the curated knowledge base and pick the entries for an area (exact filter — no embeddings needed at 28 entries)."""
import re
from functools import lru_cache
from pathlib import Path

import yaml

KB_PATH = Path(__file__).resolve().parent.parent / "kb" / "knowledge_base.yaml"
AREAS = ("deposit", "consumer", "salary")
STATE_SPECIFIC = {"up_tenancy_11": ["uttar pradesh", "u.p", "lucknow", "kanpur", "varanasi", "noida", "ghaziabad", "prayagraj",
                                    "allahabad", "agra", "meerut", "gorakhpur", "bareilly", "उत्तर प्रदेश", "लखनऊ", "वाराणसी"],
                  "tn_tenancy_11": ["tamil nadu", "chennai", "coimbatore", "madurai", "trichy", "salem", "तमिलनाडु"]}


@lru_cache(maxsize=1)
def load() -> dict:
    data = yaml.safe_load(KB_PATH.read_text(encoding="utf-8"))
    return {e["id"]: e for e in data["entries"]}


def for_area(area: str, place: str | None = None, notice: bool = False) -> list[dict]:
    """Entries for one area (+ notice entries if the user received a notice, + referral). State laws only for that state."""
    want = {area, "referral"} | ({"notice"} if notice else set())
    place_l = (place or "").lower()
    out = []
    for e in load().values():
        if e["category"] not in want and not want.intersection(e.get("also", [])):
            continue
        if e["id"] in STATE_SPECIFIC and not any(w in place_l for w in STATE_SPECIFIC[e["id"]]) and place_l.strip() != "up":
            continue
        out.append(e)
    return out


def for_prompt(entries: list[dict]) -> str:
    lines = []
    for e in entries:
        sec = str(e.get("section"))
        head = f"[KB:{e['id']}] {e['title']} — {e['act']}" + ("" if sec in ("none", "process", "status", "model", "rules") else f", {sec}")
        parts = [head, f"  Says: {e['summary']}"]
        for k, label in (("forum", "Where"), ("time_limit", "Time limit"), ("notes", "Note")):
            if e.get(k):
                parts.append(f"  {label}: {e[k]}")
        if e.get("documents"):
            parts.append(f"  Documents: {', '.join(e['documents'])}")
        parts.append(f"  Confidence: {e['confidence']}")
        lines.append("\n".join(parts))
    return "\n\n".join(lines)


def allowed_act_names() -> set[str]:
    return {_norm(e["act"]) for e in load().values()}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9ऀ-ॿ]", "", s.lower())
