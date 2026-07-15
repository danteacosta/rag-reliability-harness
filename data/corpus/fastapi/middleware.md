# Middleware

Middleware wraps every request and response, letting you run cross-cutting logic before and after path operations.

## Adding middleware

Register middleware with `@app.middleware("http")` or `app.add_middleware(...)`. The middleware function receives the request and a `call_next` callable that continues the stack.

## Request timing

A common pattern is to record a start timestamp, await `call_next(request)`, then attach an elapsed-time header on the response. Timing middleware must not block the event loop with synchronous heavy work.

## Exception awareness

Unhandled exceptions raised inside path operations still flow through middleware. You can catch them around `call_next` to log failures or rewrite error responses consistently.
