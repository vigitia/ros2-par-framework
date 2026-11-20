# Written by Claude Code
from glob import glob

from setuptools import setup

package_name = 'par_camera_adapters'

setup(
    name=package_name,
    version='0.1.0',
    packages=[],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        # The camera types whose drivers come from elsewhere: one entry per type, each naming its
        # launch file below (templates/par_camera/)
        ('share/ament_index/resource_index/par_framework_cameras',
            glob('resource/par_framework_cameras/*')),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', glob('launch/*.launch.py')),
        # The camera types' default parameters (parameters_file in their entries)
        ('share/' + package_name + '/config', glob('config/*.yaml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='vitus',
    maintainer_email='vitus.maierhoefer@gmail.com',
    description='Camera types of the PAR framework for third-party ROS 2 camera drivers.',
    license='MIT',
)
