"""逐次检查动作模型的输入预算，保留同一步的格式重试。"""
from uuid import uuid4

from pace.context import BudgetExceeded
from .webwalkerqa import chat_with_retry

PROTOCOL = "per-response-v2"


class BudgetedActor:
    def __init__(self, api, model, counter, budget, provider_input_budget=None):
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
            return self.api.chat(self.model, current, "actor", max_tokens=max_tokens, input_budget=self.provider_input_budget)

        return chat_with_retry(request, messages, "actor")
