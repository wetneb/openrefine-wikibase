import re

q_re = re.compile(r'(<?http://www.wikidata.org/entity/)?(Q[0-9]+)>?')

def to_q(url):
    """
    Normalizes a Wikidata identifier

    >>> to_q('Q1234')
    u'Q1234'
    >>> to_q('<http://www.wikidata.org/entity/Q801> ')
    u'Q801'
    """
    match = q_re.match(url.strip())
    if match:
        return match.group(2)

