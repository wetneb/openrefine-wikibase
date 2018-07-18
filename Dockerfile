FROM debian:stable
ENV LANG C.UTF-8

ADD . /openrefine-wikibase

WORKDIR /openrefine-wikibase

RUN apt-get update && apt-get install -qq python3 python3-pip redis-server
RUN pip3 install -r requirements.txt
RUN cp config.py.in config.py

RUN echo never > /sys/kernel/mm/transparent_hugepage/enabled
RUN sysctl vm.overcommit_memory=1

EXPOSE 8000
CMD [ "./entrypoint_docker.sh" ]

