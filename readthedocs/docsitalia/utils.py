# -*- coding: utf-8 -*-
"""Utils for the docsitalia app."""

from __future__ import absolute_import
from __future__ import unicode_literals

import yaml

# pylint: disable=redefined-builtin
from requests.exceptions import ConnectionError

from django.conf import settings

from readthedocs.builds.constants import LATEST, STABLE
from readthedocs.builds.models import Build
from readthedocs.projects.models import Project
from readthedocs.api.v2.client import api as apiv2


def load_yaml(txt):
    """Helper for yaml parsing."""
    try:
        return yaml.safe_load(txt)
    except yaml.YAMLError as exc:
        note = ''
        if hasattr(exc, 'problem_mark'):
            mark = exc.problem_mark
            note = ' (line %d, column %d)' % (mark.line + 1, mark.column + 1)
        raise ValueError(
            "The file could not be loaded, "
            "possibly due to a syntax error%s" % (
                note,))


def get_subprojects(project_pk):
    """
    Returns the list of subprojects from a project primary key by using the API.

    This makes it suitable for using in signals and wherever you don't have access to the
    project context

    :param project_pk:
    :return:
    """
    try:
        return (
            apiv2.project(project_pk)
            .subprojects()
            .get()['subprojects']
        )
    except ConnectionError:
        return []


def get_projects_with_builds(only_public=True):
    """Returns a queryset of Projects with active only public by default builds."""
    builds = Build.objects.filter(
        success=True,
        state='finished',
        version__active=True
    )
    if only_public:
        builds = builds.filter(version__privacy_level='public',)

    filtered_projects = builds.values_list(
        'project',
        flat=True
    )
    return Project.objects.filter(
        pk__in=filtered_projects
    )


def get_international_version_slug(project, lang_slug, version_slug):
    """For readability of urls we are changing slug names if language is not Italian."""
    lang_slug = lang_slug or project.language
    version_slug = version_slug or project.get_default_version()
    if lang_slug != 'it':
        if version_slug == STABLE:
            return getattr(settings, 'RTD_STABLE_EN', 'stable')
        if version_slug == LATEST:
            return getattr(settings, 'RTD_LATEST_EN', 'latest')
    return version_slug


def get_real_version_slug(lang_slug, version_slug):
    """Get the real slug names from international version."""
    if lang_slug != 'it':
        rtd_stable_en = getattr(settings, 'RTD_STABLE_EN', 'stable')
        rtd_latest_en = getattr(settings, 'RTD_LATEST_EN', 'latest')

        if version_slug == rtd_stable_en:
            version_slug = STABLE
        if version_slug == rtd_latest_en:
            version_slug = LATEST
    return version_slug
