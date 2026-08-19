import json, urllib.request, urllib.error

BASE = 'http://127.0.0.1:8000'
scene_id = 'scene_90c9e14c'
agent_id = 'agent_7112b7c831534f75'
api_key = 'mem_cd240240e2e1e488cac7a5a6800f81accdfde04eaa745ea91548baec01d16062'
session_id = 'sess_4e72f967da1b'
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

h = {'X-API-Key': api_key, 'X-User-Id': uid, 'X-Agent-Id': agent_id}

log('='*70)
log('【第三层】去重融合验证')
log('='*70)

# [12] 写入相似内容（应 MERGE 或 DISCARD）
log('[12] 写入相似内容...')
r = call('POST', '/api/v1/memory/write', {
    'user_id': uid, 'scene_id': scene_id, 'session_id': session_id,
    'interaction_type': 'dialogue',
    'messages': [{'role': 'user', 'content': '就是那个DH001的退货退款，帮我催一下'}]
}, h)
log('[12] 相似内容: ' + json.dumps(r, ensure_ascii=False)[:250])

# [13] 写入全新内容（应 ADD）
log('[13] 写入全新内容...')
r = call('POST', '/api/v1/memory/write', {
    'user_id': uid, 'scene_id': scene_id, 'session_id': session_id,
    'interaction_type': 'dialogue',
    'messages': [{'role': 'user', 'content': '另外我还想咨询会员积分规则'}]
}, h)
log('[13] 全新内容: ' + json.dumps(r, ensure_ascii=False)[:250])

# [14] 写入矛盾内容（应 UPDATE 或 CONFLICT）
log('[14] 写入矛盾内容...')
r = call('POST', '/api/v1/memory/write', {
    'user_id': uid, 'scene_id': scene_id, 'session_id': session_id,
    'interaction_type': 'dialogue',
    'messages': [{'role': 'user', 'content': '之前说退款3个工作日是错的，实际是7个工作日'}]
}, h)
log('[14] 矛盾内容: ' + json.dumps(r, ensure_ascii=False)[:250])

log('')
log('='*70)
log('【第四层】生命周期管理')
log('='*70)

# [15] 任务管理
log('[15] 创建任务...')
r = call('POST', '/api/v1/task', {'user_id': uid, 'title': '处理DH001退款', 'goal': '完成退款全流程', 'scene_id': scene_id}, h)
log('[15] 创建任务: ' + json.dumps(r, ensure_ascii=False)[:200])
task_id = r.get('data',{}).get('task_id','')

if task_id:
    log('[15b] 更新任务进展...')
    r = call('PUT', f'/api/v1/task/{task_id}', {'status': 'in_progress', 'progress': '已提交退货申请'}, h)
    log('[15b] 更新进展: ' + json.dumps(r, ensure_ascii=False)[:200])

    log('[15c] 查询进展...')
    r = call('GET', f'/api/v1/task/{task_id}/progress', headers=h)
    log('[15c] 进展: ' + json.dumps(r, ensure_ascii=False)[:250])

    log('[15d] 完成任务...')
    r = call('POST', f'/api/v1/task/{task_id}/complete', headers=h)
    log('[15d] 完成: ' + json.dumps(r, ensure_ascii=False)[:200])

# [16] 关闭会话
log('[16] 关闭会话...')
r = call('POST', f'/api/v1/session/{session_id}/close', headers=h)
log('[16] 关闭会话: ' + json.dumps(r, ensure_ascii=False)[:300])

# [17] 用户画像
log('[17] 用户画像...')
r = call('POST', '/api/v1/memory/profile', {'user_id': uid}, h)
log('[17] 画像: ' + json.dumps(r, ensure_ascii=False)[:400])

# [18] 记忆管理
log('[18] 列出记忆...')
r = call('GET', f'/api/v1/memory/list?user_id={uid}', headers=h)
log('[18] list: total=' + str(r.get('data',{}).get('total','?')) + ' 前几条=' + json.dumps(r.get('data',{}).get('items',[])[:2], ensure_ascii=False)[:200])

log('[18b] 层级统计...')
r = call('GET', f'/api/v1/memory/stats?user_id={uid}', headers=h)
log('[18b] stats: ' + json.dumps(r, ensure_ascii=False)[:300])
