from OEILP.model.dgl.graph_classifier import GraphClassifier
import torch.nn.functional as F
from dgl import mean_nodes
import torch
import torch.nn as nn



class PoolEncoder(nn.Module):
    def __init__(
            self,
            num_features,
            num_templates,
            inner_dim,
            output_dim,
            pooling="sum",
    ):
        super(PoolEncoder, self).__init__()

        self.pooling = pooling
        self.layer_norm = nn.LayerNorm(num_features)
        self.dropout = torch.nn.Dropout(0.1)
        self.num_features = num_features
        self.num_templates = num_templates
        self.inner_dim = inner_dim
        self.output_dim = output_dim
        self.prompt_encoders = torch.nn.ModuleList(
            [
                PromptEncoder(self.num_features)
                for _ in range(self.num_templates)
            ]
        )

        # Linear projection to reduce dimensionality after aggregation
        if pooling == "concat":
            self.linear_reduce = nn.Linear(self.inner_dim * num_templates, self.output_dim)
        else:
            self.linear_reduce = nn.Linear(self.inner_dim, self.output_dim)

        # Final output layer
        self.output_layer = nn.Linear(self.output_dim, self.output_dim)

    def forward(self, x):
        x = self.layer_norm(x)
        x = self.dropout(x)
        encoded_prompts = []
        for i, encoder in enumerate(self.prompt_encoders):
            # Extract the i-th prompt for all samples in the batch
            prompt_input = x[:, i, :]  # (batch_size, num_features)
            encoded = encoder(prompt_input)  # (batch_size, inner_dim)
            encoded_prompts.append(encoded)

        # Stack encoded prompts: (batch_size, num_templates, inner_dim)
        encoded_prompts = torch.stack(encoded_prompts, dim=1)
        # Combination
        combined = aggregate_prompts(encoded_prompts)



        # Dimensionality reduction
        if self.pooling is not "sum":
            combined = self.linear_reduce(combined)

        # RELU
        combined = torch.relu(combined)
        # Final output
        output = self.output_layer(combined)

        return output


def aggregate_prompts(prompt_encodings, aggr="sum"):
    if aggr == "mean":
        combined = torch.mean(prompt_encodings, dim=1)
    elif aggr == "max":
        combined, _ = torch.max(prompt_encodings, dim=1)
    elif aggr == "sum":
        combined = torch.sum(prompt_encodings, dim=1)
    elif aggr == "concat":
        combined = prompt_encodings.view(prompt_encodings.size(0), -1)
    return combined


