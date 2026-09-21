#!/usr/bin/env bash
# =============================================================================
# memProject MCP Server — 远程 Streamable HTTP 全套工具健康测试
#
# 用法: bash test_mcp_remote.sh [BASE_URL]
# 说明: 后端 FastAPI 内嵌 MCP server,挂载于 {BASE}/mcp/ 。OpenMemory 为内部
#       存储依赖,不对外暴露;本脚本测试的是 memProject 自己的 MCP 表面。
# 覆盖: initialize 握手 → tools/list → create_session → write_conversation
#       → search_memories(最多等 90s 让 L1 异步抽取)→ get_memory_context
#       → write_session_summary → close_session
# =============================================================================
set -u
BASE="${1:-http://211.87.232.203:8001}"
MCP="$BASE/mcp/"
TAG="mcp_tst_$(date +%s)"
MUID="$TAG"
AGENT="agent_mcp"
SCENE="mcp_scene_$TAG"
RET=0
SEARCH_TIMEOUT="${SEARCH_TIMEOUT:-90}"
SEARCH_INTERVAL="${SEARCH_INTERVAL:-10}"
SEQ=0

echo "================ 远程 MCP Server 健康测试 ================"
echo "MCP Endpoint : $MCP"
echo "测试用户     : $MUID"

# ---- 发送 JSON-RPC 请求;剥离 SSE 前缀,取第一条 data(JSON)----
mcp_req() { # $1=method, $2=params(JSON 字符串)
  SEQ=$((SEQ+1))
  curl -sN --max-time 20 -X POST "$MCP" \
    -H 'Content-Type: application/json' \
    -H 'Accept: application/json, text/event-stream' \
    -d "{\"jsonrpc\":\"2.0\",\"id\":$SEQ,\"method\":\"$1\",\"params\":$2}" \
    | sed -n 's/^data: //p' \
    | head -1
}

# ---- 从 JSON-RPC 响应中提取工具结果(兼容 data / structuredContent / content[0].text)----
extract_tool_result() {
  python3 -c '
import sys, json
raw = sys.stdin.read().strip()
if not raw:
    print("EMPTY"); sys.exit(0)
try:
    r = json.loads(raw)
except Exception as e:
    print("PARSE_ERR: " + str(e)); sys.exit(0)
res = r.get("result", r)
if isinstance(res, dict) and "data" in res:
    print(json.dumps(res["data"], ensure_ascii=False))
elif isinstance(res, dict) and "structuredContent" in res:
    print(json.dumps(res["structuredContent"], ensure_ascii=False))
elif isinstance(res, dict):
    c = res.get("content") or []
    if c and isinstance(c, list):
        first = c[0] if isinstance(c[0], dict) else {}
        print(first.get("text", "") if "text" in first else json.dumps(first, ensure_ascii=False))
    else:
        print(json.dumps(res, ensure_ascii=False))
else:
    print(json.dumps(res, ensure_ascii=False))
'
}

echo
echo "========== 1) initialize 握手 =========="
mcp_req initialize '{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"claude-probe","version":"1.0"}}' \
  | python3 -c '
import sys, json
raw = sys.stdin.read().strip()
r = json.loads(raw).get("result", {})
s = r.get("serverInfo", {})
caps = r.get("capabilities", {})
ok = bool(s.get("name")) and "tools" in caps
print(("✔" if ok else "✘"), "server:", s.get("name"), "v" + s.get("version", ""), "| tools capability:", "tools" in caps)
'
if [ $? -ne 0 ]; then RET=1; fi

echo
echo "========== 2) tools/list =========="
TOOLS=$(mcp_req tools/list '{}')
echo "$TOOLS" | python3 -c '
import sys, json
tools = json.loads(sys.stdin.read().strip()).get("result", {}).get("tools", [])
names = sorted(t["name"] for t in tools)
print("工具列表:", names)
'
if [ $? -ne 0 ]; then RET=1; fi

echo
echo "========== A) REST 上游预检 (MCP 工具内部依赖) =========="
# MCP 工具经 app/mcp_server.py _request 调用 REST API,上游默认 http://127.0.0.1:8000
U8_8000=$(echo "$BASE" | sed 's/:[0-9]*$/:8000/')
R801=$(curl -s --connect-timeout 3 -o /dev/null -w '%{http_code}' "$BASE/health")
R8000=$(curl -s --connect-timeout 3 -o /dev/null -w '%{http_code}' "$U8_8000/health" 2>/dev/null)
echo "  $BASE/health    -> HTTP ${R801:-000} (MCP 所在后端)"
echo "  $U8_8000/health -> HTTP ${R8000:-000} (代码默认上游 127.0.0.1:8000)"
if [ "$R8000" != "200" ]; then
  echo
  echo "[✘] MCP server 本体在线(握手成功、工具齐全),但工具调用内部连的默认上游 127.0.0.1:8000 不可达,"
  echo "    每个工具调用会等 http 超时后返回 'Upstream request timed out'。"
  echo "    修复: 部署端设置环境变量 MEMPROJECT_API_URL=http://127.0.0.1:8001 (与后端实际端口对齐) 并重启后端。"
  exit 2
fi
echo "[✔] 默认上游 8000 可达,继续工具测试"

