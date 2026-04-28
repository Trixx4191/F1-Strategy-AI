from setuptools import setup, find_packages

setup(
    name="f1-strategy-ai",
    version="0.1.0",
    description="Monte Carlo F1 race strategy simulator using FastF1",
    author="Your Name",
    python_requires=">=3.11",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "fastf1>=3.3.0",
        "pandas>=2.0.0",
        "numpy>=1.26.0",
        "scikit-learn>=1.4.0",
        "scipy>=1.12.0",
        "matplotlib>=3.8.0",
        "seaborn>=0.13.0",
        "streamlit>=1.32.0",
        "python-dotenv>=1.0.0",
        "tqdm>=4.66.0",
    ],
    extras_require={
        "dev": [
            "pytest>=8.0.0",
            "jupyterlab>=4.0.0",
        ]
    },
)
