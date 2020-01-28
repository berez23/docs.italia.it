# -*- coding: utf-8 -*-
"""Models for the docsitalia app."""

from django.db import models
from django.contrib.postgres.fields import JSONField
from django.utils.encoding import python_2_unicode_compatible
from django.utils.translation import ugettext_lazy as _
from django.core.urlresolvers import reverse

from readthedocs.builds.models import Version
from readthedocs.core.utils import broadcast
from readthedocs.projects.models import Project
from readthedocs.oauth.models import RemoteOrganization, RemoteRepository

from readthedocs.core.resolver import resolver

from . import tags_vocabulary
from .utils import get_projects_with_builds
from .monkeypatch import monkey_patch_project_model  # NOQA


def update_project_from_metadata(project, metadata):
    """Update a project instance with the validated  project metadata."""
    document = metadata['document']
    project.name = document['name']
    project.description = document['description']
    project.tags.set(*document['tags'], clear=True)
    try:
        project.language = document['language']
    except KeyError:
        project.language = 'it'
    project.save()


@python_2_unicode_compatible
class Publisher(models.Model):

    """
    The Publisher is the organization that hosts projects (PublisherProject).

    The idea is to tie a Publisher to a RemoteOrganization, if we have a
    Publisher instance for a RemoteOrganization we can sync its data as
    available in the well-known repo and config files.

    Given the requirement of handling content in different languages we don't
    want to duplicate the publisher data here so the config file is the source
    of truth. A parsed version of the configuration is saved in the metadata
    field.

    The publisher homepage is handled by a django view with data from the
    metadata field.
    """

    # Auto fields
    pub_date = models.DateTimeField(_('Publication date'), auto_now_add=True)
    modified_date = models.DateTimeField(_('Modified date'), auto_now=True)

    # we need something unique
    name = models.CharField(_('Name'), max_length=255, unique=True, help_text=_(
        'Publisher\'s name in full. You can refer to the "name" field from '
        '"publisher_settings.yml", e.g. Ministero della Documentazione.'
    ))
    slug = models.SlugField(_('Slug'), max_length=255, unique=True, help_text=_(
        'Pick the URL fragment following "https://github.com" in the organization '
        'URL, e.g ministero-della-documentazione.'
    ))

    # TODO: is this enough to hold the publisher metadata?
    # https://github.com/italia/docs-italia-starter-kit/tree/master/repo-configurazione
    metadata = JSONField(_('Publisher Metadata'), blank=True, default=dict)
    projects_metadata = JSONField(_('Projects Metadata'), blank=True, default=dict)

    # the name of the repository that will hold the metadata
    config_repo_name = models.CharField(_('Docs italia config repo'),
                                        max_length=255,
                                        default=u'italia-conf')

    # the remote organization where we can find the configuration repository
    remote_organization = models.ForeignKey(RemoteOrganization,
                                            verbose_name=_('Remote organization'),
                                            on_delete=models.SET_NULL,
                                            null=True,
                                            blank=True)

    active = models.BooleanField(_('Active'), default=True, help_text=_(
        'Enables the import of documents.'
    ))

    def __str__(self):
        return self.name

    def create_projects_from_metadata(self, settings):  # pylint: disable=too-many-locals
        """Create PublisherProjects from metadata."""
        slugs = []
        repo_urls_cache = {}
        for project in settings['projects']:
            # since the slug is used for filtering we use it as key
            # for not duplicating renamed instances
            proj, created = PublisherProject.objects.get_or_create(
                publisher=self,
                slug=project['slug'],
                defaults={
                    'name': project['name'],
                }
            )
            if not created:
                proj.name = project['name']
            proj.metadata = project
            proj.active = True
            proj.save()

            slugs.append(project['slug'])

            # we cache the repository of each document for the
            # project so we can filter already uploaded documents easily
            for doc in project['documents']:
                repo_urls_cache[doc['repo_url']] = proj

        # we disable PublisherProjects that does not have
        # a slug in the metadata
        old_pub_projects = PublisherProject.objects.filter(
            publisher=self
        ).exclude(
            slug__in=slugs
        )
        old_pub_projects.update(
            active=False
        )

        # we need to port to the new PublisherProject any
        # already uploaded document connected to the disabled
        # PublisherProjects
        projects_to_move_pks = old_pub_projects.values_list(
            'projects',
            flat=True
        )
        repos_to_move = RemoteRepository.objects.filter(
            project__in=projects_to_move_pks,
            html_url__in=repo_urls_cache.keys()
        ).select_related('project')

        # we can now remove the documents from the old projects
        # and add them to the new one
        old_pub_projects_pks = list(old_pub_projects.values_list('pk', flat=True))
        for repo in repos_to_move:
            project = repo.project

            old_pub_projects = project.publisherproject_set.filter(
                pk__in=old_pub_projects_pks
            )
            for old_pub_proj in old_pub_projects:
                old_pub_proj.projects.remove(project)

            repo_url = repo.html_url
            new_pub_proj = repo_urls_cache[repo_url]
            new_pub_proj.projects.add(project)

    def active_publisher_projects(self):
        """Active publisher projects with active documents."""
        with_public_version = Version.objects.filter(
            privacy_level='public',
            active=True,
        ).values_list(
            'project',
            flat=True
        )
        return self.publisherproject_set.filter(
            active=True,
            projects__in=with_public_version
        ).order_by(
            '-modified_date', '-pub_date'
        ).distinct()

    def get_absolute_url(self):
        """Get absolute url for publisher."""
        return reverse('publisher_detail', args=[self.slug])

    def get_canonical_url(self):
        """Get canonical url for publisher."""
        return resolver.resolve_docsitalia(self.slug)

    def delete(self, *args, **kwargs):  # pylint: disable=arguments-differ
        """Delete Publisher and its organization."""
        if self.remote_organization:
            self.remote_organization.delete()
        super(Publisher, self).delete(*args, **kwargs)


