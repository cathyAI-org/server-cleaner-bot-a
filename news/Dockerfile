FROM catcord-bots-framework:latest

ENV PYTHONUNBUFFERED=1

WORKDIR /app
COPY __init__.py /app/news/__init__.py
COPY main.py /app/news/main.py
COPY format.py /app/news/format.py
COPY state.py /app/news/state.py

ENTRYPOINT ["python", "-u", "-m", "news.main"]
