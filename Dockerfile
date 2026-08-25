FROM apify/actor-python:3.12

WORKDIR /usr/src/app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

ENV PYTHONUNBUFFERED=1

COPY . ./

CMD ["python", "-u", "src/main.py"]
