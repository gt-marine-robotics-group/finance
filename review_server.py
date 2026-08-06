"""
Local server for review.html to save price edits directly to the SharePoint-synced xlsx.

Start this before opening review.html:
    python review_server.py

It runs on http://localhost:8321 and accepts price updates from the browser.
"""

import os
import json
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import parse_qs
import openpyxl

XLSX_PATH = os.environ.get("FINANCE_XLSX_PATH", os.path.expanduser(
    "~/Library/CloudStorage/OneDrive-GeorgiaInstituteofTechnology/"
    "Documents - Marine Robotics Group/OPS-1 Operations/FY27 Finances/FY27_Bills_Budget.xlsx"
))
SHEET_NAME = "Bills"
PORT = 8321


class ReviewHandler(SimpleHTTPRequestHandler):
    def do_POST(self):
        if self.path == "/save-prices":
            content_length = int(self.headers["Content-Length"])
            body = self.rfile.read(content_length)
            data = json.loads(body)

            try:
                updates = data.get("prices", [])
                if not updates:
                    self._respond(400, {"error": "No prices provided"})
                    return

                # Open xlsx and update
                wb = openpyxl.load_workbook(XLSX_PATH)
                ws = wb[SHEET_NAME]

                # Find column indices
                headers = [cell.value for cell in ws[1]]
                name_col = None
                cost_col = None
                for i, h in enumerate(headers):
                    if h and str(h).strip() == "Item Name":
                        name_col = i
                    if h and str(h).strip() == "Cost":
                        cost_col = i

                if name_col is None or cost_col is None:
                    self._respond(500, {"error": "Could not find Item Name or Cost column"})
                    return

                updated = []
                for update in updates:
                    item_name = update["item_name"].strip()
                    new_price = update["price"]

                    # Find the row
                    for row in ws.iter_rows(min_row=2):
                        cell_name = row[name_col].value
                        if cell_name and str(cell_name).strip() == item_name:
                            row[cost_col].value = new_price
                            updated.append(item_name)
                            break

                wb.save(XLSX_PATH)
                print(f"✅ Updated {len(updated)} prices in spreadsheet")
                for name in updated:
                    print(f"   • {name}")

                # Touch the file to trigger OneDrive sync detection
                os.utime(XLSX_PATH, None)

                # Open the file in Excel so OneDrive syncs the changes
                import subprocess
                subprocess.run(["open", XLSX_PATH])
                print(f"   📂 Opened in Excel — save (Cmd+S) and close to ensure sync")

                self._respond(200, {"updated": updated, "count": len(updated)})

            except Exception as e:
                print(f"❌ Error: {e}")
                self._respond(500, {"error": str(e)})

        else:
            self._respond(404, {"error": "Not found"})

    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _respond(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, format, *args):
        # Only log POST requests, not static file requests
        if "POST" in str(args):
            super().log_message(format, *args)


if __name__ == "__main__":
    print(f"📝 Review server running on http://localhost:{PORT}")
    print(f"   Saving to: {XLSX_PATH}")
    print(f"   Press Ctrl+C to stop\n")
    server = HTTPServer(("localhost", PORT), ReviewHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Server stopped")
