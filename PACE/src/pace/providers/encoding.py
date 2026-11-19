"""文本计数、远程嵌入及可选的本地 BGE。"""
import hashlib
import math
import re

from .api import EmbeddingInputError, ProviderError


def tokenizer_for(model):
    try:
        from transformers import AutoTokenizer
    except ImportError:
        raise ValueError("install transformers for this tokenizer, or use the explicit utf8 counter") from None
    return AutoTokenizer.from_pretrained(model, trust_remote_code=False)


class ChatTokens:
    """Count the actual two-message request using the selected tokenizer's chat template."""
    def __init__(self, model):
        self.codec = tokenizer_for(model)

    def text(self, text):
        return len(self.codec.encode(text, add_special_tokens=False))

    def messages(self, messages):
        return len(self.codec.apply_chat_template(messages, tokenize=True, add_generation_prompt=True))


class Utf8Counter:
    """Byte proxy with framing allowance; a gateway can add unobservable input tokens."""
    @staticmethod
    def text(text):
        return len(text.encode("utf-8"))

    def messages(self, messages):
        return 32 + sum(16 + self.text(m["content"]) for m in messages)


class BgeEncoder:
    def __init__(self, model="BAAI/bge-m3"):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ValueError("install sentence-transformers for local BGE-M3") from None
        self.model = SentenceTransformer(model)
        self.model.max_seq_length = min(8192, self.model.max_seq_length)

    def __call__(self, text):
        # SentenceTransformer applies its tokenizer's limit identically to queries and keys.
        return self.model.encode(text, normalize_embeddings=True, show_progress_bar=False)


class RemoteEncoder:
    def __init__(self, api, model, limit, tokenizer=None):
        if limit < 1:
            raise ValueError("embedding input limit must be positive")
        self.api, self.model, self.limit = api, model, limit
        self.codec = tokenizer_for(tokenizer) if tokenizer else None

    def __call__(self, text):
        if self.codec:
            ids = self.codec.encode(text, add_special_tokens=False)
            if len(ids) > self.limit:
                text = self.codec.decode(ids[:self.limit], skip_special_tokens=True)
        else:
            # Conservative cap for hosted models that do not publish their tokenizer.
            text = text.encode("utf-8")[:self.limit].decode("utf-8", errors="ignore")
        try:
            return self._vectors([text])[0]
        except EmbeddingInputError:
            if len(text.encode("utf-8")) < 2048:
                raise
        # 仅在上游拒收长输入时分成两段，同模型编码，不丢弃任何字符。
        mid = len(text) // 2
        parts = [text[:mid], text[mid:]]
        vectors = self._vectors(parts)
        weights = [len(part.encode("utf-8")) for part in parts]
        with self.api.lock:
            self.api.usage["embedding"]["split_inputs"] += 1
        return [(a * weights[0] + b * weights[1]) / sum(weights) for a, b in zip(*vectors)]

    def _vectors(self, parts):
        payload = self.api.post("/embeddings", {"model": self.model, "input": parts}, "embedding")
        try:
            items = payload["data"]
            if len(items) != len(parts):
                raise ValueError
            if len(parts) > 1:
                items = sorted(items, key=lambda item: item["index"])
                if [item["index"] for item in items] != list(range(len(parts))):
                    raise ValueError
            vectors = [item["embedding"] for item in items]
            if not all(isinstance(v, list) and v and len(v) == len(vectors[0])
                       and all(math.isfinite(x) for x in v) for v in vectors):
                raise ValueError
            return vectors
        except (KeyError, IndexError, ValueError, TypeError):
            raise ProviderError("embedding: no valid dense vector") from None


def demo_encode(text):
    vector = [0.0] * 256
    for word in re.findall(r"\w+", text.lower()):
        vector[hashlib.sha256(word.encode()).digest()[0]] += 1
    return vector if any(vector) else [1.0] + vector[1:]
