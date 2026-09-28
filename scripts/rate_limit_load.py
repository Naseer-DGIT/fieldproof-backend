"""Rate limit load test.

Sends N requests to /auth/login and reports the distribution of status
codes. The limiter is expected to return 401 for the first K attempts
and 429 after the limit is reached.

Usage:

    python scripts/rate_limit_load.py --port 8001 --count 20
    python scripts/rate_limit_load.py --port 8001 --count 20 --concurrency 5
"""

import argparse
import asyncio
from collections import Counter

import httpx


async def one(client: httpx.AsyncClient, url: str) -> int:
    try:
        r = await client.post(
            url,
            json={"email": "nobody@example.com", "password": "wrong"},
            timeout=5.0,
        )
        return r.status_code
    except httpx.RequestError:
        return 0


async def run(port: int, count: int, concurrency: int) -> Counter:
    url = f"http://localhost:{port}/api/v1/auth/login"
    codes: Counter = Counter()

    async with httpx.AsyncClient() as client:
        sem = asyncio.Semaphore(concurrency)

        async def bounded():
            async with sem:
                return await one(client, url)

        results = await asyncio.gather(*(bounded() for _ in range(count)))
        for c in results:
            codes[c] += 1

    return codes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=1,
                        help="number of requests in flight at once")
    args = parser.parse_args()

    print(f"target: http://localhost:{args.port}/api/v1/auth/login")
    print(f"count: {args.count}  concurrency: {args.concurrency}")
    print()

    codes = asyncio.run(run(args.port, args.count, args.concurrency))

    print("status distribution:")
    for code, n in sorted(codes.items()):
        label = {0: "no response", 401: "invalid creds", 429: "rate limited"}.get(code, "")
        print(f"  {code:3}  {n:3}  {label}")

    total = sum(codes.values())
    if 429 in codes:
        print(f"\nPASS: {codes[429]} of {total} requests were rate limited")
    else:
        print(f"\nFAIL: no 429 in {total} requests")


if __name__ == "__main__":
    main()
