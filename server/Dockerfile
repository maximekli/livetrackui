FROM node:22-bookworm AS electron-build
WORKDIR /opt/livetrackui/electron
COPY electron/package*.json ./
RUN npm ci
COPY electron/ ./
RUN npm run package:linux

FROM python:3.13-slim-bookworm
WORKDIR /opt/livetrackui
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates libnss3 libatk-bridge2.0-0 libdrm2 libxkbcommon0 libgbm1 libgtk-3-0 libasound2 \
    && rm -rf /var/lib/apt/lists/*

COPY server/requirements.txt ./server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt \
    && playwright install chromium

COPY server/app ./server/app
COPY --from=electron-build /opt/livetrackui/electron/dist ./electron/dist

VOLUME ["/data"]
EXPOSE 8000
CMD ["uvicorn", "server.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
