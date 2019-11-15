"""Search views."""
import collections
import itertools
import logging
from operator import attrgetter

from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render

from readthedocs.builds.constants import LATEST
from readthedocs.projects.models import Project
from readthedocs.search.faceted_search import (
    ALL_FACETS,
    PageSearch,
    ProjectSearch,
)
from readthedocs.search import utils


log = logging.getLogger(__name__)
LOG_TEMPLATE = '(Elastic Search) [%(user)s:%(type)s] [%(project)s:%(version)s:%(language)s] %(msg)s'

PAGE_SIZE = 9
RELEVANCE_KEY = 'relevance'
ALL_SORTS = {
    RELEVANCE_KEY: {'value': '_score', 'label': 'Rilevanza'},
    'alphabetical': {'value': 'name', 'label': 'Ordine alfabetico'},
    'newest': {'value': 'date', 'label': 'Più recente'},
    'oldest': {'value': '-date', 'label': 'Meno recente'},
}

UserInput = collections.namedtuple(
    'UserInput',
    (
        'query',
        'type',
        'project',
        'version',
        'taxonomy',
        'language',
        'role_name',
        'index',
        'publisher',
        'publisher_project',
        'sort',
        'tags',
        'page',
    ),
)


class ESPaginator(Paginator):
    def __init__(self, response, *args, **kwargs):
        super().__init__(list(response), *args, **kwargs)
        self._count = response.hits.total

    def page(self, number):
        number = self.validate_number(number)
        return self._get_page(self.object_list, number, self)

    @property
    def count(self):
        return self._count


def elastic_search(request, project_slug=None):
    """
    Global user search on the dashboard.

    This is for both the main search and project search.

    :param project_slug: Sent when the view is a project search
    """

    request_type = None
    if project_slug:
        queryset = Project.objects.protected(request.user)
        project_obj = get_object_or_404(queryset, slug=project_slug)
        request_type = request.GET.get('type', 'file')

    user_input = UserInput(
        query=request.GET.get('q'),
        type=request_type or request.GET.get('type', 'project'),
        project=project_slug or request.GET.get('project'),
        version=request.GET.get('version', LATEST),
        taxonomy=request.GET.get('taxonomy'),
        language=request.GET.get('language'),
        role_name=request.GET.get('role_name'),
        index=request.GET.get('index'),
        publisher=request.GET.get('publisher'),
        publisher_project=request.GET.getlist('publisher_project'),
        sort=request.GET.get('sort'),
        tags=request.GET.getlist('tags'),
        page=request.GET.get('page'),
    )
    search_facets = collections.defaultdict(
        lambda: ProjectSearch,
        {
            'project': ProjectSearch,
            'file': PageSearch,
        }
    )

    results = None
    facets = {}
    sort_key = user_input.sort if user_input.sort in ALL_SORTS.keys() else RELEVANCE_KEY
    try:
        page_int = int(user_input.page)
    except (TypeError, ValueError):
        page_int = 1
    page_start = (page_int - 1) * PAGE_SIZE
    page_end = page_start + PAGE_SIZE

    if user_input.query:
        kwargs = {}
        kwargs['sort'] = [ALL_SORTS[sort_key]['value']]

        for avail_facet in ALL_FACETS:
            value = getattr(user_input, avail_facet, None)
            if value:
                kwargs[avail_facet] = value

        search = search_facets[user_input.type](
            query=user_input.query, user=request.user, **kwargs
        )
        results = search[page_start:page_end].execute()
        if not results:
            page_int = 1
            results = search[0:PAGE_SIZE].execute()
        facets = results.facets

        log.info(
            LOG_TEMPLATE,
            {
                'user': request.user,
                'project': user_input.project or '',
                'type': user_input.type or '',
                'version': user_input.version or '',
                'language': user_input.language or '',
                'msg': user_input.query or '',
            }
        )

    # Make sure our selected facets are displayed even when they return 0 results
    for avail_facet in ALL_FACETS:
        value = getattr(user_input, avail_facet, None)
        if not value or avail_facet not in facets:
            continue
        if isinstance(value, list):
            for v in value:
                if v not in [val[0] for val in facets[avail_facet]]:
                    facets[avail_facet].insert(0, (v, 0, True))
            continue
        if value not in [val[0] for val in facets[avail_facet]]:
            facets[avail_facet].insert(0, (value, 0, True))

    if results:

        # sorting inner_hits (if present)
        if user_input.type == 'file':

            try:
                for result in results:
                    inner_hits = result.meta.inner_hits
                    sections = inner_hits.sections or []
                    domains = inner_hits.domains or []
                    all_results = itertools.chain(sections, domains)

                    sorted_results = utils._get_sorted_results(
                        results=all_results,
                        source_key='source',
                    )

                    result.meta.inner_hits = sorted_results
            except Exception:
                log.exception('Error while sorting the results (inner_hits).')

        log.debug('Search results: %s', results.to_dict())
        log.debug('Search facets: %s', results.facets.to_dict())

    paginator = ESPaginator(results, PAGE_SIZE)
    page = paginator.page(page_int)

    template_vars = user_input._asdict()
    template_vars.update({
        'results': results,
        'page': page,
        'facets': facets,
        'results_dict': results.to_dict() if results else {},
        'facets_dict': facets.to_dict() if facets else {},
        'sorts': {k: {
            'label': v['label'], 'selected': k == sort_key
        } for k, v in ALL_SORTS.items()},
    })

    if project_slug:
        template_vars.update({'project_obj': project_obj})

    return render(
        request,
        'search/elastic_search.html',
        template_vars,
    )
