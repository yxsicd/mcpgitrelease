#!/usr/bin/env python3
from __future__ import annotations
import json, pathlib, sys

ROOT=pathlib.Path(__file__).resolve().parents[1]

REQ={"id","name","kind","description","disclosure","lifecycle","authority"}

def parse_frontmatter(path:pathlib.Path):
    text=path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise SystemExit(f"{path}: missing YAML frontmatter")
    head=text.split("\n---\n",1)[0][4:]
    out={}
    current=None
    for raw in head.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"): continue
        if raw.startswith("  ") and current:
            k,v=raw.strip().split(":",1)
            out[current][k.strip()]=v.strip().strip('"')
            continue
        if ":" not in raw: continue
        k,v=raw.split(":",1); k=k.strip(); v=v.strip()
        if not v:
            out[k]={}; current=k
        else:
            out[k]=v.strip('"'); current=None
    missing=REQ-set(out)
    if missing: raise SystemExit(f"{path}: missing {sorted(missing)}")
    return out

def local_ref(base:pathlib.Path, value:str):
    if value.startswith(("http://","https://","mcpgit://")): return None
    return (base/value).resolve()

generated={ROOT/'metadata/skills.json', ROOT/'web-components/catalog.json'}
skills=[]
for path in sorted(ROOT.rglob("SKILL.md")):
    if ".git" in path.parts: continue
    # Repository-local maintainer Skills are deliberately outside the public
    # consumer discovery index. Validate them separately below.
    if ".agents" in path.parts: continue
    meta=parse_frontmatter(path)
    rel=path.relative_to(ROOT).as_posix()
    for _,value in (meta.get("metadata") or {}).items():
        target=local_ref(path.parent,value)
        if target and not target.exists() and target not in generated:
            raise SystemExit(f"{rel}: metadata target missing: {value}")
    skills.append({"path":rel,**meta})

ids=[s["id"] for s in skills]
if len(ids)!=len(set(ids)): raise SystemExit("duplicate Skill ids")

maintainer_skills=[]
maintainer_root=ROOT/".agents"
if maintainer_root.exists():
    for path in sorted(maintainer_root.rglob("SKILL.md")):
        meta=parse_frontmatter(path)
        rel=path.relative_to(ROOT).as_posix()
        for _,value in (meta.get("metadata") or {}).items():
            target=local_ref(path.parent,value)
            if target and not target.exists() and target not in generated:
                raise SystemExit(f"{rel}: metadata target missing: {value}")
        maintainer_skills.append({"path":rel,**meta})
    maintainer_ids=[s["id"] for s in maintainer_skills]
    if len(maintainer_ids)!=len(set(maintainer_ids)):
        raise SystemExit("duplicate maintainer Skill ids")
    overlap=set(ids)&set(maintainer_ids)
    if overlap:
        raise SystemExit(f"public/maintainer Skill id collision: {sorted(overlap)}")

channel_path=ROOT/"web-components/channels/stable.json"
channel=json.loads(channel_path.read_text())
registry_path=(channel_path.parent/channel["registry"]).resolve()
if ROOT.resolve() not in registry_path.parents:
    raise SystemExit("stable registry escaped repository root")
registry=json.loads(registry_path.read_text())
components=registry["components"]
catalog=[]
for cid,item in sorted(components.items()):
    skill_path=ROOT/"web-components"/cid/"SKILL.md"
    if not skill_path.exists(): raise SystemExit(f"registry component lacks SKILL.md: {cid}")
    skill=parse_frontmatter(skill_path)
    if skill["id"]!=f"web-component:{cid}": raise SystemExit(f"component Skill id mismatch: {cid}")
    manifest=local_ref(skill_path.parent,skill["metadata"]["manifest"])
    if not manifest or not manifest.exists(): raise SystemExit(f"component manifest missing: {cid}")
    m=json.loads(manifest.read_text())
    if m["id"]!=cid or m["version"]!=item["version"] or str(m["api"])!=str(item["api"]):
        raise SystemExit(f"component registry/manifest mismatch: {cid}")

    # Agent-visible Skill documentation must not lag the machine contract.
    skill_text=skill_path.read_text(encoding="utf-8")
    contract=m.get("contract") or {}
    required_tokens=[]
    entry=contract.get("entry")
    if entry:
        required_tokens.append(str(entry).split("(",1)[0])
    for method in contract.get("methods") or []:
        required_tokens.append(str(method).split("(",1)[0])
    for event in contract.get("events") or []:
        required_tokens.append(str(event))
    for attr in (contract.get("attributes") or {}).keys():
        required_tokens.append(str(attr))
    state_schema=(m.get("state") or {}).get("schema")
    if state_schema:
        required_tokens.append(str(state_schema))
    missing_tokens=sorted({token for token in required_tokens if token and token not in skill_text})
    if missing_tokens:
        raise SystemExit(f"component Skill contract coverage missing for {cid}: {missing_tokens}")
    catalog.append({
      "id":cid,"skill":skill_path.relative_to(ROOT).as_posix(),
      "version":item["version"],"api":item["api"],"channel":skill.get("channel"),
      "manifest":manifest.relative_to(ROOT).as_posix(),"entry":item["entry"],"integrity":item["integrity"]
    })

skill_index={"schema":"mcpgitrelease/skill-index/v1","skills":skills}
component_catalog={"schema":"mcpgitrelease/web-components-catalog/v1","registry":registry_path.relative_to(ROOT).as_posix(),"components":catalog}
out1=ROOT/"metadata/skills.json"; out1.parent.mkdir(parents=True,exist_ok=True)
out2=ROOT/"web-components/catalog.json"
render=lambda x: json.dumps(x,indent=2,ensure_ascii=False,sort_keys=False)+"\n"

if "--check" in sys.argv:
    for path,value in [(out1,skill_index),(out2,component_catalog)]:
        if not path.exists() or path.read_text()!=render(value):
            raise SystemExit(f"generated metadata stale: {path.relative_to(ROOT)}")
    print(f"PASS skill index: {len(skills)} public Skills, {len(maintainer_skills)} maintainer Skills, {len(catalog)} Web Components")
else:
    out1.write_text(render(skill_index),encoding="utf-8")
    out2.write_text(render(component_catalog),encoding="utf-8")
    print(f"WROTE {out1.relative_to(ROOT)} {out2.relative_to(ROOT)}; validated {len(maintainer_skills)} maintainer Skills")
