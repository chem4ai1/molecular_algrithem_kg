import os
import argparse
import logging
from ITLP.utils import enable_determinism
import multiprocessing

# sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ITLP.dataset import Dataset
import torch
from scipy.sparse import SparseEfficiencyWarning

from OEILP.subgraph_extraction.datasets import (
    generate_subgraph_datasets,
)

# from OEILP.utils.initialization_utils import initialize_model
from ITLP.initialization_utils import initialize_experiment, initialize_model
from OEILP.utils.graph_utils import (
    collate_dgl,
    move_batch_to_device_dgl,
    collate_dgl_onto,
    move_batch_to_device_dgl_onto,
)

#from ITLP.tyler import TextGraphClassifier as dgl_model
#from ITLP.tyler_3 import TextGraphClassifier as dgl_model
#from ITLP.new import TextGraphClassifier as dgl_model # sum pooling
#from ITLP.tyler_moe import TextGraphClassifier as dgl_model # sum pooling
#from ITLP.tyler_moe_2 import TextGraphClassifier as dgl_model # sum pooling
#from ITLP.tyler_moe_fusion_2 import TextGraphClassifier as dgl_model # sum pooling
#from ITLP.tyler_5 import TextGraphClassifier as dgl_model # attn pooling without out layer
#from ITLP.graph_classifier_clean import TextGraphClassifier as dgl_model
from ITLP.tyler_simple import TextGraphClassifier as dgl_model
#from ITLP.tyler_simple_onlytype import TextGraphClassifier as dgl_model
#from ITLP.tyler_simple import TextGraphClassifier as dgl_model
#from ITLP.tyler_simple_moe import TextGraphClassifier as dgl_model
#from ITLP.tyler_simple import TextGraphClassifier as dgl_model
#from ITLP.tyler_simple_sum import TextGraphClassifier as dgl_model
#from ITLP.tyler_simple_attn import TextGraphClassifier as dgl_model
#from ITLP.tyler_simple_moe import TextGraphClassifier as dgl_model
#from ITLP.tyler_simple_moe_attn import TextGraphClassifier as dgl_model

from ITLP.evaluator import Evaluator
from ITLP.trainer import Trainer

from warnings import simplefilter


def main(params):
    multiprocessing.set_start_method("spawn")
    simplefilter(action="ignore", category=UserWarning)
    simplefilter(action="ignore", category=SparseEfficiencyWarning)

    params.db_path = os.path.join(
        params.main_dir,
        f"data/{params.dataset}/subgraphs_en_{params.enclosing_sub_graph}_neg_{params.num_neg_samples_per_link}_hop_{params.hop}",
    )

    if not os.path.isdir(params.db_path):
        generate_subgraph_datasets(params)

    enable_determinism(params.seed)

    train = Dataset(
        params.db_path,
        "train_pos",
        "train_neg",
        params.file_paths,
        params.file_paths_onto,
        params.file_paths_type,
        add_traspose_rels=params.add_traspose_rels,
        num_neg_samples_per_link=params.num_neg_samples_per_link,
        use_kge_embeddings=params.use_kge_embeddings,
        dataset=params.dataset,
        kge_model=params.kge_model,
        file_name=params.train_file,
        device=params.device,
        model_dir=params.exp_dir,
        pretrained_model_name=params.pretrained_language_model,
        pretrained_model_is_causal=params.pretrained_language_model_is_causal,
        labels_file=params.labels_file,
        main_dir=params.main_dir,
    )

    valid = Dataset(
        params.db_path,
        "valid_pos",
        "valid_neg",
        params.file_paths,
        params.file_paths_onto,
        params.file_paths_type,
        add_traspose_rels=params.add_traspose_rels,
        num_neg_samples_per_link=params.num_neg_samples_per_link,
        use_kge_embeddings=params.use_kge_embeddings,
        dataset=params.dataset,
        kge_model=params.kge_model,
        file_name=params.valid_file,
        model_dir=params.exp_dir,
        device=params.device,
        pretrained_model_name=params.pretrained_language_model,
        pretrained_model_is_causal=params.pretrained_language_model_is_causal,
        labels_file=params.labels_file,
        main_dir=params.main_dir,
    )

    train_id2logits = train.id2logits
    valid_id2logits = valid.id2logits

    params.num_rels = train.num_rels
    params.aug_num_rels = train.aug_num_rels

    params.num_ontos = 0
    params.num_meta_rels = 0
    if params.init_onto_use:
        params.inp_dim = train.n_feat_dim + params.sem_dim
    else:
        params.inp_dim = train.n_feat_dim

    #    params.inp_dim = params.sem_dim # TODO: ONLYTYPE
    # Log the max label value to save it in the model. This will be used to cap the labels generated on test set.
    params.max_label_value = train.max_n_label
    params.train_id2logits = train_id2logits
    params.valid_id2logits = valid_id2logits
    graph_classifier = initialize_model(params, dgl_model, params.load_model)
    print(graph_classifier)
    graph_classifier.id2entity = train.id2entity

    logging.info(f"Device: {params.device}")
    logging.info(
        f"Input dim : {params.inp_dim}, # Relations : {params.num_rels}, # Augmented relations : {params.aug_num_rels}"
    )

    valid_evaluator = Evaluator(params, graph_classifier, valid)

    trainer = Trainer(params, graph_classifier, train, None, valid_evaluator, None)

    logging.info("Starting training with full batch...")

    enable_determinism(params.seed)

    trainer.train()


