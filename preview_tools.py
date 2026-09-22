#!/usr/bin/env python3
"""
Render the tool list Airia will show for an OpenAPI spec, before you upload it.

This reimplements mcp-link's tool generation exactly as its source does it
(utils/adapter.go, sanitizeToolName + the name/description construction), so what you
see here is what Airia's "N tools discovered" preview and endpoint list will show.

    python3 preview_tools.py sony-ci-openapi.yaml

Read the output the way a reviewer reads the Airia screen: is the count what you
expected, does every tool have a real description, and does each one expose the
arguments it needs?
"""
import sys, re, yaml

MCP_NAME_LIMIT = 64   # most MCP clients reject tool names longer than this


def sanitize(name: str) -> str:
    s = name.lower()
    for a, b in ((" ", "_"), ("-", "_"), ("/", "_"), (".", "_"), ("{", ""), ("}", ""),
                 (":", "_"), ("?", ""), ("&", "and"), ("=", "_eq_"), ("%", "_pct_")):
        s = s.replace(a, b)
    while "__" in s:
        s = s.replace("__", "_")
    s = s.strip("_")
    return s or "unnamed_tool"


def main(path):
    spec = yaml.safe_load(open(path, encoding="utf-8"))
    title = (spec.get("info") or {}).get("title", "")
    prefix = "mcplink_" + sanitize(title)
    paths = spec.get("paths") or {}
    METHODS = ("get", "post", "put", "delete", "patch", "head", "options")

    tools, seen = [], {}
    for p, item in paths.items():
        if not isinstance(item, dict):
            continue
        declared_path_params = set()
        for m, op in item.items():
            if m not in METHODS or not isinstance(op, dict):
                continue
            name = sanitize(f"{prefix}_{m}_{p}")
            desc = " ".join(x for x in (op.get("operationId", ""),
                                        op.get("summary", ""),
                                        op.get("description", "")) if x).strip()
            args = []
            for prm in (item.get("parameters", []) or []) + (op.get("parameters", []) or []):
                if isinstance(prm, dict) and prm.get("name") and prm.get("in") in ("path", "query"):
                    args.append((prm["name"], prm["in"], bool(prm.get("required"))))
            if op.get("requestBody"):
                args.append(("<body>", "body", True))
            needed = set(re.findall(r"{([^}]+)}", p))
            supplied = {a for a, kind, _ in args if kind == "path"}
            tools.append({
                "name": name, "desc": " ".join(desc.split()), "args": args,
                "route": f"{m.upper()} {p}", "missing": needed - supplied,
            })
            seen.setdefault(name, []).append(f"{m.upper()} {p}")

    print(f"\nSpec:   {path}")
    print(f"Title:  {title!r}")
    print(f"Prefix: {prefix}")
    print(f"\n  *** Airia will report: {len(tools)} tools discovered ***\n")
    print("=" * 78)

    for t in sorted(tools, key=lambda x: x["name"]):
        over = len(t["name"]) - MCP_NAME_LIMIT
        print(f"\n{t['name']}")
        print(f"    route       {t['route']}")
        print(f"    name length {len(t['name'])}" + (f"  <-- {over} OVER the {MCP_NAME_LIMIT}-char limit" if over > 0 else ""))
        if t["desc"]:
            d = t["desc"]
            print(f"    description {d[:150]}{'...' if len(d) > 150 else ''}")
        else:
            print(f"    description (EMPTY - the model gets nothing to decide on)")
        if t["args"]:
            print(f"    arguments   " + ", ".join(
                f"{a}[{k}{'*' if r else ''}]" for a, k, r in t["args"]))
        else:
            print(f"    arguments   (none)")
        if t["missing"]:
            print(f"    !! the URL needs {{{', '.join(sorted(t['missing']))}}} but the tool never "
                  f"asks for {'it' if len(t['missing'])==1 else 'them'}.")
            print(f"       every call ships a literal placeholder and fails at runtime.")

    print("\n" + "=" * 78)
    blank = [t for t in tools if not t["desc"]]
    broken = [t for t in tools if t["missing"]]
    longn = [t for t in tools if len(t["name"]) > MCP_NAME_LIMIT]
    dupes = {n: r for n, r in seen.items() if len(r) > 1}

    print(f"\nWhat a reviewer should notice on the Airia screen:\n")
    print(f"  tools discovered ........... {len(tools)}")
    print(f"  with no description ........ {len(blank)}" + ("   <-- unusable by the model" if blank else ""))
    print(f"  missing a path argument .... {len(broken)}" + ("   <-- will fail at runtime" if broken else ""))
    print(f"  name over {MCP_NAME_LIMIT} chars ......... {len(longn)}" + ("   <-- some clients will reject these" if longn else ""))
    print(f"  colliding tool names ....... {len(dupes)}")
    for n, r in dupes.items():
        print(f"      {n}  <-  {', '.join(r)}")
    print()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python3 preview_tools.py <spec.yaml>")
    main(sys.argv[1])
