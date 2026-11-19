from ITLP.model.dgl.rgcn_model import RGCN
from dgl import mean_nodes
import torch.nn as nn
import torch.nn.functional as F
import torch
import numpy as np

"""
File based off of dgl tutorial on RGCN
Source: https://github.com/dmlc/dgl/tree/master/examples/pytorch/rgcn

- Reduction of prompt embeddings up to sem_dim 
- MSE loss btw last layer and layer 0

"""

class PWLayer(nn.Module):
    """Single Parametric Whitening Layer
    """
    def __init__(self, input_size, output_size, dropout=0.0):
        super(PWLayer, self).__init__()

        self.dropout = nn.Dropout(p=dropout)
        self.bias = nn.Parameter(torch.zeros(input_size), requires_grad=True)
        self.lin = nn.Linear(input_size, output_size, bias=False)

        self.apply(self._init_weights)

    def _init_weights(self, module):
        if isinstance(module, nn.Linear):
            module.weight.data.normal_(mean=0.0, std=0.02)

    def forward(self, x):
        return self.lin(self.dropout(x) - self.bias)

class MoEAdaptorLayer(nn.Module):
    """
    MoE-enhanced Adaptor
    unisrec
    """
    def __init__(self, n_exps, layers, dropout=0.0, noise=True):

        super(MoEAdaptorLayer, self).__init__()

        self.n_exps = n_exps
        self.noisy_gating = noise

        self.experts = nn.ModuleList([PWLayer(layers[0], layers[1], dropout) for i in range(n_exps)])
        self.w_gate = nn.Parameter(torch.zeros(layers[0], n_exps), requires_grad=True)
        self.w_noise = nn.Parameter(torch.zeros(layers[0], n_exps), requires_grad=True)

    def noisy_top_k_gating(self, x, train, noise_epsilon=1e-2):
        clean_logits = x @ self.w_gate
        if self.noisy_gating and train:
            raw_noise_stddev = x @ self.w_noise
            noise_stddev = ((F.softplus(raw_noise_stddev) + noise_epsilon))
            noisy_logits = clean_logits + (torch.randn_like(clean_logits).to(x.device) * noise_stddev)
            logits = noisy_logits
        else:
            logits = clean_logits

        gates = F.softmax(logits, dim=-1)
        return gates

    def forward(self, x):
        gates = self.noisy_top_k_gating(x, self.training) # (B, n_E)
        expert_outputs = [self.experts[i](x).unsqueeze(-2) for i in range(self.n_exps)] # [(B, 1, D)]
        expert_outputs = torch.cat(expert_outputs, dim=-2)
        multiple_outputs = gates.unsqueeze(-1) * expert_outputs
        return multiple_outputs.sum(dim=-2)

class PoolEncoder(nn.Module):
    def __init__(
            self,
            num_features,
            num_templates,
            output_dim,
            inner_dim=128,
            pooling="sum",
    ):
        super(PoolEncoder, self).__init__()
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
        self.pooling = pooling
        self.dropout = torch.nn.Dropout(0.1)

        # Linear projection to reduce dimensionality after aggregation
        # Linear projection to reduce dimensionality after aggregation
        if pooling == "concat":
            self.output_layer = nn.Linear(self.inner_dim * num_templates, self.output_dim)
        else:
            self.output_layer = nn.Linear(self.inner_dim, self.output_dim)  
        # Final output layer

    def aggregate_prompts(self, prompt_encodings, aggr="sum"):
        if aggr == "mean":
            combined = torch.mean(prompt_encodings, dim=1)
        elif aggr == "sum":
            combined = torch.sum(prompt_encodings, dim=1)
        elif aggr == "concat":
            combined = prompt_encodings.view(prompt_encodings.size(0), -1)
        elif aggr == "attn":
            # prompt_encodings: [B, NUM_TEMPLATES, dim]
            query = prompt_encodings[:, 0:1, :]         # [B, 1, dim]
            keys_values = prompt_encodings[:, 1:, :]    # [B, NUM_TEMPLATES-1, dim]

            # Compute dot-product attention scores
            scores = torch.matmul(query, keys_values.transpose(1, 2))  # [B, 1, NUM_TEMPLATES-1]
            attention_weights = F.softmax(scores, dim=-1)              # [B, 1, NUM_TEMPLATES-1]

            # Weighted sum of values
            attended = torch.matmul(attention_weights, keys_values)    # [B, 1, dim]
            attended = attended.squeeze(1)                             # [B, dim]
            first_template = query.squeeze(1)                          # [B, dim]

            # Combine first template and attended features (e.g., via concatenation)
            combined = first_template + attended
            #scores = torch.einsum('bsi,i->bs', prompt_encodings, self.attention_weights)
            #attention_weights = F.softmax(scores, dim=1)  # Normalize over sequence dimension
            #combined = torch.einsum('bsi,bs->bi', prompt_encodings, attention_weights)
        return combined



    def forward(self, x):
        encoded_prompts = []
        for i, encoder in enumerate(self.prompt_encoders):
            # Extract the i-th prompt for all samples in the batch
            prompt_input = x[:, i, :]  # (batch_size, num_features)
            encoded = encoder(prompt_input)  # (batch_size, inner_dim)
            encoded_prompts.append(encoded)

        # Stack encoded prompts: (batch_size, num_templates, inner_dim)
        encoded_prompts = torch.stack(encoded_prompts, dim=1)
        # Combination
        combined = self.aggregate_prompts(encoded_prompts, aggr=self.pooling)
        # Dimensionality reduction
