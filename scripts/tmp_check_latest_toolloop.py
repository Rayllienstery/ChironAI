import json
import sqlite3


def safe_json(x: str):
    try:
        return json.loads(x)
    except Exception:
        return None


def main() -> None:
    db = "C:/Users/Raylee/AI/logs/webui.db"
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    rows = cur.execute(
        "select id, message, metadata from logs where session_id='proxy' and source='proxy' order by id desc limit 200"
    ).fetchall()

    def is_target(user_text: str) -> bool:
        t = (user_text or "").lower()
        return ("@app.jsx" in t or "app.jsx" in t) and ("move rag" in t or ("rag" in t and "top" in t))

    picked = None
    for r in rows:
        md = r["metadata"]
        if not md:
            continue
        o = safe_json(md)
        if not isinstance(o, dict):
            continue
        tr = o.get("trace") if isinstance(o.get("trace"), dict) else {}
        req = tr.get("request") if isinstance(tr.get("request"), dict) else {}
        user_q = req.get("user_query_preview") or o.get("user_query") or ""
        if isinstance(user_q, str) and is_target(user_q):
            picked = (r["id"], o)
            break

    if picked is None:
        # Fallback: pick the latest with tools_count>0
        for r in rows:
            md = r["metadata"]
            if not md:
                continue
            o = safe_json(md)
            if not isinstance(o, dict):
                continue
            tr = o.get("trace") if isinstance(o.get("trace"), dict) else {}
            req = tr.get("request") if isinstance(tr.get("request"), dict) else {}
            if (req.get("tools_count") or 0) and int(req.get("tools_count") or 0) > 0:
                picked = (r["id"], o)
                break

    if picked is None:
        print("No proxy logs found")
        # Fallback: show latest 15 logs overall to discover where the new requests are logged.
        print("Latest 15 rows in logs (any session/source):")
        all_rows = cur.execute(
            "select id, session_id, source, message from logs order by id desc limit 15"
        ).fetchall()
        for rr in all_rows:
            print(
                "id",
                rr["id"],
                "session_id",
                rr["session_id"],
                "source",
                rr["source"],
                "message_preview",
                (rr["message"] or "")[:120].replace("\n", " "),
            )
        return

    # Always print a short summary of the latest proxy traces.
    latest_proxy_rows = cur.execute(
        "select id, message, metadata from logs where session_id='proxy' and source='proxy' order by id desc limit 12"
    ).fetchall()
    print("---- latest_proxy_summary ----")
    for rr in latest_proxy_rows:
        oo = safe_json(rr["metadata"] or "")
        trr = oo.get("trace") if isinstance(oo, dict) and isinstance(oo.get("trace"), dict) else {}
        reqr = trr.get("request") if isinstance(trr.get("request"), dict) else {}
        respr = trr.get("response") if isinstance(trr.get("response"), dict) else {}
        uq = reqr.get("user_query_preview") or ""
        cp = respr.get("content_preview") or ""
        print(
            "id",
            rr["id"],
            "tools",
            reqr.get("tools_count"),
            "has_tool_result",
            reqr.get("has_tool_result"),
            "stream",
            reqr.get("stream"),
            "tool_calls_count",
            respr.get("tool_calls_count"),
            "user_q",
            str(uq)[:60].replace("\n", " "),
            "resp",
            str(cp)[:60].replace("\n", " "),
        )

    log_id, o = picked
    tr = o.get("trace") if isinstance(o.get("trace"), dict) else {}
    req = tr.get("request") if isinstance(tr.get("request"), dict) else {}
    resp = tr.get("response") if isinstance(tr.get("response"), dict) else {}

    keys_req = [
        "tools_count",
        "tool_choice",
        "has_tool_result",
        "tool_loop_retry_enabled",
        "tool_result_indicates_failure",
        "tool_result_last_content_preview",
        "stream",
        "selected_edit_tool_name",
    ]
    keys_resp = ["tool_calls_count", "tool_mode_error", "content_preview", "content_length_chars"]

    print("picked_log_id", log_id)
    print("request", {k: req.get(k) for k in keys_req})
    print("response", {k: (resp.get(k)[:160] if isinstance(resp.get(k), str) else resp.get(k)) for k in keys_resp})

    con.close()


if __name__ == "__main__":
    main()

