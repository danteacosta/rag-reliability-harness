# Attribution

The markdown files under `data/corpus/fastapi/` are **original paraphrases** written for this harness. They are inspired by themes covered in the public FastAPI documentation and are **not** copies of FastAPI source or docs text.

## Themes and inspiration

| Local file | Themes paraphrased | Public reference |
|---|---|---|
| `fastapi/routing.md` | Path operations, `APIRouter`, route ordering | [FastAPI Tutorial — First Steps / Bigger Applications](https://fastapi.tiangolo.com/) |
| `fastapi/path_parameters.md` | Path parameters, types, `Path()` constraints | [Path Parameters](https://fastapi.tiangolo.com/tutorial/path-params/) |
| `fastapi/dependencies.md` | `Depends`, sub-dependencies, class dependencies | [Dependencies](https://fastapi.tiangolo.com/tutorial/dependencies/) |
| `fastapi/security.md` | OAuth2 password flow, bearer tokens, scopes | [Security — OAuth2](https://fastapi.tiangolo.com/tutorial/security/) |
| `fastapi/middleware.md` | HTTP middleware, timing, exception flow | [Middleware](https://fastapi.tiangolo.com/tutorial/middleware/) |
| `fastapi/cors.md` | `CORSMiddleware`, origins, preflight | [CORS](https://fastapi.tiangolo.com/tutorial/cors/) |
| `fastapi/background_tasks.md` | `BackgroundTasks`, post-response work | [Background Tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/) |
| `fastapi/settings.md` | Settings / env-driven configuration patterns | [Settings and Environment Variables](https://fastapi.tiangolo.com/advanced/settings/) |
| `fastapi/connection_limits.md` | Distractor: pool idle/checkout deadlines (harness-authored) | N/A — synthetic for ambiguous-ranking evals |

## Mutable corpus

Files under `data/corpus/mutable/v1/` and `data/corpus/mutable/v2/` are **harness-authored** operational config snippets used to exercise stale-context drift. They are not derived from FastAPI documentation.

## License note

FastAPI is released under the MIT license. This project does not redistribute FastAPI documentation verbatim; only thematic attribution is provided above.
