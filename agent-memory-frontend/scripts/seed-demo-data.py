# -*- coding: utf-8 -*-
"""
演示数据造数脚本 —— 智能体记忆系统前端联调用

作用：
    当前后端 DEEPSEEK_API_KEY / SILICONFLOW_API_KEY 为空，/memory/write 与
    /memory/generate 走降级模式，不会真正产出 t_memory 记录。本脚本绕过
    LLM 管道，直接用后端 ORM 向 PostgreSQL 插入一套完整的演示数据，
    覆盖 用户级 / 会话级 / 任务级 / 智能体级 记忆、会话、任务、智能体、
    场景、检索日志，供前端各页面联调验证界面改动。

运行方式（必须用后端 venv 的 Python，因为它装了 asyncpg/sqlalchemy）：
    D:\\PythonProject\\agent_mem-master\\memProject\\.venv\\Scripts\\python.exe ^
        scripts\\seed-demo-data.py

说明：
    - 幂等：重复运行会先清掉本脚本创建的 user_001 / user_002 演示数据再重插。
    - 数据主场景：企业级「智能客服 + 冷链物流 + 前端控制台」，与现有演示文案一致。
    - 记忆类型已对齐后端 5 类（fact / preference / task_state / process / correction）。
    - 0820 登录改造后：userId 由登录返回（不再手动配置）。若想登录后看到演示数据，
      把下方 PRIMARY_USER 常量改为登录返回的 user_id 后重跑。
"""

import asyncio
import logging
import sys
from datetime import datetime, timezone
from uuid import uuid4

logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

# 允许脚本在任意工作目录下导入后端模块
BACKEND_DIR = r"D:\PythonProject\agent_mem-master\memProject"
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.models.base import (
    Agent, Memory, MemoryRelation, RetrievalRequest, RetrievalResult,
    Scene, Session, Task, User,
)

DEMO_USERS = ("user_001", "user_002")


def utc(y, m, d, h=9, mi=0):
    """构造 UTC 时间。"""
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


def now():
    return datetime.now(timezone.utc)


# ============================================================
# 1. 场景 / 用户 / 智能体
# ============================================================

SCENES = [
    dict(scene_id="memory-console", scene_name="记忆管理控制台", description="前端控制台场景，承载开发与画像梳理类记忆"),
    dict(scene_id="customer_service", scene_name="智能客服", description="企业客服场景，承载退货退款、物流咨询类记忆"),
]

USERS = [
    dict(user_id="user_001", name="张三"),
    dict(user_id="user_002", name="李四"),
]

AGENTS = [
    dict(agent_id="agent_cs_001", agent_name="客服助手", scene_id="customer_service", permissions=["read", "write"]),
    dict(agent_id="agent_logistics_01", agent_name="物流调度助手", scene_id="customer_service", permissions=["read", "write"]),
    dict(agent_id="agent_dev_001", agent_name="前端开发助手", scene_id="memory-console", permissions=["read", "write", "admin"]),
]

# ============================================================
# 2. 会话 / 任务
# ============================================================

SESSIONS = [
    dict(session_id="sess_1001", user_id="user_001", agent_id="agent_cs_001", scene_id="customer_service", task_id="task_101", status="closed", started_at=utc(2026, 8, 7, 10), ended_at=utc(2026, 8, 7, 10, 40), message_count=12),
    dict(session_id="sess_1002", user_id="user_001", agent_id="agent_cs_001", scene_id="customer_service", task_id="task_102", status="active", started_at=utc(2026, 8, 9, 14), message_count=8),
    dict(session_id="sess_1003", user_id="user_001", agent_id="agent_cs_001", scene_id="customer_service", task_id=None, status="closed", started_at=utc(2026, 8, 10, 16), ended_at=utc(2026, 8, 10, 16, 30), message_count=6),
    dict(session_id="sess_1004", user_id="user_001", agent_id="agent_dev_001", scene_id="memory-console", task_id="task_103", status="active", started_at=utc(2026, 8, 11, 9), message_count=10),
    dict(session_id="sess_1005", user_id="user_001", agent_id="agent_dev_001", scene_id="memory-console", task_id=None, status="closed", started_at=utc(2026, 8, 7, 15), ended_at=utc(2026, 8, 7, 16), message_count=5),
    dict(session_id="sess_2001", user_id="user_002", agent_id="agent_cs_001", scene_id="customer_service", task_id="task_201", status="active", started_at=utc(2026, 8, 11, 11), message_count=7),
]

