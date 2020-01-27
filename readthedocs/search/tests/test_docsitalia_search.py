import json
import time
import mock
import pytest
from django.urls import reverse
from django_dynamic_fixture import G

from readthedocs.builds.models import Version
from readthedocs.docsitalia.models import Publisher, PublisherProject
from readthedocs.projects.models import HTMLFile, Project
from readthedocs.search.documents import PageDocument, ProjectDocument
from readthedocs.search.tasks import index_objects_to_es
from readthedocs.search.tests.utils import get_search_query_from_project_file


@pytest.mark.django_db
@pytest.mark.search
class TestDocsItaliaSearch:
    fixtures = ['eric', 'test_data']

    def test_docsitalia_api_results_with_publisher(self, all_projects, client, es_index):

        publisher = Publisher.objects.create(
            name='Test Org',
            slug='publisher',
            metadata={},
            projects_metadata={},
            active=True
        )
        pub_project = PublisherProject.objects.create(
            name='Test Project',
            slug='testproject',
            metadata={
                'documents': [
                    'https://github.com/testorg/myrepourl',
                    'https://github.com/testorg/anotherrepourl',
                ]
            },
            publisher=publisher,
            active=True
        )
        project = all_projects[0]
        pub_project.projects.add(project)

        kwargs = {
            'app_label': Project._meta.app_label,
            'model_name': Project.__name__,
            'document_class': str(ProjectDocument),
            'objects_id': [project.id],
        }

        index_objects_to_es.delay(**kwargs)
        inst = ProjectDocument.get(id=project.id)

        assert inst.publisher == publisher.name
        assert inst.publisher_project == pub_project.slug

    @mock.patch('readthedocs.search.api.PageSearch')
    def test_docsitalia_api_empty_results(self, execute, all_projects, client, es_index):
        execute.return_value = []
        project = all_projects[0]
        query = get_search_query_from_project_file(project_slug=project.slug)
        url = reverse('doc_search')
        search_params = {'q': query, 'project': project.slug, 'version': 'latest'}

        response = client.get(url, search_params)
        assert response.status_code == 200
        expected = {"count": 0, "next": None, "previous": None, "results": []}
        assert json.loads(response.content.decode('utf-8')) == expected


@pytest.mark.django_db
@pytest.mark.search
class TestDocsItaliaPageSearch(object):
    url = reverse('search')

    def _get_search_result(self, url, client, search_params):
        resp = client.get(url, search_params)
        assert resp.status_code == 200

        results = resp.context['results']
        facets = resp.context['facets']

        return results, facets

    def test_search_filter_default_version(self, client, all_projects):
        search_params = {'q': 'celery', 'type': 'file'}
        results, facets = self._get_search_result(
            url=self.url,
            client=client,
            search_params=search_params
        )
        assert len(results) == 5

        for result in results:
            project = Project.objects.get(slug=result.project)
            assert result.version == project.default_version
            assert result.is_default

        search_params['version'] = 'latest'

        results, facets = self._get_search_result(
            url=self.url,
            client=client,
            search_params=search_params
        )

        assert len(results) == 5

        project = all_projects[0]
        new_version = G(Version, project=project)
        html_files = HTMLFile.objects.filter(project=project)
        # create HTML files for different version
        for html_file in html_files:
            new_html = G(HTMLFile, project=project, version=new_version, name=html_file.name)
            PageDocument().update(new_html)

        query = get_search_query_from_project_file(project_slug=project.slug)
        search_params = {'q': query, 'type': 'file'}
        results, facets = self._get_search_result(
            url=self.url,
            client=client,
            search_params=search_params,
        )
        assert len(results) == 1
        assert results[0].is_default
        assert project.default_version == results[0].version

        search_params['version'] = new_version.slug
        results, facets = self._get_search_result(
            url=self.url,
            client=client,
            search_params=search_params,
        )
        assert len(results) == 1

        assert search_params['version'] == results[0].version
        assert not results[0].is_default

        search_params['version'] = 'nonexistent'
        results, facets = self._get_search_result(
            url=self.url,
            client=client,
            search_params=search_params,
        )
        assert not results

    @pytest.mark.skip(reason="doesn't work with CELERY_ALWAYS_EAGER=True")
    def test_change_default_version(self, client, all_projects, settings):
        project = all_projects[0]
        new_version = G(Version, project=project)
        html_files = HTMLFile.objects.filter(project=project)
        for html_file in html_files:
            new_html = G(HTMLFile, project=project, version=new_version, name=html_file.name)
            PageDocument().update(new_html)

        query = get_search_query_from_project_file(project_slug=project.slug)
        search_params = {'q': query, 'type': 'file'}
        results, facets = self._get_search_result(
            url=self.url,
            client=client,
            search_params=search_params,
        )
        assert len(results) == 1
        assert results[0].is_default
        assert project.default_version == results[0].version
        assert new_version.slug != results[0].version

        project.default_version = new_version.slug
        project.save()
        time.sleep(2)
        results, facets = self._get_search_result(
            url=self.url,
            client=client,
            search_params=search_params,
        )
        assert len(results) == 1
        assert results[0].is_default
        assert project.default_version == results[0].version
        assert new_version.slug == results[0].version

    def test_search_file_priority(self, client, all_projects):
        by_slug = {}
        for index, project in enumerate(all_projects):
            by_slug[project.slug] = project
            project.projectorder.priority = 100 - index
            project.projectorder.save()

        results, _ = self._get_search_result(
            url=self.url,
            client=client,
            search_params={'q': '*', 'type': 'file', 'sort': 'priority'}
        )
        assert len(results) >= 1

        previous_priority = 100
        # enumerating all the index content and checking that priority are
        # strictly in decreasing order and project and index has the same
        # priority for the same project
        for index, result in enumerate(results):
            project_by_slug = by_slug[result.project]
            assert previous_priority >= result.priority
            assert result.priority == project_by_slug.projectorder.priority
            previous_priority = result.priority

    def test_search_by_tag(self, client, all_projects):
        by_slug = {}
        for index, project in enumerate(all_projects):
            by_slug[project.slug] = project
            project.projectorder.priority = 100 - index
            project.projectorder.save()

        custom_tag = 'search_by_tag'
        other_tag = 'other_tag'
        project = all_projects[0]
        project.tags.add(custom_tag)
        new_version = G(Version, project=project)
        project.default_version = new_version.slug
        project.save()

        other_project = all_projects[1]
        other_project.tags.add(other_tag)
        new_version = G(Version, project=other_project)
        other_project.default_version = new_version.slug
        other_project.save()

        # test normal search works with tags
        default_search_results, _ = self._get_search_result(
            url=self.url,
            client=client,
            search_params={'q': '*', 'type': 'file', 'tags': custom_tag}
        )
        assert len(default_search_results) == 2
        for result in default_search_results:
            assert result.project == project.slug

        # custom search yields the same results as the normal search
        search_by_tag_url = reverse('search_by_tag', kwargs={'tag': custom_tag})
        search_by_tag_results, _ = self._get_search_result(
            url=search_by_tag_url,
            client=client,
            search_params={}
        )
        assert len(search_by_tag_results) == 2
        for result in search_by_tag_results:
            assert result.project == project.slug

        # tags passed via GET are merged with the base one
        search_by_tag_url = reverse('search_by_tag', kwargs={'tag': custom_tag})
        new_url = '%s?%s' % (reverse('search'), 'tags=other_tag')
        resp = client.get(search_by_tag_url, {'tags': other_tag})
        assert resp.status_code == 302
        assert resp['Location'] == new_url
