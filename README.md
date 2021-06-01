Wikibase reconciliation interface for OpenRefine 
================================================
i[![Python tests](https://github.com/wetneb/openrefine-wikibase/actions/workflows/tests.yml/badge.svg)](https://github.com/wetneb/openrefine-wikibase/actions/workflows/tests.yml) [![Documentation Status](https://readthedocs.org/projects/openrefine-wikibase/badge/?version=latest)](https://openrefine-wikibase.readthedocs.io/en/latest/?badge=latest) [![Coverage Status](https://coveralls.io/repos/github/wetneb/openrefine-wikidata/badge.svg?branch=master)](https://coveralls.io/github/wetneb/openrefine-wikidata?branch=master)


An instance of this endpoint for Wikidata can be found at:
https://wikidata.reconci.link/en/api

This endpoint is described in the paper ["Running a reconciliation service for Wikidata", Antonin Delpeuch](http://ceur-ws.org/Vol-2773/paper-17.pdf).

This is a new reconciliation interface, with the following features:
* Matching columns with Wikibase properties, to improve the fuzzy
  matching score ;
* Autocomplete for properties and items ;
* Support for SPARQL-like property paths such as "P17/P297" (which fetches the ISO code of the country of an item) ;
* Language selection (use /$lng/api as endpoint, where $lng is your
  language code) ;
* Reconciliation from sitelinks (Wikipedia in the case of Wikidata).

![Screenshot](https://wdreconcile.toolforge.org/static/screenshot_items.png)

MIT license.


