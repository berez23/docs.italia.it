# -*- coding: utf-8 -*-
"""Define endpoints for the related projects section ("Documenti correlati")."""

from django.db.models import Prefetch
from rest_framework.generics import RetrieveAPIView
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response

from readthedocs.api.v2.permissions import APIPermission
from readthedocs.projects.models import Project

from ..serializers import RelatedProjectsSerializer


class RelatedProjectsView(RetrieveAPIView):
    """A view returning 3 sections of related projects using a given project slug."""

    lookup_field = 'slug'
    permission_classes = (APIPermission,)
    queryset = Project.objects.filter(
        documentation_type__contains='sphinx'
    ).prefetch_related("publisherproject_set__publisher", "tags")
    renderer_classes = (JSONRenderer,)
    serializer_class = RelatedProjectsSerializer
