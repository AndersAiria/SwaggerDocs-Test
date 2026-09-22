# SwaggerDocs-Test

OpenAPI specifications hosted for use as **Airia custom MCP servers**.

Airia's MCP Gateway can turn a hosted OpenAPI spec into a live MCP server: it fetches the
YAML, parses it, and presents each operation as a tool an AI agent can call. The customer
publishes a static document; Airia runs the server.

## Contents

| File | Purpose |
|---|---|
| `sony-ci-openapi.yaml` | A curated 14-operation subset of the Sony Ci Media Cloud REST API |
| `sony-ci-openapi-BROKEN.yaml` | The same spec with eight deliberate faults, for demonstrating validation |
| `validate_openapi.py` | Pre-flight validator — run before registering a spec |

## Raw URLs

Use the `raw.githubusercontent.com` URL as the **OpenAPI spec URL** in Airia:

```
https://raw.githubusercontent.com/AndersAiria/SwaggerDocs-Test/main/sony-ci-openapi.yaml
```

Pair it with the upstream API base URL:

```
https://api.cimediacloud.com
```

## About `sony-ci-openapi.yaml`

Sony Ci publishes REST documentation at https://developers.cimediacloud.com/ but ships no
OpenAPI file, so this spec was authored from that documentation. Every path was verified
against the live docs on 2026-09-22.

The published Ci API exposes roughly 80 operations. This spec exposes **14**, chosen to cover
a realistic media-asset workflow while spanning the full risk range:

- **Read** — list workspaces, list and search workspace contents, get asset details, list
  elements, list media logs
- **Personal data** — list workspace members
- **Data egress** — generate a signed download URL for an asset's master media
- **Write** — update an asset, add custom metadata
- **Destructive** — trash assets, delete an asset, purge a trash bin, delete a workspace

Operations absent from this file cannot be called by an agent, and no prompt can reintroduce
them. That curation is the point: the spec is the tool surface.

The destructive operations are included deliberately so that a reviewer can see they exist and
decide on them explicitly, rather than trust that they were remembered. They are expected to be
denied at the gateway.

> This spec is authored, not official. It is not published or endorsed by Sony. Re-verify
> against your own contracted Ci version before any production use.

## Validating a spec

```bash
pip install pyyaml
python3 validate_openapi.py sony-ci-openapi.yaml
```

Checks that the document parses, is OpenAPI 3.x, declares an absolute `servers` URL, gives every
operation a unique and well-formed `operationId` and a usable `description`, declares every path
parameter, resolves every `$ref`, and defines the security schemes it references. It then groups
the destructive and data-egress operations for a security review.

Exit code `0` means valid. Compare:

```bash
python3 validate_openapi.py sony-ci-openapi-BROKEN.yaml   # 8 errors, exit 1
```

## Notes for registering a spec in Airia

- **Host the spec on GitHub.** Specs served from other hosts currently fail the spec test, and
  the save is gated on that test passing.
- **Keep specs small.** Multi-megabyte specs can fail to fetch. This one is 16 KB.
- **The authentication method is locked after creation.** Choose it deliberately the first time.
- Sony Ci expects `Authorization: Bearer <token>`, so register it with **API Key** auth. Ci
  issues tokens via the OAuth 2.0 password grant at `POST /oauth2/token`; tokens last 24 hours.
