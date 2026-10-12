import json
from fastapi.routing import APIRoute
from app.main import app
def walk(dep, acc):
    for d in dep.dependencies:
        c=d.call; n=getattr(c,'__qualname__',str(c)); roles=None
        for cell in (getattr(c,'__closure__',None) or ()):
            v=cell.cell_contents
            if isinstance(v,tuple) and v and all(hasattr(x,'value') for x in v):
                roles=sorted(x.value for x in v)
        acc.append((n,roles)); walk(d,acc)
rows=[]
for r in app.routes:
    if isinstance(r,APIRoute):
        acc=[]; walk(r.dependant,acc)
        roles=next((a[1] for a in acc if a[1]),None)
        if roles: auth='ROLES:'+'|'.join(roles)
        elif any('get_current_user' in a[0] for a in acc): auth='ANY_AUTHENTICATED'
        else: auth='PUBLIC'
        for m in sorted(r.methods-{'HEAD','OPTIONS'}): rows.append((r.path,m,auth,r.name))
    else:
        rows.append((getattr(r,'path','?'),type(r).__name__,'(mount/ws)',getattr(r,'name','')))
rows.sort(); json.dump(rows,open('docs/week-1/tools/routes.json','w'))
from collections import Counter
print(len(rows),'entries',dict(Counter(r[2] for r in rows)))
for r in rows:
    if r[2] in('PUBLIC','(mount/ws)'): print(r)
