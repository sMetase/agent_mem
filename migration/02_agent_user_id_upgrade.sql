-- ============================================================================
-- Oracle 26ai 记忆系统 —— 增量升级 SQL（本轮修复: t_agent 增加 user_id 归属列）
--
-- 与 migration/upgrade_agent_ownership.sh 等价（供 DBA / sqlplus 手动执行或存档）。
-- 目标用户: DEVUSER（脚本默认以应用用户连接，直接操作自己的 schema）
--
-- 幂等 / 零数据丢失:
--   - 加列(ADD) + 建索引(CREATE INDEX) + 回填(UPDATE ... WHERE user_id IS NULL)
--   - 不 DROP、不 TRUNCATE、不改已有值；重复执行安全
--   - 回填语义与后端 bootstrap 一致: t_agent.user_id = 其场景 t_scene.user_id;
--     无主/无场景的智能体保持 NULL，由列表查询「场景归属兜底」保证仍可见
--
-- 执行: sqlplus DEVUSER/密码@host:1521/FREEPDB1 @02_agent_user_id_upgrade.sql
-- ============================================================================

SET SERVEROUTPUT ON
SET FEEDBACK OFF

DECLARE
  cnt NUMBER;
  upd NUMBER;
BEGIN
  -- 1) 加列（幂等）
  SELECT COUNT(*) INTO cnt FROM user_tab_columns
   WHERE table_name='T_AGENT' AND column_name='USER_ID';
  IF cnt = 0 THEN
    EXECUTE IMMEDIATE 'ALTER TABLE t_agent ADD (user_id VARCHAR2(128))';
    DBMS_OUTPUT.PUT_LINE('[1/3] 已新增列 t_agent.user_id VARCHAR2(128)');
  ELSE
    DBMS_OUTPUT.PUT_LINE('[1/3] 列 t_agent.user_id 已存在, 跳过');
  END IF;

  -- 2) 建索引（幂等）
  SELECT COUNT(*) INTO cnt FROM user_indexes WHERE index_name='IX_T_AGENT_USER_ID';
  IF cnt = 0 THEN
    EXECUTE IMMEDIATE 'CREATE INDEX ix_t_agent_user_id ON t_agent(user_id)';
    DBMS_OUTPUT.PUT_LINE('[2/3] 已创建索引 ix_t_agent_user_id');
  ELSE
    DBMS_OUTPUT.PUT_LINE('[2/3] 索引 ix_t_agent_user_id 已存在, 跳过');
  END IF;

  -- 3) 回填（幂等; 仅补 user_id 为空的智能体, 已有值不动）
  UPDATE t_agent a
     SET a.user_id = (SELECT s.user_id FROM t_scene s WHERE s.scene_id = a.scene_id)
   WHERE a.user_id IS NULL;
  upd := SQL%ROWCOUNT;
  COMMIT;
  DBMS_OUTPUT.PUT_LINE('[3/3] 回填完成: 本次更新 ' || upd || ' 条');
END;
/

-- 校验
SELECT COUNT(*) AS total_agents,
       COUNT(user_id) AS owned_agents,
       COUNT(*) - COUNT(user_id) AS null_user_id
  FROM t_agent;

EXIT;