TASKS = [
    dict(task_id="task_101", user_id="user_001", agent_id="agent_cs_001", scene_id="customer_service", session_id="sess_1001", title="处理订单DH001退货退款", goal="完成订单DH001的退货退款全流程：物流核实、仓库质检、退款到账", status="in_progress",
         progress="仓库质检已通过，正在安排退款至原支付渠道",
         completed_items=["确认订单DH001属于可退换商品", "用户确认退货原因为尺寸不合适", "仓库质检通过"],
         pending_items=["退款到账确认", "售后回访"],
         started_at=utc(2026, 8, 7, 10)),
    dict(task_id="task_102", user_id="user_001", agent_id="agent_cs_001", scene_id="customer_service", session_id="sess_1002", title="物流配送方案优化", goal="优化冷链物流配送方案，降低温度偏差率，保留全程温度记录", status="in_progress",
         progress="两家候选承运商进入试运行，正在分析温度稳定性指标",
         completed_items=["对比三家承运商的温度监控方案", "确定双温区冷箱候选"],
         pending_items=["试运行温度数据分析", "确定最终承运商"],
         started_at=utc(2026, 8, 9, 14)),
    dict(task_id="task_103", user_id="user_001", agent_id="agent_dev_001", scene_id="memory-console", session_id="sess_1004", title="前端控制台性能优化", goal="优化前端控制台首屏加载与图表体积，构建体积下降约25%", status="completed",
         progress="图表按需引入与路由懒加载改造完成",
         completed_items=["依赖体积分析", "图表库按需引入", "路由懒加载改造"],
         pending_items=[],
         started_at=utc(2026, 8, 8, 9), ended_at=utc(2026, 8, 11, 18)),
    dict(task_id="task_104", user_id="user_001", agent_id="agent_dev_001", scene_id="memory-console", session_id=None, title="用户画像梳理", goal="梳理客户方关键角色与决策链路，形成结构化画像文档", status="pending",
         progress="已收集基础访谈记录，待整理结构化画像",
         completed_items=["访谈记录收集"],
         pending_items=["画像结构化整理", "关键角色图谱"],
         started_at=utc(2026, 8, 12, 9)),
    dict(task_id="task_201", user_id="user_002", agent_id="agent_cs_001", scene_id="customer_service", session_id="sess_2001", title="售后工单自动化初审改造", goal="实现售后工单自动化初审，降低人工转派成本", status="in_progress",
         progress="完成初审规则梳理，待开发",
         completed_items=["工单流转效率分析"],
         pending_items=["初审规则开发", "联调验收"],
         started_at=utc(2026, 8, 12, 10)),
]

# ============================================================
# 3. 记忆（核心）
#    字段：user/scope/type/content/tags/session/task/scene/created_at/importance/confidence/status
# ============================================================

def mem(**kw):
    kw.setdefault("importance", 0.8)
    kw.setdefault("confidence", 0.85)
    kw.setdefault("status", "active")
    return kw


