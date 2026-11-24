# CLAUDE.md

Always respond to the user in Vietnamese. Keep code, comments, and commit messages in English.

## Project overview

- University DBMS course project (Bài tập lớn Hệ Quản trị CSDL): compare MySQL (InnoDB) and MongoDB (WiredTiger) on one e-commerce workload.
- Core goal: model the same domain in both databases, load identical large datasets, benchmark queries before and after indexing/optimization, and report latency, TPS, resource use, and disk footprint.
- Deliverables are source code, data scripts, a final report, and defense slides. This is not a production system.

## Tech stack

- Databases: MySQL (InnoDB), pinned to the 9.7 LTS line; MongoDB 6.0+ (WiredTiger), run as a single-node replica set (`rs0`) to support multi-document transactions — not a HA setup, just one node.
- Infrastructure: Docker, Docker Compose.
- Monitoring: Prometheus (`prom/prometheus:v3.15.0`), `mysqld_exporter` (`prom/mysqld-exporter:v0.19.0`), `mongodb_exporter` (`percona/mongodb_exporter:0.53.0`), Grafana (`grafana/grafana:13.2.2`). Grafana datasource + dashboards are provisioned from files in `infra/grafana/provisioning/`.
- Data seeding: Python with Faker, Pandas, `multiprocessing` and/or `asyncio`.
- Load testing: Grafana k6 (chosen 2026-10-28), custom binary built from `infra/k6/Dockerfile` with `xk6-sql` + MySQL driver and `xk6-mongo` (all versions pinned), driving both databases directly, no API layer, as the `k6` service (profile `loadtest`); see `docs/HUONG_DAN_BUILD_K6_EXTENSIONS.md`.

## Project structure

Proposed layout. Folders marked (planned) don't exist yet. Confirm before creating any folder not needed by the current phase.

- `docker-compose.yml`: all services (MySQL, MongoDB, Prometheus, exporters, Grafana). `mysql` service mounts `schema/mysql/schema.sql` at `/docker-entrypoint-initdb.d/01-schema.sql` — runs automatically on first start against an empty `mysql_data` volume. `mongodb-schema-init` (one-shot, after `mongodb-init`) mounts `schema/mongodb/` and runs `01-collections.js` then `02-indexes.js` on every `up`; it is idempotent but never drops anything, so an index removed from `02-indexes.js` must be dropped by hand in an existing database. Prometheus, the exporters and Grafana are currently commented out.
- `infra/prometheus/` (planned): Prometheus config and scrape targets.
- `infra/grafana/` (planned): Grafana provisioning (datasources, dashboards).
- `docs/PLAN.md` (planned): full phased plan.
- `docs/schema/`: `erd.dbml` (database-agnostic DBML model, shared reference before the MySQL/MongoDB split) + `erd.md` (entity/attribute writeup and full design review — ACID, 3NF, decisions log with rationale). Read `erd.md` before touching the schema; it is the source of truth for *why* the design looks the way it does.
- `schema/mysql/`: `schema.sql` — DDL for all 9 business-entity tables, written and verified against a live `mysql:9.7.2` container.
- `schema/mongodb/`: `01-collections.js` (6 collections with `$jsonSchema` validators) + `02-indexes.js` (uniqueness indexes only). Design rationale: `docs/schema/mongodb-design-summary.md`.
- `seed/` (Phase 3): `loaders/` and `checks/` (scripts run inside the `seed-*` one-shot services, profile `seed`) and `data/` (gitignored: the load-ready `mysql/`, `mongodb/`, `manifest.json`).
- `docs/benchmark-operations.md`: the chosen benchmark operations (class 1 queries, class 2 load flows). It is the list of queries to implement.
- `queries/` (planned, Phase 4): benchmark queries for both databases, `queries/{mysql,mongodb}/baseline/qN_<name>.{sql,js}`.
- `infra/k6/`: `Dockerfile` for the custom k6 binary (`dbperf-k6:local`).
- `benchmark/`: `scenarios/` (k6 scripts, mounted read-only at `/scripts` in the `k6` service) and `results/` (mounted writable at `/results`; baseline runs go in `results/baseline/`). Both are empty so far.
- `report/` (planned, Phase 6): final report and slides.

