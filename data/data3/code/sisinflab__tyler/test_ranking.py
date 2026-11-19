import os
import re
import random
import argparse
import logging
import json
import time
from collections import defaultdict
import scipy.sparse as ssp
from tqdm import tqdm
import networkx as nx
import torch
import numpy as np
import dgl

from ITLP.utils import compute_logits_emb, enable_determinism

def compute_edge_count_percentile_metrics(ranks_edges, ranks, edge_count_percentiles):
    # Step 3: Bin indices based on edge counts
    ranks_edges = np.array(ranks_edges)
    ranks = np.array(ranks)
    bins = [
        ranks_edges <= edge_count_percentiles[0],                               # 0–25%
        (ranks_edges > edge_count_percentiles[0]) & (ranks_edges <= edge_count_percentiles[1]),  # 25–50%
        (ranks_edges > edge_count_percentiles[1]) & (ranks_edges <= edge_count_percentiles[2]),  # 50–75%
        ranks_edges > edge_count_percentiles[2],                                # 75–100%
    ]

    # Step 4: Compute results for each bin
    results_by_bin = {}
    for i, mask in enumerate(bins):
        bin_ranks = np.array(ranks)[mask]
        results_by_bin[i] = compute_ranking_metrics(bin_ranks.tolist())
    
    return results_by_bin


def get_triples(g, id2entity_, id2relation_):
    triples = []
    for (
        etype
    ) in g.etypes:  # etypes gives the list of edge types, e.g., 'follows', 'writes'
        # Get source and destination node indices for the current edge type
        src, dst = g.edges(etype=etype)
        # Get the source and destination node types
        src_type, dst_type = (
            g.to_canonical_etype(etype)[0],
            g.to_canonical_etype(etype)[2],
        )
        # Fetch the actual node IDs using the '_ID' node data (custom IDs)
        src_ids = g.nodes[src_type].data["_ID"][src]
        dst_ids = g.nodes[dst_type].data["_ID"][dst]
        # Fetch the relation IDs stored in edge data
        relation_types = g.edges[etype].data[
            "type"
        ]  # Assuming edge data contains 'relation_id'
        # Add the triples (source_id, relation_id, destination_id)
        relation_ids = g.edges[etype].data["_ID"]

        for s, d, r, i in zip(src_ids, dst_ids, relation_types, relation_ids):
            if i != 0:
                triples.append(
                    (id2entity_[s.item()], id2relation_[r.item()], id2entity_[d.item()])
                )  # r.item() is the actual relation ID
    return triples


def aggregate_results(results_list):
    # Initialize structures for accumulation
    global_accumulator = defaultdict(list)
    type_accumulator = defaultdict(lambda: defaultdict(list))
    edge_accumulator = defaultdict(lambda: defaultdict(list))

    # Step 1: Accumulate all values
    for result in results_list:
        # Global metrics
        for metric, val in result["global_metrics"].items():
            global_accumulator[metric].append(val)

        # Type metrics
        for t, metrics in result["type_metrics"].items():
            for metric, val in metrics.items():
                type_accumulator[t][metric].append(val)

        for t, metrics in result["edge_metrics"].items():
            for metric, val in metrics.items():
                edge_accumulator[t][metric].append(val)


    # Step 2: Compute mean and std for global metrics
    global_stats = {
        metric: {
            "mean": float(np.mean(vals)),
            "std": float(np.std(vals))
        }
        for metric, vals in global_accumulator.items()
    }

    # Step 3: Compute mean and std for type metrics
    type_stats = {
        t: {
            metric: {
                "mean": float(np.mean(vals)),
                "std": float(np.std(vals))
            }
            for metric, vals in metrics.items()
        }
        for t, metrics in type_accumulator.items()
    }

    edge_stats = {
        t: {
            metric: {
                "mean": float(np.mean(vals)),
                "std": float(np.std(vals))
            }
            for metric, vals in metrics.items()
        }
        for t, metrics in edge_accumulator.items()
    }

    return {
        "global_metrics": global_stats,
        "type_metrics": type_stats,
        "edge_metrics": edge_stats
    }

def assign_type_categories(entity_dict):
    """
    Assigns each entity to one of six categories based on its number_of_links,
    then returns two objects:
      1) Dictionary {entity_id: category}
      2) Dictionary {category: count_of_entities_in_that_category}

    Categories:
      - 0 -> 0 links
      - 1 -> 1 link
      - 2..5 -> quartiles among entities with >= 2 links

    Parameters
    ----------
    entity_dict : dict
        Dictionary mapping {entity_id: number_of_links}.

    Returns
    -------
    (result_dict, counts_dict) : (dict, dict)
        - result_dict: {entity_id: category}
        - counts_dict: {category: number_of_entities}
    """
    # 1. Convert dictionary values to a NumPy array for percentile computations
    link_counts = np.array(list(entity_dict.values()))
    rest_mask = (link_counts >= 2)  # Entities that have 2 or more links

    # 2. Check if any entities have >=2 links (for quartile calculation)
    if not np.any(rest_mask):
        # No quartiles to compute; all are either 0 or 1 links
        result_dict = {}
        for e, c in entity_dict.items():
            if c == 0:
                result_dict[e] = 0
            elif c == 1:
                result_dict[e] = 1
            else:
                # Optional: handle unexpected values gracefully
                result_dict[e] = None

        # Summarize the category counts
        counts_dict = {}
        for cat in result_dict.values():
            counts_dict[cat] = counts_dict.get(cat, 0) + 1

        return result_dict, counts_dict

    # 3. Extract subset for quartile computation (counts >= 2)
    rest_counts = link_counts[rest_mask]
    q1 = np.percentile(rest_counts, [50])

    # 4. Helper function to determine category
    def get_category(count):
        if count == 0:
            return 0
        elif count == 1:
            return 1
        else:
            if count <= q1:
                return 2
            else:
                return 3

    # 5. Create the result mapping {entity_id: category}
    result_dict = {}
    for e_id, c in entity_dict.items():
        result_dict[e_id] = get_category(c)

    # 6. Count how many entities fall into each category
    counts_dict = {}
    for cat in result_dict.values():
        counts_dict[cat] = counts_dict.get(cat, 0) + 1

    # 7. Return both dictionaries
    return result_dict, counts_dict


