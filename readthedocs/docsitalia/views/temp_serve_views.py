import logging
import mimetypes
import os

from django.conf import settings
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.utils.encoding import iri_to_uri

from readthedocs.builds.models import Version
from readthedocs.core.permissions import AdminPermission
from readthedocs.docsitalia.utils import get_real_version_slug
from readthedocs.projects import constants

from readthedocs.core.views.serve import map_project_slug, map_subproject_slug, redirect_project_slug, _serve_401


log = logging.getLogger(__name__)


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


@map_project_slug
@map_subproject_slug
def serve_docs(
        request,
        project,
        subproject,
        lang_slug=None,
        version_slug=None,
        filename='',
):
    """Map existing proj, lang, version, filename views to the file format."""
    final_project, lang_slug, version_slug, filename = _get_project_data_from_request(  # noqa
        request,
        project_slug=project,
        subproject_slug=subproject,
        lang_slug=lang_slug,
        version_slug=version_slug,
        filename=filename,
    )

    log.debug(
        'Serving docs: project=%s, subproject=%s, lang_slug=%s, version_slug=%s, filename=%s',
        final_project.slug, subproject, lang_slug, version_slug, filename
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

    # TODO: un-comment when ready to perform redirect here
    # redirect_path, http_status = self.get_redirect(
    #     final_project,
    #     lang_slug,
    #     version_slug,
    #     filename,
    #     request.path,
    # )
    # if redirect_path and http_status:
    #     return self.get_redirect_response(request, redirect_path, http_status)

    # Check user permissions and return an unauthed response if needed
    # TODO - now it is a fake method returning True
    # if not self.allowed_user(request, final_project, version_slug):
    #     return self.get_unauthed_response(request, final_project)

    try:
        version = (
            Version.objects
            .public(user=request.user, project=project)
            .get(slug=version_slug)
        )
    except Version.DoesNotExist:
        # Properly raise a 404 if the version doesn't exist (or is inactive) and
        # a 401 if it does
        if project.versions.filter(slug=version_slug, active=True).exists():
            return _serve_401(request, project)
        raise Http404('Version does not exist.')

    if (version.privacy_level == constants.PRIVATE and
            not AdminPermission.is_member(user=request.user, obj=project)):
        return _serve_401(request, project)

    storage_path = final_project.get_storage_path(
        type_='html', version_slug=version_slug, include_file=False
    )
    path = os.path.join(storage_path, filename)

    # Handle our backend storage not supporting directory indexes,
    # so we need to append index.html when appropriate.
    if path[-1] == '/':
        path += 'index.html'

    # raise Exception(path)

    log.info('[Nginx serve] path=%s, project=%s', path, final_project.slug)

    if not path.startswith(settings.AZURE_MEDIA_STORAGE_URL):
        if path[0] == '/':
            path = path[1:]
        path = f'{settings.settings.AZURE_MEDIA_STORAGE_URL}{path}'

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
