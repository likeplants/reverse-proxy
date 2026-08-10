import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, HTMLResponse, RedirectResponse, JSONResponse
from starlette.background import BackgroundTask
from contextlib import asynccontextmanager
import httpx
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.middleware.cors import CORSMiddleware
import importlib

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

def import_python_file(filepath):
    args = importlib.import_module(filepath.replace("/", ".").replace(".py", ""))
    return args


def get_clients(url2port):
    url2client = {}
    for (u, p) in url2port.items():
        c = httpx.AsyncClient(base_url=f'http://127.0.0.1:{p:04d}/')
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
        content={"error": "too many requests"}
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
    url = httpx.URL(path=request.url.path, query=request.url.query.encode('utf-8'))
    domain = request.headers.get("host").split(":")[0]
    #print("DOMAIN:", request.headers)
    #domain = request.url.netloc
    domain = request.url.hostname
    if not domain in list(url2client.keys()):
        return HTMLResponse("The domain " + str(domain) + " is not in the list of valid urls", 400)
    client = url2client[domain]
    req = client.build_request(
        request.method, url, headers=request.headers.raw, content=request.stream())
    try:
        r = await client.send(req, stream=True)
        return StreamingResponse(
            r.aiter_raw(),
            status_code=r.status_code,
            headers=r.headers,
            background=BackgroundTask(r.aclose)
        )
    except Exception as e:
        print(e)
        return HTMLResponse("Server for domain " + domain + " at port " + str(settings.url2port[domain]) + " is down")

app.add_route("/{path:path}", _reverse_proxy, ["GET", "POST", "DELETE", "PUT"])


# HTTP Server (Redirect to HTTPS)
redirect_app = FastAPI()


@redirect_app.get("/{path:path}")
async def redirect_to_https(request: Request):
    https_url = request.url.replace(scheme="https")
    print(https_url)
    return RedirectResponse(url=https_url, status_code=301)

if __name__ == "__main__":
    import multiprocessing

    # HTTPS Server
    https_process = multiprocessing.Process(
        target=uvicorn.run,
        args=(app,),
        kwargs={
            "host": "0.0.0.0",
            "port": 443,
            "ssl_keyfile": f"/etc/letsencrypt/live/{settings.SSLFOLDER}/privkey.pem",
            "ssl_certfile": f"/etc/letsencrypt/live/{settings.SSLFOLDER}/fullchain.pem",
        },
    )

    # HTTP Server (for redirection)
    http_process = multiprocessing.Process(
        target=uvicorn.run,
        args=(redirect_app,),
        kwargs={"host": "0.0.0.0", "port": 80},
    )

    https_process.start()

    https_process.join()

