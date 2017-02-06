
# TODO add language fallback graph
# https://translatewiki.net/docs/Translate/html/fallbacks-graph_8php_source.html

def language_fallback(dct, target_language):
    """
    Finds the most appropriate text given a target
    language and a dict of values
    """
    if not dct:
        return
    if not target_language:
        target_language = 'en'
    if target_language in dct:
        return dct[target_language]
    return dct.get('en')

