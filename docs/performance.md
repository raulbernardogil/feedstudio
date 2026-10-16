# Performance measurements

Measured on 2026-10-16 with `backend/scripts/benchmark.py`. Reproduce:

```bash
cd backend
.venv/Scripts/python -m scripts.benchmark ../client_feed.xml --synthetic-mb 50 100 --full
```

Machine: Windows 11 (10.0.26300), AMD64 Family 25 (16 logical CPUs), Python 3.13.15,
SQLite (WAL) on local disk. Synthetic files repeat the real items with unique ids
until the target size is exceeded, hence 62 MB and 112 MB.

| File | Size | Products | Parse + schema | Rules (8) in memory | Import (parse + persist + validate) | Generate (rules + validate + XML + CSV) | Output XML |
|---|---|---|---|---|---|---|---|
| Real client feed | 12.5 MB | 4,159 | 2.2 s | 0.39 s | 2.54 s | 3.06 s | 11.8 MB |
| Synthetic | 62.4 MB | 20,795 | 12.2 s | 2.11 s | 14.36 s | 20.05 s | 58.9 MB |
| Synthetic | 112.4 MB | 37,431 | 19.2–28.3 s | 3.38 s | 25.49 s | 34.86 s | 106.0 MB |

Memory (parse phase, process RSS sampled every 500 items with psutil):

| File | RSS before | RSS peak (sampled) |
|---|---|---|
| 12.5 MB | 37.2 MB | 39.0 MB |
| 112.4 MB | 38.2 MB | 40.0 MB |

`tracemalloc` reports ~0.3 MB because it only tracks Python objects; lxml's
native memory is only visible in RSS. Full-pipeline memory was not measured.

Docker Compose stack (PostgreSQL 16 + Redis + 1 RQ worker, Docker Desktop on
WSL 2, same machine), real feed, job durations reported by the worker:

| Step | Duration |
|---|---|
| Import (4,159 products, 22 attributes) | 4.2 s |
| Generate with 4 rules (4,159 items, XML 11.8 MB) | 5.6 s |

Not measured yet: concurrent users, several workers, files above 112 MB on
PostgreSQL.

The real feed contains long descriptions (~3 KB per item), so throughput in
products/second is lower than for typical feeds with short descriptions.
