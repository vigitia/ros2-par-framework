# syntax=docker/dockerfile:1
#
# Runtime environment for the PAR framework: ROS 2 plus every dependency the
# node repositories declare. It deliberately contains NO node source -- src/ is
# cloned on the host by scripts/sync_nodes.sh and bind-mounted at /ros2_ws/src,
# so editing a node needs a colcon build, not an image rebuild.

ARG ROS_DISTRO=lyrical

FROM osrf/ros:${ROS_DISTRO}-desktop AS base
ARG ROS_DISTRO
ENV DEBIAN_FRONTEND=noninteractive
ENV ROS_WS=/ros2_ws

RUN mkdir -p ${ROS_WS}/src
WORKDIR ${ROS_WS}

RUN apt-get update && apt-get install -y --no-install-recommends \
        v4l-utils \
        python3-pip \
        python3-colcon-common-extensions \
    && rm -rf /var/lib/apt/lists/*

# Only the dependency manifests (package.xml / requirements.txt) of every
# workspace package, staged into docker/deps/ by scripts/sync_nodes.sh. Copying
# manifests instead of whole repos is what keeps the two slow layers below out
# of the edit-build loop: they are only invalidated when a declared dependency
# changes, not when node code does.
COPY docker/deps/ /tmp/deps/

# ROS and apt dependencies from every package.xml.
RUN apt-get update && \
    rosdep update --rosdistro ${ROS_DISTRO} && \
    rosdep install --from-paths /tmp/deps --ignore-src -y --rosdistro ${ROS_DISTRO} && \
    rm -rf /var/lib/apt/lists/*

# PyPI dependencies from every requirements.txt. All files go into a single pip
# invocation so the resolver sees all constraints at once: if two nodes pin
# conflicting versions the build fails here, instead of one node silently
# upgrading a package another one depends on.
RUN --mount=type=cache,target=/root/.cache/pip \
    find /tmp/deps -maxdepth 2 -name requirements.txt -printf '-r\0%p\0' | \
    xargs -0 -r python3 -m pip install --break-system-packages

COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Interactive shells get the same environment the entrypoint sets up.
RUN echo "source /opt/ros/${ROS_DISTRO}/setup.bash" >> /root/.bashrc && \
    echo "[ -f ${ROS_WS}/install/local_setup.bash ] && source ${ROS_WS}/install/local_setup.bash" >> /root/.bashrc && \
    echo "cd ${ROS_WS}" >> /root/.bashrc

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["bash"]
