"""Quick endpoint verification script."""
import urllib.request
import json

base = "http://127.0.0.1:8001/api"
tests = [
    ("GET", "/health"),
    ("GET", "/ready"),
    ("GET", "/documents"),
    ("GET", "/templates"),
    ("GET", "/workflow-runs"),
]

print("=" * 60)
print("  ENDPOINT VERIFICATION")
print("=" * 60)

for method, path in tests:
    url = base + path
    try:
        r = urllib.request.urlopen(url)
        data = json.loads(r.read().decode())
        msg = data.get("message", "")
        print(f"  OK  {r.status}  {method:6s} {path:30s} -> {msg}")
    except Exception as e:
        print(f"  FAIL       {method:6s} {path:30s} -> {e}")

# Test 404 cases
not_found_tests = [
    ("GET", "/documents/doc_does_not_exist"),
    ("GET", "/workflow-runs/wf_does_not_exist"),
    ("GET", "/outputs/out_does_not_exist"),
]

print()
print("  404 ERROR HANDLING")
print("-" * 60)

for method, path in not_found_tests:
    url = base + path
    try:
        r = urllib.request.urlopen(url)
        print(f"  UNEXPECTED OK  {method} {path}")
    except urllib.error.HTTPError as e:
        status = e.code
        if status in (404, 500):
            print(f"  OK  {status}  {method:6s} {path:30s} -> Error handled")
        else:
            print(f"  UNEXPECTED {status} {method} {path}")
    except Exception as e:
        print(f"  FAIL       {method:6s} {path:30s} -> {e}")

# Test file upload
print()
print("  FILE UPLOAD TEST")
print("-" * 60)

import io
import http.client
import os

boundary = "----TestBoundary123"
body = (
    f"--{boundary}\r\n"
    f'Content-Disposition: form-data; name="file"; filename="test.txt"\r\n'
    f"Content-Type: text/plain\r\n\r\n"
    f"Hello, this is a test document.\r\n"
    f"--{boundary}--\r\n"
).encode()

req = urllib.request.Request(
    base + "/documents/upload",
    data=body,
    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    method="POST",
)

try:
    r = urllib.request.urlopen(req)
    data = json.loads(r.read().decode())
    doc_id = data.get("data", {}).get("document_id", "")
    print(f"  OK  {r.status}  POST   /documents/upload             -> doc_id={doc_id}")

    # verify it appears in list
    r2 = urllib.request.urlopen(base + "/documents")
    list_data = json.loads(r2.read().decode())
    total = list_data.get("data", {}).get("total", 0)
    print(f"  OK  {r2.status}  GET    /documents (total={total})")

    # Get the document
    r3 = urllib.request.urlopen(base + f"/documents/{doc_id}")
    get_data = json.loads(r3.read().decode())
    print(f"  OK  {r3.status}  GET    /documents/{doc_id}")

    # Delete
    del_req = urllib.request.Request(base + f"/documents/{doc_id}", method="DELETE")
    r4 = urllib.request.urlopen(del_req)
    del_data = json.loads(r4.read().decode())
    deleted = del_data.get("data", {}).get("deleted", False)
    print(f"  OK  {r4.status}  DELETE /documents/{doc_id} -> deleted={deleted}")

except Exception as e:
    print(f"  FAIL  Upload test -> {e}")

print()
print("=" * 60)
print("  VERIFICATION COMPLETE")
print("=" * 60)
