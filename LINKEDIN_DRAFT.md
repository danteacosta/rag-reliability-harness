# LinkedIn draft — why eval beats another RAG demo

Most “RAG portfolios” show a chat UI and a vector DB. Hiring managers already know retrieval exists. What they rarely see is **how you know it still works next week**.

I built an offline RAG reliability harness that treats eval as the product:

- Golden-set metrics (recall@k, MRR, groundedness, refusal accuracy)
- A CI gate that fails on regression (no API keys)
- Three named failure modes with reproducible catch rates: **stale-context**, **ambiguous-ranking**, **unsupported-answer** — 0% → 100% via `make simulate` on a public FastAPI-style corpus

Demos impress for 30 seconds. Eval gates protect the next release.

Repo: `https://github.com/danteacosta/rag-reliability-harness`

---

# Versão PT-BR (curta)

A maioria dos portfólios de RAG mostra um chat e um vector DB. O mercado já sabe que retrieval existe. O que quase ninguém mostra é **como garantir que continua certo na próxima semana**.

Montei um harness offline de confiabilidade: golden set, gate no CI (sem API keys) e três modos de falha nomeados — contexto stale, ranking ambíguo e resposta sem suporte — com taxas de captura reproduzíveis via `make simulate`.

Demo impressiona 30 segundos. Eval protege o próximo release.

Repo: `https://github.com/danteacosta/rag-reliability-harness`
