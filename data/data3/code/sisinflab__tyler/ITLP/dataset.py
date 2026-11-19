import os
from OEILP.subgraph_extraction.datasets import SubgraphDataset
import re

import logging
import lmdb
import numpy as npi
import json

from ITLP.sparql_utils import retrieve_id2label
from ITLP.logger import get_logger
from ITLP.utils import compute_logits_emb
import numpy as np
from OEILP.utils.graph_utils import send_graph_to_device
from OEILP.utils.graph_utils import ssp_multigraph_to_dgl
from OEILP.utils.data_utils import process_files, save_to_file
from OEILP.subgraph_extraction.graph_sampler import *

logger = get_logger()


def split_and_remove_underscores(d):
    modified_dict = {}
    for key, value in d.items():
        # Split the string by underscores and join with spaces
        modified_dict[key] = " ".join(value.split("_"))
    return modified_dict


class Dataset(SubgraphDataset):

    def _prepare_subgraphs(self, nodes, r_label, n_labels):
        subgraph = self.graph.subgraph(nodes)
        subgraph.edata['label'] = torch.tensor(r_label * np.ones(subgraph.edata['type'].shape), dtype=torch.long, device=self.graph.device)

        edges_btw_roots = subgraph.edge_ids(0, 1, return_uv=True)[2].tolist()
        rel_link = np.nonzero(subgraph.edata['type'][edges_btw_roots] == r_label)
        if rel_link.squeeze().nelement() == 0:
            subgraph.add_edges(0, 1)
            subgraph.edata['type'][-1] = torch.tensor(r_label).type(torch.LongTensor)
            subgraph.edata['label'][-1] = torch.tensor(r_label).type(torch.LongTensor)

        # map the id read by GraIL to the entity IDs as registered by the KGE embeddings
        kge_nodes = [self.kge_entity2id[self.id2entity[n]] for n in nodes] if self.kge_entity2id else None
        n_feats = self.node_features[kge_nodes] if self.node_features is not None else None
        subgraph = self._prepare_features(subgraph, n_labels, r_label, n_feats)

        # Add the onto node
        subgraph.ndata['onto'] = torch.LongTensor(self.entity2onto[subgraph.ndata['_ID'].cpu()]).to(self.graph.device)
        subgraph.ndata['onto_neg'] = torch.LongTensor(self.entity2onto_neg[subgraph.ndata['_ID'].cpu()]).to(self.graph.device)

        if self.id2logits is None:
            rng_state = torch.cuda.get_rng_state() # TODO
            rng_state_cpu = torch.get_rng_state() # TODO
            self.id2logits = compute_logits_emb(
                self.id2entity,
                entity2label=self.entity2label,
                huggingface_model=self.pretrained_model_name,
                persist=os.path.join(self.main_dir, "embeddings", self.dataset, self.pretrained_model_name.split("/")[-1], self.file_name),
                is_causal=self.pretrained_model_is_causal,
            )
            torch.cuda.set_rng_state(rng_state) # TODO
            torch.set_rng_state(rng_state_cpu) # TODO
        return subgraph

    def _prepare_features(self, subgraph, n_labels, r_label, n_feats=None):
        # One hot encode the node label feature and concat to n_feature
        n_nodes = subgraph.number_of_nodes()
        label_feats = np.zeros((n_nodes, self.max_n_label[0] + 1 + self.max_n_label[1] + 1))
        label_feats[np.arange(n_nodes), n_labels[:, 0]] = 1
        label_feats[np.arange(n_nodes), self.max_n_label[0] + 1 + n_labels[:, 1]] = 1
        n_feats = np.concatenate((label_feats, n_feats), axis=1) if n_feats is not None else label_feats
        subgraph.ndata['feat'] = torch.FloatTensor(n_feats).to(self.graph.device)

        head_id = np.argwhere([label[0] == 0 and label[1] == 1 for label in n_labels])
        tail_id = np.argwhere([label[0] == 1 and label[1] == 0 for label in n_labels])
        n_ids = np.zeros(n_nodes)
        n_ids[head_id] = 1  # head
        n_ids[tail_id] = 2  # tail
        subgraph.ndata['id'] = torch.FloatTensor(n_ids).to(self.graph.device)

        subgraph.ndata['r_label'] = torch.LongTensor(np.ones(n_nodes) * r_label).to(self.graph.device)

        self.n_feat_dim = n_feats.shape[1]  # Find cleaner way to do this -- i.e. set the n_feat_dim
        return subgraph

    def __init_original(self, db_path, db_name_pos, db_name_neg, raw_data_paths, onto_data_paths, type_data_paths,
                included_relations=None,
                add_traspose_rels=False, num_neg_samples_per_link=1, use_kge_embeddings=False, dataset='',
                kge_model='', file_name=''):

        self.main_env = lmdb.open(db_path, readonly=True, max_dbs=3, lock=False)
        self.db_pos = self.main_env.open_db(db_name_pos.encode())
        self.db_neg = self.main_env.open_db(db_name_neg.encode())
        self.node_features, self.kge_entity2id = get_kge_embeddings(dataset, kge_model) if use_kge_embeddings else (
            None, None)
        self.num_neg_samples_per_link = num_neg_samples_per_link
        self.file_name = file_name

        ssp_graph, triplets, __, __, id2entity, id2relation, __, __, __, __, __, __, entity2onto, entity2onto_neg = process_files(
            raw_data_paths, onto_data_paths, type_data_paths, saved_data2id=included_relations)
        self.num_rels = len(ssp_graph)
        # Compute unique values and their counts


        # Add transpose matrices to handle both directions of relations.
        if add_traspose_rels:
            ssp_graph_t = [adj.T for adj in ssp_graph]
            ssp_graph += ssp_graph_t

        # the effective number of relations after adding symmetric adjacency matrices and/or self connections
        self.aug_num_rels = len(ssp_graph)
        self.graph = ssp_multigraph_to_dgl(ssp_graph)

        self.graph = send_graph_to_device(self.graph, self.device)

        self.ssp_graph = ssp_graph
        self.id2entity = id2entity
        self.id2relation = id2relation

        self.entity2onto = entity2onto
        self.entity2onto_neg = entity2onto_neg

        self.max_n_label = np.array([0, 0])


        with self.main_env.begin() as txn:
            self.max_n_label[0] = int.from_bytes(txn.get('max_n_label_sub'.encode()), byteorder='little')
            self.max_n_label[1] = int.from_bytes(txn.get('max_n_label_obj'.encode()), byteorder='little')

            self.avg_subgraph_size = struct.unpack('f', txn.get('avg_subgraph_size'.encode()))
            self.min_subgraph_size = struct.unpack('f', txn.get('min_subgraph_size'.encode()))
            self.max_subgraph_size = struct.unpack('f', txn.get('max_subgraph_size'.encode()))
            self.std_subgraph_size = struct.unpack('f', txn.get('std_subgraph_size'.encode()))

            self.avg_enc_ratio = struct.unpack('f', txn.get('avg_enc_ratio'.encode()))
            self.min_enc_ratio = struct.unpack('f', txn.get('min_enc_ratio'.encode()))
            self.max_enc_ratio = struct.unpack('f', txn.get('max_enc_ratio'.encode()))
            self.std_enc_ratio = struct.unpack('f', txn.get('std_enc_ratio'.encode()))

            self.avg_num_pruned_nodes = struct.unpack('f', txn.get('avg_num_pruned_nodes'.encode()))
            self.min_num_pruned_nodes = struct.unpack('f', txn.get('min_num_pruned_nodes'.encode()))
            self.max_num_pruned_nodes = struct.unpack('f', txn.get('max_num_pruned_nodes'.encode()))
            self.std_num_pruned_nodes = struct.unpack('f', txn.get('std_num_pruned_nodes'.encode()))

        logging.info(f"Max distance from sub : {self.max_n_label[0]}, Max distance from obj : {self.max_n_label[1]}")

        with self.main_env.begin(db=self.db_pos) as txn:
            self.num_graphs_pos = int.from_bytes(txn.get('num_graphs'.encode()), byteorder='little')
        with self.main_env.begin(db=self.db_neg) as txn:
            self.num_graphs_neg = int.from_bytes(txn.get('num_graphs'.encode()), byteorder='little')

        self.__getitem__(0)

    def __init__(self, *args, **kwargs):

        labels_file = kwargs.pop("labels_file", None)
        self.pretrained_model_name = kwargs.pop(
            "pretrained_model_name", "FacebookAI/roberta-large"
        )
        self.pretrained_model_is_causal = kwargs.pop(
            "pretrained_model_is_causal", False
        )
        self.id2label = None
        self.device = kwargs.pop("device", "cuda:0")  # TODO: handle this
        self.id2logits = None  
        self.model_dir = kwargs.pop("model_dir", "")
        self.main_dir = kwargs.pop("main_dir", "")
        self.entity2label = None
        self.dataset = kwargs.pop("dataset", "")

        if labels_file is not None:
            self.entity2label = {}
            with open(labels_file, 'r', encoding="utf-8") as file:
                for line in file:
                    # Split the line into two parts by tab character
                    kv_pair = re.split(r'\t', line.strip(), maxsplit=1)
                   
                    if len(kv_pair) == 1:
                        key = kv_pair[0]
                        value = kv_pair[0]
                    else:
                        key, value = kv_pair
                        key = key.strip()

                    self.entity2label[key] = value

        self.__init_original(*args, **kwargs)



