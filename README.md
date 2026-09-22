# SwaggerDocs-Test

OpenAPI specifications hosted for use as **Airia custom MCP servers** (OpenAPI Spec / SpecLink).

Airia's MCP Gateway turns a hosted OpenAPI spec into a live MCP server: it fetches the YAML,
parses it, and presents each operation as a tool an agent can call. You publish a static
document; Airia runs the server.

## The three specs

These accompany a recorded walkthrough of spec registration.

| File | Demonstrates | Expected result |
|---|---|---|
| `video/sony-ci.yaml` | A correct spec whose tools are legitimate, except one carrying injected instructions | Verifies · 7 tools · prompt-injection finding on `addAssetMetadata` |
| `video/sony-ci-malformed.yaml` | A spec that genuinely cannot be parsed | Fails at the parse stage |

### Registration values

```
Spec URL   https://raw.githubusercontent.com/AndersAiria/SwaggerDocs-Test/main/video/sony-ci.yaml
           https://raw.githubusercontent.com/AndersAiria/SwaggerDocs-Test/main/video/sony-ci-malformed.yaml

Base URL   https://api.cimediacloud.com
```

## About the API

Sony Ci Media Cloud publishes REST documentation at https://developers.cimediacloud.com/ but
ships no OpenAPI file, so these specs were authored from that documentation. Every path was
verified against the live docs on 2026-09-22.

The published API exposes roughly 80 operations. `sony-ci.yaml` exposes seven: six read
operations and one write. Operations absent from a spec cannot be called by an agent and no
prompt can reintroduce them: the spec is the tool surface.

> These specs are authored, not official. They are not published or endorsed by Sony. Re-verify
> against your own contracted Ci version before any production use.

## Notes for authoring specs

- **Host the spec on GitHub.** Specs served from other hosts currently fail the spec test, and
  the save is gated on that test passing.
- **Keep specs small.** Multi-megabyte specs can fail to fetch.
- **Set `operationId` on every operation.** The tool name is the spec's tool prefix plus the
  `operationId`; without one it falls back to the method and path, which reads poorly. Two
  operations sharing an `operationId` produce two tools with the same name.
- **Keep `info.title` short.** It becomes the tool-name prefix, and generated names must match
  `^[a-zA-Z0-9_-]{1,64}$`. A long title plus a descriptive `operationId` runs past the limit.
  `x-mcp-tool-prefix` overrides the prefix when the title needs to stay long.
- **Descriptions are what the model reasons over.** They carry more weight than any other field
  in deciding whether a tool gets used correctly.
- **The authentication method is locked at creation.** Choose it deliberately the first time.
- Sony Ci expects `Authorization: Bearer <token>`, so register it with **API Key** auth. Ci
  issues tokens via the OAuth 2.0 password grant at `POST /oauth2/token`; tokens last 24 hours.

## Note on `video/sony-ci.yaml`

The `addAssetMetadata` operation carries a deliberate tool-poisoning sample in its description,
so a security scan has something real to detect. It is a demo artifact and is labelled as such
inside the file. The endpoint itself is an ordinary write; the risk lives in the text the model
reads, which is why descriptions are scanned and not just HTTP verbs.
