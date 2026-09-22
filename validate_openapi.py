#!/usr/bin/env python3
"""
Pre-flight validator for an OpenAPI YAML destined to become an Airia custom MCP server.

Run this BEFORE handing the spec to the security team. It catches the class of problem
that otherwise only surfaces when security uploads the file and it fails to deploy.

    python3 validate_openapi.py sony-ci-openapi.yaml

Exit code 0 = valid, safe to hand off.  Exit code 1 = errors, fix before handing off.
Requires only PyYAML:  pip install pyyaml
"""
import sys, re, json

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required:  pip install pyyaml")

ERRORS, WARNINGS, NOTES = [], [], []
DESTRUCTIVE_HINTS = ("delete", "purge", "remove", "destroy", "trash", "archive", "wipe")
EGRESS_HINTS = ("download", "export", "share", "publish")

def err(m):  ERRORS.append(m)
def warn(m): WARNINGS.append(m)
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
        err("No 'openapi:' version key. Airia expects an OpenAPI v3 document, not Swagger 2.")
    elif not ver.startswith("3."):
        err(f"openapi version is '{ver}'. Airia's spec-to-MCP adapter expects 3.x.")

    # 3. info
    info = spec.get("info") or {}
    if not info.get("title"):
        err("info.title is missing. It becomes the MCP server's display name.")
    if not info.get("version"):
        warn("info.version is missing.")

    # 4. servers - the single most common cause of a spec that parses but cannot call anything
    servers = spec.get("servers") or []
    if not servers:
        err("No 'servers:' block. Without an absolute base URL the generated tools have "
            "nowhere to send requests.")
    else:
        for s in servers:
            u = (s or {}).get("url", "")
            if not u.startswith(("http://", "https://")):
                err(f"servers.url '{u}' is not an absolute URL.")
            elif u.startswith("http://"):
                warn(f"servers.url '{u}' is plain HTTP, not HTTPS.")

    # 5. paths and operations
    paths = spec.get("paths") or {}
    if not paths:
        err("No 'paths:' - the document describes zero operations.")

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
                err(f"{label} has no operationId. Airia names the MCP tool from it; "
                    f"without one the tool is unnamed or auto-generated.")
            else:
                if oid in seen_ids:
                    err(f"Duplicate operationId '{oid}' on {label} and {seen_ids[oid]}. "
                        f"Two MCP tools cannot share a name.")
                seen_ids[oid] = label
                if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", oid):
                    err(f"operationId '{oid}' on {label} is not a usable tool name "
                        f"(letters/digits/underscore/hyphen, must start with a letter, max 64).")

            # description -> becomes the tool description the model reads when choosing
            desc = (op.get("description") or "").strip()
            summ = (op.get("summary") or "").strip()
            if not desc and not summ:
                err(f"{label} has neither summary nor description. The model has nothing "
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
                            err(f"{label} path parameter '{prm.get('name')}' must be "
                                f"required: true.")
                    if prm.get("in") and not prm.get("schema") and "$ref" not in prm:
                        warn(f"{label} parameter '{prm.get('name')}' has no schema.")
            missing = path_params - declared
            if missing and "<ref>" not in declared:
                err(f"{label} uses {{{', '.join(sorted(missing))}}} in the path but does not "
                    f"declare {'it' if len(missing)==1 else 'them'} as a parameter.")

            # bodies on mutating verbs
            if m in ("post", "put", "patch") and not op.get("requestBody"):
                warn(f"{label} is a {m.upper()} with no requestBody.")

            if not op.get("responses"):
                err(f"{label} declares no responses.")

    # 6. every $ref resolves
    refs = []
    collect_refs(spec, refs)
    for r in sorted(set(refs)):
        if not resolve(spec, r):
            err(f"Unresolvable $ref: '{r}'.")

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
        err(f"security references scheme '{u}' which is not defined in "
            f"components.securitySchemes.")
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
    print(f"Base URL:   {servers[0]['url'] if servers else '(none)'}")
    print(f"Operations: {len(ops)}  ->  {len(ops)} MCP tools\n")

    for tag, items, sym in (("ERROR", ERRORS, "x"), ("WARN", WARNINGS, "!")):
        for i in items:
            print(f"  [{sym}] {tag}: {i}")
    if not ERRORS and not WARNINGS:
        print("  No errors, no warnings.")

    if destructive or egress:
        print("\n  For the security review:")
        for d in destructive:
            print(f"    DESTRUCTIVE   {d}")
        for e in egress:
            print(f"    DATA EGRESS   {e}")

    print()
    if ERRORS:
        print(f"RESULT: INVALID - {len(ERRORS)} error(s), {len(WARNINGS)} warning(s).")
        print("Fix the errors before handing this spec to the security team.\n")
        return 1
    print(f"RESULT: VALID - 0 errors, {len(WARNINGS)} warning(s).")
    print("Safe to hand to the security team for the permit/deny review.\n")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python3 validate_openapi.py <spec.yaml>")
    sys.exit(main(sys.argv[1]))
