"""외부 호출 재시도(갭7) — 네트워크 오류만 백오프 재시도.

HTTP 4xx/5xx 응답은 재시도하지 않는다: 토스 confirm 같은 비멱등 호출을
응답을 받은 상태에서 중복 실행하면 안 되기 때문. 재시도 대상은
"요청이 서버에 닿았는지조차 불확실한" 연결·타임아웃 계열로 한정한다.
"""
import time

import httpx

RETRYABLE = (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.PoolTimeout)
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = 0.5


def post_with_retry(url: str, **kwargs) -> httpx.Response:
    last: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            return httpx.post(url, **kwargs)
        except RETRYABLE as e:
            last = e
            if attempt < MAX_ATTEMPTS - 1:
                time.sleep(BACKOFF_SECONDS * (attempt + 1))
    raise last  # type: ignore[misc]
