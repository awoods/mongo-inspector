#!/usr/bin/env python3
"""Query the DRS MOS Mongo collection for a list of objectUrn values and write a CSV.

Connection settings come from a .env file (MONGO_URI, MONGO_DB, MONGO_COLLECTION).

deliveryUrns is stored as a list of {deliveryType, url, urn} subdocuments; the CSV
carries the url of each one.

The collection stores one document per object (contentType="object") plus one per
file (contentType="file"); all of them share the same objectUrn, so a single input
urn normally yields several output rows. Use --content-type to narrow that down.
"""

import argparse
import csv
import os
import sys

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import PyMongoError

DEFAULT_DB = "drsmos"
DEFAULT_COLLECTION = "main"

FIELDNAMES = ["objectUrn", "correlationId", "deliveryState", "contentType", "deliveryUrns"]


def read_urns(path):
    """Read objectUrns one per line, skipping blanks and # comments, keeping order."""
    seen, urns = set(), []
    stream = sys.stdin if path == "-" else open(path, encoding="utf-8-sig")
    try:
        for line in stream:
            urn = line.strip()
            if not urn or urn.startswith("#"):
                continue
            if urn not in seen:
                seen.add(urn)
                urns.append(urn)
    finally:
        if stream is not sys.stdin:
            stream.close()
    return urns


def format_delivery_urns(value, separator):
    """Join the url of each deliveryUrns subdocument: {deliveryType, url, urn}."""
    if not value:
        return ""
    urls = [entry.get("url") for entry in value if isinstance(entry, dict)]
    return separator.join(str(u) for u in urls if u)


def build_row(doc, separator):
    return {
        "objectUrn": doc.get("objectUrn", ""),
        "correlationId": doc.get("correlationId", ""),
        "deliveryState": doc.get("deliveryState", ""),
        "contentType": doc.get("contentType", ""),
        "deliveryUrns": format_delivery_urns(doc.get("deliveryUrns"), separator),
    }


def chunked(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Query Mongo for objectUrn values and write correlationId, "
                    "deliveryState, contentType and deliveryUrns to a CSV.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("-i", "--input", required=True,
                   help="File of objectUrn values, one per line ('-' for stdin).")
    p.add_argument("-o", "--output", required=True,
                   help="Output CSV path ('-' for stdout).")
    p.add_argument("--env", default=".env", help="Path to the .env file.")
    p.add_argument("--db", help="Database name (default: MONGO_DB or %s)." % DEFAULT_DB)
    p.add_argument("--collection",
                   help="Collection name (default: MONGO_COLLECTION or %s)." % DEFAULT_COLLECTION)
    p.add_argument("--content-type", choices=["object", "file"],
                   help="Only return documents of this contentType.")
    p.add_argument("--separator", default="|",
                   help="Separator between multiple deliveryUrns urls.")
    p.add_argument("--batch-size", type=int, default=500,
                   help="Number of objectUrns per $in query.")
    p.add_argument("--include-missing", action="store_true",
                   help="Emit a row with empty columns for objectUrns that match nothing.")
    p.add_argument("--timeout-ms", type=int, default=15000,
                   help="Server selection timeout in milliseconds.")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    load_dotenv(args.env)
    uri = os.getenv("MONGO_URI")
    if not uri:
        sys.exit("MONGO_URI is not set in %s (or the environment)." % args.env)
    db_name = args.db or os.getenv("MONGO_DB") or DEFAULT_DB
    coll_name = args.collection or os.getenv("MONGO_COLLECTION") or DEFAULT_COLLECTION

    urns = read_urns(args.input)
    if not urns:
        sys.exit("No objectUrn values found in %s." % args.input)

    projection = {"_id": 0, "objectUrn": 1, "correlationId": 1, "deliveryState": 1,
                  "contentType": 1, "deliveryUrns": 1}

    out = sys.stdout if args.output == "-" else open(args.output, "w", newline="", encoding="utf-8")
    client = MongoClient(uri, serverSelectionTimeoutMS=args.timeout_ms)
    rows = 0
    found = set()
    try:
        collection = client[db_name][coll_name]
        writer = csv.DictWriter(out, fieldnames=FIELDNAMES)
        writer.writeheader()
        for batch in chunked(urns, args.batch_size):
            query = {"objectUrn": {"$in": batch}}
            if args.content_type:
                query["contentType"] = args.content_type
            for doc in collection.find(query, projection):
                writer.writerow(build_row(doc, args.separator))
                rows += 1
                found.add(doc.get("objectUrn"))
        missing = [u for u in urns if u not in found]
        if missing and args.include_missing:
            for urn in missing:
                writer.writerow({"objectUrn": urn, "correlationId": "", "deliveryState": "",
                                 "contentType": "", "deliveryUrns": ""})
                rows += 1
    except PyMongoError as exc:
        sys.exit("Mongo error: %s" % exc)
    finally:
        if out is not sys.stdout:
            out.close()
        client.close()

    print("%d objectUrns queried, %d matched, %d rows written to %s"
          % (len(urns), len(found), rows, args.output), file=sys.stderr)
    if missing:
        print("%d objectUrns had no matching document%s"
              % (len(missing), "" if args.include_missing else " (use --include-missing to list them)"),
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