## Commands

- Validate stack: `docker compose config`
- Start stack: `docker compose up -d`
- Stop stack: `docker compose down`
- View logs: `docker compose logs -f <service>`
- Check status: `docker compose ps`
- Verify MySQL schema loaded: `docker compose exec mysql mysql -uroot -p"$MYSQL_ROOT_PASSWORD" dbperf -e 'SHOW TABLES;'` (expects 9 tables). Only re-runs `schema/mysql/schema.sql` on an empty volume — after editing it, `docker compose down -v && docker compose up -d` to force re-init.
- Verify MongoDB schema applied: `docker compose logs mongodb-schema-init` (expects the "collections ready" and "unique indexes ready" lines). Re-apply after editing `schema/mongodb/*.js`: `docker compose up -d` (or `docker compose run --rm mongodb-schema-init`).
- Install Python deps: TBD
- Load seed data (stack up, `seed/data/{mysql,mongodb}/` populated; reloads are idempotent, they empty the tables/collections first): `docker compose --profile seed run --rm seed-mysql` and `docker compose --profile seed run --rm seed-mongodb`. Each loads, then compares counts with `seed/data/manifest.json` (exit code 1 on mismatch). Verify only: append `/loaders/verify_mysql.sh` or `/loaders/verify_mongodb.sh` to the command. Scripts live in `seed/loaders/` and run inside the containers, so they work on any host OS.
- Check seeded data: `docker compose --profile seed run --rm seed-check-mysql` and `... seed-check-mongodb` (31 logic checks per DB, exit code 1 on FAIL; the second one run also compares with the first: identical check counts and aggregates). Scripts in `seed/checks/`.
- Build k6 image and check extensions: `docker compose --profile loadtest build k6 && docker compose --profile loadtest run --rm k6 version` (must list `k6/x/mongo`, `k6/x/sql`, `k6/x/sql/driver/mysql`).
- Run benchmarks: `docker compose --profile loadtest run --rm k6 run --summary-export=/results/baseline/<name>.json /scripts/<scenario>.js`. The `k6` service is capped at 2 CPUs / 2g; record this with every result.
- Test: TBD
- Lint/format: TBD

## Coding conventions

- Write all code, comments, identifiers, and commit messages in English.
- Pin every Docker image to an explicit version tag. Never use `latest`.
- Keep MySQL on the Oracle LTS line (currently pinned to `mysql:9.7.2`) and MongoDB on 6.0 or newer (currently pinned to `mongo:8.0.32`).
- Never hardcode credentials in `docker-compose.yml` or scripts. Read them from `.env`, keep `.env` in `.gitignore`, and commit a `.env.example` with placeholder values.
- Name Docker services by role: `mysql`, `mongodb`, `prometheus`, `mysqld-exporter`, `mongodb-exporter`, `grafana`.
- Persist database data in named Docker volumes so `docker compose down` does not wipe data.
- Naming style, formatter, test framework, and commit message format: TBD (see Open decisions). Until decided, keep commit messages short, imperative, and in English (e.g. `Add Prometheus scrape config for MongoDB exporter`).

## Phase 1 – Infrastructure (done; theory notes removed)

Monitoring stack is complete: `docker-compose.yml` starts MySQL, MongoDB (single-node replica set `rs0`), Prometheus, `mysqld_exporter`, `mongodb_exporter`, and Grafana; Prometheus scrapes both exporters; Grafana shows live metrics for both databases via provisioned dashboards.

The Phase 1 theory notes (CAP/ACID/BASE, InnoDB and WiredTiger internals, locking, transactions, and the MongoDB schema design notes) were removed from the repo on 2026-10-27 together with `docs/theory/`; they remain in git history.

## Phase 2 – Practical database schema design (done)

