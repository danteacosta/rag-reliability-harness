# Security and OAuth2

FastAPI ships security utilities for common authentication flows, including OAuth2 password and bearer schemes.

## OAuth2 password flow

`OAuth2PasswordBearer` expects a token URL where clients exchange username and password for an access token. Protect routes by declaring the bearer scheme as a dependency.

## Bearer tokens

Clients send `Authorization: Bearer <token>` on subsequent requests. Your dependency extracts the token string; you verify it and load the current user before the path operation runs.

## Scopes

OAuth2 scopes express fine-grained permissions. Declare required scopes on the security dependency so unauthorized callers receive a 403 instead of reaching protected handlers.
