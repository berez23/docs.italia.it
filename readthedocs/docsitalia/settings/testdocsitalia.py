from __future__ import absolute_import
import os

from readthedocs.settings.test import CommunityTestSettings


class DocsItaliaTestSettings(CommunityTestSettings):
    ES_SEARCH_FILE_MIN_SCORE = 0  # Neeeded for RTD compat tests

    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'PREFIX': 'docs',
        }
    }

    if os.environ.get('TRAVIS_DOCSITALIA_DOCKER', False):
        DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.postgresql_psycopg2',
                'USER': 'docs',
                'HOST': 'db',
                'PORT': 5432,
                'PASSWORD': 'docs',
                'NAME': 'rtd'
            }
        }

        ES_HOSTS = ['es:9200']
        ELASTICSEARCH_DSL = {
            'default': {
                'hosts': 'es:9200'
            },
        }
    elif os.environ.get('TOX_ENV_NAME', None) == 'migrations':
        DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': ':memory'
            }
        }
    else:
        DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.postgresql_psycopg2',
                'USER': '',
                'HOST': '',
                'PORT': 5432,
                'PASSWORD': '',
                'NAME': 'test_docsitalia'
            }
        }

    AZURE_MEDIA_STORAGE_URL = '/media/'

    @property
    def INSTALLED_APPS(self):  # noqa
        apps = super().INSTALLED_APPS
        apps.append('readthedocs.docsitalia')
        apps.append('dal',)
        apps.append('dal_select2',)
        apps.append('docs_italia_convertitore_web')
        return apps

    @property
    def TEMPLATES(self):  # noqa
        TEMPLATES = super().TEMPLATES
        TEMPLATE_OVERRIDES = os.path.join(super().TEMPLATE_ROOT, 'docsitalia', 'overrides')
        TEMPLATES[0]['DIRS'].insert(0, TEMPLATE_OVERRIDES)
        return TEMPLATES


DocsItaliaTestSettings.load_settings(__name__)

if not os.environ.get('DJANGO_SETTINGS_SKIP_LOCAL', False):
    try:
        from .test_local_settings import *  # noqa
    except ImportError:
        pass
