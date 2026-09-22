# SwaggerDocs-Test

OpenAPI specifications hosted for use as **Airia custom MCP servers**.

Airia's MCP Gateway can turn a hosted OpenAPI spec into a live MCP server: it fetches the
YAML, parses it, and presents each operation as a tool an AI agent can call. The customer
publishes a static document; Airia runs the server.

## video/ — three specs for the recorded walkthrough

| File | Beat | Expected in Airia |
|---|---|---|
| `video/sony-ci-read.yaml` | Golden path | Verifies, **6 tools**, no warnings |
| `video/sony-ci-admin.yaml` | Valid but unsafe | Verifies, **7 tools**, security flags on the destructive, egress and poisoned tools |
| `video/sony-ci-malformed.yaml` | Genuinely invalid | Fails at the **parse** stage, Save stays disabled |

```
https://raw.githubusercontent.com/AndersAiria/SwaggerDocs-Test/main/video/sony-ci-read.yaml
https://raw.githubusercontent.com/AndersAiria/SwaggerDocs-Test/main/video/sony-ci-admin.yaml
https://raw.githubusercontent.com/AndersAiria/SwaggerDocs-Test/main/video/sony-ci-malformed.yaml
```

Upstream base URL for all three: `https://api.cimediacloud.com`

`video/sony-ci-admin.yaml` contains a deliberate tool-poisoning sample in one description,
so that a security scan has something real to detect. It is a demo artifact.

## Contents

| File | Purpose |
|---|---|
| `sony-ci-openapi.yaml` | A curated 14-operation subset of the Sony Ci Media Cloud REST API |
| `sony-ci-openapi-SLOPPY.yaml` | The same spec with eight deliberate faults. Airia verifies it anyway |
| `sony-ci-openapi-FATAL.yaml` | Unparseable YAML — one of the few things that genuinely fails |
| `validate_openapi.py` | Pre-flight checker — blockers vs quality issues |
| `preview_tools.py` | Renders the exact tool list Airia will show, before you upload |

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

Findings are split into **blockers** (the converter cannot build a server) and **quality**
issues (it will happily build one, but the resulting tools are worse for it). Most real faults
are quality issues:

```bash
python3 validate_openapi.py sony-ci-openapi.yaml         # 0 blockers, 1 quality note
python3 validate_openapi.py sony-ci-openapi-SLOPPY.yaml  # 0 blockers, 12 quality issues
python3 validate_openapi.py sony-ci-openapi-FATAL.yaml   # does not parse, exit 1
```

The converter behind Airia's OpenAPI servers is deliberately permissive: it does not check the
spec version, does not require `operationId`, does not detect duplicates, does not cross-check
path parameters against the path template, and never reads `securitySchemes`. It also takes the
upstream base URL from Airia's form rather than the spec's `servers` block.

So a spec can be wrong by OpenAPI's rules and still verify and produce working tools. Passing
verification is a low bar. It is not a substitute for reading the generated tool list.

One consequence worth knowing: the tool **name** is generated from the HTTP method and path,
not from `operationId`. The `operationId`, `summary` and `description` are concatenated into the
tool **description**. Descriptions are therefore the field that determines whether an agent uses
the API well.

## Previewing the tool list

`preview_tools.py` reimplements the converter's tool generation, so it shows the names,
descriptions and arguments Airia will display, before you register anything:

```bash
python3 preview_tools.py sony-ci-openapi.yaml
```

Worth knowing: the tool name is built as `mcplink_<title>_<method>_<path>`, and the sanitizer
does **not** strip parentheses. A title like `Sony Ci Media Cloud (curated)` produces names
containing `(curated)` and pushes most of them past the 64-character limit many MCP clients
enforce. Keep `info.title` short and alphanumeric.

## Notes for registering a spec in Airia

- **Host the spec on GitHub.** Specs served from other hosts currently fail the spec test, and
  the save is gated on that test passing.
- **Keep specs small.** Multi-megabyte specs can fail to fetch. This one is 16 KB.
- **The authentication method is locked after creation.** Choose it deliberately the first time.
- Sony Ci expects `Authorization: Bearer <token>`, so register it with **API Key** auth. Ci
  issues tokens via the OAuth 2.0 password grant at `POST /oauth2/token`; tokens last 24 hours.
