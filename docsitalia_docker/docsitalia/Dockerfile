# `docs_italia_it_base`: Base Image
# Image used as a common base for the multi stage process
# Not really used by any container

FROM python:3.6-slim AS docs_italia_it_base

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        git \
        libpq-dev \
        locales \
        wait-for-it \
        gettext \
        libgettextpo-dev \
    && rm -rf /var/lib/apt/lists/*

RUN sed -i -e 's/# \(en_US\.UTF-8 .*\)/\1/' -e 's/# \(it_IT\.UTF-8 .*\)/\1/'  /etc/locale.gen && \
    dpkg-reconfigure --frontend=noninteractive locales && \
    update-locale LANG=en_US.UTF-8

WORKDIR /app

# `docs_italia_it_test`: Test Image
# Used in `docker-compose-test`.
# As all the test will run in a tox virtualenv we need development libraries here
# We don't need code in this image as will be mounted the live one via the local
# volume

FROM docs_italia_it_base AS docs_italia_it_test

RUN pip install --no-cache-dir -U pip tox

CMD ["/bin/bash"]

# `docs_italia_it_build`:
# We need additional packages to build documentation in LocalBuildEnvironment

FROM docs_italia_it_base AS docs_italia_it_build

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        libarchive-tools \
        libjpeg62-turbo-dev \
        texlive \
        texlive-latex-extra \
        latexmk \
    && rm -rf /var/lib/apt/lists/*

ARG COMANDI_CONVERSIONE_URL=https://github.com/italia/docs-italia-comandi-conversione/releases/download/v0.6
ARG PANDOC_FILTERS_URL=https://github.com/italia/docs-italia-pandoc-filters/releases/download/v0.1.4

SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN curl -sSL ${COMANDI_CONVERSIONE_URL}/converti.zip | bsdtar -xf- -C /usr/local/bin \
    && curl -sSL ${COMANDI_CONVERSIONE_URL}/pandoc-font-to-style.zip | bsdtar -xf- -C /usr/local/bin \
    && curl -sSL ${COMANDI_CONVERSIONE_URL}/pandoc-to-sphinx.zip | bsdtar -xf- -C /usr/local/bin \
    && curl -sSL ${COMANDI_CONVERSIONE_URL}/pandoc.zip | bsdtar -xf- -C /usr/local/bin \
    && curl -sSL ${PANDOC_FILTERS_URL}/filtro-acronimi > /usr/local/bin/filtro-acronimi \
    && curl -sSL ${PANDOC_FILTERS_URL}/filtro-didascalia > /usr/local/bin/filtro-didascalia \
    && curl -sSL ${PANDOC_FILTERS_URL}/filtro-google-docs > /usr/local/bin/filtro-google-docs \
    && curl -sSL ${PANDOC_FILTERS_URL}/filtro-quotes > /usr/local/bin/filtro-quotes \
    && curl -sSL ${PANDOC_FILTERS_URL}/filtro-references > /usr/local/bin/filtro-references \
    && curl -sSL ${PANDOC_FILTERS_URL}/filtro-rimuovi-div > /usr/local/bin/filtro-rimuovi-div \
    && curl -sSL ${PANDOC_FILTERS_URL}/filturo-stile-liste > /usr/local/bin/filtro-stile-liste \
    && chmod 755 /usr/local/bin/converti /usr/local/bin/pandoc* /usr/local/bin/filtro-*

RUN pip install --no-cache-dir -U pip virtualenv

CMD ["/bin/bash"]

# `docs_italia_it_dev`: Final application Image
# Image for all the application containers (web, api, celery-docs, celery-web, celery-build)
# We don't need to copy the RTD code in this image as will be mounted the live
# one via the local volume. We only need to copy the files needed inside the
# container (utility shell scripts and requirements)

FROM docs_italia_it_build AS docs_italia_it_dev

COPY requirements/ /app/requirements/
RUN pip install --no-cache-dir -r /app/requirements/docsitalia.txt
COPY docsitalia_docker/ /app/docker/

ENV DJANGO_SETTINGS_MODULE=readthedocs.docsitalia.settings.docker

CMD ["/bin/bash"]

# `docs_italia_it_web_prod`: Production image for Application
# Copies the application code inside the container

FROM docs_italia_it_dev AS docs_italia_it_prod

COPY readthedocs/ /app/readthedocs/
COPY media/ /app/media/
COPY logs/ /app/logs/
COPY manage.py setup* *.json /app/

CMD ["/bin/bash"]
