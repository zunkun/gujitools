import json, sys
from collections import Counter

d = json.load(open('.pyright_out.json', encoding='utf-8'))
diag = d['generalDiagnostics']

mode = sys.argv[1] if len(sys.argv) > 1 else 'files'
if mode == 'files':
    files = Counter(x['file'].replace('\\', '/') for x in diag)
    for f, n in files.most_common(40):
        print(n, f.split('gujitools/')[-1])
elif mode == 'rules':
    rules = Counter((x['rule'] or 'none') for x in diag)
    for k, v in rules.most_common():
        print(v, k)
elif mode == 'sample':
    rule = sys.argv[2]
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else 15
    shown = 0
    for x in diag:
        if x.get('rule') == rule:
            print(x['file'].replace('\\', '/').split('gujitools/')[-1], x['range']['start']['line'] + 1, x['message'][:200])
            shown += 1
            if shown >= limit:
                break
elif mode == 'all':
    for x in diag:
        print(x['file'].replace('\\', '/').split('gujitools/')[-1], x['range']['start']['line'] + 1, x['rule'], x['message'][:300])