USER_001_SCOPE_USER = [
    mem(memory_id="mem_u01", user_id="user_001", memory_scope="user", memory_type="preference", created_at=utc(2026, 8, 7, 10), tags=["颜色", "主题"],
        content="用户偏好深蓝色作为界面主题色，对暗色模式接受度较高", importance=0.7),
    mem(memory_id="mem_u02", user_id="user_001", memory_scope="user", memory_type="preference", created_at=utc(2026, 8, 8, 11), tags=["客服", "时效"],
        content="用户对智能客服的响应速度要求较高，期望5分钟内首次响应", importance=0.85),
    mem(memory_id="mem_u03", user_id="user_001", memory_scope="user", memory_type="preference", created_at=utc(2026, 8, 9, 9), tags=["沟通风格"],
        content="用户沟通风格简洁直接，偏好直达要点，不喜欢冗长解释", importance=0.75),
    mem(memory_id="mem_u04", user_id="user_001", memory_scope="user", memory_type="preference", created_at=utc(2026, 8, 10, 10), tags=["型号", "采购"],
        content="用户偏好使用Pro系列作为默认型号，关注交付时效", importance=0.8),
    mem(memory_id="mem_u05", user_id="user_001", memory_scope="user", memory_type="preference", created_at=utc(2026, 8, 11, 9), tags=["安全", "约束"],
        content="用户对数据安全要求严格，要求所有导出文件脱敏处理", importance=0.9),
    mem(memory_id="mem_u06", user_id="user_001", memory_scope="user", memory_type="preference", created_at=utc(2026, 8, 12, 10), tags=["代码风格"],
        content="用户偏好简洁高效的代码风格，强调可维护性", importance=0.7),
    mem(memory_id="mem_u07", user_id="user_001", memory_scope="user", memory_type="preference", created_at=utc(2026, 8, 12, 15), tags=["决策习惯"],
        content="用户决策偏保守，技术选型倾向成熟稳定方案", importance=0.8),
    mem(memory_id="mem_u08", user_id="user_001", memory_scope="user", memory_type="fact", created_at=utc(2026, 8, 8, 15), tags=["技术栈"],
        content="用户当前负责企业级管理控制台的开发，使用 React 19 + TypeScript 技术栈", importance=0.85),
    mem(memory_id="mem_u09", user_id="user_001", memory_scope="user", memory_type="fact", created_at=utc(2026, 8, 9, 10), tags=["团队"],
        content="用户所在团队共6人，客户方对接人为徐庸辉老师", importance=0.8),
    mem(memory_id="mem_u10", user_id="user_001", memory_scope="user", memory_type="fact", created_at=utc(2026, 8, 9, 16), tags=["项目", "排期"],
        content="项目计划于8月28日全量部署，8月20日前后进入部署测试", importance=0.9),
    mem(memory_id="mem_u11", user_id="user_001", memory_scope="user", memory_type="fact", created_at=utc(2026, 8, 10, 11), tags=["冷链"],
        content="用户采购过冷链运输服务，关注温度区间2-8°C的可靠性", importance=0.85),
    mem(memory_id="mem_u12", user_id="user_001", memory_scope="user", memory_type="fact", created_at=utc(2026, 8, 11, 14), tags=["业务"],
        content="用户有两个主营渠道：电商平台和线下门店", importance=0.7),
    mem(memory_id="mem_u13", user_id="user_001", memory_scope="user", memory_type="fact", created_at=utc(2026, 8, 12, 9), tags=["约束"],
        content="用户约束：所有记忆写入必须关联有效 Agent ID，禁止无主数据", importance=0.9),
    mem(memory_id="mem_u14", user_id="user_001", memory_scope="user", memory_type="correction", created_at=utc(2026, 8, 12, 16), tags=["修正"],
        content="用户曾更正：调度方案的偏好不是最快到达，而是温度稳定优先", importance=0.9),
    mem(memory_id="mem_u15", user_id="user_001", memory_scope="user", memory_type="preference", created_at=utc(2026, 8, 13, 9), tags=["客服"],
        content="用户对客服人员要求耐心细致，避免机械式回复", importance=0.75),
    mem(memory_id="mem_u16", user_id="user_001", memory_scope="user", memory_type="preference", created_at=utc(2026, 8, 13, 11), tags=["通知", "偏好"],
        content="用户希望重大变更提前一周书面通知", importance=0.8),
]

