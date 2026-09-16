# mongo-mos

Queries the DRS MOS Mongo collection for a list of `objectUrn` values and writes the
results to a CSV.

## Setup

Dependencies are managed with [uv](https://docs.astral.sh/uv/):

```bash
uv sync
```

Create a `.env` in this directory:

```
MONGO_URI=mongodb://USER:PASSWORD@mongo-prod1.lts.harvard.edu:27017/?authSource=drsmos&replicaSet=prodrs&readPreference=primary&ssl=false
MONGO_DB=drsmos
MONGO_COLLECTION=main
```

`MONGO_URI` is required; the other two default to `drsmos` / `main`. The URI holds a
live credential — keep the file at mode `600` and out of version control.

## Usage

```bash
uv run query_mos.py -i urns.txt -o out.csv
```

`urns.txt` is one `objectUrn` per line; blank lines and `#` comments are skipped and
duplicates are dropped. Use `-` for either path to read from stdin or write to stdout
(the summary line goes to stderr, so piping stays clean).

Other flags:

| Flag | Purpose |
| --- | --- |
| `--content-type {object,file}` | Only return documents of that type |
| `--include-missing` | Emit an empty row for urns that match nothing |
| `--separator` | Joins multiple `deliveryUrns` urls (default `\|`) |
| `--env`, `--db`, `--collection` | Override the `.env` values |
| `--batch-size` | objectUrns per `$in` query (default 500) |
| `--timeout-ms` | Server selection timeout (default 15000) |

## Output

```
objectUrn,correlationId,deliveryState,contentType,deliveryUrns
```

Two things to know about the shape of the data:

- The collection holds one document per object (`contentType: "object"`) plus one per
  file (`contentType: "file"`), all sharing the same `objectUrn` and `correlationId`.
  A single input urn therefore produces many rows — pass `--content-type object` for
  one row per urn.
- `deliveryUrns` is stored as a list of `{deliveryType, url, urn}` subdocuments. The
  CSV carries the `url` of each entry.

There is no `deliveryStatus` field in the collection; the delivery status is
`deliveryState`, with values `READY`, `STAGED`, `IN_PROGRESS` and `DELETED`.
