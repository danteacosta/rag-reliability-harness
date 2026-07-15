# Application runtime config

Operational defaults for the HTTP service. This document is versioned so evals can simulate stale indexes.

## Default request timeout

default_request_timeout_seconds = 30

The HTTP layer aborts in-flight client requests that exceed this request timeout of 30 seconds. Treat 30 as the authoritative default request timeout for this configuration version.
