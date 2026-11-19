import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import csv

TITLE = 'Execution accuracy'
OUT = 'storage/generated/fig_main.pdf'
DATA = 'storage/generated/results.csv'

models, values = [], []
with open(DATA, encoding='utf-8-sig') as f:
    r = list(csv.DictReader(f))
    key = [k for k in r[0] if k != 'model'][0]
    models = [x['model'] for x in r]; values = [float(x[key]) for x in r]
fig, ax = plt.subplots(figsize=(6, 3))
ax.bar(models, values); ax.set_ylabel(key); ax.set_title(TITLE)
plt.xticks(rotation=30, ha='right')
fig.tight_layout(); fig.savefig(OUT)
