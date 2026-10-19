import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, RedirectResponse, JSONResponse
from starlette.background import BackgroundTask
import httpx
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.middleware.cors import CORSMiddleware
import importlib

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded


import json
import time

with open('blacklist_endpoints.json', 'r') as f:
    blacklist = json.load(f)

# IP -> timestamp when blacklisted
blacklisted_ips: dict[str, float] = {}

BLACKLIST_DURATION = 24 * 60 * 60  # 24 hours

def check_blacklist(request: Request) -> None:
    now = time.time()

    # Remove expired bans
    expired_ips = [
        ip
        for ip, timestamp in blacklisted_ips.items()
        if now - timestamp >= BLACKLIST_DURATION
    ]

    for ip in expired_ips:
        del blacklisted_ips[ip]

    # Get client IP
    client_ip = request.client.host if request.client else None

    if not client_ip:
        raise HTTPException(status_code=403, detail="Forbidden")

    # Reject already-blacklisted IPs
    if client_ip in blacklisted_ips:
        raise HTTPException(status_code=403, detail="Forbidden")

    # Check requested endpoint
    requested_path = request.url.path

    if any(requested_path.endswith(endpoint) for endpoint in blacklist):
        blacklisted_ips[client_ip] = now
        raise HTTPException(status_code=403, detail="Forbidden")


def import_python_file(filepath):
    args = importlib.import_module(
        filepath.replace("/", ".").replace(".py", "")
    )
    return args


def get_clients(url2port):
    url2client = {}

    for (u, p) in url2port.items():
        c = httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{p:04d}/",
            timeout=60.0,
        )
        url2client[u] = c

    return url2client


# HTTPS Server (Main App)
app = FastAPI()


# Rate limiting
limiter = Limiter(
    key_func=get_remote_address
)

app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request, exc):
    return JSONResponse(
        status_code=429,
        content={
            "success": False,
            "code": "RATE_LIMIT_EXCEEDED",
            "message": "Too many requests.",
        },
    )


# Middleware
origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(HTTPSRedirectMiddleware)


settings = import_python_file("settings.py")
url2client = get_clients(settings.url2port)


@limiter.limit("120/minute")
async def _reverse_proxy(request: Request):
    check_blacklist(request)

    url = httpx.URL(
        path=request.url.path,
        query=request.url.query.encode("utf-8"),
    )

    domain = request.url.hostname

    if domain not in url2client:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "code": "INVALID_DOMAIN",
                "message": (
                    f"The domain {domain} is not a valid "
                    "configured domain."
                ),
            },
        )

    client = url2client[domain]

    req = client.build_request(
        request.method,
        url,
        headers=request.headers.raw,
        content=request.stream(),
    )

    try:

        r = await client.send(
            req,
            stream=True,
        )

        return StreamingResponse(
            r.aiter_raw(),
            status_code=r.status_code,
            headers=r.headers,
            background=BackgroundTask(
                r.aclose
            ),
        )

    except httpx.TimeoutException as exc:

        print(
            f"Proxy timeout for {domain}: {exc}"
        )

        return JSONResponse(
            status_code=504,
            content={
                "success": False,
                "code": "UPSTREAM_TIMEOUT",
                "message": (
                    f"Server for domain {domain} "
                    "took too long to respond."
                ),
            },
        )

    except httpx.ConnectError as exc:

        print(
            f"Proxy connection error for {domain}: {exc}"
        )

        return JSONResponse(
            status_code=502,
            content={
                "success": False,
                "code": "UPSTREAM_UNAVAILABLE",
                "message": (
                    f"Server for domain {domain} "
                    "is unavailable."
                ),
            },
        )

    except httpx.RequestError as exc:

        print(
            f"Proxy request error for {domain}: {exc}"
        )

        return JSONResponse(
            status_code=502,
            content={
                "success": False,
                "code": "UPSTREAM_ERROR",
                "message": (
                    f"An error occurred while contacting "
                    f"the server for domain {domain}."
                ),
            },
        )

    except Exception as exc:

        print(
            f"Unexpected proxy error for {domain}: {exc}"
        )

        return JSONResponse(
            status_code=502,
            content={
                "success": False,
                "code": "PROXY_ERROR",
                "message": "An internal proxy error occurred.",
            },
        )


app.add_route(
    "/{path:path}",
    _reverse_proxy,
    ["GET", "POST", "DELETE", "PUT"],
)


# HTTP Server (Redirect to HTTPS)
redirect_app = FastAPI()


@redirect_app.get("/{path:path}")
async def redirect_to_https(request: Request):

    https_url = request.url.replace(
        scheme="https"
    )

    print(https_url)

    return RedirectResponse(
        url=https_url,
        status_code=301,
    )


if __name__ == "__main__":
    import multiprocessing

    # HTTPS Server
    https_process = multiprocessing.Process(
        target=uvicorn.run,
        args=(app,),
        kwargs={
            "host": "0.0.0.0",
            "port": 8443,
            "ssl_keyfile": (
                f"/etc/letsencrypt/live/"
                f"{settings.SSLFOLDER}/privkey.pem"
            ),
            "ssl_certfile": (
                f"/etc/letsencrypt/live/"
                f"{settings.SSLFOLDER}/fullchain.pem"
            ),
        },
    )

    # HTTP Server (for redirection)
    http_process = multiprocessing.Process(
        target=uvicorn.run,
        args=(redirect_app,),
        kwargs={
            "host": "0.0.0.0",
            "port": 80,
        },
    )

    https_process.start()

    http_process.start()

    https_process.join()
    http_process.join()
