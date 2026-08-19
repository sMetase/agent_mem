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

# ============================================================
log('='*70)
log('第一部分：接入（场景 / 智能体 / 会话）')
log('='*70)

r = call('POST', '/api/v1/scene', {'scene_name': '客服场景', 'description': '处理咨询退款'})
ctx['scene_id'] = r['data']['scene_id']
log('[1] 创建场景 → ' + ctx['scene_id'])

r = call('GET', f"/api/v1/scene/{ctx['scene_id']}")
log('[2] 查询场景 → ' + json.dumps(r.get('data',{}).get('scene_name',''), ensure_ascii=False))

r = call('GET', '/api/v1/scene')
log('[3] 场景列表 → 数量=' + str(len(r.get('data',{}).get('items', r.get('data',[])))))

r = call('POST', '/api/v1/agent/register', {'agent_name': '客服助手', 'scene_id': ctx['scene_id'], 'permissions': ['read','write']})
ctx['agent_id'] = r['data']['agent_id']; ctx['api_key'] = r['data']['api_key']
log('[4] 注册智能体 → ' + ctx['agent_id'])

r = call('GET', f"/api/v1/agent/{ctx['agent_id']}", headers={'X-API-Key': ctx['api_key']})
log('[5] 查询智能体 → ' + json.dumps(r.get('data',{}).get('agent_id',''), ensure_ascii=False))

r = call('GET', '/api/v1/agent', headers={'X-API-Key': ctx['api_key']})
log('[6] 智能体列表 → 数量=' + str(len(r.get('data',{}).get('items', r.get('data',[])))))

h = {'X-API-Key': ctx['api_key'], 'X-User-Id': uid, 'X-Agent-Id': ctx['agent_id']}
r = call('POST', '/api/v1/session', {'user_id': uid, 'scene_id': ctx['scene_id']}, h)
ctx['session_id'] = r['data']['session_id']
log('[7] 创建会话 → ' + ctx['session_id'])

r = call('GET', f"/api/v1/session/{ctx['session_id']}", headers=h)
log('[8] 查询会话 → status=' + str(r.get('data',{}).get('status','')))

r = call('GET', '/api/v1/session', headers=h)
log('[9] 会话列表 → 数量=' + str(len(r.get('data',{}).get('items', r.get('data',[])))))

# ============================================================
log('')
log('='*70)
log('第二部分：主链路（检索→写入→检索→上下文）')
log('='*70)

r = call('POST', '/api/v1/memory/search', {'query': '退货退款', 'user_id': uid, 'top_k': 5}, h)
log('[10] 写入前检索 → total_candidates=' + str(r.get('data',{}).get('total_candidates','?')) + ' (应为0)')

log('')
log('='*70)
log('第三部分：去重类型多次测试（新增/合并/覆盖/丢弃）')
log('='*70)

def wr(label, itype, messages=None, **kw):
    body = {'user_id': uid, 'scene_id': ctx['scene_id'], 'session_id': ctx['session_id'], 'interaction_type': itype}
    if messages: body['messages'] = messages
    body.update(kw)
    r = call('POST', '/api/v1/memory/write', body, h)
    ev = [(x.get('event'), x.get('id','')[:12]) for x in r.get('data',{}).get('results',[])]
    log(f'{label} → {ev}')
    return r

# 新增 keep_new ×4
wr('[11] 新增1(退货DH001) dialogue', 'dialogue', [
    {'role':'user','content':'我买的衣服尺寸不合适想退货，订单号DH001'},
    {'role':'assistant','content':'好的，帮您提交退货申请，退款3个工作日内到账'}])
wr('[12] 新增2(会员积分) dialogue', 'dialogue', [
    {'role':'user','content':'我想咨询会员积分规则'}])
wr('[13] 新增3(运费) session', 'session', [
    {'role':'user','content':'运费是多少'},{'role':'assistant','content':'运费10元，满99包邮'}],
    session_time='2026-08-01T10:00:00Z', session_source='电话客服')
wr('[14] 新增4(发票) dialogue', 'dialogue', [
    {'role':'user','content':'我想开发票，需要提供什么信息'}])

# 合并 merge ×3
wr('[15] 合并1(电话咨询退款流程) dialogue', 'dialogue', [
    {'role':'user','content':'我之前还打电话咨询过退款流程'}])
wr('[16] 合并2(退货地址) dialogue', 'dialogue', [
    {'role':'user','content':'退货地址是上海市浦东新区XX路100号'}])
wr('[17] 合并3(质检) task_process', 'task_process',
    task_goal='处理订单DH001退款', task_progress='已提交退货申请，等待仓库质检', task_result='')

