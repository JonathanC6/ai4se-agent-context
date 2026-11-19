import threading
import unittest
from collections import Counter
from unittest.mock import Mock

from pace.providers.api import EmbeddingInputError, ProviderError
from pace.providers.encoding import RemoteEncoder


class EmbeddingWindowTests(unittest.TestCase):
    def test_long_rejected_input_is_preserved_and_response_order_is_checked(self):
        api = Mock(lock=threading.Lock(), usage={"embedding": Counter()})
        api.post.side_effect = [
            EmbeddingInputError("1210"),
            {"data": [{"index": 1, "embedding": [0, 1]}, {"index": 0, "embedding": [1, 0]}]},
        ]
        value = "x" * 1100 + "日" * 1100
        result = RemoteEncoder(api, "model", 8192)(value)
        self.assertEqual(result, [0.25, 0.75])
        self.assertEqual("".join(api.post.call_args.args[1]["input"]), value)
        self.assertEqual(api.usage["embedding"]["split_inputs"], 1)

    def test_other_provider_errors_propagate(self):
        api = Mock()
        api.post.side_effect = ProviderError("denied")
        with self.assertRaises(ProviderError):
            RemoteEncoder(api, "model", 8192)("x" * 5000)
        api.post.assert_called_once()
