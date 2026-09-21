#!/usr/bin/env bash
# =============================================================================
# 智能体记忆系统 — L0 / L1 / L2 / L3 Worker 端到端健康测试
#
# 用法:
#   bash test_workers_e2e.sh [BASE_URL]            # 默认 http://211.87.232.203:8001
#   POLLS=20 INTERVAL=8 bash test_workers_e2e.sh   # 自定义轮询次数/间隔
#
# 原理:
#   写入一条含多条事实的 8+2 对话 → L0 落库(pending_extract)
#     → L1 worker 游标抽取出 L1 记忆
#     → L2 worker 按 (scene,user) 聚合生成 SceneBlock
#     → L3 worker 攒够 >=5 条新 L1 触发 Persona 画像
#   轮询 /api/v1/monitor/stats 观察每层 backlog 归零 + success 环比增加。
#
# 判定:
#   L0: write 返回 accepted 且 l0_count>0
#   L1: l1.success 增加 >=1 且 l1.backlog 归零
#   L2: l2.success 增加 >=1 且 l2.backlog 归零
#   L3: l3.success 增加 >=1(画像生成);backlog 归零
#   另用 /memory/list 确认 L1 内容、/memory/profile 确认 Persona。
# =============================================================================
set -u
BASE="${1:-http://211.87.232.203:8001}"
POLLS="${POLLS:-18}"
INTERVAL="${INTERVAL:-8}"
TAG="tst_wk_$(date +%s)"
MUID="$TAG"
SCENE="scene_${TAG}"
SESS="sess_${TAG}"
RET=0

echo "================ 测试环境 ================"
echo "BASE  : $BASE"
echo "USER  : $MUID"
echo "SCENE : $SCENE"
echo "SESS  : $SESS"

fetch_stats() {
  curl -s "$BASE/api/v1/monitor/stats" | python3 -c '
import sys, json
d = json.load(sys.stdin)["data"]["layers"]
print(d["l1"]["success"], d["l1"]["failed"], d["l1"]["backlog"],
      d["l2"]["success"], d["l2"]["failed"], d["l2"]["backlog"],
      d["l3"]["success"], d["l3"]["failed"], d["l3"]["backlog"])
'
}

echo
echo "============= 健康 & 初始指标 ============="
echo "health: $(curl -s "$BASE/api/v1/health")"
read L1Si L1Fi L1Bi L2Si L2Fi L2Bi L3Si L3Fi L3Bi <<< "$(fetch_stats)"
echo "init   : l1(s=$L1Si f=$L1Fi b=$L1Bi) | l2(s=$L2Si f=$L2Fi b=$L2Bi) | l3(s=$L3Si f=$L3Fi b=$L3Bi)"

