# Managed settings file

import os
import re

from readthedocs.settings.base import CommunityBaseSettings

_redis = {
    'default': dict(zip(['host', 'port', 'db'], re.split(':|/|@', os.environ['REDIS_CACHE_URL']))),
    'celery': dict(zip(['host', 'port', 'db'], re.split(':|/|@', os.environ['REDIS_CELERY_URL']))),
    'stats': dict(zip(['host', 'port', 'db'], re.split(':|/|@', os.environ['REDIS_STATS_URL']))),
}


class DocsItaliaDockerSettings(CommunityBaseSettings):

    """Settings for local development"""

    SERVE_DOCS = ['private']
    PYTHON_MEDIA = True
    PRODUCTION_DOMAIN = os.environ['RTD_DOMAIN']
    USE_SUBDOMAIN = False
    PUBLIC_DOMAIN = os.environ['PUBLIC_DOMAIN']
    PUBLIC_API_URL = os.environ['PUBLIC_API_URL']
    GLOBAL_ANALYTICS_CODE = os.environ['GLOBAL_ANALYTICS_CODE']
    PUBLIC_DOMAIN_USES_HTTPS = os.environ['RTD_PROTO'] == 'https'

    # default build versions
    RTD_LATEST = 'bozza'
    RTD_LATEST_VERBOSE_NAME = RTD_LATEST
    RTD_STABLE = 'stabile'
    RTD_STABLE_VERBOSE_NAME = RTD_STABLE
    RTD_LATEST_EN = 'draft'
    RTD_STABLE_EN = 'stable'

    # General settings
    DEBUG = os.environ['DEBUG']
    TEMPLATE_DEBUG = False
    TAGGIT_TAGS_FROM_STRING = 'readthedocs.docsitalia.utils.docsitalia_parse_tags'

    DOCS_BASE = os.environ.get('DOCS_BASE', CommunityBaseSettings.SITE_ROOT)
    MEDIA_ROOT = os.path.join(DOCS_BASE, 'media/')
    STATIC_ROOT = os.path.join(DOCS_BASE, 'media/static/')
    MEDIA_URL = os.environ['MEDIA_URL']
    STATIC_URL = MEDIA_URL + 'static/'
    ADMIN_MEDIA_PREFIX = MEDIA_URL + 'admin/'
    SECRET_KEY = os.environ['SECRET_KEY']
    DEFAULT_FROM_EMAIL = os.environ['DEFAULT_FROM_EMAIL']
    SESSION_COOKIE_DOMAIN = os.environ['RTD_DOMAIN']

    DOCROOT = os.path.join(DOCS_BASE, 'user_builds')
    UPLOAD_ROOT = os.path.join(DOCS_BASE, 'user_uploads')
    CNAME_ROOT = os.path.join(DOCS_BASE, 'cnames')
    LOGS_ROOT = os.path.join(DOCS_BASE, 'logs')
    PRODUCTION_ROOT = os.path.join(DOCS_BASE, 'prod_artifacts')
    PUBLIC_BASE = DOCS_BASE
    PRIVATE_BASE = DOCS_BASE

    @property
    def TEMPLATES(self):  # noqa
        TEMPLATES = super().TEMPLATES
        TEMPLATE_OVERRIDES = os.path.join(super().TEMPLATE_ROOT, 'docsitalia', 'overrides')
        TEMPLATES[0]['DIRS'].insert(0, TEMPLATE_OVERRIDES)
        return TEMPLATES

    @property
    def INSTALLED_APPS(self):  # noqa
        apps = super().INSTALLED_APPS
        # Insert our depends above RTD applications, after guaranteed third
        # party package
        apps.append('readthedocs.docsitalia')
        apps.append('dal',)
        apps.append('dal_select2',)
        if os.environ.get('DOCS_CONVERTER_VERSION', False):
            apps.insert(apps.index('rest_framework'), 'docs_italia_convertitore_web')

        if os.environ.get('SENTRY_DSN', False):
            apps.insert(apps.index('rest_framework'), 'raven.contrib.django.raven_compat')

        if os.environ.get('DEBUG', False):
            apps.append('debug_toolbar')

        return apps

    if os.environ.get('REDIS_PASS', None):
        REDIS_CELERY_URL = ':%(pass)s@%(url)s' % {
            'pass': os.environ['REDIS_PASS'], 'url': os.environ['REDIS_CELERY_URL']
        }
        for cache_name in _redis:
            _redis[cache_name]['host'] = ':%(pass)s@%(host)s' % {
                'pass': os.environ['REDIS_PASS'], 'host': _redis[cache_name]['host']
            }
    # Celery
    CACHES = dict(
        (cache_name, {
            'BACKEND': 'redis_cache.RedisCache',
            'LOCATION': 'redis://{host}:{port}'.format(**cache),
            'OPTIONS': {
                'DB': cache['db'],
                'PICKLE_VERSION': -1,
            },
        })
        for (cache_name, cache)
        in _redis.items()
        if cache_name != 'celery'
    )

    BROKER_URL = 'redis://%s' % REDIS_CELERY_URL
    CELERY_RESULT_BACKEND = 'redis://%s' % REDIS_CELERY_URL

    # Docker
    DOCKER_SOCKET = os.environ.get('DOCKER_BUILD_HOST', None)
    DOCKER_ENABLE = bool(os.environ.get('DOCKER_BUILD_HOST', False))
    DOCKER_IMAGE = os.environ.get('DOCKER_BUILD_IMAGE', '')
    DOCKER_VERSION = '1.33'
    DOCKER_LIMITS = {
        'memory': '999m',
        'time': 3600,
    }
    if os.environ.get('SENTRY_DSN', False):

        import raven  # NOQA
        RAVEN_CONFIG = {
            'dsn': os.environ['SENTRY_DSN'],
            'release': raven.fetch_git_sha(CommunityBaseSettings.SITE_ROOT)
        }

    # Haystack - we don't really use it. ES API is used instead
    HAYSTACK_CONNECTIONS = {
        'default': {
            'ENGINE': 'haystack.backends.simple_backend.SimpleEngine',
        },
    }

    CELERY_ALWAYS_EAGER = False
    CELERY_HAYSTACK_DEFAULT_ALIAS = None
    CELERY_TASK_RESULT_EXPIRES = 7200

    # Elastic Search
    ES_HOSTS = []
    for host in os.environ['ES_HOST'].split(','):
        if os.environ.get('ES_USER', None) and os.environ.get('ES_PASS', None):
            ES_HOSTS.append('http://%(user)s:%(pass)s@%(host)s' % {
                'user': os.environ.get('ES_USER', None),
                'pass': os.environ.get('ES_PASS', None),
                'host': host,
            })
        else:
            ES_HOSTS.append(host)
    ELASTICSEARCH_DSL = {
        'default': {
            'hosts': ES_HOSTS
        },
    }

    # RTD settings
    # This goes together with FILE_SYNCER setting
    # eg: FILE_SINCER = 'readthedocs.builds.syncers.*' (likely RemoteSyncer)
    SLUMBER_API_HOST = 'http://%s' % os.environ['API_HOST']
    SLUMBER_USERNAME = os.environ['SLUMBER_USERNAME']
    SLUMBER_PASSWORD = os.environ['SLUMBER_PASSWORD']
    SYNC_USER = os.environ['RTD_USER']

    ACCOUNT_EMAIL_VERIFICATION = 'mandatory'
    SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    REPO_LOCK_SECONDS = 300
    DONT_HIT_DB = False

    # Override classes
    CLASS_OVERRIDES = {
        'readthedocs.builds.syncers.Syncer': 'readthedocs.builds.syncers.LocalSyncer',
        'readthedocs.core.resolver.Resolver': 'readthedocs.docsitalia.resolver.ItaliaResolver',
        'readthedocs.oauth.services.GitHubService':
            'readthedocs.docsitalia.oauth.services.github.DocsItaliaGithubService',
    }

    # Email
    if os.environ.get('EMAIL_HOST', False):
        EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
        EMAIL_USE_TLS = True
        EMAIL_HOST = os.environ['EMAIL_HOST']
        EMAIL_HOST_USER = os.environ['EMAIL_HOST_USER']
        EMAIL_HOST_PASSWORD = os.environ['EMAIL_HOST_PASSWORD']
    else:
        EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

    # Social Auth
    GITHUB_APP_ID = os.environ['GITHUB_APP_ID']
    GITHUB_API_SECRET = os.environ['GITHUB_API_SECRET']

    SOCIALACCOUNT_PROVIDERS = {
        'github': {'SCOPE': ['user:email', 'read:org', 'admin:repo_hook', 'repo:status']}
    }

    ACCOUNT_DEFAULT_HTTP_PROTOCOL = os.environ.get('ACCOUNT_HTTP_PROTO', 'http')

    ADMINS = (
        ('Test', 'test@{{ rtd_domain }}'),
    )
    TIME_ZONE = 'Europe/Rome'
    LANGUAGE_CODE = 'it-it'

    CORS_ORIGIN_WHITELIST = (
        '%s:8000' % os.environ['RTD_DOMAIN'],
    )

    if os.environ.get('CORS_HEADERS_HOSTS', False) == 'all':
        CORS_ORIGIN_ALLOW_ALL = True

    WEBSOCKET_HOST = '%s:8088' % os.environ['RTD_DOMAIN']

    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql_psycopg2',
            'NAME': os.environ.get('POSTGRES_NAME'),
            'USER': os.environ.get('POSTGRES_USER'),
            'PASSWORD': os.environ.get('POSTGRES_PASS'),
            'HOST': os.environ.get('POSTGRES_HOST'),
            'PORT': os.environ.get('POSTGRES_PORT'),
        },
    }

    # Etc
    RESTRUCTUREDTEXT_FILTER_SETTINGS = {
        'cloak_email_addresses': True,
        'file_insertion_enabled': False,
        'raw_enabled': False,
        'strip_comments': True,
        'doctitle_xform': True,
        'sectsubtitle_xform': True,
        'initial_header_level': 2,
        'report_level': 5,
        'syntax_highlight': 'none',
        'math_output': 'latex',
        'field_name_limit': 50,
    }
    USE_PROMOS = False

    ALLOWED_HOSTS = ['*']
    USER_MATURITY_DAYS = 14
    READTHEDOCSEXT_MONITORING_CACHE = 'stats'
    DEFAULT_VERSION_PRIVACY_LEVEL = os.environ['DEFAULT_VERSION_PRIVACY_LEVEL']

    @property
    def TEXTCLASSIFIER_DATA_FILE(self): # NOQA
        return os.path.join(self.SITE_ROOT, 'textclassifier.json')

    # Banned" projects
    HTML_ONLY_PROJECTS = (
        'atom',
        'galaxy-central',
        'django-geoposition',
    )

    # Add fancy sessions after the session middleware
    @property
    def MIDDLEWARE(self):
        middlewares = list(super().MIDDLEWARE)
        index = middlewares.index(
            'readthedocs.core.middleware.FooterNoSessionMiddleware'
        )
        middlewares.insert(
            index + 1,
            'restrictedsessions.middleware.RestrictedSessionsMiddleware'
        )
        if os.environ.get('DEBUG', False) and os.environ.get('ENABLE_DEBUG_TOOLBAR', True):
            middlewares.insert(0, 'debug_toolbar.middleware.DebugToolbarMiddleware')
        return middlewares

    RESTRICTEDSESSIONS_AUTHED_ONLY = True

    # Logging
    @property
    def LOGGING(self): # NOQA
        logging = super(DocsItaliaDockerSettings, self).LOGGING
        logging['formatters']['syslog'] = {
            'format': 'readthedocs/%(name)s[%(process)d]: '
                      '%(levelname)s %(message)s [%(name)s:%(lineno)s]',
            'datefmt': '%d/%b/%Y %H:%M:%S'
        }
        logging['loggers'] = {
            '': {
                'handlers': ['console'],
                'level': 'INFO',
            }
        }
        return logging

    INTERNAL_IPS = ["127.0.0.1", "localhost", "local.docs.italia.it"]

    def show_toolbar(request):
            return True

    DEBUG_TOOLBAR_CONFIG = {
        'SHOW_TOOLBAR_CALLBACK': show_toolbar,
    }

DocsItaliaDockerSettings.load_settings(__name__)

if not os.environ.get('DJANGO_SETTINGS_SKIP_LOCAL', False):
    try:
        # pylint: disable=unused-wildcard-import
        from .local_settings import *  # noqa
    except ImportError:
        pass
