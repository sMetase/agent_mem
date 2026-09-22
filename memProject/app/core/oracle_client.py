# -*- coding: utf-8 -*-
"""
Oracle 26ai AI Vector Search 客户端 — 向量 + 关键词检索统一在 t_memory「同表」完成。

替代原 Oracle 26ai（dense 向量）+ Oracle 26ai sparse BM25 方案：
- 语义检索：t_memory.embedding 使用 Oracle VECTOR 类型，VECTOR_DISTANCE 计算余弦相似度
- 关键词检索：jieba 分词 → INSTR(content) 多候选 + 命中数排序（不依赖 Oracle Text 词法分析器，中文友好）
- 向量写入：以 memory_id 为唯一键，UPDATE t_memory.embedding（同表，无需桥接表）

依赖 python-oracledb（thin 模式），连接 Oracle 26ai Free 的 FREEPDB1（用户 DEVUSER）。
"""
import array
from typing import Optional

import jieba

try:
    import oracledb
except ImportError as exc:  # pragma: no cover - dependency guard
    raise ImportError('Oracle 26ai 向量检索需要安装依赖: pip install oracledb') from exc

from app.core.config import get_settings
from app.core.exceptions import VectorStoreError
from app.core.logger import get_logger

logger = get_logger('oracle_client')

EMBEDDING_DIM = 1024            # bge-m3 维度（与 embedding_client 一致）
DISTANCE_METRIC = 'COSINE'
DEFAULT_SCORE_THRESHOLD = 0.5

# 允许作为筛选条件的 t_memory 真实列（白名单，防注入）
_FILTERABLE_COLUMNS = {'user_id', 'agent_id', 'scene_id', 'task_id', 'session_id', 'memory_type'}


def _dsn(settings) -> str:
    """Oracle 连接串 host:port/service_name。"""
    db = settings.database
    service = db.service or db.database
    return f'{db.host}:{db.port}/{service}'


def _rows_to_result(rows: list) -> list[dict]:
    """把 Oracle 原始行转成 {id, score, payload} 统一结构。"""
    return [
        {
            'id': row[0],
            'score': round(max(0.0, min(1.0, float(row[1]))), 6),
            'payload': {'memory_id': row[0]},
        }
        for row in rows
    ]


def _build_memory_filters(user_id, payload_filters, params) -> list[str]:
    """构造 t_memory 筛选条件（user_id + 可过滤列白名单）。"""
    where = ['user_id = :u', "status = 'active'"]
    if payload_filters:
        for key, value in payload_filters.items():
            if key in _FILTERABLE_COLUMNS and value:
                where.append(f'{key} = :f_{key}')
                params[f'f_{key}'] = value
    return where


def _tokenize(text: str) -> list[str]:
    """jieba 分词出关键词（过滤空白/单字符，用于 INSTR 关键词检索）。"""
    if not text:
        return []
    import re
    try:
        words = [w.strip() for w in jieba.cut(text)]
    except Exception:
        words = re.split(r'[\s,，。．.、!！?？;；:：]+', text)
    seen: list[str] = []
    for w in words:
        if not w:
            continue
        if len(w) <= 1:
            continue
        if w not in seen:
            seen.append(w)
    return seen


