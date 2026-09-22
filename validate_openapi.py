#!/usr/bin/env python3
"""
Quality checker for an OpenAPI YAML destined to become an Airia custom MCP server.

IMPORTANT - what this tool is and is not.

Airia's OpenAPI servers are built by mcp-link, which is extremely permissive. Verified
against its source on 2026-09-22: it does not check the openapi version, does not require
operationId, does not detect duplicate operationIds, does not cross-check path parameters,
and never reads securitySchemes. It also takes the upstream base URL from Airia's form
rather than the spec's servers block. A spec can therefore be badly wrong by OpenAPI's
rules and still verify in Airia and produce working tools.

So the findings below are split:

  BLOCKER  - mcp-link cannot build a server from this. Airia's probe fails.
  QUALITY  - Airia will accept this happily. The resulting tools are worse for it,
             which an agent pays for at runtime and a reviewer pays for at review time.

Most real faults are QUALITY. That is the uncomfortable and useful finding: passing
Airia's verification is a low bar, and it is not a substitute for reading the tool list.

    python3 validate_openapi.py sony-ci-openapi.yaml

Exit code 0 = valid, safe to hand off.  Exit code 1 = errors, fix before handing off.
Requires only PyYAML:  pip install pyyaml
"""
import sys, re, json

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required:  pip install pyyaml")

BLOCKERS, QUALITY, NOTES = [], [], []
ERRORS, WARNINGS = BLOCKERS, QUALITY   # back-compat aliases
DESTRUCTIVE_HINTS = ("delete", "purge", "remove", "destroy", "trash", "archive", "wipe")
EGRESS_HINTS = ("download", "export", "share", "publish")

def err(m):  BLOCKERS.append(m)
def warn(m): QUALITY.append(m)
def note(m): NOTES.append(m)


def collect_refs(node, acc):
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "$ref" and isinstance(v, str):
                acc.append(v)
            else:
                collect_refs(v, acc)
    elif isinstance(node, list):
        for v in node:
            collect_refs(v, acc)


def resolve(spec, ref):
    if not ref.startswith("#/"):
        return True  # external ref, not our problem to resolve here
    node = spec
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or part not in node:
            return False
        node = node[part]
    return True


