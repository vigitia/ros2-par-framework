# Written by Claude Code
from glob import glob

from setuptools import find_packages, setup

package_name = 'example_app'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        # Every package: registers it as installed
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        # A PAR app: registers it in the framework's app list, with its entry as the content
        ('share/ament_index/resource_index/par_framework_apps',
            ['resource/par_framework_apps/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        # Only with launch_file in the entry
        ('share/' + package_name + '/launch', glob('launch/*.launch.py')),
        # Only for an app that serves a web frontend: the built files (npm run build), see the
        # launch file. data_files copies no subfolders, so each one needs its own line; these
        # two are what Vite builds
        ('share/' + package_name + '/frontend', glob('frontend/dist/*.*')),
        ('share/' + package_name + '/frontend/assets', glob('frontend/dist/assets/*')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='vitus',
    maintainer_email='vitus.maierhoefer@gmail.com',
    description='One sentence on what the app shows on the table.',
    entry_points={
        'console_scripts': [
            'example_app = example_app.example_app_node:main',
        ],
    },
)
