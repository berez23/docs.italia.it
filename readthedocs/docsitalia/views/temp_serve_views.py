# pylint: disable=invalid-name
"""
Temporary mix of old `serve_docs` view and Proxito view from upstream to make azure storage work.

Should be deleted after merge with new version of upstream.
"""

import logging
import mimetypes
from urllib.parse import urlparse, urlunparse
import os
from functools import wraps

from django.conf import settings
from django.http import Http404, HttpResponse, HttpResponseRedirect, HttpResponsePermanentRedirect
from django.shortcuts import get_object_or_404
from django.utils.encoding import iri_to_uri

from readthedocs.builds.models import Version
from readthedocs.core.permissions import AdminPermission
from readthedocs.docsitalia.utils import get_real_version_slug
from readthedocs.projects import constants
from readthedocs.projects.models import ProjectRelationship

from readthedocs.core.views.serve import map_project_slug, redirect_project_slug, _serve_401


log = logging.getLogger(__name__)


def map_subproject_slug(view_func):
    """
    A decorator that maps a ``subproject_slug`` URL param into a Project.

    :raises: Http404 if the Project doesn't exist

    .. warning:: Does not take into account any kind of privacy settings.
    """

    @wraps(view_func)
    def inner_view(  # noqa
            request, subproject=None, subproject_slug=None, *args, **kwargs
    ):
        if subproject is None and subproject_slug:
            # Try to fetch by subproject alias first, otherwise we might end up
            # redirected to an unrelated project.
            # Depends on a project passed into kwargs
            rel = ProjectRelationship.objects.filter(
                parent=kwargs['project'],
                alias=subproject_slug,
            ).first()
            if rel:
                subproject = rel.child
            else:
                rel = ProjectRelationship.objects.filter(
                    parent=kwargs['project'],
                    child__slug=subproject_slug,
                ).first()
                if rel:
                    subproject = rel.child
                else:
                    log.warning(
                        'The slug is not subproject of project. subproject_slug=%s project_slug=%s',
                        subproject_slug, kwargs['project'].slug
                    )
                    raise Http404('Invalid subproject slug')

        return view_func(request, subproject=subproject, *args, **kwargs)

    return inner_view


@map_project_slug
@map_subproject_slug
def _get_project_data_from_request(
        request,
        project,
        subproject,
        lang_slug=None,
        version_slug=None,
        filename='',
):
    """
    Get the proper project based on the request and URL.

    This is used in a few places and so we break out into a utility function.
    """
    # Take the most relevant project so far
    current_project = subproject or project

    if lang_slug and version_slug:
        version_slug = get_real_version_slug(lang_slug, version_slug)

    # Handle single-version projects that have URLs like a real project
    if current_project.single_version:
        if lang_slug and version_slug:
            filename = os.path.join(lang_slug, version_slug, filename)
            lang_slug = version_slug = None

    # Check to see if we need to serve a translation
    if not lang_slug or lang_slug == current_project.language:
        final_project = current_project
    else:
        final_project = get_object_or_404(
            current_project.translations.all(), language=lang_slug
        )

    # Handle single version by grabbing the default version
    if final_project.single_version:
        version_slug = final_project.get_default_version()

    # ``final_project`` is now the actual project we want to serve docs on,
    # accounting for:
    # * Project
    # * Subproject
    # * Translations

    return final_project, lang_slug, version_slug, filename


def get_redirect(project, lang_slug, version_slug, filename, full_path):
    # pylint: disable=unused-argument
    """
    Check for a redirect for this project that matches ``full_path``.

    :returns: the path to redirect the request and its status code
    :rtype: tuple
    """
    redirect_path, http_status = project.redirects.get_redirect_path_with_status(
        language=lang_slug,
        version_slug=version_slug,
        path=filename,
        # full_path=full_path, # do not work right now
    )
    return redirect_path, http_status


