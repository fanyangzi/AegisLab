"""Optional LLM adapter.

The default provider is ``offline`` and never makes a network request. A
provider can be selected through environment variables, but a missing key,
unsupported provider, or adapter error always degrades to a deterministic
summary so review decisions remain available offline.
"""

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class LLMResult:
    provider: str
    available: bool
    text: str
    degraded: bool = False


class LLMAdapter:
    def __init__(self) -> None:
        self.base_url = os.getenv("LABSAFETY_LLM_BASE_URL", "https://hk.getelucid.com/v1").rstrip("/")
        self.model = os.getenv("LABSAFETY_LLM_MODEL", "gpt-6.1-sol")
        self.api_key = os.getenv("LABSAFETY_LLM_API_KEY", "")
        self.enabled = bool(self.api_key) and os.getenv("LABSAFETY_LLM_ENABLED", "1").lower() not in {"0", "false", "no"}

    def status(self) -> Dict[str, Any]:
        configured = bool(self.api_key)
        return {
            "provider": "openai-compatible",
            "model": self.model or None,
            "configured": configured,
            "available": bool(self.enabled and configured),
            "mode": "remote" if self.enabled and configured else "offline",
            "base_url": self.base_url,
        }

    def summarize(self, review: Dict[str, Any], evaluation: Dict[str, Any]) -> LLMResult:
        if not self.enabled or not self.api_key:
            return LLMResult("offline", True, self._offline_summary(review, evaluation))
        prompt = {
            "review": review,
            "evaluation": evaluation,
            "instruction": "用中文总结化学实验安全审查结果。只解释风险、证据和待人工确认项，不生成危险反应参数或可执行处置指令。",
        }
        body = json.dumps({
            "model": self.model,
            "temperature": 0.1,
            "max_tokens": 700,
            "messages": [
                {"role": "system", "content": "你是实验室安全审查辅助模型。规则引擎结论优先，证据不足时必须建议人工复核。"},
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ],
        }).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=12) as response:
                data = json.loads(response.read().decode("utf-8"))
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            if not text:
                raise ValueError("empty model response")
            return LLMResult("openai-compatible", True, text)
        except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError, KeyError, IndexError):
            return LLMResult("offline", True, self._offline_summary(review, evaluation), degraded=True)

    @staticmethod
    def _offline_summary(review: Dict[str, Any], evaluation: Dict[str, Any]) -> str:
        findings = review.get("findings", [])
        failed = [item.get("message", "policy failed") for item in evaluation.get("results", []) if not item.get("passed")]
        if failed:
            return f"Offline assessment: {len(findings)} finding(s); review is blocked by " + "; ".join(failed) + "."
        return f"Offline assessment: {len(findings)} finding(s), risk score {evaluation.get('risk_score', 0)}, all policy gates passed."
