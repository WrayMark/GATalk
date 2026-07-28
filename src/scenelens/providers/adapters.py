from __future__ import annotations

import base64
import json
from typing import Any, Mapping

from scenelens.core.schema_validation import validate_json_schema
from scenelens.providers.contracts import (
    CancellationToken,
    ProviderCapability,
    ProviderError,
    ProviderManifest,
    ProviderResponse,
    StructuredOutputRequest,
    VisionReviewRequest,
    require_user_approval,
)
from scenelens.providers.schema_adapters import (
    gemini_compatible_schema,
    gemini_schema_profile,
    gemini_structural_schema,
    schema_output_template,
)
from scenelens.providers.transport import (
    JsonTransport,
    JsonTransportRequest,
    UrllibJsonTransport,
)


def _data_url(media_type: str, value: bytes) -> str:
    encoded = base64.b64encode(value).decode("ascii")
    return f"data:{media_type};base64,{encoded}"


def _parse_json_text(value: str) -> Mapping[str, Any]:
    text = value.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].lstrip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProviderError(
            "AI 返回内容不是有效的结构化 JSON。",
            code="invalid_structured_output",
            retryable=False,
            technical_detail=f"line={exc.lineno},column={exc.colno}",
        ) from exc
    if not isinstance(result, dict):
        raise ProviderError(
            "AI 返回的 JSON 顶层必须是对象。",
            code="invalid_structured_output",
            retryable=False,
        )
    return result


def _structured_schema_prompt(schema: Mapping[str, Any]) -> str:
    serialized = json.dumps(
        dict(schema),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    template = json.dumps(
        schema_output_template(schema),
        ensure_ascii=False,
        sort_keys=False,
        separators=(",", ":"),
    )
    return (
        "SCENELENS_OUTPUT_JSON_SCHEMA="
        f"{serialized}\n"
        "SCENELENS_OUTPUT_JSON_TEMPLATE="
        f"{template}\n"
        "严格保留模板中的对象、数组和必填字段层级，把“待填写”替换为实际"
        "内容。数组元素必须遵守 items 类型；evidence_claims 只能包含完整"
        "对象，无法提供矩形、指标、阈值和可信度时必须返回空数组。"
        "只返回一个符合 Schema 的 JSON 对象，不要使用 Markdown 代码围栏。"
    )


def _is_gemini_schema_rejection(
    error: ProviderError,
    wire: JsonTransportRequest,
) -> bool:
    if error.code != "http_400":
        return False
    try:
        text_format = wire.body["generationConfig"]["responseFormat"][
            "text"
        ]
    except (KeyError, TypeError):
        return False
    return isinstance(text_format, Mapping) and "schema" in text_format


def _vision_from_structured(
    request: StructuredOutputRequest,
    manifest: ProviderManifest,
) -> VisionReviewRequest:
    return VisionReviewRequest(
        system_instruction=request.system_instruction,
        payload=request.payload,
        images=(),
        output_schema=request.output_schema,
        model_id=manifest.model_for(
            ProviderCapability.STRUCTURED_OUTPUT,
            request.model_id,
        ),
        user_initiated=request.user_initiated,
        disclosure_confirmed=request.disclosure_confirmed,
        timeout_seconds=request.timeout_seconds,
    )


class OpenAICompatibleChatProvider:
    def __init__(
        self,
        manifest: ProviderManifest,
        transport: JsonTransport | None = None,
    ) -> None:
        self.manifest = manifest
        self.transport = transport or UrllibJsonTransport()

    def build_request(
        self,
        request: VisionReviewRequest,
        credential: str,
    ) -> JsonTransportRequest:
        require_user_approval(request)
        model = self.manifest.model_for(
            ProviderCapability.VISION_REVIEW,
            request.model_id,
        )
        content: list[dict[str, Any]] = []
        for image in request.images:
            content.append(
                {
                    "type": "text",
                    "text": f"IMAGE_ROLE={image.role}",
                }
            )
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": _data_url(image.media_type, image.data),
                        "detail": "high",
                    },
                }
            )
        content.append(
            {
                "type": "text",
                "text": request.canonical_payload(),
            }
        )
        structured_output_mode = str(
            self.manifest.options.get("structured_output_mode", "")
        )
        if (
            not structured_output_mode
            and bool(self.manifest.options.get("json_schema_mode", False))
        ):
            structured_output_mode = "json_schema"
        system_instruction = request.system_instruction
        if structured_output_mode == "json_object":
            system_instruction = (
                f"{system_instruction}\nReturn JSON only and do not wrap it "
                "in Markdown."
            )
            content.append(
                {
                    "type": "text",
                    "text": _structured_schema_prompt(
                        request.output_schema
                    ),
                }
            )
        body: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": content},
            ],
            "temperature": 0.2,
        }
        if structured_output_mode == "json_schema":
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "scenelens_review",
                    "strict": True,
                    "schema": dict(request.output_schema),
                },
            }
        elif structured_output_mode == "json_object":
            body["response_format"] = {"type": "json_object"}
        if request.max_output_tokens is not None:
            body["max_tokens"] = request.max_output_tokens
        return JsonTransportRequest(
            url=f"{self.manifest.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {credential}",
                "Content-Type": "application/json",
            },
            body=body,
            timeout_seconds=request.timeout_seconds,
        )

    def review(
        self,
        request: VisionReviewRequest,
        credential: str,
        cancellation: CancellationToken,
    ) -> ProviderResponse:
        wire = self.build_request(request, credential)
        response = self.transport.send(wire, cancellation)
        try:
            text = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(
                "AI 服务响应缺少结构化输出。",
                code="missing_output",
                retryable=False,
            ) from exc
        return ProviderResponse(
            provider_id=self.manifest.provider_id,
            model_id=str(response.get("model", wire.body["model"])),
            output=_parse_json_text(str(text)),
            request_id=(
                None if response.get("id") is None else str(response["id"])
            ),
            usage=dict(response.get("usage", {})),
        )

    def generate_structured(
        self,
        request: StructuredOutputRequest,
        credential: str,
        cancellation: CancellationToken,
    ) -> ProviderResponse:
        return self.review(
            _vision_from_structured(request, self.manifest),
            credential,
            cancellation,
        )


