from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from scenelens.providers.contracts import (
    CancellationToken,
    ProviderError,
)


@dataclass(frozen=True)
class JsonTransportRequest:
    url: str
    headers: Mapping[str, str]
    body: Mapping[str, Any]
    timeout_seconds: float


class JsonTransport(Protocol):
    def send(
        self,
        request: JsonTransportRequest,
        cancellation: CancellationToken,
    ) -> Mapping[str, Any]:
        """Send JSON and return a decoded JSON object."""


@dataclass(frozen=True)
class BinaryTransportRequest:
    url: str
    headers: Mapping[str, str]
    body: bytes
    timeout_seconds: float


class BinaryTransport(Protocol):
    def send(
        self,
        request: BinaryTransportRequest,
        cancellation: CancellationToken,
    ) -> Mapping[str, Any]:
        """Send a pre-encoded body and return decoded JSON."""


class UrllibJsonTransport:
    def send(
        self,
        request: JsonTransportRequest,
        cancellation: CancellationToken,
    ) -> Mapping[str, Any]:
        cancellation.raise_if_cancelled()
        encoded = json.dumps(
            dict(request.body),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        raw_request = urllib.request.Request(
            request.url,
            data=encoded,
            headers=dict(request.headers),
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                raw_request,
                timeout=request.timeout_seconds,
            ) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            retryable = exc.code in {408, 409, 429} or exc.code >= 500
            raise ProviderError(
                "AI 服务请求失败，请检查服务状态或稍后重试。",
                code=f"http_{exc.code}",
                retryable=retryable,
                technical_detail=f"HTTP {exc.code}",
            ) from exc
        except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
            raise ProviderError(
                "无法连接 AI 服务，请检查网络后重试。",
                code="network_error",
                retryable=True,
                technical_detail=type(exc).__name__,
            ) from exc
        cancellation.raise_if_cancelled()
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderError(
                "AI 服务返回了无法解析的数据。",
                code="invalid_json_response",
                retryable=False,
                technical_detail=type(exc).__name__,
            ) from exc
        if not isinstance(value, dict):
            raise ProviderError(
                "AI 服务返回格式不符合预期。",
                code="invalid_response_shape",
                retryable=False,
            )
        return value


class UrllibBinaryTransport:
    def send(
        self,
        request: BinaryTransportRequest,
        cancellation: CancellationToken,
    ) -> Mapping[str, Any]:
        cancellation.raise_if_cancelled()
        raw_request = urllib.request.Request(
            request.url,
            data=request.body,
            headers=dict(request.headers),
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                raw_request,
                timeout=request.timeout_seconds,
            ) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            retryable = exc.code in {408, 409, 429} or exc.code >= 500
            raise ProviderError(
                "AI 图像服务请求失败，请检查服务状态或稍后重试。",
                code=f"http_{exc.code}",
                retryable=retryable,
                technical_detail=f"HTTP {exc.code}",
            ) from exc
        except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
            raise ProviderError(
                "无法连接 AI 图像服务，请检查网络后重试。",
                code="network_error",
                retryable=True,
                technical_detail=type(exc).__name__,
            ) from exc
        cancellation.raise_if_cancelled()
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderError(
                "AI 图像服务返回了无法解析的数据。",
                code="invalid_json_response",
                technical_detail=type(exc).__name__,
            ) from exc
        if not isinstance(value, dict):
            raise ProviderError(
                "AI 图像服务返回格式不符合预期。",
                code="invalid_response_shape",
            )
        return value


class RecordingJsonTransport:
    def __init__(self, responses: list[Mapping[str, Any]]) -> None:
        self.responses = list(responses)
        self.requests: list[JsonTransportRequest] = []

    def send(
        self,
        request: JsonTransportRequest,
        cancellation: CancellationToken,
    ) -> Mapping[str, Any]:
        cancellation.raise_if_cancelled()
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("No recording response configured.")
        return self.responses.pop(0)


class RecordingBinaryTransport:
    def __init__(self, responses: list[Mapping[str, Any]]) -> None:
        self.responses = list(responses)
        self.requests: list[BinaryTransportRequest] = []

    def send(
        self,
        request: BinaryTransportRequest,
        cancellation: CancellationToken,
    ) -> Mapping[str, Any]:
        cancellation.raise_if_cancelled()
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("No recording response configured.")
        return self.responses.pop(0)