USER_001_SCOPE_SESSION = [
    mem(memory_id="mem_s01", user_id="user_001", memory_scope="session", memory_type="fact", session_id="sess_1001", scene_id="customer_service", created_at=utc(2026, 8, 7, 10), tags=["退货", "退款"],
        content="会话概要：用户咨询订单DH001退货退款，原因是尺寸不合适，已提交退货申请", importance=0.9),
    mem(memory_id="mem_s02", user_id="user_001", memory_scope="session", memory_type="fact", session_id="sess_1001", scene_id="customer_service", created_at=utc(2026, 8, 7, 10, 30), tags=["地址", "退款"],
        content="用户确认收货地址为北京市朝阳区，客服承诺3个工作日内退款到账", importance=0.85),
    mem(memory_id="mem_s03", user_id="user_001", memory_scope="session", memory_type="fact", session_id="sess_1002", scene_id="customer_service", created_at=utc(2026, 8, 9, 14), tags=["冷链", "物流"],
        content="会话概要：用户咨询冷链配送进度，确认包裹温度保持在2-8°C范围内", importance=0.85),
    mem(memory_id="mem_s04", user_id="user_001", memory_scope="session", memory_type="preference", session_id="sess_1002", scene_id="customer_service", created_at=utc(2026, 8, 9, 14, 20), tags=["冷链"],
        content="用户明确要求冷链运输必须全程温度记录可查", importance=0.9),
    mem(memory_id="mem_s05", user_id="user_001", memory_scope="session", memory_type="task_state", session_id="sess_1002", scene_id="customer_service", created_at=utc(2026, 8, 10, 9), tags=["物流", "进度"],
        content="客服正在核实配送异常原因，预计当日18点前反馈", importance=0.8),
    mem(memory_id="mem_s06", user_id="user_001", memory_scope="session", memory_type="fact", session_id="sess_1003", scene_id="customer_service", created_at=utc(2026, 8, 10, 16), tags=["收货", "反馈"],
        content="会话概要：用户签收后反馈包装完好，对整体服务满意", importance=0.7),
    mem(memory_id="mem_s07", user_id="user_001", memory_scope="session", memory_type="correction", session_id="sess_1003", scene_id="customer_service", created_at=utc(2026, 8, 10, 16, 30), tags=["反馈"],
        content="用户反馈客服响应速度快，但希望物流提醒更主动", importance=0.75),
    mem(memory_id="mem_s08", user_id="user_001", memory_scope="session", memory_type="fact", session_id="sess_1004", scene_id="memory-console", created_at=utc(2026, 8, 11, 9), tags=["性能"],
        content="会话概要：讨论控制台图表加载慢的问题，定位为G2运行时体积1.4MB", importance=0.8),
    mem(memory_id="mem_s09", user_id="user_001", memory_scope="session", memory_type="process", session_id="sess_1004", scene_id="memory-console", created_at=utc(2026, 8, 12, 10), tags=["图表"],
        content="决定将图表库改为按需引入，首页图表懒加载", importance=0.85),
    mem(memory_id="mem_s10", user_id="user_001", memory_scope="session", memory_type="task_state", session_id="sess_1004", scene_id="memory-console", created_at=utc(2026, 8, 13, 9), tags=["性能", "进度"],
        content="性能优化任务进行中，已完成依赖分析，待实施拆分", importance=0.8),
    mem(memory_id="mem_s11", user_id="user_001", memory_scope="session", memory_type="fact", session_id="sess_1005", scene_id="memory-console", created_at=utc(2026, 8, 7, 15), tags=["技术栈"],
        content="会话概要：确定前端技术栈为 React 19 + Vite 8 + Ant Design 6", importance=0.9),
    mem(memory_id="mem_s12", user_id="user_001", memory_scope="session", memory_type="process", session_id="sess_1005", scene_id="memory-console", created_at=utc(2026, 8, 7, 16), tags=["图表"],
        content="图表方案选定 @ant-design/plots 而非 @ant-design/charts，避免 graphs 冗余", importance=0.85),
]

