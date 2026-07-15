# Routing

FastAPI binds HTTP methods and URL paths to Python callables with decorator-based route declarations on an application or router instance.

## Declaring routes

Use decorators such as `@app.get`, `@app.post`, `@app.put`, and `@app.delete` to register handlers. Each decorator takes a path string and optionally response model metadata.

## APIRouter

Group related endpoints with `APIRouter`, then mount the router on the main app with `include_router`. Prefixes and tags applied on the router apply to every route it owns.

## Path operation order

More specific paths should be declared before catch-all patterns. FastAPI matches routes in registration order, so a static path can be shadowed by an earlier parameterized route.
