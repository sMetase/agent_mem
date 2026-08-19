import json, urllib.request, urllib.error

BASE = 'http://127.0.0.1:8000'

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

ctx = {}
uid = 'test_user_001'

log('='*70)
log('Step 0 — 接入：场景 / 智能体 / 会话')
log('='*70)

r = call('POST', '/api/v1/scene', {'scene_name': '客服场景', 'description': '处理咨询退款'})
ctx['scene_id'] = r['data']['scene_id']
log('[0.1] 创建场景 → scene_id=' + ctx['scene_id'])

r = call('POST', '/api/v1/agent/register', {'agent_name': '客服助手', 'scene_id': ctx['scene_id'], 'permissions': ['read','write']})
ctx['agent_id'] = r['data']['agent_id']
ctx['api_key'] = r['data']['api_key']
log('[0.2] 注册智能体 → agent_id=' + ctx['agent_id'])

h = {'X-API-Key': ctx['api_key'], 'X-User-Id': uid, 'X-Agent-Id': ctx['agent_id']}
r = call('POST', '/api/v1/session', {'user_id': uid, 'scene_id': ctx['scene_id']}, h)
ctx['session_id'] = r['data']['session_id']
log('[0.3] 创建会话 → session_id=' + ctx['session_id'])

log('')
log('='*70)
log('Step 1 — 对话写入(dialogue) → 新增 keep_new')
log('='*70)
log('目的：写入一个全新事实，预期事件 ADD')
r = call('POST', '/api/v1/memory/write', {
    'user_id': uid, 'scene_id': ctx['scene_id'], 'session_id': ctx['session_id'],
    'interaction_type': 'dialogue',
    'messages': [
        {'role': 'user', 'content': '我买的衣服尺寸不合适想退货，订单号DH001'},
        {'role': 'assistant', 'content': '好的，帮您提交退货申请，退款3个工作日内到账'}
    ]
}, h)
log('[1] 响应: ' + json.dumps(r, ensure_ascii=False))

log('')
log('='*70)
log('Step 2 — 对话写入(dialogue) → 合并 merge')
log('='*70)
log('目的：对同一订单补充细节，预期事件 MERGE')
r = call('POST', '/api/v1/memory/write', {
    'user_id': uid, 'scene_id': ctx['scene_id'], 'session_id': ctx['session_id'],
    'interaction_type': 'dialogue',
    'messages': [{'role': 'user', 'content': '我之前还打电话咨询过退款流程'}]
}, h)
log('[2] 响应: ' + json.dumps(r, ensure_ascii=False))

log('')
log('='*70)
log('Step 3 — 对话写入(dialogue) → 覆盖更新 update_existing')
log('='*70)
log('目的：写入与已有事实矛盾的新值，预期事件 UPDATE')
r = call('POST', '/api/v1/memory/write', {
    'user_id': uid, 'scene_id': ctx['scene_id'], 'session_id': ctx['session_id'],
    'interaction_type': 'dialogue',
    'messages': [{'role': 'user', 'content': '之前说退款3个工作日是错的，实际是7个工作日'}]
}, h)
log('[3] 响应: ' + json.dumps(r, ensure_ascii=False))

log('')
log('='*70)
log('Step 4 — 对话写入(dialogue) → 丢弃 discard')
log('='*70)
log('目的：写入与已有记忆高度重复的内容，预期事件 SKIP')
r = call('POST', '/api/v1/memory/write', {
    'user_id': uid, 'scene_id': ctx['scene_id'], 'session_id': ctx['session_id'],
    'interaction_type': 'dialogue',
    'messages': [{'role': 'user', 'content': '我买的衣服尺寸不合适想退货，订单号是DH001'}]
}, h)
log('[4] 响应: ' + json.dumps(r, ensure_ascii=False))

log('')
log('='*70)
log('Step 5 — 历史会话写入(session) → 新增 keep_new')
log('='*70)
log('目的：导入一段历史会话（全新话题），预期事件 ADD')
r = call('POST', '/api/v1/memory/write', {
    'user_id': uid, 'scene_id': ctx['scene_id'], 'session_id': ctx['session_id'],
    'interaction_type': 'session',
    'session_time': '2026-08-01T10:00:00Z', 'session_source': '电话客服',
    'messages': [
        {'role': 'user', 'content': '我之前电话咨询过运费是多少'},
        {'role': 'assistant', 'content': '运费是10元，满99元包邮'}
    ]
}, h)
log('[5] 响应: ' + json.dumps(r, ensure_ascii=False))

log('')
log('='*70)
log('Step 6 — 任务过程写入(task_process) → 补充')
log('='*70)
log('目的：写入任务过程（关于DH001任务），预期事件 MERGE 或 ADD')
r = call('POST', '/api/v1/memory/write', {
    'user_id': uid, 'scene_id': ctx['scene_id'], 'session_id': ctx['session_id'],
    'interaction_type': 'task_process',
    'task_goal': '处理订单DH001退款', 'task_progress': '已提交退货申请，等待仓库质检', 'task_result': ''
}, h)
log('[6] 响应: ' + json.dumps(r, ensure_ascii=False))

log('')
log('session_id=' + ctx['session_id'])
log('agent_id=' + ctx['agent_id'])
log('scene_id=' + ctx['scene_id'])
log('api_key=' + ctx['api_key'])