def compute_ranking_metrics(ranks):
    isHit1List = [x for x in ranks if x <= 1]
    isHit5List = [x for x in ranks if x <= 5]
    isHit10List = [x for x in ranks if x <= 10]
    hits_1 = len(isHit1List) / len(ranks) if len(ranks) > 0 else 0
    hits_5 = len(isHit5List) / len(ranks) if len(ranks) > 0 else 0
    hits_10 = len(isHit10List) / len(ranks) if len(ranks) > 0 else 0

    mrr = np.mean(1 / np.array(ranks))
    return {
        "hits_1": hits_1,
        "hits_5": hits_5,
        "hits_10": hits_10,
        "mrr": mrr,
        "support": len(ranks)
    }


def process_files(
    files,
    onto_files,
    type_files,
    saved_data2id,
    add_traspose_rels,
    use_test_subgraph=False,
):
    """
    files: Dictionary map of file paths to read the triplets from.
    onto_files: Dictionary map of file paths to read the ontology triplets from.
    type_file: Dictionary map of file paths to read the type information from.
    saved_relation2id: Saved relation2id (mostly passed from a trained model) which can be used to map relations to pre-defined indices and filter out the unknown ones.
    """

    adj_list_onto = None
    triplets_onto = None
    onto2id = None
    id2onto = None
    meta2id = None
    id2meta = None
    m_e2o = None

    entity2id = {}
    relation2id = saved_data2id[0]

    triplets = {}

    ent = 0
    # rel = 0

    for file_type, file_path in files.items():

        data = []
        with open(file_path) as f:
            file_data = [line.split() for line in f.read().split("\n")[:-1]]

        if file_type == "graph" and params.dataset in ["yago", "db"]:
            file_data = []
        for triplet in file_data:
            if len(file_data) == 0:
                data = []
                break
            if triplet[0] not in entity2id:
                entity2id[triplet[0]] = ent
                ent += 1
            if triplet[2] not in entity2id:
                entity2id[triplet[2]] = ent
                ent += 1

            # Save the triplets corresponding to only the known relations
            if triplet[1] in relation2id:
                data.append(
                    [
                        entity2id[triplet[0]],
                        entity2id[triplet[2]],
                        relation2id[triplet[1]],
                    ]
                )

        triplets[file_type] = np.array(data)

    id2entity = {v: k for k, v in entity2id.items()}
    id2relation = {v: k for k, v in relation2id.items()}

    # Construct the list of adjacency matrix each corresponding to eeach relation. Note that this is constructed only from the train data.
    adj_list = []
    adj_list_all = []
    for i in range(len(relation2id)):
        if len(triplets["graph"]) > 0:
            idx = np.argwhere(triplets["graph"][:, 2] == i)
            adj_list.append(
                ssp.csc_matrix(
                    (
                        np.ones(len(idx), dtype=np.uint8),
                        (
                            triplets["graph"][:, 0][idx].squeeze(1),
                            triplets["graph"][:, 1][idx].squeeze(1),
                        ),
                    ),
                    shape=(len(entity2id), len(entity2id)),
                )
            )
            a = ssp.csc_matrix(
                (
                    np.ones(len(idx), dtype=np.uint8),
                    (
                        triplets["graph"][:, 0][idx].squeeze(1),
                        triplets["graph"][:, 1][idx].squeeze(1),
                    ),
                ),
                shape=(len(entity2id), len(entity2id)),
            )
        else:
            a = None
        c = a
        if use_test_subgraph:

            idx_t = np.argwhere(triplets["links"][:, 2] == i)
            b = ssp.csc_matrix(
                (
                    np.ones(len(idx_t), dtype=np.uint8),
                    (
                        triplets["links"][:, 0][idx_t].squeeze(1),
                        triplets["links"][:, 1][idx_t].squeeze(1),
                    ),
                ),
                shape=(len(entity2id), len(entity2id)),
            )
            if a is not None:
                c = a + b
            else:
                c = b
        adj_list_all.append(c)
    # Add transpose matrices to handle both directions of relations.
    adj_list_aug = adj_list
    if add_traspose_rels:
        adj_list_t = [adj.T for adj in adj_list]
        adj_list_aug = adj_list + adj_list_t

    if a is not None:
        dgl_adj_list = ssp_multigraph_to_dgl(adj_list_aug)
    else:
        dgl_adj_list = None
    adj_list_all_aug = adj_list_all
    if add_traspose_rels:
        adj_list_all_t = [adj.T for adj in adj_list_all]
        adj_list_all_aug = adj_list_all + adj_list_all_t

    dgl_adj_list_all = ssp_multigraph_to_dgl(adj_list_all_aug)


