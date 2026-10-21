import json

from app.models import DocStatus
from app.services import pipeline
from app.services.bedrock import LocalBedrock
from app.services.store import MemoryStore
from lambdas.ingest_trigger import doc_ids_from_records


def rec(key):
    return {"body": json.dumps({"detail": {"object": {"key": key}}})}


def test_ingest_trigger_extracts_unique_doc_ids_and_skips_metadata_files():
    ids = doc_ids_from_records([rec("docs/a1/x.pdf"), rec("docs/a1/x.pdf.metadata.json"), rec("docs/b2/y.docx"),
                                rec("docs/a1/x.pdf"), rec("other/z.pdf"), rec("docs/c3/nested/z.pdf")])
    assert ids == ["a1", "b2"]


def test_batch_then_poll_marks_indexed_and_requests_summary():
    store = MemoryStore()
    for i in ("1", "2"):
        store.put_doc({"id": i, "title": i, "groups": ["A"], "status": DocStatus.UPLOADED, "updated_at": "2026-01-01"})
    bedrock = LocalBedrock(store)
    job = pipeline.start_batch(store, bedrock, ["1", "2"])
    assert store.get_doc("1")["status"] == DocStatus.INGESTING and store.get_doc("1")["job_id"] == job
    queued = []
    assert pipeline.poll_jobs(store, bedrock, queued.append) == 1
    assert store.get_doc("2")["status"] == DocStatus.INDEXED and queued == ["1", "2"]
    assert pipeline.poll_jobs(store, bedrock) == 0  # job đã xong, không xử lý lại


def test_failed_job_marks_docs_failed_and_skips_summary():
    store = MemoryStore()
    store.put_doc({"id": "1", "title": "1", "groups": ["A"], "status": DocStatus.UPLOADED})

    class Failing(LocalBedrock):
        def get_ingestion_job(self, job_id):
            return {"status": "FAILED", "failure_reasons": ["parse error"]}

    pipeline.start_batch(store, Failing(store), ["1"])
    queued = []
    pipeline.poll_jobs(store, Failing(store), queued.append)
    assert store.get_doc("1")["status"] == DocStatus.FAILED and queued == []


def test_lambda_modules_import_without_flask():
    """Lambda runtime không có Flask: import lambdas/app.services không được kéo theo Flask."""
    import subprocess, sys
    code = ("import sys; sys.modules['flask'] = None; "
            "import lambdas.ingest_trigger, lambdas.poll_jobs, lambdas.summarize")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
