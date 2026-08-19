# -*- coding: utf-8 -*-
"""
关键词检索的稀疏向量编码 — jieba 分词 + 词频（TF）。

Qdrant 的 SparseVectorParams(modifier=IDF) 会在检索时自动做 IDF 加权，
所以这里只需生成「词 → 词频」的稀疏向量，不需要自己实现完整 BM25。
"""

import hashlib

import jieba


def _word_to_id(word: str) -> int:
    """词 → uint32 稳定 hash（md5 前 8 位，避免 Python 内置 hash 的随机化）。"""
    return int(hashlib.md5(word.encode("utf-8")).hexdigest()[:8], 16)


def text_to_sparse(text: str) -> dict[int, float]:
    """文本 → 稀疏向量 {词ID: 词频}。"""
    words = [w for w in jieba.lcut(text) if w.strip()]
    tf: dict[str, int] = {}
    for w in words:
        tf[w] = tf.get(w, 0) + 1
    return {_word_to_id(w): float(c) for w, c in tf.items()}