#  ------  type sparsity computation

    # test entities
    test_entities = np.union1d(triplets["links"][:, 0], triplets["links"][:, 1])

    # Read the type test mapping file
    with open(type_files["type_test"], "r") as file:
        lines = file.readlines()
    type_test = np.array([(line.split(" type ")[0], line.split(" type ")[1].strip()) for line in lines])

    entity2ntypes = {} # number of types for each entity

    for e in test_entities:
        e_label = id2entity[e]
        entity2ntypes[e] = sum(type_test[:, 0] == e_label)

    entity2type_percentile, category_count = assign_type_categories(entity2ntypes)



    if len(saved_data2id) > 1:
        onto2id = saved_data2id[1]
        meta2id = saved_data2id[2]
        triplets_onto = {}

        for file_type, file_path in onto_files.items():

            data_onto = []
            with open(file_path) as f:
                file_data = [line.split() for line in f.read().split("\n")[:-1]]

            for triplet in file_data:
                # Save the triplets corresponding to only the known relations
                if (
                    triplet[1] in meta2id
                    and triplet[0] in onto2id
                    and triplet[2] in onto2id
                ):
                    data_onto.append(
                        [onto2id[triplet[0]], onto2id[triplet[2]], meta2id[triplet[1]]]
                    )

            triplets_onto[file_type] = np.array(data_onto)

        id2onto = {v: k for k, v in onto2id.items()}
        id2meta = {v: k for k, v in meta2id.items()}

        # Construct the list of adjacency matrix each corresponding to each meta relation. Note that this is constructed only from the onto data.
        adj_list_onto = []
        for i in range(len(meta2id)):
            idx = np.argwhere(triplets_onto["onto"][:, 2] == i)
            adj_list_onto.append(
                ssp.csc_matrix(
                    (
                        np.ones(len(idx), dtype=np.uint8),
                        (
                            triplets_onto["onto"][:, 0][idx].squeeze(1),
                            triplets_onto["onto"][:, 1][idx].squeeze(1),
                        ),
                    ),
                    shape=(len(onto2id), len(onto2id)),
                )
            )

        # Establish the mapping relationship between entities and their corresponding concepts. Based on all data.
        entity2onto = {}
        for file_type, file_path in type_files.items():
            with open(file_path) as f:
                file_data = [line.split() for line in f.read().split("\n")[:-1]]
            for triplet in file_data:
                if triplet[0] in entity2id and triplet[2] in onto2id:
                    ent_id = entity2id[triplet[0]]
                    onto_id = onto2id[triplet[2]]
                    if ent_id in entity2onto:
                        if onto_id not in entity2onto[ent_id]:
                            entity2onto[ent_id].append(onto_id)
                    else:
                        entity2onto[ent_id] = [onto_id]
        m_e2o = np.ones([len(entity2id), len(id2onto)]) * len(id2onto)
        for enti, ont in entity2onto.items():
            ont = np.array(ont)
            m_e2o[enti][: ont.shape[0]] = ont
        print("Construct matrix of entity2onto done!")
    # default = "meta-llama/Llama-2-7b-hf",

    return (
        adj_list,
        dgl_adj_list,
        adj_list_all,
        dgl_adj_list_all,
        triplets,
        entity2id,
        relation2id,
        id2entity,
        id2relation,
        adj_list_onto,
        triplets_onto,
        onto2id,
        id2onto,
        meta2id,
        id2meta,
        m_e2o,
        entity2type_percentile
    )


#def intialize_worker(
#    model,
#    adj_list_all,
#    dgl_adj_list_all,
#    id2entity,
#    entity2onto,
#    params,
#    node_features,
#    kge_entity2id,
#    id2relation,
#):
#    global model_, adj_list_all_, dgl_adj_list_all_, id2entity_, entity2onto_, params_, node_features_, kge_entity2id_, id2relation_
#
#    (
#
#    ) = (
#        model,
#        adj_list_all,
#        dgl_adj_list_all,
#        id2entity,
#        entity2onto,
#        params,
#        node_features,
#        kge_entity2id,
#        id2relation,
#    )
#

def get_neg_samples_replacing_head_tail(test_links, adj_list, num_samples=50):
    n, r = adj_list[0].shape[0], len(adj_list)
    heads, tails, rels = test_links[:, 0], test_links[:, 1], test_links[:, 2]

    neg_triplets = []
    for i, (head, tail, rel) in enumerate(zip(heads, tails, rels)):
        neg_triplet = {"head": [[], 0], "tail": [[], 0]}
        neg_triplet["head"][0].append([head, tail, rel])
        while len(neg_triplet["head"][0]) < num_samples:
            neg_head = head
            neg_tail = np.random.choice(n)

            if neg_head != neg_tail and adj_list[rel][neg_head, neg_tail] == 0:
                neg_triplet["head"][0].append([neg_head, neg_tail, rel])

        neg_triplet["tail"][0].append([head, tail, rel])
        while len(neg_triplet["tail"][0]) < num_samples:
            neg_head = np.random.choice(n)
            neg_tail = tail
            # neg_head, neg_tail, rel = np.random.choice(n), np.random.choice(n), np.random.choice(r)

            if neg_head != neg_tail and adj_list[rel][neg_head, neg_tail] == 0:
                neg_triplet["tail"][0].append([neg_head, neg_tail, rel])

        neg_triplet["head"][0] = np.array(neg_triplet["head"][0])
        neg_triplet["tail"][0] = np.array(neg_triplet["tail"][0])

        neg_triplets.append(neg_triplet)

    return neg_triplets