class PromptEncoder(nn.Module):
    def __init__(self, input_dim):
        super(PromptEncoder, self).__init__()
        self.linear_1 = nn.Linear(input_dim, input_dim // 4)
        self.relu = nn.ReLU()
        self.out = nn.Linear(input_dim // 4, input_dim // 4)
        self.dropout = torch.nn.Dropout(0.1)

    def forward(self, x):
        x = self.layer_norm(x)
        x = self.dropout(x)  # noise
        x = self.linear_1(x)
        x = self.relu(x)
        x = self.dropout(x)
        x = self.out(x)
        return x


class TextGraphClassifier(GraphClassifier):

    def __init__(self, *args, **kwargs):
        # bert-base-cased
        self.device = args[0].device
        self.train_id2logits = args[0].train_id2logits.to(self.device)
        self.valid_id2logits = args[0].valid_id2logits.to(self.device)
        self.num_features = kwargs.pop("num_features", self.train_id2logits.shape[-1])

        if self.train_id2logits.ndim == 3:
            self.num_pools = 1
            self.num_templates = self.train_id2logits.shape[1]
        elif self.train_id2logits.ndim == 4:
            self.num_pools = self.train_id2logits.shape[1]
            self.num_templates = self.train_id2logits.shape[2]
        else:
            raise Exception("Embeddings must have either 3 or 4 dims")

        self.train_id2logits.requires_grad = False
        self.valid_id2logits.requires_grad = False
        self.inner_dim_1 = self.num_features // 4
        self.inner_dim_2 = self.inner_dim_1 // 4

        self.reg_loss = 0

        self.valid = False
        self.test = False

        super().__init__(*args, **kwargs)

        self.pretrained_language_model = self.params.pretrained_language_model
        self.pretrained_language_model_is_causal = self.params.pretrained_language_model_is_causal

        self.pool_encoders = torch.nn.ModuleList(
            [
                PoolEncoder(
                    num_features=self.num_features,
                    num_templates=self.num_templates,
                    inner_dim=self.inner_dim_1,
                    output_dim=self.inner_dim_2,
                )
                for _ in range(self.num_pools)
            ]
        )

        self.out_proj = nn.Linear(self.inner_dim_2, self.params.sem_dim)

        if self.params.add_ht_emb:
            self.fc_layer = torch.nn.Linear(
                3 * self.params.num_gcn_layers * self.params.emb_dim
                + self.params.rel_emb_dim,
                1,
            )
        else:
            self.fc_layer = torch.nn.Linear(
                self.params.num_gcn_layers * self.params.emb_dim
                + self.params.rel_emb_dim,
                1,
            )

    def init_ent_emb_matrix(self, g):
        """Entity feature initialization with ontology information"""
        if self.valid:
            ent_feats = self.aggregate_embeddings(self.valid_id2logits[g.ndata["_ID"]].to(self.device))
        elif self.test:
            ent_feats = self.aggregate_embeddings(self.test_id2logits[g.ndata["_ID"]].to(self.device))
        else:
            ent_feats = self.aggregate_embeddings(self.train_id2logits[g.ndata["_ID"]].to(self.device))

        g.ndata["init"] = torch.cat([g.ndata["feat"], ent_feats], dim=1)
        # plot_embeddings(ent_feats, labels=[self.id2entity[i.item()] for i in g.ndata['_ID']])

    def forward(self, data, cal_onto=False, cal_type=False, separate=False):
        g, rel_labels = data

        self.current_graph = g

        if self.params.init_onto_use:
            self.init_ent_emb_matrix(g)
        else:
            g.ndata["init"] = g.ndata["feat"].clone()
        # r: Embedding of relation
        r = self.rel_emb.weight.clone()

        # Input graph into GNN to get embeddings.
        g.ndata["h"], r_emb_out = self.gnn(g, r)

        out_dim = self.params.num_gcn_layers * self.params.emb_dim
        g_out = mean_nodes(g, "repr").view(-1, out_dim)  # [n, hidden_dim]

        head_ids = (g.ndata["id"] == 1).nonzero().squeeze(1)
        head_embs = g.ndata["repr"][head_ids]

        tail_ids = (g.ndata["id"] == 2).nonzero().squeeze(1)
        tail_embs = g.ndata["repr"][tail_ids]
        # tail_sem = g.ndata['init'][tail_ids][:, g.ndata['feat'].shape[-1]:]
        # head_labels = [self.id2entity[i.item()] for i in g.ndata['_ID'][head_ids]]
        # tail_labels = [self.id2entity[i.item()] for i in g.ndata['_ID'][tail_ids]]

        # if self.training:
        #    self.reg_loss = 0.5 * contrastive_loss(g.ndata['init'], g.ndata['repr'][:, -1, :]) # additional loss
        # plot_embeddings(g.ndata['repr'][:, -1, :][tail_ids], labels=[self.id2entity[i.item()] for i in g.ndata['_ID']])

        if self.params.add_ht_emb:
            g_rep = torch.cat(
                [
                    g_out,
                    head_embs.view(-1, out_dim),
                    tail_embs.view(-1, out_dim),
                    F.embedding(rel_labels, r_emb_out, padding_idx=-1),
                ],
                dim=1,
            )
        else:
            g_rep = torch.cat([g_out, self.rel_emb(rel_labels)], dim=1)

        self.r_emb_out = r_emb_out

        output = self.fc_layer(g_rep)

        return output

    def aggregate_embeddings(self, x):
        if x.ndim < 3:
            raise Exception("Embeddings shape is not valid")
        if x.ndim == 3:
            x = torch.unsqueeze(x, 1)

        res = [pe(x[:, i, :]) for i, pe in enumerate(self.pool_encoders)]
        x = torch.cat(res, dim=-1)
        x = self.out_proj(x)  # B x sem_dim
        x = torch.sigmoid(x)

        return x
