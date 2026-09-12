from __future__ import annotations

import json
import os
import secrets

from fastapi import FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from garmin_vercel_sync.config import Settings
from garmin_vercel_sync.date_ranges import PERIODS, period_window
from garmin_vercel_sync.mcp_auth import MCPAuthError, validate_supabase_access_token
from garmin_vercel_sync.mcp_protocol import TOOLS, initialize_result, tool_result
from garmin_vercel_sync.supabase import SupabaseREST
from garmin_vercel_sync.sync import sync_recent
from garmin_vercel_sync.upstash import UpstashREST

app = FastAPI(title="Garmin Vercel Sync", docs_url=None, redoc_url=None)


def _settings() -> Settings:
    try:
        return Settings.from_env()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _authorize(authorization: str | None, secret: str) -> None:
    expected = f"Bearer {secret}"
    if not authorization or not secrets.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


def _mcp_resource_metadata_url(request: Request) -> str:
    return f"{str(request.base_url).rstrip('/')}/.well-known/oauth-protected-resource/mcp"


def _authorize_mcp(authorization: str | None, request: Request) -> Settings:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="OAuth bearer token is required",
            headers={"WWW-Authenticate": f'Bearer resource_metadata="{_mcp_resource_metadata_url(request)}"'},
        )
    allowed_email = os.getenv("MCP_ALLOWED_EMAIL", "")
    if not allowed_email:
        raise HTTPException(status_code=503, detail="MCP_ALLOWED_EMAIL is not configured")
    settings = _settings()
    try:
        validate_supabase_access_token(
            settings.supabase_url,
            settings.supabase_secret_key,
            authorization.removeprefix("Bearer "),
            allowed_email,
        )
    except MCPAuthError as exc:
        raise HTTPException(
            status_code=401,
            detail=str(exc),
            headers={"WWW-Authenticate": f'Bearer resource_metadata="{_mcp_resource_metadata_url(request)}"'},
        ) from exc
    return settings


