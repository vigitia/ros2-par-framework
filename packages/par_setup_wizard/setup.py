# Written by Claude Code
from setuptools import find_packages, setup

package_name = 'par_setup_wizard'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='vitus',
    maintainer_email='vitus.maierhoefer@gmail.com',
    description='Setup wizard for the PAR framework.',
    license='MIT',
    entry_points={
        'console_scripts': [
            'par_setup_wizard = par_setup_wizard.par_setup_wizard:main',
        ],
    },
)