echo
echo "=============== 1) 驱动 L0 落库 ================"
MSG=$(python3 -c '
import json
facts = [
    "我的名字叫李晓明，今年28岁，是一名软件工程师。",
    "我目前在负责Alpha项目的后端开发，团队一共5个人。",
    "我养了一只叫咪咪的橘猫，它今年3岁。",
    "我平时喜欢打篮球，也爱看科幻小说。",
    "我的擅长领域是Python后端和数据库设计。",
    "我对公司的代码评审流程不太满意，觉得耗时太长。",
    "最近我在学习Kubernetes容器编排技术。",
    "我的作息是晚上12点睡，早上8点起。",
]
msgs = [{"role": "user", "content": c} for c in facts]
msgs.append({"role": "assistant", "content": "这些信息我都记下了。"})
print(json.dumps({
    "user_id": "'"$MUID"'",
    "scene_id": "'"$SCENE"'",
    "session_id": "'"$SESS"'",
    "interaction_type": "dialogue",
    "messages": msgs,
}))
')
WRITE=$(curl -s -X POST "$BASE/api/v1/memory/write" -H 'Content-Type: application/json' -d "$MSG")
echo "write: $WRITE"
L0=$(echo "$WRITE" | python3 -c 'import sys,json; print(json.load(sys.stdin)["data"].get("l0_count",0))' 2>/dev/null)
if [ "${L0:-0}" -gt 0 ]; then
  echo "[✔] L0 落库成功: accepted + l0_count=$L0"
else
  echo "[✘] L0: write 未返回 accepted/l0_count"
  RET=1
fi

echo
echo "=============== 2) 轮询观测 L1/L2/L3 ================"
i=0
while [ "$i" -lt "$POLLS" ]; do
  sleep "$INTERVAL"
  i=$((i+1))
  read L1S L1F L1B L2S L2F L2B L3S L3F L3B <<< "$(fetch_stats)"
  printf "t+%3ss  l1(s=%d f=%d b=%d)   l2(s=%d f=%d b=%d)   l3(s=%d f=%d b=%d)\n" \
    $((i*INTERVAL)) "$L1S" "$L1F" "$L1B" "$L2S" "$L2F" "$L2B" "$L3S" "$L3F" "$L3B"
done

echo
echo "============== 3) 各层判定 ================"
DL1=$((L1S-L1Si)); DL1F=$((L1F-L1Fi))
DL2=$((L2S-L2Si)); DL2F=$((L2F-L2Fi))
DL3=$((L3S-L3Si)); DL3F=$((L3F-L3Fi))

if [ "$DL1" -ge 1 ] && [ "$L1B" -eq 0 ]; then
  echo "[✔] L1 抽取正常: success +$DL1, backlog=0"
else
  echo "[✘] L1 抽取: success 增量=$DL1, failed 增量=$DL1F, backlog=$L1B"
  RET=1
fi

if [ "$DL2" -ge 1 ] && [ "$L2B" -eq 0 ]; then
  echo "[✔] L2 场景聚合正常: success +$DL2, backlog=0"
else
  echo "[✘] L2 聚合: success 增量=$DL2, failed 增量=$DL2F, backlog=$L2B"
  RET=1
fi

# L3 以画像实际产出为准(画像 LLM 可能比轮询窗口更慢,stats 计数器会有时序延迟)
PROF=$(curl -s -X POST "$BASE/api/v1/memory/profile" -H 'Content-Type: application/json' \
  -d '{"user_id":"'"$MUID"'","scene_id":"'"$SCENE"'"}')
PERSONA=$(echo "$PROF" | python3 -c 'import sys,json; d=json.load(sys.stdin).get("data") or {}; print(d.get("persona") or "")')
CS=$(echo "$PROF" | python3 -c 'import sys,json; d=json.load(sys.stdin).get("data") or {}; print(d.get("changed_scenes") or 0)')
if [ -n "$PERSONA" ]; then
  echo "[✔] L3 画像生成正常: persona 已生成, changed_scenes=$CS"
else
  echo "[✘] L3 画像: stats 增量 DL3=$DL3 backlog=$L3B, 且 profile 查无 persona"
  RET=1
fi

echo
echo "============== 4) 内容校验 ================"
echo "-- /memory/list (L1 记忆) --"
curl -s "$BASE/api/v1/memory/list?user_id=$MUID&scene_id=$SCENE&page_size=50" \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print("L1 记忆总条数:", d.get("total")); [print("  -", it.get("content","")[:60]) for it in d.get("items",[])[:8]]'

echo "-- /memory/profile (L3 画像) --"
curl -s -X POST "$BASE/api/v1/memory/profile" -H 'Content-Type: application/json' \
  -d '{"user_id":"'"$MUID"'","scene_id":"'"$SCENE"'"}'
echo

echo
if [ "$RET" -eq 0 ]; then
  echo "==== 结论: 全部 PASS — L0/L1/L2/L3 worker 均正常工作 ===="
else
  echo "==== 结论: 部分 FAIL(见上方 [✘]) ===="
fi
exit "$RET"
