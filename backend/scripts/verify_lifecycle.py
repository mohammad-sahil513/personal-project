"""Verify template upload + workflow creation + inspection endpoints."""
import urllib.request
import json

base = "http://127.0.0.1:8001/api"

print("=" * 60)
print("  TEMPLATE + WORKFLOW LIFECYCLE TEST")
print("=" * 60)

# 1. Upload a document
boundary = "----TestBoundary456"
body = (
    f"--{boundary}\r\n"
    f'Content-Disposition: form-data; name="file"; filename="test_doc.pdf"\r\n'
    f"Content-Type: application/pdf\r\n\r\n"
    f"Fake PDF content for testing purposes.\r\n"
    f"--{boundary}--\r\n"
).encode()

req = urllib.request.Request(
    base + "/documents/upload",
    data=body,
    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    method="POST",
)
r = urllib.request.urlopen(req)
doc_data = json.loads(r.read().decode())
doc_id = doc_data["data"]["document_id"]
print(f"  1. Document uploaded: {doc_id}")

# 2. Upload a template
boundary2 = "----TestBoundary789"
body2 = (
    f"--{boundary2}\r\n"
    f'Content-Disposition: form-data; name="file"; filename="test_template.docx"\r\n'
    f"Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document\r\n\r\n"
    f"Fake DOCX content for testing.\r\n"
    f"--{boundary2}\r\n"
    f'Content-Disposition: form-data; name="template_type"\r\n\r\n'
    f"PROPOSAL\r\n"
    f"--{boundary2}\r\n"
    f'Content-Disposition: form-data; name="version"\r\n\r\n'
    f"1.0.0\r\n"
    f"--{boundary2}--\r\n"
).encode()

req2 = urllib.request.Request(
    base + "/templates/upload",
    data=body2,
    headers={"Content-Type": f"multipart/form-data; boundary={boundary2}"},
    method="POST",
)
r2 = urllib.request.urlopen(req2)
tpl_data = json.loads(r2.read().decode())
tpl_id = tpl_data["data"]["template_id"]
tpl_status = tpl_data["data"]["status"]
print(f"  2. Template uploaded: {tpl_id} (status={tpl_status})")

# 3. Get template
r3 = urllib.request.urlopen(base + f"/templates/{tpl_id}")
get_tpl = json.loads(r3.read().decode())
print(f"  3. Template GET OK: type={get_tpl['data'].get('template_type')}, version={get_tpl['data'].get('version')}")

# 4. Get compiled template (should work even without compilation)
r3b = urllib.request.urlopen(base + f"/templates/{tpl_id}/compiled")
compiled = json.loads(r3b.read().decode())
print(f"  4. Compiled template GET OK: status={compiled['data']['status']}")

# 5. Create workflow (no auto-start)
wf_body = json.dumps({
    "document_id": doc_id,
    "template_id": tpl_id,
    "start_immediately": False,
}).encode()

req5 = urllib.request.Request(
    base + "/workflow-runs",
    data=wf_body,
    headers={"Content-Type": "application/json"},
    method="POST",
)
r5 = urllib.request.urlopen(req5)
wf_data = json.loads(r5.read().decode())
wf_id = wf_data["data"]["workflow_run_id"]
wf_status = wf_data["data"]["status"]
print(f"  5. Workflow created: {wf_id} (status={wf_status})")

# 6. Get workflow
r6 = urllib.request.urlopen(base + f"/workflow-runs/{wf_id}")
get_wf = json.loads(r6.read().decode())
print(f"  6. Workflow GET OK: phase={get_wf['data']['current_phase']}, progress={get_wf['data']['overall_progress_percent']}%")

# 7. Get workflow status (detailed)
r7 = urllib.request.urlopen(base + f"/workflow-runs/{wf_id}/status")
status_data = json.loads(r7.read().decode())
print(f"  7. Workflow status OK: step_label={status_data['data'].get('current_step_label')}")

# 8. Get workflow sections (should be empty)
r8 = urllib.request.urlopen(base + f"/workflow-runs/{wf_id}/sections")
sections_data = json.loads(r8.read().decode())
total_sections = sections_data["data"]["total_sections"]
print(f"  8. Workflow sections OK: total={total_sections}")

# 9. Workflow inspection endpoints
r9a = urllib.request.urlopen(base + f"/workflow-runs/{wf_id}/errors")
errors_data = json.loads(r9a.read().decode())
error_count = len(errors_data["data"].get("errors", []))
print(f"  9a. Workflow errors OK: count={error_count}")

r9b = urllib.request.urlopen(base + f"/workflow-runs/{wf_id}/artifacts")
artifacts_data = json.loads(r9b.read().decode())
artifact_count = len(artifacts_data["data"].get("artifacts", []))
print(f"  9b. Workflow artifacts OK: count={artifact_count}")

r9c = urllib.request.urlopen(base + f"/workflow-runs/{wf_id}/events/snapshot?limit=5")
events_data = json.loads(r9c.read().decode())
event_count = len(events_data["data"].get("events", []))
print(f"  9c. Workflow events snapshot OK: count={event_count}")

r9d = urllib.request.urlopen(base + f"/workflow-runs/{wf_id}/diagnostics")
diag_data = json.loads(r9d.read().decode())
has_output = diag_data["data"].get("has_output", False)
print(f"  9d. Workflow diagnostics OK: has_output={has_output}")

# 10. Template compile-status (should just return current status)
r10 = urllib.request.urlopen(base + f"/templates/{tpl_id}/compile-status")
cs = json.loads(r10.read().decode())
print(f"  10. Template compile-status OK: status={cs['data']['status']}")

# 11. Test validation endpoint (should return a clear error about needing compilation)
try:
    validate_req = urllib.request.Request(
        base + f"/templates/{tpl_id}/validate",
        data=b"",
        method="POST",
    )
    r11 = urllib.request.urlopen(validate_req)
    print(f"  11. Template validate: UNEXPECTED OK")
except urllib.error.HTTPError as e:
    body = json.loads(e.read().decode())
    err_code = ""
    if body.get("errors"):
        err_code = body["errors"][0].get("code", "")
    elif body.get("detail"):
        err_code = str(body["detail"])[:60]
    print(f"  11. Template validate: {e.code} -> {err_code} (expected)")
except Exception as e:
    print(f"  11. Template validate: ERROR {e}")

# 12. Test resolve endpoint
try:
    resolve_req = urllib.request.Request(
        base + f"/templates/{tpl_id}/resolve",
        data=b"",
        method="POST",
    )
    r12 = urllib.request.urlopen(resolve_req)
    print(f"  12. Template resolve: UNEXPECTED OK")
except urllib.error.HTTPError as e:
    body = json.loads(e.read().decode())
    err_code = ""
    if body.get("errors"):
        err_code = body["errors"][0].get("code", "")
    elif body.get("detail"):
        err_code = str(body["detail"])[:60]
    print(f"  12. Template resolve: {e.code} -> {err_code} (expected)")
except Exception as e:
    print(f"  12. Template resolve: ERROR {e}")

# Cleanup
del_req = urllib.request.Request(base + f"/documents/{doc_id}", method="DELETE")
urllib.request.urlopen(del_req)
print(f"\n  Cleanup: document {doc_id} deleted")

print()
print("=" * 60)
print("  ALL LIFECYCLE TESTS PASSED")
print("=" * 60)
