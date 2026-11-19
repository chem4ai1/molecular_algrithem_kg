# Codebase for the Paper "Type-Less yet Type-Aware Inductive Link Prediction with Pretrained Language Models" (EMNLP2025)

This repository contains the code needed to replicate the experiments of the paper "Type-Less yet Type-Aware Inductive Link Prediction with Pretrained Language Models" (EMNLP 2025).

## Setting up the Environment

This repository is based on the following dependencies:

* Python 3.8.19
* CUDA 12.1
* DGL 2.4.0
* PyTorch 2.3.0

To set-up the environment, execute:

```shell
conda create -n tyler python=3.8.19
conda activate tyler
```

To install the required dependencies, execute:

```shell
conda install -c dglteam/label/th23_cu121 dgl
conda install pytorch==2.3.0 torchvision==0.18.0 torchaudio==2.3.0 pytorch-cuda=12.1 -c pytorch -c nvidia
pip install -r requirements.txt
```

## Training TyleR

To train TylerR, run the command (the example is for FB237-V1, but it applies to any of the datasets):

```shell
python train.py -e tyler_fbv1_roberta -d fb237_v1 --pretrained_language_model="FacebookAI/roberta-large" --pretrained_language_model_is_causal=False
```

## Training Baselines

To train GraIL, run the following command:

```shell
python train_grail.py -e grail_fbv1 -d fb237_v1
```

To train the ontology-enhanced model (Zhou et al. 2023), run the following:


```shell
python train_oeilp.py -e oeilp_fbv1 -d fb237_v1
```

*Note: it is heavily recommended to train TyleR before any other baseline.*


## Running the Evaluation

To run evaluation, run the command (*Note: it requires a pre-existing checkpoint, which can be obtained by running the training script**)

```shell
python test_ranking.py -e tyler_fbv1_roberta -d fb237_v1_ind
```

For yago, run the following:


```shell
python test_ranking.py -e tyler_yago_roberta -d yago --use_test_subgraph=True
```


## Credits

* Komal K. Teru, Etienne G. Denis, and William L. Hamilton. 2020. Inductive relation prediction by subgraph742
reasoning. In ICML, volume 119 of Proceedings of Machine Learning Research, pages 9448–9457. PMLR. 

* Wentao Zhou, Jun Zhao, Tao Gui, Qi Zhang, and Xuanjing Huang. 2023. Inductive relation inference of knowledge graph enhanced by ontology information. In EMNLP (Findings), pages 6491–6502. Association for Computational Linguistics