class ResponsesVisionProvider:
    def __init__(
        self,
        manifest: ProviderManifest,
        transport: JsonTransport | None = None,
    ) -> None:
        self.manifest = manifest
        self.transport = transport or UrllibJsonTransport()

    def build_request(
        self,
        request: VisionReviewRequest,
        credential: str,
    ) -> JsonTransportRequest:
        require_user_approval(request)
        model = self.manifest.model_for(
            ProviderCapability.VISION_REVIEW,
            request.model_id,
        )
        content: list[dict[str, Any]] = []
        for image in request.images:
            content.append(
                {
                    "type": "input_text",
                    "text": f"IMAGE_ROLE={image.role}",
                }
            )
            content.append(
                {
                    "type": "input_image",
                    "image_url": _data_url(image.media_type, image.data),
                    "detail": "high",
                }
            )
        content.append(
            {
                "type": "input_text",
                "text": request.canonical_payload(),
            }
        )
        body = {
            "model": model,
            "instructions": request.system_instruction,
            "input": [{"role": "user", "content": content}],
            "store": False,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "scenelens_review",
                    "strict": True,
                    "schema": dict(request.output_schema),
                }
            },
        }
        if request.max_output_tokens is not None:
            body["max_output_tokens"] = request.max_output_tokens
        return JsonTransportRequest(
            url=f"{self.manifest.base_url}/responses",
            headers={
                "Authorization": f"Bearer {credential}",
                "Content-Type": "application/json",
            },
            body=body,
            timeout_seconds=request.timeout_seconds,
        )

    def review(
        self,
        request: VisionReviewRequest,
        credential: str,
        cancellation: CancellationToken,
    ) -> ProviderResponse:
        wire = self.build_request(request, credential)
        response = self.transport.send(wire, cancellation)
        text = response.get("output_text")
        if text is None:
            for item in response.get("output", []):
                if item.get("type") != "message":
                    continue
                for content in item.get("content", []):
                    if content.get("type") == "output_text":
                        text = content.get("text")
                        break
        if text is None:
            raise ProviderError(
                "AI 服务响应缺少结构化输出。",
                code="missing_output",
                retryable=False,
            )
        return ProviderResponse(
            provider_id=self.manifest.provider_id,
            model_id=str(response.get("model", wire.body["model"])),
            output=_parse_json_text(str(text)),
            request_id=(
                None if response.get("id") is None else str(response["id"])
            ),
            usage=dict(response.get("usage", {})),
        )

    def generate_structured(
        self,
        request: StructuredOutputRequest,
        credential: str,
        cancellation: CancellationToken,
    ) -> ProviderResponse:
        return self.review(
            _vision_from_structured(request, self.manifest),
            credential,
            cancellation,
        )


