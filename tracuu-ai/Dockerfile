# Giai đoạn 1: build giao diện
FROM node:22-slim AS web
WORKDIR /web
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html vite.config.js ./
COPY src ./src
RUN npm run build

# Giai đoạn 2: Flask + gunicorn (gevent cho kết nối SSE dài)
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 BACKEND=aws AUTH_MODE=alb STATIC_DIR=/srv/dist
WORKDIR /srv
COPY requirements.txt requirements-prod.txt ./
RUN pip install --no-cache-dir -r requirements-prod.txt
COPY app ./app
COPY --from=web /web/dist ./dist
RUN useradd --system --no-create-home app
USER app
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/healthz')"
CMD ["gunicorn", "-k", "gevent", "-w", "2", "--worker-connections", "200", "--timeout", "120", "-b", "0.0.0.0:8000", "app:create_app()"]
