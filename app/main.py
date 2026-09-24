from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.attendance import router as attendance_router
from app.api.audit import router as audit_router
from app.api.auth import router as auth_router
from app.api.devices import router as devices_router
from app.core.config import settings
from app.core.config import settings as _settings
from app.core.security_headers import (
    HstsHeaderMiddleware,
    HttpsRedirectMiddleware,
)
from app.services.audit import record_denial

app = FastAPI(
    title="FieldProof API",
    version="0.3.0",
    docs_url="/docs" if not settings.is_prod else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Order: CORS → HSTS → Redirect. In Starlette, the middleware added
# last runs first on the request path and last on the response path,
# so HSTS is added before Redirect sees the request and after Redirect
# emits the response. That way a 307 redirect also carries HSTS.
app.add_middleware(HstsHeaderMiddleware)
app.add_middleware(HttpsRedirectMiddleware)


@app.exception_handler(HTTPException)
async def audit_http_exception_handler(
    request: Request,
    exc: HTTPException,
) -> JSONResponse:
    """Record every 401/403/404 decision, then respond normally.

    The response body and status code are unchanged from FastAPI's
    default. The only addition is the audit row.
    """
    record_denial(request, exc.status_code, str(exc.detail))
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=getattr(exc, "headers", None),
    )


app.include_router(auth_router, prefix="/api/v1")
app.include_router(devices_router, prefix="/api/v1")
app.include_router(attendance_router, prefix="/api/v1")
app.include_router(audit_router, prefix="/api/v1")

if _settings.is_lab:
    from app.lab.bola import router as lab_bola_router
    from app.lab.file_read import router as lab_file_read_router
    from app.lab.mass_assign import router as lab_mass_assign_router
    from app.lab.pickle_load import router as lab_pickle_router
    from app.lab.sqli import router as lab_sqli_router
    from app.lab.ssrf import router as lab_ssrf_router
    from app.lab.xxe import router as lab_xxe_router

    app.include_router(lab_sqli_router, prefix="/api/v1")
    app.include_router(lab_bola_router, prefix="/api/v1")
    app.include_router(lab_xxe_router, prefix="/api/v1")
    app.include_router(lab_pickle_router, prefix="/api/v1")
    app.include_router(lab_ssrf_router, prefix="/api/v1")
    app.include_router(lab_mass_assign_router, prefix="/api/v1")
    app.include_router(lab_file_read_router, prefix="/api/v1")


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.environment}