USER_001_SCOPE_TASK = [
    mem(memory_id="mem_t01", user_id="user_001", memory_scope="task", memory_type="task_state", task_id="task_101", scene_id="customer_service", created_at=utc(2026, 8, 7, 10), tags=["退货", "目标"],
        content="任务目标：完成订单DH001退货退款全流程", importance=0.9),
    mem(memory_id="mem_t02", user_id="user_001", memory_scope="task", memory_type="process", task_id="task_101", scene_id="customer_service", created_at=utc(2026, 8, 8, 9), tags=["物流"],
        content="已联系物流确认退货入库，等待仓库质检", importance=0.8),
    mem(memory_id="mem_t03", user_id="user_001", memory_scope="task", memory_type="process", task_id="task_101", scene_id="customer_service", created_at=utc(2026, 8, 10, 11), tags=["退款"],
        content="仓库质检通过，正在安排退款至原支付渠道", importance=0.85),
    mem(memory_id="mem_t04", user_id="user_001", memory_scope="task", memory_type="process", task_id="task_101", scene_id="customer_service", created_at=utc(2026, 8, 10, 11, 30), tags=["决策"],
        content="决定优先原路退款，避免用户提供额外银行信息", importance=0.8),
    mem(memory_id="mem_t05", user_id="user_001", memory_scope="task", memory_type="task_state", task_id="task_102", scene_id="customer_service", created_at=utc(2026, 8, 9, 14), tags=["冷链", "目标"],
        content="任务目标：优化冷链物流配送方案，降低温度偏差率", importance=0.9),
    mem(memory_id="mem_t06", user_id="user_001", memory_scope="task", memory_type="process", task_id="task_102", scene_id="customer_service", created_at=utc(2026, 8, 11, 10), tags=["物流"],
        content="已对比三家承运商的温度监控方案，候选两家进入试运行", importance=0.85),
    mem(memory_id="mem_t07", user_id="user_001", memory_scope="task", memory_type="process", task_id="task_102", scene_id="customer_service", created_at=utc(2026, 8, 13, 9), tags=["冷链", "数据"],
        content="试运行数据采集完成，正在分析温度稳定性指标", importance=0.85),
    mem(memory_id="mem_t08", user_id="user_001", memory_scope="task", memory_type="process", task_id="task_102", scene_id="customer_service", created_at=utc(2026, 8, 13, 11), tags=["决策"],
        content="决定保留双温区冷箱方案，配合实时温度上报", importance=0.8),
    mem(memory_id="mem_t09", user_id="user_001", memory_scope="task", memory_type="task_state", task_id="task_103", scene_id="memory-console", created_at=utc(2026, 8, 8, 9), tags=["性能", "目标"],
        content="任务目标：优化前端控制台首屏加载与图表体积", importance=0.85),
    mem(memory_id="mem_t10", user_id="user_001", memory_scope="task", memory_type="process", task_id="task_103", scene_id="memory-console", created_at=utc(2026, 8, 11, 16), tags=["性能"],
        content="已完成图表按需引入与路由懒加载改造，构建体积下降约25%", importance=0.85),
    mem(memory_id="mem_t11", user_id="user_001", memory_scope="task", memory_type="process", task_id="task_103", scene_id="memory-console", created_at=utc(2026, 8, 11, 17), tags=["决策"],
        content="确定保留 @ant-design/plots 惰性加载方案，不引入额外图库", importance=0.8),
    mem(memory_id="mem_t12", user_id="user_001", memory_scope="task", memory_type="task_state", task_id="task_104", scene_id="memory-console", created_at=utc(2026, 8, 12, 9), tags=["画像", "目标"],
        content="任务目标：梳理客户方关键角色与决策链路，形成画像文档", importance=0.8),
    mem(memory_id="mem_t13", user_id="user_001", memory_scope="task", memory_type="process", task_id="task_104", scene_id="memory-console", created_at=utc(2026, 8, 13, 10), tags=["画像"],
        content="已收集基础访谈记录，待整理结构化画像", importance=0.75),
]

USER_001_SCOPE_AGENT = [
    mem(memory_id="mem_a01", user_id="user_001", memory_scope="agent", memory_type="fact", agent_id="agent_cs_001", scene_id="customer_service", created_at=utc(2026, 8, 8, 10), tags=["能力"],
        content="智能体能力：客服助手支持退货退款、物流查询、工单转派三类流程", importance=0.85),
    mem(memory_id="mem_a02", user_id="user_001", memory_scope="agent", memory_type="process", agent_id="agent_cs_001", scene_id="customer_service", created_at=utc(2026, 8, 9, 11), tags=["经验"],
        content="智能体经验：遇冷链异常时先核验温度记录再答复，避免误判", importance=0.85),
    mem(memory_id="mem_a03", user_id="user_001", memory_scope="agent", memory_type="fact", agent_id="agent_cs_001", scene_id="customer_service", created_at=utc(2026, 8, 10, 10), tags=["边界"],
        content="智能体边界：客服助手不处理账户余额查询，需转人工", importance=0.8),
    mem(memory_id="mem_a04", user_id="user_001", memory_scope="agent", memory_type="fact", agent_id="agent_cs_001", scene_id="customer_service", created_at=utc(2026, 8, 11, 9), tags=["约束"],
        content="智能体约束：答复需附真实数据来源，禁止编造物流信息", importance=0.9),
]

