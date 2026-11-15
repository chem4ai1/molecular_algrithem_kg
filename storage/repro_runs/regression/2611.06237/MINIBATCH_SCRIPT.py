"""Auto-generated mini-batch shape probe (GGR P3-2).
Pure stdlib. Constructs real mini-batches, measures observed shapes.
No file IO, no expected values, no model weights.
"""
import json

PROBES = json.loads('[{"benchmark": "benchmark:sapt10k", "input_form": "原子坐标", "label": "SAPT10k", "output_form": "能量/力"}, {"benchmark": "benchmark:quid", "input_form": "原子坐标", "label": "QUID", "output_form": "能量/力"}, {"benchmark": "benchmark:jsch_2005", "input_form": "原子坐标", "label": "JSCH-2005", "output_form": "能量/力"}, {"benchmark": "benchmark:pla15", "input_form": "原子坐标", "label": "PLA15", "output_form": "能量/力"}, {"benchmark": "benchmark:torsionnet500", "input_form": "3D坐标", "label": "TorsionNet500", "output_form": "标量"}, {"benchmark": "benchmark:glcmal", "input_form": "SMILES", "label": "GlcMal", "output_form": "分子"}, {"benchmark": "benchmark:proline_catalyzed_aldol_addition", "input_form": "SMILES", "label": "Proline-catalyzed aldol addition", "output_form": "分子"}, {"benchmark": "benchmark:side_chain_pka_of_pentapeptides", "input_form": "氨基酸序列", "label": "Side-chain pKa of pentapeptides", "output_form": "活性/MIC 标签"}, {"benchmark": "benchmark:crambin_in_water", "input_form": "原子坐标", "label": "Crambin in water", "output_form": "能量/力"}, {"benchmark": "benchmark:canonical:sapt10k", "input_form": "原子坐标", "label": "SAPT10k", "output_form": "能量/力"}, {"benchmark": "benchmark:canonical:quid", "input_form": "原子坐标", "label": "QUID", "output_form": "能量/力"}, {"benchmark": "benchmark:canonical:jsch_2005", "input_form": "原子坐标", "label": "JSCH-2005", "output_form": "能量/力"}, {"benchmark": "benchmark:canonical:pla15", "input_form": "原子坐标", "label": "PLA15", "output_form": "能量/力"}, {"benchmark": "benchmark:canonical:torsionnet500", "input_form": "3D坐标", "label": "TorsionNet500", "output_form": "标量"}, {"benchmark": "benchmark:canonical:glcmal", "input_form": "SMILES", "label": "GlcMal", "output_form": "分子"}, {"benchmark": "benchmark:canonical:proline_catalyzed_aldol_addition", "input_form": "SMILES", "label": "Proline-catalyzed aldol addition", "output_form": "分子"}, {"benchmark": "benchmark:canonical:side_chain_pka_of_pentapeptides", "input_form": "氨基酸序列", "label": "Side-chain pKa of pentapeptides", "output_form": "活性/MIC 标签"}, {"benchmark": "benchmark:canonical:crambin_in_water", "input_form": "原子坐标", "label": "Crambin in water", "output_form": "能量/力"}, {"benchmark": "benchmark:drew_dickerson_dodecamer", "input_form": "3D坐标", "label": "Drew–Dickerson dodecamer", "output_form": "3D坐标"}, {"benchmark": "benchmark:cis_platin_1_2_d_gpg_crosslink", "input_form": "3D坐标", "label": "cis-platin 1,2-d(GpG) crosslink", "output_form": "3D坐标"}, {"benchmark": "benchmark:popc_bilayer", "input_form": "3D坐标", "label": "POPC bilayer", "output_form": "3D坐标"}]')
BATCH = 4

SMILES = ["CCO", "c1ccccc1", "CC(=O)O", "C1CCCCC1", "CN1C=NC2=C1C(=O)N(C)C(=O)N2C"]


def construct(form, b):
    f = str(form or "").strip()
    low = f.lower()
    if low == "smiles":
        return [SMILES[i % len(SMILES)] for i in range(b)]
    if f == "向量":
        return [[float((i + j) % 7) / 7.0 for j in range(8)] for i in range(b)]
    if f == "标量":
        return [0.5 + 0.1 * i for i in range(b)]
    if f in ("3D坐标", "坐标"):
        return [[[float((i + j + k) % 9) / 9.0 for k in range(3)]
                 for j in range(3)] for i in range(b)]
    if f in ("图", "分子图"):
        return {
            "x": [[float((i + j) % 5) / 5.0 for j in range(8)] for i in range(b)],
            "edge_index": [[i for i in range(b)], [(i + 1) % b for i in range(b)]],
        }
    if f == "序列":
        return [[(i + j) % 20 for j in range(12)] for i in range(b)]
    if f == "分布":
        return [[float((i + j) % 11) / 11.0 for j in range(16)] for i in range(b)]
    return None


def count_scalars(x):
    if isinstance(x, dict):
        return sum(count_scalars(v) for v in x.values())
    if isinstance(x, (list, tuple)):
        return sum(count_scalars(v) for v in x)
    return 1


def inspect(x):
    if isinstance(x, dict):
        return {"kind": "struct",
                 "fields": {k: inspect(v) for k, v in x.items()},
                 "n_scalars": count_scalars(x)}
    dims = []
    cur = x
    while isinstance(cur, (list, tuple)) and len(cur) > 0:
        dims.append(len(cur))
        cur = cur[0]
    shape = "(" + ", ".join(str(d) for d in dims)
    if len(dims) == 1:
        shape += ","
    shape += ")"
    return {"kind": "array", "shape": shape, "dims": dims,
             "dtype": type(cur).__name__, "n_scalars": count_scalars(x)}


def main():
    out = []
    for p in PROBES:
        rec = {"benchmark": p["benchmark"], "label": p["label"]}
        for side in ("input", "output"):
            form = p[side + "_form"]
            obj = construct(form, BATCH)
            rec[side] = {
                "form": form,
                "constructed": obj is not None,
                "observed": inspect(obj) if obj is not None else None,
                "reason": "" if obj is not None else "form_not_declared_or_unregistered",
            }
        out.append(rec)
    print(json.dumps({"batch_size": BATCH, "probes": out},
                     ensure_ascii=False, sort_keys=True))


main()