def get_neg_samples_replacing_head_tail_all(test_links, adj_list):
    n, r = adj_list[0].shape[0], len(adj_list)
    heads, tails, rels = test_links[:, 0], test_links[:, 1], test_links[:, 2]

    neg_triplets = []
    print("sampling negative triplets...")
    for i, (head, tail, rel) in tqdm(
        enumerate(zip(heads, tails, rels)), total=len(heads)
    ):
        neg_triplet = {"head": [[], 0], "tail": [[], 0]}
        neg_triplet["head"][0].append([head, tail, rel])
        for neg_tail in range(n):
            neg_head = head

            if neg_head != neg_tail and adj_list[rel][neg_head, neg_tail] == 0:
                neg_triplet["head"][0].append([neg_head, neg_tail, rel])

        neg_triplet["tail"][0].append([head, tail, rel])
        for neg_head in range(n):
            neg_tail = tail

            if neg_head != neg_tail and adj_list[rel][neg_head, neg_tail] == 0:
                neg_triplet["tail"][0].append([neg_head, neg_tail, rel])

        neg_triplet["head"][0] = np.array(neg_triplet["head"][0])
        neg_triplet["tail"][0] = np.array(neg_triplet["tail"][0])

        neg_triplets.append(neg_triplet)

    return neg_triplets


def incidence_matrix(adj_list):
    """
    adj_list: List of sparse adjacency matrices
    """

    rows, cols, dats = [], [], []
    dim = adj_list[0].shape
    for adj in adj_list:
        adjcoo = adj.tocoo()
        rows += adjcoo.row.tolist()
        cols += adjcoo.col.tolist()
        dats += adjcoo.data.tolist()
    row = np.array(rows)
    col = np.array(cols)
    data = np.array(dats)
    return ssp.csc_matrix((data, (row, col)), shape=dim)


def _bfs_relational(adj, roots, max_nodes_per_hop=None):
    """
    BFS for graphs with multiple edge types. Returns list of level sets.
    Each entry in list corresponds to relation specified by adj_list.
    Modified from dgl.contrib.data.knowledge_graph to node accomodate sampling
    """
    visited = set()
    current_lvl = set(roots)

    next_lvl = set()

    while current_lvl:

        for v in current_lvl:
            visited.add(v)

        next_lvl = _get_neighbors(adj, current_lvl)
        next_lvl -= visited  # set difference

        if max_nodes_per_hop and max_nodes_per_hop < len(next_lvl):
            next_lvl = set(random.sample(next_lvl, max_nodes_per_hop))

        yield next_lvl

        current_lvl = set.union(next_lvl)


def _get_neighbors(adj, nodes):
    """Takes a set of nodes and a graph adjacency matrix and returns a set of neighbors.
    Directly copied from dgl.contrib.data.knowledge_graph"""
    sp_nodes = _sp_row_vec_from_idx_list(list(nodes), adj.shape[1])
    sp_neighbors = sp_nodes.dot(adj)
    neighbors = set(ssp.find(sp_neighbors)[1])  # convert to set of indices
    return neighbors


def _sp_row_vec_from_idx_list(idx_list, dim):
    """Create sparse vector of dimensionality dim from a list of indices."""
    shape = (1, dim)
    data = np.ones(len(idx_list))
    row_ind = np.zeros(len(idx_list))
    col_ind = list(idx_list)
    return ssp.csr_matrix((data, (row_ind, col_ind)), shape=shape)


def get_neighbor_nodes(roots, adj, h=1, max_nodes_per_hop=None):
    bfs_generator = _bfs_relational(adj, roots, max_nodes_per_hop)
    lvls = list()
    for _ in range(h):
        try:
            lvls.append(next(bfs_generator))
        except StopIteration:
            pass
    return set().union(*lvls)


def subgraph_extraction_labeling(
    ind,
    rel,
    A_list,
    h=1,
    enclosing_sub_graph=False,
    max_nodes_per_hop=None,
    node_information=None,
    max_node_label_value=None,
):
    # extract the h-hop enclosing subgraphs around link 'ind'
    A_incidence = incidence_matrix(A_list)
    A_incidence += A_incidence.T

    # could pack these two into a function
    root1_nei = get_neighbor_nodes(set([ind[0]]), A_incidence, h, max_nodes_per_hop)
    root2_nei = get_neighbor_nodes(set([ind[1]]), A_incidence, h, max_nodes_per_hop)

    subgraph_nei_nodes_int = root1_nei.intersection(root2_nei)
    subgraph_nei_nodes_un = root1_nei.union(root2_nei)

    # Extract subgraph | Roots being in the front is essential for labelling and the model to work properly.
    if enclosing_sub_graph:
        subgraph_nodes = list(ind) + list(subgraph_nei_nodes_int)
    else:
        subgraph_nodes = list(ind) + list(subgraph_nei_nodes_un)

    subgraph = [adj[subgraph_nodes, :][:, subgraph_nodes] for adj in A_list]

    labels, enclosing_subgraph_nodes = node_label_new(
        incidence_matrix(subgraph), max_distance=h
    )

    pruned_subgraph_nodes = np.array(subgraph_nodes)[enclosing_subgraph_nodes].tolist()
    pruned_labels = labels[enclosing_subgraph_nodes]

    if max_node_label_value is not None:
        pruned_labels = np.array(
            [
                np.minimum(label, max_node_label_value).tolist()
                for label in pruned_labels
            ]
        )
    # if len(pruned_subgraph_nodes) > 2:
    #    print(ind)
    return pruned_subgraph_nodes, pruned_labels


def remove_nodes(A_incidence, nodes):
    idxs_wo_nodes = list(set(range(A_incidence.shape[1])) - set(nodes))
    return A_incidence[idxs_wo_nodes, :][:, idxs_wo_nodes]


