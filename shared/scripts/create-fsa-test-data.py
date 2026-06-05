"""Create test folder structure on smb_test_vol via ONTAP REST API.

This script creates a nested folder structure for FSA Explorer drill-down testing.
Run from a host that can reach the ONTAP management endpoint.

Usage:
  export ONTAP_IP=<management-ip>
  export ONTAP_PASS=$(aws secretsmanager get-secret-value --secret-id fsx-ontap-fsxadmin-credentials --query SecretString --output text | python3 -c "import sys,json; print(json.load(sys.stdin)['password'])")
  python3 shared/scripts/create-fsa-test-data.py
"""
import json
import urllib3
import os
import base64
import time
import sys

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ONTAP_IP = os.environ.get('ONTAP_IP')
ONTAP_PASS = os.environ.get('ONTAP_PASS')
SVM_NAME = os.environ.get('SVM_NAME', 'FPolicySMB')
VOL_NAME = os.environ.get('VOL_NAME', 'smb_test_vol')

if not ONTAP_IP or not ONTAP_PASS:
    print("Error: ONTAP_IP and ONTAP_PASS environment variables required")
    sys.exit(1)

http = urllib3.PoolManager(cert_reqs='CERT_NONE')
auth = base64.b64encode(f"fsxadmin:{ONTAP_PASS}".encode()).decode()
headers = {
    'Authorization': f'Basic {auth}',
    'Content-Type': 'application/json',
    'Accept': 'application/json'
}


def api_get(path):
    """GET request to ONTAP REST API."""
    url = f"https://{ONTAP_IP}/api{path}"
    resp = http.request('GET', url, headers=headers)
    return json.loads(resp.data.decode())


def api_post(path, body=None, content_type='application/json'):
    """POST request to ONTAP REST API."""
    url = f"https://{ONTAP_IP}/api{path}"
    h = dict(headers)
    if content_type != 'application/json':
        h['Content-Type'] = content_type
    payload = json.dumps(body).encode() if body and content_type == 'application/json' else body
    resp = http.request('POST', url, headers=h, body=payload)
    return resp.status, resp.data.decode()


def main():
    """Create test folder structure for FSA Explorer verification."""
    # Get volume UUID
    vols = api_get(f"/storage/volumes?name={VOL_NAME}&svm.name={SVM_NAME}&fields=uuid")
    if not vols.get('records'):
        print(f"Error: Volume {VOL_NAME} not found in SVM {SVM_NAME}")
        sys.exit(1)

    vol_uuid = vols['records'][0]['uuid']
    print(f"Volume: {VOL_NAME} (UUID: {vol_uuid})")
    print(f"SVM: {SVM_NAME}")
    print()

    # Create nested folder structure matching Excel verification data
    folders = [
        'folder1',
        'folder1/folder2',
        'folder1/folder2/folder3',
        'folder1/folder2/folder3/folder4',
        'folder1/folder2/folder3/folder4/folder5'
    ]

    print("Creating directories...")
    for folder in folders:
        path = f"/storage/volumes/{vol_uuid}/files/{folder}"
        status, data = api_post(path, {"type": "directory", "unix_permissions": "755"})
        status_icon = "ok" if status in (200, 201) else "!!"
        print(f"  [{status_icon}] {folder} (HTTP {status})")

    print()
    print("Creating test files...")
    for i, folder in enumerate(folders, start=1):
        file_num = i + 1
        for suffix in [str(file_num), str(file_num) * 2]:
            filepath = f"{folder}/text{suffix}.txt"
            url = f"https://{ONTAP_IP}/api/storage/volumes/{vol_uuid}/files/{filepath}?overwrite=true"
            content = f"Test file for FSA Explorer verification\nPath: /{filepath}\nCreated: {time.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
            resp = http.request('POST', url, headers={
                'Authorization': f'Basic {auth}',
                'Content-Type': 'application/octet-stream',
            }, body=content.encode())
            status_icon = "ok" if resp.status in (200, 201) else "!!"
            print(f"  [{status_icon}] {filepath} (HTTP {resp.status})")

    print()
    print("Test data created successfully!")
    print()
    print("Expected FSA Explorer behavior:")
    print("  / (root)")
    print("    folder1 -> 4 subdirs, 8 files")
    print("      folder2 -> 3 subdirs, 6 files")
    print("        folder3 -> 2 subdirs, 4 files")
    print("          folder4 -> 1 subdir, 2 files")
    print("            folder5 -> 0 subdirs, 2 files")


if __name__ == '__main__':
    main()
