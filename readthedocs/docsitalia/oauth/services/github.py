from __future__ import absolute_import
from builtins import str
import logging
import json

from django.apps import apps
from django.db.models import Q
from django.conf import settings
from django.core.urlresolvers import reverse
from requests.exceptions import RequestException

from readthedocs.oauth.services.github import GitHubService
from readthedocs.oauth.models import RemoteOrganization, RemoteRepository

from readthedocs.docsitalia.github import get_metadata_for_publisher
from readthedocs.docsitalia.metadata import (
    PUBLISHER_SETTINGS, PROJECTS_SETTINGS, InvalidMetadata)
from readthedocs.docsitalia.models import (
    Publisher, PublisherIntegration)

log = logging.getLogger(__name__)


class DocsItaliaGithubService(GitHubService):
    def sync(self):
        """Sync organizations."""
        self.sync_organizations()

    def sync_organizations(self):
        """Sync organizations from GitHub API."""
        dsl_app = apps.get_app_config('django_elasticsearch_dsl')
        signal_processor = dsl_app.signal_processor
        # this is a rather brutal way to handle this, but I cannot find a better solution
        # when syncing the orgs, we repeatedly save the publisher, which is linked to
        # the PageDocument and ProjectDocument. As django-elasticsearch-dsl is configured in
        # autosync this triggers the ES update for all the linked documents, and with large
        # organizations (namely: `italia`) this can yield a significant delay and unnecessary load.
        # Completely silencing the signals during this process it's the only option I have found.
        signal_processor.teardown()
        invalid_metadata_errors = []
        try:
            orgs = self.paginate('https://api.github.com/user/orgs')
            for org in orgs:
                org_resp = self.get_session().get(org['url'])
                org_obj = self.create_organization(org_resp.json())

                # we ingest only whitelisted organizations
                if not org_obj:
                    continue

                publisher = Publisher.objects.get(
                    remote_organization=org_obj, active=True)

                session = self.get_session()
                try:
                    publisher_metadata = get_metadata_for_publisher(
                        org_obj, publisher, PUBLISHER_SETTINGS, session)
                    projects_metadata = get_metadata_for_publisher(
                        org_obj, publisher, PROJECTS_SETTINGS, session)
                except InvalidMetadata as e:
                    log.error(
                        'Syncing GitHub organizations: %s', e)
                    # add errors
                    invalid_metadata_errors.append(str(e))
                    continue

                publisher.metadata = publisher_metadata
                publisher.projects_metadata = projects_metadata
                publisher.save()
                publisher.create_projects_from_metadata(projects_metadata)

                # FIXME: is this the right place?
                success, _ = self.setup_metadata_webhook(publisher)
                publisher.has_valid_webhook = success
                publisher.save()

                # Add repos
                # TODO ?per_page=100
                org_repos = self.paginate(
                    '{org_url}/repos'.format(org_url=org['url'])
                )
                repo_whitelist = set()
                for project in projects_metadata['projects']:
                    for document in project['documents']:
                        repo_whitelist.add(document['repository'])
                for repo in org_repos:
                    # create repo only for whitelisted repositories
                    if repo['name'] not in repo_whitelist:
                        continue
                    self.create_repository(repo, organization=org_obj)
                RemoteRepository.objects.filter(
                    Q(organization=org_obj),
                    ~Q(name__in=list(repo_whitelist))
                ).delete()
        except (TypeError, ValueError) as e:
            log.error('Error syncing GitHub organizations: %s',
                      str(e), exc_info=True)
            raise Exception('Could not sync your GitHub organizations, '
                            'try reconnecting your account')
        signal_processor.setup()
        if invalid_metadata_errors:
            raise Exception(' / '.join(invalid_metadata_errors))

    def create_organization(self, fields):
        """
        Update or create remote organization from GitHub API response.

        :param fields: dictionary response of data from API
        :rtype: Publisher
        """
        login = fields.get('login')
        log.info('Syncing organization %s', login)
        try:
            publisher = Publisher.objects.get(
                slug=login,
                active=True)
        except Publisher.DoesNotExist:
            log.info('No active publisher for slug %s', login)
            return None

        try:
            organization = RemoteOrganization.objects.get(
                slug=login,
                users=self.user,
                account=self.account,
            )
        except RemoteOrganization.DoesNotExist:
            # TODO: fun fact: slug is not unique
            organization = RemoteOrganization.objects.create(
                slug=login,
                account=self.account,
            )
            organization.users.add(self.user)

        publisher.remote_organization = organization
        publisher.save()

        organization.url = fields.get('html_url')
        organization.name = fields.get('name')
        organization.email = fields.get('email')
        organization.avatar_url = fields.get('avatar_url')
        if not organization.avatar_url:
            organization.avatar_url = self.default_org_avatar_url
        organization.json = json.dumps(fields)
        organization.account = self.account
        organization.save()

        return organization

    def get_metadata_webhook_data(self, publisher, integration):
        """Get metadata webhook JSON data to post to the API."""
        return json.dumps({
            'name': 'web',
            'active': True,
            'config': {
                'url': 'https://{domain}{path}'.format(
                    domain=settings.PRODUCTION_DOMAIN,
                    path=reverse(
                        'metadata_webhook',
                        kwargs={'publisher_slug': publisher.slug,
                                'integration_pk': integration.pk}
                    )
                ),
                'content_type': 'json',
            },
            'events': ['push'],
        })

    def setup_metadata_webhook(self, publisher):
        """
        Set up GitHub publisher configuration metadata webhook for configuration repo.

        :param publisher: publisher to set up webhook for
        :type publisher: Publisher
        :returns: boolean based on webhook set up success, and requests Response object
        :rtype: (Bool, Response)
        """
        session = self.get_session()
        owner = publisher.remote_organization.slug
        repo = publisher.config_repo_name
        integration, _ = PublisherIntegration.objects.get_or_create(
            publisher=publisher,
            integration_type=PublisherIntegration.GITHUB_WEBHOOK,
        )
        data = self.get_metadata_webhook_data(publisher, integration)
        resp = None
        try:
            resp = session.post(
                ('https://api.github.com/repos/{owner}/{repo}/hooks'
                 .format(owner=owner, repo=repo)),
                data=data,
                headers={'content-type': 'application/json'}
            )
            # GitHub will return 200 if already synced
            if resp.status_code in [200, 201]:
                recv_data = resp.json()
                integration.provider_data = recv_data
                integration.save()
                log.info('GitHub metadata webhook creation successful for publisher: %s',
                         publisher)
                return (True, resp)
        # Catch exceptions with request or deserializing JSON
        except (RequestException, ValueError):
            log.error('GitHub metadata webhook creation failed for publisher: %s',
                      publisher, exc_info=True)
        else:
            log.error('GitHub metadata webhook creation failed for publisher: %s',
                      publisher)
            # Response data should always be JSON, still try to log if not though
            try:
                debug_data = resp.json()
            except ValueError:
                debug_data = resp.content
            log.debug('GitHub metadata webhook creation failure response: %s',
                      debug_data)
            return (False, resp)
