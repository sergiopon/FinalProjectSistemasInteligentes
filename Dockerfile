FROM python:3.12.14-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 HF_HOME=/opt/hf
WORKDIR /app
COPY requirements.txt ./
RUN pip install -r requirements.txt
COPY . .
RUN python -m ml.representations --download && chmod -R a+rX /opt/hf
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
USER 1000
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
