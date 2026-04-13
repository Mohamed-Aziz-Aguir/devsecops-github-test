FROM python:3.11-slim

WORKDIR /app

# install dependencies
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# copy application
COPY app/ app/

# run user
WORKDIR /app/app

EXPOSE 5000

CMD ["python", "app.py"]
