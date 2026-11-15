(function(){
var css='.pv{margin:10px 0;border:1px solid #1d2940;border-radius:6px;padding:8px 10px;background:#0c1526}'
+'.pv h4{margin:0 0 6px;font-size:12px;color:#8fb4ff}'
+'.pv h4 .n{color:#7d8bb0;font-weight:400}'
+'.pvrow{display:flex;gap:8px;align-items:center;padding:3px 0;font-size:11px}'
+'.pvrow b{flex:1;font-weight:500;word-break:break-word}'
+'.pvrow em{color:#7d8bb0;font-style:normal}'
+'.cells{font-size:11px}'
+'.chead,.crow{display:grid;grid-template-columns:1.1fr 1fr .7fr 1.4fr;gap:6px;padding:3px 0}'
+'.chead{color:#7d8bb0;border-bottom:1px solid #1d2940}'
+'.crow{border-bottom:1px solid #131d30}'
+'.crow em{color:#7ee0c0;font-style:normal;word-break:break-all}';
var st=document.createElement('style');st.textContent=css;document.head.appendChild(st);
function esc(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
window.renderProvenance=function(pv){
pv=pv||{};var h='';var papers=pv.papers||[];
if(papers.length){h+='<div class="pv"><h4>溯源 · 来源论文</h4>';
papers.forEach(function(x){h+='<div class="pvrow"><span class="badge">'+esc(x.relation)
+'</span><b>'+esc(x.title||x.id)+'</b><em>'+esc(x.arxiv_id||'')+'</em></div>';});h+='</div>';}
var hits=pv.report_hits||[];
if(hits.length){h+='<div class="pv"><h4>溯源 · 抽取报告</h4>';
hits.forEach(function(x){h+='<div class="pvrow"><b>'+esc(x.arxiv_id)+'</b><em>'
+esc((x.stages||[]).join(' · '))+'</em></div>';});h+='</div>';}
var n=pv.n_cells||0,cells=pv.cells||[];
if(n){h+='<div class="pv"><h4>单元格级溯源 <span class="n">'+n+' 格</span></h4><div class="cells">'
+'<div class="chead"><span>模型</span><span>指标</span><span>数值</span><span>出处</span></div>';
cells.forEach(function(c){h+='<div class="crow"><span>'+esc(c.model)+'</span><span>'
+esc(c.metric)+'</span><b>'+esc(c.value)+'</b><em>'
+esc(c.provenance||c.source||c.paper_id||'')+'</em></div>';});
h+='</div>';if(n>cells.length){h+='<div class="hint">仅显示前 '+cells.length+' 格</div>';}h+='</div>';}
if(!h){h='<div class="pv"><h4>溯源</h4><div class="hint">该节点暂无来源记录</div></div>';}
return h;};
})();