def node_label_new(subgraph, max_distance=1):
    # an implementation of the proposed double-radius node labeling (DRNd   L)
    roots = [0, 1]
    sgs_single_root = [remove_nodes(subgraph, [root]) for root in roots]
    dist_to_roots = [
        np.clip(
            ssp.csgraph.dijkstra(
                sg, indices=[0], directed=False, unweighted=True, limit=1e6
            )[:, 1:],
            0,
            1e7,
        )
        for r, sg in enumerate(sgs_single_root)
    ]
    dist_to_roots = np.array(
        list(zip(dist_to_roots[0][0], dist_to_roots[1][0])), dtype=int
    )

    # dist_to_roots[np.abs(dist_to_roots) > 1e6] = 0
    # dist_to_roots = dist_to_roots + 1
    target_node_labels = np.array([[0, 1], [1, 0]])
    labels = (
        np.concatenate((target_node_labels, dist_to_roots))
        if dist_to_roots.size
        else target_node_labels
    )

    enclosing_subgraph_nodes = np.where(np.max(labels, axis=1) <= max_distance)[0]
    return labels, enclosing_subgraph_nodes


def ssp_multigraph_to_dgl(graph, n_feats=None):
    """
    Converting ssp multigraph (i.e. list of adjs) to dgl multigraph.
    """

    g_nx = nx.MultiDiGraph()
    g_nx.add_nodes_from(list(range(graph[0].shape[0])))
    # Add edges
    for rel, adj in enumerate(graph):
        # Convert adjacency matrix to tuples for nx0
        nx_triplets = []
        for src, dst in list(zip(adj.tocoo().row, adj.tocoo().col)):
            nx_triplets.append((src, dst, {"type": rel}))
        g_nx.add_edges_from(nx_triplets)

    # make dgl graph
    g_dgl = dgl.from_networkx(g_nx, edge_attrs=["type"])
    # add node features
    if n_feats is not None:
        g_dgl.ndata["feat"] = torch.tensor(n_feats)

    return g_dgl


def prepare_features(subgraph, n_labels, r_label, max_n_label, n_feats=None):
    # One hot encode the node label feature and concat to n_featsure
    n_nodes = subgraph.number_of_nodes()
    label_feats = np.zeros((n_nodes, max_n_label[0] + 1 + max_n_label[1] + 1))
    label_feats[np.arange(n_nodes), n_labels[:, 0]] = 1
    label_feats[np.arange(n_nodes), max_n_label[0] + 1 + n_labels[:, 1]] = 1
    n_feats = (
        np.concatenate((label_feats, n_feats), axis=1)
        if n_feats is not None
        else label_feats
    )
    subgraph.ndata["feat"] = torch.FloatTensor(n_feats)

    head_id = np.argwhere([label[0] == 0 and label[1] == 1 for label in n_labels])
    tail_id = np.argwhere([label[0] == 1 and label[1] == 0 for label in n_labels])
    n_ids = np.zeros(n_nodes)
    n_ids[head_id] = 1  # head
    n_ids[tail_id] = 2  # tail
    subgraph.ndata["id"] = torch.FloatTensor(n_ids)

    subgraph.ndata["r_label"] = torch.LongTensor(np.ones(n_nodes) * r_label)

    return subgraph


def get_subgraphs(
    all_links,
    adj_list,
    dgl_adj_list,
    max_node_label_value,
    id2entity,
    entity2onto,
    params_,
    node_features=None,
    kge_entity2id=None,
):

    subgraphs = []
    r_labels = []

    for link in all_links:
        head, tail, rel = link[0], link[1], link[2]

        nodes, node_labels = subgraph_extraction_labeling(
            (head, tail),
            rel,
            adj_list,
            h=params_.hop,
            enclosing_sub_graph=params_.enclosing_sub_graph,
            max_node_label_value=max_node_label_value,
        )

        subgraph = dgl_adj_list.subgraph(nodes)

        subgraph.edata["label"] = torch.tensor(
            rel * np.ones(subgraph.edata["type"].shape), dtype=torch.long
        )

        edges_btw_roots = subgraph.edge_ids(0, 1, return_uv=True)[2].tolist()
        rel_link = np.nonzero(subgraph.edata["type"][edges_btw_roots] == rel)

        if rel_link.squeeze().nelement() == 0:
            subgraph.add_edges(0, 1)
            subgraph.edata["type"][-1] = torch.tensor(rel).type(torch.LongTensor)
            subgraph.edata["label"][-1] = torch.tensor(rel).type(torch.LongTensor)

        #        decorate_subgraph(subgraph, 0)

        kge_nodes = (
            [kge_entity2id[id2entity[n]] for n in nodes] if kge_entity2id else None
        )
        n_feats = node_features[kge_nodes] if node_features is not None else None
        subgraph = prepare_features(
            subgraph, node_labels, rel, max_node_label_value, n_feats
        )

        # Add the onto node
        if entity2onto is not None:
            subgraph.ndata["onto"] = torch.LongTensor(
                entity2onto[subgraph.ndata["_ID"]]
            )

        subgraphs.append(subgraph)
        r_labels.append(rel)

    batched_graph = dgl.batch(subgraphs)
    r_labels = torch.LongTensor(r_labels)

    return (batched_graph, r_labels)


