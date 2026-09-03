FROM python:3.12-slim

WORKDIR /app

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY requirements.txt .

# RUN pip config set global.index-url http://10.10.41.127:8081/repository/pypi-group/simple && pip config set global.trusted-host 10.10.41.127
RUN pip install --no-cache-dir -r requirements.txt

# 应用代码
COPY . .

# 非 root 运行
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000 9090

CMD ["sh", "-c", "python -m alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1"]
