# Application runtime config

Operational defaults for the HTTP service. This document is versioned so evals can simulate stale indexes.

## Default request timeout

default_request_timeout_seconds = 60

The HTTP layer aborts in-flight client requests that exceed this request timeout of 60 seconds. Treat 60 as the authoritative default request timeout for this configuration version.
