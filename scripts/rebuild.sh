#!/usr/bin/env bash
# 重建派生层：关系索引 / 溯源索引 / 页面快照
set -e
cd "$(dirname "$0")/.."
PYTHONPATH=src python -c "
from capfactory.po import POGraph
from capfactory.sciforge.relation_layer import build_relations
from capfactory.semantic.provenance import build_index, export_missing_csv
from capfactory.applayer.miner import mine_all
g = POGraph.load('storage_cf/sciforge/batch10_semantic_v4.json')
print('snapshot', mine_all(g, task=None, persist=True)['nodes'])
print('relations', build_relations(g, persist=True))
print('provenance', build_index(g))
print('missing_csv', export_missing_csv(g)['n_missing'])
"
