# Application settings

Centralize configuration with Pydantic settings models so environment variables and `.env` files feed typed fields.

## BaseSettings

Subclass `BaseSettings` (or the Pydantic v2 settings base) to declare fields such as database URLs, debug flags, and feature toggles. Field names map to environment variables automatically.

## Environment overrides

Values loaded from the environment override defaults defined on the settings class. Missing required fields raise a validation error at startup instead of failing mid-request.

## Dependency injection of settings

Expose a `get_settings` dependency that returns a cached settings instance. Path operations depend on it to read configuration without importing globals everywhere.