def get_rank(neg_links, model_, adj_list_all_, dgl_adj_list_all_, id2entity_, entity2onto_, params_, node_features_, kge_entity2id_, id2relation_):

    head_neg_links = neg_links["head"][0]
    head_target_id = neg_links["head"][1]  # the id of the positive

    # if id2relation_[head_neg_links[0][2]] != "influences":
    #    return False, False, False, False, False, False
    target_triple = head_neg_links[neg_links["head"][1]]
    head_subgraph = []
    tail_subgraph = []
    if head_target_id != 10000:
        data = get_subgraphs(
            head_neg_links,
            adj_list_all_,
            dgl_adj_list_all_,
            model_.gnn.max_label_value,
            id2entity_,
            entity2onto_,
            params_,
            node_features_,
            kge_entity2id_,
        )

        data = (data[0].to(model_.device), data[1].to(model_.device))
        head_subgraph = get_triples(data[0], id2entity_, id2relation_)
        with torch.no_grad():
            model_out = model_(data)
        if isinstance(model_out, tuple):
            model_out = model_out[0]
        head_scores = model_out.squeeze(1).detach().cpu().numpy()
        head_rank = np.sum(head_scores >= head_scores[head_target_id])

        # head_rank_2 = np.argwhere(np.argsort(head_scores)[::-1] == head_target_id) + 1
    else:
        head_scores = np.array([])
        head_rank = 10000

    num_edges = dgl.unbatch(data[0])[head_target_id].num_edges()  # number of edges in 

    tail_neg_links = neg_links["tail"][0]
    tail_target_id = neg_links["tail"][1]

    if tail_target_id != 10000:
        data = get_subgraphs(
            tail_neg_links,
            adj_list_all_,
            dgl_adj_list_all_,
            model_.gnn.max_label_value,
            id2entity_,
            entity2onto_,
            params_,
            node_features_,
            kge_entity2id_,
        )
        data = (data[0].to(model_.device), data[1].to(model_.device))
        tail_subgraph = get_triples(data[0], id2entity_, id2relation_)
        with torch.no_grad():
            model_out = model_(data)
        if isinstance(model_out, tuple):
            model_out = model_out[0]

        tail_scores = model_out.squeeze(1).detach().cpu().numpy()
        tail_rank = np.sum(tail_scores >= tail_scores[tail_target_id])

        # tail_rank = np.argwhere(np.argsort(tail_scores)[::-1] == tail_target_id) + 1
    else:
        tail_scores = np.array([])
        tail_rank = 10000

    num_edges_tail = dgl.unbatch(data[0])[tail_target_id].num_edges()  # number of edges in 

    assert num_edges == num_edges_tail

    return head_scores, head_rank, tail_scores, tail_rank, head_subgraph, tail_subgraph, target_triple, num_edges


def save_to_file(neg_triplets, id2entity, id2relation, file_name, run_no=0):
    with open(
        os.path.join("./data", params.dataset,
                     f"{file_name}_ranking_head_{run_no}.txt"), "w"
    ) as f:
        for neg_triplet in neg_triplets:
            for s, o, r in neg_triplet["head"][0]:
                f.write("\t".join([id2entity[s], id2relation[r], id2entity[o]]) + "\n")

    with open(
        os.path.join("./data", params.dataset,
                     f"{file_name}_ranking_tail_{run_no}.txt"), "w"
    ) as f:
        for neg_triplet in neg_triplets:
            for s, o, r in neg_triplet["tail"][0]:
                f.write("\t".join([id2entity[s], id2relation[r], id2entity[o]]) + "\n")



def save_ranks(head_ranks, tail_ranks, run_no=0):

    with open(
        os.path.join(
            os.path.dirname(params.model_path),
            f"ranks_{run_no}.txt",
        ),
        "w",
    ) as f:
         for h, t in zip(head_ranks, tail_ranks):
            f.write(f"{h}\t{t}\n")


def save_score_to_file(
    neg_triplets,
    all_head_scores,
    all_tail_scores,
    id2entity,
    id2relation,
    file_name,
    head_subgraphs,
    tail_subgraphs,
):
    with open(
        os.path.join(
            os.path.dirname(params.model_path),
            f"{file_name}_ranking_head_predictions.txt",
        ),
        "w",
    ) as f:
        for i, neg_triplet in enumerate(neg_triplets):
            f.write("\n---------")
            if head_subgraphs[i]:
                for [s, o, r] in head_subgraphs[i]:
                    f.write(f"\n{s}, {o}, {r}")
            f.write("\n..........\n")
            for [s, o, r], head_score in sorted(
                zip(neg_triplet["head"][0], all_head_scores[50 * i : 50 * (i + 1)]),
                key=lambda x: x[
                    1
                ],  # Sort by the second element of the tuple (the score)
                reverse=True,  # Sort in descending order
            ):
                line = (
                    "\t".join(
                        [id2entity[s], id2relation[r], id2entity[o], str(head_score)]
                    )
                    + "\n"
                )
                if (s, o, r) == tuple(neg_triplet["head"][0][0]):
                    line = "*\t" + line

                f.write(line)

    with open(
        os.path.join(
            os.path.dirname(params.model_path),
            f"{file_name}_ranking_tail_predictions.txt",
        ),
        "w",
    ) as f:
        for i, neg_triplet in enumerate(neg_triplets):
            f.write("\n---------")
            if tail_subgraphs[i]:
                for [s, o, r] in tail_subgraphs[i]:
                    f.write(f"\n{s}, {o}, {r}")
            f.write("\n..........\n")
            for [s, o, r], tail_score in sorted(
                zip(neg_triplet["tail"][0], all_tail_scores[50 * i : 50 * (i + 1)]),
                key=lambda x: x[
                    1
                ],  # Sort by the second element of the tuple (the score)
                reverse=True,  # Sort in descending order
            ):
                line = (
                    "\t".join(
                        [id2entity[s], id2relation[r], id2entity[o], str(tail_score)]
                    )
                    + "\n"
                )
                if (s, o, r) == tuple(neg_triplet["tail"][0][0]):
                    line = "*\t" + line

                f.write(line)