def _mcp_error(message_id: object, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": message}}


@app.get("/api")
def root() -> dict:
    return {"service": "garmin-vercel-sync", "ok": True}


@app.get("/api/status")
def status(authorization: str | None = Header(default=None)) -> dict:
    settings = _settings()
    _authorize(authorization, settings.cron_secret)
    redis = UpstashREST(settings.upstash_url, settings.upstash_token)
    has_token = bool(redis.get(settings.garmin_token_key))
    return {
        "ok": True,
        "garmin_token_configured": has_token,
        "supabase_configured": bool(settings.supabase_url),
        "table": settings.supabase_table,
        "sync_days": settings.sync_days,
        "timezone": settings.tz_name,
    }


@app.get("/api/sync")
def sync(authorization: str | None = Header(default=None)) -> dict:
    settings = _settings()
    _authorize(authorization, settings.cron_secret)
    try:
        return sync_recent(settings)
    except HTTPException:
        raise
    except Exception as exc:
        # Do not return credentials/tokens. The exception type is enough for API callers;
        # detailed traceback remains in Vercel logs.
        print(f"sync failed: {type(exc).__name__}: {exc}")
        raise HTTPException(status_code=500, detail=f"Sync failed: {type(exc).__name__}") from exc


@app.get("/api/backfill")
def backfill(authorization: str | None = Header(default=None)) -> dict:
    """One-time protected import of the most recent two months of Garmin data."""
    settings = _settings()
    _authorize(authorization, settings.cron_secret)
    try:
        return sync_recent(settings, days=60)
    except Exception as exc:
        print(f"backfill failed: {type(exc).__name__}: {exc}")
        raise HTTPException(status_code=500, detail=f"Backfill failed: {type(exc).__name__}") from exc


@app.get("/api/data")
def data(
    period: str = Query(default="daily", description="daily, 30d, 60d, 90d, 180d, 360d, or ytd"),
    authorization: str | None = Header(default=None),
) -> dict:
    """Read Garmin health rows for a local-calendar period from Supabase."""
    settings = _settings()
    _authorize(authorization, settings.cron_secret)
    try:
        start, end = period_window(period, settings.tz_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"period must be one of: {', '.join(sorted(PERIODS))}") from exc

    database = SupabaseREST(
        settings.supabase_url,
        settings.supabase_secret_key,
        settings.supabase_table,
    )
    rows = database.fetch_rows(start.isoformat(), end.isoformat())
    return {
        "period": period,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "row_count": len(rows),
        "rows": rows,
    }


@app.get("/api/activities")
def activities(
    period: str = Query(default="daily", description="daily, 30d, 60d, 90d, 180d, 360d, or ytd"),
    authorization: str | None = Header(default=None),
) -> dict:
    """Read individual workouts, including Garmin's unmodified activity payload."""
    settings = _settings()
    _authorize(authorization, settings.cron_secret)
    try:
        start, end = period_window(period, settings.tz_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"period must be one of: {', '.join(sorted(PERIODS))}") from exc
    rows = SupabaseREST(settings.supabase_url, settings.supabase_secret_key, "garmin_activities").fetch_rows_by_date_column(
        "calendar_date", start.isoformat(), end.isoformat()
    )
    return {"period": period, "start_date": start.isoformat(), "end_date": end.isoformat(), "row_count": len(rows), "rows": rows}


@app.get("/api/metric-payloads")
def metric_payloads(
    period: str = Query(default="daily", description="daily, 30d, 60d, 90d, 180d, 360d, or ytd"),
    metric_type: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
) -> dict:
    """Read lossless Garmin endpoint payloads, including intraday time-series."""
    settings = _settings()
    _authorize(authorization, settings.cron_secret)
    try:
        start, end = period_window(period, settings.tz_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"period must be one of: {', '.join(sorted(PERIODS))}") from exc
    database = SupabaseREST(settings.supabase_url, settings.supabase_secret_key, "garmin_metric_payloads")
    rows = database.fetch_rows_by_date_column("calendar_date", start.isoformat(), end.isoformat())
    if metric_type:
        rows = [row for row in rows if row.get("metric_type") == metric_type]
    return {"period": period, "metric_type": metric_type, "start_date": start.isoformat(), "end_date": end.isoformat(), "row_count": len(rows), "rows": rows}


@app.get("/mcp")
@app.get("/api/mcp")
def mcp_get(request: Request, authorization: str | None = Header(default=None)) -> StreamingResponse:
    _authorize_mcp(authorization, request)
    # Streamable HTTP clients may open an SSE stream even when this read-only
    # server has no server-initiated messages to send.
    async def events():
        yield b": connected\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@app.post("/mcp")
@app.post("/api/mcp")
async def mcp_post(
    request: Request,
    authorization: str | None = Header(default=None),
) -> Response:
    origin = request.headers.get("origin")
    if origin and origin not in {"https://chatgpt.com", "https://chat.openai.com"}:
        raise HTTPException(status_code=403, detail="Invalid MCP origin")
    settings = _authorize_mcp(authorization, request)
    try:
        message = await request.json()
    except Exception as exc:
        return JSONResponse(_mcp_error(None, -32700, "Parse error"), status_code=400)
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return JSONResponse(_mcp_error(None, -32600, "Invalid Request"), status_code=400)

    message_id = message.get("id")
    method = message.get("method")
    if method == "notifications/initialized":
        return Response(status_code=202)
    if method == "initialize":
        return JSONResponse({"jsonrpc": "2.0", "id": message_id, "result": initialize_result()})
    if method == "ping":
        return JSONResponse({"jsonrpc": "2.0", "id": message_id, "result": {}})
    if method == "tools/list":
        return JSONResponse({"jsonrpc": "2.0", "id": message_id, "result": {"tools": TOOLS}})
    if method == "tools/call":
        params = message.get("params")
        if not isinstance(params, dict) or not isinstance(params.get("name"), str):
            return JSONResponse(_mcp_error(message_id, -32602, "Invalid tool parameters"), status_code=400)
        arguments = params.get("arguments", {})
        if not isinstance(arguments, dict):
            return JSONResponse(_mcp_error(message_id, -32602, "arguments must be an object"), status_code=400)
        database = SupabaseREST(
            settings.supabase_url, settings.supabase_secret_key, settings.supabase_table
        )
        activities_database = SupabaseREST(
            settings.supabase_url, settings.supabase_secret_key, "garmin_activities"
        )
        metrics_database = SupabaseREST(
            settings.supabase_url, settings.supabase_secret_key, "garmin_metric_payloads"
        )
        result = tool_result(
            params["name"],
            arguments,
            database,
            settings.tz_name,
            activities_database,
            metrics_database,
        )
        return JSONResponse({"jsonrpc": "2.0", "id": message_id, "result": result})
    return JSONResponse(_mcp_error(message_id, -32601, "Method not found"), status_code=404)


@app.get("/.well-known/oauth-protected-resource/mcp")
@app.get("/api/oauth-protected-resource")
def oauth_protected_resource(request: Request) -> JSONResponse:
    """OAuth protected-resource metadata used by MCP clients for discovery."""
    supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    if not supabase_url:
        raise HTTPException(status_code=503, detail="SUPABASE_URL is not configured")
    return JSONResponse(
        {
            "resource": f"{str(request.base_url).rstrip('/')}/mcp",
            "authorization_servers": [f"{supabase_url}/auth/v1"],
            "bearer_methods_supported": ["header"],
        }
    )


@app.get("/oauth/consent", response_class=HTMLResponse)
@app.get("/api/consent", response_class=HTMLResponse)
def oauth_consent() -> HTMLResponse:
    """Minimal browser consent page used by Supabase's OAuth 2.1 server."""
    supabase_url = os.getenv("SUPABASE_URL", "")
    publishable_key = os.getenv("SUPABASE_PUBLISHABLE_KEY", "")
    if not supabase_url or not publishable_key:
        raise HTTPException(status_code=503, detail="Supabase OAuth browser configuration is incomplete")
    config = json.dumps({"url": supabase_url, "key": publishable_key})
    return HTMLResponse(
        f"""<!doctype html>
<html><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>Authorize Garmin Health</title></head>
<body><main><h1>Garmin Health</h1><p id=\"status\">Preparing secure sign-in…</p>
<button id=\"approve\" hidden>Allow read-only health data</button>
<button id=\"deny\" hidden>Deny</button></main>
<script type=\"module\">
import {{ createClient }} from 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/+esm';
const config = {config};
const supabase = createClient(config.url, config.key);
const status = document.querySelector('#status');
const approve = document.querySelector('#approve');
const deny = document.querySelector('#deny');
const authorizationId = new URLSearchParams(location.search).get('authorization_id');
if (!authorizationId) {{ status.textContent = 'Missing authorization request.'; }} else {{
  const {{ data: {{ session }} }} = await supabase.auth.getSession();
  if (!session) {{
    status.textContent = 'Redirecting to Google sign-in…';
    const {{ error }} = await supabase.auth.signInWithOAuth({{ provider: 'google', options: {{ redirectTo: location.href }} }});
    if (error) status.textContent = error.message;
  }} else {{
    const {{ data, error }} = await supabase.auth.oauth.getAuthorizationDetails(authorizationId);
    if (error || !data) {{ status.textContent = error?.message || 'Invalid authorization request.'; }}
    else if (!('authorization_id' in data)) location.assign(data.redirect_url);
    else {{
      status.textContent = `Allow ${{data.client.name}} read-only access to your Garmin health data?`;
      approve.hidden = false; deny.hidden = false;
      approve.onclick = async () => {{ const {{ data, error }} = await supabase.auth.oauth.approveAuthorization(authorizationId); if (error) status.textContent = error.message; else location.assign(data.redirect_url); }};
      deny.onclick = async () => {{ const {{ data, error }} = await supabase.auth.oauth.denyAuthorization(authorizationId); if (error) status.textContent = error.message; else location.assign(data.redirect_url); }};
    }}
  }}
}}
</script></body></html>"""
    )
