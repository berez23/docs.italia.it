"""Github related utils."""

from __future__ import absolute_import

from urllib.parse import urlparse

import requests
from django.utils.encoding import force_text
from django.utils.translation import ugettext_lazy as _

from readthedocs.docsitalia.metadata import (
    SETTINGS_VALIDATORS, DOCUMENT_SETTINGS, InvalidMetadata
)


RAW_GITHUB_BASE_URL = (
    'https://raw.githubusercontent.com/{org}/{repo}/master/{path}'
)


def get_metadata_from_url(url, session=None):
    """Gets an url via a requests compatible api."""
    if not session:
        session = requests
    response = session.get(url)
    return response.text


def parse_metadata(data, org, model, settings):
    """parse metadata for a specific settings file."""
    if not data:
        msg = _('no {} metadata for {}'.format(settings, model))
        raise InvalidMetadata(msg)

    validator = SETTINGS_VALIDATORS[settings]
    try:
        metadata = validator(org=org, settings=data, model=model)
    except ValueError as error:
        msg = _('invalid {} metadata for {} - {}'.format(
            settings, model, force_text(error)))
        raise InvalidMetadata(msg)

    return metadata


def get_metadata_for_publisher(org, publisher, settings, session=None):
    """Fetch and validate publisher metadata for a specific settings file."""
    url = RAW_GITHUB_BASE_URL.format(
        org=org.slug,
        repo=publisher.config_repo_name,
        path=settings)
    data = get_metadata_from_url(url, session=session)
    return parse_metadata(data, org, publisher, settings)


def get_metadata_for_document(document):
    """Fetch and validate document metadata."""
    # get the repo name
    repo_url = urlparse(document.repo)
    _, org, repo = repo_url.path.split('/')
    if repo.endswith('.git'):
        repo = repo[:-4]
    url = RAW_GITHUB_BASE_URL.format(
        org=org,
        repo=repo,
        path=DOCUMENT_SETTINGS)
    data = get_metadata_from_url(url)
    return parse_metadata(data, None, document, DOCUMENT_SETTINGS)
