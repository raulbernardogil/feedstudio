"""Reproducible performance measurement.

Usage:
    python -m scripts.benchmark path/to/feed.xml [--synthetic-mb 50 100] [--full]

Measures, per file:
- parse: streaming parse + schema inventory (wall time, tracemalloc peak).
- engine: applying a representative rule set to every product.
- full (--full): complete import + feed generation through the services
  against a temporary SQLite database (wall time per phase).

Results are printed as JSON so they can be stored with docs/performance.md.
Numbers depend on hardware; always report the machine used.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from feedstudio.ingestion.parser import ParserLimits, detect_structure, iter_items  # noqa: E402
from feedstudio.ingestion.schema import SchemaCollector  # noqa: E402
from feedstudio.rules.engine import CompiledRule, RuleEngine  # noqa: E402
from feedstudio.rules.schema import RuleDefinition  # noqa: E402

RULES = [
    {"name": "precio", "priority": 1, "target": "price", "actions": [{"type": "normalize_price"}]},
    {"name": "oferta", "priority": 1, "target": "sale_price", "actions": [{"type": "normalize_price"}]},
    {"name": "identificadores", "priority": 3, "target": "identifier_exists",
     "actions": [{"type": "map_values", "mappings": [{"from": "FALSE", "to": "no"}, {"from": "TRUE", "to": "yes"}]}]},
    {"name": "disp", "priority": 2, "target": "availability",
     "actions": [{"type": "map_values", "mappings": [{"from": "In Stock", "to": "in_stock"}]}]},
    {"name": "marca", "priority": 10, "target": "title",
     "condition": {"conditions": [{"field": "brand", "operator": "not_empty"},
                                  {"field": "title", "operator": "not_contains", "value_field": "brand"}]},
     "actions": [{"type": "prepend", "template": "{brand} "}]},
    {"name": "color", "priority": 20, "target": "title", "actions": [{"type": "append", "template": "[ - {color}][ - {size}]"}]},
    {"name": "desc", "priority": 30, "target": "description",
     "actions": [{"type": "collapse_whitespace"}, {"type": "set_if_empty", "template": "{title}[ de {brand}]."}]},
    {"name": "label", "priority": 40, "target": "custom_label_1",
     "condition": {"conditions": [{"field": "price", "operator": "greater_than", "value": "500000"}]},
     "actions": [{"type": "set_value", "template": "ticket_alto"}]},
]


def synthesize(source: Path, target_mb: int, out_dir: Path) -> Path:
    """Repeat the real items (with unique ids) until the file reaches target_mb."""
    out = out_dir / f"synthetic-{target_mb}mb.xml"
    text = source.read_text(encoding="utf-8")
    start, end = text.index("<item>"), text.rindex("</item>") + len("</item>")
    body = text[start:end]
    head, tail = text[:start], text[end:]
    target = target_mb * 1024 * 1024
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(head)
        written, copy = len(head.encode()), 0
        while written < target:
            chunk = body.replace("<g:id><![CDATA[", f"<g:id><![CDATA[C{copy}-")
            fh.write(chunk)
            written += len(chunk.encode())
            copy += 1
        fh.write(tail)
    return out


def _rss_mb() -> float | None:
    """Current resident memory of this process (includes lxml's native memory)."""
    try:
        import psutil
    except ImportError:
        return None
    return round(psutil.Process().memory_info().rss / 1024 / 1024, 1)


def measure_parse(path: Path) -> dict:
    """Streaming parse. Memory is sampled every 500 items: tracemalloc only sees
    Python objects, so RSS (via psutil) is reported too to include lxml."""
    limits = ParserLimits(max_bytes=1024 * 1024 * 1024)
    rss_before = _rss_mb()
    rss_peak = rss_before
    tracemalloc.start()
    t0 = time.perf_counter()
    structure = detect_structure(path, limits)
    collector = SchemaCollector()
    count = 0
    for item in iter_items(path, structure, limits):
        collector.add(item.attributes, item.qnames)
        count += 1
        if count % 500 == 0 and rss_peak is not None:
            rss_peak = max(rss_peak, _rss_mb() or 0)
    elapsed = time.perf_counter() - t0
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {"products": count, "fields": len(collector.fields), "seconds": round(elapsed, 2),
            "products_per_second": round(count / elapsed), "python_heap_peak_mb": round(peak / 1024 / 1024, 1),
            "rss_before_mb": rss_before, "rss_peak_sampled_mb": rss_peak}


def measure_engine(path: Path) -> dict:
    limits = ParserLimits(max_bytes=1024 * 1024 * 1024)
    structure = detect_structure(path, limits)
    products = [i.attributes for i in iter_items(path, structure, limits)]
    engine = RuleEngine([CompiledRule(i + 1, r["name"], RuleDefinition.model_validate(r)) for i, r in enumerate(RULES)])
    t0 = time.perf_counter()
    changed = sum(1 for p in products if engine.apply(p).changes)
    elapsed = time.perf_counter() - t0
    return {"rules": len(RULES), "products": len(products), "changed": changed, "seconds": round(elapsed, 2),
            "products_per_second": round(len(products) / elapsed)}


def measure_full(path: Path) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="feedstudio-bench-"))
    db_url = f"sqlite:///{(tmp / 'bench.db').as_posix()}"
    os.environ["FEEDSTUDIO_DATABASE_URL"] = db_url
    os.environ["FEEDSTUDIO_STORAGE_DIR"] = str(tmp / "storage")
    os.environ["FEEDSTUDIO_MAX_FEED_MB"] = "1024"
    from alembic import command
    from alembic.config import Config

    from feedstudio import config, db, jobs, storage
    from feedstudio.db import session_scope
    from feedstudio.models import Channel, FeedVersion, ProcessingJob, Rule, Source, SourceSnapshot

    config.get_settings.cache_clear()
    db.configure(db_url)
    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    cfg.attributes["database_url"] = db_url
    command.upgrade(cfg, "head")
    store = storage.LocalStorage(tmp / "storage")
    storage.set_storage(store)

    with session_scope() as s:
        src = Source(organization_id=1, name="bench", kind="upload")
        s.add(src)
        s.flush()
        snap = SourceSnapshot(source_id=src.id, status="pending")
        s.add(snap)
        s.flush()
        key = f"sources/{src.id}/snapshots/{snap.id}.xml"
        with open(path, "rb") as fh:
            store.put_stream(key, fh, 1024 ** 3)
        snap.storage_key = key
        job = ProcessingJob(organization_id=1, kind="import", source_id=src.id, params={"snapshot_id": snap.id}, events=[])
        s.add(job)
        s.flush()
        src_id, job_id = src.id, job.id
    t0 = time.perf_counter()
    jobs.run_job(job_id)
    import_s = time.perf_counter() - t0

    with session_scope() as s:
        status = s.get(ProcessingJob, job_id)
        assert status.status == "succeeded", status.error
        src = s.get(Source, src_id)
        ch = Channel(organization_id=1, source_id=src_id, name="g", kind="google", public_token=os.urandom(8).hex(), settings={})
        s.add(ch)
        s.flush()
        for i, r in enumerate(RULES):
            s.add(Rule(organization_id=1, source_id=src_id, channel_id=None, name=r["name"], priority=r["priority"],
                       definition=RuleDefinition.model_validate(r).model_dump(mode="json", by_alias=True)))
        v = FeedVersion(channel_id=ch.id, snapshot_id=src.active_snapshot_id, number=1)
        s.add(v)
        s.flush()
        gen = ProcessingJob(organization_id=1, kind="generate", channel_id=ch.id, params={"version_id": v.id}, events=[])
        s.add(gen)
        s.flush()
        gen_id, vid = gen.id, v.id
    t0 = time.perf_counter()
    jobs.run_job(gen_id)
    gen_s = time.perf_counter() - t0
    with session_scope() as s:
        g = s.get(ProcessingJob, gen_id)
        assert g.status == "succeeded", g.error
        v = s.get(FeedVersion, vid)
        result = {"import_seconds": round(import_s, 2), "generate_seconds": round(gen_s, 2),
                  "items": v.item_count, "errors": v.error_count, "warnings": v.warning_count,
                  "output_mb": round((v.size_bytes or 0) / 1024 / 1024, 1)}
    db.get_engine().dispose()
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("feed", type=Path)
    parser.add_argument("--synthetic-mb", type=int, nargs="*", default=[])
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()

    files = [args.feed]
    out_dir = Path(tempfile.mkdtemp(prefix="feedstudio-synth-"))
    files += [synthesize(args.feed, mb, out_dir) for mb in args.synthetic_mb]
    report = {"machine": {"python": platform.python_version(), "platform": platform.platform(),
                          "processor": platform.processor(), "cpus": os.cpu_count()}, "runs": []}
    for f in files:
        run = {"file": f.name, "size_mb": round(f.stat().st_size / 1024 / 1024, 1), "parse": measure_parse(f), "engine": measure_engine(f)}
        if args.full:
            run["full_pipeline_sqlite"] = measure_full(f)
        report["runs"].append(run)
        print(json.dumps(run, ensure_ascii=False), flush=True)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
