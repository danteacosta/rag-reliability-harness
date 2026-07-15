# Path parameters

Path parameters capture dynamic segments of the URL and pass them into the path operation function as typed arguments.

## Curly brace syntax

Declare a path parameter by wrapping its name in curly braces inside the route path, for example `/items/{item_id}`. The function parameter name must match the brace name.

## Type conversion

Annotate path parameters with Python types such as `int` or `UUID`. FastAPI validates and converts the path segment before calling your function, returning a validation error when conversion fails.

## Path constraints

Use `Path()` to attach validation rules: minimum and maximum values, string length bounds, and regex patterns. Constraints keep invalid identifiers from reaching business logic.
