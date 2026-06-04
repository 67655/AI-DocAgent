# -*- coding: utf-8 -*-
"""
AI-DocAgent - 通用AI文档结构化处理框架
"""
from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="ai-docagent",
    version="0.1.0",
    author="AI-DocAgent Team",
    description="通用化AI文档解析&自动化结构化处理Agent框架",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/67655/AI-DocAgent",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "docagent=src.main:main",
        ],
    },
)
