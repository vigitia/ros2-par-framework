# Written by Claude Code
from setuptools import find_packages, setup

package_name = 'projection_corners'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    # Makes colcon test run pytest; without it, it falls back to unittest and finds no tests
    extras_require={'test': ['pytest']},
    zip_safe=True,
    maintainer='vitus',
    maintainer_email='vitus.maierhoefer@gmail.com',
    description='Holds the projection corners and publishes them latched.',
    license='MIT',
    entry_points={
        'console_scripts': [
            'projection_corners = projection_corners.projection_corners_node:main',
        ],
    },
)
