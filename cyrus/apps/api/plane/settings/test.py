# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Test Settings"""

import os

# Override environment variables for testing with localhost
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/")
os.environ.setdefault(
    "DATABASE_URL", "postgresql://plane:plane@localhost:5432/plane"
)

from .common import *  # noqa

DEBUG = True

# Send it in a dummy outbox
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

INSTALLED_APPS.append(  # noqa
    "plane.tests"
)
