# Match the organizers' labeling image (Python 3.13 and pinned dependencies).
FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 SQLGLOT_BASE=/opt/sqlglot \
    PYTHONPATH=/app:/opt/sqlglot SKIP_INTEGRATION=0 HOME=/tmp
WORKDIR /app
COPY requirements.lock fetch_sqlglot.py /app/
RUN python fetch_sqlglot.py
# The exact upstream test dependencies, taken directly from official starter kit.
RUN pip install --no-cache-dir -r /app/requirements.lock
COPY main.py selector.py build_map.py coverage_plugin.py /app/
# Only base-revision test coverage and static source/test references are indexed.
RUN python build_map.py && chmod -R a+rX /app /opt/sqlglot
USER 65534:65534
CMD ["python", "/app/main.py"]
