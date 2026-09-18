import PptxGenJS from 'pptxgenjs';
import { PptxViewer, RECOMMENDED_ZIP_LIMITS } from '@aiden0z/pptx-renderer/browser';

const template=document.createElement('template');
template.innerHTML=`<style>
:host{display:block;min-height:360px;color:#111;font-family:Arial,"Microsoft YaHei",sans-serif}
:host([data-css-fullscreen]){position:fixed;inset:0;z-index:2147483647;width:100vw;height:100vh;background:#111}
*{box-sizing:border-box}.card{height:100%;min-height:360px;background:#fff;border:1px solid #d8dadd;border-radius:12px;overflow:hidden;display:grid;grid-template-rows:auto 1fr auto;box-shadow:0 3px 18px rgba(0,0,0,.05)}
:host([data-css-fullscreen]) .card{border:0;border-radius:0;height:100vh}.bar{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 12px;background:#fafafa;border-bottom:1px solid #ddd}
.meta{font-size:11px;color:#666;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:60vw}.nav{display:flex;align-items:center;gap:7px}.nav button{border:1px solid #bbb;background:#fff;padding:6px 10px;border-radius:6px;cursor:pointer}.nav button:disabled{opacity:.35}
.page{min-width:62px;text-align:center;font-size:12px;font-weight:700}.shell{min-height:0;background:#d7d9dc;display:flex;align-items:center;justify-content:center;padding:12px;overflow:hidden}
.stage{position:relative;width:100%;max-width:calc((100vh - 160px)*16/9);aspect-ratio:16/9;background:#fff;overflow:hidden;box-shadow:0 2px 14px rgba(0,0,0,.18)}
:host([data-css-fullscreen]) .stage{max-width:calc((100vh - 92px)*16/9)}.viewer{position:absolute;inset:0;width:100%;height:100%;overflow:hidden}
.status{padding:7px 12px;font-size:11px;color:#666;background:#fafafa;border-top:1px solid #ddd;display:flex;justify-content:space-between;gap:10px}.loading{position:absolute;inset:0;display:grid;place-items:center;background:#fff;color:#666;font-size:13px;z-index:5}.loading[hidden]{display:none}
</style>
<section class="card"><div class="bar"><div><strong>Presentation</strong><div class="meta"></div></div><div class="nav"><button class="prev">←</button><span class="page">0 / 0</span><button class="next">→</button><button class="full">Fullscreen</button></div></div>
<div class="shell"><div class="stage"><div class="viewer"></div><div class="loading">Loading presentation…</div></div></div><div class="status"><span>Click left/right · wheel · ←/→ · F</span><span class="perf"></span></div></section>`;

function normalizeBuildResult(result){
  if(result instanceof ArrayBuffer)return {bytes:result,meta:{}};
  if(result?.bytes instanceof ArrayBuffer)return {bytes:result.bytes,meta:result};
  throw new TypeError('buildDeck() must return ArrayBuffer or { bytes: ArrayBuffer, ...metadata }');
}