def get_kge_embeddings(dataset, kge_model):
    path = "./experiments/kge_baselines/{}_{}".format(kge_model, dataset)
    node_features = np.load(os.path.join(path, "entity_embedding.npy"))
    with open(os.path.join(path, "id2entity.json")) as json_file:
        kge_id2entity = json.load(json_file)
        kge_entity2id = {v: int(k) for k, v in kge_id2entity.items()}

    return node_features, kge_entity2id


def main(params):
    params.main_dir = os.path.relpath(os.path.dirname(os.path.abspath(__file__)))
    if params.dataset[:2] == "fb":
        params.labels_file = os.path.join(
            params.main_dir, "data/{}/{}.tsv".format(params.dataset, "label")
        )

    else:
        params.labels_file = None

    entity2label = None

    if params.labels_file is not None:
        entity2label = {}
        with open(params.labels_file, 'r', encoding="utf-8") as file:
            for line in file:
                # Split the line into two parts by tab character
                kv_pair = re.split(r'\t', line.strip(), maxsplit=1)
                
                if len(kv_pair) == 1:
                    key = kv_pair[0]
                    value = kv_pair[0]
                else:
                    key, value = kv_pair
                    key = key.strip()

                entity2label[key] = value


    model = torch.load(params.model_path, map_location="cuda").to("cuda")
    model.device = "cuda"  # TODO: workaround
    print(model)

    model.eval()
    if not hasattr(model, "data2id"):
        model.data2id = [model.relation2id]

    (
        adj_list,
        dgl_adj_list,
        adj_list_all,
        dgl_adj_list_all,
        triplets,
        entity2id,
        relation2id,
        id2entity,
        id2relation,
        adj_list_onto,
        triplets_onto,
        onto2id,
        id2onto,
        meta2id,
        id2meta,
        entity2onto,
        entity2type_percentile
    ) = process_files(
        params.file_paths,
        params.file_paths_onto,
        params.file_paths_type,
        model.data2id,
        params.add_traspose_rels,
        params.use_test_subgraph,
    )


    # TODO:
    # - for each entity:
        # - compute type sparsity
        # - compute structural sparsity


    if hasattr(model, "train_id2logits"):
        if not hasattr(model, "pretrained_language_model"):
            raise Exception("Couldn't find pretrained LLM information in loaded model. Aborting..")
        id2logits = compute_logits_emb(
            id2entity,
            entity2label=entity2label,
            huggingface_model=model.pretrained_language_model,
            is_causal=model.pretrained_language_model_is_causal,
            persist=os.path.join(".", "embeddings", params.dataset, model.pretrained_language_model.split("/")[-1], "test")
        ).to("cuda")
        model.test_id2logits = id2logits.to("cuda")

    model.id2entity = id2entity
    model.test = True
    model.valid = False
    model.train = False

    node_features, kge_entity2id = (
        get_kge_embeddings(params.dataset, params.kge_model)
        if params.use_kge_embeddings
        else (None, None)
    )

    if params.mode == "sample":
        if params.dataset in ["yago", "db"]:
            neg_triplets = get_neg_samples_replacing_head_tail(
                triplets["links"], adj_list_all
            )
        else:
            neg_triplets = get_neg_samples_replacing_head_tail(
                triplets["links"], adj_list
            )

    else:
        if params.dataset in ["yago", "db"]:
            neg_triplets = get_neg_samples_replacing_head_tail_all(
                triplets["links"], adj_list_all
            )
        else:
            neg_triplets = get_neg_samples_replacing_head_tail_all(
                triplets["links"], adj_list
            )
    save_to_file(neg_triplets, id2entity, id2relation, "links",
                 run_no=params.run_no)

    type_percentile_ranks = {}
    for p in set(entity2type_percentile.values()):
        type_percentile_ranks.setdefault(p, [])
    ranks = []
    head_ranks = []
    tail_ranks = []
    head_subgraphs = []
    tail_subgraphs = []
    all_head_scores = []
    all_tail_scores = []


    tail_ranks_edges = []
    head_ranks_edges = []
    ranks_edges = []

    with tqdm(total=len(neg_triplets)) as pbar:
        for neg_triple in neg_triplets:
            (
                head_scores,
                head_rank,
                tail_scores,
                tail_rank,
                head_subgraph,
                tail_subgraph,
                target_triple,
                num_edges,
            ) = get_rank(neg_triple, model, adj_list_all, dgl_adj_list_all, id2entity, entity2onto, params, node_features, kge_entity2id, id2relation)

            # rank of triple when predicting tail goes into type percentile of head
            type_percentile_ranks[entity2type_percentile[target_triple[0]]].append(head_rank)
            type_percentile_ranks[entity2type_percentile[target_triple[1]]].append(tail_rank)

            ranks.append(head_rank)
            ranks.append(tail_rank)


            # per-rank number of edges in subgraph
            head_ranks_edges.append(num_edges)
            tail_ranks_edges.append(num_edges)
            ranks_edges.append(num_edges)
            ranks_edges.append(num_edges)

            head_ranks.append(head_rank)
            tail_ranks.append(tail_rank)
            head_subgraphs.append(head_subgraph)
            tail_subgraphs.append(tail_subgraph)

            all_head_scores += head_scores.tolist()
            all_tail_scores += tail_scores.tolist()
            metrics = compute_ranking_metrics(ranks)
            head_metrics = compute_ranking_metrics(head_ranks)
            tail_metrics = compute_ranking_metrics(tail_ranks)
            head_metrics = {
                "head_" + key: value for key, value in head_metrics.items()
            }
            tail_metrics = {
                "tail_" + key: value for key, value in tail_metrics.items()
            }
            metrics.update(head_metrics)
            metrics.update(tail_metrics)
            pbar.set_postfix(**metrics)
            pbar.update(1)
            if len(head_ranks) % 100 == 0:
                save_score_to_file(
                    neg_triplets[: len(head_ranks)],
                    all_head_scores,
                    all_tail_scores,
                    id2entity,
                    id2relation,
                    "links",
                    head_subgraphs,
                    tail_subgraphs,
                )

    save_ranks(head_ranks, tail_ranks, run_no=params.run_no)

    assert(len(head_ranks_edges) == len(neg_triplets))

    # Step 2: Compute edge count percentiles
    edge_count_percentiles = np.percentile(head_ranks_edges, [25, 50, 75])
    logger.info("edge count percentiles")
    logger.info(edge_count_percentiles)
    edge_sparsity_metrics = compute_edge_count_percentile_metrics(ranks_edges, ranks, edge_count_percentiles)



    save_score_to_file(
        neg_triplets,
        all_head_scores,
        all_tail_scores,
        id2entity,
        id2relation,
        "links",
        head_subgraphs,
        tail_subgraphs,
    )

    global_metrics = compute_ranking_metrics(ranks)

    logger.info(json.dumps(global_metrics))

    per_type_metrics = {}
    for p, r in type_percentile_ranks.items():
        per_type_metrics[p] = compute_ranking_metrics(r)
    logger.info(json.dumps(per_type_metrics))

    logger.info("Edge sparsity metrics:")
    logger.info(json.dumps(edge_sparsity_metrics))

    results = {
        "global_metrics": global_metrics,
        "type_metrics": per_type_metrics,
        "edge_metrics": edge_sparsity_metrics,
    }

    return results



