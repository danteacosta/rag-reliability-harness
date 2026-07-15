# Background tasks

Background tasks run work after the response has been sent, without blocking the client on secondary side effects.

## BackgroundTasks parameter

Inject `BackgroundTasks` into a path operation. Call `background_tasks.add_task(func, *args)` to schedule work that executes after the response is returned.

## Typical uses

Send confirmation emails, write audit logs, or invalidate caches as background tasks. Keep tasks short; long-running jobs belong in a dedicated worker queue.

## Error handling

Exceptions inside background tasks are logged by the server but do not change the HTTP status already sent to the client. Design tasks to be idempotent when retries are possible.
