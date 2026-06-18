from __future__ import annotations

import json
import os
import time
from enum import Enum
from typing import Any

import requests

from app.core.config import settings
from app.core.logger import get_logger


class LLMErrorType(str, Enum):
    CONFIG = "config_error"
    AUTH = "auth_error"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    NETWORK = "network_error"
    SERVER = "server_error"
    BAD_RESPONSE = "bad_response"
    PARSE = "parse_error"
    UNKNOWN = "unknown_error"


class LLMClientError(Exception):
    def __init__(
        self,
        message: str,
        *,
        error_type: LLMErrorType = LLMErrorType.UNKNOWN,
        status_code: int | None = None,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.status_code = status_code
        self.retryable = retryable
        self.details = details or {}


class StructuredOutputError(LLMClientError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message,
            error_type=LLMErrorType.PARSE,
            retryable=False,
            details=details,
        )


class LLMClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: int = 120,
        max_retries: int | None = None,
        retry_backoff: float | None = None,
        default_temperature: float | None = None,
        default_max_tokens: int | None = None,
        enable_logging: bool | None = None,
        log_payload_preview_chars: int = 800,
    ) -> None:
        self.logger = get_logger("app.core.llm_client")
        self.api_key = api_key or os.getenv("LLM_API_KEY", "") or settings.LLM_API_KEY
        self.base_url = (base_url or os.getenv("LLM_BASE_URL", "") or settings.LLM_BASE_URL).rstrip("/")
        self.model = model or os.getenv("LLM_MODEL", "") or settings.LLM_MODEL
        self.timeout = timeout

        self.max_retries = int(os.getenv("LLM_MAX_RETRIES", str(max_retries if max_retries is not None else 2)))
        self.retry_backoff = float(os.getenv("LLM_RETRY_BACKOFF", str(retry_backoff if retry_backoff is not None else 1.5)))
        self.default_temperature = float(
            os.getenv("LLM_DEFAULT_TEMPERATURE", str(default_temperature if default_temperature is not None else 0.1))
        )
        self.default_max_tokens = int(
            os.getenv("LLM_DEFAULT_MAX_TOKENS", str(default_max_tokens if default_max_tokens is not None else 0))
        )
        self.thinking_type = (os.getenv("LLM_THINKING_TYPE", "") or settings.LLM_THINKING_TYPE).strip()
        self.reasoning_effort = (os.getenv("LLM_REASONING_EFFORT", "") or settings.LLM_REASONING_EFFORT).strip()
        self.enable_logging = bool(
            enable_logging
            if enable_logging is not None
            else str(os.getenv("LLM_ENABLE_LOGGING", "false")).strip().lower() in {"1", "true", "yes", "on"}
        )
        self.log_payload_preview_chars = max(100, int(log_payload_preview_chars))

        self.enabled = bool(self.api_key and self.base_url and self.model)

    def set_model(self, model: str) -> None:
        new_model = (model or "").strip()
        if not new_model:
            raise LLMClientError(
                "model must not be empty",
                error_type=LLMErrorType.CONFIG,
                retryable=False,
            )
        self.model = new_model
        self.enabled = bool(self.api_key and self.base_url and self.model)

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        response_format: dict[str, Any] | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        retries: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        if not self.enabled:
            raise LLMClientError(
                "LLM is not configured",
                error_type=LLMErrorType.CONFIG,
                retryable=False,
            )

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        use_model = model or self.model
        use_temperature = self.default_temperature if temperature is None else float(temperature)
        use_max_tokens = self.default_max_tokens if max_tokens is None else int(max_tokens)

        payload: dict[str, Any] = {
            "model": use_model,
            "temperature": use_temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        if use_max_tokens > 0:
            payload["max_tokens"] = use_max_tokens

        if response_format:
            payload["response_format"] = response_format

        if self.thinking_type:
            payload["thinking"] = {"type": self.thinking_type}

        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort

        attempt_limit = self.max_retries if retries is None else max(0, int(retries))
        last_error: LLMClientError | None = None

        for attempt in range(attempt_limit + 1):
            try:
                self._log_request(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    payload=payload,
                    metadata=metadata,
                    attempt=attempt,
                    attempt_limit=attempt_limit,
                )
                resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
                if resp.status_code >= 400:
                    raise self._build_http_error(resp)

                data = resp.json()
                try:
                    content = data["choices"][0]["message"]["content"]
                except Exception as e:
                    raise LLMClientError(
                        f"Invalid LLM response format: {e}",
                        error_type=LLMErrorType.BAD_RESPONSE,
                        retryable=False,
                        details={"response": data},
                    ) from e

                self._log_response(content=content, metadata=metadata, attempt=attempt)
                return content
            except requests.Timeout as e:
                last_error = LLMClientError(
                    f"LLM request timeout: {e}",
                    error_type=LLMErrorType.TIMEOUT,
                    retryable=True,
                )
            except requests.RequestException as e:
                last_error = LLMClientError(
                    f"LLM network error: {e}",
                    error_type=LLMErrorType.NETWORK,
                    retryable=True,
                )
            except LLMClientError as e:
                last_error = e

            if last_error is None:
                continue

            can_retry = attempt < attempt_limit and bool(last_error.retryable)
            self._log_error(error=last_error, metadata=metadata, attempt=attempt, retrying=can_retry)
            if not can_retry:
                raise last_error

            sleep_seconds = self._compute_backoff(attempt)
            time.sleep(sleep_seconds)

        raise LLMClientError(
            "LLM request failed without detailed error",
            error_type=LLMErrorType.UNKNOWN,
            retryable=False,
        )

    def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        retries: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        raw = self.chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            response_format={"type": "json_object"},
            model=model,
            max_tokens=max_tokens,
            retries=retries,
            metadata=metadata,
        )
        try:
            return json.loads(raw)
        except Exception as e:
            raise StructuredOutputError(
                f"Failed to parse LLM JSON response: {e}",
                details={"raw": raw},
            ) from e

    def chat_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_schema: dict[str, Any],
        temperature: float | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        retries: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "structured_output",
                "schema": output_schema,
                "strict": False,
            },
        }
        raw = self.chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            response_format=response_format,
            model=model,
            max_tokens=max_tokens,
            retries=retries,
            metadata=metadata,
        )
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise StructuredOutputError(
                    "Structured output is not a JSON object",
                    details={"raw": raw},
                )
            return data
        except StructuredOutputError:
            raise
        except Exception as e:
            raise StructuredOutputError(
                f"Failed to parse structured output: {e}",
                details={"raw": raw},
            ) from e

    # ---------- high-level helpers (for legacy/server usage) ----------
    def summarize_text(self, text: str, instruction: str = "") -> str:
        prompt = {
            "instruction": instruction or "Summarize the input text concisely.",
            "text": text,
        }
        result = self.chat_json(
            system_prompt="You are a precise summarization assistant. Return JSON: {\"summary\": string}.",
            user_prompt=json.dumps(prompt, ensure_ascii=False),
            metadata={"op": "summarize_text"},
        )
        summary = result.get("summary")
        return str(summary or "").strip()

    def summarize(self, text: str, user_prompt: str) -> str:
        return self.summarize_text(text=text, instruction=user_prompt)

    def extract_fields(self, **kwargs) -> dict[str, Any]:
        content = kwargs.get("content", kwargs.get("text", ""))
        instruction = kwargs.get("instruction", kwargs.get("user_prompt", "Extract fields"))
        fields = kwargs.get("fields")
        prompt = {
            "instruction": instruction,
            "content": content,
            "fields": fields,
        }
        result = self.chat_json(
            system_prompt="Extract structured fields. Return JSON object only.",
            user_prompt=json.dumps(prompt, ensure_ascii=False),
            metadata={"op": "extract_fields"},
        )
        if fields is not None and isinstance(result, dict) and "fields" not in result:
            # 兼容老调用：返回直接字段对象
            return result
        return result

    def match_source_to_template(
        self,
        template_placeholders: list[str],
        source_content: Any,
        instruction: str = "",
    ) -> dict[str, Any]:
        prompt = {
            "instruction": instruction or "Map source content to template placeholders.",
            "template_placeholders": template_placeholders,
            "source_content": source_content,
        }
        result = self.chat_json(
            system_prompt="Return JSON mapping placeholder -> value.",
            user_prompt=json.dumps(prompt, ensure_ascii=False),
            metadata={"op": "match_source_to_template"},
        )
        return result if isinstance(result, dict) else {}

    def extract_for_template(self, source_text: str, placeholders: list[str], user_prompt: str) -> dict[str, Any]:
        mapping = self.match_source_to_template(
            template_placeholders=placeholders,
            source_content=source_text,
            instruction=user_prompt,
        )
        filled_data = {key: mapping.get(key, "") for key in placeholders}
        missing_fields = [key for key, value in filled_data.items() if value in (None, "")]
        return {
            "filled_data": filled_data,
            "missing_fields": missing_fields,
        }

    def finalize_response(
        self,
        user_prompt: str,
        plan: dict[str, Any] | None,
        memory_snapshot: dict[str, Any] | None,
        step_records: list[dict[str, Any]] | None,
    ) -> str:
        payload = {
            "user_prompt": user_prompt,
            "plan": plan or {},
            "memory": memory_snapshot or {},
            "step_records": step_records or [],
        }
        result = self.chat_json(
            system_prompt="Generate concise final user-facing answer. Return JSON: {\"answer\": string}.",
            user_prompt=json.dumps(payload, ensure_ascii=False),
            metadata={"op": "finalize_response"},
        )
        return str(result.get("answer") or "").strip()

    def critique_step_failure(
        self,
        user_prompt: str,
        step: dict[str, Any],
        verifier_result: dict[str, Any],
        memory_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {
            "user_prompt": user_prompt,
            "step": step,
            "verifier_result": verifier_result,
            "memory_snapshot": memory_snapshot,
        }
        result = self.chat_json(
            system_prompt=(
                "Analyze failure and return JSON: "
                "{\"action\": \"retry|replan|abort\", \"reason\": string, \"hints\": list}."
            ),
            user_prompt=json.dumps(payload, ensure_ascii=False),
            metadata={"op": "critique_step_failure"},
        )
        return result if isinstance(result, dict) else {}

    # ---------- internal helpers ----------
    def _compute_backoff(self, attempt: int) -> float:
        return max(0.1, self.retry_backoff ** max(0, attempt))

    def _build_http_error(self, resp: requests.Response) -> LLMClientError:
        code = int(resp.status_code)
        body = resp.text[:1000]

        if code in (401, 403):
            return LLMClientError(
                f"LLM auth failed: {code} {body}",
                error_type=LLMErrorType.AUTH,
                status_code=code,
                retryable=False,
            )
        if code == 429:
            return LLMClientError(
                f"LLM rate limited: {code} {body}",
                error_type=LLMErrorType.RATE_LIMIT,
                status_code=code,
                retryable=True,
            )
        if code >= 500:
            return LLMClientError(
                f"LLM server error: {code} {body}",
                error_type=LLMErrorType.SERVER,
                status_code=code,
                retryable=True,
            )
        return LLMClientError(
            f"LLM request failed: {code} {body}",
            error_type=LLMErrorType.BAD_RESPONSE,
            status_code=code,
            retryable=False,
        )

    def _log_request(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        payload: dict[str, Any],
        metadata: dict[str, Any] | None,
        attempt: int,
        attempt_limit: int,
    ) -> None:
        if not self.enable_logging:
            return
        self.logger.info(
            "LLM request | model=%s attempt=%s/%s metadata=%s system=%s user=%s payload=%s",
            payload.get("model"),
            attempt + 1,
            attempt_limit + 1,
            metadata or {},
            self._preview(system_prompt),
            self._preview(user_prompt),
            self._preview(json.dumps(payload, ensure_ascii=False, default=str)),
        )

    def _log_response(self, *, content: str, metadata: dict[str, Any] | None, attempt: int) -> None:
        if not self.enable_logging:
            return
        self.logger.info(
            "LLM response | attempt=%s metadata=%s content=%s",
            attempt + 1,
            metadata or {},
            self._preview(content),
        )

    def _log_error(
        self,
        *,
        error: LLMClientError,
        metadata: dict[str, Any] | None,
        attempt: int,
        retrying: bool,
    ) -> None:
        if not self.enable_logging:
            return
        self.logger.warning(
            "LLM error | attempt=%s type=%s status=%s retryable=%s retrying=%s metadata=%s message=%s",
            attempt + 1,
            error.error_type.value,
            error.status_code,
            error.retryable,
            retrying,
            metadata or {},
            str(error),
        )

    def _preview(self, text: str) -> str:
        value = str(text or "")
        if len(value) <= self.log_payload_preview_chars:
            return value
        return value[: self.log_payload_preview_chars] + "..."