USER_002 = [
    mem(memory_id="mem_2u01", user_id="user_002", memory_scope="user", memory_type="fact", scene_id="customer_service", created_at=utc(2026, 8, 10, 10), tags=["售后"],
        content="用户李四负责售后工单，关注退货率指标", importance=0.8),
    mem(memory_id="mem_2u02", user_id="user_002", memory_scope="user", memory_type="preference", scene_id="customer_service", created_at=utc(2026, 8, 11, 11), tags=["汇报风格"],
        content="用户偏好表格化汇报，倾向数据支撑的结论", importance=0.8),
    mem(memory_id="mem_2s01", user_id="user_002", memory_scope="session", memory_type="fact", session_id="sess_2001", scene_id="customer_service", created_at=utc(2026, 8, 11, 11), tags=["售后"],
        content="会话概要：讨论售后工单流转效率，建议自动化初审", importance=0.8),
    mem(memory_id="mem_2t01", user_id="user_002", memory_scope="task", memory_type="task_state", task_id="task_201", scene_id="customer_service", created_at=utc(2026, 8, 12, 10), tags=["工单", "目标"],
        content="任务目标：跟进售后工单自动化初审改造", importance=0.8),
]

ALL_MEMORIES = (
    USER_001_SCOPE_USER + USER_001_SCOPE_SESSION + USER_001_SCOPE_TASK + USER_001_SCOPE_AGENT + USER_002
)

# 记忆关联（补充 / 冲突 / 继承），供管理端记忆详情展示
RELATIONS = [
    dict(source="mem_u14", target="mem_t05", relation_type="conflicts_with",
         description="调度偏好更正：温度稳定优先，替代『最快到达』口径", confidence=0.9),
    dict(source="mem_s09", target="mem_s10", relation_type="supplements",
         description="性能优化决策补充了当前进行中的任务状态", confidence=0.8),
    dict(source="mem_u08", target="mem_s11", relation_type="supplements",
         description="技术栈事实与会话选型结论相互印证", confidence=0.85),
]

# ============================================================
# 4. 检索日志（喂首页看板 / 监控页「联调记录」）
# ============================================================

RETRIEVAL_LOGS = [
    ("退货退款流程", "hybrid", utc(2026, 8, 7, 10, 5)),
    ("冷链配送温度", "semantic", utc(2026, 8, 9, 14, 20)),
    ("物流异常反馈", "hybrid", utc(2026, 8, 10, 9, 15)),
    ("React 技术栈", "keyword", utc(2026, 8, 11, 9, 30)),
    ("图表体积优化", "semantic", utc(2026, 8, 12, 10, 5)),
    ("订单退款进度", "hybrid", utc(2026, 8, 12, 15, 40)),
    ("冷链承运商对比", "rerank", utc(2026, 8, 13, 9, 10)),
    ("用户画像偏好", "hybrid", utc(2026, 8, 13, 11, 20)),
    ("售后工单流转", "keyword", utc(2026, 8, 13, 13, 0)),
]


# ============================================================
# 5. 执行
# ============================================================

async def clear_demo(db: AsyncSession) -> None:
    """清空本脚本创建的演示数据（幂等）。"""
    from sqlalchemy import bindparam

    await db.execute(text("DELETE FROM t_memory_relation WHERE source_memory_id LIKE 'mem_%'"))
    await db.execute(text("DELETE FROM t_memory WHERE user_id IN :users").bindparams(bindparam("users", expanding=True)),
                     {"users": list(DEMO_USERS)})
    await db.execute(text("DELETE FROM t_retrieval_result WHERE request_id LIKE 'demo_%'"))
    await db.execute(text("DELETE FROM t_retrieval_request WHERE request_id LIKE 'demo_%'"))
    await db.execute(text("DELETE FROM t_task WHERE user_id IN :users").bindparams(bindparam("users", expanding=True)),
                     {"users": list(DEMO_USERS)})
    await db.execute(text("DELETE FROM t_session WHERE user_id IN :users").bindparams(bindparam("users", expanding=True)),
                     {"users": list(DEMO_USERS)})
    await db.execute(text("DELETE FROM t_agent WHERE agent_id IN :agents").bindparams(bindparam("agents", expanding=True)),
                     {"agents": [a["agent_id"] for a in AGENTS]})
    await db.execute(text("DELETE FROM t_user WHERE user_id IN :users").bindparams(bindparam("users", expanding=True)),
                     {"users": list(DEMO_USERS)})
    await db.execute(text("DELETE FROM t_scene WHERE scene_id IN :scenes").bindparams(bindparam("scenes", expanding=True)),
                     {"scenes": [s["scene_id"] for s in SCENES]})
    await db.commit()