class PptxPresentation extends HTMLElement{
  static get observedAttributes(){return['src']}
  constructor(){super();this.attachShadow({mode:'open'}).append(template.content.cloneNode(true));this.$=s=>this.shadowRoot.querySelector(s);this.context=undefined;this._loadSeq=0;this._viewer=null;this._current=0;this._total=0;this._wheel=0;this._wheelLock=0;this._onKey=e=>this.#onKey(e)}
  connectedCallback(){this.$('.prev').onclick=()=>this.previous();this.$('.next').onclick=()=>this.next();this.$('.full').onclick=()=>this.toggleFullscreen();this.$('.stage').onclick=e=>{const r=this.$('.stage').getBoundingClientRect();this.goTo(this._current+(e.clientX-r.left<r.width/2?-1:1))};this.$('.stage').ondblclick=e=>{e.preventDefault();this.toggleFullscreen()};this.$('.stage').addEventListener('wheel',e=>this.#onWheel(e),{passive:false});window.addEventListener('keydown',this._onKey);if(this.src)this.load(this.src)}
  disconnectedCallback(){window.removeEventListener('keydown',this._onKey)}
  attributeChangedCallback(name,oldValue,newValue){if(name==='src'&&oldValue!==newValue&&this.isConnected&&newValue)this.load(newValue)}
  get src(){return this.getAttribute('src')||''} set src(v){this.setAttribute('src',v)}
  get currentSlide(){return this._current} get slideCount(){return this._total} get ready(){return !!this._viewer}
  async refresh(){if(this.src)return this.load(this.src)}
  async load(src){
    const seq=++this._loadSeq,started=performance.now();this._viewer=null;this._current=0;this._total=0;this.$('.viewer').replaceChildren();this.$('.loading').hidden=false;this.$('.loading').textContent='Loading presentation…';this.#sync();
    try{
      const absoluteSrc=new URL(src,document.baseURI).href;const buildStart=performance.now();const mod=await import(absoluteSrc);
      if(typeof mod.buildDeck!=='function')throw new Error(`${src} must export buildDeck(runtime, context)`);
      const result=normalizeBuildResult(await mod.buildDeck(PptxGenJS,this.context));const buildMs=performance.now()-buildStart;if(seq!==this._loadSeq)return;
      const openStart=performance.now();this._viewer=await PptxViewer.open(result.bytes,this.$('.viewer'),{zipLimits:RECOMMENDED_ZIP_LIMITS,renderMode:'slide',fitMode:'contain'});if(seq!==this._loadSeq)return;
      this._total=this._viewer.slideCount;this._current=0;this.$('.meta').textContent=src;this.$('.perf').textContent=`build ${buildMs.toFixed(0)} ms · open ${(performance.now()-openStart).toFixed(0)} ms · ready ${(performance.now()-started).toFixed(0)} ms`;this.$('.loading').hidden=true;this.#sync();
      this.dispatchEvent(new CustomEvent('ready',{detail:{src,slideCount:this._total,build:result.meta}}));
    }catch(error){if(seq!==this._loadSeq)return;this.$('.loading').hidden=false;this.$('.loading').textContent=`Failed: ${error.message}`;this.dispatchEvent(new CustomEvent('error',{detail:{src,error}}))}
  }
  async goTo(index){if(!this._viewer||!this._total)return;const n=Math.max(0,Math.min(this._total-1,index));if(n===this._current&&this.$('.viewer').childElementCount)return;await this._viewer.renderSlide(n);this._current=n;this.#sync();this.dispatchEvent(new CustomEvent('slidechange',{detail:{index:n}}))}
  next(){return this.goTo(this._current+1)} previous(){return this.goTo(this._current-1)}
  async toggleFullscreen(){if(this.hasAttribute('data-css-fullscreen')){this.removeAttribute('data-css-fullscreen');this.$('.full').textContent='Fullscreen';return}if(document.fullscreenElement){try{await document.exitFullscreen()}catch{};this.$('.full').textContent='Fullscreen';return}const request=this.requestFullscreen||this.webkitRequestFullscreen;if(request){try{await request.call(this);this.$('.full').textContent='Exit Fullscreen';return}catch{}}this.setAttribute('data-css-fullscreen','');this.$('.full').textContent='Exit Fullscreen'}
  #sync(){this.$('.page').textContent=`${this._total?this._current+1:0} / ${this._total}`;this.$('.prev').disabled=!this._total||this._current<=0;this.$('.next').disabled=!this._total||this._current>=this._total-1}
  #onWheel(e){if(e.ctrlKey||e.metaKey||!this._viewer)return;e.preventDefault();const now=performance.now();if(now<this._wheelLock)return;this._wheel+=Math.abs(e.deltaY)>=Math.abs(e.deltaX)?e.deltaY:e.deltaX;if(Math.abs(this._wheel)>=72){const d=this._wheel>0?1:-1;this._wheel=0;this._wheelLock=now+320;this.goTo(this._current+d)}}
  #onKey(e){if(!this.matches(':hover')&&document.fullscreenElement!==this&&!this.hasAttribute('data-css-fullscreen'))return;if(e.key==='ArrowLeft'||e.key==='PageUp')this.previous();if(e.key==='ArrowRight'||e.key==='PageDown'||e.key===' ')this.next();if(e.key==='Home')this.goTo(0);if(e.key==='End')this.goTo(this._total-1);if(e.key.toLowerCase()==='f')this.toggleFullscreen()}
}
if(!customElements.get('pptx-presentation'))customElements.define('pptx-presentation',PptxPresentation);
export {PptxPresentation};
