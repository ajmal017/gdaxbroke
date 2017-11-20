# -*- coding: utf-8 -*-

"""
Setup for GBroke.
"""

from setuptools import setup
import os.path
import re

HERE = os.path.abspath(os.path.dirname(__file__))
try:        # Workaround lack of Markdown support on PyPI
    import pypandoc
    long_description = pypandoc.convert(os.path.join(HERE, 'README.md'), 'rst')
except (IOError, ImportError):
    long_description = open(os.path.join(HERE, 'README.md')).read()


def find_version(*file_paths):
    """:Return: the __version__ string from the path components `file_paths`."""
    with open(os.path.join(os.path.dirname(__file__), *file_paths),'rb') as verfile:
        file_contents = verfile.read().decode('utf-8')
    version_match = re.search(r"^__version__ = ['\"]([^'\"]*)['\"]", file_contents, re.M)
    if version_match:
        return version_match.group(1)
    raise RuntimeError("Unable to find version string.")

setup(
    name='GBroke',
    version=find_version('gbroke.py'),
    description='Interactive Brokers for Humans',
    long_description=long_description,
    url='https://github.com/kanghua309/gdaxbroke',
    author='kanghua',
    license='LGPL-3.0+',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Topic :: Office/Business :: Financial :: Investment',
        'License :: OSI Approved :: GNU Lesser General Public License v3 or later (LGPLv3+)',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
    ],
    keywords='interactive brokers tws api finance trading',
    py_modules=['gbroke'],
    install_requires=['pytz', 'ciso8601'],
    dependency_links=[
        'git+git://github.com/kanghua309/gdax-python/archive/master.zip#egg=private-gdax',
    ],
    extras_require={'dev': ['pypandoc'],},
    package_data={},
)
