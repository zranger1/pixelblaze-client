#!/usr/bin/python3
# -*- coding: utf-8 -*-

import setuptools

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name = 'pixelblaze-client',
    version = "1.1.2",
    description = 'Library for Pixelblaze addressable LED controller.',
    long_description=long_description,
    long_description_content_type="text/markdown",
    url = 'https://github.com/zranger1/pixelblaze-client',
    author = 'pixxxie & ZRanger1',
    license='MIT',
    classifiers=[
      "Development Status :: 5 - Production/Stable",
      "License :: OSI Approved :: MIT License",
      "Programming Language :: Python :: 3",
      "Operating System :: OS Independent",
      "Topic :: Software Development :: Libraries :: Python Modules",
      "Topic :: System :: Hardware",
      "Intended Audience :: Developers",
    ],
    keywords = 'pixelblaze',
    install_requires=[
      "websocket-client",
      "requests",
      "pytz",
      "py-mini-racer"
    ],
    packages=["pixelblaze"],
    python_requires='>=3.9',
)
