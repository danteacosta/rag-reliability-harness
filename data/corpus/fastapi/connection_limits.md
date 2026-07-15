# Connection pool limits

Database and upstream connection pools use separate idle deadlines from HTTP request timeouts.

## Idle connection deadline

The connection pool closes idle database sockets after an idle deadline of 120 seconds. This idle timeout governs pooled connections only; it does not abort an in-flight HTTP request.

## Pool checkout timeout

If no free connection is available, checkout waits up to a pool timeout before failing. A pool checkout timeout is a resource-acquisition deadline, not the default request timeout used by the HTTP layer.