if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Testing script for hits@10")

    # Experiment setup params
    parser.add_argument(
        "--experiment_name",
        "-e",
        type=str,
        default="fb_v2_margin_loss",
        help="Experiment name. Log file with this name will be created",
    )
    parser.add_argument(
        "--dataset", "-d", type=str, default="FB237_v2", help="Path to dataset"
    )
    parser.add_argument(
        "--mode",
        "-m",
        type=str,
        default="sample",
        choices=["sample", "all"],
        help="Negative sampling mode",
    )
    parser.add_argument(
        "--use_kge_embeddings",
        "-kge",
        type=bool,
        default=False,
        help="whether to use pretrained KGE embeddings",
    )
    parser.add_argument(
        "--kge_model",
        type=str,
        default="TransE",
        help="Which KGE model to load entity embeddings from",
    )
    parser.add_argument(
        "--enclosing_sub_graph",
        "-en",
        type=bool,
        default=True,
        help="whether to only consider enclosing subgraph",
    )
    parser.add_argument(
        "--hop",
        type=int,
        default=3,
        help="How many hops to go while extracting subgraphs?",
    )
    parser.add_argument(
        "--add_traspose_rels",
        "-tr",
        type=bool,
        default=False,
        help="Whether to append adj matrix list with symmetric relations?",
    )
    parser.add_argument(
        "--onto_use_test",
        "-out",
        type=bool,
        default=False,
        help="Whether to use ontology validation triplets",
    )
    parser.add_argument(
        "--use_test_subgraph",
        "-uts",
        type=bool,
        default=False,
        help="Whether to use test triples to build subgraph",
    )
    parser.add_argument(
        "--seed", "-s", type=int, default="28", help="Numpy random seed"
    )
    parser.add_argument(
        "--num_runs", type=int, default="5", help="Number of runs"
    )

    params = parser.parse_args()


    params.file_paths = {
        "graph": os.path.join("./data", params.dataset, "train.txt"),
        "links": os.path.join("./data", params.dataset, "test.txt"),
    }

    params.file_paths_type = {
        "type": os.path.join("./data", params.dataset, "type.txt"),
        "type_test": os.path.join("./data", params.dataset, "type_test.txt"),
    }
    params.file_paths_onto = {
        "onto": os.path.join("./data", params.dataset, "onto.txt")
    }

    params.ruleN_pred_path = os.path.join(
        "./data", params.dataset, "pos_predictions.txt"
    )
    params.model_path = os.path.join(
        "experiments", params.experiment_name, "best_graph_classifier.pth"
    )

    file_handler = logging.FileHandler(
        os.path.join(
            "experiments", params.experiment_name, f"log_rank_test_{time.time()}.txt"
        )
    )
    logger = logging.getLogger()
    logger.addHandler(file_handler)

    logger.info("============ Initialized logger ============")
    logger.info(
        "\n".join("%s: %s" % (k, str(v)) for k, v in sorted(dict(vars(params)).items()))
    )
    logger.info("============================================")

    initial_seed = params.seed

    all_runs_results = []
    for i in range(params.num_runs):
        enable_determinism(initial_seed + i)
        params.run_no = i
        curr_run_results = main(params)
        all_runs_results.append(curr_run_results)

    aggr_results = aggregate_results(all_runs_results)

    logger.info("Aggregated results (mean and std):")
    logger.info(json.dumps(aggr_results))
