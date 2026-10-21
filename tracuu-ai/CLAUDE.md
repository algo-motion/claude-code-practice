# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Tra Cứu AI: internal-document search and RAG Q&A (Vietnamese UI). Flask API + React SPA + Lambdas + AWS CDK. The sibling folder `../tracuu-ai-design/` holds the original prototype and the architecture/UML pages; `README.md` has deployment context.

## Commands

Run from this directory on Windows; the Python venv is `.venv\Scripts\python`.

```
# API with in-memory sample data (BACKEND=local, AUTH_MODE=dev), then the UI which proxies /api and /auth to :5000
.venv\Scripts\python -m flask --app app run --port 5000
npm run dev

.venv\Scripts\python -m pytest                              # backend (pytest.ini limits it to tests/)
.venv\Scripts\python -m pytest tests/test_api.py::test_feedback
npm run build                                               # only frontend check: no lint, no frontend tests

cd infra && .venv\Scripts\python -m pytest                  # CDK template assertions, ~25s, separate venv
cd infra && cdk deploy -c domain_name=... -c certificate_arn=... -c model_arn=...   # never deployed yet
```

Gotchas: the machine's `AWS_PROFILE` points at a profile that does not exist, so `tests/conftest.py` clears it and sets dummy credentials (keep that autouse fixture so tests can never reach real AWS). Printing Vietnamese from a script on this console fails under cp932; set `PYTHONUTF8=1`. Heredocs containing Vietnamese plus quotes break the Bash tool; write files with the Write tool.

## Architecture

**Four deployables share one codebase:** Flask app (`app/`), three Lambdas (`lambdas/`), React SPA (`src/`, built to `dist/` and served by Flask with SPA fallback), CDK stack (`infra/`).

**Backend modes.** `BACKEND=local|aws` and `AUTH_MODE=dev|alb` (see `app/config.py`). `create_app` refuses `dev` auth with `aws`. `app/services/__init__.py:build_services` wires three gateways that each have an AWS and a local implementation: `Store` (`DynamoStore`/`MemoryStore`), `Bedrock` (`AwsBedrock`/`LocalBedrock`), `Storage` (`S3Storage`/`LocalStorage`). Routes call `RagService`/`DocumentService`, never boto3. Store tests are one contract suite run against both stores (`store` fixture; DynamoStore uses moto). Local mode is seeded from `app/services/seed.json` and simulates S3 + EventBridge + Lambda ingestion with timers in `library/routes.py:register_local_upload`.

**Lambdas must not import Flask.** The Lambda runtime has none, and the package contains only `app/` + `lambdas/`. That is why Flask imports live inside `create_app` and why `app/services`, `models`, `config` must stay Flask-free (`test_lambda_modules_import_without_flask` guards it). Ingestion logic shared by API and Lambdas is `services/pipeline.py`.

**Authorization model (cross-cutting).** Identity and groups come only from the ALB-signed JWT (`app/auth`); never accept groups from the client. `user.groups` always includes "Toàn công ty"; admin means membership of `ADMIN_GROUP`. Retrieval is filtered server-side by per-group boolean metadata flags `g_<sha1(name)>` (`services/acl.py`, written to `<file>.metadata.json` next to each S3 object) using `equals`/`orAll`; `listContains` is deliberately avoided because only OpenSearch supports it. The same ACL also lives in DynamoDB (`ACL#` items, GSI1) for the UI, so group changes must update both. Unauthorized documents return 404, not 403.

**Q&A flow.** `RagService.ask` is a generator of events streamed by `search/routes.py` as SSE (`meta`, `delta`, `blocked`, `citations`, `done`, `error`). `AwsBedrock.ask_stream` inserts `[n]` markers numbered by first use of each source; the frontend maps `[n]` to `docs[n-1]`, so citation order must stay stable. The search page calls `/api/ask` with `save=false` (no chat session); chat uses a real session and stores Bedrock's `sessionId` instead of replaying history. Search history is written by `/api/search`, not `/api/ask`.

**Ingestion.** Upload creates the DOCUMENT item and metadata, returns a presigned PUT; S3 → EventBridge → SQS (60 s batching) → `ingest_trigger` → `pipeline.start_batch`; `poll_jobs` (every minute) moves docs to INDEXED/FAILED and queues summaries. Status lifecycle is `DocStatus` in `app/models.py`. DynamoDB key design is in `services/store.py` and documented in `../tracuu-ai-design/Thiet ke UML.html`.

**Frontend.** JSX (no TypeScript, no router); `App.jsx` holds the screen state and the three layouts (sidebar/topbar/rail) ported from the prototype. All server calls go through `src/api.js` (`askStream` parses SSE from a POST). The dev-only settings panel and `X-Dev-Role` header exist only under `import.meta.env.DEV`.

**Embedding model.** Default `cohere.embed-multilingual-v3` because Titan V2 is not offered in `ap-southeast-1`; the vector index dimension (1024) and chunk size (400 tokens for Cohere, 512 otherwise, in `infra/tracuu/rag.py`) depend on it, and changing it after data is loaded means rebuilding the index and re-ingesting everything. The admin page's `emb` setting is stored only; it does not switch the real model.

**Infra (`infra/tracuu/`).** One stack on purpose (separate stacks create KMS-key/role cycles). Required context: `domain_name`, `certificate_arn`, `model_arn`. Cost decisions are intentional, not omissions: S3 Vectors instead of OpenSearch (so `SEARCH_TYPE=SEMANTIC`, no hybrid) and public subnets with no NAT or interface endpoints. Lambda code is staged into `infra/.build/lambda` by `ingest.py:lambda_code()` because CDK's `exclude` globs do not match dot-folders and would zip `.venv`. `ALB_ARN` is not passed to the task (it would create a dependency cycle), so the JWT `signer` check is off. Infra tests only assert the synthesized template; real-AWS behaviour (S3 Vectors filters, region availability) is unverified.

**Design docs.** When architecture or data model changes, update `../tracuu-ai-design/Kien truc AWS.html` and `Thiet ke UML.html` (Mermaid blocks can be checked with the mermaid parser). The prototype `Tra Cuu AI.html` is stale: it still has the password login form and two admin tiles the real app removed.
