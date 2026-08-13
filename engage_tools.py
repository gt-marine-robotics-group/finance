"""
SharePoint File Download & Conversion Utilities

Downloads the bill spreadsheet from GT SharePoint and converts xlsx → csv.

=== SETUP ===

1. Register an app in Azure Portal (portal.azure.com):
   - App registrations → New registration
   - Name: "MRG Finance Automation" (or whatever)
   - Supported account types: "Accounts in this organizational directory only"
   - Enable "Allow public client flows" under Authentication
   - Add API permissions: Microsoft Graph → Delegated → Files.Read.All, Sites.Read.All

2. Create .env in this directory with AZURE_TENANT_ID, AZURE_CLIENT_ID, etc.

=== USAGE ===

    python engage_tools.py ls [folder]           # list SharePoint files
    python engage_tools.py download [-o file]    # download the spreadsheet
    python engage_tools.py convert file.xlsx     # convert xlsx to csv
"""

import os
import sys
import urllib.parse
import requests
import msal

# === Load config from .env file ===
def load_env():
    """Load environment variables from .env file if it exists."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())

load_env()

# === SharePoint / Microsoft Graph Config ===
TENANT_ID = os.environ.get("AZURE_TENANT_ID", "")
CLIENT_ID = os.environ.get("AZURE_CLIENT_ID", "")
SHAREPOINT_HOST = os.environ.get("SHAREPOINT_HOST", "gatech.sharepoint.com")
SHAREPOINT_SITE = os.environ.get("SHAREPOINT_SITE", "")
SHAREPOINT_FILE_PATH = os.environ.get("SHAREPOINT_FILE_PATH", "")

GRAPH_ENDPOINT = "https://graph.microsoft.com/v1.0"
GRAPH_SCOPES = ["Files.Read.All", "Sites.Read.All"]

TOKEN_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".token_cache.bin")


# ============================================================
# AUTHENTICATION
# ============================================================

def get_graph_token():
    """
    Authenticate to Microsoft Graph using device code flow.
    Caches token for reuse. First time: prompts user to open a URL and sign in.
    """
    if not TENANT_ID or not CLIENT_ID:
        print("❌ AZURE_TENANT_ID and AZURE_CLIENT_ID must be set in .env")
        sys.exit(1)

    authority = f"https://login.microsoftonline.com/{TENANT_ID}"

    # Token cache for persistence across runs
    cache = msal.SerializableTokenCache()
    if os.path.exists(TOKEN_CACHE_FILE):
        cache.deserialize(open(TOKEN_CACHE_FILE, "r").read())

    app = msal.PublicClientApplication(
        CLIENT_ID,
        authority=authority,
        token_cache=cache,
    )

    # Try silent token acquisition first
    accounts = app.get_accounts()
    result = None
    if accounts:
        result = app.acquire_token_silent(GRAPH_SCOPES, account=accounts[0])

    if not result:
        # Device code flow — user opens browser to authenticate
        flow = app.initiate_device_flow(scopes=GRAPH_SCOPES)
        if "user_code" not in flow:
            raise Exception(f"Failed to create device flow: {flow}")

        print(f"\n🔐 To sign in, open: {flow['verification_uri']}")
        print(f"   Enter code: {flow['user_code']}")
        print(f"   (Sign in with your @gatech.edu account)\n")

        result = app.acquire_token_by_device_flow(flow)

    # Save cache
    if cache.has_state_changed:
        with open(TOKEN_CACHE_FILE, "w") as f:
            f.write(cache.serialize())

    if "access_token" not in result:
        raise Exception(f"Authentication failed: {result.get('error_description', result)}")

    return result["access_token"]


# ============================================================
# SHAREPOINT OPERATIONS
# ============================================================

def _get_drive_id(headers):
    """Get the SharePoint site's default drive ID."""
    if not SHAREPOINT_SITE:
        print("❌ SHAREPOINT_SITE must be set in .env")
        print("   This is the part after /sites/ in your SharePoint URL")
        print("   Example: https://gatech.sharepoint.com/sites/MarineRoboticsGroup → MarineRoboticsGroup")
        sys.exit(1)

    # Get site ID
    site_url = f"{GRAPH_ENDPOINT}/sites/{SHAREPOINT_HOST}:/sites/{SHAREPOINT_SITE}"
    resp = requests.get(site_url, headers=headers)
    if resp.status_code != 200:
        print(f"❌ Failed to find site '{SHAREPOINT_SITE}': {resp.status_code}")
        print(f"   {resp.json().get('error', {}).get('message', resp.text)}")
        sys.exit(1)
    site_id = resp.json()["id"]

    # Get drive
    resp = requests.get(f"{GRAPH_ENDPOINT}/sites/{site_id}/drive", headers=headers)
    if resp.status_code != 200:
        print(f"❌ Failed to get drive: {resp.status_code} {resp.text}")
        sys.exit(1)
    return resp.json()["id"]


