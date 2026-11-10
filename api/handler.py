"""Wanderly travel API: catalog in Aurora PostgreSQL, bookings in DynamoDB.

Custom compute (offering=lambda-custom). Routes:
  GET  /destinations[?q=&country=]  catalog search (Aurora, seeded lazily)
  GET  /destinations/{id}           one destination
  POST /bookings                    create booking (DynamoDB, priced from Aurora)
  GET  /bookings?email=...          a traveler's bookings
  GET  /__health
"""
import json
import os
import uuid
from decimal import Decimal

import boto3

TABLES = json.loads(os.environ.get("CAP_TABLES", "{}"))
rds = boto3.client("rds-data")
dynamo = boto3.resource("dynamodb")

SEED = [
    ("kyoto", "Kyoto in Bloom", "Japan", 1899, 4.9, "Temples, tea houses and spring gardens over six slow days.", "linear-gradient(135deg,#f6c6ea,#b8c6f9)"),
    ("santorini", "Santorini Caldera Escape", "Greece", 2249, 4.8, "Whitewashed villages, caldera sails and long lunches.", "linear-gradient(135deg,#aee3f5,#fdfbfb)"),
    ("patagonia", "Patagonia Trek", "Argentina", 2699, 4.9, "Granite towers, glaciers and refugio nights in El Chalten.", "linear-gradient(135deg,#89f7fe,#66a6ff)"),
    ("marrakech", "Marrakech & the Atlas", "Morocco", 1499, 4.7, "Medinas, mountain kasbahs and a desert night under stars.", "linear-gradient(135deg,#f6d365,#fda085)"),
    ("banff", "Banff Alpine Week", "Canada", 1799, 4.8, "Lakes, larches and gondola mornings in the Rockies.", "linear-gradient(135deg,#84fab0,#8fd3f4)"),
    ("amalfi", "Amalfi Coast Slow Travel", "Italy", 2599, 4.8, "Lemons, cliff paths and boat days between Positano and Ravello.", "linear-gradient(135deg,#fddb92,#d1fdff)"),
    ("hanoi", "Hanoi Food Trail", "Vietnam", 1199, 4.7, "Street-food safaris, old-quarter mornings and Ha Long Bay.", "linear-gradient(135deg,#ffecd2,#fcb69f)"),
    ("reykjavik", "Iceland Ring in Miniature", "Iceland", 2399, 4.9, "Waterfalls, black beaches and aurora hunts on the south coast.", "linear-gradient(135deg,#a1c4fd,#c2e9fb)"),
]
_ensured = False


def _sql(sql, params=()):
    cfg = TABLES["destinations"]
    return rds.execute_statement(
        resourceArn=cfg["clusterArn"], secretArn=cfg["secretArn"],
        database=cfg.get("database", "capdb"), sql=sql,
        parameters=[{"name": n, "value": v} for n, v in params],
        includeResultMetadata=True)


def ensure():
    global _ensured
    if _ensured:
        return
    _sql('CREATE TABLE IF NOT EXISTS "destinations" ("id" TEXT PRIMARY KEY, '
         '"name" TEXT, "country" TEXT, "price" DOUBLE PRECISION, '
         '"rating" DOUBLE PRECISION, "blurb" TEXT, "gradient" TEXT)')
    count = _rows(_sql('SELECT COUNT(*) AS n FROM "destinations"'))[0]["n"]
    if not count:
        for row in SEED:
            _sql('INSERT INTO "destinations" VALUES (:a,:b,:c,:d,:e,:f,:g) '
                 "ON CONFLICT (\"id\") DO NOTHING",
                 [("a", {"stringValue": row[0]}), ("b", {"stringValue": row[1]}),
                  ("c", {"stringValue": row[2]}), ("d", {"doubleValue": float(row[3])}),
                  ("e", {"doubleValue": float(row[4])}), ("f", {"stringValue": row[5]}),
                  ("g", {"stringValue": row[6]})])
    _ensured = True


def _rows(response):
    labels = [c.get("label") for c in response.get("columnMetadata", [])]
    out = []
    for record in response.get("records", []):
        row = {}
        for label, cell in zip(labels, record):
            row[label] = next(iter(cell.values())) if "isNull" not in cell else None
        out.append(row)
    return out


def bookings():
    return dynamo.Table(TABLES["bookings"]["table"])


def respond(status, body=None):
    return {"statusCode": status,
            "headers": {"Content-Type": "application/json",
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
                        "Access-Control-Allow-Headers": "Content-Type"},
            "body": "" if body is None else json.dumps(body)}


def handler(event, context=None):
    http = (event.get("requestContext") or {}).get("http") or {}
    method = http.get("method", "GET")
    parts = [p for p in (event.get("rawPath") or "/").split("/") if p]
    query = event.get("queryStringParameters") or {}
    payload = json.loads(event.get("body") or "{}")
    if method == "OPTIONS":
        return respond(204)
    try:
        ensure()
        if parts == ["__health"]:
            return respond(200, {"ok": True, "collections": sorted(TABLES)})
        if parts == ["destinations"] and method == "GET":
            clauses, params = [], []
            if query.get("country"):
                clauses.append('"country" = :country')
                params.append(("country", {"stringValue": query["country"]}))
            if query.get("q"):
                clauses.append('LOWER("name" || "blurb") LIKE :q')
                params.append(("q", {"stringValue": "%" + query["q"].lower() + "%"}))
            where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
            items = _rows(_sql(f'SELECT * FROM "destinations"{where} ORDER BY "rating" DESC', params))
            return respond(200, {"items": items})
        if len(parts) == 2 and parts[0] == "destinations" and method == "GET":
            found = _rows(_sql('SELECT * FROM "destinations" WHERE "id" = :id',
                               [("id", {"stringValue": parts[1]})]))
            return respond(200, found[0]) if found else respond(404, {"error": "not found"})
        if parts == ["bookings"] and method == "POST":
            dest_id = str(payload.get("destinationId", ""))
            found = _rows(_sql('SELECT * FROM "destinations" WHERE "id" = :id',
                               [("id", {"stringValue": dest_id})]))
            if not found:
                return respond(400, {"error": "unknown destination"})
            travelers = int(payload.get("travelers") or 1)
            booking = {
                "id": uuid.uuid4().hex, "destinationId": dest_id,
                "email": str(payload.get("email", "")), 
                "name": str(payload.get("name", "")),
                "travelers": Decimal(travelers),
                "date": str(payload.get("date", "")),
                "total": Decimal(str(found[0]["price"] * travelers)),
            }
            if not booking["email"] or not booking["date"]:
                return respond(400, {"error": "email and date are required"})
            bookings().put_item(Item=booking)
            booking["travelers"] = travelers
            booking["total"] = float(booking["total"])
            return respond(201, booking)
        if parts == ["bookings"] and method == "GET":
            email = query.get("email")
            if not email:
                return respond(400, {"error": "email query parameter required"})
            mine = [i for i in bookings().scan(Limit=500).get("Items", [])
                    if i.get("email") == email]
            for item in mine:
                for key, value in list(item.items()):
                    if isinstance(value, Decimal):
                        item[key] = int(value) if value == value.to_integral_value() else float(value)
            return respond(200, {"items": mine})
        return respond(404, {"error": "unknown route"})
    except Exception as error:
        return respond(500, {"error": str(error)[:300]})
