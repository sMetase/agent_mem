#!/usr/bin/env bash
# =============================================================================
# 智能体记忆系统 — Worker 只读监控脚本
#
# 用法: bash test_workers_monitor.sh [BASE_URL] [次数] [间隔秒]
# 默认采样 6 次、间隔 5 秒;观察 backlog 是否长时间滞留(worker 卡死判定)。
# 只读操作(不写入任何数据)。
# =============================================================================
set -u
BASE="${1:-http://211.87.232.203:8001}"
N="${2:-6}"
IV="${3:-5}"

echo "== 连续采样 $N 次(间隔 ${IV}s) =="
echo "日期: $(date '+%F %T')  后端: $BASE"
for i in $(seq 1 "$N"); do
  curl -s "$BASE/api/v1/monitor/stats" | python3 -c '
import sys, json
d = json.load(sys.stdin)["data"]
ls = d["layers"]
print("uptime=%ss | l1(s=%s f=%s b=%s r=%s) | l2(s=%s f=%s b=%s) | l3(s=%s f=%s b=%s)"
      % (d["uptime_seconds"],
         ls["l1"]["success"], ls["l1"]["failed"], ls["l1"]["backlog"], ls["l1"]["rate_per_min"],
         ls["l2"]["success"], ls["l2"]["failed"], ls["l2"]["backlog"],
         ls["l3"]["success"], ls["l3"]["failed"], ls["l3"]["backlog"]))
'
  [ "$i" -lt "$N" ] && sleep "$IV"
done
echo "== 提示: 若某层 backlog 持续 >0 且不下降, 该层 worker 可能卡死 =="
