Wikibase reconciliation interface for OpenRefine 
================================================
[![Build Status](https://travis-ci.org/wetneb/openrefine-wikibase.svg?branch=master)](https://travis-ci.org/wetneb/openrefine-wikibase) [![Coverage Status](https://coveralls.io/repos/github/wetneb/openrefine-wikidata/badge.svg?branch=master)](https://coveralls.io/github/wetneb/openrefine-wikidata?branch=master)

An instance of this endpoint for Wikidata can be found at:
https://tools.wmflabs.org/openrefine-wikidata/en/api

This is a new reconciliation interface, with the following features:
* Matching columns with Wikibase properties, to improve the fuzzy
  matching score ;
* Autocomplete for properties and items ;
* Support for SPARQL-like property paths such as "P17/P297" (which fetches the ISO code of the country of an item) ;
* Language selection (use /$lng/api as endpoint, where $lng is your
  language code) ;
* Reconciliation from sitelinks (Wikipedia in the case of Wikidata).

TODO (Pull requests welcome!)
* Better scoring ;
* Web-based interface ;
* More optimization for speed.

![Screenshot](https://tools.wmflabs.org/openrefine-wikidata/static/screenshot_items.png)

MIT license.

Running with Docker
-------------------

You can run this service with Docker:
```
docker pull pintoch/openrefine-wikibase
docker run pintoch/openrefine-wikibase
```

On Windows you will need to expose the port so that get the Windows Firewall popup to accept on:
```
docker run -p 8000:8000 pintoch/openrefine-wikibase
```

Running manually
----------------

It is possible to run this web service locally. You will need Python 3 and a redis instance.

* Clone this repository, either with git (`git clone https://github.com/wetneb/openrefine-wikibase`) or by downloading the repository from Github as an archive
* It is recommended to set up a virtualenv to isolate the dependencies of the software from the other python packages installed on your computer. On a UNIX system, `virtualenv .venv` and `source .venv/bin/activate` will do. On a Windows system, `python.exe
  -m venv venv` followed by `venvname\Scripts\activate` should work.
* Install the Python dependencies with `pip install -r requirements.txt`
* Copy the configuration file: `cp config.py.in config.py` (`copy config.py.in config.py` on Windows)
* Edit the configuration file `config.py` so that `redis_client` contains the correct settings to access your redis instance. The default parameters should be fine if you are running redis locally on the default port.
* Finally, run the instance with `python app.py`. The service will be available at `http://localhost:8000/en/api`.


On Debian-based systems, it looks as follows:
```
sudo apt-get install git redis-server python3 virtualenv
git clone https://github.com/wetneb/openrefine-wikibase
cd openrefine-wikibase
virtualenv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config.py.in config.py
python app.py
```


