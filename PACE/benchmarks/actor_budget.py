"""逐次检查动作模型的输入预算，保留同一步的格式重试。"""
from uuid import uuid4

from pace.context import BudgetExceeded
from pace.providers import ReplyFormatError
from .webwalkerqa import chat_with_retry

PROTOCOL = "per-response-v2"


class BudgetedActor:
    def __init__(self, api, model, counter, budget, provider_input_budget=None, *, enforce_provider_budget=True,
                 seed_query=None):
        self.enforce_provider_budget = enforce_provider_budget
        self.seed_query = seed_query
        self.api, self.model = api, model
        self.counter, self.budget = counter, budget
        self.provider_input_budget = budget if provider_input_budget is None else provider_input_budget
        self.episode_id = uuid4().hex
        self.step = 0
        self.last_messages = None

    def __call__(self, messages):
        self.step += 1

        def request(current, attempt, max_tokens):
            estimate = self.counter.messages(current)
            if estimate > self.budget:
                raise BudgetExceeded(f"format retry needs {estimate} tokens (budget {self.budget})")
            self.last_messages = current
            self.api.actor_log = dict(episode_id=self.episode_id, decision_step=self.step,
                                      format_attempt=attempt, input_tokens_estimate=estimate)
            options = {"json_mode": True} if self.seed_query else {}
            reply = self.api.chat(self.model, current, "actor", max_tokens=max_tokens,
                                  input_budget=self.provider_input_budget,
                                  enforce_input_budget=self.enforce_provider_budget, **options)
            if self.seed_query:
                actual = self.api.last_input_tokens.get("actor")
                if self.enforce_provider_budget and actual is not None and actual > self.provider_input_budget:
                    return reply
                if (reply.get("tool") not in ("search", "visit", "finish", "reread", "glimpse")
                        or not isinstance(reply.get("args"), dict)):
                    raise ReplyFormatError("actor: expected one named action and an args object")
            return reply

        try:
            return chat_with_retry(request, messages, "actor")
        except ReplyFormatError:
            if self.step != 1 or not self.seed_query:
                raise
            # 只在首步两次协议失败时发出原问题搜索。记录来源，后续答案必须由模型提交。
            return dict(tool="search", args={"query": self.seed_query}, note="Search the original question",
                        origin="first_step_fallback")
