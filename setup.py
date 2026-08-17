"""
Porter - Cloudflare Tunnel Portal CLI
Install with: pip install -e .
"""

from setuptools import setup, find_packages

setup(
    name="porter-cli",
    version="2.0.0",
    description="CLI for Cloudflare Tunnel Portal",
    long_description=open("README.md").read() if __import__("os").path.exists("README.md") else "",
    long_description_content_type="text/markdown",
    author="Tect0nic",
    url="https://github.com/yourusername/porter",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[
        "httpx>=0.25",
    ],
    entry_points={
        "console_scripts": [
            "porter=porter.cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Topic :: System :: Networking",
    ],
)
