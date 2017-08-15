Wikidata reconciliation interface for OpenRefine 
================================================
[![Build Status](https://travis-ci.org/wetneb/openrefine-wikidata.svg?branch=master)](https://travis-ci.org/wetneb/openrefine-wikidata) [![Coverage Status](https://coveralls.io/repos/github/wetneb/openrefine-wikidata/badge.svg?branch=master)](https://coveralls.io/github/wetneb/openrefine-wikidata?branch=master)

An instance of this endpoint can be found at:
https://tools.wmflabs.org/openrefine-wikidata/en/api

This is a new reconciliation interface, with the following features:
* Matching columns with Wikidata properties, to improve the fuzzy
  matching score ;
* Autocomplete for properties and items ;
* Support for SPARQL-like property paths such as "P17/P297" (which fetches the ISO code of the country of an item) ;
* Language selection (use /$lng/api as endpoint, where $lng is your
  language code) ;
* Reconciliation from Wikipedia links.

TODO (Pull requests welcome!)
* Flyout service ;
* Better scoring ;
* Web-based interface ;
* More optimization for speed.

![Screenshot](https://tools.wmflabs.org/openrefine-wikidata/static/screenshot_items.png)

MIT license.

