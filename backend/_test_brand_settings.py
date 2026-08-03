import json
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"


def req(method, path, data=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = None if data is None else json.dumps(data, ensure_ascii=False).encode("utf-8")
    r = urllib.request.Request(BASE + path, data=body, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=60) as resp:
        raw = resp.read()
        ctype = resp.headers.get("content-type", "")
        if "json" in ctype:
            return resp.status, json.loads(raw.decode("utf-8"))
        return resp.status, raw


def main():
    st, login = req("POST", "/api/v1/auth/login", {"username": "admin", "password": "Admin@12345"})
    token = login.get("access_token") or login.get("token")
    print("login", st, bool(token))

    st, brand = req("GET", "/api/v1/public/app-settings/brand")
    print("public_brand", st, brand.get("org_abbr"), brand.get("primary_color"))

    st, form = req("GET", "/api/v1/public/app-settings/registration-form")
    print("public_form_fields", st, len(form.get("fields") or []))

    st, put = req(
        "PUT",
        "/api/v1/admin/app-settings/brand",
        {"settings": {**brand, "secondary_color": "#C89B3C"}},
        token,
    )
    print("put_brand", st, put.get("success"))

    st, form2 = req("GET", "/api/v1/admin/app-settings/registration-form", token=token)
    st, putf = req(
        "PUT",
        "/api/v1/admin/app-settings/registration-form",
        {"settings": form2},
        token,
    )
    print("put_form", st, putf.get("success"))

    st, pdata = req(
        "GET",
        "/api/v1/admin/registrations/print-data?max_records=5&scope=filtered",
        token=token,
    )
    print(
        "print",
        st,
        "rows",
        len(pdata.get("items") or []),
        "color",
        pdata.get("primary_color"),
        "title",
        pdata.get("report_title"),
    )

    st, xbytes = req("GET", "/api/v1/admin/registrations/export-xlsx?max_records=5", token=token)
    path = "_test_out/brand_report.xlsx"
    with open(path, "wb") as f:
        f.write(xbytes if isinstance(xbytes, (bytes, bytearray)) else b"")
    print("excel", st, "size", len(xbytes) if isinstance(xbytes, (bytes, bytearray)) else 0)

    try:
        req("GET", "/api/v1/admin/app-settings/brand")
        print("no_auth_unexpected_ok")
    except urllib.error.HTTPError as e:
        print("no_auth_brand_blocked", e.code)

    # permission keys on me / check-admin
    st, me = req("GET", "/api/v1/auth/me", token=token)
    perms = (me.get("permissions") if isinstance(me, dict) else None) or {}
    print(
        "perms",
        perms.get("manage_brand_settings"),
        perms.get("manage_registration_form_settings"),
    )

    print("DONE")


if __name__ == "__main__":
    main()
