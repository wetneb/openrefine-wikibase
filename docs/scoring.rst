.. _page-scoring:

Scoring mechanism
=================

This page describes how the scores of reconciliation candidates are computed.

Stability
---------

The scoring mechanism used in this reconciliation service can change, the specifics of its computation should not be relied on by users.
Instead, we recommend that `individual scoring features <https://reconciliation-api.github.io/specs/latest/#dfn-matching-feature>`_ are used instead.

Global matching formula
-----------------------

The score of each candidate is obtained as a weighted sum of the scores of individual features. It ranges from 0 to 100.
When no candidates can be found matching the target type, candidates of wrong or no types are also returned, with their score divided by two.

Name matching
-------------

Two names (such as an item label and a query) are matched by token-based fuzzy matching.

Identifier matching
-------------------

Values of properties which hold identifiers are matched to the queries using exact string equality (100 score if the strings are equal, 0 otherwise).

Geographical coordinate matching
--------------------------------

Geographical coordinates are expected to be supplied in `lat,long` format (such as `53.3175,-4.6204`). The matching score 
peaks at 100 when the position is exactly the same and decreases linearly as the distance between the points increase,
reaching 0 when the points are 1 km apart.

Date matching
-------------

The precision of Wikibase dates is taken into account when matching them against strings. Query dates are expected to be supplied in ISO format (YYYY-MM-DD) and will match the Wikibase date perfectly if they fall into the range described by the precision.
It is also possible to supply query dates in YYYY-MM or YYYY format.

Quantity matching
-----------------

Integer quantities are matched (score 100) if they are equal, and have a 0 score otherwise.
For floating-point numbers, the score peaks at 100 for exact equality and follows otherwise this formula:


URL matching
------------

URLs are canonicalized before being matched. Differences in scheme (HTTPS vs HTTP) are ignored.
