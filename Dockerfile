
FROM python:3.11

WORKDIR /usr/src/app

COPY pyproject.toml ./
RUN pip install --no-cache-dir .[test,dev]

RUN mkdir .pytest_cache && chown 1000:1000 .pytest_cache

COPY . .

USER 1000:1000
CMD [ "python", "./src/driver.py" ]

