from SPARQLWrapper import SPARQLWrapper, JSON
from typing import Dict, List
from tqdm import tqdm

sparql = SPARQLWrapper("https://yago-knowledge.org/sparql/query")


def retrieve_id2label(id2entity: Dict[int, str]) -> Dict[int, str]:
    id2label = dict()

    for i, e in tqdm(id2entity.items()):
        label = retrieve_label(e)
        if label:
            id2label[i] = retrieve_label(e)
    return id2label


def retrieve_labels(entities: List[str]) -> Dict[str, str]:
    result = {}
    for e in tqdm(entities):
        label = retrieve_label(e)
        if label:
            result[e] = label

    return result


def retrieve_label(entity: str) -> str:
    # Define the query, including the filter for English labels
    query = (
        """
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    SELECT ?label WHERE {
      <http://yago-knowledge.org/resource/"""
        + entity
        + """> rdfs:label ?label .
      FILTER (lang(?label) = "en")
    }
    """
    )

    # Set the query and the return format
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)

    # Execute the query and fetch the results
    try:
        results = sparql.query().convert()
    except:
        return ""

    if len(results["results"]["bindings"]) >= 1:
        return results["results"]["bindings"][0]["label"]["value"]
    else:
        return ""
