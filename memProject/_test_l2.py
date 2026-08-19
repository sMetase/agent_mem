import json, urllib.request, sys

BASE = 'http://127.0.0.1:8000'
scene_id = 'scene_0a17f4ec'
api_key = 'mem_ced5c9d8bf9d95dbfee406237ded7855c0b855d4fe27cdb590605379dfa8266b'
uid = 'test_user_001'

def log(msg):
    print(msg, flush=True)

def call(method, path, body=None, headers=None):
    h = {'Content-Type': 'application/json'}
    if headers: h.update(headers)
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(BASE+path, data=data, headers=h, method=method)
    try:
        r = urllib.request.urlopen(req, timeout=90)
        return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())
    except Exception as e:
        return {"error": str(e)}

h = {'X-API-Key': api_key, 'X-User-Id': uid}

log('='*60)
log('测试⑤: 创建会话')
r = call('POST', '/api/v1/session', {'user_id': uid, 'scene_id': scene_id}, h)
log(json.dumps(r, ensure_ascii=False))
session_id = r.get('data', {}).get('session_id', '')

log('='*60)
log('测试⑥: 写入前先检索')
r = call('POST', '/api/v1/memory/search', {'query': '退货退款', 'user_id': uid, 'top_k': 5}, h)
log(json.dumps(r, ensure_ascii=False)[:300])

log('='*60)
log('测试⑦: 写入对话（dialogue）— 等待LLM...')
r = call('POST', '/api/v1/memory/write', {
    'user_id': uid, 'scene_id': scene_id, 'session_id': session_id,
    'interaction_type': 'dialogue',
    'messages': [
        {'role': 'user', 'content': '我买的衣服尺寸不合适想退货，订单号DH001'},
        {'role': 'assistant', 'content': '好的，我帮您提交退货申请，退款3个工作日内到账'}
    ]
}, h)
log(json.dumps(r, ensure_ascii=False))

log('session_id=' + session_id)