See `docs/PLAN.md` for all phases.

Goal: equivalent MySQL and MongoDB schemas for the same e-commerce business domain, each reflecting the natural strengths of its database paradigm.

Deliverables:



- [x] Entities defined: Customer, Product, Product SKU (variant), Inventory, Order — plus Category, Warehouse, Payment, Order detail (9 tables in `erd.dbml`). `order_status_history` and several attributes were dropped on 2026-10-22; see `docs/schema/erd.md` 3.4.22. Status/payment_method domains are per-table `ENUM` columns (a "one true lookup table" was tried and reverted — see `docs/schema/erd.md` 3.4.17/3.4.19 for why). See `docs/schema/erd.md` section 1 for the full attribute list and section 3 for the full design review (ACID, 3NF, every decision and trade-off made along the way, including 1 accepted deviation: `sku.variant_attributes` as JSON instead of strict 1NF).
- [x] MySQL schema (`schema/mysql/schema.sql`): 3NF design; price-at-purchase-time snapshotting solved via `order_detail.unit_price_snapshot`; Product vs SKU relationship modeled (`product` = concept, `sku` = priced/stocked variant). `order_detail.line_total` is a `GENERATED ALWAYS AS` column, DB-enforced; `orders.total_amount` (a cross-row aggregate, SUM of `line_total`) is a documented application-level convention instead, since MySQL can't enforce that one at the DB layer. Verified end-to-end against a live `mysql:9.7.2` container (DDL executes clean, FKs/CHECKs/generated columns behave as designed). Updated on 2026-10-22 to the simplified 9-table `erd.dbml` (see `docs/schema/erd.md` 3.4.22) and re-verified against a scratch database. An already-initialised `mysql_data` volume still holds the old 10-table schema until it is recreated.
- [x] MongoDB schema (`schema/mongodb/`): 6 collections (`categories`, `products` with embedded `skus[]`, `warehouses`, `inventory`, `customers`, `orders` with embedded `lines[]`, `payments[]`, `shipping`) covering the same 9 business entities. Embed line items, price snapshot, payments and shipping info directly into `Order`; reference Customer and Category (not embed) to stay under the 16MB document limit. Validators and the 4 uniqueness indexes (`skus.sku_id`, `skus.sku_code`, `(sku_id, warehouse_id)`, `email`) load cleanly into `mongo:8.0.32`. `docs/schema/mongodb-design-summary.md` summarizes the current design. The old 10-step tracker and agent prompt files were removed; the summary is the only MongoDB design record.

Done when: MySQL DDL and MongoDB validator/schema have been reviewed, and both models represent the exact same business scenarios. Both sides match the current 9-table ERD. Cross-review done on 2026-10-26: field-by-field parity confirmed; the only intentional differences are listed in `docs/schema/mongodb-design-summary.md` (last section).

## Phase 3 – Data generation and loading (done on the pilot set)

Closed on 2026-10-27 with the pilot dataset `pilot-20261024-final-v4` (5,000 customers, 2,000 SKUs, 100,000 orders; see `README.md` (Setup)). Both databases hold the same data: counts match `seed/data/manifest.json`, 31 logic checks per database pass (0 FAIL) with identical results, and 172 business aggregates are identical across MySQL and MongoDB.

Accepted gaps, carried forward:

- Scale is about 100x below the PLAN.md target (500K customers, 200K SKUs, 10M+ orders), and the repo has no generator (the data was produced outside the repo and is only placed in `seed/data/`), so the data cannot be regenerated or scaled from here. At 100K orders the data fits in cache, so latency differences and index effects in Phase 4–5 will be small; say so in the report.
- Known data issues (WARN level in `seed/checks/`): 39% of customers have `updated_at < created_at`, `unit_price_snapshot` always equals the catalog price, most `shipped` orders are old.
- Loader optimization (parallel table loads, split CSVs) and writing load times to a file are not done; notes are in `README.md` (section on loader optimization).

