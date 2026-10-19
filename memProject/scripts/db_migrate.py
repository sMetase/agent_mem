#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Alembic 迁移入口 —— 部署时由 backend 容器在启动前自动执行（幂等）。

schema 管理分工（后端 command 顺序: db_migrate → oracle_bootstrap → uvicorn）:
  - 本脚本（alembic）: 版本化增量迁移。
      * 已有 alembic 版本基线 → 执行 `upgrade head`，应用挂起迁移
        （例如本轮 t_agent.user_id 加列+索引+回填）；
      * 无版本基线（bootstrap/create_all 管理的存量库，或全新库）→ `stamp head`，
        因为 oracle_bootstrap 的 create_all + 幂等补丁步骤已保证 schema 与当前模型一致。
  - scripts/oracle_bootstrap.py: 基础 schema 同步（create_all + VECTOR 列/索引/序列/
    TIMESTAMP 升级），紧随其后运行，负责全新库建表与 Oracle 专属对象。

零数据丢失: 本脚本只维护 alembic_version 版本表 + 执行迁移文件本身（增量 ALTER/回填），
不 DROP、不 TRUNCATE、不改已有值；重复执行安全（版本已到 head 时直接 no-op）。

用法:
  python scripts/db_migrate.py          # 正常执行（幂等）
  python scripts/db_migrate.py --dry-run  # 只打印将走的分支，不修改库
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # memProject
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, text
from alembic.config import Config as AlembicConfig
from alembic import command as alembic_command

from app.core.config import get_settings

ALEMBIC_INI = ROOT / "alembic.ini"
ALEMBIC_DIR = ROOT / "alembic"


def _build_config() -> AlembicConfig:
    cfg = AlembicConfig(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(ALEMBIC_DIR))
    return cfg


def _current_version(engine) -> tuple[bool, str | None]:
    """返回 (是否已有版本表, 当前版本号 or None)。"""
    with engine.connect() as conn:
        has_table = conn.execute(text(
            "SELECT COUNT(*) FROM user_tables WHERE table_name = 'ALEMBIC_VERSION'"
        )).scalar() > 0
        if not has_table:
            return False, None
        row = conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
        return True, (row[0] if row else None)


def _print_ownership_check(settings) -> None:
    """本轮修复的归属升级校验（仅当表已存在时；全新库由 bootstrap 建表后自动具备）。"""
    try:
        eng = create_engine(settings.database.sync_url, pool_pre_ping=True)
        try:
            with eng.connect() as c:
                has_agent = c.execute(text(
                    "SELECT COUNT(*) FROM user_tables WHERE table_name = 'T_AGENT'"
                )).scalar() > 0
                if not has_agent:
                    print("[db_migrate] T_AGENT 尚不存在（全新库，将由 oracle_bootstrap 创建）")
                    return
                col = c.execute(text(
                    "SELECT COUNT(*) FROM user_tab_columns "
                    "WHERE table_name='T_AGENT' AND column_name='USER_ID'")).scalar()
                idx = c.execute(text(
                    "SELECT COUNT(*) FROM user_indexes WHERE index_name='IX_T_AGENT_USER_ID'")).scalar()
                total = c.execute(text("SELECT COUNT(*) FROM t_agent")).scalar()
                gap = c.execute(text(
                    """SELECT COUNT(*) FROM t_agent a
                        WHERE a.user_id IS NULL AND EXISTS (
                            SELECT 1 FROM t_scene s WHERE s.scene_id = a.scene_id AND s.user_id IS NOT NULL)"""
                )).scalar()
                print(f"[db_migrate] 归属校验: t_agent.user_id 列={'是' if col else '否'} "
                      f"索引={'有' if idx else '无'} (共 {total} 条, 待回填 {gap})")
        finally:
            eng.dispose()
    except Exception as e:  # pragma: no cover
        print(f"[db_migrate] 归属校验跳过: {str(e).splitlines()[0]}")


def main() -> int:
    dry_run = "--dry-run" in sys.argv[1:]
    settings = get_settings()
    engine = create_engine(settings.database.sync_url, pool_pre_ping=True)
    try:
        has_table, version = _current_version(engine)
        cfg = _build_config()

        if dry_run:
            branch = (
                f"upgrade head（当前版本 {version}）"
                if has_table and version
                else f"stamp head（无版本基线, has_table={has_table}, version={version!r}）"
            )
            print(f"[db_migrate][dry-run] 将执行分支: {branch}（未修改任何库）")
            return 0

        if not has_table or not version:
            # 无版本基线: bootstrap 管理的存量库或全新库 → 标记为当前。
            # create_all + 补丁步骤已保证 schema 与当前模型一致；后续增量迁移基于此版本逐步应用。
            print(f"[db_migrate] 未检测到 alembic 版本基线 (has_table={has_table}, version={version!r})，"
                  f"执行 stamp head（基础 schema 由 oracle_bootstrap 维护）")
            alembic_command.stamp(cfg, "head")
        else:
            print(f"[db_migrate] 当前 alembic 版本: {version}，执行 upgrade head")
            alembic_command.upgrade(cfg, "head")
    finally:
        engine.dispose()

    _print_ownership_check(settings)
    print("[db_migrate] 完成（零数据丢失、幂等、可重复执行）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
