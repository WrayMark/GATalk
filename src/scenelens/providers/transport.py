from __future__ import annotations

import http.client
import json
import socket
import ssl
import urllib.error
import urllib.parse
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


@dataclass(frozen=True)
class DownloadedBinary:
    data: bytes
    media_type: str


class BinaryDownloadTransport(Protocol):
    def download(
        self,
        url: str,
        cancellation: CancellationToken,
        *,
        timeout_seconds: float,
        max_bytes: int,
    ) -> DownloadedBinary:
        """Download a provider-returned HTTPS artifact."""


def _http_public_message(status: int, *, image: bool) -> str:
    subject = "AI 图像服务" if image else "AI 服务"
    messages = {
        400: f"{subject}拒绝了请求参数。",
        401: f"{subject}未通过 API Key 认证。",
        403: (
            f"{subject}拒绝访问。请检查 API Key 权限、服务开通状态、"
            "地域与模型访问权限。"
        ),
        404: f"{subject}找不到所选模型或接口。",
        408: f"{subject}请求超时。",
        409: f"{subject}当前状态冲突，请稍后重试。",
        413: f"{subject}拒绝了过大的图片或请求数据。",
        422: f"{subject}无法处理当前请求参数。",
        429: f"{subject}达到调用频率或额度限制。",
    }
    if status in messages:
        return messages[status]
    if status >= 500:
        return f"{subject}暂时不可用。"
    return f"{subject}请求失败（HTTP {status}）。"


def _read_http_error_detail(exc: urllib.error.HTTPError) -> str:
    try:
        raw = exc.read(32 * 1024)
    except Exception:
        raw = b""
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        return f"HTTP {exc.code}"
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        compact = " ".join(text.split())
        return f"HTTP {exc.code} | {compact[:800]}"
    if not isinstance(value, dict):
        return f"HTTP {exc.code}"
    error = value.get("error", value)
    if not isinstance(error, dict):
        error = value
    parts = [f"HTTP {exc.code}"]
    for key in ("status", "type", "code", "param", "request_id"):
        item = error.get(key)
        if item is None:
            item = value.get(key)
        if item not in (None, "", exc.code, str(exc.code)):
            parts.append(f"{key}={str(item)[:160]}")
    message = error.get("message")
    if message is None:
        message = value.get("message")
    if message not in (None, ""):
        parts.append(f"message={str(message)[:800]}")
    return " | ".join(parts)[:1200]


_TRANSIENT_NETWORK_ERRORS = (
    urllib.error.URLError,
    TimeoutError,
    socket.timeout,
    http.client.RemoteDisconnected,
    http.client.IncompleteRead,
    ConnectionResetError,
    ConnectionAbortedError,
    ConnectionRefusedError,
    BrokenPipeError,
    ssl.SSLError,
)


def _network_provider_error(
    exc: BaseException,
    *,
    image: bool,
    request_bytes: int | None = None,
    download: bool = False,
) -> ProviderError:
    subject = "AI 图像服务" if image else "AI 服务"
    disconnected = isinstance(
        exc,
        (
            http.client.RemoteDisconnected,
            http.client.IncompleteRead,
            ConnectionResetError,
            ConnectionAbortedError,
            BrokenPipeError,
        ),
    )
    if download:
        message = (
            "下载 AI 返回图片时连接被中途断开。SceneLens 会自动重试；"
            "如果仍失败，请检查代理、VPN 或网络稳定性。"
            if disconnected
            else "无法下载 AI 返回图片。SceneLens 会自动重试；"
            "如果仍失败，请检查网络。"
        )
        code = "output_connection_closed" if disconnected else "output_download_error"
    elif disconnected:
        message = (
            f"{subject}在返回结果前中断了连接。SceneLens 会自动重试；"
            "如果仍失败，请检查代理、VPN 或网络稳定性。"
        )
        code = "connection_closed"
    else:
        message = (
            f"无法连接{subject}。SceneLens 会自动重试；"
            "如果仍失败，请检查网络。"
        )
        code = "network_error"
    details = [type(exc).__name__]
    if request_bytes is not None:
        details.append(f"request_bytes={request_bytes}")
    return ProviderError(
        message,
        code=code,
        retryable=True,
        technical_detail=" | ".join(details),
    )


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
                _http_public_message(exc.code, image=False),
                code=f"http_{exc.code}",
                retryable=retryable,
                technical_detail=_read_http_error_detail(exc),
            ) from exc
        except _TRANSIENT_NETWORK_ERRORS as exc:
            raise _network_provider_error(
                exc,
                image=False,
                request_bytes=len(encoded),
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
                _http_public_message(exc.code, image=True),
                code=f"http_{exc.code}",
                retryable=retryable,
                technical_detail=_read_http_error_detail(exc),
            ) from exc
        except _TRANSIENT_NETWORK_ERRORS as exc:
            raise _network_provider_error(
                exc,
                image=True,
                request_bytes=len(request.body),
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


class UrllibBinaryDownloadTransport:
    def download(
        self,
        url: str,
        cancellation: CancellationToken,
        *,
        timeout_seconds: float,
        max_bytes: int,
    ) -> DownloadedBinary:
        cancellation.raise_if_cancelled()
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme.lower() != "https" or not parsed.netloc:
            raise ProviderError(
                "AI 图像服务返回了不安全的下载地址。",
                code="unsafe_output_url",
                retryable=False,
            )
        request = urllib.request.Request(
            url,
            headers={"Accept": "image/*"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=timeout_seconds,
            ) as response:
                content_length = response.headers.get("Content-Length")
                try:
                    declared_size = (
                        int(content_length)
                        if content_length is not None
                        else None
                    )
                except (TypeError, ValueError):
                    declared_size = None
                if declared_size is not None and declared_size > max_bytes:
                    raise ProviderError(
                        "AI 返回图片超过本地安全大小限制。",
                        code="output_image_too_large",
                    )
                data = response.read(max_bytes + 1)
                media_type = (
                    response.headers.get_content_type()
                    or "application/octet-stream"
                )
        except ProviderError:
            raise
        except urllib.error.HTTPError as exc:
            retryable = exc.code in {408, 409, 429} or exc.code >= 500
            raise ProviderError(
                _http_public_message(exc.code, image=True),
                code=f"download_http_{exc.code}",
                retryable=retryable,
                technical_detail=_read_http_error_detail(exc),
            ) from exc
        except _TRANSIENT_NETWORK_ERRORS as exc:
            raise _network_provider_error(
                exc,
                image=True,
                download=True,
            ) from exc
        if len(data) > max_bytes:
            raise ProviderError(
                "AI 返回图片超过本地安全大小限制。",
                code="output_image_too_large",
            )
        if not media_type.lower().startswith("image/"):
            raise ProviderError(
                "AI 返回的下载内容不是图片。",
                code="invalid_output_media_type",
                technical_detail=f"media_type={media_type}",
            )
        cancellation.raise_if_cancelled()
        return DownloadedBinary(data=data, media_type=media_type)


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


class RecordingBinaryDownloadTransport:
    def __init__(self, responses: list[DownloadedBinary]) -> None:
        self.responses = list(responses)
        self.urls: list[str] = []

    def download(
        self,
        url: str,
        cancellation: CancellationToken,
        *,
        timeout_seconds: float,
        max_bytes: int,
    ) -> DownloadedBinary:
        del timeout_seconds, max_bytes
        cancellation.raise_if_cancelled()
        self.urls.append(url)
        if not self.responses:
            raise AssertionError("No recording download response configured.")
        return self.responses.pop(0)
