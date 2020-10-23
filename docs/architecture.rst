.. _architecture:

Architecture overview
=====================

This service acts as a thin wrapper between the reconciliation client (such as OpenRefine) and the Wikibase instance.
It does not maintain a search index on its own: it relies on the existing search capabilities of the Wikibase instance (via the MediaWiki API) and the SPARQL query service.

A redis instance is used for caching data to avoid making too many queries to the Wikibase instance.

Reconciliation
--------------

Reconciliation queries are processed as follows:
 * The given text (`query` field) is searched for with both search APIs provided the Wikibase instance (the auto-complete API and the search API). For both search endpoints we only look at the first page of results. The results are merged into one list;
 * The contents of each candidate item is retrieved in JSON via the `wbgetentities` API action. Furthermore, the types and any other property used for reconciliation is also fetched on the candidate items (again with `wbgetentities`);
 * Candidates are filtered by type. This is done by fetching the Qids of all the subclasses of the given target type (with SPARQL) and only keeping the candidates whose type is one of these subclasses;
 * The candidates are scored by comparing the values supplied in the query to the values obtained in the previous step;
 * The candidates are sorted by decreasing score and returned to the user.

There are exceptions to this workflow:
 * When Qids or sitelinks are supplied in the `query` field, they are directly looked up accordingly (instead of being searched for with the search APIs);
 * When a unique identifier is supplied as a property, candidates are first fetched by looking for items with the supplied identifiers (via SPARQL), and text search on the query is only used as a fallback.
 * When no type constraint is supplied, an implicit negative type constraint is used instead (to filter out all internal items, which are marked by subclasses of `Wikimedia internal item (Q17442446) <https://www.wikidata.org/wiki/Q17442446>`_.

Calls to the API are done in parallel, up to a limit of maximum concurrent queries to avoid overloading the Wikibase instance.
This means that supplying queries by batch (as allowed by the protocol) can be significantly more efficient than submitting them individually.

Auto-complete (suggest) services
--------------------------------

These services are used to provide auto-complete widgets in user interfaces around the reconciliation process.
The calls to these services are directly translated to the corresponding API actions of the Wikibase instance,
except for properties where the user input is also parsed as a property path beforehand (if the parsing succeeds, the parsed property path is returned as sole candidate).

Preview
-------

Previewing entities is done by fetching data for the corresponding item and displaying a few snippets of information for the item. For Wikidata, the `autodesc service <https://bitbucket.org/magnusmanske/autodesc>`_ is also used to generate a description automatically for the item.

Data extension
--------------

Properties requested on items are fetched in the same way as during reconciliation, by attempting to minimize the calls to the Wikibase instance (batching requested items, caching).
