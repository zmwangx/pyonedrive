#!/usr/bin/env python3

import os
import setuptools

here = os.path.dirname(os.path.realpath(__file__))

with open(os.path.join(here, 'README.rst')) as readme:
    long_description = readme.read()

# read version from version.py and save in __version__
with open(os.path.join(here, 'onedrive', 'version.py')) as f:
    exec(f.read())

setuptools.setup(
    name='onedrive',
    version=__version__,
    description='OneDrive API/CLI client',
    long_description=long_description,
    url='https://github.com/zmwangx/pyonedrive',
    author='Zhiming Wang',
    author_email='zmwangx@gmail.com',
    license='MIT',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: End Users/Desktop',
        'Topic :: Internet',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3 :: Only',
    ],
    keywords='onedrive upload',
    packages=['onedrive'],
    install_requires=[
        'arrow',
        'requests',
        'zmwangx>=0.1.39+g4019762',
    ],
    entry_points={
        'console_scripts': [
            'onedrive-auth=onedrive.auth:main',
            'onedrive-cp=onedrive.cli:cli_cp',
            'onedrive-download=onedrive.cli:cli_download',
            'onedrive-geturl=onedrive.cli:cli_geturl',
            'onedrive-metadata=onedrive.cli:cli_metadata',
            'onedrive-mkdir=onedrive.cli:cli_mkdir',
            'onedrive-ls=onedrive.cli:cli_ls',
            'onedrive-mv=onedrive.cli:cli_mv',
            'onedrive-rm=onedrive.cli:cli_rm',
            'onedrive-rmdir=onedrive.cli:cli_rmdir',
            'onedrive-upload=onedrive.cli:cli_upload',
        ]
    },
    dependency_links = [
        'git+https://github.com/zmwangx/pyzmwangx.git@master#egg=zmwangx-0.1.39',
    ],
    test_suite='tests',
)
