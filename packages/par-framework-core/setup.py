# Co-authored by Claude Code
from glob import glob

from setuptools import find_packages, setup

package_name = 'par_framework_core'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        # The camera types whose drivers come from elsewhere: one entry per type, each naming its
        # launch file below (templates/par_camera/)
        ('share/ament_index/resource_index/par_framework_cameras',
            glob('resource/par_framework_cameras/*')),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', glob('launch/*.launch.py')),
        ('share/' + package_name + '/config', glob('config/*.yaml')),
        ('share/' + package_name + '/config/rviz', glob('config/rviz/*.rviz')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='vitus',
    maintainer_email='vitus.maierhoefer@gmail.com',
    description='Launch files and per-setup parameters for the PAR framework.',
    license='MIT',
    entry_points={
        'console_scripts': [],
    },
)
