import json
d = json.load(open("streams.json", encoding="utf-8"))
for g in d["groups"]:
    print(f'[{g["name"]}] - {len(g["channels"])} tran')
    for c in g["channels"]:
        print(f'  - {c["name"]}')
