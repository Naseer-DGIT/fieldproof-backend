"""Streaming CSV response helper.

Yields the header line, then one line per row, then closes. The
response object is a `StreamingResponse` so the first byte reaches
the client before the generator finishes.
"""

import csv
import io
from typing import Iterable, Iterator

from fastapi.responses import StreamingResponse


def _encode(row: list) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(row)
    return buf.getvalue()


def streaming_csv(
    rows: Iterable[dict],
    filename: str,
) -> StreamingResponse:
    """Return a CSV download for the given row dicts.

    The first row's keys become the header. Every subsequent row uses
    the same order. Keys are sorted for stability across requests.
    """
    iterator: Iterator[dict] = iter(rows)
    try:
        first = next(iterator)
    except StopIteration:
        # No rows: send only a header-less empty file.
        def _empty():
            yield ""
        return StreamingResponse(
            _empty(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    headers = sorted(first.keys())

    def _generate():
        yield _encode(headers)
        yield _encode([first.get(h, "") for h in headers])
        for row in iterator:
            yield _encode([row.get(h, "") for h in headers])

    return StreamingResponse(
        _generate(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
