import json, urllib.request, urllib.error, re
BASE = 'http://120.27.207.238:8000'
uid = 'remote_test_user'

def log(msg): print(msg, flush=True)

def call(method, path, body=None, headers=None):
    h = {'Content-Type': 'application/json'}
    if headers: h.update(headers)
    req = urllib.request.Request(BASE+path, data=json.dumps(body).encode() if body else None, headers=h, method=method)
    try:
        r = urllib.request.urlopen(req, timeout=90)
        return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try: return json.loads(e.read())
        except: return {'http_error': e.code}
    except Exception as e: return {'error': str(e)}

def cn_count(s):
    return len(re.findall(r'[一-鿿]', s or ''))

log('='*60)
log('1) 健康检查 + 接入')
log('='*60)
r = call('GET', '/health'); log('[health] ' + str(r.get('status')))
r = call('GET', '/api/v1/health'); log('[db] ' + str(r.get('database')))
r = call('POST', '/api/v1/scene', {'scene_name':'远程测试场景','description':'连通性+中文验证'}); scene = r.get('data',{}).get('scene_id',''); log('[创建场景] ' + scene)
r = call('POST', '/api/v1/agent/register', {'agent_name':'远程测试助手','scene_id':scene,'permissions':['read','write']})
agent = r.get('data',{}).get('agent_id',''); key = r.get('data',{}).get('api_key',''); log('[注册智能体] ' + agent)
h = {'X-API-Key':key,'X-User-Id':uid,'X-Agent-Id':agent}
r = call('POST', '/api/v1/session', {'user_id':uid,'scene_id':scene}, h); sess = r.get('data',{}).get('session_id',''); log('[创建会话] ' + sess)

log('')
log('='*60)
log('2) 去重类型 + 中文输出验证')
log('='*60)
def wr(label, itype, msgs, **kw):
    body = {'user_id':uid,'scene_id':scene,'session_id':sess,'interaction_type':itype,'messages':msgs}; body.update(kw)
    r = call('POST','/api/v1/memory/write', body, h)
    for x in r.get('data',{}).get('results',[]):
        mem = x.get('memory','')
        log(f'{label} -> event={x.get("event")} 中文数={cn_count(mem)} 内容={mem[:50]}')

wr('[新增]','dialogue',[{'role':'user','content':'我买的衣服尺寸不合适想退货，订单号DH001'},{'role':'assistant','content':'好的，帮您提交退货申请，退款3个工作日内到账'}])
wr('[合并]','dialogue',[{'role':'user','content':'我之前还打电话咨询过退款流程'}])
wr('[覆盖]','dialogue',[{'role':'user','content':'之前说退款3个工作日是错的，实际是7个工作日'}])
wr('[丢弃]','dialogue',[{'role':'user','content':'我买的衣服尺寸不合适想退货，订单号DH001'}])

log('')
log('='*60)
log('3) 检索 + 上下文')
log('='*60)
r = call('POST','/api/v1/memory/search', {'query':'退款','user_id':uid,'top_k':5}, h)
log('[检索 退款] total=' + str(r.get('data',{}).get('total_candidates')))
r = call('POST','/api/v1/memory/context', {'query':'退款进度','user_id':uid,'max_tokens':2000}, h)
log('[上下文] memory_count=' + str(r.get('data',{}).get('memory_count')))

log('')
log('='*60)
log('4) 任务管理 + 会话关闭')
log('='*60)
r = call('POST','/api/v1/task', {'user_id':uid,'title':'处理DH001退款','goal':'完成退款全流程','scene_id':scene}, h)
tid = r.get('data',{}).get('task_id',''); log('[创建任务] ' + tid)
if tid:
    call('PUT', f'/api/v1/task/{tid}', {'status':'in_progress','progress':'已提交退货申请'}, h)
    call('POST', f'/api/v1/task/{tid}/complete', headers=h)
    log('[任务完成] done')
r = call('POST', f'/api/v1/session/{sess}/close', headers=h)
log('[关闭会话] total=' + str(r.get('data',{}).get('total_memory_count')) + ' compressed=' + str(r.get('data',{}).get('compressed_count')))

log('')
log('scene=' + scene)
log('agent=' + agent)
log('sess=' + sess)
log('api_key=' + key)
