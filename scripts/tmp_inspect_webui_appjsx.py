import json
import sqlite3


def main() -> None:
    db = "C:/Users/Raylee/AI/logs/webui.db"
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    rows = cur.execute(
        "select id, message, metadata from logs where session_id='proxy' and source='proxy' order by id desc limit 40"
    ).fetchall()
    for r in rows:
        msg = r["message"] or ""
        if "Generate a concise" in msg:
            continue
        if not r["metadata"]:
            continue
        try:
            o = json.loads(r["metadata"])
        except Exception:
            continue
        tr = o.get("trace") if isinstance(o.get("trace"), dict) else {}
        req = tr.get("request") if isinstance(tr.get("request"), dict) else {}
        resp = tr.get("response") if isinstance(tr.get("response"), dict) else {}
        uq = (req.get("user_query_preview") or o.get("user_query") or "").lower()
        if "app.jsx" not in uq and "llm" not in uq and "поставь" not in uq:
            continue
        print("--- id", r["id"])
        print("  message", (msg[:90] + "...") if len(msg) > 90 else msg)
        print(
            "  tools",
            req.get("tools_count"),
            "sel",
            req.get("selected_edit_tool_name"),
            "stream",
            req.get("stream"),
        )
        print("  user_q_preview", (req.get("user_query_preview") or "")[:160].replace("\n", " "))
        cp = resp.get("content_preview") or ""
        print("  resp_preview", cp[:200].replace("\n", " "))
        tc = resp.get("tool_calls") or []
        print("  tool_calls_n", len(tc))
        if tc and isinstance(tc[0], dict):
            fn = tc[0].get("function") or {}
            name = fn.get("name")
            raw_args = fn.get("arguments") or "{}"
            try:
                args = json.loads(raw_args)
            except Exception:
                args = {"_raw": raw_args[:200]}
            print("  tool_name", name)
            for k in ("path", "file_path", "mode", "replacement", "new_text", "content"):
                if k not in args:
                    continue
                v = args[k]
                s = str(v) if v is not None else ""
                tail = "..." if len(s) > 220 else ""
                print(f"    {k}_len", len(s), "preview", (s[:220] + tail).replace("\n", "\\n"))
    con.close()


if __name__ == "__main__":
    main()
