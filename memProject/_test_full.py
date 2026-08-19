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

# 全局变量
ctx = {}

log('='*70)
log('【第一层】接入与基础 CRUD')
log('='*70)

# [1] 创建场景
r = call('POST', '/api/v1/scene', {'scene_name': '客服场景', 'description': '处理咨询退款'})
log('[1] 创建场景: ' + json.dumps(r, ensure_ascii=False)[:150])
ctx['scene_id'] = r['data']['scene_id']

# [2] 注册智能体
r = call('POST', '/api/v1/agent/register', {'agent_name': '客服助手', 'scene_id': ctx['scene_id'], 'permissions': ['read','write']})
log('[2] 注册智能体: ' + json.dumps(r, ensure_ascii=False)[:200])
ctx['agent_id'] = r['data']['agent_id']
ctx['api_key'] = r['data']['api_key']

# [3] 校验不存在的 scene
r = call('POST', '/api/v1/agent/register', {'agent_name': 'x', 'scene_id': '不存在'})
log('[3] 无效scene校验: code=' + str(r.get('code')) + ' error_code=' + str(r.get('error_code')))

# [4] 查询智能体
r = call('GET', f"/api/v1/agent/{ctx['agent_id']}", headers={'X-API-Key': ctx['api_key']})
log('[4] 查询智能体: agent_id=' + r.get('data',{}).get('agent_id','') + ' scene_id=' + r.get('data',{}).get('scene_id',''))

log('')
log('='*70)
log('【第二层】主链路时序')
log('='*70)

uid = 'test_user_001'
h = {'X-API-Key': ctx['api_key'], 'X-User-Id': uid, 'X-Agent-Id': ctx['agent_id']}

# [5] 创建会话
r = call('POST', '/api/v1/session', {'user_id': uid, 'scene_id': ctx['scene_id']}, h)
log('[5] 创建会话: session_id=' + r.get('data',{}).get('session_id','') + ' agent_id=' + r.get('data',{}).get('agent_id',''))
ctx['session_id'] = r.get('data',{}).get('session_id','')

# [6] 写入前检索
r = call('POST', '/api/v1/memory/search', {'query': '退货退款', 'user_id': uid, 'top_k': 5}, h)
log('[6] 写入前检索: total_candidates=' + str(r.get('data',{}).get('total_candidates')) + ' (应为0)')

# [7] 写入对话
log('[7] 写入对话(dialogue)... 等待LLM')
r = call('POST', '/api/v1/memory/write', {
    'user_id': uid, 'scene_id': ctx['scene_id'], 'session_id': ctx['session_id'],
    'interaction_type': 'dialogue',
    'messages': [
        {'role': 'user', 'content': '我买的衣服尺寸不合适想退货，订单号DH001'},
        {'role': 'assistant', 'content': '好的，我帮您提交退货申请，退款3个工作日内到账'}
    ]
}, h)
log('[7] 写入结果: ' + json.dumps(r, ensure_ascii=False)[:300])

# [8] 再检索
r = call('POST', '/api/v1/memory/search', {'query': '退货退款', 'user_id': uid, 'top_k': 5}, h)
log('[8] 写入后检索: total_candidates=' + str(r.get('data',{}).get('total_candidates')))

# [9] 上下文返回
r = call('POST', '/api/v1/memory/context', {'query': '退货退款', 'user_id': uid, 'max_tokens': 2000}, h)
log('[9] 上下文返回: memory_count=' + str(r.get('data',{}).get('memory_count')) + ' text=' + str(r.get('data',{}).get('formatted_text',''))[:120])

# [10] 写入历史会话
log('[10] 写入历史会话(session)... 等待LLM')
r = call('POST', '/api/v1/memory/write', {
    'user_id': uid, 'scene_id': ctx['scene_id'], 'session_id': ctx['session_id'],
    'interaction_type': 'session',
    'session_time': '2026-08-10T10:00:00Z', 'session_source': '电话客服',
    'messages': [
        {'role': 'user', 'content': '我之前电话问过退款流程'},
        {'role': 'assistant', 'content': '电话里已告知退款3个工作日到账'}
    ]
}, h)
log('[10] 历史会话写入: ' + json.dumps(r, ensure_ascii=False)[:200])

# [11] 写入任务过程
log('[11] 写入任务过程(task_process)... 等待LLM')
r = call('POST', '/api/v1/memory/write', {
    'user_id': uid, 'scene_id': ctx['scene_id'], 'session_id': ctx['session_id'],
    'interaction_type': 'task_process',
    'task_goal': '处理订单DH001退款', 'task_progress': '已提交退货申请，等待仓库质检',
    'task_result': ''
}, h)
log('[11] 任务过程写入: ' + json.dumps(r, ensure_ascii=False)[:200])

log('')
log('session_id=' + ctx['session_id'])
log('agent_id=' + ctx['agent_id'])
log('scene_id=' + ctx['scene_id'])
log('api_key=' + ctx['api_key'])