class GeminiVisionProvider:
    def __init__(
        self,
        manifest: ProviderManifest,
        transport: JsonTransport | None = None,
    ) -> None:
        self.manifest = manifest
        self.transport = transport or UrllibJsonTransport()

    def build_request(
        self,
        request: VisionReviewRequest,
        credential: str,
    ) -> JsonTransportRequest:
        return self._build_request(
            request,
            credential,
            schema_mode="auto",
        )

    def _build_request(
        self,
        request: VisionReviewRequest,
        credential: str,
        *,
        schema_mode: str,
    ) -> JsonTransportRequest:
        require_user_approval(request)
        model = self.manifest.model_for(
            ProviderCapability.VISION_REVIEW,
            request.model_id,
        )
        parts: list[dict[str, Any]] = []
        for image in request.images:
            parts.append({"text": f"IMAGE_ROLE={image.role}"})
            parts.append(
                {
                    "inlineData": {
                        "mimeType": image.media_type,
                        "data": base64.b64encode(image.data).decode("ascii"),
                    }
                }
            )
        parts.append({"text": request.canonical_payload()})
        compatible_schema = gemini_compatible_schema(
            request.output_schema
        )
        if schema_mode == "auto":
            schema_mode = (
                "structural"
                if gemini_schema_profile(
                    request.output_schema
                ).requires_structural_mode
                else "full"
            )
        if schema_mode not in {"full", "structural", "prompt"}:
            raise ValueError(f"Unknown Gemini schema mode: {schema_mode}")
        if schema_mode in {"structural", "prompt"}:
            parts.append(
                {
                    "text": _structured_schema_prompt(
                        request.output_schema
                    )
                }
            )
        text_format: dict[str, Any] = {
            # generateContent exposes this field as the
            # TextResponseFormat.MimeType enum.  The REST
            # documentation also shows the MIME spelling in
            # some examples, but the current v1beta endpoint
            # accepts the enum wire value used here.
            "mimeType": "APPLICATION_JSON",
        }
        if schema_mode == "full":
            text_format["schema"] = compatible_schema
        elif schema_mode == "structural":
            text_format["schema"] = gemini_structural_schema(
                request.output_schema
            )
        generation_config: dict[str, Any] = {
            "responseFormat": {"text": text_format},
        }
        if request.max_output_tokens is not None:
            generation_config["maxOutputTokens"] = (
                request.max_output_tokens
            )
        return JsonTransportRequest(
            url=(
                f"{self.manifest.base_url}/models/{model}:generateContent"
            ),
            headers={
                "x-goog-api-key": credential,
                "Content-Type": "application/json",
            },
            body={
                "systemInstruction": {
                    "parts": [{"text": request.system_instruction}]
                },
                "contents": [{"role": "user", "parts": parts}],
                "generationConfig": generation_config,
            },
            timeout_seconds=request.timeout_seconds,
        )

    def review(
        self,
        request: VisionReviewRequest,
        credential: str,
        cancellation: CancellationToken,
    ) -> ProviderResponse:
        wire, response = self._send_with_schema_fallback(
            request,
            credential,
            cancellation,
        )
        output = self._parse_response_output(response)
        first_usage = dict(response.get("usageMetadata", {}))
        issues = validate_json_schema(output, request.output_schema)
        repaired = False
        if issues:
            cancellation.raise_if_cancelled()
            repair_request = VisionReviewRequest(
                system_instruction=(
                    "你是 JSON 结构纠错器。修复给定审阅结果，使其严格符合"
                    "输出 Schema。保留原有美术观察、证据、优先级和建议语义；"
                    "不得增加新的美术结论，不得虚构坐标或测量。缺少完整结构"
                    "信息的 evidence_claims 必须返回空数组。只输出 JSON。"
                ),
                payload={
                    "original_input": dict(request.payload),
                    "invalid_output": dict(output),
                    "schema_issues": [
                        str(issue) for issue in issues
                    ],
                },
                images=request.images,
                output_schema=request.output_schema,
                model_id=request.model_id,
                user_initiated=request.user_initiated,
                disclosure_confirmed=request.disclosure_confirmed,
                timeout_seconds=request.timeout_seconds,
                max_output_tokens=request.max_output_tokens,
            )
            wire, response = self._send_with_schema_fallback(
                repair_request,
                credential,
                cancellation,
            )
            output = self._parse_response_output(response)
            repaired = True
            remaining = validate_json_schema(
                output,
                request.output_schema,
            )
            if remaining:
                detail = " | ".join(
                    str(issue) for issue in remaining[:12]
                )
                raise ProviderError(
                    "AI 返回结构经过一次自动纠错后仍不完整。",
                    code="invalid_structured_output_after_repair",
                    retryable=False,
                    technical_detail=detail,
                )
        usage = dict(response.get("usageMetadata", {}))
        if repaired:
            usage = {
                "schemaRepairAttempted": True,
                "initial": first_usage,
                "repair": usage,
            }
        return ProviderResponse(
            provider_id=self.manifest.provider_id,
            model_id=str(wire.url.split("/models/", 1)[1].split(":", 1)[0]),
            output=output,
            request_id=None,
            usage=usage,
        )

    def _send_with_schema_fallback(
        self,
        request: VisionReviewRequest,
        credential: str,
        cancellation: CancellationToken,
    ) -> tuple[JsonTransportRequest, Mapping[str, Any]]:
        wire = self.build_request(request, credential)
        try:
            response = self.transport.send(wire, cancellation)
        except ProviderError as exc:
            if not _is_gemini_schema_rejection(exc, wire):
                raise
            cancellation.raise_if_cancelled()
            wire = self._build_request(
                request,
                credential,
                schema_mode="prompt",
            )
            response = self.transport.send(wire, cancellation)
        return wire, response

    @staticmethod
    def _parse_response_output(
        response: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        try:
            parts = response["candidates"][0]["content"]["parts"]
            text = next(part["text"] for part in parts if "text" in part)
        except (KeyError, IndexError, StopIteration, TypeError) as exc:
            raise ProviderError(
                "AI 服务响应缺少结构化输出。",
                code="missing_output",
                retryable=False,
            ) from exc
        return _parse_json_text(str(text))

    def generate_structured(
        self,
        request: StructuredOutputRequest,
        credential: str,
        cancellation: CancellationToken,
    ) -> ProviderResponse:
        return self.review(
            _vision_from_structured(request, self.manifest),
            credential,
            cancellation,
        )


def create_vision_provider(
    manifest: ProviderManifest,
    transport: JsonTransport | None = None,
):
    if manifest.api_style == "openai_chat":
        return OpenAICompatibleChatProvider(manifest, transport)
    if manifest.api_style == "openai_responses":
        return ResponsesVisionProvider(manifest, transport)
    if manifest.api_style == "gemini_generate_content":
        return GeminiVisionProvider(manifest, transport)
    raise ValueError(
        f"Provider {manifest.provider_id} does not expose vision review."
    )