class OracleVectorStore:
    """
    Oracle AI Vector Search 客户端单例 — 替代 Oracle 26ai 完成记忆去重/检索的向量能力。

    面向 t_memory「同表」方案：search_similar / search_keyword / upsert_vectors /
    delete_vectors 与旧 qdrant_client 接口保持一致，上层可直接替换。
    """

    def __init__(self) -> None:
        self._pool: Optional[oracledb.ConnectionPool] = None
        self._config = get_settings()

    def close(self) -> None:
        if self._pool is not None:
            try:
                self._pool.close()
            except Exception as e:
                logger.warning(f'Oracle pool close failed (non-fatal): {e}')
            self._pool = None

    def _get_pool(self) -> oracledb.ConnectionPool:
        if self._pool is None:
            db = self._config.database
            self._pool = oracledb.create_pool(
                user=db.user,
                password=db.password,
                dsn=_dsn(self._config),
                min=1,
                max=4,
                getmode=oracledb.POOL_GETMODE_WAIT,
            )
        return self._pool

    @property
    def is_available(self) -> bool:
        """校验 Oracle 连通性（SELECT 1 FROM dual）。"""
        try:
            with self._get_pool().acquire() as conn, conn.cursor() as cursor:
                cursor.execute('SELECT 1 FROM dual')
                cursor.fetchone()
            return True
        except Exception as e:
            logger.warning(f'Oracle unavailable: {e}')
            return False

    @property
    def collection_name(self) -> str:
        """兼容旧属性：Oracle 同表方案下指 memory 主表。"""
        return 't_memory'

    def search_similar(
        self,
        query_vector: list[float],
        user_id: str,
        top_k: int = 5,
        score_threshold: float = DEFAULT_SCORE_THRESHOLD,
        payload_filters: dict | None = None,
    ) -> list[dict]:
        """语义检索：t_memory.embedding 与查询向量做 COSINE 距离排序，返回 Top-K。"""
        params = {'q': array.array('f', query_vector), 'u': user_id, 'k': int(top_k)}
        where = ['embedding IS NOT NULL'] + _build_memory_filters(user_id, payload_filters, params)
        if score_threshold is not None:
            dist_threshold = 1.0 - float(score_threshold)
            where.append('VECTOR_DISTANCE(embedding, :q, COSINE) <= :thr')
            params['thr'] = dist_threshold

        sql = (
            'SELECT memory_id, VECTOR_DISTANCE(embedding, :q, COSINE) AS d '
            f"FROM t_memory WHERE {' AND '.join(where)} "
            'ORDER BY d FETCH FIRST :k ROWS ONLY'
        )
        try:
            with self._get_pool().acquire() as conn, conn.cursor() as cursor:
                cursor.execute(sql, params)
                rows = cursor.fetchall()
        except Exception as e:
            logger.error(f'Oracle search_similar failed: {e}')
            raise VectorStoreError(f'Oracle 语义检索失败: {str(e)}')

        results = _rows_to_result(rows)
        logger.info(f'Oracle semantic search: user={user_id}, top_k={top_k}, found={len(results)}')
        return results

    def search_keyword(
        self,
        query_text: str,
        user_id: str,
        top_k: int = 5,
        payload_filters: dict | None = None,
    ) -> list[dict]:
        """
        关键词检索：jieba 分词 → INSTR(content) 多候选命中，按命中词数排序。

        说明：Oracle Text 默认词法分析器对中文分不了词（CONTAINS 中文命中率低），
        因此这里改用 jieba 分词 + INSTR 子串匹配，中文友好的同时不依赖 Oracle Text 全文本。
        """
        tokens = _tokenize(query_text)
        if not tokens:
            return []

        params = {'u': user_id, 'k': int(top_k)}
        where = ['user_id = :u', "status = 'active'"]
        for i, tok in enumerate(tokens):
            where.append(f'INSTR(content, :t{i}) > 0')
            params[f't{i}'] = tok
        base_filters = _build_memory_filters(user_id, payload_filters, params)
        for clause in base_filters:
            if clause not in where:
                where.append(clause)

        # 命中词数作为相关系数（CASE 累加），同时保留 INSTR 过滤条件
        score_case = ' + '.join(f"(CASE WHEN INSTR(content, :t{i}) > 0 THEN 1 ELSE 0 END)" for i in range(len(tokens)))
        sql = (
            f'SELECT memory_id, ({score_case}) AS matched '
            'FROM t_memory WHERE '
            + ' AND '.join(where)
            + ' ORDER BY matched DESC FETCH FIRST :k ROWS ONLY'
        )
        try:
            with self._get_pool().acquire() as conn, conn.cursor() as cursor:
                cursor.execute(sql, params)
                rows = cursor.fetchall()
        except Exception as e:
            logger.error(f'Oracle search_keyword failed: {e}')
            raise VectorStoreError(f'Oracle 关键词检索失败: {str(e)}')

        total = len(tokens)
        results = [
            {
                'id': row[0],
                'score': round(max(0.0, min(1.0, float(row[1]) / max(1, total))), 6),
                'payload': {'memory_id': row[0]},
            }
            for row in rows
        ]
        logger.info(f'Oracle keyword search: user={user_id}, top_k={top_k}, found={len(results)}')
        return results

    def upsert_vectors(
        self,
        vectors: list[list[float]],
        payloads: list[dict],
        ids: list[str],
        sparse_vectors: list[dict] | None = None,
    ) -> None:
        """批量写入/更新向量 — Oracle 同表：以 memory_id 定位 UPDATE t_memory.embedding。"""
        if len(vectors) != len(payloads) or len(vectors) != len(ids):
            raise ValueError('vectors, payloads, ids 长度必须一致')
        try:
            with self._get_pool().acquire() as conn, conn.cursor() as cursor:
                cursor.setinputsizes(v=oracledb.DB_TYPE_VECTOR)
                for i, mid in enumerate(ids):
                    cursor.execute(
                        'UPDATE t_memory SET embedding = :v WHERE memory_id = :mid',
                        v=array.array('f', vectors[i]),
                        mid=mid,
                    )
                conn.commit()  # Oracle 默认非自动提交；不 commit 其他连接读不到，检索会 0 命中
        except Exception as e:
            logger.error(f'Oracle upsert failed: {e}')
            raise VectorStoreError(f'Oracle 向量写入失败: {str(e)}')
        logger.info(f'Oracle upsert: {len(ids)} vectors')

    def upsert_single(self, point_id: str, vector: list[float], payload: dict) -> None:
        """写入/更新单条向量。"""
        self.upsert_vectors([vector], [payload], [point_id])

    def update_payload(self, point_id: str, payload: dict) -> None:
        """
        同表方案下 payload 即 t_memory 真实列，无需单独更新；
        保留此方法仅为兼容旧接口（幂等 no-op + 尽量更新可映射列）。
        """
        try:
            settable = {k: v for k, v in payload.items() if k in _FILTERABLE_COLUMNS and v}
            if not settable:
                return
            set_clause = ', '.join(f'{k} = :{k}' for k in settable)
            settable['point_id'] = point_id
            with self._get_pool().acquire() as conn, conn.cursor() as cursor:
                cursor.execute(
                    f'UPDATE t_memory SET {set_clause} WHERE memory_id = :point_id',
                    settable,
                )
                conn.commit()
        except Exception as e:
            logger.warning(f'Oracle update_payload failed (non-fatal): {e}')

    def delete_vectors(self, ids: list[str]) -> None:
        """
        删除向量 — 同表软删除语义：将 embedding 置 NULL（行保留，供状态/审计/历史使用）。
        若后续要物理清理，可改为 DELETE，但当前上层以软删除为准。
        """
        try:
            with self._get_pool().acquire() as conn, conn.cursor() as cursor:
                for mid in ids:
                    cursor.execute(
                        'UPDATE t_memory SET embedding = NULL WHERE memory_id = :mid',
                        mid=mid,
                    )
                conn.commit()
            logger.info(f'Oracle delete_vectors: {len(ids)} vectors')
        except Exception as e:
            logger.warning(f'Oracle delete_vectors failed (non-fatal): {e}')


# 模块级单例
oracle_vector_store = OracleVectorStore()
