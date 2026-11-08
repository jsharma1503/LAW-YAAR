"""Practice mode: the model plays the other side (fast model); a coach gives feedback at the end."""
import json

from core import guard, lang, llm, prompts


def role(state: dict) -> str:
    op = (state.get("case") or {}).get("other_party") or {}
    return f"{op['name']} ({op['type']})" if op.get("name") and op.get("type") else (op.get("name") or f"the {op.get('type') or 'other party'}")


def reply(state: dict, history: list[dict]) -> str:
    case = state.get("case") or {}
    situation = json.dumps({k: case.get(k) for k in ("summary_one_line", "amount_inr", "timeline", "desired_outcome")}, ensure_ascii=False)
    system = prompts.PRACTICE.format(role=role(state), situation=situation, lang_name=lang.NAMES[state.get("language", "en")])
    text = llm.chat([{"role": "system", "content": system}] + history, fast=True, temperature=0.7, max_tokens=300)
    return guard.check_and_render(text, markdown_links=False)[0]


def feedback(state: dict, history: list[dict]) -> dict:
    convo = "\n".join(f"{'USER' if m['role'] == 'user' else 'OTHER SIDE'}: {m['content']}" for m in history)
    system = prompts.PRACTICE_FEEDBACK.format(role=role(state), lang_name=lang.NAMES[state.get("language", "en")])
    return llm.chat_json([{"role": "system", "content": system}, {"role": "user", "content": convo}], fast=True, max_tokens=600)
