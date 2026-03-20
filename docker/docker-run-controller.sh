#!/bin/bash

# -v "${HOME}":/home/user/ \

docker run \
--cap-add=SYS_ADMIN \
--device /dev/snd \
--device /dev/dri \
-e "DISPLAY=unix$DISPLAY" \
-e "SSH_AUTH_SOCK=${SSH_AUTH_SOCK}" \
--mount type=bind,src="${SSH_AUTH_SOCK}",target="${SSH_AUTH_SOCK}" \
--log-driver json-file \
--log-opt max-size=10m \
-v /dev/log:/dev/log \
-v /etc/localtime:/etc/localtime \
-v "${HOME}":/mnt/ \
-v /tmp/.X11-unix:/tmp/.X11-unix \
-h controller \
--net host \
--name controller \
--rm -ti \
auto-controller /bin/zsh

# -v "${HOME}"/.ssh:/home/user/.ssh/ \
