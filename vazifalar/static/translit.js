/* CORE: reusable — Uzbek Latin → Cyrillic for the page text (same rules as core/translit.py).
   Runs only when the person chose Cyrillic. Inputs and textareas are left as typed. */
(function(){
  var APOS="'ʻ‘’`ʼ", VOW="aeiouAEIOU";
  var PAIRS={sh:"ш",ch:"ч",yo:"ё",yu:"ю",ya:"я",ye:"е"};
  var S={a:"а",b:"б",d:"д",f:"ф",g:"г",h:"ҳ",i:"и",j:"ж",k:"к",l:"л",m:"м",n:"н",o:"о",p:"п",q:"қ",r:"р",
         s:"с",t:"т",u:"у",v:"в",x:"х",y:"й",z:"з",c:"с",w:"в"};
  function isA(c){return !!c && c.toLowerCase()!==c.toUpperCase();}
  function isU(c){return c!==c.toLowerCase();}
  function cs(src,out){if(src.length>1?isU(src[0])&&isU(src[1]):false)return out.toUpperCase();
    if(src.length===1&&isU(src)&&out.length===1)return out.toUpperCase();
    if(isU(src[0]))return out[0].toUpperCase()+out.slice(1);return out;}
  function tr(t){var o="",i=0,n=t.length;while(i<n){var c=t[i],lo=c.toLowerCase(),nx=t[i+1]||"",pv=i>0?t[i-1]:"";
      var ws=!isA(pv)&&APOS.indexOf(pv)<0||pv==="";
      if((lo==="o"||lo==="g")&&nx&&APOS.indexOf(nx)>=0){o+=cs(c,lo==="o"?"ў":"ғ");i+=2;continue;}
      var pr=(c+nx).toLowerCase();if(nx&&PAIRS[pr]){o+=cs(isU(nx)?c+nx:c,PAIRS[pr]);i+=2;continue;}
      if(lo==="e"){o+=cs(c,(ws||VOW.indexOf(pv)>=0)?"э":"е");i++;continue;}
      if(APOS.indexOf(c)>=0&&isA(pv)){o+="ъ";i++;continue;}
      if(S[lo]){o+=cs(c,S[lo]);i++;continue;}o+=c;i++;}return o;}
  var W={yanvar:"январь",fevral:"февраль",aprel:"апрель",iyun:"июнь",iyul:"июль",avgust:"август",
    sentabr:"сентябрь",oktabr:"октябрь",noyabr:"ноябрь",dekabr:"декабрь",sen:"сен",okt:"окт",noy:"ноя",dek:"дек",yan:"янв",fev:"фев"};
  function words(t){return t.replace(/[A-Za-z][A-Za-z'ʻ‘’`ʼ]*/g,function(w){var c=W[w.toLowerCase()];
    if(c===undefined)return tr(w);return isU(w[0])?c[0].toUpperCase()+c.slice(1):c;});}
  window.toCyrillic=words;
  if(document.documentElement.dataset.script!=="cyrl")return;
  var skip={SCRIPT:1,STYLE:1,TEXTAREA:1,INPUT:1,SELECT:1,OPTION:0};
  function walk(el){for(var n=el.firstChild;n;n=n.nextSibling){
      if(n.nodeType===3){if(/[A-Za-z]/.test(n.nodeValue))n.nodeValue=words(n.nodeValue);}
      else if(n.nodeType===1&&!skip[n.tagName]&&!n.classList.contains("keep")){walk(n);}}
    }
  function attrs(){document.querySelectorAll("[placeholder],[aria-label],[title]").forEach(function(e){
      ["placeholder","aria-label","title"].forEach(function(a){var v=e.getAttribute(a);if(v)e.setAttribute(a,words(v));});});
    document.title=words(document.title);}
  walk(document.body);attrs();
})();
