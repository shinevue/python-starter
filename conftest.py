from __future__ import absolute_import, division, print_function

import os

import pytest
from hypothesis import settings


@pytest.fixture(scope="session")
def C():
    """
    Return a simple but fully featured attrs class with an x and a y attribute.
    """
    from attr import attributes, attr

    @attributes
    class C(object):
        x = attr()
        y = attr()

    return C
