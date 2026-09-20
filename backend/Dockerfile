FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings

WORKDIR /app/backend

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8010

CMD ["sh", "-c", "python manage.py wait_for_db && python manage.py migrate && python manage.py load_demo_data && python manage.py runserver 0.0.0.0:8010"]
