# syntax=docker/dockerfile:1.3
ARG BASE=""
FROM rclone/rclone AS final
FROM corpusops/alpine-bare AS helpers
FROM $BASE AS run
WORKDIR /w
ADD *txt ./
RUN --mount=type=bind,from=helpers,target=/s bash -exc ': \
      && /s/cops_helpers/infest.sh'
RUN apk update && apk add --no-cache python3 py3-pip && pip install -r requirements.txt
RUN --mount=type=bind,from=final,target=/s bash -exc ': \
  && for i in /usr/local/bin/rclone;do rsync -aAH --numeric-ids /s${i} ${i};done'
ENV PATH=/cops_helpers:$PATH
ENTRYPOINT []
CMD ["bash"]
