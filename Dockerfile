FROM ghcr.io/astral-sh/uv AS uv
FROM python:3.9

ENV PYTHON_UNBUFFERED=1
ENV PYTHONFAULTHANDLER=1
ENV PYTHONHASHSEED=1
ENV UV_NO_SYNC=1

WORKDIR /src
COPY --from=uv /uv /usr/bin/uv
COPY uv.lock pyproject.toml /src/
RUN uv sync --frozen --no-dev
ADD . /src

RUN useradd -m user
USER user