@python_2_unicode_compatible
class PublisherProject(models.Model):

    """
    The PublisherProject is the project that contains documents.

    These are created from the organization metadata and created at import time

    The publisher project homepage is handled by a django view with data
    from the metadata field.
    """

    # Auto fields
    pub_date = models.DateTimeField(_('Publication date'), auto_now_add=True)
    modified_date = models.DateTimeField(_('Modified date'), auto_now=True)

    name = models.CharField(_('Name'), max_length=255)
    slug = models.SlugField(_('slug'), max_length=255)

    # this holds the metadata for the single project
    metadata = JSONField(_('Metadata'), blank=True, default=dict)

    # the organization that holds the project
    publisher = models.ForeignKey(Publisher, verbose_name=_('Publisher'))
    # projects are the documents :)
    projects = models.ManyToManyField(Project, verbose_name=_('Projects'))

    featured = models.BooleanField(_('Featured'), default=False)
    active = models.BooleanField(_('Active'), default=False)

    class Meta:
        # we want slug uniqueness only inside the same publisher
        unique_together = [('publisher', 'slug')]

    def __str__(self):
        return self.name

    def active_documents(self):
        """Active documents."""
        builded_projects = get_projects_with_builds().filter(
            publisherproject=self
        )
        return builded_projects.order_by(
            '-modified_date', '-pub_date'
        )

    def description(self):
        """Get publisher project description from metadata."""
        return self.metadata.get('description', '')

    def short_name(self):
        """Get publisher project short-name from metadata."""
        return self.metadata.get('short-name', '')

    def get_absolute_url(self):
        """get absolute url for publisher project."""
        return reverse('publisher_project_detail', args=[self.publisher.slug, self.slug])

    def get_canonical_url(self):
        """get canonical url for publisher project."""
        return resolver.resolve_docsitalia(self.publisher.slug, self.slug)

    def delete(self, *args, **kwargs):  # pylint: disable=arguments-differ
        """delete pb and all its projects and builds."""
        from readthedocs.projects import tasks

        projects = Project.objects.filter(publisherproject=self)
        versions = Version.objects.filter(project__in=projects)
        for version in versions:
            broadcast(type='app', task=tasks.remove_build_storage_paths, args=[version.pk])
        projects.delete()
        super(PublisherProject, self).delete(*args, **kwargs)


@python_2_unicode_compatible
class PublisherIntegration(models.Model):

    """Inbound webhook integration for publisher."""

    GITHUB_WEBHOOK = 'github_webhook'

    WEBHOOK_INTEGRATIONS = (
        (GITHUB_WEBHOOK, _('GitHub incoming webhook')),
    )

    INTEGRATIONS = WEBHOOK_INTEGRATIONS

    publisher = models.ForeignKey(Publisher, related_name='integrations')
    integration_type = models.CharField(
        _('Integration type'),
        max_length=32,
        choices=INTEGRATIONS
    )
    provider_data = JSONField(_('Provider data'), blank=True, default=dict)

    # Integration attributes
    has_sync = True

    def __str__(self):
        return (
            _('{0} for {1}')
            .format(self.get_integration_type_display(), self.publisher.name))


@python_2_unicode_compatible
class AllowedTag(models.Model):

    """
    Tags allowed to be used for a document.

    If a document contains a tag that does not belong to this table, it
    will be removed.
    """

    BASE_TAGS = tags_vocabulary.BASE_TAGS

    name = models.CharField(_('Name'), max_length=255, unique=True)
    enabled = models.BooleanField(_('Enabled'), default=True)

    class Meta:
        verbose_name = _('allowed tag')
        verbose_name_plural = _('allowed tags')
        ordering = ('name',)

    def __str__(self):
        return self.name

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        """Save the model instance to the database."""
        self.clean()
        return super(AllowedTag, self).save(
            force_insert=force_insert,
            force_update=force_update,
            using=using,
            update_fields=update_fields,
        )

    def clean(self):
        """Perform custom validation."""
        self.name = self.name.strip().lower()
        return super(AllowedTag, self).clean()

    @classmethod
    def remove_unallowed(cls):
        """Remove unallowed tags from existing projects."""
        allowed = cls.objects.filter(enabled=True).values_list('name', flat=True)
        for project in Project.objects.all():
            for tag in project.tags.names():
                if tag not in allowed:
                    project.tags.remove(tag)
            project.save()  # trigger a new search update


class ProjectOrder(models.Model):
    project = models.OneToOneField(Project, verbose_name=_('Projects'), on_delete=models.CASCADE)
    priority = models.PositiveIntegerField(
        default=0,
        help_text=_('Greater number goes first in Project list')
    )

    class Meta:
        verbose_name = _('project order')
        verbose_name_plural = _('projects order')
        ordering = ('-priority',)

    def __str__(self):
        return self.project.name
