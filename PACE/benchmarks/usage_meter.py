"""把客户端可见文本和供应方 usage 并列记录；不保存请求、回答或凭据正文。"""
from functools import lru_cache
import hashlib
import json

from pace.providers.encoding import VisibleWindowCounter, load_count_tokenizer
from pace.providers.api import usage_fields


@lru_cache(maxsize=2)
def local_meter(tokenizer_path):
    if not tokenizer_path.is_file():
        return None
    try:
        return VisibleWindowCounter(load_count_tokenizer(tokenizer_path))
    except ImportError:
        return None


def chat_measurements(body, response, meter):
    messages = body.get("messages")
    if not isinstance(messages, list):
        return {}
    usage = usage_fields(response)
    out = {"response_id":response.get("id"), "requested_model":body.get("model"),
           "response_model":response.get("model")}
    missing = [k for k in ("prompt_tokens","completion_tokens","total_tokens")
               if type(usage.get(k)) is not int or usage[k] < 0 or (k == "prompt_tokens" and usage[k] == 0)]
    if missing:
        out["gateway_usage_missing"] = missing
    else:
        out["gateway_total_matches_parts"] = usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]
    details = usage.get("prompt_tokens_details")
    if isinstance(details, dict):
        out["prompt_cache_details"] = {k: details[k] for k in ("cached_tokens","cached_creation_tokens")
                                       if type(details.get(k)) is int}
    serialized = json.dumps(messages, ensure_ascii=False, separators=(",", ":"))
    out["messages_sha256"] = hashlib.sha256(serialized.encode()).hexdigest()
    if not all(isinstance(m,dict) and isinstance(m.get("content"), str) for m in messages):
        out["client_meter_unavailable"] = "non-text messages"
        return out
    out["message_chars"] = sum(len(m["content"]) for m in messages)
    if meter is None:
        out["client_meter_unavailable"] = "local tokenizer unavailable"
        return out
    out["client_meter"] = meter.method
    out["input_text_subwords"], out["visible_input_estimate"] = meter.measure(messages)
    # 只数实际可见的回答。隐藏推理、缓存字段以及服务器模板都不加入正文长度。
    choices = response.get("choices")
    first = choices[0] if isinstance(choices,list) and choices else None
    msg = first.get("message") if isinstance(first,dict) else None
    if isinstance(msg,dict) and isinstance(msg.get("content"),str):
        out["output_text_subwords"] = meter.subwords(msg["content"])
    return out


def add_measurement(totals, event):
    """保留覆盖数。旧流水只有 actor 输入估值，其他缺失值不能当作零。"""
    totals["responses"] = totals.get("responses", 0) + 1
    estimate = event.get("visible_input_estimate", event.get("input_tokens_estimate"))
    for field, value in (("visible_input_estimate",estimate), ("input_text_subwords",event.get("input_text_subwords")),
                         ("output_text_subwords",event.get("output_text_subwords"))):
        if type(value) is int:
            totals[field] = totals.get(field,0) + value
            key = field + "_responses"
            totals[key] = totals.get(key,0) + 1
    if event.get("gateway_usage_missing") or event.get("gateway_total_matches_parts") is False:
        totals["incomplete_or_inconsistent_usage"] = totals.get("incomplete_or_inconsistent_usage",0) + 1
