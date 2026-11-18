#!/usr/bin/env python3
"""用 OpenRouter Ernie 对 52 篇新论文做全量 E1-E3 抽取 + 落语义层图。

断点续跑：报告存在且 ok=True 则跳过。
"""
from __future__ import annotations
import json, sys, time, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
from capfactory.po import POGraph
from capfactory.semantic.extraction.runner import run_extraction
from capfactory.semantic.apply import apply_one
from capfactory.vector.labeler import OpenRouterBackend

MODEL='baidu/ernie-5.5-flash-preview:free'
GRAPH=ROOT/'storage/sciforge/semantic_factory_52.json'
REPORTS=ROOT/'storage/sciforge/semantic_extraction'
MD=ROOT/'data/docx'

def main():
    b=OpenRouterBackend(model=MODEL)
    if not b.ok:
        print('OpenRouter key 不可用'); return 1
    from capfactory.llm.backends import chat as vllm_chat
    def chat_fn(prompt, **kw):
        try:
            r = b.chat(prompt, max_tokens=kw.get('max_tokens',16000))
            if r and r.strip():
                return r
        except Exception:
            pass
        # Ernie 限流/空串 → 本地 vLLM 兜底（零成本，不限流）
        return vllm_chat(prompt, backend='vllm', max_tokens=kw.get('max_tokens',16384))
    print('后端策略: Ernie(优先) → vLLM(429/空串兜底)', flush=True)
    g=POGraph.load(str(GRAPH)) if GRAPH.exists() else POGraph('factory52')
    ids=sorted(p.stem for p in MD.glob('*.md'))
    stat={'ok':0,'skip':0,'fail':0}; t0=time.time()
    lock=threading.Lock()
    def task(aid):
        rp=REPORTS/f'{aid}.json'
        if rp.exists():
            try:
                d=json.loads(rp.read_text(encoding='utf-8'))
                if d.get('ok'): return (aid,d,'skip')
            except Exception: pass
        try:
            rep=run_extraction(aid,graph=g,persist=True,chat_fn=chat_fn,
                               run_stages=['E1_paper','E2_algorithm','E3_benchmark'])
            if rep.get('ok'): return (aid,rep,'ok')
            return (aid,None,'fail')
        except Exception as e:
            print(f'ERR {aid}: {str(e)[:60]}',flush=True)
            return (aid,None,'fail')
    todo=[a for a in ids]  # 断点由 task 内判断
    applied=0
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs={ex.submit(task,a):a for a in todo}
        for i,fu in enumerate(as_completed(futs),1):
            aid,rep,status=fu.result()
            with lock:
                stat[status]+=1
                if rep is not None:
                    apply_one(g,rep)   # 主线程串行写图
                    applied+=1
                if i%10==0: g.save(str(GRAPH))
                print(f'[{i}/{len(ids)}] {status} {aid}',flush=True)
    g.save(str(GRAPH))
    print({'stat':stat,'secs':round(time.time()-t0,1),'nodes':len(g.nodes),
           'assertions':len(g.assertions),'graph':str(GRAPH)},flush=True)
    return 0

if __name__=='__main__':
    raise SystemExit(main())
