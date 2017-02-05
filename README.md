Wikidata reconciliation interface for OpenRefine [![Build Status](https://travis-ci.org/wetneb/openrefine-wikidata.svg?branch=master)](https://travis-ci.org/wetneb/openrefine-wikidata)
================================================

An instance of this endpoint can be found at:
https://tools.wmflabs.org/openrefine-wikidata/api

This is a new reconciliation interface, with the following features:
* Matching columns with Wikidata properties, to improve the fuzzy
  matching score
* Relatively fast thanks to redis caching at various places, and few
  calls to the Wikidata API and SPARQL endpoint

TODO:
* Better scoring
* Suggest API
* Label language selection
* Support for other modes of type matching
* Updating the OpenRefine sources to use this interface by default
* Docs

MIT license.

