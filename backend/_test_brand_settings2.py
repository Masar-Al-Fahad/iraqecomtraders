import json
import sqlite3
import urllib.request

BASE = "http://127.0.0.1:8000"

body = json.dumps({"username": "admin", "password": "Admin@12345"}).encode()
r = urllib.request.Request(
    BASE + "/api/v1/auth/login",
    data=body,
    headers={"Content-Type": "application/json"},
    method="POST",
)
login = json.load(urllib.request.urlopen(r))
token = login.get("access_token") or login.get("token")
h = {"Authorization": "Bearer " + token}

r = urllib.request.Request(BASE + "/api/v1/admin/registrations?limit=5", headers=h)
data = json.load(urllib.request.urlopen(r))
print("regs_total", data.get("total"), "items", len(data.get("items") or []))

r = urllib.request.Request(
    BASE + "/api/v1/admin/registrations/print-data?scope=all&max_records=10",
    headers=h,
)
pdata = json.load(urllib.request.urlopen(r))
print(
    "print_all_rows",
    len(pdata.get("items") or []),
    "primary",
    pdata.get("primary_color"),
    "logo",
    pdata.get("logo"),
)

r = urllib.request.Request(
    BASE + "/api/v1/admin/registrations/export-xlsx?max_records=10",
    headers=h,
)
raw = urllib.request.urlopen(r).read()
open("_test_out/brand_report.xlsx", "wb").write(raw)
print("excel_size", len(raw), "is_xlsx", raw[:2] == b"PK")

r = urllib.request.Request(BASE + "/api/v1/admin/registrations/check-admin", headers=h)
chk = json.load(urllib.request.urlopen(r))
perms = chk.get("permissions") or {}
print(
    "check_admin",
    chk.get("is_super_admin"),
    perms.get("manage_brand_settings"),
    perms.get("manage_registration_form_settings"),
)

con = sqlite3.connect("local_app.db")
cur = con.cursor()
tables = [t[0] for t in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print("has_app_settings", "app_settings" in tables)
if "audit_logs" in tables:
    rows = cur.execute(
        "SELECT action, actor_email FROM audit_logs "
        "WHERE action LIKE '%brand%' OR action LIKE '%registration_form%' "
        "ORDER BY id DESC LIMIT 5"
    ).fetchall()
    print("audit_count", len(rows))
    for row in rows:
        print("AUDIT", row[0], row[1])
else:
    print("no_audit_table")

settings = cur.execute("SELECT key, length(value), updated_by FROM app_settings").fetchall()
print("settings_rows", settings)
print("DONE")
