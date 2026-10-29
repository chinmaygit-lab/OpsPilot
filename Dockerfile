FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY opspilot ./opspilot
RUN pip install --no-cache-dir .
RUN useradd --create-home opspilot && mkdir -p /app/data && chown -R opspilot:opspilot /app/data
USER opspilot
EXPOSE 8000
CMD ["uvicorn","opspilot.api:app","--host","0.0.0.0","--port","8000"]
