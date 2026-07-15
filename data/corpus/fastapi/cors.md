# Cross-Origin Resource Sharing (CORS)

Browsers enforce same-origin policy; CORS headers tell the browser which foreign origins may call your API from JavaScript.

## CORSMiddleware

Enable CORS by adding Starlette's `CORSMiddleware` to the FastAPI application. Configure allowed origins, methods, and headers at registration time.

## Allowed origins

Set `allow_origins` to an explicit list of trusted front-end origins. Using `["*"]` with credentials disabled is convenient for local demos but is rarely appropriate in production.

## Preflight requests

Browsers send an `OPTIONS` preflight for non-simple cross-origin calls. `CORSMiddleware` answers those preflights using your configured methods and headers so the actual request can proceed.
