"""Stable failures raised when a downstream container call cannot complete."""


class DownstreamError(Exception):
    """Base error safe for the Master API exception handler to translate."""

    code = "downstream_error"
    status_code = 502
    retryable = False

    def __init__(self, component: str, message: str) -> None:
        super().__init__(message)
        self.component = component
        self.message = message


class DownstreamTimeoutError(DownstreamError):
    code = "downstream_timeout"
    status_code = 504
    retryable = True


class DownstreamUnavailableError(DownstreamError):
    code = "downstream_unavailable"
    status_code = 503
    retryable = True


class DownstreamResponseError(DownstreamError):
    code = "downstream_response_invalid"
    status_code = 502


class DownstreamHttpError(DownstreamError):
    code = "downstream_http_error"
    status_code = 502
    retryable = True