def get_redirect_response(request, redirect_path, http_status):
    """
    Build the response for the ``redirect_path`` and its ``http_status``.

    :returns: redirect respose with the correct path
    :rtype: HttpResponseRedirect or HttpResponsePermanentRedirect
    """
    schema, netloc, _, params, query, fragments = urlparse(request.path)
    new_path = urlunparse((schema, netloc, redirect_path, params, query, fragments))
    # Re-use the domain and protocol used in the current request.
    # Redirects shouldn't change the domain, version or language.
    # However, if the new_path is already an absolute URI, just use it
    new_path = request.build_absolute_uri(new_path)

    log.info(
        'Redirecting: from=%s to=%s http_status=%s',
        request.build_absolute_uri(),
        new_path,
        http_status,
    )

    if http_status and http_status == 301:
        return HttpResponsePermanentRedirect(new_path)

    return HttpResponseRedirect(new_path)


def serve_docs(
        request,
        project_slug=None,
        subproject_slug=None,
        lang_slug=None,
        version_slug=None,
        filename='',
):
    # pylint: disable-msg=too-many-locals
    """Map existing proj, lang, version, filename views to the file format."""
    final_project, lang_slug, version_slug, filename = _get_project_data_from_request(  # noqa
        request,
        project_slug=project_slug,
        subproject_slug=subproject_slug,
        lang_slug=lang_slug,
        version_slug=version_slug,
        filename=filename,
    )

    log.debug(
        'Serving docs: project=%s, subproject=%s, lang_slug=%s, version_slug=%s, filename=%s',
        final_project.slug, subproject_slug, lang_slug, version_slug, filename
    )
    # Handle a / redirect when we aren't a single version
    if all([lang_slug is None, version_slug is None, filename == '',
            not final_project.single_version]):
        redirect_to = redirect_project_slug(
            request,
            project=final_project,
            subproject=None,
        )
        log.info(
            'Proxito redirect: from=%s, to=%s, project=%s', filename,
            redirect_to, final_project.slug
        )
        return redirect_to

    if (lang_slug is None or version_slug is None) and not final_project.single_version:
        log.info(
            'Invalid URL for project with versions. url=%s, project=%s',
            filename, final_project.slug
        )
        raise Http404('Invalid URL for project with versions')

    redirect_path, http_status = get_redirect(
        final_project,
        lang_slug,
        version_slug,
        filename,
        request.path,
    )
    if redirect_path and http_status:
        return get_redirect_response(request, redirect_path, http_status)

    try:
        version = (
            Version.objects
            .public(user=request.user, project=final_project)
            .get(slug=version_slug)
        )
    except Version.DoesNotExist:
        # Properly raise a 404 if the version doesn't exist (or is inactive) and
        # a 401 if it does
        if final_project.versions.filter(slug=version_slug, active=True).exists():
            return _serve_401(request, final_project)
        raise Http404('Version does not exist.')

    if (version.privacy_level == constants.PRIVATE and
            not AdminPermission.is_member(user=request.user, obj=final_project)):
        return _serve_401(request, final_project)

    storage_path = final_project.get_storage_path(
        type_='html', version_slug=version_slug, include_file=False
    )
    path = os.path.join(storage_path, filename)

    # Handle our backend storage not supporting directory indexes,
    # so we need to append index.html when appropriate.
    if path[-1] == '/':
        path += 'index.html'

    log.info('[Nginx serve] path=%s, project=%s', path, final_project.slug)

    if not path.startswith(settings.AZURE_MEDIA_STORAGE_URL):
        if path[0] == '/':
            path = path[1:]
        path = f'{settings.AZURE_MEDIA_STORAGE_URL}{path}'

    content_type, encoding = mimetypes.guess_type(path)
    content_type = content_type or 'application/octet-stream'
    response = HttpResponse(
        f'Serving internal path: {path}', content_type=content_type
    )
    if encoding:
        response['Content-Encoding'] = encoding

    # NGINX does not support non-ASCII characters in the header, so we
    # convert the IRI path to URI so it's compatible with what NGINX expects
    # as the header value.
    # https://github.com/benoitc/gunicorn/issues/1448
    # https://docs.djangoproject.com/en/1.11/ref/unicode/#uri-and-iri-handling
    x_accel_redirect = iri_to_uri(path)
    response['X-Accel-Redirect'] = x_accel_redirect

    return response