if __name__ == "__main__":
    main_dir = "../OEILP"
    dataset = "yago"
    db_path = os.path.join(main_dir, f"data/{dataset}/subgraphs_en_True_neg_1_hop_3")
    file_paths = {
        "train": os.path.join(main_dir, "data/{}/{}.txt".format(dataset, "train")),
        "valid": os.path.join(main_dir, "data/{}/{}.txt".format(dataset, "valid")),
    }
    file_paths_type = {
        "type": os.path.join(main_dir, "data/{}/{}.txt".format(dataset, "type")),
        "type_valid": os.path.join(
            main_dir, "data/{}/{}.txt".format(dataset, "type_valid")
        ),
    }
    file_paths_onto = {
        "onto": os.path.join(main_dir, "data/{}/{}.txt".format(dataset, "onto"))
    }

    labels_file = os.path.join(main_dir, "data/{}/{}.txt".format(dataset, "label"))
    train = Dataset(
        db_path,
        "train_pos",
        "train_neg",
        file_paths,
        file_paths_onto,
        file_paths_type,
        add_traspose_rels=False,
        num_neg_samples_per_link=1,
        use_kge_embeddings=False,
        dataset=dataset,
        kge_model="TransE",
        file_name="train",
        labels_file=labels_file,
    )

    pass


