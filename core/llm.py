"""The only place that talks to Groq.

Chat: LangChain's ChatGroq. Speech: Groq Whisper via the groq SDK.
"""
import json
import re
from functools import lru_cache

from core import config


class LLMError(RuntimeError):
    pass


@lru_cache(maxsize=8)
def _client(model: str, temperature: float, max_tokens: int, json_mode: bool):
    from langchain_groq import ChatGroq
    kw = {"model": model, "temperature": temperature, "max_tokens": max_tokens, "max_retries": 3, "timeout": 120}
    if model.startswith("openai/gpt-oss"):
        kw["reasoning_effort"] = "low"      # faster and cheaper; the knowledge base carries the legal facts
    llm = ChatGroq(**kw)
    return llm.bind(response_format={"type": "json_object"}) if json_mode else llm


def chat(messages, fast=False, temperature=0.2, max_tokens=1500, config_=None) -> str:
    model = config.FAST_MODEL if fast else config.MODEL
    try:
        out = _client(model, temperature, max_tokens, False).invoke(messages, config=config_)
    except Exception as e:
        raise LLMError(_explain(e)) from e
    return (out.content or "").strip()


def chat_json(messages, fast=False, temperature=0.2, max_tokens=2500, config_=None) -> dict:
    model = config.FAST_MODEL if fast else config.MODEL
    try:
        raw = _client(model, temperature, max_tokens, True).invoke(messages, config=config_).content
    except Exception as e:
        raise LLMError(_explain(e)) from e
    try:
        return parse_json(raw)
    except Exception:  # one repair attempt
        repair = list(messages) + [{"role": "assistant", "content": raw},
                                   {"role": "user", "content": "That was not valid JSON. Return ONLY the corrected JSON object."}]
        try:
            return parse_json(_client(model, 0.0, max_tokens, True).invoke(repair, config=config_).content)
        except Exception as e:
            raise LLMError(f"The model did not return valid JSON: {e}") from e


def parse_json(text: str) -> dict:
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", (text or "").strip())
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        a, b = t.find("{"), t.rfind("}")
        if a != -1 and b > a:
            return json.loads(t[a:b + 1])
        raise


def transcribe(audio: bytes, filename: str = "voice.wav") -> str:
    from groq import Groq
    try:
        r = Groq().audio.transcriptions.create(file=(filename, audio), model=config.STT_MODEL, temperature=0.0)
    except Exception as e:
        raise LLMError(_explain(e)) from e
    return (r.text or "").strip()


def _explain(e: Exception) -> str:
    s = str(e)
    if "401" in s or "invalid_api_key" in s.lower():
        return "Groq rejected the API key. Check GROQ_API_KEY."
    if "429" in s or "rate_limit" in s.lower():
        return "Groq free-tier limit reached (tokens per minute/day). Wait a minute and try again."
    return f"Groq call failed: {s[:300]}"