if __name__ == "__main__":

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="TransE model")

    # Experiment setup params
    parser.add_argument(
        "--experiment_name",
        "-e",
        type=str,
        default="default",
        help="A folder with this name would be created to dump saved models and log files",
    )
    parser.add_argument("--dataset", "-d", type=str, help="Dataset string")
    parser.add_argument("--gpu", type=int, default=0, help="Which GPU to use?")
    parser.add_argument("--disable_cuda", action="store_true", help="Disable CUDA")
    parser.add_argument(
        "--load_model", action="store_true", help="Load existing model?"
    )
    parser.add_argument(
        "--train_file",
        "-tf",
        type=str,
        default="train",
        help="Name of file containing training triplets",
    )
    parser.add_argument(
        "--valid_file",
        "-vf",
        type=str,
        default="valid",
        help="Name of file containing validation triplets",
    )
    parser.add_argument(
        "--type_file",
        "-tyf",
        type=str,
        default="type",
        help="Name of file containing type triplets",
    )
    parser.add_argument(
        "--type_valid_file",
        "-tvf",
        type=str,
        default="type_valid",
        help="Name of file containing type triplets",
    )
    parser.add_argument(
        "--onto_file",
        "-of",
        type=str,
        default="onto",
        help="Name of file containing ontology triplets",
    )
    parser.add_argument(
        "--onto_valid_file",
        "-ovf",
        type=str,
        default="onto_valid",
        help="Name of file containing ontology validation triplets",
    )
    parser.add_argument(
        "--onto_use_valid",
        "-ouv",
        type=bool,
        default=True,
        help="Whether to use ontology validation triplets",
    )

    # Training regime params
    parser.add_argument(
        "--num_epochs",
        "-ne",
        type=int,
        default=50,
        help="Learning rate of the optimizer",
    )
    parser.add_argument("--eval_every", type=int, default=3, help="?")
    parser.add_argument(
        "--eval_every_iter",
        type=int,
        default=455,
        help="Interval of iterations to evaluate the model?",
    )
    parser.add_argument(
        "--save_every",
        type=int,
        default=10,
        help="Interval of epochs to save a checkpoint of the model?",
    )
    parser.add_argument(
        "--early_stop", type=int, default=100, help="Early stopping patience"
    )
    parser.add_argument(
        "--optimizer", type=str, default="Adam", help="Which optimizer to use?"
    )
    parser.add_argument(
        "--lr", type=float, default=1e-3, help="Learning rate of the optimizer"
    )
    parser.add_argument(
        "--clip", type=int, default=1000, help="Maximum gradient norm allowed"
    )
    parser.add_argument(
        "--l2", type=float, default=5e-4, help="Regularization constant for GNN weights"
    )
    parser.add_argument(
        "--margin",
        type=float,
        default=10,
        help="The margin between positive and negative samples in the max-margin loss",
    )
    parser.add_argument(
        "--margin2",
        type=float,
        default=10,
        help="The margin between positive and negative onto samples in the max-margin loss",
    )
    parser.add_argument(
        "--margin3",
        type=float,
        default=5,
        help="The margin between positive and negative onto samples in the max-margin loss",
    )
    parser.add_argument(
        "--alpha",
        type=float,
        default=1,
        help="A weighing hyperparameter for balancing loss function",
    )
    parser.add_argument(
        "--omega",
        type=float,
        default=1,
        help="A weighing hyperparameter for balancing loss function",
    )

    # Data processing pipeline params
    parser.add_argument(
        "--max_links",
        type=int,
        default=1000000,
        help="Set maximum number of train links (to fit into memory)",
    )
    parser.add_argument(
        "--hop", type=int, default=3, help="Enclosing subgraph hop number"
    )
    parser.add_argument(
        "--max_nodes_per_hop",
        "-max_h",
        type=int,
        default=None,
        help="if > 0, upper bound the # nodes per hop by subsampling",
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
        "--model_type",
        "-m",
        type=str,
        choices=["ssp", "dgl"],
        default="dgl",
        help="what format to store subgraphs in for model",
    )
    parser.add_argument(
        "--constrained_neg_prob",
        "-cn",
        type=float,
        default=0.0,
        help="with what probability to sample constrained heads/tails while neg sampling",
    )
    parser.add_argument("--batch_size", type=int, default=16, help="Batch size")
    parser.add_argument(
        "--num_neg_samples_per_link",
        "-neg",
        type=int,
        default=1,
        help="Number of negative examples to sample per positive link",
    )
    parser.add_argument(
        "--num_workers", type=int, default=0, help="Number of dataloading processes"
    )
    parser.add_argument(
        "--add_traspose_rels",
        "-tr",
        type=bool,
        default=False,
        help="whether to append adj matrix list with symmetric relations",
    )
    parser.add_argument(
        "--enclosing_sub_graph",
        "-en",
        type=bool,
        default=True,
        help="whether to only consider enclosing subgraph",
    )

    # Model params
    parser.add_argument(
        "--rel_emb_dim", "-r_dim", type=int, default=32, help="Relation embedding size"
    )
    parser.add_argument(
        "--attn_rel_emb_dim",
        "-ar_dim",
        type=int,
        default=32,
        help="Relation embedding size for attention",
    )
    parser.add_argument(
        "--emb_dim", "-dim", type=int, default=32, help="Entity embedding size"
    )
    parser.add_argument(
        "--onto_emb_dim", "-o_dim", type=int, default=32, help="Ontology embedding size"
    )
    parser.add_argument(
        "--sem_dim",
        type=int,
        default=24,
        help="the dimension of sematic part of node embedding",
    )
    parser.add_argument(
        "--num_gcn_layers", "-l", type=int, default=3, help="Number of GCN layers"
    )
    parser.add_argument(
        "--num_bases",
        "-b",
        type=int,
        default=4,
        help="Number of basis functions to use for GCN weights",
    )
    parser.add_argument(
        "--dropout", type=float, default=0, help="Dropout rate in GNN layers"
    )
    parser.add_argument(
        "--edge_dropout",
        type=float,
        default=0.5,
        help="Dropout rate in edges of the subgraphs",
    )
    parser.add_argument(
        "--nei_onto_dropout",
        type=float,
        default=0.4,
        help="Dropout rate in aggregating ontology embeddings",
    )
    parser.add_argument(
        "--gnn_agg_type",
        "-a",
        type=str,
        choices=["sum", "mlp", "gru"],
        default="sum",
        help="what type of aggregation to do in gnn msg passing",
    )
    parser.add_argument(
        "--add_ht_emb",
        "-ht",
        type=bool,
        default=True,
        help="whether to concatenate head/tail embedding with pooled graph representation",
    )
    parser.add_argument(
        "--has_attn",
        "-attn",
        type=bool,
        default=True,
        help="whether to have attn in model or not",
    )
    parser.add_argument(
        "--is_comp",
        type=str,
        default="sub",
        choices=["mult", "sub"],
        help="The composition manner of node and relation",
    )
    parser.add_argument(
        "--init_onto_use",
        type=bool,
        default=True,
        help="Whether to use ontology information to initialize entity embedding",
    )

    parser.add_argument(
        "--pretrained_language_model",
        type=str,
#        default="FacebookAI/roberta-base",
#        default="Qwen/Qwen2.5-3B",
        default="FacebookAI/roberta-large",
#        default="EleutherAI/pythia-2.8b",
#        default="meta-llama/Meta-Llama-3-8B",
#        default="Qwen/Qwen2.5-7B",
        help="The huggingface pretrained language model path",
    )

    parser.add_argument(
        "--pretrained_language_model_is_causal",
        type=bool,
        default=False,
        help="The huggingface pretrained language model (causal or not)",
    )
    parser.add_argument(
        "--seed", "-s", type=int, default="28", help="Numpy random seed"
    )

    params = parser.parse_args()

    enable_determinism(params.seed)

    initialize_experiment(params, __file__)

    params.file_paths = {
        "train": os.path.join(
            params.main_dir, "data/{}/{}.txt".format(params.dataset, params.train_file)
        ),
        "valid": os.path.join(
            params.main_dir, "data/{}/{}.txt".format(params.dataset, params.valid_file)
        ),
    }

    if params.dataset[:2] == "fb":
        params.labels_file = os.path.join(
            params.main_dir, "data/{}/{}.tsv".format(params.dataset, "label")
        )

    else:
        params.labels_file = None

    params.file_paths_type = {
        "type": os.path.join(
            params.main_dir, "data/{}/{}.txt".format(params.dataset, params.type_file)
        ),
        "type_valid": os.path.join(
            params.main_dir,
            "data/{}/{}.txt".format(params.dataset, params.type_valid_file),
        ),
    }
    if params.onto_use_valid:
        params.file_paths_onto = {
            "onto": os.path.join(
                params.main_dir,
                "data/{}/{}.txt".format(params.dataset, params.onto_file),
            ),
            "onto_valid": os.path.join(
                params.main_dir,
                "data/{}/{}.txt".format(params.dataset, params.onto_valid_file),
            ),
        }
    else:
        params.file_paths_onto = {
            "onto": os.path.join(
                params.main_dir,
                "data/{}/{}.txt".format(params.dataset, params.onto_file),
            )
        }

    if not params.disable_cuda and torch.cuda.is_available():
        params.device = torch.device("cuda:%d" % params.gpu)
    else:
        params.device = torch.device("cpu")

    params.collate_fn = collate_dgl
    params.move_batch_to_device = move_batch_to_device_dgl

    params.collate_fn_onto = collate_dgl_onto
    params.move_batch_to_device_onto = move_batch_to_device_dgl_onto

    main(params)
