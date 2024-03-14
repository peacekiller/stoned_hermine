FROM python:3.12-bookworm

RUN mkdir -p /stoned-hermine/changelogs
WORKDIR /stoned-hermine

COPY *.py /stoned-hermine/
COPY config.example.ini /stoned-hermine/config.ini
COPY changelogs/* /stoned-hermine/changelogs/

VOLUME config:/stoned-hermine/config.ini
COPY config.example.ini /stoned-hermine/config.ini

RUN apt-get update && apt-get install -y python3-pip
COPY requirements.txt /tmp/requirements.txt

RUN python -m venv .venv
RUN pip install -r /tmp/requirements.txt

COPY create_config.sh /stoned-hermine
RUN chmod +x create_config.sh
RUN ./create_config.sh

RUN chmod +x StonedHermine.py
ENTRYPOINT python StonedHermine.py