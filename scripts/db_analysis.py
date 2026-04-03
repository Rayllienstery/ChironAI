import json
import sqlite3

conn = sqlite3.connect("logs/webui.db")
c = conn.cursor()

rows = c.execute("select id, timestamp, metadata from logs where source='proxy' order by id desc limit 30").fetchall()

picked = []

for rid, ts, md in rows:
    if md and ("test.swift" in md and "add 6" in md.lower()):
        picked.append((rid, ts, md))
    if len(picked) >= 2:
        break

print("PICKED", [(r[0], r[1]) for r in picked])

for r in picked:
    print("\n===", r[0], r[1], "\n", r[2])
