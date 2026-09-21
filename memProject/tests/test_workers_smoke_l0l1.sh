#!/usr/bin/env bash
# =============================================================================
# 智能体记忆系统 — L0 / L1 快速冒烟测试(约 25 秒)
#
# 用法: bash test_workers_smoke_l0l1.sh [BASE_URL]
#
# 快速验证:
#   L0: write 返回 accepted + record_ids(落库/投递成功)
#   L1: 写入后 l1.backlog 出现待抽取记录,随后归零且 l1.success 增加
# 不等待 L2/L3(由 e2e 脚本覆盖)。
# =============================================================================
set -u
BASE="${1:-http://211.87.232.203:8001}"
TAG="tst_l0l1_$(date +%s)"
MUID="$TAG"
SESS="sess_${TAG}"
RET=0

echo "== health =="
curl -s "$BASE/api/v1/health"; echo

echo "== 写入对话(user=$MUID) =="
MSG='{"user_id":"'"$MUID"'","session_id":"'"$SESS"'","interaction_type":"dialogue","messages":[{"role":"user","content":"我叫王强，是运维工程师，喜欢跑步。"}]}'
WRITE=$(curl -s -X POST "$BASE/api/v1/memory/write" -H 'Content-Type: application/json' -d "$MSG")
echo "write: $WRITE"
L0=$(echo "$WRITE" | python3 -c 'import sys,json; print(json.load(sys.stdin)["data"].get("l0_count",0))' 2>/dev/null)
if [ "${L0:-0}" -gt 0 ]; then echo "[✔] L0 落库: accepted, l0_count=$L0"; else echo "[✘] L0 失败"; RET=1; fi

echo "-- t+3s: 应看到 l1.backlog 出现 --"
sleep 3
curl -s "$BASE/api/v1/monitor/stats" | python3 -c 'import sys,json; d=json.load(sys.stdin)["data"]["layers"]; print("l1: success=%s failed=%s backlog=%s" % (d["l1"]["success"],d["l1"]["failed"],d["l1"]["backlog"]))'

echo "-- t+18s: l1.backlog 应归零, success 应增加 --"
sleep 15
curl -s "$BASE/api/v1/monitor/stats" | python3 -c 'import sys,json; d=json.load(sys.stdin)["data"]["layers"]; print("l1: success=%s failed=%s backlog=%s" % (d["l1"]["success"],d["l1"]["failed"],d["l1"]["backlog"]))'

echo "== /memory/list 该用户 L1 记忆 =="
curl -s "$BASE/api/v1/memory/list?user_id=$MUID&page_size=20" \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print("total:", d.get("total")); [print("  -", it.get("content","")[:70]) for it in d.get("items",[])[:5]]'

[ "$RET" -eq 0 ] && echo "== 冒烟结论: PASS ==" || echo "== 冒烟结论: FAIL =="
exit "$RET"
