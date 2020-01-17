# -*- coding: utf-8 -*-
"""Docs italia serializers."""

from rest_framework import serializers
from rest_framework.fields import empty
# from readthedocs.restapi.serializers import ProjectSerializer
# todo merge
from readthedocs.api.v2.serializers import ProjectSerializer
from readthedocs.projects.models import Project


class DocsItaliaProjectSerializer(ProjectSerializer):

    """DocsItalia custom serializer for Projects."""

    publisher = serializers.SerializerMethodField()
    publisher_project = serializers.SerializerMethodField()
    tags = serializers.SerializerMethodField()

    class Meta(ProjectSerializer.Meta):
        fields = (
            'id',
            'name', 'slug', 'description', 'language',
            'programming_language', 'repo', 'repo_type',
            'default_version', 'default_branch',
            'documentation_type',
            'users',
            'canonical_url',
            'tags', 'publisher', 'publisher_project',
        )

    @staticmethod
    def get_publisher(obj):
        """gets the publisher."""
        p_p = obj.publisherproject_set.first()
        if p_p:
            metadata = p_p.publisher.metadata.get('publisher', {})
            return {
                'name': metadata.get('name', obj.name),
                'canonical_url': p_p.publisher.get_canonical_url()
            }

    @staticmethod
    def get_publisher_project(obj):
        """gets the publisher project."""
        p_p = obj.publisherproject_set.first()
        if p_p:
            return {
                'name': p_p.name,
                'canonical_url': p_p.get_canonical_url()
            }

    @staticmethod
    def get_tags(obj):
        """gets the project tags."""
        return obj.tags.slugs()


class DocsItaliaProjectAdminSerializer(DocsItaliaProjectSerializer):

    """
    Project serializer for admin only access.

    Includes special internal fields that don't need to be exposed through the
    general API, mostly for fields used in the build process
    """

    features = serializers.SlugRelatedField(
        many=True,
        read_only=True,
        slug_field='feature_id',
    )

    class Meta(DocsItaliaProjectSerializer.Meta):
        fields = DocsItaliaProjectSerializer.Meta.fields + (
            'enable_epub_build',
            'enable_pdf_build',
            'conf_py_file',
            'analytics_code',
            'cdn_enabled',
            'container_image',
            'container_mem_limit',
            'container_time_limit',
            'install_project',
            'use_system_packages',
            # 'suffix', TODO merge
            'skip',
            'requirements_file',
            'python_interpreter',
            'features',
        )


class RelatedProjectsSectionSerializer(ProjectSerializer):

    """DocsItalia custom serializer for a single Related Projects section."""

    extra_data = serializers.SerializerMethodField()

    class Meta(ProjectSerializer.Meta):
        fields = ('name', 'slug', 'description', 'canonical_url', 'extra_data')

    @staticmethod
    def get_extra_data(obj):
        """Return an object containing Publisher and PublisherProject detail."""
        try:
            publisher_project = obj.publisherproject_set.all()[0]
        except IndexError:
            return {}
        else:
            publisher_data = publisher_project.publisher.metadata.get('publisher', {})
            return {
                'publisher_project': {
                    'name': publisher_project.name,
                    'canonical_url': publisher_project.get_canonical_url()
                },
                'publisher': {
                    'name': publisher_data.get('name', obj.name),
                    'canonical_url': publisher_project.publisher.get_canonical_url()
                }
            }


class RelatedProjectsSerializer(serializers.ModelSerializer):

    """DocsItalia custom serializer for Related Projects ("Documenti correlati")."""

    same_publisher = serializers.SerializerMethodField()
    same_publisher_project = serializers.SerializerMethodField()
    similar_tags = serializers.SerializerMethodField()

    class Meta(ProjectSerializer.Meta):
        fields = ('same_publisher', 'same_publisher_project', 'similar_tags')
        model = Project

    def __init__(self, instance=None, data=empty, **kwargs):
        super().__init__(instance=instance, data=data, **kwargs)
        self.publisher_project = instance.publisherproject_set.first()

    def get_same_publisher(self, obj):
        """Return projects having the same publisher as `obj`."""
        queryset = Project.objects.filter(
            publisherproject__publisher=self.publisher_project.publisher,
            versions__built=True
        ).exclude(pk=obj.pk).distinct()[:4]
        return RelatedProjectsSectionSerializer(queryset, many=True).data

    def get_same_publisher_project(self, obj):
        """Return projects having the same publisher project as `obj`."""
        queryset = Project.objects.filter(
            publisherproject=self.publisher_project,
            versions__built=True
        ).exclude(pk=obj.pk).distinct()[:4]
        return RelatedProjectsSectionSerializer(queryset, many=True).data

    @staticmethod
    def get_similar_tags(obj):
        """Return projects having similar tags to `obj`."""
        similar_projects = []
        for project in obj.tags.similar_objects():
            if project.versions.filter(built=True).exists():
                similar_projects.append(project)
            if len(similar_projects) == 4:
                break
        return RelatedProjectsSectionSerializer(similar_projects, many=True).data
