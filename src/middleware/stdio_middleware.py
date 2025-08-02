import json
import time
import asyncio
from collections import deque
from typing import Callable, TypeVar, Any, Union, cast
from functools import wraps
from utils.logging_config import get_logger

logger = get_logger(__name__)
F = TypeVar("F", bound=Callable[..., Any])


class StdioRateLimiter:
    """STDIO-specific rate limiting"""

    def __init__(self, requests_per_minute: int = 10, window_seconds: int = 60):
        self.requests_per_minute = requests_per_minute
        self.window_seconds = window_seconds
        self.request_timestamps = deque()

    def check_rate_limit(self) -> bool:
        """Check rate limit for STDIO client"""
        current_time = time.time()

        while (
            self.request_timestamps
            and current_time - self.request_timestamps[0] >= self.window_seconds
        ):
            self.request_timestamps.popleft()

        if len(self.request_timestamps) >= self.requests_per_minute:
            logger.warning("STDIO rate limit exceeded")
            return False

        self.request_timestamps.append(current_time)
        return True


class StdioMiddleware:
    """STDIO authentication and rate limiting"""

    def __init__(self, requests_per_minute: int = 20):
        self.authenticated = False
        self.client_id = "anonymous"
        self.rate_limiter = StdioRateLimiter(requests_per_minute=requests_per_minute)

    def require_auth_and_rate_limit(self, func: F) -> F:
        """Decorator for auth and rate limiting"""

        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Union[str, Any]:
            if not self.authenticated:
                logger.error(
                    json.dumps({"error": "Authentication required", "code": 401})
                )
                return json.dumps({"error": "Authentication required", "code": 401})

            if not self.rate_limiter.check_rate_limit():
                logger.error(json.dumps({"error": "Rate limited", "code": 429}))
                return json.dumps({"error": "Rate limited", "code": 429})

            return await func(*args, **kwargs)

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Union[str, Any]:
            if not self.authenticated:
                logger.error(
                    json.dumps({"error": "Authentication required", "code": 401})
                )
                return json.dumps({"error": "Authentication required", "code": 401})

            if not self.rate_limiter.check_rate_limit():
                logger.error(json.dumps({"error": "Rate limited", "code": 429}))
                return json.dumps({"error": "Rate limited", "code": 429})

            return func(*args, **kwargs)

        if asyncio.iscoroutinefunction(func):
            return cast(F, async_wrapper)
        return cast(F, sync_wrapper)

    def authenticate(self, key: str) -> bool:
        """Authenticate with API key"""
        if key and key.strip():
            self.authenticated = True
            self.client_id = key
            return True
        else:
            self.authenticated = False
            return False
