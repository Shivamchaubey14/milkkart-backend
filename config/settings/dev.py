from .base import *  # noqa: F401, F403

DEBUG = True

ALLOWED_HOSTS = ["*"]

REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"].append(  # noqa: F405
    "rest_framework.renderers.BrowsableAPIRenderer",
)