def download_from_sharepoint(output_path=None):
    """Download the bill spreadsheet from GT SharePoint."""
    if not SHAREPOINT_FILE_PATH:
        print("❌ SHAREPOINT_FILE_PATH must be set in .env")
        print("   Use 'python engage_tools.py ls' to browse for the file")
        sys.exit(1)

    token = get_graph_token()
    headers = {"Authorization": f"Bearer {token}"}
    drive_id = _get_drive_id(headers)

    # Get file metadata
    print(f"📡 Looking for: {SHAREPOINT_FILE_PATH}")
    file_url = urllib.parse.quote(SHAREPOINT_FILE_PATH)
    resp = requests.get(f"{GRAPH_ENDPOINT}/drives/{drive_id}/root:/{file_url}", headers=headers)
    if resp.status_code != 200:
        print(f"❌ File not found: {SHAREPOINT_FILE_PATH}")
        print(f"   {resp.json().get('error', {}).get('message', resp.text)}")
        sys.exit(1)
    file_info = resp.json()
    file_name = file_info["name"]
    file_size = file_info.get("size", 0)

    # Download content
    download_url = file_info.get("@microsoft.graph.downloadUrl")
    if download_url:
        resp = requests.get(download_url)
    else:
        file_id = file_info["id"]
        resp = requests.get(f"{GRAPH_ENDPOINT}/drives/{drive_id}/items/{file_id}/content", headers=headers)

    if resp.status_code != 200:
        print(f"❌ Failed to download: {resp.status_code}")
        sys.exit(1)

    # Save file
    if output_path is None:
        output_path = file_name
    with open(output_path, "wb") as f:
        f.write(resp.content)

    print(f"✅ Downloaded: {file_name} ({file_size:,} bytes) → {output_path}")
    return output_path


def list_sharepoint_files(folder_path=""):
    """List files in a SharePoint folder."""
    token = get_graph_token()
    headers = {"Authorization": f"Bearer {token}"}
    drive_id = _get_drive_id(headers)

    # List folder contents
    if folder_path:
        folder_url = urllib.parse.quote(folder_path)
        url = f"{GRAPH_ENDPOINT}/drives/{drive_id}/root:/{folder_url}:/children"
    else:
        url = f"{GRAPH_ENDPOINT}/drives/{drive_id}/root/children"

    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        print(f"❌ Failed to list folder: {resp.status_code}")
        print(f"   {resp.json().get('error', {}).get('message', resp.text)}")
        sys.exit(1)

    items = resp.json().get("value", [])

    print(f"\n📁 /{folder_path or '(root)'}")
    print(f"{'Type':<6} {'Size':<12} {'Name'}")
    print("-" * 60)
    for item in items:
        item_type = "📁" if "folder" in item else "📄"
        size = f"{item.get('size', 0):,}" if "file" in item else ""
        print(f"{item_type:<6} {size:<12} {item['name']}")
    return items


# ============================================================
# CLI
# ============================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description="SharePoint download & file utilities")
    subparsers = parser.add_subparsers(dest="command")

    # Download command
    dl_parser = subparsers.add_parser("download", help="Download spreadsheet from SharePoint")
    dl_parser.add_argument("-o", "--output", help="Output file path", default=None)

    # List command
    ls_parser = subparsers.add_parser("ls", help="List files in SharePoint folder")
    ls_parser.add_argument("folder", nargs="?", default="", help="Folder path to list")

    # Convert command (xlsx → csv)
    convert_parser = subparsers.add_parser("convert", help="Convert .xlsx to .csv")
    convert_parser.add_argument("input", help="Input .xlsx file")
    convert_parser.add_argument("-o", "--output", help="Output .csv file", default=None)

    args = parser.parse_args()

    if args.command == "download":
        download_from_sharepoint(output_path=args.output)

    elif args.command == "ls":
        list_sharepoint_files(args.folder)

    elif args.command == "convert":
        import pandas as pd
        output = args.output or args.input.rsplit(".", 1)[0] + ".csv"
        df = pd.read_excel(args.input)
        df.to_csv(output, index=False, encoding="utf-8-sig")
        print(f"✅ Converted: {args.input} → {output}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
