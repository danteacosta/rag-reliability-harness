# Dependencies

Dependencies let you share reusable logic—database sessions, auth checks, pagination—across path operations without duplicating code in every handler.

## Depends

Declare a dependency with `Depends(callable)`. FastAPI resolves the callable (and its own nested dependencies) before invoking the path operation, then injects the result.

## Sub-dependencies

Dependency functions may themselves declare `Depends(...)` parameters. The framework builds a dependency tree and caches results for the duration of a single request when appropriate.

## Class-based dependencies

A class with a `__call__` method can act as a dependency. Instance state configured at construction time is available each time FastAPI invokes the class for a request.