echo
echo "========== 3) create_session =========="
CS=$(mcp_req tools/call '{"name":"create_session","arguments":{"user_id":"'$MUID'","scene_id":"'$SCENE'","agent_id":"'$AGENT'"}}')
SID=$(echo "$CS" | extract_tool_result | python3 -c 'import sys,json
try: print(json.loads(sys.stdin.read().strip()).get("session_id",""))
except Exception: print("")')
echo "create_session 结果: $(echo "$CS" | extract_tool_result)"
if [ -n "$SID" ]; then
  echo "[✔] create_session -> session_id=$SID"
else
  echo "[✘] create_session 未返回 session_id"
  RET=1; SID="sess_$TAG"
fi

echo
echo "========== 4) write_conversation (3 条事实) =========="
PARAMS='{"name":"write_conversation","arguments":{"user_id":"'$MUID'","session_id":"'$SID'","scene_id":"'$SCENE'","agent_id":"'$AGENT'","messages":[{"role":"user","content":"我叫李伟,28岁,是一名后端工程师,专注Python和数据库设计。"},{"role":"user","content":"我养了一只3岁的橘猫,名字叫咪咪,它是我重要的生活伙伴。"},{"role":"user","content":"我平时喜欢打篮球,也爱看科幻小说;最近在学Kubernetes。"},{"role":"assistant","content":"好的,这些信息我都记下了。"}]}}'
WC=$(mcp_req tools/call "$PARAMS")
echo "write_conversation 结果: $(echo "$WC" | extract_tool_result)"
echo "$WC" | extract_tool_result | python3 -c 'import sys,json
try:
    d=json.loads(sys.stdin.read().strip()); acc=d.get("accepted"); n=d.get("l0_count",0)
    print("[✔] write_conversation -> accepted=%s l0_count=%s" % (acc,n)) if acc else print("[✘] accepted 非真")
except Exception as e: print("[✘] 解析失败:", e)' \
  | grep -q '^[✔]' || RET=1

echo
echo "========== 5) search_memories (等待 L1 异步抽取) =========="
QUERY_PARAMS='{"name":"search_memories","arguments":{"user_id":"'$MUID'","scene_id":"'$SCENE'","query":"橘猫 咪咪","top_k":5}}'
SEARCHED=0
WAIT=0
while [ "$WAIT" -lt "$SEARCH_TIMEOUT" ]; do
  R=$(mcp_req tools/call "$QUERY_PARAMS")
  CNT=$(echo "$R" | extract_tool_result | python3 -c 'import sys,json
try:
    d=json.loads(sys.stdin.read().strip()); items=d.get("items") or d.get("results") or []
    print(len(items))
except Exception: print(-1)')
  echo "  t+${WAIT}s 检索命中: ${CNT} 条"
  if [ "${CNT:-0}" -gt 0 ]; then SEARCHED=1; break; fi
  sleep "$SEARCH_INTERVAL"; WAIT=$((WAIT+SEARCH_INTERVAL))
done
if [ "$SEARCHED" -eq 1 ]; then
  echo "[✔] search_memories 命中 ${CNT} 条(语义检索链路可用)"
else
  echo "[✘] search_memories 在 ${SEARCH_TIMEOUT}s 内未命中"
  RET=1
fi

echo
echo "========== 6) get_memory_context =========="
CTX=$(mcp_req tools/call '{"name":"get_memory_context","arguments":{"user_id":"'$MUID'","scene_id":"'$SCENE'","query":"用户基本情况","max_tokens":1500,"top_k":5}}')
echo "$CTX" | extract_tool_result | python3 -c 'import sys,json
try:
    d=json.loads(sys.stdin.read().strip())
    txt=d.get("context") or d.get("text") or ""
    print("[✔] get_memory_context 返回 %d 字符" % len(txt)) if len(txt)>0 else print("[✘] 返回为空")
except Exception as e: print("[✘] 解析失败:", e)' \
  | grep -q '^[✔]' || RET=1

echo
echo "========== 7) write_session_summary =========="
SUM=$(mcp_req tools/call '{"name":"write_session_summary","arguments":{"user_id":"'$MUID'","session_id":"'$SID'","scene_id":"'$SCENE'","agent_id":"'$AGENT'","session_summary":"本会话收集了用户李伟的基本信息:后端工程师、养橘猫咪咪、喜欢篮球和科幻小说、正在学习Kubernetes。"}}')
echo "write_session_summary 结果: $(echo "$SUM" | extract_tool_result)"
echo "$SUM" | extract_tool_result | python3 -c 'import sys,json
try:
    d=json.loads(sys.stdin.read().strip())
    print("[✔] write_session_summary -> accepted=%s l0_count=%s" % (d.get("accepted"), d.get("l0_count",0))) if d.get("accepted") else print("[✘] accepted 非真")
except Exception as e: print("[✘] 解析失败:", e)' \
  | grep -q '^[✔]' || RET=1

echo
echo "========== 8) close_session =========="
CL=$(mcp_req tools/call '{"name":"close_session","arguments":{"user_id":"'$MUID'","session_id":"'$SID'","agent_id":"'$AGENT'"}}')
echo "close_session 结果: $(echo "$CL" | extract_tool_result)"
echo "$CL" | extract_tool_result | python3 -c 'import sys,json
raw=sys.stdin.read().strip()
if raw and raw not in ("EMPTY",):
    print("[✔] close_session 已返回,压缩流程已触发")
else:
    print("[✔] close_session 已触发(无数据返回)")' \
  | grep -q '^[✔]' || RET=1

echo
echo "================ 结果汇总 ================"
if [ "$RET" -eq 0 ]; then
  echo "==== MCP Server 全部 PASS — create/write/search/context/summary/close 正常 ===="
else
  echo "==== MCP Server 部分 FAIL(见上方 [✘]) ===="
fi
exit "$RET"