# 覆盖更新 update ×2
wr('[18] 覆盖1(3→7工作日) dialogue', 'dialogue', [
    {'role':'user','content':'之前说退款3个工作日是错的，实际是7个工作日'}])
wr('[19] 覆盖2(订单号DH001→DH002) dialogue', 'dialogue', [
    {'role':'user','content':'订单号我记错了，不是DH001，是DH002'}])

# 丢弃 discard ×2
wr('[20] 丢弃1(重述退货子集) dialogue', 'dialogue', [
    {'role':'user','content':'我买的衣服尺寸不合适想退货，订单号是DH002'}])
wr('[21] 丢弃2(重述运费) session', 'session', [
    {'role':'user','content':'运费是多少'},{'role':'assistant','content':'运费10元，满99包邮'}],
    session_time='2026-08-01T10:05:00Z', session_source='电话客服')

log('')
r = call('POST', '/api/v1/memory/search', {'query': '退款', 'user_id': uid, 'top_k': 5}, h)
log('[22] 写入后检索(退款) → total_candidates=' + str(r.get('data',{}).get('total_candidates','?')))

r = call('POST', '/api/v1/memory/context', {'query': '退款进度', 'user_id': uid, 'max_tokens': 2000}, h)
log('[23] 上下文(退款进度) → memory_count=' + str(r.get('data',{}).get('memory_count','?')))

# ============================================================
log('')
log('='*70)
log('第四部分：任务管理')
log('='*70)

r = call('POST', '/api/v1/task', {'user_id': uid, 'title': '处理DH002退款', 'goal': '完成退款全流程', 'scene_id': ctx['scene_id']}, h)
ctx['task_id'] = r.get('data',{}).get('task_id','')
log('[24] 创建任务 → ' + ctx['task_id'])

r = call('GET', f"/api/v1/task/{ctx['task_id']}", headers=h)
log('[25] 查询任务 → status=' + str(r.get('data',{}).get('status','')))

r = call('GET', '/api/v1/task', headers=h)
log('[26] 任务列表 → 数量=' + str(len(r.get('data',{}).get('items', r.get('data',[])))))

r = call('PUT', f"/api/v1/task/{ctx['task_id']}", {'status': 'in_progress', 'progress': '已提交退货申请'}, h)
log('[27] 更新任务进展 → ' + json.dumps(r.get('data',{}), ensure_ascii=False)[:80])

r = call('GET', f"/api/v1/task/{ctx['task_id']}/progress", headers=h)
log('[28] 任务进展摘要 → ' + json.dumps(r.get('data',{}), ensure_ascii=False)[:120])

r = call('POST', f"/api/v1/task/{ctx['task_id']}/complete", headers=h)
log('[29] 完成任务 → status=' + str(r.get('data',{}).get('status','')))

# ============================================================
log('')
log('='*70)
log('第五部分：生命周期（关闭会话/画像/列表/统计）')
log('='*70)

r = call('POST', f"/api/v1/session/{ctx['session_id']}/close", headers=h)
log('[30] 关闭会话 → ' + json.dumps(r.get('data',{}), ensure_ascii=False)[:200])

r = call('POST', '/api/v1/memory/profile', {'user_id': uid}, h)
log('[31] 用户画像 → memory_count=' + str(r.get('data',{}).get('memory_count','?')))

r = call('POST', '/api/v1/memory/list?user_id=' + uid, headers=h)
log('[32] 记忆列表 → total=' + str(r.get('data',{}).get('total','?')))

r = call('GET', f"/api/v1/memory/stats?user_id={uid}", headers=h)
log('[33] 层级统计 → ' + json.dumps(r.get('data',{}).get('level_distribution',[]), ensure_ascii=False)[:150])

# ============================================================
log('')
log('='*70)
log('第六部分：记忆管理（手动更新/软删除/检索）')
log('='*70)

# 先查一条 active 记忆用于更新/删除
r = call('POST', '/api/v1/memory/list?user_id=' + uid, headers=h)
items = r.get('data',{}).get('items',[])
if items:
    mid = items[0]['memory_id']
    r = call('PUT', '/api/v1/memory/update', {'memory_id': mid, 'importance': 0.9}, h)
    log(f'[34] 手动更新记忆({mid[:12]}) → updated=' + str(r.get('data',{}).get('updated','')))
    r = call('DELETE', '/api/v1/memory/delete', {'memory_id': mid, 'reason': '测试删除'}, h)
    log(f'[35] 软删除记忆({mid[:12]}) → deleted=' + str(r.get('data',{}).get('deleted','')))
else:
    log('[34/35] 无 active 记忆可更新/删除')

