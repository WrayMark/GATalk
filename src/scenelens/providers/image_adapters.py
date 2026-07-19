from __future__ import annotations

import base64
import hashlib
import json
from typing import Any, Mapping

from scenelens.providers.contracts import (
    CancellationToken,
    ImageEditRequest,
    ImageEditResponse,
    ProviderCapability,
    ProviderError,
    ProviderManifest,
    require_user_approval,
)
from scenelens.providers.transport import (
    BinaryTransport,
    BinaryTransportRequest,
    JsonTransport,
    JsonTransportRequest,
    UrllibBinaryTransport,
    UrllibJsonTransport,
)


class GeminiImageEditProvider:
    def __init__(
        self,
        manifest: ProviderManifest,
        transport: JsonTransport | None = None,
    ) -> None:
        self.manifest = manifest
        self.transport = transport or UrllibJsonTransport()

    def build_request(
        self,
        request: ImageEditRequest,
        credential: str,
    ) -> JsonTransportRequest:
        require_user_approval(request)
        model = self.manifest.model_for(
            ProviderCapability.IMAGE_EDIT,
            request.model_id,
        )
        parts: list[dict[str, Any]] = [
            {
                "inline_data": {
                    "mime_type": image.media_type,
                    "data": base64.b64encode(image.data).decode("ascii"),
                }
            }
            for image in request.images
        ]
        parts.append(
            {
                "text": json.dumps(
                    dict(request.instruction),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            }
        )
        return JsonTransportRequest(
            url=f"{self.manifest.base_url}/models/{model}:generateContent",
            headers={
                "x-goog-api-key": credential,
                "Content-Type": "application/json",
            },
            body={
                "contents": [{"role": "user", "parts": parts}],
                "generationConfig": {
                    "responseModalities": ["IMAGE"],
                },
            },
            timeout_seconds=request.timeout_seconds,
        )

    def edit_image(
        self,
        request: ImageEditRequest,
        credential: str,
        cancellation: CancellationToken,
    ) -> ImageEditResponse:
        wire = self.build_request(request, credential)
        response = self.transport.send(wire, cancellation)
        try:
            parts = response["candidates"][0]["content"]["parts"]
            image_part = next(
                part.get("inlineData") or part.get("inline_data")
                for part in parts
                if part.get("inlineData") or part.get("inline_data")
            )
            data = base64.b64decode(image_part["data"], validate=True)
            media_type = str(
                image_part.get("mimeType")
                or image_part.get("mime_type")
                or "image/png"
            )
        except (
            KeyError,
            IndexError,
            StopIteration,
            TypeError,
            ValueError,
        ) as exc:
            raise ProviderError(
                "Gemini 图像响应缺少可用图片。",
                code="missing_image_output",
            ) from exc
        return ImageEditResponse(
            self.manifest.provider_id,
            self.manifest.model_for(
                ProviderCapability.IMAGE_EDIT,
                request.model_id,
            ),
            media_type,
            data,
            {"usage": dict(response.get("usageMetadata", {}))},
        )


class DashScopeImageEditProvider:
    def __init__(
        self,
        manifest: ProviderManifest,
        transport: JsonTransport | None = None,
    ) -> None:
        self.manifest = manifest
        self.transport = transport or UrllibJsonTransport()

    def build_request(
        self,
        request: ImageEditRequest,
        credential: str,
    ) -> JsonTransportRequest:
        require_user_approval(request)
        content: list[dict[str, str]] = [
            {
                "image": (
                    f"data:{image.media_type};base64,"
                    + base64.b64encode(image.data).decode("ascii")
                )
            }
            for image in request.images
        ]
        content.append(
            {
                "text": json.dumps(
                    dict(request.instruction),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            }
        )
        endpoint = str(
            self.manifest.options.get(
                "endpoint",
                "/api/v1/services/aigc/multimodal-generation/generation",
            )
        )
        return JsonTransportRequest(
            url=f"{self.manifest.base_url}{endpoint}",
            headers={
                "Authorization": f"Bearer {credential}",
                "Content-Type": "application/json",
            },
            body={
                "model": self.manifest.model_for(
                    ProviderCapability.IMAGE_EDIT,
                    request.model_id,
                ),
                "input": {
                    "messages": [{"role": "user", "content": content}]
                },
                "parameters": {"n": 1},
            },
            timeout_seconds=request.timeout_seconds,
        )

    def edit_image(
        self,
        request: ImageEditRequest,
        credential: str,
        cancellation: CancellationToken,
    ) -> ImageEditResponse:
        wire = self.build_request(request, credential)
        response = self.transport.send(wire, cancellation)
        try:
            content = response["output"]["choices"][0]["message"]["content"]
            image_value = next(
                item.get("b64_json") or item.get("image")
                for item in content
                if item.get("b64_json") or item.get("image")
            )
            data, media_type = _decode_image_value(str(image_value))
        except (KeyError, IndexError, StopIteration, TypeError, ValueError) as exc:
            raise ProviderError(
                "万相响应缺少内嵌图片；远端 URL 输出需人工验证。",
                code="missing_image_output",
            ) from exc
        return ImageEditResponse(
            self.manifest.provider_id,
            str(wire.body["model"]),
            media_type,
            data,
            {"request_id": response.get("request_id")},
        )


class MultipartImageEditProvider:
    def __init__(
        self,
        manifest: ProviderManifest,
        transport: BinaryTransport | None = None,
    ) -> None:
        self.manifest = manifest
        self.transport = transport or UrllibBinaryTransport()

    def build_request(
        self,
        request: ImageEditRequest,
        credential: str,
    ) -> BinaryTransportRequest:
        require_user_approval(request)
        prompt = json.dumps(
            dict(request.instruction),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(
            prompt.encode("utf-8")
            + b"".join(image.data for image in request.images)
        ).hexdigest()[:24]
        boundary = f"----SceneLens{digest}"
        fields: list[bytes] = []
        for name, value in (
            (
                "model",
                self.manifest.model_for(
                    ProviderCapability.IMAGE_EDIT,
                    request.model_id,
                ),
            ),
            ("prompt", prompt),
        ):
            fields.append(
                (
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                    f"{value}\r\n"
                ).encode("utf-8")
            )
        for index, image in enumerate(request.images):
            fields.append(
                (
                    f"--{boundary}\r\n"
                    'Content-Disposition: form-data; name="image[]"; '
                    f'filename="{index}-{image.role}.png"\r\n'
                    f"Content-Type: {image.media_type}\r\n\r\n"
                ).encode("utf-8")
                + image.data
                + b"\r\n"
            )
        fields.append(f"--{boundary}--\r\n".encode("ascii"))
        endpoint = str(
            self.manifest.options.get("endpoint", "/images/edits")
        )
        return BinaryTransportRequest(
            url=f"{self.manifest.base_url}{endpoint}",
            headers={
                "Authorization": f"Bearer {credential}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
            body=b"".join(fields),
            timeout_seconds=request.timeout_seconds,
        )

    def edit_image(
        self,
        request: ImageEditRequest,
        credential: str,
        cancellation: CancellationToken,
    ) -> ImageEditResponse:
        wire = self.build_request(request, credential)
        response = self.transport.send(wire, cancellation)
        try:
            item: Mapping[str, Any] = response["data"][0]
            value = item.get("b64_json") or item.get("image")
            if value is None:
                raise ValueError("URL-only output")
            data, media_type = _decode_image_value(str(value))
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderError(
                "图像编辑响应缺少内嵌图片；URL-only 响应尚未自动下载。",
                code="missing_image_output",
            ) from exc
        return ImageEditResponse(
            self.manifest.provider_id,
            self.manifest.model_for(
                ProviderCapability.IMAGE_EDIT,
                request.model_id,
            ),
            media_type,
            data,
            {"response_created": response.get("created")},
        )


def create_image_edit_provider(
    manifest: ProviderManifest,
    *,
    json_transport: JsonTransport | None = None,
    binary_transport: BinaryTransport | None = None,
):
    if manifest.api_style == "gemini_image_edit":
        return GeminiImageEditProvider(manifest, json_transport)
    if manifest.api_style == "dashscope_image_edit":
        return DashScopeImageEditProvider(manifest, json_transport)
    if manifest.api_style == "multipart_image_edit":
        return MultipartImageEditProvider(manifest, binary_transport)
    raise ValueError(
        f"Provider {manifest.provider_id} does not expose image edit."
    )


def _decode_image_value(value: str) -> tuple[bytes, str]:
    media_type = "image/png"
    encoded = value
    if value.startswith("data:"):
        header, encoded = value.split(",", 1)
        media_type = header[5:].split(";", 1)[0] or media_type
    if value.startswith("http://") or value.startswith("https://"):
        raise ValueError("remote URL is not embedded image data")
    return base64.b64decode(encoded, validate=True), media_type
