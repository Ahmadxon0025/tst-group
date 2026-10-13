# Rebuilds crm.html from crm_template.html + suppliers.json
import json
d=json.load(open('suppliers.json',encoding='utf-8'))
t=open('crm_template.html',encoding='utf-8').read()
open('crm.html','w',encoding='utf-8').write(t.replace('__DATA__',json.dumps(d,ensure_ascii=False).replace('</','<\\/')))
print('crm.html built,',len(d),'suppliers')
