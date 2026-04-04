# ---- ビルドステージ ----
FROM python:3.12-slim AS builder

WORKDIR /build

COPY requirements-web.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements-web.txt

# ---- 実行ステージ ----
FROM python:3.12-slim

LABEL org.opencontainers.image.title="3lvlpwm-simulator" \
      org.opencontainers.image.description="Three-phase PWM inverter learning simulator" \
      org.opencontainers.image.version="phase5-v1"

# セキュリティ: 非 root ユーザで実行
RUN useradd --system --create-home --uid 1001 appuser

WORKDIR /app

# ビルドステージで取得した依存パッケージをコピー
COPY --from=builder /install /usr/local

# アプリケーションコードのみコピー（ui/ tests/ docs/ は Docker 実行に不要）
COPY simulation/ simulation/
COPY application/ application/
COPY webapi/ webapi/
COPY webui/ webui/

RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# --workers 1: シングルプロセス（学習用少人数想定）
#   複数同時利用時は --workers を増やすか Gunicorn に切り替えること
# --no-access-log: コンテナログ軽量化
#   障害調査時はこのオプションを削除して再ビルドすること
CMD ["python", "-m", "uvicorn", "webapi.app:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", "--no-access-log"]
