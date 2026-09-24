# Written by Claude Code
from setuptools import find_packages, setup

package_name = 'rviz_bridge'

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
    description='Republishes PAR framework outputs as RViz markers.',
    license='MIT',
    entry_points={
        'console_scripts': [
            'rviz_bridge = rviz_bridge.rviz_bridge_node:main',
        ],
    },
)
