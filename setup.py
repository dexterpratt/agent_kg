"""Setup configuration for the agent_kg package."""

import os
from setuptools import setup, find_packages

# Read the README file for the long description
here = os.path.abspath(os.path.dirname(__file__))
try:
    with open(os.path.join(here, 'README.md'), encoding='utf-8') as f:
        long_description = f.read()
except FileNotFoundError:
    long_description = ""

setup(
    name="agent_kg",
    version="0.1.0",
    author="Agent KG Team",
    description="Knowledge Graph MCP Server for Agent Memory Management",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.9",  # For type hint support
    install_requires=[
        "fastmcp>=0.1.0",
        "uvicorn>=0.27.0",
        "psycopg2-binary>=2.9.9",
        "pandas>=2.1.4",
        "python-dotenv>=1.0.0"
    ],
    extras_require={
        'dev': [
            'pytest>=7.0.0',
            'pytest-asyncio>=0.23.0',
            'pytest-cov>=4.1.0',
            'black>=23.0.0',
            'isort>=5.12.0',
            'mypy>=1.5.0',
            'pylint>=3.0.0',
        ],
    },
    entry_points={
        "console_scripts": [
            "agent-kg=agent_kg.main:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Database :: Database Engines/Servers",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Operating System :: OS Independent",
    ],
    keywords="knowledge-graph mcp-server agent-memory postgresql",
    project_urls={
        "Source": "https://github.com/yourusername/agent_kg",  # Update with actual URL
        "Bug Reports": "https://github.com/yourusername/agent_kg/issues",
    },
)
