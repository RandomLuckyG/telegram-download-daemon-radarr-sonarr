FROM python:3.12 AS compile-image

RUN pip install --no-cache-dir telethon cryptg pysocks

FROM python:3.12 AS run-image

COPY --from=compile-image /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages

WORKDIR /app
COPY *.py ./
RUN chmod 777 /app/*.py

CMD [ "python3", "./telegram-download-daemon.py" ]
