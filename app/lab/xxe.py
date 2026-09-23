"""Lab: XML External Entity (XXE).

VULNERABILITY: the XML parser is configured to resolve external
entities. A payload with a DOCTYPE that declares an entity pointing
at `file:///etc/hosts` (or any URL) causes the parser to read the
file or fetch the URL and embed its content in the response.

This file is intentionally vulnerable. The fix disables entity
resolution, DTD loading, and network access.

CWE-611, OWASP A05:2021 Security Misconfiguration / A03 Injection.
"""

from fastapi import APIRouter, Body, HTTPException, status
from lxml import etree

router = APIRouter(prefix="/lab/xxe", tags=["lab"])


@router.post("/parse")
def parse_xml(body: str = Body(..., media_type="application/xml")) -> dict:
    """Parse XML and return the concatenated text content.

    BUG: `resolve_entities=True` allows the payload to include external
    entities. A DOCTYPE that declares an entity pointing at a local
    file causes the file to be read.
    """
    try:
        # FIXED: no external entities, no DTD loading, no network.
        parser = etree.XMLParser(
            resolve_entities=False,
            load_dtd=False,
            no_network=True,
            dtd_validation=False,
        )
        root = etree.fromstring(body.encode("utf-8"), parser=parser)
    except etree.XMLSyntaxError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid XML: {exc}",
        )

    return {
        "root_tag": root.tag,
        "text": "".join(root.itertext()),
    }
