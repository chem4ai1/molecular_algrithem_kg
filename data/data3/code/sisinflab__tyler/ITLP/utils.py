import dgl
import torch
import os
import tqdm
from transformers import (
    AutoTokenizer,
    AutoModelForMaskedLM,
    AutoModelForCausalLM,
    BartForConditionalGeneration,
)
#import matplotlib.pyplot as plt
#from sklearn.decomposition import PCA
#from sklearn.manifold import TSNE
import random
import numpy as np

#_TYPE_TEMPLATES = [
#    "The type of [1] is [2].",
#    "The type of [1] is related to [2].",
#    "The type of [1] is subclass of [2].",
#    "The type of [1] is equivalent to [2].",
#    "The type of [1] is different from [2].",
#    "The type of [1] is similar to [2].",
#]

_ENTITY_TEMPLATES = [
    "[1] is a type of [2].",  # type
    "[1] is located in [2].",  # geographic
    "[1] is member of [2].",  # membership
    "[1] is equivalent to [2].",  # equivalence
    "[1] is different from [2].",  # difference
    "[1] is similar to [2].",  # similarity
]

_ENTITY_REPR = [_ENTITY_TEMPLATES]


def enable_determinism(random_seed=123):
    random.seed(random_seed)
    np.random.seed(random_seed)
    torch.manual_seed(random_seed)
    torch.cuda.manual_seed(random_seed)
    torch.cuda.manual_seed_all(random_seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    dgl.seed(random_seed)
    torch.use_deterministic_algorithms(True)
    os.environ["PYTHONHASHSEED"] = str(random_seed)
    os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":16:8"


#def plot_embeddings(
#    tensor, labels=None, method="pca", filename="embeddings_plot.png", save_dir="."
#):
#    """
#    Reduces dimensionality of a given tensor and plots the embeddings, saving the plot to disk.
#
#    Parameters:
#    - tensor (torch.Tensor): Input tensor of shape (N, D), where N is the number of samples and D is the dimension.
#    - method (str): Dimensionality reduction method ('pca' or 'tsne'). Defaults to 'pca'.
#    - filename (str): The name of the file where the plot will be saved. Defaults to 'embeddings_plot.png'.
#    - save_dir (str): The directory where the plot will be saved. Defaults to current directory.
#    """
#    # Convert tensor to numpy array
#    embeddings_np = tensor.cpu().detach().numpy()
#
#    # Step 1: Dimensionality Reduction
#    if method == "pca":
#        reducer = PCA(n_components=2)  # PCA for dimensionality reduction
#    elif method == "tsne":
#        reducer = TSNE(n_components=2)  # t-SNE for dimensionality reduction
#    else:
#        raise ValueError("Method should be 'pca' or 'tsne'")
#
#    embeddings_2d = reducer.fit_transform(embeddings_np)
#
#    # Step 2: Plotting
#    plt.figure(figsize=(8, 6))
#    plt.scatter(
#        embeddings_2d[:, 0], embeddings_2d[:, 1], c="blue", marker="o", edgecolor="k"
#    )
#    if labels is not None:
#        if len(labels) != len(embeddings_2d):
#            raise ValueError(
#                "The number of labels must match the number of data points."
#            )
#        for i, label in enumerate(labels):
#            plt.text(
#                embeddings_2d[i, 0],
#                embeddings_2d[i, 1],
#                str(label),
#                fontsize=9,
#                ha="right",
#            )
#
#    plt.title(f"2D Visualization of Embeddings using {method.upper()}")
#    plt.xlabel("Component 1")
#    plt.ylabel("Component 2")
#
#    # Ensure the directory exists
#    os.makedirs(save_dir, exist_ok=True)
#
#    # Create the full path
#    file_path = os.path.join(save_dir, filename)
#
#    # Save the plot to disk
#    plt.savefig(file_path)
#    plt.close()
#
#    print(f"Plot saved to {file_path}")


def format_templates(templates, tokenizer, causal=False):
    if causal:
        type_temp = [t.split("[2]")[0].strip() + ":" for t in templates]
    else:
        type_temp = [t.replace("[2]", tokenizer.mask_token).strip() for t in templates]
    return type_temp


def compute_logits_emb(
    id2entity,
    entity2label=None,
    huggingface_model="FacebookAI/roberta-large",
    is_causal=False,
    batch_size=64,
    persist="id2logits",
):

    if os.path.isfile(f"{persist}.pt"):
        id2logits = torch.load(f"{persist}.pt")
        print(f"Found embeddings in {persist}.pt")
        return id2logits

    tokenizer = AutoTokenizer.from_pretrained(huggingface_model)
    if entity2label is not None:
        id2label = {idx: entity2label.get(id2entity[idx], id2entity[idx]) for idx in id2entity}

    else:
        id2label = {idx: " ".join(id2entity[idx].split("_")) for idx in id2entity}

    if not is_causal:
        if "bart" in huggingface_model:
            plm = BartForConditionalGeneration.from_pretrained(huggingface_model).to(
                "cuda:0"
            )
        else:
            plm = AutoModelForMaskedLM.from_pretrained(huggingface_model).to("cuda:0")
    else:
        plm = AutoModelForCausalLM.from_pretrained(
            huggingface_model, torch_dtype="auto", device_map="cuda"
        )
        if "llama" in huggingface_model.lower() or "pythia" in huggingface_model.lower():
            tokenizer.pad_token = tokenizer.eos_token

    plm.eval()

    repr = []

    for TEMPLATES in _ENTITY_REPR:
        id2logits = []
        templates = format_templates(TEMPLATES, causal=is_causal, tokenizer=tokenizer)
        for prompt_template in templates:
            prompts = {
                idx: prompt_template.replace("[1]", ent)
                for idx, ent in id2label.items()
            }

            nlogits = []
            for i in tqdm.tqdm(range(0, len(prompts), batch_size)):
                if len(prompts) - i < batch_size:
                    curr_prompts = [prompts[j] for j in range(i, i + len(prompts) - i)]
                else:
                    curr_prompts = [prompts[j] for j in range(i, i + batch_size)]

                labels_tok = tokenizer(
                    curr_prompts,
                    add_special_tokens=True,
                    padding=True,
                    return_tensors="pt",
                )
                labels_tok = {
                    key: value.to(plm.device) for key, value in labels_tok.items()
                }

                # labels_tok = {k: v.to(self.device) for k, v in labels_tok.items()}
                with torch.no_grad():
                    if "bart" in huggingface_model:
                        logits = plm(
                            **labels_tok, output_hidden_states=True
                        ).encoder_hidden_states[-1]
                    else:
                        logits = plm(
                            **labels_tok, output_hidden_states=True
                        ).hidden_states[-1]

                if not is_causal:
                    mask_token_index = torch.nonzero(
                        labels_tok["input_ids"] == tokenizer.mask_token_id,
                        as_tuple=True,
                    )

                    mask_logits = logits[mask_token_index]
                else:
                    mask_logits = logits[
                        torch.arange(logits.shape[0]),
                        (labels_tok["attention_mask"] != 0).sum(-1) - 1,
                    ]

                nlogits.extend(mask_logits.to("cpu"))
                torch.cuda.empty_cache()

            id2logits.append(torch.stack(nlogits))

        repr.append(torch.stack(id2logits, dim=1).to(torch.float32))

    if len(repr) > 1:
        repr = torch.stack(repr, dim=1)
    else:
        repr = repr[0]

    if persist:
        print(f"Saving embeddings to ./{persist}.pt")
        os.makedirs(os.path.dirname(persist), exist_ok=True)

        torch.save(repr, f"{persist}.pt")
    return repr
