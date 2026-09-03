FROM harbor.goertek.com/g-eam/python:3.12-slim

LABEL org.opencontainers.image.name="mem0/openmemory-mcp"

WORKDIR /usr/src/openmemory

COPY requirements.txt .
# RUN pip config set global.index-url http://10.10.41.127:8081/repository/pypi-group/simple && pip config set global.trusted-host 10.10.41.127
RUN pip install -r requirements.txt

COPY config.json .
COPY . .

EXPOSE 8765
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8765"]
