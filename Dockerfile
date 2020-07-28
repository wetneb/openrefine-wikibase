FROM python:3.7-alpine

WORKDIR /openrefine-wikibase

RUN apk add --no-cache gcc musl-dev linux-headers libffi-dev
COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt

ADD . /openrefine-wikibase

EXPOSE 8000
CMD [ "python", "app.py" ]
