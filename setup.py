from setuptools import setup, find_packages

setup(
    name="FinanceManagement",
    version="1.0",
    packages=find_packages(),
    install_requires=[
        'cryptography',
        'requests',
        'pandas',
        'matplotlib',
        'tk',
        'bcrypt'
    ],
    entry_points={
        'console_scripts': [
            'financemanagement = finance_management.main:main',
        ],
    },
    include_package_data=True,
)