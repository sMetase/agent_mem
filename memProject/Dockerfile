FROM python:3.12-slim-bookworm

WORKDIR /app

# 系统依赖已由 scripts/prepare-offline-debs.sh 下载到构建上下文。
COPY offline-debs/ /tmp/offline-debs/
RUN set -eux; \
    test -n "$(find /tmp/offline-debs -maxdepth 1 -name '*.deb' -print -quit)"; \
    dpkg --unpack /tmp/offline-debs/*.deb; \
    dpkg --configure -a; \
    rm -rf /tmp/offline-debs

# Python 依赖
COPY requirements.txt .

RUN pip config set global.index-url http://10.10.41.127:8081/repository/pypi-group/simple && pip config set global.trusted-host 10.10.41.127
RUN pip install --no-cache-dir -r requirements.txt

# 应用代码
COPY . .

# 非 root 运行
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000 9090

CMD ["sh", "-c", "python -m alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1"]