# ============================================================
log('')
log('='*70)
log('第七部分：生成接口')
log('='*70)

r = call('POST', '/api/v1/memory/generate', {'user_id': uid, 'scene_id': ctx['scene_id'], 'session_id': ctx['session_id'], 'text': '用户咨询退款流程，客服告知退款7个工作日到账'}, h)
log('[36] 生成(generate) → ' + json.dumps(r, ensure_ascii=False)[:120])

r = call('POST', '/api/v1/memory/generate/batch', {'user_id': uid, 'texts': ['用户喜欢简洁的回复风格', '用户是VIP会员']}, h)
log('[37] 批量生成(batch) → ' + json.dumps(r, ensure_ascii=False)[:120])

r = call('POST', '/api/v1/memory/compress', {'user_id': uid, 'text': '用户问了很多关于退款的问题，最后确认退款7个工作日到账，用户表示满意'}, h)
log('[38] 压缩(compress) → ' + json.dumps(r, ensure_ascii=False)[:120])

# ============================================================
log('')
log('='*70)
log('第八部分：管理类端点（更新/停用/清空/后台统计）')
log('='*70)

r = call('PUT', f"/api/v1/scene/{ctx['scene_id']}", {'description': '处理咨询退款（已更新）'})
log('[39] 更新场景 → ' + json.dumps(r.get('data',{}), ensure_ascii=False)[:80])

r = call('PUT', f"/api/v1/agent/{ctx['agent_id']}", {'agent_name': '客服助手V2'}, headers={'X-API-Key': ctx['api_key']})
log('[40] 更新智能体 → ' + json.dumps(r.get('data',{}), ensure_ascii=False)[:80])

r = call('GET', '/api/v1/admin/stats', headers=h)
log('[41] admin/stats → ' + json.dumps(r.get('data',{}), ensure_ascii=False)[:150])

r = call('GET', '/api/v1/admin/dashboard', headers=h)
log('[42] admin/dashboard → ' + json.dumps(r, ensure_ascii=False)[:120])

r = call('GET', '/api/v1/admin/memories?page=1&page_size=5', headers=h)
log('[43] admin/memories → 数量=' + str(len(r.get('data',{}).get('items', r.get('data',[])))))

r = call('GET', '/api/v1/admin/api-logs', headers=h)
log('[44] admin/api-logs → ' + json.dumps(r, ensure_ascii=False)[:100])

# ============================================================
log('')
log('='*70)
log('第九部分：多场景 / 多用户隔离')
log('='*70)

r = call('POST', '/api/v1/scene', {'scene_name': '售前场景', 'description': '售前咨询'})
scene2 = r['data']['scene_id']
log('[45] 创建场景2 → ' + scene2)

r = call('POST', '/api/v1/agent/register', {'agent_name': '售前助手', 'scene_id': scene2, 'permissions': ['read','write']})
agent2 = r['data']['agent_id']; api2 = r['data']['api_key']
log('[46] 注册智能体2 → ' + agent2)

h2 = {'X-API-Key': api2, 'X-User-Id': 'test_user_002', 'X-Agent-Id': agent2}
r = call('POST', '/api/v1/session', {'user_id': 'test_user_002', 'scene_id': scene2}, h2)
sess2 = r['data']['session_id']
log('[47] 创建用户2会话 → ' + sess2)

r = call('POST', '/api/v1/memory/write', {'user_id': 'test_user_002', 'scene_id': scene2, 'session_id': sess2, 'interaction_type': 'dialogue', 'messages': [{'role':'user','content':'你们有蓝牙耳机吗'}]}, h2)
log('[48] 用户2写入(蓝牙耳机) → ' + str([(x.get('event')) for x in r.get('data',{}).get('results',[])]))

r = call('POST', '/api/v1/memory/search', {'query': '蓝牙耳机', 'user_id': 'test_user_002', 'top_k': 5}, h2)
log('[49] 用户2检索(蓝牙耳机) → total_candidates=' + str(r.get('data',{}).get('total_candidates','?')))

r = call('POST', '/api/v1/memory/search', {'query': '蓝牙耳机', 'user_id': 'test_user_001', 'top_k': 5}, h)
log('[50] 用户1检索(蓝牙耳机,应看不到) → total_candidates=' + str(r.get('data',{}).get('total_candidates','?')) + ' (应为0)')

log('')
log('session_id=' + ctx['session_id'])
log('agent_id=' + ctx['agent_id'])
log('scene_id=' + ctx['scene_id'])
log('api_key=' + ctx['api_key'])
log('scene2=' + scene2)
log('agent2=' + agent2)
log('sess2=' + sess2)
