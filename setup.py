"""
Setup for IBroke.
"""

from setuptools import setup
from os import path
_readme = path.join(path.abspath(path.dirname(__file__)), 'README.md')
try:        # Workaround lack of Markdown support on PyPI
    import pypandoc
    long_description = pypandoc.convert(_readme, 'rst')
except (IOError, ImportError):
    long_description = open(_readme).read()


__version__ = "0.0.2"


setup(
    name='IBroke',
    version=__version__,
    description='Interactive Brokers for Humans',
    long_description=long_description,
    url='https://gitlab.com/doctorj/ibroke',
    author='Doctor J',
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
    py_modules=['ibroke'],
    install_requires=['ibpy2'],
    extras_require={'dev': ['pypandoc'],},
    package_data={},
)
