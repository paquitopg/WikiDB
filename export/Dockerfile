# Word and PowerPoint export service (U14, KTD17). Built from the repository root:
#   docker build -f export/Dockerfile .
# Nubonyxia's Forge project rebuilds it FROM this image's digest plus the ministry CA, like the wiki image.
FROM python:3.13-slim@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml ./
COPY tools ./tools
RUN pip install --no-cache-dir ".[export]" && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin export

USER 10001
EXPOSE 8000
CMD ["uvicorn", "wikidb.export.server:app", "--host", "0.0.0.0", "--port", "8000"]