async def main() -> None:
    async with async_session_factory() as db:
        await clear_demo(db)

        for row in SCENES:
            db.add(Scene(scene_id=row["scene_id"], scene_name=row["scene_name"], description=row["description"]))
        for row in USERS:
            db.add(User(user_id=row["user_id"], name=row["name"]))
        for row in AGENTS:
            db.add(Agent(agent_id=row["agent_id"], agent_name=row["agent_name"], scene_id=row["scene_id"],
                         api_key_hash="demo", api_key_prefix="mem_demo**", is_active=True, permissions=row["permissions"]))

        for row in SESSIONS:
            db.add(Session(
                session_id=row["session_id"], user_id=row["user_id"], agent_id=row["agent_id"],
                scene_id=row["scene_id"], task_id=row["task_id"], status=row["status"],
                started_at=row["started_at"], ended_at=row.get("ended_at"),
                message_count=row["message_count"],
            ))
        for row in TASKS:
            db.add(Task(
                task_id=row["task_id"], user_id=row["user_id"], agent_id=row["agent_id"],
                scene_id=row["scene_id"], session_id=row["session_id"], title=row["title"], goal=row["goal"],
                status=row["status"], progress=row["progress"],
                completed_items=row["completed_items"], pending_items=row["pending_items"],
                started_at=row["started_at"], ended_at=row.get("ended_at"),
            ))

        for row in ALL_MEMORIES:
            db.add(Memory(
                memory_id=row["memory_id"], user_id=row["user_id"],
                agent_id=row.get("agent_id"), scene_id=row.get("scene_id"),
                session_id=row.get("session_id"), task_id=row.get("task_id"),
                content=row["content"], summary=row["content"][:40],
                key_points=[], memory_type=row["memory_type"], tags=row["tags"],
                entities=[], status=row["status"], importance=row["importance"],
                confidence=row["confidence"], memory_scope=row["memory_scope"],
                source_type="manual_seed", source_record_ids=[],
                created_at=row["created_at"], updated_at=row["created_at"],
            ))

        for row in RELATIONS:
            db.add(MemoryRelation(
                source_memory_id=row["source"], target_memory_id=row["target"],
                relation_type=row["relation_type"], description=row["description"],
                confidence=row["confidence"], created_at=now(),
            ))

        memory_id_by_keyword = {
            "退货退款": "mem_s01", "冷链": "mem_s03", "物流": "mem_s05", "React": "mem_u08",
            "图表": "mem_s08", "退款": "mem_t03", "承运商": "mem_t06", "画像": "mem_t13", "工单": "mem_2u01",
        }
        for query, mode, ts in RETRIEVAL_LOGS:
            request_id = f"demo_retr_{uuid4().hex[:12]}"
            db.add(RetrievalRequest(
                request_id=request_id, agent_id="agent_cs_001", user_id="user_001",
                scene_id="customer_service", query_text=query, filter_conditions={"memory_types": []},
                top_k=10, is_triggered=True, retrieval_mode=mode, created_at=ts,
            ))
            # 首位结果关联一条真实记忆，让看板「最近检索」可溯源
            target = next((mid for kw, mid in memory_id_by_keyword.items() if kw in query), "mem_s01")
            db.add(RetrievalResult(
                request_id=request_id, memory_id=target, rank=0,
                relevance_score=round(0.72 + (abs(hash(query)) % 25) / 100, 4), created_at=ts,
            ))

        await db.commit()
        print("[OK] seed done: %d memories, %d sessions, %d tasks, %d agents, %d retrieval logs" % (
            len(ALL_MEMORIES), len(SESSIONS), len(TASKS), len(AGENTS), len(RETRIEVAL_LOGS)))


if __name__ == "__main__":
    asyncio.run(main())
