FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml ./
RUN uv pip install --system flask apscheduler requests
COPY app ./app
COPY start.sh ./start.sh
RUN chmod +x start.sh
ENV HOST=0.0.0.0 PORT=5000 STOCKTRACE_DATA_DIR=/app/data
VOLUME ["/app/data"]
EXPOSE 5000
CMD ["./start.sh"]