#        combined = self.linear_reduce(combined)
        # RELU
        combined = torch.relu(combined)
        #dropout
        combined = self.dropout(combined)
        # Final output
        output = self.output_layer(combined)

        return output

class PromptEncoder(nn.Module):
    def __init__(self, input_dim, output_dim=128):
        super(PromptEncoder, self).__init__()
        self.layer_norm = nn.LayerNorm(input_dim)
        self.linear_1 = nn.Linear(input_dim, output_dim)
        self.dropout = torch.nn.Dropout(0.1)

    def forward(self, x):
        x = self.dropout(x)
        x = self.layer_norm(x)
        x = self.linear_1(x)
        return x


class TextGraphClassifier(nn.Module):
    def __init__(self, params, relation2id, *args, **kwargs):  # in_dim, h_dim, rel_emb_dim, out_dim, num_rels, num_bases):
        super().__init__()

        self.params = params
        self.device = self.params.device
        self.train_id2logits = self.params.train_id2logits.to(self.device)
        self.valid_id2logits = self.params.valid_id2logits.to(self.device)

        self.num_features = kwargs.pop("num_features", self.train_id2logits.shape[-1])

        self.w_recon = nn.Linear(self.params.emb_dim, self.params.sem_dim)
        self.n_pos_emb = ((self.params.emb_dim - self.params.sem_dim) // 2)
        self.pos_emb_h = nn.Embedding(self.n_pos_emb, self.n_pos_emb)
        self.pos_emb_t = nn.Embedding(self.n_pos_emb, self.n_pos_emb)

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

        self.reg_loss = 0

        self.valid = False
        self.test = False

        self.relation2id = relation2id
        self.gnn = RGCN(self.params)  # in_dim, h_dim, h_dim, num_rels, num_bases)

        self.rel_emb = nn.Embedding(self.params.num_rels + 1, self.params.inp_dim, sparse=False,
                                    padding_idx=self.params.num_rels)

        self.data2id = [self.relation2id]
        self.sigmoid = nn.Sigmoid()
        self.dropout = nn.Dropout(self.params.dropout)

        if self.params.add_ht_emb:
            self.fc_layer = nn.Linear(3 * self.params.num_gcn_layers * self.params.emb_dim + self.params.rel_emb_dim, 1)
        else:
            self.fc_layer = nn.Linear(self.params.num_gcn_layers * self.params.emb_dim + self.params.rel_emb_dim, 1)

        self.pretrained_language_model = self.params.pretrained_language_model
        self.pretrained_language_model_is_causal = self.params.pretrained_language_model_is_causal

        self.pool_encoders = torch.nn.ModuleList(
            [
                PoolEncoder(
                    num_features=self.num_features,
                    num_templates=self.num_templates,
                    output_dim=self.params.sem_dim,
                    inner_dim=128,
                    pooling="sum",
                )
                for _ in range(self.num_pools)
            ]
        )
        if len(self.pool_encoders) > 1:
            self.out_proj = nn.Linear(self.params.sem_dim * len(self.pool_encoders), self.params.sem_dim)

    def init_ent_emb_matrix(self, g):
        """Entity feature initialization with ontology information"""
        if self.valid:
            ent_feats = self.aggregate_embeddings(self.valid_id2logits[g.ndata["_ID"]])
        elif self.test:
            ent_feats = self.aggregate_embeddings(self.test_id2logits[g.ndata["_ID"]])
        else:
            ent_feats = self.aggregate_embeddings(self.train_id2logits[g.ndata["_ID"]])

        g.ndata["init"] = torch.cat([g.ndata["feat"], ent_feats], dim=1)

    def get_onto_emb(self, triples):
        pass

    def get_mapping_constraint(self, g, head_ids, tail_ids, separate=False):
        pass

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

        # MSE output-input
        #init_recon = self.w_recon(g.ndata["h"][tail_ids])
        #self.reg_loss = nn.functional.mse_loss(init_recon, g.ndata["init"][tail_ids][:, -self.params.sem_dim:], reduction='sum')

        return output

    def aggregate_embeddings(self, x):
        # TODO: rimuovi
        # graph_ids = self.current_graph.ndata["_ID"]
        if x.ndim < 3:
            raise Exception("Embeddings shape is not valid")
        if x.ndim == 3:
            x = torch.unsqueeze(x, 1)

        if len(self.pool_encoders) > 1:
            res = [pe(x[:, i, :]) for i, pe in enumerate(self.pool_encoders)]
            x = torch.cat(res, dim=-1)
            x = self.out_proj(x)  # B x sem_dim
        else:
            x = self.pool_encoders[0](x[:, 0, :])    # for i, pe in enumerate(self.pool_encoders)] # TODO

        x = torch.sigmoid(x)

        return x