## Current phase: Phase 4 – Baseline and query optimizer analysis

See `docs/PLAN.md`. Goal: measure both databases before any optimization, as the reference for Phase 5.

Deliverables: optimizer theory note (CBO, `EXPLAIN ANALYZE` / `explain("executionStats")`), location to be decided now that `docs/theory/` is gone; the baseline queries (class 1 in `docs/benchmark-operations.md`) per database in `queries/{mysql,mongodb}/baseline/`; load scenarios in `benchmark/scenarios/` with results in `benchmark/results/baseline/`. Baseline means no indexes beyond what the schema requires.

File placement and result format are defined in the last section of `docs/benchmark-operations.md` (class 1: `queries/{mysql,mongodb}/baseline/qN_<name>.{sql,js}` with names `q1_revenue_by_month` … `q5_low_stock_by_warehouse`, results in `benchmark/results/baseline/{mysql,mongodb}/`; class 2: `benchmark/scenarios/<scenario>.<db>.js`). For every `qN` both databases must print the same TSV and `diff` must be empty before anything is timed. "Revenue" counts `delivered` orders only (team assumption, not yet confirmed by the instructor).

Two classes of baseline operations; details and open questions in `docs/benchmark-operations.md`. Both classes are chosen; open questions for class 2 are in that file:

- Class 1, infrequent but scanning many documents or collections, compared query by query (latency, execution plan): revenue by month; top SKUs by period; revenue by category; top customers by spend; low-stock report by warehouse.
- Class 2, frequent user-facing flows with many concurrent users, compared under load (TPS, latency under load, saturation): search and filter products (category, price, colour, name keyword, paginated); place an order (checkout, write, multi-document transaction). Other candidates were considered and dropped (product detail, stock view, record payment, cancel order, order history, order detail, customer lookup by email).
- Write flows change the data, so reload the seed data before each measured run and re-run `seed/checks/` afterwards (e.g. `inventory_reserved_ne_pending` detects lost updates).

Fairness note: InnoDB creates an index on every FK column, so MySQL already has an index on `orders.customer_id`, while MongoDB has none until Phase 5. Record this in the baseline results.

Dataset note: `seed/data/manifest.json` currently describes run `bigdata-final` (50,000 customers, 20,000 SKUs, 1,000,000 orders), not the 100K-order pilot described under Phase 3. The contract parameters were picked from this dataset; check which dataset is actually loaded in both databases before measuring.

## Out of scope for now

Do not build any of the following until the corresponding phase is active:

- Indexes beyond what the schema itself requires (PK/FK/unique constraints) — index tuning and additional indexes are Phase 5.
- Data generation or seeding scripts (Phase 3).
- Benchmark queries or k6 scenarios (Phase 4).
- Query optimization, pagination rewrites (Phase 5).
- Reports, charts, slides (Phase 6).
- Never implement these at any phase; they are report-only recommendations in Phase 6: replication/replica sets for HA, Redis, ProxySQL, table partitioning, sharding, archiving, RBAC/encryption setup, Flyway/Liquibase.

## Working rules for the agent

- Work only on the current phase. If a task belongs to a later phase, say so and ask before doing it.
- Ask before adding any new dependency, Docker service, or tool not listed in Tech stack.
- Keep each change small and focused on one deliverable. Do not refactor unrelated files.
- After changing `docker-compose.yml`, run `docker compose config` to validate it, then `docker compose up -d` and check `docker compose ps`.
- When writing Python code, add tests in the same change once a test framework is chosen.
- Do not make decisions listed under Open decisions. Ask the user instead.
- Update this file when a phase is completed, a command becomes defined, a convention changes, or an open decision is resolved.

## Open decisions

- Python version and dependency manager (pip + `requirements.txt`, Poetry, uv, ...).
- Test framework, linter, formatter for Python.
- Commit message format (free-form imperative vs Conventional Commits).
- Directory layout above: confirm or change.
- Language and format of the final report (Vietnamese/English; Markdown/Word/LaTeX).