def main(path):
    raw = open(path, encoding="utf-8").read()

    # 1. Does it parse at all?
    try:
        spec = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        print(f"FAIL  YAML does not parse: {e}")
        return 1
    if not isinstance(spec, dict):
        print("FAIL  Top level of the document is not a mapping.")
        return 1

    # 2. OpenAPI version
    ver = str(spec.get("openapi", ""))
    if not ver:
        warn("No 'openapi:' version key. mcp-link never reads it, so this does not block "
             "anything, but it signals the document was not written to a version.")
    elif not ver.startswith("3."):
        warn(f"openapi version is '{ver}', not 3.x. mcp-link does not check the version "
             f"field, so this still deploys - but a 2.0-shaped document will have other "
             f"structural differences that do bite.")

    # 3. info
    info = spec.get("info") or {}
    if not info.get("title"):
        err("info.title is missing. It becomes the MCP server's display name.")
    if not info.get("version"):
        warn("info.version is missing.")

    # 4. servers - the single most common cause of a spec that parses but cannot call anything
    servers = spec.get("servers") or []
    if not servers:
        warn("No 'servers:' block. Airia takes the upstream base URL from its own form "
             "field, so this does NOT block deployment - but nothing in the file records "
             "which API it describes.")
    else:
        for s in servers:
            u = (s or {}).get("url", "")
            if not u.startswith(("http://", "https://")):
                err(f"servers.url '{u}' is not an absolute URL.")
            elif u.startswith("http://"):
                warn(f"servers.url '{u}' is plain HTTP, not HTTPS.")

    # 5. paths and operations
    paths = spec.get("paths")
    if not isinstance(paths, dict) or not paths:
        err("No usable 'paths:' mapping - mcp-link returns zero endpoints, so the server "
            "deploys with no tools at all.")
        paths = {}

    METHODS = ("get", "post", "put", "delete", "patch", "head", "options")
    seen_ids, ops = {}, []

    for p, item in paths.items():
        if not isinstance(item, dict):
            err(f"Path '{p}' is not a mapping.")
            continue
        path_params = set(re.findall(r"{([^}]+)}", p))
        shared = item.get("parameters", []) or []

        for m, op in item.items():
            if m not in METHODS:
                continue
            if not isinstance(op, dict):
                err(f"{m.upper()} {p} is not a mapping.")
                continue
            ops.append((m, p, op))
            label = f"{m.upper()} {p}"

            # operationId -> becomes the MCP tool name
            oid = op.get("operationId")
            if not oid:
                warn(f"{label} has no operationId. mcp-link builds the tool NAME from the "
                     f"method and path regardless, so this deploys - but operationId is "
                     f"prepended to the tool description, so the model loses a useful hint.")
            else:
                if oid in seen_ids:
                    warn(f"Duplicate operationId '{oid}' on {label} and {seen_ids[oid]}. "
                         f"Tool names come from method+path so they will not collide, but "
                         f"two tools now carry the same hint in their descriptions.")
                seen_ids[oid] = label
                if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", oid):
                    warn(f"operationId '{oid}' on {label} is oddly formed. It lands in the "
                         f"tool description rather than the name, so this is cosmetic.")

            # description -> becomes the tool description the model reads when choosing
            desc = (op.get("description") or "").strip()
            summ = (op.get("summary") or "").strip()
            if not desc and not summ:
                warn(f"{label} has neither summary nor description. This is the single most "
                     f"damaging quality fault: mcp-link concatenates operationId, summary and "
                     f"description into the tool description, so the model gets almost nothing "
                     f"to decide on and will misuse or ignore the tool.")
            elif not desc:
                warn(f"{label} has a summary but no description. Descriptions are what the "
                     f"model actually reasons over.")
            elif len(desc) < 25:
                warn(f"{label} description is very short ({len(desc)} chars).")

            # parameters declared vs used in the path template
            declared = set()
            for prm in shared + (op.get("parameters", []) or []):
                if isinstance(prm, dict):
                    if "$ref" in prm:
                        declared.add("<ref>")
                    elif prm.get("in") == "path":
                        declared.add(prm.get("name"))
                        if not prm.get("required"):
                            warn(f"{label} path parameter '{prm.get('name')}' is not marked "
                                 f"required: true.")
                    if prm.get("in") and not prm.get("schema") and "$ref" not in prm:
                        warn(f"{label} parameter '{prm.get('name')}' has no schema.")
            missing = path_params - declared
            if missing and "<ref>" not in declared:
                warn(f"{label} uses {{{', '.join(sorted(missing))}}} in the path but does not "
                     f"declare {'it' if len(missing)==1 else 'them'} as a parameter. The tool "
                     f"deploys, but the agent is never given the argument, so every call to it "
                     f"hits a literal {{placeholder}} in the URL and fails at runtime.")

            # bodies on mutating verbs
            if m in ("post", "put", "patch") and not op.get("requestBody"):
                warn(f"{label} is a {m.upper()} with no requestBody.")

            if not op.get("responses"):
                warn(f"{label} declares no responses.")

    # 6. every $ref resolves
    refs = []
    collect_refs(spec, refs)
    for r in sorted(set(refs)):
        if not resolve(spec, r):
            warn(f"Unresolvable $ref: '{r}'. mcp-link resolves refs non-recursively, so a "
                 f"dangling ref nested inside a response usually passes unnoticed; one at the "
                 f"top level can fail the parse.")

    # 7. security
    schemes = ((spec.get("components") or {}).get("securitySchemes") or {})
    used = set()
    for entry in (spec.get("security") or []):
        used.update(entry.keys())
    for _, _, op in ops:
        for entry in (op.get("security") or []):
            used.update(entry.keys())
    if not schemes:
        warn("No components.securitySchemes. If the API needs auth, declare it so Airia "
             "knows which credential to attach.")
    for u in used - set(schemes):
        warn(f"security references scheme '{u}' which is not defined in "
             f"components.securitySchemes. mcp-link never reads either field - Airia supplies "
             f"auth from the credential you attach - so this is documentation only.")
    for s in set(schemes) - used:
        warn(f"securityScheme '{s}' is defined but never applied.")

    # 8. risk surface - what security is going to be asked to sign off
    destructive, egress = [], []
    for m, p, op in ops:
        # Classify on the operationId and summary only. Descriptions routinely contain
        # negated mentions ("does not delete...") that would produce false positives.
        text = f"{op.get('operationId','')} {op.get('summary','')}".lower()
        if m == "delete" or any(h in text for h in DESTRUCTIVE_HINTS):
            destructive.append(f"{m.upper()} {p}  ({op.get('operationId','?')})")
        elif any(h in text for h in EGRESS_HINTS):
            egress.append(f"{m.upper()} {p}  ({op.get('operationId','?')})")

    # ------------------------------------------------------------------ report
    print(f"\nSpec:       {path}")
    print(f"Title:      {info.get('title','(none)')}  v{info.get('version','?')}")
    print(f"Base URL:   {servers[0]['url'] if servers else '(none in spec - Airia supplies it)'}")
    print(f"Operations: {len(ops)}  ->  {len(ops)} MCP tools\n")

    for b in BLOCKERS:
        print(f"  [x] BLOCKER: {b}")
    for q in QUALITY:
        print(f"  [!] QUALITY: {q}")
    if not BLOCKERS and not QUALITY:
        print("  Nothing to report.")

    if destructive or egress:
        print("\n  For the security review:")
        for d in destructive:
            print(f"    DESTRUCTIVE   {d}")
        for e in egress:
            print(f"    DATA EGRESS   {e}")

    print()
    if BLOCKERS:
        print(f"RESULT: WILL NOT DEPLOY - {len(BLOCKERS)} blocker(s), "
              f"{len(QUALITY)} quality issue(s).")
        return 1
    if QUALITY:
        print(f"RESULT: DEPLOYS, BUT LOW QUALITY - 0 blockers, {len(QUALITY)} quality issue(s).")
        print("Airia will verify this spec and build tools from it. That is not the same as")
        print("the tools being good. Fix the quality issues, then hand it to the reviewer.")
        return 0
    print("RESULT: CLEAN - 0 blockers, 0 quality issues.")
    print("Safe to register, and ready for the permit/deny review.\n")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python3 validate_openapi.py <spec.yaml>")
    sys.exit(main(sys.argv[1]))
