/*! Licences of the bundled libraries: THIRD-PARTY-LICENSES.txt */
"use strict";(()=>{var t_=Object.defineProperty;var i_=(i,e,t)=>e in i?t_(i,e,{enumerable:!0,configurable:!0,writable:!0,value:t}):i[e]=t;var Ch=(i,e,t)=>i_(i,typeof e!="symbol"?e+"":e,t);var Ue=i=>typeof i=="string",ta=()=>{let i,e,t=new Promise((n,r)=>{i=n,e=r});return t.resolve=i,t.reject=e,t},Rh=i=>i==null?"":String(i),n_=(i,e,t)=>{i.forEach(n=>{e[n]&&(t[n]=e[n])})},r_=/###/g,hp=i=>i&&i.includes("###")?i.replace(r_,"."):i,up=i=>!i||Ue(i),ia=(i,e,t)=>{let n=Ue(e)?e.split("."):e,r=0;for(;r<n.length-1;){if(up(i))return{};let s=hp(n[r]);!i[s]&&t&&(i[s]=new t),Object.prototype.hasOwnProperty.call(i,s)?i=i[s]:i={},++r}return up(i)?{}:{obj:i,k:hp(n[r])}},dp=(i,e,t)=>{let{obj:n,k:r}=ia(i,e,Object);if(n!==void 0||e.length===1){n[r]=t;return}let s=e[e.length-1],a=e.slice(0,e.length-1),o=ia(i,a,Object);for(;o.obj===void 0&&a.length;)s=`${a[a.length-1]}.${s}`,a=a.slice(0,a.length-1),o=ia(i,a,Object),o?.obj&&typeof o.obj[`${o.k}.${s}`]<"u"&&(o.obj=void 0);o.obj[`${o.k}.${s}`]=t},s_=(i,e,t,n)=>{let{obj:r,k:s}=ia(i,e,Object);r[s]=r[s]||[],r[s].push(t)},Po=(i,e)=>{let{obj:t,k:n}=ia(i,e);if(t&&Object.prototype.hasOwnProperty.call(t,n))return t[n]},a_=(i,e,t)=>{let n=Po(i,t);return n!==void 0?n:Po(e,t)},xp=(i,e,t)=>{for(let n in e)n!=="__proto__"&&n!=="constructor"&&(Object.prototype.hasOwnProperty.call(i,n)?Ue(i[n])||i[n]instanceof String||Ue(e[n])||e[n]instanceof String?t&&(i[n]=e[n]):xp(i[n],e[n],t):i[n]=e[n]);return i},pn=i=>i.replace(/[\-\[\]\/\{\}\(\)\*\+\?\.\\\^\$\|]/g,"\\$&"),o_={"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;","/":"&#x2F;"},l_=i=>Ue(i)?i.replace(/[&<>"'\/]/g,e=>o_[e]):i,Lh=class{constructor(e){this.capacity=e,this.regExpMap=new Map,this.regExpQueue=[]}getRegExp(e){let t=this.regExpMap.get(e);if(t!==void 0)return t;let n=new RegExp(e);return this.regExpQueue.length===this.capacity&&this.regExpMap.delete(this.regExpQueue.shift()),this.regExpMap.set(e,n),this.regExpQueue.push(e),n}},c_=[" ",",","?","!",";"],h_=new Lh(20),u_=(i,e,t)=>{e=e||"",t=t||"";let n=c_.filter(a=>!e.includes(a)&&!t.includes(a));if(n.length===0)return!0;let r=h_.getRegExp(`(${n.map(a=>a==="?"?"\\?":a).join("|")})`),s=!r.test(i);if(!s){let a=i.indexOf(t);a>0&&!r.test(i.substring(0,a))&&(s=!0)}return s},Dh=(i,e,t=".")=>{if(!i)return;if(i[e])return Object.prototype.hasOwnProperty.call(i,e)?i[e]:void 0;let n=e.split(t),r=i;for(let s=0;s<n.length;){if(!r||typeof r!="object")return;let a,o="";for(let l=s;l<n.length;++l)if(l!==s&&(o+=t),o+=n[l],a=r[o],a!==void 0){if(["string","number","boolean"].includes(typeof a)&&l<n.length-1)continue;s+=l-s+1;break}r=a}return r},na=i=>i?.replace(/_/g,"-"),d_={type:"logger",log(i){this.output("log",i)},warn(i){this.output("warn",i)},error(i){this.output("error",i)},output(i,e){console?.[i]?.apply?.(console,e)}},Nh=class i{constructor(e,t={}){this.init(e,t)}init(e,t={}){this.prefix=t.prefix||"i18next:",this.logger=e||d_,this.options=t,this.debug=t.debug}log(...e){return this.forward(e,"log","",!0)}warn(...e){return this.forward(e,"warn","",!0)}error(...e){return this.forward(e,"error","")}deprecate(...e){return this.forward(e,"warn","WARNING DEPRECATED: ",!0)}forward(e,t,n,r){return r&&!this.debug?null:(e=e.map(s=>Ue(s)?s.replace(/[\r\n\x00-\x1F\x7F]/g," "):s),Ue(e[0])&&(e[0]=`${n}${this.prefix} ${e[0]}`),this.logger[t](e))}create(e){return new i(this.logger,{prefix:`${this.prefix}:${e}:`,...this.options})}clone(e){return e=e||this.options,e.prefix=e.prefix||this.prefix,new i(this.logger,e)}},Ji=new Nh,ts=class{constructor(){this.observers={}}on(e,t){return e.split(" ").forEach(n=>{this.observers[n]||(this.observers[n]=new Map);let r=this.observers[n].get(t)||0;this.observers[n].set(t,r+1)}),this}off(e,t){if(this.observers[e]){if(!t){delete this.observers[e];return}this.observers[e].delete(t)}}once(e,t){let n=(...r)=>{t(...r),this.off(e,n)};return this.on(e,n),this}emit(e,...t){this.observers[e]&&Array.from(this.observers[e].entries()).forEach(([r,s])=>{for(let a=0;a<s;a++)r(...t)}),this.observers["*"]&&Array.from(this.observers["*"].entries()).forEach(([r,s])=>{for(let a=0;a<s;a++)r(e,...t)})}},fp=new WeakSet,Io=class extends ts{constructor(e,t={ns:["translation"],defaultNS:"translation"}){super(),this.data=e||{},this.options=t,this.options.keySeparator===void 0&&(this.options.keySeparator="."),this.options.ignoreJSONStructure===void 0&&(this.options.ignoreJSONStructure=!0)}addNamespaces(e){this.options.ns.includes(e)||this.options.ns.push(e)}removeNamespaces(e){let t=this.options.ns.indexOf(e);t>-1&&this.options.ns.splice(t,1)}getResource(e,t,n,r={}){let s=r.keySeparator!==void 0?r.keySeparator:this.options.keySeparator,a=r.ignoreJSONStructure!==void 0?r.ignoreJSONStructure:this.options.ignoreJSONStructure,o;e.includes(".")?o=e.split("."):(o=[e,t],n&&(Array.isArray(n)?o.push(...n):Ue(n)&&s?o.push(...n.split(s)):o.push(n)));let l=Po(this.data,o);return!l&&!t&&!n&&e.includes(".")&&(e=o[0],t=o[1],n=o.slice(2).join(".")),l||!a||!Ue(n)?l:Dh(this.data?.[e]?.[t],n,s)}addResource(e,t,n,r,s={silent:!1}){let a=s.keySeparator!==void 0?s.keySeparator:this.options.keySeparator,o=[e,t];n&&(o=o.concat(a?n.split(a):n)),e.includes(".")&&(o=e.split("."),r=t,t=o[1]),this.addNamespaces(t),dp(this.data,o,r),s.silent||this.emit("added",e,t,n,r)}addResources(e,t,n,r={silent:!1}){for(let s in n)(Ue(n[s])||Array.isArray(n[s]))&&this.addResource(e,t,s,n[s],{silent:!0});r.silent||this.emit("added",e,t,n)}addResourceBundle(e,t,n,r,s,a={silent:!1,skipCopy:!1}){let o=[e,t];e.includes(".")&&(o=e.split("."),r=n,n=t,t=o[1]),this.addNamespaces(t);let l=Po(this.data,o)||{};a.skipCopy||(n=JSON.parse(JSON.stringify(n))),r?xp(l,n,s):l={...l,...n},dp(this.data,o,l),a.silent||this.emit("added",e,t,n)}removeResourceBundle(e,t){this.hasResourceBundle(e,t)&&delete this.data[e][t],this.removeNamespaces(t),this.emit("removed",e,t)}hasResourceBundle(e,t){return this.getResource(e,t)!==void 0}getResourceBundle(e,t){return t||(t=this.options.defaultNS),this.getResource(e,t)}getDataByLanguage(e){return this.data[e]}hasLanguageSomeTranslations(e){let t=this.getDataByLanguage(e);return!!(t&&Object.keys(t)||[]).find(r=>{let s=t[r];return fp.has(s)?!0:!s||Object.keys(s).length===0?!1:(typeof s=="object"&&fp.add(s),!0)})}toJSON(){return this.data}},vp={processors:{},addPostProcessor(i){this.processors[i.name]=i},handle(i,e,t,n,r){return i.forEach(s=>{e=this.processors[s]?.process(e,t,n,r)??e}),e}},bp=Symbol("i18next/PATH_KEY");function f_(){let i=[],e=Object.create(null),t;return e.get=(n,r)=>(t?.revoke?.(),r===bp?i:(i.push(r),t=Proxy.revocable(n,e),t.proxy)),Proxy.revocable(Object.create(null),e).proxy}function es(i,e){let{[bp]:t}=i(f_()),n=e?.keySeparator??".",r=e?.nsSeparator??":",s=e?.enableSelector==="strict";if(t.length>1&&r){let a=e?.ns,o=s?Array.isArray(a)?a:a?[a]:null:Array.isArray(a)?a:null;if(o&&(s?o:o.length>1?o.slice(1):[]).includes(t[0]))return`${t[0]}${r}${t.slice(1).join(n)}`}return t.join(n)}var Ph=i=>!Ue(i)&&typeof i!="boolean"&&typeof i!="number",Lo=class i extends ts{constructor(e,t={}){super(),n_(["resourceStore","languageUtils","pluralResolver","interpolator","backendConnector","i18nFormat","utils"],e,this),this.options=t,this.options.keySeparator===void 0&&(this.options.keySeparator="."),this.logger=Ji.create("translator"),this.checkedLoadedFor={}}changeLanguage(e){e&&(this.language=e)}exists(e,t={interpolation:{}}){let n={...t};if(e==null)return!1;let r=this.resolve(e,n);if(r?.res===void 0)return!1;let s=Ph(r.res);return!(n.returnObjects===!1&&s)}extractFromKey(e,t){let n=t.nsSeparator!==void 0?t.nsSeparator:this.options.nsSeparator;n===void 0&&(n=":");let r=t.keySeparator!==void 0?t.keySeparator:this.options.keySeparator,s=t.ns||this.options.defaultNS||[],a=n&&e.includes(n),o=!this.options.userDefinedKeySeparator&&!t.keySeparator&&!this.options.userDefinedNsSeparator&&!t.nsSeparator&&!u_(e,n,r);if(a&&!o){let l=e.match(this.interpolator.nestingRegexp);if(l&&l.length>0)return{key:e,namespaces:Ue(s)?[s]:s};let c=e.split(n);(n!==r||n===r&&this.options.ns.includes(c[0]))&&(s=c.shift()),e=c.join(r)}return{key:e,namespaces:Ue(s)?[s]:s}}translate(e,t,n){let r=typeof t=="object"?{...t}:t;if(typeof r!="object"&&this.options.overloadTranslationOptionHandler&&(r=this.options.overloadTranslationOptionHandler(arguments)),typeof r=="object"&&(r={...r}),r||(r={}),e==null)return"";typeof e=="function"&&(e=es(e,{...this.options,...r})),Array.isArray(e)||(e=[String(e)]),e=e.map(I=>typeof I=="function"?es(I,{...this.options,...r}):String(I));let s=r.returnDetails!==void 0?r.returnDetails:this.options.returnDetails,a=r.keySeparator!==void 0?r.keySeparator:this.options.keySeparator,{key:o,namespaces:l}=this.extractFromKey(e[e.length-1],r),c=l[l.length-1],h=r.nsSeparator!==void 0?r.nsSeparator:this.options.nsSeparator;h===void 0&&(h=":");let u=r.lng||this.language,d=r.appendNamespaceToCIMode||this.options.appendNamespaceToCIMode;if(u?.toLowerCase()==="cimode")return d?s?{res:`${c}${h}${o}`,usedKey:o,exactUsedKey:o,usedLng:u,usedNS:c,usedParams:this.getUsedParamsDetails(r)}:`${c}${h}${o}`:s?{res:o,usedKey:o,exactUsedKey:o,usedLng:u,usedNS:c,usedParams:this.getUsedParamsDetails(r)}:o;let f=this.resolve(e,r),p=f?.res,y=f?.usedKey||o,m=f?.exactUsedKey||o,g=["[object Number]","[object Function]","[object RegExp]"],v=r.joinArrays!==void 0?r.joinArrays:this.options.joinArrays,S=!this.i18nFormat||this.i18nFormat.handleAsObject,_=r.count!==void 0&&!Ue(r.count),M=i.hasDefaultValue(r),w=_?this.pluralResolver.getSuffix(u,r.count,r):"",E=r.ordinal&&_?this.pluralResolver.getSuffix(u,r.count,{ordinal:!1}):"",x=_&&!r.ordinal&&r.count===0,A=x&&r[`defaultValue${this.options.pluralSeparator}zero`]||r[`defaultValue${w}`]||r[`defaultValue${E}`]||r.defaultValue,C=p;S&&!p&&M&&(C=A);let D=Ph(C),U=Object.prototype.toString.apply(C);if(S&&C&&D&&!g.includes(U)&&!(Ue(v)&&Array.isArray(C))){if(!r.returnObjects&&!this.options.returnObjects){this.options.returnedObjectHandler||this.logger.warn("accessing an object - but returnObjects options is not enabled!");let I=this.options.returnedObjectHandler?this.options.returnedObjectHandler(y,C,{...r,ns:l}):`key '${o} (${this.language})' returned an object instead of string.`;return s?(f.res=I,f.usedParams=this.getUsedParamsDetails(r),f):I}if(a){let I=Array.isArray(C),L=I?[]:{},k=I?m:y;for(let H in C)if(Object.prototype.hasOwnProperty.call(C,H)){let X=`${k}${a}${H}`;M&&!p?L[H]=this.translate(X,{...r,defaultValue:Ph(A)?A[H]:void 0,joinArrays:!1,ns:l}):L[H]=this.translate(X,{...r,joinArrays:!1,ns:l}),L[H]===X&&(L[H]=C[H])}p=L}}else if(S&&Ue(v)&&Array.isArray(p))p=p.join(v),p&&(p=this.extendTranslation(p,e,r,n));else{let I=!1,L=!1;!this.isValidLookup(p)&&M&&(I=!0,p=A),this.isValidLookup(p)||(L=!0,p=o);let H=(r.missingKeyNoValueFallbackToKey||this.options.missingKeyNoValueFallbackToKey)&&L?void 0:p,X=M&&A!==p&&this.options.updateMissing;if(L||I||X){if(this.logger.log(X?"updateKey":"missingKey",u,c,_&&!X?`${o}${this.pluralResolver.getSuffix(u,r.count,r)}`:o,X?A:p),a){let N=this.resolve(o,{...r,keySeparator:!1});N&&N.res&&this.logger.warn("Seems the loaded translations were in flat JSON format instead of nested. Either set keySeparator: false on init or make sure your translations are published in nested format.")}let Y=[],q=this.languageUtils.getFallbackCodes(this.options.fallbackLng,r.lng||this.language);if(this.options.saveMissingTo==="fallback"&&q&&q[0])for(let N=0;N<q.length;N++)Y.push(q[N]);else this.options.saveMissingTo==="all"?Y=this.languageUtils.toResolveHierarchy(r.lng||this.language):Y.push(r.lng||this.language);let K=(N,ie,re)=>{let De=M&&re!==p?re:H;this.options.missingKeyHandler?this.options.missingKeyHandler(N,c,ie,De,X,r):this.backendConnector?.saveMissing&&this.backendConnector.saveMissing(N,c,ie,De,X,r),this.emit("missingKey",N,c,ie,p)};this.options.saveMissing&&(this.options.saveMissingPlurals&&_?Y.forEach(N=>{let ie=this.pluralResolver.getSuffixes(N,r);x&&r[`defaultValue${this.options.pluralSeparator}zero`]&&!ie.includes(`${this.options.pluralSeparator}zero`)&&ie.push(`${this.options.pluralSeparator}zero`),ie.forEach(re=>{K([N],o+re,r[`defaultValue${re}`]||A)})}):K(Y,o,A))}p=this.extendTranslation(p,e,r,f,n),L&&p===o&&this.options.appendNamespaceToMissingKey&&(p=`${c}${h}${o}`),(L||I)&&this.options.parseMissingKeyHandler&&(p=this.options.parseMissingKeyHandler(this.options.appendNamespaceToMissingKey?`${c}${h}${o}`:o,I?p:void 0,r))}return s?(f.res=p,f.usedParams=this.getUsedParamsDetails(r),f):p}extendTranslation(e,t,n,r,s){if(this.i18nFormat?.parse)e=this.i18nFormat.parse(e,{...this.options.interpolation.defaultVariables,...n},n.lng||this.language||r.usedLng,r.usedNS,r.usedKey,{resolved:r});else if(!n.skipInterpolation){n.interpolation&&this.interpolator.init({...n,interpolation:{...this.options.interpolation,...n.interpolation}});let l=Ue(e)&&(n?.interpolation?.skipOnVariables!==void 0?n.interpolation.skipOnVariables:this.options.interpolation.skipOnVariables),c;if(l){let u=e.match(this.interpolator.nestingRegexp);c=u&&u.length}let h=n.replace&&!Ue(n.replace)?n.replace:n;if(this.options.interpolation.defaultVariables&&(h={...this.options.interpolation.defaultVariables,...h}),e=this.interpolator.interpolate(e,h,n.lng||this.language||r.usedLng,n),l){let u=e.match(this.interpolator.nestingRegexp),d=u&&u.length;c<d&&(n.nest=!1)}!n.lng&&r&&r.res&&(n.lng=this.language||r.usedLng),n.nest!==!1&&(e=this.interpolator.nest(e,(...u)=>s?.[0]===u[0]&&!n.context?(this.logger.warn(`It seems you are nesting recursively key: ${u[0]} in key: ${t[0]}`),null):this.translate(...u,t),n)),n.interpolation&&this.interpolator.reset()}let a=n.postProcess||this.options.postProcess,o=Ue(a)?[a]:a;return e!=null&&o?.length&&n.applyPostProcessor!==!1&&(e=vp.handle(o,e,t,this.options&&this.options.postProcessPassResolved?{i18nResolved:{...r,usedParams:this.getUsedParamsDetails(n)},...n}:n,this)),e}resolve(e,t={}){let n,r,s,a,o;return Ue(e)&&(e=[e]),Array.isArray(e)&&(e=e.map(l=>typeof l=="function"?es(l,{...this.options,...t}):l)),e.forEach(l=>{if(this.isValidLookup(n))return;let c=this.extractFromKey(l,t),h=c.key;r=h;let u=c.namespaces;this.options.fallbackNS&&(u=u.concat(this.options.fallbackNS));let d=t.count!==void 0&&!Ue(t.count),f=d&&!t.ordinal&&t.count===0,p=t.context!==void 0&&(Ue(t.context)||typeof t.context=="number")&&t.context!=="",y=t.lngs?t.lngs:this.languageUtils.toResolveHierarchy(t.lng||this.language,t.fallbackLng);u.forEach(m=>{this.isValidLookup(n)||(o=m,!this.checkedLoadedFor[`${y[0]}-${m}`]&&this.utils?.hasLoadedNamespace&&!this.utils?.hasLoadedNamespace(o)&&(this.checkedLoadedFor[`${y[0]}-${m}`]=!0,this.logger.warn(`key "${r}" for languages "${y.join(", ")}" won't get resolved as namespace "${o}" was not yet loaded`,"This means something IS WRONG in your setup. You access the t function before i18next.init / i18next.loadNamespace / i18next.changeLanguage was done. Wait for the callback or Promise to resolve before accessing it!!!")),y.forEach(g=>{if(this.isValidLookup(n))return;a=g;let v=[h];if(this.i18nFormat?.addLookupKeys)this.i18nFormat.addLookupKeys(v,h,g,m,t);else{let _;d&&(_=this.pluralResolver.getSuffix(g,t.count,t));let M=`${this.options.pluralSeparator}zero`,w=`${this.options.pluralSeparator}ordinal${this.options.pluralSeparator}`;if(d&&(t.ordinal&&_.startsWith(w)&&v.push(h+_.replace(w,this.options.pluralSeparator)),v.push(h+_),f&&v.push(h+M)),p){let E=`${h}${this.options.contextSeparator||"_"}${t.context}`;v.push(E),d&&(t.ordinal&&_.startsWith(w)&&v.push(E+_.replace(w,this.options.pluralSeparator)),v.push(E+_),f&&v.push(E+M))}}let S;for(;S=v.pop();)this.isValidLookup(n)||(s=S,n=this.getResource(g,m,S,t))}))})}),{res:n,usedKey:r,exactUsedKey:s,usedLng:a,usedNS:o}}isValidLookup(e){return e!==void 0&&!(!this.options.returnNull&&e===null)&&!(!this.options.returnEmptyString&&e==="")}getResource(e,t,n,r={}){return this.i18nFormat?.getResource?this.i18nFormat.getResource(e,t,n,r):this.resourceStore.getResource(e,t,n,r)}getUsedParamsDetails(e={}){let t=["defaultValue","ordinal","context","replace","lng","lngs","fallbackLng","ns","keySeparator","nsSeparator","returnObjects","returnDetails","joinArrays","postProcess","interpolation"],n=e.replace&&!Ue(e.replace),r=n?e.replace:e;if(n&&typeof e.count<"u"&&(r={...r,count:e.count}),this.options.interpolation.defaultVariables&&(r={...this.options.interpolation.defaultVariables,...r}),!n){r={...r};for(let s of t)delete r[s]}return r}static hasDefaultValue(e){let t="defaultValue";for(let n in e)if(Object.prototype.hasOwnProperty.call(e,n)&&n.startsWith(t)&&e[n]!==void 0)return!0;return!1}},Do=class{constructor(e){this.options=e,this.supportedLngs=this.options.supportedLngs||!1,this.logger=Ji.create("languageUtils"),this.resolveHierarchyCache={}}clearCache(){this.resolveHierarchyCache={}}getScriptPartFromCode(e){if(e=na(e),!e||!e.includes("-"))return null;let t=e.split("-");return t.length===2||(t.pop(),t[t.length-1].toLowerCase()==="x")?null:this.formatLanguageCode(t.join("-"))}getLanguagePartFromCode(e){if(e=na(e),!e||!e.includes("-"))return e;let t=e.split("-");return this.formatLanguageCode(t[0])}formatLanguageCode(e){if(Ue(e)&&e.includes("-")){let t;try{t=Intl.getCanonicalLocales(e)[0]}catch{}return t&&this.options.lowerCaseLng&&(t=t.toLowerCase()),t||(this.options.lowerCaseLng?e.toLowerCase():e)}return this.options.cleanCode||this.options.lowerCaseLng?e.toLowerCase():e}isSupportedCode(e){return(this.options.load==="languageOnly"||this.options.nonExplicitSupportedLngs)&&(e=this.getLanguagePartFromCode(e)),!this.supportedLngs||!this.supportedLngs.length||this.supportedLngs.includes(e)}getBestMatchFromCodes(e){if(!e)return null;let t;return e.forEach(n=>{if(t)return;let r=this.formatLanguageCode(n);(!this.options.supportedLngs||this.isSupportedCode(r))&&(t=r)}),!t&&this.options.supportedLngs&&e.forEach(n=>{if(t)return;let r=this.getScriptPartFromCode(n);if(this.isSupportedCode(r))return t=r;let s=this.getLanguagePartFromCode(n);if(this.isSupportedCode(s))return t=s;t=this.options.supportedLngs.find(a=>a===s?!0:!a.includes("-")&&!s.includes("-")?!1:!!(a.includes("-")&&!s.includes("-")&&a.slice(0,a.indexOf("-"))===s||a.startsWith(s)&&s.length>1))}),t||(t=this.getFallbackCodes(this.options.fallbackLng)[0]),t}getFallbackCodes(e,t){if(!e)return[];if(typeof e=="function"&&(e=e(t)),Ue(e)&&(e=[e]),Array.isArray(e))return e;if(!t)return e.default||[];let n=e[t];return n||(n=e[this.getScriptPartFromCode(t)]),n||(n=e[this.formatLanguageCode(t)]),n||(n=e[this.getLanguagePartFromCode(t)]),n||(n=e.default),n||[]}toResolveHierarchy(e,t){let n=this.options.fallbackLng,r=Array.isArray(n)?n.join("|"):n;r!==this._cachedFallbackLng&&(this.resolveHierarchyCache={},this._cachedFallbackLng=r);let s=t===void 0||t===!1||Ue(t),a=t===void 0&&typeof this.options.fallbackLng=="function",o=Ue(e)&&s&&!a,l=null;if(o){let d;t===void 0?d="undefined":t===!1?d="boolean:false":d=`string:${t}`,l=`${e.length}:${e}|${d}`}if(l!==null){let d=this.resolveHierarchyCache[l];if(d!==void 0)return d.slice()}let c=this.getFallbackCodes((t===!1?[]:t)||this.options.fallbackLng||[],e),h=[],u=d=>{d&&(this.isSupportedCode(d)?h.push(d):this.logger.warn(`rejecting language code not found in supportedLngs: ${d}`))};return Ue(e)&&(e.includes("-")||e.includes("_"))?(this.options.load!=="languageOnly"&&u(this.formatLanguageCode(e)),this.options.load!=="languageOnly"&&this.options.load!=="currentOnly"&&u(this.getScriptPartFromCode(e)),this.options.load!=="currentOnly"&&u(this.getLanguagePartFromCode(e))):Ue(e)&&u(this.formatLanguageCode(e)),c.forEach(d=>{let f=this.formatLanguageCode(d);h.includes(f)||u(f)}),l!==null?(this.resolveHierarchyCache[l]=h,h.slice()):h}},pp={zero:0,one:1,two:2,few:3,many:4,other:5},mp={select:i=>i===1?"one":"other",resolvedOptions:()=>({pluralCategories:["one","other"]})},Uh=class{constructor(e,t={}){this.languageUtils=e,this.options=t,this.logger=Ji.create("pluralResolver"),this.pluralRulesCache={}}clearCache(){this.pluralRulesCache={}}getRule(e,t={}){let n=na(e==="dev"?"en":e),r=t.ordinal?"ordinal":"cardinal",s=JSON.stringify({cleanedCode:n,type:r});if(s in this.pluralRulesCache)return this.pluralRulesCache[s];let a;try{a=new Intl.PluralRules(n,{type:r})}catch{if(typeof Intl>"u")return this.logger.error("No Intl support, please use an Intl polyfill!"),mp;if(!e.match(/-|_/))return mp;let l=this.languageUtils.getLanguagePartFromCode(e);a=this.getRule(l,t)}return this.pluralRulesCache[s]=a,a}needsPlural(e,t={}){let n=this.getRule(e,t);return n||(n=this.getRule("dev",t)),n?.resolvedOptions().pluralCategories.length>1}getPluralFormsOfKey(e,t,n={}){return this.getSuffixes(e,n).map(r=>`${t}${r}`)}getSuffixes(e,t={}){let n=this.getRule(e,t);return n||(n=this.getRule("dev",t)),n?n.resolvedOptions().pluralCategories.sort((r,s)=>pp[r]-pp[s]).map(r=>`${this.options.prepend}${t.ordinal?`ordinal${this.options.prepend}`:""}${r}`):[]}getSuffix(e,t,n={}){let r=this.getRule(e,n);return r?`${this.options.prepend}${n.ordinal?`ordinal${this.options.prepend}`:""}${r.select(t)}`:(this.logger.warn(`no plural rule found for: ${e}`),this.getSuffix("dev",t,n))}},gp=(i,e,t,n=".",r=!0)=>{let s=a_(i,e,t);return!s&&r&&Ue(t)&&(s=Dh(i,t,n),s===void 0&&(s=Dh(e,t,n))),s},p_=i=>i.replace(/\$/g,"$$$$"),No=class{constructor(e={}){this.logger=Ji.create("interpolator"),this.options=e,this.format=e?.interpolation?.format||(t=>t),this.init(e)}init(e={}){e.interpolation||(e.interpolation={escapeValue:!0});let{escape:t,escapeValue:n,useRawValueToEscape:r,prefix:s,prefixEscaped:a,suffix:o,suffixEscaped:l,formatSeparator:c,unescapeSuffix:h,unescapePrefix:u,nestingPrefix:d,nestingPrefixEscaped:f,nestingSuffix:p,nestingSuffixEscaped:y,nestingOptionsSeparator:m,maxReplaces:g,alwaysFormat:v}=e.interpolation;this.escape=t!==void 0?t:l_,this.escapeValue=n!==void 0?n:!0,this.useRawValueToEscape=r!==void 0?r:!1,this.prefix=s?pn(s):a||"{{",this.suffix=o?pn(o):l||"}}",this.formatSeparator=c||",",this.unescapePrefix=h?"":u?pn(u):"-",this.unescapeSuffix=this.unescapePrefix?"":h?pn(h):"",this.nestingPrefix=d?pn(d):f||pn("$t("),this.nestingSuffix=p?pn(p):y||pn(")"),this.nestingOptionsSeparator=m||",",this.maxReplaces=g||1e3,this.alwaysFormat=v!==void 0?v:!1,this.resetRegExp()}reset(){this.options&&this.init(this.options)}resetRegExp(){let e=(t,n)=>t?.source===n?(t.lastIndex=0,t):new RegExp(n,"g");this.regexp=e(this.regexp,`${this.prefix}(.+?)${this.suffix}`),this.regexpUnescape=e(this.regexpUnescape,`${this.prefix}${this.unescapePrefix}(.+?)${this.unescapeSuffix}${this.suffix}`),this.nestingRegexp=e(this.nestingRegexp,`${this.nestingPrefix}((?:[^()"']|"[^"]*"|'[^']*'|\\((?:[^()"']|"[^"]*"|'[^']*')*\\))*?)${this.nestingSuffix}`)}interpolate(e,t,n,r){let s,a,o,l=this.options&&this.options.interpolation&&this.options.interpolation.defaultVariables||{},c=f=>{if(!f.includes(this.formatSeparator)){let g=gp(t,l,f,this.options.keySeparator,this.options.ignoreJSONStructure);return this.alwaysFormat?this.format(g,void 0,n,{...r,...t,interpolationkey:f}):g}let p=f.split(this.formatSeparator),y=p.shift().trim(),m=p.join(this.formatSeparator).trim();return this.format(gp(t,l,y,this.options.keySeparator,this.options.ignoreJSONStructure),m,n,{...r,...t,interpolationkey:y})};this.resetRegExp(),!this.escapeValue&&typeof e=="string"&&/\$t\([^)]*\{[^}]*\{\{/.test(e)&&this.logger.warn("nesting options string contains interpolated variables with escapeValue: false \u2014 if any of those values are attacker-controlled they can inject additional nesting options (e.g. redirect lng/ns). Sanitise untrusted input before passing it to t(), or keep escapeValue: true.");let h=r?.missingInterpolationHandler||this.options.missingInterpolationHandler,u=r?.interpolation?.skipOnVariables!==void 0?r.interpolation.skipOnVariables:this.options.interpolation.skipOnVariables;return[{regex:this.regexpUnescape,safeValue:f=>f},{regex:this.regexp,safeValue:f=>this.escapeValue?this.escape(f):f}].forEach(f=>{for(o=0;s=f.regex.exec(e);){let p=s[1].trim();if(a=c(p),a===void 0)if(typeof h=="function"){let m=h(e,s,r);a=Ue(m)?m:""}else if(r&&Object.prototype.hasOwnProperty.call(r,p))a="";else if(u){a=s[0];continue}else this.logger.warn(`missed to pass in variable ${p} for interpolating ${e}`),a="";else!Ue(a)&&!this.useRawValueToEscape&&(a=Rh(a));let y=f.safeValue(a);if(e=e.replace(s[0],p_(y)),u?(f.regex.lastIndex+=y.length,f.regex.lastIndex-=s[0].length):f.regex.lastIndex=0,o++,o>=this.maxReplaces)break}}),e}nest(e,t,n={}){let r,s,a,o=(u,d)=>{let f=this.nestingOptionsSeparator;if(!u.includes(f))return u;let p=u.split(new RegExp(`${pn(f)}[ ]*{`)),y=`{${p[1]}`;u=p[0],y=this.interpolate(y,a);let m=y.match(/'/g),g=y.match(/"/g);((m?.length??0)%2===0&&!g||(g?.length??0)%2!==0)&&(y=y.replace(/'/g,'"'));try{a=JSON.parse(y),d&&(a={...d,...a})}catch(v){return this.logger.warn(`failed parsing options string in nesting for key ${u}`,v),`${u}${f}${y}`}return a.defaultValue&&a.defaultValue.includes(this.prefix)&&delete a.defaultValue,u},l=new RegExp(this.nestingRegexp),c="",h=0;for(;r=l.exec(e);){let u=[];a={...n},a=a.replace&&!Ue(a.replace)?a.replace:a,a.applyPostProcessor=!1,delete a.defaultValue;let d=/{.*}/s.test(r[1])?r[1].lastIndexOf("}")+1:r[1].indexOf(this.formatSeparator);if(d!==-1&&(u=r[1].slice(d).split(this.formatSeparator).map(f=>f.trim()).filter(Boolean),r[1]=r[1].slice(0,d)),s=t(o.call(this,r[1].trim(),a),a),s&&r[0]===e&&!Ue(s))return s;Ue(s)||(s=Rh(s)),s||(this.logger.warn(`missed to resolve ${r[1]} for nesting ${e}`),s=""),u.length&&(s=u.reduce((f,p)=>this.format(f,p,n.lng,{...n,interpolationkey:r[1].trim()}),s.trim())),c+=e.slice(h,r.index)+Rh(s),h=l.lastIndex,this.regexp.lastIndex=0}return h?c+e.slice(h):e}},m_=i=>{let e=i.toLowerCase().trim(),t={};if(i.includes("(")){let n=i.split("(");e=n[0].toLowerCase().trim();let r=n[1].slice(0,-1);e==="currency"&&!r.includes(":")?t.currency||(t.currency=r.trim()):e==="relativetime"&&!r.includes(":")?t.range||(t.range=r.trim()):r.split(";").forEach(a=>{if(a){let[o,...l]=a.split(":"),c=l.join(":").trim().replace(/^'+|'+$/g,""),h=o.trim();t[h]||(t[h]=c),c==="false"&&(t[h]=!1),c==="true"&&(t[h]=!0),isNaN(c)||(t[h]=parseInt(c,10))}})}return{formatName:e,formatOptions:t}},yp=i=>{let e={};return(t,n,r)=>{let s=r;r&&r.interpolationkey&&r.formatParams&&r.formatParams[r.interpolationkey]&&r[r.interpolationkey]&&(s={...s,[r.interpolationkey]:void 0});let a=n+JSON.stringify(s),o=e[a];return o||(o=i(na(n),r),e[a]=o),o(t)}},g_=i=>(e,t,n)=>i(na(t),n)(e),Oh=class{constructor(e={}){this.logger=Ji.create("formatter"),this.options=e,this.init(e)}init(e,t={interpolation:{}}){this.formatSeparator=t.interpolation.formatSeparator||",";let n=t.cacheInBuiltFormats?yp:g_;this.formats={number:n((r,s)=>{let a=new Intl.NumberFormat(r,{...s});return o=>a.format(o)}),currency:n((r,s)=>{let a=new Intl.NumberFormat(r,{...s,style:"currency"});return o=>a.format(o)}),datetime:n((r,s)=>{let a=new Intl.DateTimeFormat(r,{...s});return o=>a.format(o)}),relativetime:n((r,s)=>{let a=new Intl.RelativeTimeFormat(r,{...s});return o=>a.format(o,s.range||"day")}),list:n((r,s)=>{let a=new Intl.ListFormat(r,{...s});return o=>a.format(o)})}}add(e,t){this.formats[e.toLowerCase().trim()]=t}addCached(e,t){this.formats[e.toLowerCase().trim()]=yp(t)}format(e,t,n,r={}){if(!t||e==null)return e;let s=t.split(this.formatSeparator),a=[];for(let l=0;l<s.length;l++){let c=s[l];for(;c.indexOf("(")>-1&&!c.includes(")")&&l+1<s.length;)c=`${c}${this.formatSeparator}${s[++l]}`;a.push(c)}return a.reduce((l,c)=>{let{formatName:h,formatOptions:u}=m_(c);if(this.formats[h]){let d=l;try{let f=r?.formatParams?.[r.interpolationkey]||{},p=f.locale||f.lng||r.locale||r.lng||n;d=this.formats[h](l,p,{...u,...r,...f})}catch(f){this.logger.warn(f)}return d}else this.logger.warn(`there was no format function for ${h}`);return l},e)}},y_=(i,e)=>{i.pending[e]!==void 0&&(delete i.pending[e],i.pendingCount--)},Fh=class extends ts{constructor(e,t,n,r={}){super(),this.backend=e,this.store=t,this.services=n,this.languageUtils=n.languageUtils,this.options=r,this.logger=Ji.create("backendConnector"),this.waitingReads=[],this.maxParallelReads=r.maxParallelReads||10,this.readingCalls=0,this.maxRetries=r.maxRetries>=0?r.maxRetries:5,this.retryTimeout=r.retryTimeout>=1?r.retryTimeout:350,this.state={},this.queue=[],this.backend?.init?.(n,r.backend,r)}queueLoad(e,t,n,r){let s={},a={},o={},l={};return e.forEach(c=>{let h=!0;t.forEach(u=>{let d=`${c}|${u}`;!n.reload&&this.store.hasResourceBundle(c,u)?this.state[d]=2:this.state[d]<0||(this.state[d]===1?a[d]===void 0&&(a[d]=!0):(this.state[d]=1,h=!1,a[d]===void 0&&(a[d]=!0),s[d]===void 0&&(s[d]=!0),l[u]===void 0&&(l[u]=!0)))}),h||(o[c]=!0)}),(Object.keys(s).length||Object.keys(a).length)&&this.queue.push({pending:a,pendingCount:Object.keys(a).length,loaded:{},errors:[],callback:r}),{toLoad:Object.keys(s),pending:Object.keys(a),toLoadLanguages:Object.keys(o),toLoadNamespaces:Object.keys(l)}}loaded(e,t,n){let r=e.split("|"),s=r[0],a=r[1];t&&this.emit("failedLoading",s,a,t),!t&&n&&this.store.addResourceBundle(s,a,n,void 0,void 0,{skipCopy:!0}),this.state[e]=t?-1:2,t&&n&&(this.state[e]=0);let o={};this.queue.forEach(l=>{s_(l.loaded,[s],a),y_(l,e),t&&l.errors.push(t),l.pendingCount===0&&!l.done&&(Object.keys(l.loaded).forEach(c=>{o[c]||(o[c]={});let h=l.loaded[c];h.length&&h.forEach(u=>{o[c][u]===void 0&&(o[c][u]=!0)})}),l.done=!0,l.errors.length?l.callback(l.errors):l.callback())}),this.emit("loaded",o),this.queue=this.queue.filter(l=>!l.done)}read(e,t,n,r=0,s=this.retryTimeout,a){if(!e.length)return a(null,{});if(this.readingCalls>=this.maxParallelReads){this.waitingReads.push({lng:e,ns:t,fcName:n,tried:r,wait:s,callback:a});return}this.readingCalls++;let o=(c,h)=>{if(this.readingCalls--,this.waitingReads.length>0){let u=this.waitingReads.shift();this.read(u.lng,u.ns,u.fcName,u.tried,u.wait,u.callback)}if(c&&h&&r<this.maxRetries){setTimeout(()=>{this.read(e,t,n,r+1,s*2,a)},s);return}a(c,h)},l=this.backend[n].bind(this.backend);if(l.length===2){try{let c=l(e,t);c&&typeof c.then=="function"?c.then(h=>o(null,h)).catch(o):o(null,c)}catch(c){o(c)}return}return l(e,t,o)}prepareLoading(e,t,n={},r){if(!this.backend)return this.logger.warn("No backend was added via i18next.use. Will not load resources."),r&&r();Ue(e)&&(e=this.languageUtils.toResolveHierarchy(e)),Ue(t)&&(t=[t]);let s=this.queueLoad(e,t,n,r);if(!s.toLoad.length)return s.pending.length||r(),null;s.toLoad.forEach(a=>{this.loadOne(a)})}load(e,t,n){this.prepareLoading(e,t,{},n)}reload(e,t,n){this.prepareLoading(e,t,{reload:!0},n)}loadOne(e,t=""){let n=e.split("|"),r=n[0],s=n[1];this.read(r,s,"read",void 0,void 0,(a,o)=>{a&&this.logger.warn(`${t}loading namespace ${s} for language ${r} failed`,a),!a&&o&&this.logger.log(`${t}loaded namespace ${s} for language ${r}`,o),this.loaded(e,a,o)})}saveMissing(e,t,n,r,s,a={},o=()=>{}){if(this.services?.utils?.hasLoadedNamespace&&!this.services?.utils?.hasLoadedNamespace(t)){this.logger.warn(`did not save key "${n}" as the namespace "${t}" was not yet loaded`,"This means something IS WRONG in your setup. You access the t function before i18next.init / i18next.loadNamespace / i18next.changeLanguage was done. Wait for the callback or Promise to resolve before accessing it!!!");return}if(!(n==null||n==="")){if(this.backend?.create){let l={...a,isUpdate:s},c=this.backend.create.bind(this.backend);if(c.length<6)try{let h;c.length===5?h=c(e,t,n,r,l):h=c(e,t,n,r),h&&typeof h.then=="function"?h.then(u=>o(null,u)).catch(o):o(null,h)}catch(h){o(h)}else c(e,t,n,r,o,l)}!e||!e[0]||this.store.addResource(e[0],t,n,r)}}},Ih=()=>({debug:!1,initAsync:!0,ns:["translation"],defaultNS:["translation"],fallbackLng:["dev"],fallbackNS:!1,supportedLngs:!1,nonExplicitSupportedLngs:!1,load:"all",preload:!1,keySeparator:".",nsSeparator:":",pluralSeparator:"_",contextSeparator:"_",enableSelector:!1,partialBundledLanguages:!1,saveMissing:!1,updateMissing:!1,saveMissingTo:"fallback",saveMissingPlurals:!0,missingKeyHandler:!1,missingInterpolationHandler:!1,postProcess:!1,postProcessPassResolved:!1,returnNull:!1,returnEmptyString:!0,returnObjects:!1,joinArrays:!1,returnedObjectHandler:!1,parseMissingKeyHandler:!1,appendNamespaceToMissingKey:!1,appendNamespaceToCIMode:!1,overloadTranslationOptionHandler:i=>{let e={};if(typeof i[1]=="object"&&(e=i[1]),Ue(i[1])&&(e.defaultValue=i[1]),Ue(i[2])&&(e.tDescription=i[2]),typeof i[2]=="object"||typeof i[3]=="object"){let t=i[3]||i[2];Object.keys(t).forEach(n=>{e[n]=t[n]})}return e},interpolation:{escapeValue:!0,prefix:"{{",suffix:"}}",formatSeparator:",",unescapePrefix:"-",nestingPrefix:"$t(",nestingSuffix:")",nestingOptionsSeparator:",",maxReplaces:1e3,skipOnVariables:!0},cacheInBuiltFormats:!0}),_p=i=>(Ue(i.ns)&&(i.ns=[i.ns]),Ue(i.fallbackLng)&&(i.fallbackLng=[i.fallbackLng]),Ue(i.fallbackNS)&&(i.fallbackNS=[i.fallbackNS]),i.supportedLngs&&!i.supportedLngs.includes("cimode")&&(i.supportedLngs=i.supportedLngs.concat(["cimode"])),i),Ro=()=>{},__=i=>{Object.getOwnPropertyNames(Object.getPrototypeOf(i)).forEach(t=>{typeof i[t]=="function"&&(i[t]=i[t].bind(i))})},Bh=class i extends ts{constructor(e={},t){if(super(),this.options=_p(e),this.services={},this.logger=Ji,this.modules={external:[]},__(this),t&&!this.isInitialized&&!e.isClone){if(!this.options.initAsync)return this.init(e,t),this;setTimeout(()=>{this.init(e,t)},0)}}init(e={},t){this.isInitializing=!0,typeof e=="function"&&(t=e,e={}),e.defaultNS==null&&e.ns&&(Ue(e.ns)?e.defaultNS=e.ns:e.ns.includes("translation")||(e.defaultNS=e.ns[0]));let n=Ih();this.options={...n,...this.options,..._p(e)},this.options.interpolation={...n.interpolation,...this.options.interpolation},e.keySeparator!==void 0&&(this.options.userDefinedKeySeparator=e.keySeparator),e.nsSeparator!==void 0&&(this.options.userDefinedNsSeparator=e.nsSeparator),typeof this.options.overloadTranslationOptionHandler!="function"&&(this.options.overloadTranslationOptionHandler=n.overloadTranslationOptionHandler);let r=c=>c?typeof c=="function"?new c:c:null;if(!this.options.isClone){this.modules.logger?Ji.init(r(this.modules.logger),this.options):Ji.init(null,this.options);let c;this.modules.formatter?c=this.modules.formatter:c=Oh;let h=new Do(this.options);this.store=new Io(this.options.resources,this.options);let u=this.services;u.logger=Ji,u.resourceStore=this.store,u.languageUtils=h,u.pluralResolver=new Uh(h,{prepend:this.options.pluralSeparator}),c&&(u.formatter=r(c),u.formatter.init&&u.formatter.init(u,this.options),this.options.interpolation.format=u.formatter.format.bind(u.formatter)),u.interpolator=new No(this.options),u.utils={hasLoadedNamespace:this.hasLoadedNamespace.bind(this)},u.backendConnector=new Fh(r(this.modules.backend),u.resourceStore,u,this.options),u.backendConnector.on("*",(d,...f)=>{this.emit(d,...f)}),this.modules.languageDetector&&(u.languageDetector=r(this.modules.languageDetector),u.languageDetector.init&&u.languageDetector.init(u,this.options.detection,this.options)),this.modules.i18nFormat&&(u.i18nFormat=r(this.modules.i18nFormat),u.i18nFormat.init&&u.i18nFormat.init(this)),this.translator=new Lo(this.services,this.options),this.translator.on("*",(d,...f)=>{this.emit(d,...f)}),this.modules.external.forEach(d=>{d.init&&d.init(this)})}if(this.format=this.options.interpolation.format,t||(t=Ro),this.options.fallbackLng&&!this.services.languageDetector&&!this.options.lng){let c=this.services.languageUtils.getFallbackCodes(this.options.fallbackLng);c.length>0&&c[0]!=="dev"&&(this.options.lng=c[0])}!this.services.languageDetector&&!this.options.lng&&this.logger.warn("init: no languageDetector is used and no lng is defined"),["getResource","hasResourceBundle","getResourceBundle","getDataByLanguage"].forEach(c=>{this[c]=(...h)=>this.store[c](...h)}),["addResource","addResources","addResourceBundle","removeResourceBundle"].forEach(c=>{this[c]=(...h)=>(this.store[c](...h),this)});let o=ta(),l=()=>{let c=(h,u)=>{this.isInitializing=!1,this.isInitialized&&!this.initializedStoreOnce&&this.logger.warn("init: i18next is already initialized. You should call init just once!"),this.isInitialized=!0,this.options.isClone||this.logger.log("initialized",this.options),this.emit("initialized",this.options),o.resolve(u),t(h,u)};if((this.languages||this.isLanguageChangingTo)&&!this.isInitialized)return c(null,this.t.bind(this));this.changeLanguage(this.options.lng,c)};return this.options.resources||!this.options.initAsync?l():setTimeout(l,0),o}loadResources(e,t=Ro){let n=t,r=Ue(e)?e:this.language;if(typeof e=="function"&&(n=e),!this.options.resources||this.options.partialBundledLanguages){if(r?.toLowerCase()==="cimode"&&(!this.options.preload||this.options.preload.length===0))return n();let s=[],a=o=>{if(!o||o==="cimode")return;this.services.languageUtils.toResolveHierarchy(o).forEach(c=>{c!=="cimode"&&(s.includes(c)||s.push(c))})};r?a(r):this.services.languageUtils.getFallbackCodes(this.options.fallbackLng).forEach(l=>a(l)),this.options.preload?.forEach?.(o=>a(o)),this.services.backendConnector.load(s,this.options.ns,o=>{!o&&!this.resolvedLanguage&&this.language&&this.setResolvedLanguage(this.language),n(o)})}else n(null)}reloadResources(e,t,n){let r=ta();return typeof e=="function"&&(n=e,e=void 0),typeof t=="function"&&(n=t,t=void 0),e||(e=this.languages),t||(t=this.options.ns),n||(n=Ro),this.services.backendConnector.reload(e,t,s=>{r.resolve(),n(s)}),r}use(e){if(!e)throw new Error("You are passing an undefined module! Please check the object you are passing to i18next.use()");if(!e.type)throw new Error("You are passing a wrong module! Please check the object you are passing to i18next.use()");return e.type==="backend"&&(this.modules.backend=e),(e.type==="logger"||e.log&&e.warn&&e.error)&&(this.modules.logger=e),e.type==="languageDetector"&&(this.modules.languageDetector=e),e.type==="i18nFormat"&&(this.modules.i18nFormat=e),e.type==="postProcessor"&&vp.addPostProcessor(e),e.type==="formatter"&&(this.modules.formatter=e),e.type==="3rdParty"&&this.modules.external.push(e),this}setResolvedLanguage(e){if(!(!e||!this.languages)&&!["cimode","dev"].includes(e)){for(let t=0;t<this.languages.length;t++){let n=this.languages[t];if(!["cimode","dev"].includes(n)&&this.store.hasLanguageSomeTranslations(n)){this.resolvedLanguage=n;break}}!this.resolvedLanguage&&!this.languages.includes(e)&&this.store.hasLanguageSomeTranslations(e)&&(this.resolvedLanguage=e,this.languages.unshift(e))}}changeLanguage(e,t){this.isLanguageChangingTo=e;let n=ta();this.emit("languageChanging",e);let r=o=>{this.language=o,this.languages=this.services.languageUtils.toResolveHierarchy(o),this.resolvedLanguage=void 0,this.setResolvedLanguage(o)},s=(o,l)=>{l?this.isLanguageChangingTo===e&&(r(l),this.translator.changeLanguage(l),this.isLanguageChangingTo=void 0,this.emit("languageChanged",l),this.logger.log("languageChanged",l)):this.isLanguageChangingTo=void 0,n.resolve((...c)=>this.t(...c)),t&&t(o,(...c)=>this.t(...c))},a=o=>{!e&&!o&&this.services.languageDetector&&(o=[]);let l=Ue(o)?o:o&&o[0],c=this.store.hasLanguageSomeTranslations(l)?l:this.services.languageUtils.getBestMatchFromCodes(Ue(o)?[o]:o);c&&(this.language||r(c),this.translator.language||this.translator.changeLanguage(c),this.services.languageDetector?.cacheUserLanguage?.(c)),this.loadResources(c,h=>{s(h,c)})};return!e&&this.services.languageDetector&&!this.services.languageDetector.async?a(this.services.languageDetector.detect()):!e&&this.services.languageDetector&&this.services.languageDetector.async?this.services.languageDetector.detect.length===0?this.services.languageDetector.detect().then(a):this.services.languageDetector.detect(a):a(e),n}getFixedT(e,t,n,r){let s=r?.scopeNs,a=(o,l,...c)=>{let h;typeof l!="object"?h=this.options.overloadTranslationOptionHandler([o,l].concat(c)):h={...l},h.lng=h.lng||a.lng,h.lngs=h.lngs||a.lngs;let u=h.ns!==void 0&&h.ns!==null;h.ns=h.ns||a.ns,h.keyPrefix!==""&&(h.keyPrefix=h.keyPrefix||n||a.keyPrefix);let d={...this.options,...h};Array.isArray(s)&&!u&&(d.ns=s),typeof h.keyPrefix=="function"&&(h.keyPrefix=es(h.keyPrefix,d));let f=this.options.keySeparator||".",p;return h.keyPrefix&&Array.isArray(o)?p=o.map(y=>(typeof y=="function"&&(y=es(y,d)),`${h.keyPrefix}${f}${y}`)):(typeof o=="function"&&(o=es(o,d)),p=h.keyPrefix?`${h.keyPrefix}${f}${o}`:o),this.t(p,h)};return Ue(e)?a.lng=e:a.lngs=e,a.ns=t,a.keyPrefix=n,a}t(...e){return this.translator?.translate(...e)}exists(...e){return this.translator?.exists(...e)}setDefaultNamespace(e){this.options.defaultNS=e}hasLoadedNamespace(e,t={}){if(!this.isInitialized)return this.logger.warn("hasLoadedNamespace: i18next was not initialized",this.languages),!1;if(!this.languages||!this.languages.length)return this.logger.warn("hasLoadedNamespace: i18n.languages were undefined or empty",this.languages),!1;let n=t.lng||this.resolvedLanguage||this.languages[0],r=this.options?this.options.fallbackLng:!1,s=this.languages[this.languages.length-1];if(n.toLowerCase()==="cimode")return!0;let a=(c,h)=>{let u=this.services.backendConnector.state[`${c}|${h}`];return u===-1||u===0||u===2};if(t.precheck){let c=t.precheck(this,a);if(c!==void 0)return c}if(this.hasResourceBundle(n,e)||!this.services.backendConnector.backend||this.options.resources&&!this.options.partialBundledLanguages)return!0;let{languageUtils:o}=this.services,l=t.lng?o.isSupportedCode(n)&&o.toResolveHierarchy(n,!1)[0]:n;return!!((!l||a(l,e))&&(!r||a(s,e)))}loadNamespaces(e,t){let n=ta();return this.options.ns?(Ue(e)&&(e=[e]),e.forEach(r=>{this.options.ns.includes(r)||this.options.ns.push(r)}),this.loadResources(r=>{n.resolve(),t&&t(r)}),n):(t&&t(),Promise.resolve())}loadLanguages(e,t){let n=ta();Ue(e)&&(e=[e]);let r=this.options.preload||[],s=e.filter(a=>!r.includes(a)&&this.services.languageUtils.isSupportedCode(a));return s.length?(this.options.preload=r.concat(s),this.loadResources(a=>{n.resolve(),t&&t(a)}),n):(t&&t(),Promise.resolve())}dir(e){if(e||(e=this.resolvedLanguage||(this.languages?.length>0?this.languages[0]:this.language)),!e)return"rtl";try{let r=new Intl.Locale(e);if(r&&r.getTextInfo){let s=r.getTextInfo();if(s&&s.direction)return s.direction}}catch{}let t=["ar","shu","sqr","ssh","xaa","yhd","yud","aao","abh","abv","acm","acq","acw","acx","acy","adf","ads","aeb","aec","afb","ajp","apc","apd","arb","arq","ars","ary","arz","auz","avl","ayh","ayl","ayn","ayp","bbz","pga","he","iw","ps","pbt","pbu","pst","prp","prd","ug","ur","ydd","yds","yih","ji","yi","hbo","men","xmn","fa","jpr","peo","pes","prs","dv","sam","ckb"],n=this.services?.languageUtils||new Do(Ih());return e.toLowerCase().indexOf("-latn")>1?"ltr":t.includes(n.getLanguagePartFromCode(e))||e.toLowerCase().indexOf("-arab")>1?"rtl":"ltr"}static createInstance(e={},t){let n=new i(e,t);return n.createInstance=i.createInstance,n}cloneInstance(e={},t=Ro){let n=e.forkResourceStore;n&&delete e.forkResourceStore;let r={...this.options,...e,isClone:!0},s=new i(r);if((e.debug!==void 0||e.prefix!==void 0)&&(s.logger=s.logger.clone(e)),["store","services","language"].forEach(o=>{s[o]=this[o]}),s.services={...this.services},s.services.utils={hasLoadedNamespace:s.hasLoadedNamespace.bind(s)},n){let o=Object.keys(this.store.data).reduce((l,c)=>(l[c]={...this.store.data[c]},l[c]=Object.keys(l[c]).reduce((h,u)=>(h[u]={...l[c][u]},h),l[c]),l),{});s.store=new Io(o,r),s.services.resourceStore=s.store}if(e.interpolation){let l={...Ih().interpolation,...this.options.interpolation,...e.interpolation},c={...r,interpolation:l};s.services.interpolator=new No(c)}return s.translator=new Lo(s.services,r),s.translator.on("*",(o,...l)=>{s.emit(o,...l)}),s.init(r,t),s.translator.options=r,s.translator.backendConnector.services.utils={hasLoadedNamespace:s.hasLoadedNamespace.bind(s)},s}toJSON(){return{options:this.options,store:this.store,language:this.language,languages:this.languages,resolvedLanguage:this.resolvedLanguage}}},ti=Bh.createInstance(),hE=ti.createInstance,uE=ti.dir,dE=ti.init,fE=ti.loadResources,pE=ti.reloadResources,mE=ti.use,gE=ti.changeLanguage,yE=ti.getFixedT,_E=ti.t,xE=ti.exists,vE=ti.setDefaultNamespace,bE=ti.hasLoadedNamespace,SE=ti.loadNamespaces,ME=ti.loadLanguages;var Sp={"field.lat.label":"Latitude","field.lat.unit":"\xB0","field.lat.help":"The latitude of the centre of the search, in degrees (WGS84). Example: 49.2320.","field.lon.label":"Longitude","field.lon.unit":"\xB0","field.lon.help":"The longitude of the centre of the search, in degrees (WGS84). Example: 19.9817.","field.northing.label":"Northing (PL-1992)","field.northing.unit":"m","field.northing.help":"The centre of the search in the Polish grid PL-1992 (EPSG:2180), in metres. Geoportal shows it as X.","field.easting.label":"Easting (PL-1992)","field.easting.unit":"m","field.easting.help":"The centre of the search in the Polish grid PL-1992 (EPSG:2180), in metres. Geoportal shows it as Y.","field.radius.label":"Search radius","field.radius.unit":"m","field.radius.help":"The search looks for anchors in this circle around the centre. Both anchors of a line are in the circle. A larger circle takes longer and gives more lines.","field.area.label":"Area","field.area.unit":"","field.area.help":"Searches an area instead of a circle: along cliffs or the coast, an OpenStreetMap area or your file. Both anchors of a line are in the area. The webbing can go out of it.","field.buffer.label":"Band width","field.buffer.unit":"m","field.buffer.help":"The search area around cliffs, the coast, or the points and lines of your file. Polygons are used as they are. Example: 100 m takes the cliff edge and the ground behind it.","field.within.label":"Limit to","field.within.unit":"","field.within.help":'The part of the map for "Along cliffs". Give an OpenStreetMap name (e.g. Gozo) or use the map view. Cliffs near the coast of a named island are included.',"field.name.label":"Search name","field.name.unit":"","field.name.help":"The name in your list of searches. Empty: the place name from OpenStreetMap.","field.min_length.label":"Shortest line","field.min_length.unit":"m","field.min_length.help":"The distance between the anchors. Use the range of lines that you will rig. A narrow range gives a faster search and a clearer map.","field.max_length.label":"Longest line","field.max_length.unit":"m","field.max_length.help":"The distance between the anchors. Use the range of lines that you will rig. A narrow range gives a faster search and a clearer map.","field.max_anchor_diff_m.label":"Anchor height difference","field.max_anchor_diff_m.unit":"m","field.max_anchor_diff_m.help":"The largest height difference between the two anchors. A line with a large difference is steep and hard to walk. Typical highlines: 10 m or less.","field.max_anchor_diff.label":"Anchor height difference, % of length","field.max_anchor_diff.unit":"%","field.max_anchor_diff.help":"The same limit as a part of the line length. Both limits apply. Example: 5 % of a 200 m line is 10 m.","field.max_wall_angle.label":"Angle to the wall, at most","field.max_wall_angle.unit":"\xB0","field.max_wall_angle.help":"How far the line turns from the fall line of the wall at each anchor. 0\xB0: the line goes straight out over the drop. 90\xB0: the line goes along the wall. Use 30\u201345\xB0 for clean exits from a wall.","field.slope_threshold.label":"Anchor steepness","field.slope_threshold.unit":"\xB0","field.slope_threshold.help":"The terrain must be at least this steep for an anchor. A higher value keeps only edges of walls and gives fewer anchors. Default 45\xB0.","field.min_prominence.label":"Prominence of one anchor, at least","field.min_prominence.unit":"m","field.min_prominence.help":"Keeps lines with at least one anchor on a feature that stands out: a tower, a needle, a block. Prominence is the height of the rock above the place where it joins wider ground.","field.min_prominence_both.label":"Prominence of both anchors, at least","field.min_prominence_both.unit":"m","field.min_prominence_both.help":"The same, for both anchors. Use it for lines between two towers.","field.prominence_span.label":"Prominence: base width","field.prominence_span.unit":"m","field.prominence_span.help":"Ground wider than this is not part of the anchor's rock. Use a small value (30\u201350 m) for needles, a large value for big walls.","field.min_drop.label":"Drop below both anchors, at least","field.min_drop.unit":"m","field.min_drop.help":"Both anchors must be this high above the lowest ground near them. It removes anchors on small steps in a slope.","field.drop_radius.label":"Drop: measured within","field.drop_radius.unit":"m","field.drop_radius.help":"The distance around each anchor where the search finds the lowest ground for the drop.","field.nmpt.label":"Trees and buildings","field.nmpt.unit":"","field.nmpt.help":'Checks the clearance above trees and buildings too. "Mark" shows such lines in orange. "Remove" deletes them from the result. "Do not check" is faster.',"field.high_above.label":"Counts as high from","field.high_above.unit":"m","field.high_above.help":'From this height above the ground, a part of the line is "high". The result shows the high part of each line in %.',"field.min_height.label":"Highest point above the ground, at least","field.min_height.unit":"m","field.min_height.help":"Keeps lines that get this high above the ground at one point or more. The height is measured below the sagged webbing with the walker on it.","field.min_mean_height.label":"Mean height above the ground, at least","field.min_mean_height.unit":"m","field.min_mean_height.help":"Keeps lines that are this high on average along their length.","field.min_high_share.label":"High part of the line, at least","field.min_high_share.unit":"%","field.min_high_share.help":'Keeps lines that are higher than "Counts as high from" along this part of their length. Example: 70 % for lines with exposure from end to end.',"field.model.label":"Clearance model","field.model.unit":"","field.model.help":'How the search calculates the lowest point of the webbing. "Simple formula" is fast and safe for most lines. "Sag estimate" calculates the sag from the rigging values below and adds the leash fall space.',"field.pretension.label":"Pretension","field.pretension.unit":"kN","field.pretension.help":"The tension in the main line before anybody walks it.","field.stretch.label":"Webbing stretch at 10 kN","field.stretch.unit":"%","field.stretch.help":"How much the webbing gets longer at 10 kN, from its data sheet. Polyester \u2248 1\u20133 %, nylon \u2248 5\u201310 %.","field.webbing_weight.label":"Webbing weight","field.webbing_weight.unit":"g/m","field.webbing_weight.help":"Weight of the main and backup together, per metre.","field.athlete_mass.label":"Walker mass","field.athlete_mass.unit":"kg","field.athlete_mass.help":"The mass of the walker, with harness and leash.","field.fall_zone.label":"Leash fall space","field.fall_zone.unit":"m","field.fall_zone.help":"The free height that must stay below the sagged webbing for a leash fall.","field.source.label":"Elevation data","field.source.unit":"","field.source.help":'The terrain model for the search. "Automatic" uses the national LiDAR data where we have it, else a Europe-wide model.',"field.resolution.label":"Grid size","field.resolution.unit":"m","field.resolution.help":"The size of one terrain cell. Small cells find small features but the search takes longer. Default: the resolution of the data.","field.water.label":"Water surfaces","field.water.unit":"","field.water.help":"Gives the sea and lakes a height where the data has none. Then lines over water and edges of sea cliffs are found.","field.coastline.label":"Sea outline","field.coastline.unit":"","field.coastline.help":"Where the sea is. OpenStreetMap is the most accurate. The world file is one large download. The Copernicus mask is less accurate (30 m).","field.shore_buffer.label":"Shore band","field.shore_buffer.unit":"m","field.shore_buffer.help":"Cells without data this near the sea are taken as water.","field.fill_gaps.label":"Fill data gaps","field.fill_gaps.unit":"","field.fill_gaps.help":"Fills holes in the terrain data on land from another data set. No anchors are put on the edges of a filled hole.","field.update.label":"Check for newer data","field.update.unit":"","field.update.help":'Before the search, checks if the stored terrain data has a newer version. "Old only" checks data past its check interval. "All" checks everything.',"field.group_distance.label":"Group lines with anchors within","field.group_distance.unit":"m","field.group_distance.help":"Lines whose both anchors are this near become one spot. The map shows one line per spot. You can change it later in the result.","field.group_by.label":"Line shown per spot","field.group_by.unit":"","field.group_by.help":"The line that represents a spot on the map.","field.no_html.label":"Skip the interactive map","field.no_html.unit":"","field.no_html.help":"Saves the result without the interactive map: only the list of lines as CSV and GeoJSON files.","field.ortho.label":"Orthophoto for offline use","field.ortho.unit":"","field.ortho.help":'Stores aerial photo tiles with the result, so the map works without internet. "Automatic" stores them when the download is short, else the map loads them online.',"field.ortho_detail.label":"Detailed photo around the best spots","field.ortho_detail.unit":"","field.ortho_detail.help":"The number of best spots that get detailed aerial photo tiles. The map loads the detailed photo of the other spots online.","field.threads.label":"Threads","field.threads.unit":"","field.threads.help":"The number of processor threads for the line search. Default: all but one.","field.tile_size.label":"Tile size","field.tile_size.unit":"m","field.tile_size.help":"Large areas are calculated in square tiles. Default: from free memory.","choice.source.auto":"Automatic","choice.water.fill":"Fill","choice.water.off":"Leave empty","choice.coastline.overpass":"OpenStreetMap","choice.coastline.world":"OpenStreetMap world file","choice.coastline.copernicus":"Copernicus water mask","choice.fill_gaps.on":"Fill","choice.fill_gaps.off":"Leave empty","choice.nmpt.mark":"Mark in orange","choice.nmpt.reject":"Remove these lines","choice.nmpt.off":"Do not check","choice.model.formula":"Simple formula","choice.model.sag":"Sag estimate","choice.update.stale":"Old only","choice.update.all":"All","choice.group_by.clearance":"Most clearance","choice.group_by.longest":"Longest","choice.group_by.height":"Highest","choice.ortho.auto":"Automatic","choice.ortho.always":"Always","choice.ortho.never":"Never","topic.where":"Where","topic.height":"Height above the terrain","topic.anchors":"Anchors","topic.lines":"Lines","topic.data":"Elevation data","topic.rigging":"Clearance model","topic.output":"Results and map","topic.computing":"Computing","preset.typical":"Typical highline","preset.long":"Long lines","preset.short":"Short & low","preset.custom":"Custom","hint.presets.label":"Lines to look for","hint.presets.help":"A start set for the line length and the anchor height difference. Change the values after you select one.","hint.length.label":"Line length","hint.length.help":"The distance between the anchors. Use the range of lines that you will rig. A narrow range gives a faster search and a clearer map.","hint.area_name.label":"Name of the area","hint.area_name.help":"An area from OpenStreetMap: a park, an island, a mountain range. Both anchors of a line are in the area. The webbing can go out of it.","hint.area_file.label":"Area file","hint.area_file.help":"A GeoJSON, KML or GPX file. Polygons are used as they are. Points and lines get the band width around them.","hint.about":"About {{label}}","hint.bounds.min":"On this site: at least {{min}}.","hint.bounds.max":"On this site: at most {{max}}.","hint.bounds.both":"On this site: from {{min}} to {{max}}.","hint.bounds.factor":"On this site: at least {{factor}} \xD7 the grid size.","error.no_centre":"Select the centre of the search: click the map.","error.area_and_centre":"Use a point or an area, not both.","error.area_and_geometry":"Use one area: a drawn or uploaded shape, or Along cliffs, the coast or an OpenStreetMap name, not both.","error.lat_lon_both":"Give both the latitude and the longitude of the centre.","error.lat_lon_range":"The centre is not on the map: latitude \u221290 to 90\xB0, longitude \u2212180 to 180\xB0.","error.northing_easting_both":"Give both the northing and the easting of the centre.","error.unknown_source":"Unknown elevation data: {{source}}. Select one from the list.","error.resolution_min":"Grid size must be at least {{min}} m.","error.length_range":"Shortest line must be more than 0 and less than Longest line.","error.positive":"{{label}} must be more than 0.","error.not_negative":"{{label}} cannot be less than 0.","error.high_share_range":"High part of the line is a percentage: 0 to 100.","error.wall_angle_range":"Angle to the wall is 0 to 180\xB0.","error.slope_range":"Anchor steepness is more than 0\xB0 and at most 90\xB0.","error.tile_size_min":"Tile size must be at least {{min}} m.","error.control_characters":"{{label}}: remove the control characters (tabs, line breaks).","error.area_text_long":"The area name: at most {{n}} characters, no control characters.","error.name_long":"Search name: at most {{n}} characters, no control characters.","error.within_needs_area":"Limit to works only with an area search. Select Along cliffs or the coast, or clear Limit to.","error.not_a_number":"{{label}}: enter a number.","error.not_whole_number":"{{label}}: enter a whole number.","error.not_yes_no":"{{label}}: select yes or no.","error.not_a_choice":"{{label}}: select one of the choices.","error.not_a_text":"{{label}}: enter a text.","error.missing_value":"{{label}}: enter a value.","error.invalid_value":"{{label}}: this value is not possible.","error.invalid_request":"The request is not complete or not valid. Reload the page and try again.","error.unknown_fields":"The request has settings this site does not know ({{names}}). Reload the page and try again.","error.at_least":"{{label}}: at least {{min}} on this site.","error.at_most":"{{label}}: at most {{max}} on this site.","error.not_allowed":"{{label}} cannot be changed on this site.","error.not_allowed_value":'{{label}}: "{{value}}" cannot be used on this site.',"error.bad_area":"The area must be Along cliffs, the coast, an OpenStreetMap name, or a drawn or uploaded shape.","error.box_text":"Limit to: give an OpenStreetMap name or use the map view.","error.box_range":"Limit to: the map view is not a valid box. Move the map and try again.","error.osm_not_found":"OpenStreetMap has no area with the name {{name}}. Check the name or use another one.","error.region_too_large":"{{name}} is too large: its box is {{km2}} km\xB2, the limit on this site is {{max}} km\xB2. Use a smaller area.","error.area_nothing":"The area is empty: nothing was found to make it from.","error.area_empty":"The area is empty. Check Limit to and Band width, or draw the area again.","error.area_no_shapes":"The area has no shapes. Draw it again or use another file.","error.within_missing":"Along cliffs and the coast need a limit: an OpenStreetMap name or the map view.","error.no_coast_near":"OpenStreetMap has no coast within {{reach}} m of the area. Check Limit to.","error.no_cliffs_near":"OpenStreetMap has no cliffs or crags within {{reach}} m of the area. Check Limit to.","error.area_failed":"The area could not be made: {{reason}}","error.geometry_too_large":"The drawn or uploaded area is too large or too complex. Use a simpler shape.","error.geometry_vertices":"The area has {{n}} points, the limit is {{max}}. Use a simpler shape.","error.geometry_not_geojson":"The drawn or uploaded area is not valid GeoJSON. Draw it again or use another file.","error.geometry_empty":"The drawn or uploaded area is empty. Draw it again or use another file.","error.geometry_coordinates":"The area is not on the map: latitude \u221290 to 90\xB0, longitude \u2212180 to 180\xB0.","error.geometry_invalid":"The area is not a valid shape ({{reason}}). Draw it again without crossing lines.","error.coast_pieces_left_out_one":"1 part of the coast is {{near}}\u2013{{far}} m away from the area and is not searched (for example at {{lat}}, {{lon}}). A larger Longest line or the map view as Limit to includes it.","error.coast_pieces_left_out_other":"{{count}} parts of the coast are {{near}}\u2013{{far}} m away from the area and are not searched (for example at {{lat}}, {{lon}}). A larger Longest line or the map view as Limit to includes them.","error.cliff_pieces_left_out_one":"1 part of the cliffs and crags is {{near}}\u2013{{far}} m away from the area and is not searched (for example at {{lat}}, {{lon}}). A larger Longest line or the map view as Limit to includes it.","error.cliff_pieces_left_out_other":"{{count}} parts of the cliffs and crags are {{near}}\u2013{{far}} m away from the area and are not searched (for example at {{lat}}, {{lon}}). A larger Longest line or the map view as Limit to includes them.","error.overpass_day_max":"The {{max}} OpenStreetMap queries (Overpass) this site may send per day are used up. Coast and cliff areas work again tomorrow (UTC); until then searches near the sea use the Copernicus sea outline.","error.coast_fallback":"OpenStreetMap did not answer. The search uses the Copernicus sea outline: it can be up to 70 m wrong near the shore. Lines near the shore can be missing.","error.no_surface":"There is no data of trees and buildings for {{percent}} % of the area. Lines there are checked against the ground only.","error.area_too_large":"The area is {{km2}} km\xB2. The limit on this site is {{max}} km\xB2. Draw a smaller area or use a smaller Band width.","error.circle_too_large":"The circle is {{km2}} km\xB2. The limit on this site is {{max}} km\xB2. Use a smaller Search radius.","error.box_too_large":"The search reaches {{width}} \xD7 {{height}} km. The limit on this site is {{max}} km on each side. Use a smaller area, or search areas far apart one by one.","error.no_source":"No elevation data can be used here: {{reason}}","error.resolution_finer_than_data":"Grid size cannot be smaller than the cells of {{source}} ({{native}} m).","error.circle_grid_too_large":"The terrain grid is too large ({{mpx}} million cells, limit {{max}}). Use a smaller Search radius or a larger Grid size.","error.grid_too_large":"The terrain grid is too large ({{mpx}} million cells, limit {{max}}). Use a smaller area, a larger Grid size, or a shorter Longest line.","error.too_many_tiles":"The area needs {{n}} tiles, limit {{max}}. Use a smaller area or a larger Grid size.","error.download_too_large":"The search needs about {{mb}} MB of data, limit {{max}} MB. Use a smaller area, a larger Grid size, or set Trees and buildings to Do not check.","error.download_failed":"The data could not be downloaded: {{reason}}. Try again later.","error.opentopo_key":"These elevation data need an OpenTopography key, and the server has none. Select other elevation data.","error.too_many_anchors":"{{n}} anchors found, limit {{max}}. Increase Anchor steepness, use a larger Grid size, or a smaller area.","error.no_steep_terrain":"No terrain here is steep enough for anchors. Decrease Anchor steepness or search a larger area.","error.no_prominent_anchors":"No anchor stands out enough. Decrease Prominence of one anchor, Prominence of both anchors or Drop below both anchors.","error.no_lines":"No line passes the settings. Use a wider Line length, a larger Anchor height difference, or lower limits of height, prominence and drop.","error.too_many_lines_memory":"{{n}} lines found, at most {{max}} fit into the memory of this site. Narrow the search: increase Prominence of one anchor, Highest point above the ground or Drop below both anchors, or use a smaller area.","error.too_many_lines":"{{n}} lines found, limit {{max}}. Narrow the search: increase Prominence of one anchor, Highest point above the ground or Drop below both anchors, or use a smaller area.","error.too_many_lines_memory_early":"More than {{max}} lines found, more than fit into the memory of this site: the search stopped there. Narrow the search: increase Prominence of one anchor, Highest point above the ground or Drop below both anchors, or use a smaller area.","error.too_many_lines_early":"More than {{max}} lines found, the limit of this site: the search stopped there. Narrow the search: increase Prominence of one anchor, Highest point above the ground or Drop below both anchors, or use a smaller area.","error.no_profiles":"This result has no profiles.","error.profile_admin_only":"Profiles of results from {{source}} are for administrators only.","error.profile_outside":"Both points must be in the area of this result.","error.profile_too_long":"The points are {{m}} m apart. The limit is {{max}} m, the Longest line of this search.","error.profile_too_far":"The points are {{km}} km apart. At the grid size of this result, a profile can be at most {{max}} km long.","error.profile_too_close":"The points are too close. Select two points farther apart.","error.profile_crs":"A profile here needs other map coordinates than this result. Measure inside the area of the result.","error.patch_line":"The address names no line of this result. Open the 3D view from a selected line.","error.patch_admin_only":"The 3D view of results from {{source}} is for administrators only.","error.patch_outside":"The line must be in the area of this result.","error.patch_too_large":"The 3D view of this line needs {{km}} km of terrain on a side. At the grid size of this result it can show at most {{max}} km.","error.patch_crs":"The 3D view here needs other map coordinates than this result.","error.patch_no_data":"There is no elevation data around this line.","error.patch_relief":"The terrain around this line rises more than 3276 m: the 3D view cannot show it.","error.patch_damaged":"The terrain of the 3D view arrived damaged. Reload the page.","error.no_worker":"The search service does not run now. Your searches wait in the queue until it starts.","error.no_worker_local":"The search service does not run now. Your searches wait in the queue until it starts. Start it with: findaline.py worker","error.busy":"The search service is busy: no answer in {{seconds}} s. Try again later.","error.place_name":"Type a place name of 1 to {{n}} characters.","error.rate_estimate":"Too many estimates in a short time. Wait a minute and try again.","error.rate_profile":"Too many profiles in a short time. Wait a minute and try again.","error.rate_place":"Too many place searches in a short time. Wait a minute and try again.","error.rate_time_zone":"Too many time zone updates in a short time. Wait a minute and try again.","error.rate_report":"Too many problem reports in a short time. Wait a minute and try again.","error.rate_job":"Too many searches started in a short time. Wait a minute and try again.","error.rate_patch":"Too many 3D views in a short time. Wait a minute and try again.","error.disk_full":"The server is short of disk space. New searches cannot start now. Try again later.","error.disk_full_search":"The server is short of disk space, so the search stopped. Try again later.","error.queue_full":"The queue is full ({{n}} searches). Try again later.","error.quota_active":"Searches waiting or running at the same time: at most {{max}}. Wait until one ends.","error.quota_jobs_day":"Searches in 24 hours: at most {{max}}. Try again later.","error.quota_runs_gb":"Your results use {{gb}} GB of {{max}} GB. Delete old searches.","error.quota_km2":"You used {{used}} of {{max}} km\xB2 in the last 24 hours. Try again later.","error.quota_mpx":"You searched {{used}} of {{max}} km\xB2 at 1 m resolution in the last 24 hours (a coarser resolution counts less). Try again later.","error.quota_use_mpx":"This search needs {{more}} km\xB2 at 1 m resolution more: you used {{used}} of {{max}} in the last 24 hours. Try again later, or use a smaller area or a coarser resolution.","error.quota_use_km2":"This search needs {{more}} km\xB2 more: you used {{used}} of {{max}} km\xB2 in the last 24 hours. Try again later or use a smaller area.","error.quota_use_nominatim":"You used {{used}} of {{max}} place-name searches in OpenStreetMap in the last 24 hours. Try again later.","error.quota_use_download_mb":"This search needs about {{more}} MB of data: you used {{used}} of {{max}} MB in the last 24 hours. Try again later or use a smaller area.","error.quick_waiting":"Your last estimate, profile or place search is not finished. Try again when it is done.","error.favourites_max":"Favourite lines: at most {{max}}. Remove some first.","error.need_drawing":"Draw a polygon or a rectangle with the tools on the left of the map.","error.need_file":"Select a GeoJSON, KML or GPX file.","error.need_osm_name":"Type the name of an OpenStreetMap area.","error.check_settings":"Check the settings.","error.folders_max":"Folders: at most {{max}}. Delete some first.","intro.dont_show":"Do not show again","intro.got_it":"Got it","intro.search.title":"How a search works","intro.search.link":"How searching works","intro.search.what":"<b>What it does.</b> The search puts anchors on steep terrain. Then it checks every pair of anchors: the webbing with a walker on it must stay clear of the ground between them. You get the lines that pass.","intro.search.limits":"Your limits","intro.search.limits_local":"This computer has no limits.","intro.search.limits_none":"Your account has no limits.","intro.search.limits_loading":"Loading your limits\u2026","intro.search.limit_one":"One search: {{parts}}.","intro.search.limit_area":"an area up to {{area}} km\xB2","intro.search.limit_circle":"(a circle up to {{radius}} km)","intro.search.limit_radius":"a circle up to {{radius}} km","intro.search.limit_length":"lines up to {{length}} m","intro.search.limit_bbox":"The whole search fits in a box of {{bbox}} km on each side.","intro.search.limit_day":"Every {{hours}} hours: {{parts}}.","intro.search.limit_jobs_one":"{{count}} search","intro.search.limit_jobs_other":"{{count}} searches","intro.search.limit_km2":"{{km2}} km\xB2 of area","intro.search.limit_mpx":"{{km2}} km\xB2 of area at 1 m resolution (25 times as much at 5 m)","intro.search.limit_mb":"{{mb}} MB of data downloads","intro.search.limit_active_one":"{{count}} search can wait or run at a time.","intro.search.limit_active_other":"{{count}} searches can wait or run at the same time.","intro.search.limit_gb":"Your results can use {{gb}} GB.","intro.search.limit_meters":"The meters next to your searches show what you used today.","intro.search.narrow":"<b>Narrow settings make the search fast.</b> Most settings remove anchors or lines during the search: steepness, prominence, drop, height above the ground, angle to the wall. Fewer anchors means fewer pairs to check. The search ends sooner and the result is easier to read.","intro.search.wide":"<b>Wide settings on a large area give too much.</b> A range of 30\u20132000 m in a large area gives thousands of lines. The search takes long, it can stop at the limit of lines, and the map is full of lines. Start narrow. Make the settings wider only when you get too few lines.","intro.search.examples":"Examples","intro.search.mode_cliffs":"Along cliffs","intro.search.coast":"Coast","intro.search.example_long":"<b>A long line?</b> Do not set 30\u20132000 m. Set <b>{{length}}</b> 1000\u20132000 m and <b>{{diff}}</b> 100 m: long lines seldom have anchors at the same height.","intro.search.example_needle":"<b>A highline on a rock needle or tower?</b> Set <b>{{length}}</b> 15\u201360 m, <b>{{prom}}</b> 15 m and <b>{{span}}</b> 40 m. Only anchors on rock that stands out stay.","intro.search.example_exposure":"<b>Big exposure over a valley?</b> Set <b>{{height}}</b> 80 m and <b>{{share}}</b> 70 % (<b>{{highAbove}}</b> 20 m). Lines that are high only in the middle are removed.","intro.search.example_sea":"<b>Lines straight out from a sea cliff?</b> Use <b>{{cliffs}}</b> \u2192 <b>{{coast}}</b>, set <b>{{angle}}</b> 30\xB0 and <b>{{drop}}</b> 30 m. The lines leave the wall over the drop, not along it.","intro.search.example_forest":"<b>A first highline in a forest area?</b> Use the preset <b>{{preset}}</b> and set <b>{{nmpt}}</b> to <b>{{reject}}</b>. Only lines clear of the trees stay.","intro.result.title":"How to read the result","intro.result.link":"How to read the result","intro.result.spots":"<b>Spots and lines.</b> Many found lines are almost the same: their anchors are only a few metres apart. The result puts them together into a <i>spot</i>. The map shows one line for each spot: the line with the most clearance (or the longest or highest, as you select). Select a spot to see all its lines.","intro.result.colours":"<b>Colours.</b>","intro.result.colour_clean":"Pink: the line is clear of the ground.","intro.result.colour_over":"Orange: it is clear of the ground but not of trees or buildings.","intro.result.colour_favourite":"Yellow halo: your favourite.","intro.result.filters":"<b>Filters hide lines.</b> Filters do not start a new search. They hide the lines that you do not need, and you can change them at any time. The head of the result shows how many lines the filters hide. Your filters stay in this browser for every result.","intro.result.easy":"<b>Make the map easy to read.</b>","intro.result.easy_group":"Keep <b>Group similar lines into spots</b> on.","intro.result.easy_within":"Increase <b>Anchors within</b> (More filters \u2192 Grouping) to put near spots together.","intro.result.easy_clearance":"Set <b>Clearance at least</b> 1\u20132 m: lines that only just pass go away.","intro.result.easy_length":"Set <b>Length</b> to the lines that you will rig.","intro.result.easy_spot":"Set <b>Lines in a spot at least</b> 3 to see places with many options.","intro.result.easy_off":"Turn grouping off only when you look at a small part of the map.","intro.result.check":"<b>Check on the spot.</b> The result comes from terrain data. It does not see loose rock, small trees or new buildings, and it does not check a fall onto the backup. Check every line before you rig it.","ui.try":"Try interface {{ui}}","ui.credits.toggle":"Data credits","ui.searched.title":"Area searched","ui.searched.today":"{{area}} km\xB2 today","ui.searched.total_one":"{{area}} km\xB2 in {{searches}} search","ui.searched.total_other":"{{area}} km\xB2 in {{searches}} searches","ui.searched.country":"Country: {{country}}, from your browser's time zone","ui.searched.empty":"No finished searches yet. The area of every search you finish is added up here, day by day.","ui.searched.stat_total":"in total","ui.searched.stat_searches_one":"search","ui.searched.stat_searches_other":"searches","ui.searched.stat_today":"today","ui.searched.month":"{{area}} km\xB2 in the last 30 days","ui.searched.day_zero":"{{day}}: no searches","ui.searched.day_one":"{{day}}: {{area}} km\xB2 in {{searches}} search","ui.searched.day_other":"{{day}}: {{area}} km\xB2 in {{searches}} searches","ui.searched.chart":"Area searched per day, the last 30 days","ui.searched.today_axis":"Today","ui.view3d.open":"3D view","ui.view3d.title":"3D view of a line","ui.view3d.back":"Back to the map","ui.view3d.loading_terrain":"Loading the terrain\u2026","ui.view3d.loading_imagery":"Loading the imagery\u2026","ui.view3d.loading_profile":"Checking the clearance\u2026","ui.view3d.error_title":"The 3D view could not open","ui.view3d.no_webgl":"This browser cannot draw the 3D view (it needs WebGL 2).","ui.view3d.context_lost":"The 3D view stopped: the browser freed its graphics memory.","ui.view3d.reload":"Reload","ui.view3d.imagery":"Imagery","ui.view3d.imagery_ortho":"Orthophoto","ui.view3d.imagery_esri":"Satellite (Esri)","ui.view3d.imagery_shaded":"Shaded","ui.view3d.no_imagery":"No imagery for this result: the terrain is shaded.","ui.view3d.walker":"Walker","ui.view3d.walker_position":"Walker's position along the line","ui.view3d.walk":"Walk","ui.view3d.stop":"Stop","ui.view3d.speed":"Speed","ui.view3d.speed_value":"\xD7{{times}}","ui.view3d.reduced_motion":"The walk is off: your system asks for reduced motion.","ui.view3d.length":"{{m}} m long","ui.view3d.sag":"{{m}} m of sag with the walker","ui.view3d.clearance":"{{m}} m clear of the terrain","ui.view3d.over_trees":"Passes over trees or buildings","ui.view3d.edit_hint":"Drag an anchor to move it. Length and sag follow; the clearance is checked when you let go.","ui.view3d.edited":"Anchors moved: not saved","ui.view3d.reset":"Back to the found line","ui.view3d.phone_level":"Simplified view on phones: anchors cannot be dragged.","ui.view3d.level_full":"Full view","ui.view3d.credits":"Data","ui.view3d.preview_note":"A visual preview: heights and clearance come from the site's elevation data, the imagery may be off by metres. Check every line on the spot."};function kh(i,e="error"){return typeof i=="string"?i:i&&typeof i=="object"&&typeof i.message=="string"?i.message:e}function v_(i,e="en"){let t=ti.createInstance();return t.init({lng:e,fallbackLng:"en",resources:{[e]:{translation:i}},initAsync:!1,keySeparator:!1,nsSeparator:!1,interpolation:{escapeValue:!1},returnNull:!1}),(n,r)=>t.t(n,r)}var tt=v_(Sp),b_=i=>tt(`field.${i}.label`);function S_(i,e){let t=`error.${i.code}`,n={...i.params||{}};typeof n.field=="string"&&n.label===void 0&&(n.label=b_(n.field));let r=tt(t,n);return r===t&&e?e:r}function zh(i,e="error"){let t=i;return t&&typeof t=="object"&&typeof t.code=="string"?S_({code:t.code,params:t.params},kh(i,e)):kh(i,e)}function Uo(){let i=typeof window<"u"?window.FINDALINE_APP:void 0;return i?.esri_key?i.esri_key:(typeof document<"u"?document.querySelector('meta[name="findaline-esri-key"]'):null)?.content||null}var M_="Source: Esri, Vantor, Earthstar Geographics, and the GIS User Community";var Oo=19;function Fo(i){return"https://ibasemaps-api.arcgis.com/arcgis/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}?token="+encodeURIComponent(i)}function Mp(){return Vh("Powered by Esri","https://www.esri.com")+" | "+Gn(M_)}function Gn(i){return i.replace(/[&<>"']/g,e=>"&#"+e.charCodeAt(0)+";")}function Vh(i,e){return e&&/^https?:\/\//.test(e)?'<a href="'+Gn(e)+'" target="_blank" rel="noopener">'+Gn(i)+"</a>":Gn(i)}function wp(i){return Vh(i.attribution,i.attribution_url)}var w_="Find-a-Line's lines, heights, profiles and maps are computed from these data, which were resampled and combined onto a working grid (changed).";function Tp(i,e,t){let n=i.map(s=>Gn(s.attribution)+" ("+Vh(s.licence,s.url)+")"),r="Data: "+Array.from(new Set(n)).join(" | ")+". "+Gn(w_)+' <a href="'+Gn(e)+'" target="_blank">Notices</a>';return t?'<button type="button" class="u-credits-toggle" aria-expanded="'+t.open+'">'+Gn(t.label)+'</button><span class="u-credits'+(t.open?" u-open":"")+'">'+r+"</span>":r}function Ap(i){if(i.byteLength<4)throw new Error("The answer is too short.");let e=new DataView(i).getUint32(0,!0);if(4+e>i.byteLength)throw new Error("The answer's meta is cut short.");return{meta:JSON.parse(new TextDecoder().decode(new Uint8Array(i,4,e))),body:new Uint8Array(i,4+e)}}async function Cp(i){let e=new Blob([i]).stream().pipeThrough(new DecompressionStream("deflate"));return new Uint8Array(await new Response(e).arrayBuffer())}function Rp(i,e,t){if(i.byteLength!==e*t*2)throw new Error(`Expected ${e*t*2} bytes of heights, got ${i.byteLength}.`);let n=new DataView(i.buffer,i.byteOffset,i.byteLength),r=new Int16Array(e*t);for(let s=0,a=0;s<t;s++){let o=0;for(let l=0;l<e;l++,a++)o=o+n.getInt16(2*a,!0)<<16>>16,r[a]=o}return r}function Ep(i){return 512*Math.max(1,Math.ceil((i-1)/512))+1}function Pp(i,e,t,n){let r=Ep(e),s=Ep(t),a=new Float32Array(r*s).fill(NaN);for(let o=0;o<t;o++)for(let l=0;l<e;l++){let c=i[o*e+l];c!==-32768&&(a[o*r+l]=(c+n)/10)}return{heights:a,cols:r,rows:s}}var nr={LEFT:0,MIDDLE:1,RIGHT:2,ROTATE:0,DOLLY:1,PAN:2},rr={ROTATE:0,PAN:1,DOLLY_PAN:2,DOLLY_ROTATE:3},gm=0,wu=1,ym=2;var ka=1,_m=2,Is=3,sn=0,ui=1,ri=2,an=0,Ls=1,Tu=2,Eu=3,Au=4,Cu=5;var Br=100,xm=101,vm=102,bm=103,Sm=104,Ru=200,Pu=201,Mm=202,wm=203,Iu=204,Lu=205,Tm=206,Em=207,Am=208,Cm=209,Rm=210,Pm=211,Im=212,Lm=213,Dm=214,fl=0,pl=1,ml=2,xs=3,gl=4,yl=5,pa=6,_l=7,Bl=0,Nm=1,Um=2,Xi=0,Du=1,Nu=2,Uu=3,Ou=4,Fu=5,Bu=6,ku=7,fu="attached",Om="detached",zu=300,sr=301,kr=302,kl=303,zl=304,za=306,$n=1e3,Li=1001,vs=1002,At=1003,Vl=1004;var zr=1005;var St=1006,Ds=1007;var Ci=1008;var di=1009,Vu=1010,Gu=1011,Ns=1012,Gl=1013,qi=1014,fi=1015,ji=1016,Hl=1017,Wl=1018,Us=1020,Hu=35902,Wu=35899,Xu=1021,qu=1022,Ri=1023,tn=1026,ar=1027,Os=1028,Xl=1029,Ln=1030,ql=1031;var Va=1033,Ga=33776,Ha=33777,Wa=33778,Xa=33779,jl=35840,Yl=35841,$l=35842,Zl=35843,Kl=36196,Jl=37492,Ql=37496,ec=37488,tc=37489,qa=37490,ic=37491,nc=37808,rc=37809,sc=37810,ac=37811,oc=37812,lc=37813,cc=37814,hc=37815,uc=37816,dc=37817,fc=37818,pc=37819,mc=37820,gc=37821,yc=36492,_c=36494,xc=36495,vc=36283,bc=36284,ja=36285,Sc=36286;var wr=2300,Tr=2301,hl=2302,pu=2303,mu=2400,gu=2401,yu=2402,Fm=2500;var ju=0,Ya=1,Fs=2,Bm=3200;var $a=0,km=1,Dn="",bt="srgb",li="srgb-linear",ma="linear",rt="srgb";var ul=7680;var zm=519,Vm=512,Gm=513,Hm=514,Mc=515,Wm=516,Xm=517,wc=518,qm=519,Yu=35044;var $u="300 es",Gi=2e3,bs=2001;function T_(i){for(let e=i.length-1;e>=0;--e)if(i[e]>=65535)return!0;return!1}function E_(i){return ArrayBuffer.isView(i)&&!(i instanceof DataView)}function Ss(i){return document.createElementNS("http://www.w3.org/1999/xhtml",i)}function jm(){let i=Ss("canvas");return i.style.display="block",i}var Ip={},Ms=null;function ga(...i){let e="THREE."+i.shift();Ms?Ms("log",e,...i):console.log(e,...i)}function Ym(i){let e=i[0];if(typeof e=="string"&&e.startsWith("TSL:")){let t=i[1];t&&t.isStackTrace?i[0]+=" "+t.getLocation():i[1]='Stack trace not available. Enable "THREE.Node.captureStackTrace" to capture stack traces.'}return i}function Ce(...i){i=Ym(i);let e="THREE."+i.shift();if(Ms)Ms("warn",e,...i);else{let t=i[0];t&&t.isStackTrace?console.warn(t.getError(e)):console.warn(e,...i)}}function Fe(...i){i=Ym(i);let e="THREE."+i.shift();if(Ms)Ms("error",e,...i);else{let t=i[0];t&&t.isStackTrace?console.error(t.getError(e)):console.error(e,...i)}}function Mr(...i){let e=i.join(" ");e in Ip||(Ip[e]=!0,Ce(...i))}function $m(i,e,t){return new Promise(function(n,r){function s(){switch(i.clientWaitSync(e,i.SYNC_FLUSH_COMMANDS_BIT,0)){case i.WAIT_FAILED:r();break;case i.TIMEOUT_EXPIRED:setTimeout(s,t);break;default:n()}}setTimeout(s,t)})}var Zm={[fl]:pl,[ml]:pa,[gl]:_l,[xs]:yl,[pl]:fl,[pa]:ml,[_l]:gl,[yl]:xs},jt=class{addEventListener(e,t){this._listeners===void 0&&(this._listeners={});let n=this._listeners;n[e]===void 0&&(n[e]=[]),n[e].indexOf(t)===-1&&n[e].push(t)}hasEventListener(e,t){let n=this._listeners;return n===void 0?!1:n[e]!==void 0&&n[e].indexOf(t)!==-1}removeEventListener(e,t){let n=this._listeners;if(n===void 0)return;let r=n[e];if(r!==void 0){let s=r.indexOf(t);s!==-1&&r.splice(s,1)}}dispatchEvent(e){let t=this._listeners;if(t===void 0)return;let n=t[e.type];if(n!==void 0){e.target=this;let r=n.slice(0);for(let s=0,a=r.length;s<a;s++)r[s].call(this,e);e.target=null}}},ii=["00","01","02","03","04","05","06","07","08","09","0a","0b","0c","0d","0e","0f","10","11","12","13","14","15","16","17","18","19","1a","1b","1c","1d","1e","1f","20","21","22","23","24","25","26","27","28","29","2a","2b","2c","2d","2e","2f","30","31","32","33","34","35","36","37","38","39","3a","3b","3c","3d","3e","3f","40","41","42","43","44","45","46","47","48","49","4a","4b","4c","4d","4e","4f","50","51","52","53","54","55","56","57","58","59","5a","5b","5c","5d","5e","5f","60","61","62","63","64","65","66","67","68","69","6a","6b","6c","6d","6e","6f","70","71","72","73","74","75","76","77","78","79","7a","7b","7c","7d","7e","7f","80","81","82","83","84","85","86","87","88","89","8a","8b","8c","8d","8e","8f","90","91","92","93","94","95","96","97","98","99","9a","9b","9c","9d","9e","9f","a0","a1","a2","a3","a4","a5","a6","a7","a8","a9","aa","ab","ac","ad","ae","af","b0","b1","b2","b3","b4","b5","b6","b7","b8","b9","ba","bb","bc","bd","be","bf","c0","c1","c2","c3","c4","c5","c6","c7","c8","c9","ca","cb","cc","cd","ce","cf","d0","d1","d2","d3","d4","d5","d6","d7","d8","d9","da","db","dc","dd","de","df","e0","e1","e2","e3","e4","e5","e6","e7","e8","e9","ea","eb","ec","ed","ee","ef","f0","f1","f2","f3","f4","f5","f6","f7","f8","f9","fa","fb","fc","fd","fe","ff"],Lp=1234567,da=Math.PI/180,Er=180/Math.PI;function Hi(){let i=Math.random()*4294967295|0,e=Math.random()*4294967295|0,t=Math.random()*4294967295|0,n=Math.random()*4294967295|0;return(ii[i&255]+ii[i>>8&255]+ii[i>>16&255]+ii[i>>24&255]+"-"+ii[e&255]+ii[e>>8&255]+"-"+ii[e>>16&15|64]+ii[e>>24&255]+"-"+ii[t&63|128]+ii[t>>8&255]+"-"+ii[t>>16&255]+ii[t>>24&255]+ii[n&255]+ii[n>>8&255]+ii[n>>16&255]+ii[n>>24&255]).toLowerCase()}function ze(i,e,t){return Math.max(e,Math.min(t,i))}function Zu(i,e){return(i%e+e)%e}function A_(i,e,t,n,r){return n+(i-e)*(r-n)/(t-e)}function C_(i,e,t){return i!==e?(t-i)/(e-i):0}function fa(i,e,t){return(1-t)*i+t*e}function R_(i,e,t,n){return fa(i,e,1-Math.exp(-t*n))}function P_(i,e=1){return e-Math.abs(Zu(i,e*2)-e)}function I_(i,e,t){return i<=e?0:i>=t?1:(i=(i-e)/(t-e),i*i*(3-2*i))}function L_(i,e,t){return i<=e?0:i>=t?1:(i=(i-e)/(t-e),i*i*i*(i*(i*6-15)+10))}function D_(i,e){return i+Math.floor(Math.random()*(e-i+1))}function N_(i,e){return i+Math.random()*(e-i)}function U_(i){return i*(.5-Math.random())}function O_(i){i!==void 0&&(Lp=i);let e=Lp+=1831565813;return e=Math.imul(e^e>>>15,e|1),e^=e+Math.imul(e^e>>>7,e|61),((e^e>>>14)>>>0)/4294967296}function F_(i){return i*da}function B_(i){return i*Er}function k_(i){return i>0&&Number.isInteger(i)&&2**Math.round(Math.log2(i))===i}function z_(i){return Math.pow(2,Math.ceil(Math.log(i)/Math.LN2))}function V_(i){return Math.pow(2,Math.floor(Math.log(i)/Math.LN2))}function G_(i,e,t,n,r){let s=Math.cos,a=Math.sin,o=s(t/2),l=a(t/2),c=s((e+n)/2),h=a((e+n)/2),u=s((e-n)/2),d=a((e-n)/2),f=s((n-e)/2),p=a((n-e)/2);switch(r){case"XYX":i.set(o*h,l*u,l*d,o*c);break;case"YZY":i.set(l*d,o*h,l*u,o*c);break;case"ZXZ":i.set(l*u,l*d,o*h,o*c);break;case"XZX":i.set(o*h,l*p,l*f,o*c);break;case"YXY":i.set(l*f,o*h,l*p,o*c);break;case"ZYZ":i.set(l*p,l*f,o*h,o*c);break;default:Ce("MathUtils: .setQuaternionFromProperEuler() encountered an unknown order: "+r)}}function zi(i,e){switch(e.constructor){case Float32Array:return i;case Uint32Array:return i/4294967295;case Uint16Array:return i/65535;case Uint8Array:case Uint8ClampedArray:return i/255;case Int32Array:return Math.max(i/2147483647,-1);case Int16Array:return Math.max(i/32767,-1);case Int8Array:return Math.max(i/127,-1);default:throw new Error("THREE.MathUtils: Invalid component type.")}}function ct(i,e){switch(e.constructor){case Float32Array:return i;case Uint32Array:return Math.round(i*4294967295);case Uint16Array:return Math.round(i*65535);case Uint8Array:case Uint8ClampedArray:return Math.round(i*255);case Int32Array:return Math.round(i*2147483647);case Int16Array:return Math.round(i*32767);case Int8Array:return Math.round(i*127);default:throw new Error("THREE.MathUtils: Invalid component type.")}}var ye={DEG2RAD:da,RAD2DEG:Er,generateUUID:Hi,clamp:ze,euclideanModulo:Zu,mapLinear:A_,inverseLerp:C_,lerp:fa,damp:R_,pingpong:P_,smoothstep:I_,smootherstep:L_,randInt:D_,randFloat:N_,randFloatSpread:U_,seededRandom:O_,degToRad:F_,radToDeg:B_,isPowerOfTwo:k_,ceilPowerOfTwo:z_,floorPowerOfTwo:V_,setQuaternionFromProperEuler:G_,normalize:ct,denormalize:zi},ed=class ed{constructor(e=0,t=0){this.x=e,this.y=t}get width(){return this.x}set width(e){this.x=e}get height(){return this.y}set height(e){this.y=e}set(e,t){return this.x=e,this.y=t,this}setScalar(e){return this.x=e,this.y=e,this}setX(e){return this.x=e,this}setY(e){return this.y=e,this}setComponent(e,t){switch(e){case 0:this.x=t;break;case 1:this.y=t;break;default:throw new Error("THREE.Vector2: index is out of range: "+e)}return this}getComponent(e){switch(e){case 0:return this.x;case 1:return this.y;default:throw new Error("THREE.Vector2: index is out of range: "+e)}}clone(){return new this.constructor(this.x,this.y)}copy(e){return this.x=e.x,this.y=e.y,this}add(e){return this.x+=e.x,this.y+=e.y,this}addScalar(e){return this.x+=e,this.y+=e,this}addVectors(e,t){return this.x=e.x+t.x,this.y=e.y+t.y,this}addScaledVector(e,t){return this.x+=e.x*t,this.y+=e.y*t,this}sub(e){return this.x-=e.x,this.y-=e.y,this}subScalar(e){return this.x-=e,this.y-=e,this}subVectors(e,t){return this.x=e.x-t.x,this.y=e.y-t.y,this}multiply(e){return this.x*=e.x,this.y*=e.y,this}multiplyScalar(e){return this.x*=e,this.y*=e,this}divide(e){return this.x/=e.x,this.y/=e.y,this}divideScalar(e){return this.multiplyScalar(1/e)}applyMatrix3(e){let t=this.x,n=this.y,r=e.elements;return this.x=r[0]*t+r[3]*n+r[6],this.y=r[1]*t+r[4]*n+r[7],this}min(e){return this.x=Math.min(this.x,e.x),this.y=Math.min(this.y,e.y),this}max(e){return this.x=Math.max(this.x,e.x),this.y=Math.max(this.y,e.y),this}clamp(e,t){return this.x=ze(this.x,e.x,t.x),this.y=ze(this.y,e.y,t.y),this}clampScalar(e,t){return this.x=ze(this.x,e,t),this.y=ze(this.y,e,t),this}clampLength(e,t){let n=this.length();return this.divideScalar(n||1).multiplyScalar(ze(n,e,t))}floor(){return this.x=Math.floor(this.x),this.y=Math.floor(this.y),this}ceil(){return this.x=Math.ceil(this.x),this.y=Math.ceil(this.y),this}round(){return this.x=Math.round(this.x),this.y=Math.round(this.y),this}roundToZero(){return this.x=Math.trunc(this.x),this.y=Math.trunc(this.y),this}negate(){return this.x=-this.x,this.y=-this.y,this}dot(e){return this.x*e.x+this.y*e.y}cross(e){return this.x*e.y-this.y*e.x}lengthSq(){return this.x*this.x+this.y*this.y}length(){return Math.sqrt(this.x*this.x+this.y*this.y)}manhattanLength(){return Math.abs(this.x)+Math.abs(this.y)}normalize(){return this.divideScalar(this.length()||1)}angle(){return Math.atan2(-this.y,-this.x)+Math.PI}angleTo(e){let t=Math.sqrt(this.lengthSq()*e.lengthSq());if(t===0)return Math.PI/2;let n=this.dot(e)/t;return Math.acos(ze(n,-1,1))}distanceTo(e){return Math.sqrt(this.distanceToSquared(e))}distanceToSquared(e){let t=this.x-e.x,n=this.y-e.y;return t*t+n*n}manhattanDistanceTo(e){return Math.abs(this.x-e.x)+Math.abs(this.y-e.y)}setLength(e){return this.normalize().multiplyScalar(e)}lerp(e,t){return this.x+=(e.x-this.x)*t,this.y+=(e.y-this.y)*t,this}lerpVectors(e,t,n){return this.x=e.x+(t.x-e.x)*n,this.y=e.y+(t.y-e.y)*n,this}equals(e){return e.x===this.x&&e.y===this.y}fromArray(e,t=0){return this.x=e[t],this.y=e[t+1],this}toArray(e=[],t=0){return e[t]=this.x,e[t+1]=this.y,e}fromBufferAttribute(e,t){return this.x=e.getX(t),this.y=e.getY(t),this}rotateAround(e,t){let n=Math.cos(t),r=Math.sin(t),s=this.x-e.x,a=this.y-e.y;return this.x=s*n-a*r+e.x,this.y=s*r+a*n+e.y,this}random(){return this.x=Math.random(),this.y=Math.random(),this}*[Symbol.iterator](){yield this.x,yield this.y}};ed.prototype.isVector2=!0;var Se=ed,Ot=class{constructor(e=0,t=0,n=0,r=1){this.isQuaternion=!0,this._x=e,this._y=t,this._z=n,this._w=r}static slerpFlat(e,t,n,r,s,a,o){let l=n[r+0],c=n[r+1],h=n[r+2],u=n[r+3],d=s[a+0],f=s[a+1],p=s[a+2],y=s[a+3];if(u!==y||l!==d||c!==f||h!==p){let m=l*d+c*f+h*p+u*y;m<0&&(d=-d,f=-f,p=-p,y=-y,m=-m);let g=1-o;if(m<.9995){let v=Math.acos(m),S=Math.sin(v);g=Math.sin(g*v)/S,o=Math.sin(o*v)/S,l=l*g+d*o,c=c*g+f*o,h=h*g+p*o,u=u*g+y*o}else{l=l*g+d*o,c=c*g+f*o,h=h*g+p*o,u=u*g+y*o;let v=1/Math.sqrt(l*l+c*c+h*h+u*u);l*=v,c*=v,h*=v,u*=v}}e[t]=l,e[t+1]=c,e[t+2]=h,e[t+3]=u}static multiplyQuaternionsFlat(e,t,n,r,s,a){let o=n[r],l=n[r+1],c=n[r+2],h=n[r+3],u=s[a],d=s[a+1],f=s[a+2],p=s[a+3];return e[t]=o*p+h*u+l*f-c*d,e[t+1]=l*p+h*d+c*u-o*f,e[t+2]=c*p+h*f+o*d-l*u,e[t+3]=h*p-o*u-l*d-c*f,e}get x(){return this._x}set x(e){this._x=e,this._onChangeCallback()}get y(){return this._y}set y(e){this._y=e,this._onChangeCallback()}get z(){return this._z}set z(e){this._z=e,this._onChangeCallback()}get w(){return this._w}set w(e){this._w=e,this._onChangeCallback()}set(e,t,n,r){return this._x=e,this._y=t,this._z=n,this._w=r,this._onChangeCallback(),this}clone(){return new this.constructor(this._x,this._y,this._z,this._w)}copy(e){return this._x=e.x,this._y=e.y,this._z=e.z,this._w=e.w,this._onChangeCallback(),this}setFromEuler(e,t=!0){let n=e._x,r=e._y,s=e._z,a=e._order,o=Math.cos,l=Math.sin,c=o(n/2),h=o(r/2),u=o(s/2),d=l(n/2),f=l(r/2),p=l(s/2);switch(a){case"XYZ":this._x=d*h*u+c*f*p,this._y=c*f*u-d*h*p,this._z=c*h*p+d*f*u,this._w=c*h*u-d*f*p;break;case"YXZ":this._x=d*h*u+c*f*p,this._y=c*f*u-d*h*p,this._z=c*h*p-d*f*u,this._w=c*h*u+d*f*p;break;case"ZXY":this._x=d*h*u-c*f*p,this._y=c*f*u+d*h*p,this._z=c*h*p+d*f*u,this._w=c*h*u-d*f*p;break;case"ZYX":this._x=d*h*u-c*f*p,this._y=c*f*u+d*h*p,this._z=c*h*p-d*f*u,this._w=c*h*u+d*f*p;break;case"YZX":this._x=d*h*u+c*f*p,this._y=c*f*u+d*h*p,this._z=c*h*p-d*f*u,this._w=c*h*u-d*f*p;break;case"XZY":this._x=d*h*u-c*f*p,this._y=c*f*u-d*h*p,this._z=c*h*p+d*f*u,this._w=c*h*u+d*f*p;break;default:Ce("Quaternion: .setFromEuler() encountered an unknown order: "+a)}return t===!0&&this._onChangeCallback(),this}setFromAxisAngle(e,t){let n=t/2,r=Math.sin(n);return this._x=e.x*r,this._y=e.y*r,this._z=e.z*r,this._w=Math.cos(n),this._onChangeCallback(),this}setFromRotationMatrix(e){let t=e.elements,n=t[0],r=t[4],s=t[8],a=t[1],o=t[5],l=t[9],c=t[2],h=t[6],u=t[10],d=n+o+u;if(d>0){let f=.5/Math.sqrt(d+1);this._w=.25/f,this._x=(h-l)*f,this._y=(s-c)*f,this._z=(a-r)*f}else if(n>o&&n>u){let f=2*Math.sqrt(1+n-o-u);this._w=(h-l)/f,this._x=.25*f,this._y=(r+a)/f,this._z=(s+c)/f}else if(o>u){let f=2*Math.sqrt(1+o-n-u);this._w=(s-c)/f,this._x=(r+a)/f,this._y=.25*f,this._z=(l+h)/f}else{let f=2*Math.sqrt(1+u-n-o);this._w=(a-r)/f,this._x=(s+c)/f,this._y=(l+h)/f,this._z=.25*f}return this._onChangeCallback(),this}setFromUnitVectors(e,t){let n=e.dot(t)+1;return n<1e-8?(n=0,Math.abs(e.x)>Math.abs(e.z)?(this._x=-e.y,this._y=e.x,this._z=0,this._w=n):(this._x=0,this._y=-e.z,this._z=e.y,this._w=n)):(this._x=e.y*t.z-e.z*t.y,this._y=e.z*t.x-e.x*t.z,this._z=e.x*t.y-e.y*t.x,this._w=n),this.normalize()}angleTo(e){return 2*Math.acos(Math.abs(ze(this.dot(e),-1,1)))}rotateTowards(e,t){let n=this.angleTo(e);if(n===0)return this;let r=Math.min(1,t/n);return this.slerp(e,r),this}identity(){return this.set(0,0,0,1)}invert(){return this.conjugate()}conjugate(){return this._x*=-1,this._y*=-1,this._z*=-1,this._onChangeCallback(),this}dot(e){return this._x*e._x+this._y*e._y+this._z*e._z+this._w*e._w}lengthSq(){return this._x*this._x+this._y*this._y+this._z*this._z+this._w*this._w}length(){return Math.sqrt(this._x*this._x+this._y*this._y+this._z*this._z+this._w*this._w)}normalize(){let e=this.length();return e===0?(this._x=0,this._y=0,this._z=0,this._w=1):(e=1/e,this._x=this._x*e,this._y=this._y*e,this._z=this._z*e,this._w=this._w*e),this._onChangeCallback(),this}multiply(e){return this.multiplyQuaternions(this,e)}premultiply(e){return this.multiplyQuaternions(e,this)}multiplyQuaternions(e,t){let n=e._x,r=e._y,s=e._z,a=e._w,o=t._x,l=t._y,c=t._z,h=t._w;return this._x=n*h+a*o+r*c-s*l,this._y=r*h+a*l+s*o-n*c,this._z=s*h+a*c+n*l-r*o,this._w=a*h-n*o-r*l-s*c,this._onChangeCallback(),this}slerp(e,t){let n=e._x,r=e._y,s=e._z,a=e._w,o=this.dot(e);o<0&&(n=-n,r=-r,s=-s,a=-a,o=-o);let l=1-t;if(o<.9995){let c=Math.acos(o),h=Math.sin(c);l=Math.sin(l*c)/h,t=Math.sin(t*c)/h,this._x=this._x*l+n*t,this._y=this._y*l+r*t,this._z=this._z*l+s*t,this._w=this._w*l+a*t,this._onChangeCallback()}else this._x=this._x*l+n*t,this._y=this._y*l+r*t,this._z=this._z*l+s*t,this._w=this._w*l+a*t,this.normalize();return this}slerpQuaternions(e,t,n){return this.copy(e).slerp(t,n)}random(){let e=2*Math.PI*Math.random(),t=2*Math.PI*Math.random(),n=Math.random(),r=Math.sqrt(1-n),s=Math.sqrt(n);return this.set(r*Math.sin(e),r*Math.cos(e),s*Math.sin(t),s*Math.cos(t))}equals(e){return e._x===this._x&&e._y===this._y&&e._z===this._z&&e._w===this._w}fromArray(e,t=0){return this._x=e[t],this._y=e[t+1],this._z=e[t+2],this._w=e[t+3],this._onChangeCallback(),this}toArray(e=[],t=0){return e[t]=this._x,e[t+1]=this._y,e[t+2]=this._z,e[t+3]=this._w,e}fromBufferAttribute(e,t){return this._x=e.getX(t),this._y=e.getY(t),this._z=e.getZ(t),this._w=e.getW(t),this._onChangeCallback(),this}toJSON(){return this.toArray()}_onChange(e){return this._onChangeCallback=e,this}_onChangeCallback(){}*[Symbol.iterator](){yield this._x,yield this._y,yield this._z,yield this._w}},td=class td{constructor(e=0,t=0,n=0){this.x=e,this.y=t,this.z=n}set(e,t,n){return n===void 0&&(n=this.z),this.x=e,this.y=t,this.z=n,this}setScalar(e){return this.x=e,this.y=e,this.z=e,this}setX(e){return this.x=e,this}setY(e){return this.y=e,this}setZ(e){return this.z=e,this}setComponent(e,t){switch(e){case 0:this.x=t;break;case 1:this.y=t;break;case 2:this.z=t;break;default:throw new Error("THREE.Vector3: index is out of range: "+e)}return this}getComponent(e){switch(e){case 0:return this.x;case 1:return this.y;case 2:return this.z;default:throw new Error("THREE.Vector3: index is out of range: "+e)}}clone(){return new this.constructor(this.x,this.y,this.z)}copy(e){return this.x=e.x,this.y=e.y,this.z=e.z,this}add(e){return this.x+=e.x,this.y+=e.y,this.z+=e.z,this}addScalar(e){return this.x+=e,this.y+=e,this.z+=e,this}addVectors(e,t){return this.x=e.x+t.x,this.y=e.y+t.y,this.z=e.z+t.z,this}addScaledVector(e,t){return this.x+=e.x*t,this.y+=e.y*t,this.z+=e.z*t,this}sub(e){return this.x-=e.x,this.y-=e.y,this.z-=e.z,this}subScalar(e){return this.x-=e,this.y-=e,this.z-=e,this}subVectors(e,t){return this.x=e.x-t.x,this.y=e.y-t.y,this.z=e.z-t.z,this}multiply(e){return this.x*=e.x,this.y*=e.y,this.z*=e.z,this}multiplyScalar(e){return this.x*=e,this.y*=e,this.z*=e,this}multiplyVectors(e,t){return this.x=e.x*t.x,this.y=e.y*t.y,this.z=e.z*t.z,this}applyEuler(e){return this.applyQuaternion(Dp.setFromEuler(e))}applyAxisAngle(e,t){return this.applyQuaternion(Dp.setFromAxisAngle(e,t))}applyMatrix3(e){let t=this.x,n=this.y,r=this.z,s=e.elements;return this.x=s[0]*t+s[3]*n+s[6]*r,this.y=s[1]*t+s[4]*n+s[7]*r,this.z=s[2]*t+s[5]*n+s[8]*r,this}applyNormalMatrix(e){return this.applyMatrix3(e).normalize()}applyMatrix4(e){let t=this.x,n=this.y,r=this.z,s=e.elements,a=1/(s[3]*t+s[7]*n+s[11]*r+s[15]);return this.x=(s[0]*t+s[4]*n+s[8]*r+s[12])*a,this.y=(s[1]*t+s[5]*n+s[9]*r+s[13])*a,this.z=(s[2]*t+s[6]*n+s[10]*r+s[14])*a,this}applyQuaternion(e){let t=this.x,n=this.y,r=this.z,s=e.x,a=e.y,o=e.z,l=e.w,c=2*(a*r-o*n),h=2*(o*t-s*r),u=2*(s*n-a*t);return this.x=t+l*c+a*u-o*h,this.y=n+l*h+o*c-s*u,this.z=r+l*u+s*h-a*c,this}project(e){return this.applyMatrix4(e.matrixWorldInverse).applyMatrix4(e.projectionMatrix)}unproject(e){return this.applyMatrix4(e.projectionMatrixInverse).applyMatrix4(e.matrixWorld)}transformDirection(e){let t=this.x,n=this.y,r=this.z,s=e.elements;return this.x=s[0]*t+s[4]*n+s[8]*r,this.y=s[1]*t+s[5]*n+s[9]*r,this.z=s[2]*t+s[6]*n+s[10]*r,this.normalize()}divide(e){return this.x/=e.x,this.y/=e.y,this.z/=e.z,this}divideScalar(e){return this.multiplyScalar(1/e)}min(e){return this.x=Math.min(this.x,e.x),this.y=Math.min(this.y,e.y),this.z=Math.min(this.z,e.z),this}max(e){return this.x=Math.max(this.x,e.x),this.y=Math.max(this.y,e.y),this.z=Math.max(this.z,e.z),this}clamp(e,t){return this.x=ze(this.x,e.x,t.x),this.y=ze(this.y,e.y,t.y),this.z=ze(this.z,e.z,t.z),this}clampScalar(e,t){return this.x=ze(this.x,e,t),this.y=ze(this.y,e,t),this.z=ze(this.z,e,t),this}clampLength(e,t){let n=this.length();return this.divideScalar(n||1).multiplyScalar(ze(n,e,t))}floor(){return this.x=Math.floor(this.x),this.y=Math.floor(this.y),this.z=Math.floor(this.z),this}ceil(){return this.x=Math.ceil(this.x),this.y=Math.ceil(this.y),this.z=Math.ceil(this.z),this}round(){return this.x=Math.round(this.x),this.y=Math.round(this.y),this.z=Math.round(this.z),this}roundToZero(){return this.x=Math.trunc(this.x),this.y=Math.trunc(this.y),this.z=Math.trunc(this.z),this}negate(){return this.x=-this.x,this.y=-this.y,this.z=-this.z,this}dot(e){return this.x*e.x+this.y*e.y+this.z*e.z}lengthSq(){return this.x*this.x+this.y*this.y+this.z*this.z}length(){return Math.sqrt(this.x*this.x+this.y*this.y+this.z*this.z)}manhattanLength(){return Math.abs(this.x)+Math.abs(this.y)+Math.abs(this.z)}normalize(){return this.divideScalar(this.length()||1)}setLength(e){return this.normalize().multiplyScalar(e)}lerp(e,t){return this.x+=(e.x-this.x)*t,this.y+=(e.y-this.y)*t,this.z+=(e.z-this.z)*t,this}lerpVectors(e,t,n){return this.x=e.x+(t.x-e.x)*n,this.y=e.y+(t.y-e.y)*n,this.z=e.z+(t.z-e.z)*n,this}cross(e){return this.crossVectors(this,e)}crossVectors(e,t){let n=e.x,r=e.y,s=e.z,a=t.x,o=t.y,l=t.z;return this.x=r*l-s*o,this.y=s*a-n*l,this.z=n*o-r*a,this}projectOnVector(e){let t=e.lengthSq();if(t===0)return this.set(0,0,0);let n=e.dot(this)/t;return this.copy(e).multiplyScalar(n)}projectOnPlane(e){return Gh.copy(this).projectOnVector(e),this.sub(Gh)}reflect(e){return this.sub(Gh.copy(e).multiplyScalar(2*this.dot(e)))}angleTo(e){let t=Math.sqrt(this.lengthSq()*e.lengthSq());if(t===0)return Math.PI/2;let n=this.dot(e)/t;return Math.acos(ze(n,-1,1))}distanceTo(e){return Math.sqrt(this.distanceToSquared(e))}distanceToSquared(e){let t=this.x-e.x,n=this.y-e.y,r=this.z-e.z;return t*t+n*n+r*r}manhattanDistanceTo(e){return Math.abs(this.x-e.x)+Math.abs(this.y-e.y)+Math.abs(this.z-e.z)}setFromSpherical(e){return this.setFromSphericalCoords(e.radius,e.phi,e.theta)}setFromSphericalCoords(e,t,n){let r=Math.sin(t)*e;return this.x=r*Math.sin(n),this.y=Math.cos(t)*e,this.z=r*Math.cos(n),this}setFromCylindrical(e){return this.setFromCylindricalCoords(e.radius,e.theta,e.y)}setFromCylindricalCoords(e,t,n){return this.x=e*Math.sin(t),this.y=n,this.z=e*Math.cos(t),this}setFromMatrixPosition(e){let t=e.elements;return this.x=t[12],this.y=t[13],this.z=t[14],this}setFromMatrixScale(e){let t=this.setFromMatrixColumn(e,0).length(),n=this.setFromMatrixColumn(e,1).length(),r=this.setFromMatrixColumn(e,2).length();return this.x=t,this.y=n,this.z=r,this}setFromMatrixColumn(e,t){return this.fromArray(e.elements,t*4)}setFromMatrix3Column(e,t){return this.fromArray(e.elements,t*3)}setFromEuler(e){return this.x=e._x,this.y=e._y,this.z=e._z,this}setFromColor(e){return this.x=e.r,this.y=e.g,this.z=e.b,this}equals(e){return e.x===this.x&&e.y===this.y&&e.z===this.z}fromArray(e,t=0){return this.x=e[t],this.y=e[t+1],this.z=e[t+2],this}toArray(e=[],t=0){return e[t]=this.x,e[t+1]=this.y,e[t+2]=this.z,e}fromBufferAttribute(e,t){return this.x=e.getX(t),this.y=e.getY(t),this.z=e.getZ(t),this}random(){return this.x=Math.random(),this.y=Math.random(),this.z=Math.random(),this}randomDirection(){let e=Math.random()*Math.PI*2,t=Math.random()*2-1,n=Math.sqrt(1-t*t);return this.x=n*Math.cos(e),this.y=t,this.z=n*Math.sin(e),this}*[Symbol.iterator](){yield this.x,yield this.y,yield this.z}};td.prototype.isVector3=!0;var P=td,Gh=new P,Dp=new Ot,id=class id{constructor(e,t,n,r,s,a,o,l,c){this.elements=[1,0,0,0,1,0,0,0,1],e!==void 0&&this.set(e,t,n,r,s,a,o,l,c)}set(e,t,n,r,s,a,o,l,c){let h=this.elements;return h[0]=e,h[1]=r,h[2]=o,h[3]=t,h[4]=s,h[5]=l,h[6]=n,h[7]=a,h[8]=c,this}identity(){return this.set(1,0,0,0,1,0,0,0,1),this}copy(e){let t=this.elements,n=e.elements;return t[0]=n[0],t[1]=n[1],t[2]=n[2],t[3]=n[3],t[4]=n[4],t[5]=n[5],t[6]=n[6],t[7]=n[7],t[8]=n[8],this}extractBasis(e,t,n){return e.setFromMatrix3Column(this,0),t.setFromMatrix3Column(this,1),n.setFromMatrix3Column(this,2),this}setFromMatrix4(e){let t=e.elements;return this.set(t[0],t[4],t[8],t[1],t[5],t[9],t[2],t[6],t[10]),this}multiply(e){return this.multiplyMatrices(this,e)}premultiply(e){return this.multiplyMatrices(e,this)}multiplyMatrices(e,t){let n=e.elements,r=t.elements,s=this.elements,a=n[0],o=n[3],l=n[6],c=n[1],h=n[4],u=n[7],d=n[2],f=n[5],p=n[8],y=r[0],m=r[3],g=r[6],v=r[1],S=r[4],_=r[7],M=r[2],w=r[5],E=r[8];return s[0]=a*y+o*v+l*M,s[3]=a*m+o*S+l*w,s[6]=a*g+o*_+l*E,s[1]=c*y+h*v+u*M,s[4]=c*m+h*S+u*w,s[7]=c*g+h*_+u*E,s[2]=d*y+f*v+p*M,s[5]=d*m+f*S+p*w,s[8]=d*g+f*_+p*E,this}multiplyScalar(e){let t=this.elements;return t[0]*=e,t[3]*=e,t[6]*=e,t[1]*=e,t[4]*=e,t[7]*=e,t[2]*=e,t[5]*=e,t[8]*=e,this}determinant(){let e=this.elements,t=e[0],n=e[1],r=e[2],s=e[3],a=e[4],o=e[5],l=e[6],c=e[7],h=e[8];return t*a*h-t*o*c-n*s*h+n*o*l+r*s*c-r*a*l}invert(){let e=this.elements,t=e[0],n=e[1],r=e[2],s=e[3],a=e[4],o=e[5],l=e[6],c=e[7],h=e[8],u=h*a-o*c,d=o*l-h*s,f=c*s-a*l,p=t*u+n*d+r*f;if(p===0)return this.set(0,0,0,0,0,0,0,0,0);let y=1/p;return e[0]=u*y,e[1]=(r*c-h*n)*y,e[2]=(o*n-r*a)*y,e[3]=d*y,e[4]=(h*t-r*l)*y,e[5]=(r*s-o*t)*y,e[6]=f*y,e[7]=(n*l-c*t)*y,e[8]=(a*t-n*s)*y,this}transpose(){let e,t=this.elements;return e=t[1],t[1]=t[3],t[3]=e,e=t[2],t[2]=t[6],t[6]=e,e=t[5],t[5]=t[7],t[7]=e,this}getNormalMatrix(e){return this.setFromMatrix4(e).invert().transpose()}transposeIntoArray(e){let t=this.elements;return e[0]=t[0],e[1]=t[3],e[2]=t[6],e[3]=t[1],e[4]=t[4],e[5]=t[7],e[6]=t[2],e[7]=t[5],e[8]=t[8],this}setUvTransform(e,t,n,r,s,a,o){let l=Math.cos(s),c=Math.sin(s);return this.set(n*l,n*c,-n*(l*a+c*o)+a+e,-r*c,r*l,-r*(-c*a+l*o)+o+t,0,0,1),this}scale(e,t){return Mr("Matrix3: .scale() is deprecated. Use .makeScale() instead."),this.premultiply(Hh.makeScale(e,t)),this}rotate(e){return Mr("Matrix3: .rotate() is deprecated. Use .makeRotation() instead."),this.premultiply(Hh.makeRotation(-e)),this}translate(e,t){return Mr("Matrix3: .translate() is deprecated. Use .makeTranslation() instead."),this.premultiply(Hh.makeTranslation(e,t)),this}makeTranslation(e,t){return e.isVector2?this.set(1,0,e.x,0,1,e.y,0,0,1):this.set(1,0,e,0,1,t,0,0,1),this}makeRotation(e){let t=Math.cos(e),n=Math.sin(e);return this.set(t,-n,0,n,t,0,0,0,1),this}makeScale(e,t){return this.set(e,0,0,0,t,0,0,0,1),this}equals(e){let t=this.elements,n=e.elements;for(let r=0;r<9;r++)if(t[r]!==n[r])return!1;return!0}fromArray(e,t=0){for(let n=0;n<9;n++)this.elements[n]=e[n+t];return this}toArray(e=[],t=0){let n=this.elements;return e[t]=n[0],e[t+1]=n[1],e[t+2]=n[2],e[t+3]=n[3],e[t+4]=n[4],e[t+5]=n[5],e[t+6]=n[6],e[t+7]=n[7],e[t+8]=n[8],e}clone(){return new this.constructor().fromArray(this.elements)}};id.prototype.isMatrix3=!0;var Oe=id,Hh=new Oe,Np=new Oe().set(.4123908,.3575843,.1804808,.212639,.7151687,.0721923,.0193308,.1191948,.9505322),Up=new Oe().set(3.2409699,-1.5373832,-.4986108,-.9692436,1.8759675,.0415551,.0556301,-.203977,1.0569715);function H_(){let i={enabled:!0,workingColorSpace:li,spaces:{},convert:function(r,s,a){return this.enabled===!1||s===a||!s||!a||(this.spaces[s].transfer===rt&&(r.r=bn(r.r),r.g=bn(r.g),r.b=bn(r.b)),this.spaces[s].primaries!==this.spaces[a].primaries&&(r.applyMatrix3(this.spaces[s].toXYZ),r.applyMatrix3(this.spaces[a].fromXYZ)),this.spaces[a].transfer===rt&&(r.r=_s(r.r),r.g=_s(r.g),r.b=_s(r.b))),r},workingToColorSpace:function(r,s){return this.convert(r,this.workingColorSpace,s)},colorSpaceToWorking:function(r,s){return this.convert(r,s,this.workingColorSpace)},getPrimaries:function(r){return this.spaces[r].primaries},getTransfer:function(r){return r===Dn?ma:this.spaces[r].transfer},getToneMappingMode:function(r){return this.spaces[r].outputColorSpaceConfig.toneMappingMode||"standard"},getLuminanceCoefficients:function(r,s=this.workingColorSpace){return r.fromArray(this.spaces[s].luminanceCoefficients)},define:function(r){Object.assign(this.spaces,r)},_getMatrix:function(r,s,a){return r.copy(this.spaces[s].toXYZ).multiply(this.spaces[a].fromXYZ)},_getDrawingBufferColorSpace:function(r){return this.spaces[r].outputColorSpaceConfig.drawingBufferColorSpace},_getUnpackColorSpace:function(r=this.workingColorSpace){return this.spaces[r].workingColorSpaceConfig.unpackColorSpace},fromWorkingColorSpace:function(r,s){return Mr("ColorManagement: .fromWorkingColorSpace() has been renamed to .workingToColorSpace()."),i.workingToColorSpace(r,s)},toWorkingColorSpace:function(r,s){return Mr("ColorManagement: .toWorkingColorSpace() has been renamed to .colorSpaceToWorking()."),i.colorSpaceToWorking(r,s)}},e=[.64,.33,.3,.6,.15,.06],t=[.2126,.7152,.0722],n=[.3127,.329];return i.define({[li]:{primaries:e,whitePoint:n,transfer:ma,toXYZ:Np,fromXYZ:Up,luminanceCoefficients:t,workingColorSpaceConfig:{unpackColorSpace:bt},outputColorSpaceConfig:{drawingBufferColorSpace:bt}},[bt]:{primaries:e,whitePoint:n,transfer:rt,toXYZ:Np,fromXYZ:Up,luminanceCoefficients:t,outputColorSpaceConfig:{drawingBufferColorSpace:bt}}}),i}var je=H_();function bn(i){return i<.04045?i*.0773993808:Math.pow(i*.9478672986+.0521327014,2.4)}function _s(i){return i<.0031308?i*12.92:1.055*Math.pow(i,.41666)-.055}var is,xl=class{static getDataURL(e,t="image/png"){if(/^data:/i.test(e.src)||typeof HTMLCanvasElement>"u")return e.src;let n;if(e instanceof HTMLCanvasElement)n=e;else{is===void 0&&(is=Ss("canvas")),is.width=e.width,is.height=e.height;let r=is.getContext("2d");e instanceof ImageData?r.putImageData(e,0,0):r.drawImage(e,0,0,e.width,e.height),n=is}return n.toDataURL(t)}static sRGBToLinear(e){if(typeof HTMLImageElement<"u"&&e instanceof HTMLImageElement||typeof HTMLCanvasElement<"u"&&e instanceof HTMLCanvasElement||typeof ImageBitmap<"u"&&e instanceof ImageBitmap){let t=Ss("canvas");t.width=e.width,t.height=e.height;let n=t.getContext("2d");n.drawImage(e,0,0,e.width,e.height);let r=n.getImageData(0,0,e.width,e.height),s=r.data;for(let a=0;a<s.length;a++)s[a]=bn(s[a]/255)*255;return n.putImageData(r,0,0),t}else if(e.data){let t=e.data.slice(0);for(let n=0;n<t.length;n++)t instanceof Uint8Array||t instanceof Uint8ClampedArray?t[n]=Math.floor(bn(t[n]/255)*255):t[n]=bn(t[n]);return{data:t,width:e.width,height:e.height}}else return Ce("ImageUtils.sRGBToLinear(): Unsupported image type. No color space conversion applied."),e}},W_=0,ws=class{constructor(e=null){this.isTextureSource=!0,Object.defineProperty(this,"id",{value:W_++}),this.uuid=Hi(),this.data=e,this.dataReady=!0,this.version=0}getSize(e){let t=this.data;return typeof HTMLVideoElement<"u"&&t instanceof HTMLVideoElement?e.set(t.videoWidth,t.videoHeight,0):typeof VideoFrame<"u"&&t instanceof VideoFrame?e.set(t.displayWidth,t.displayHeight,0):t!==null?e.set(t.width,t.height,t.depth||0):e.set(0,0,0),e}set needsUpdate(e){e===!0&&this.version++}toJSON(e){let t=e===void 0||typeof e=="string";if(!t&&e.images[this.uuid]!==void 0)return e.images[this.uuid];let n={uuid:this.uuid,url:""},r=this.data;if(r!==null){let s;if(Array.isArray(r)){s=[];for(let a=0,o=r.length;a<o;a++)r[a].isDataTexture?s.push(Wh(r[a].image)):s.push(Wh(r[a]))}else s=Wh(r);n.url=s}return t||(e.images[this.uuid]=n),n}};function Wh(i){return typeof HTMLImageElement<"u"&&i instanceof HTMLImageElement||typeof HTMLCanvasElement<"u"&&i instanceof HTMLCanvasElement||typeof ImageBitmap<"u"&&i instanceof ImageBitmap?xl.getDataURL(i):i.data?{data:Array.from(i.data),width:i.width,height:i.height,type:i.data.constructor.name}:(Ce("Texture: Unable to serialize Texture."),{})}var X_=0,Xh=new P,Pt=class i extends jt{constructor(e=i.DEFAULT_IMAGE,t=i.DEFAULT_MAPPING,n=Li,r=Li,s=St,a=Ci,o=Ri,l=di,c=i.DEFAULT_ANISOTROPY,h=Dn){super(),this.isTexture=!0,Object.defineProperty(this,"id",{value:X_++}),this.uuid=Hi(),this.name="",this.source=new ws(e),this.mipmaps=[],this.mapping=t,this.channel=0,this.wrapS=n,this.wrapT=r,this.magFilter=s,this.minFilter=a,this.anisotropy=c,this.format=o,this.internalFormat=null,this.type=l,this.offset=new Se(0,0),this.repeat=new Se(1,1),this.center=new Se(0,0),this.rotation=0,this.matrixAutoUpdate=!0,this.matrix=new Oe,this.generateMipmaps=!0,this.premultiplyAlpha=!1,this.flipY=!0,this.unpackAlignment=4,this.colorSpace=h,this.userData={},this.updateRanges=[],this.version=0,this.onUpdate=null,this.renderTarget=null,this.isRenderTargetTexture=!1,this.isArrayTexture=!!(e&&e.depth&&e.depth>1),this.pmremVersion=0,this.normalized=!1}get width(){return this.source.getSize(Xh).x}get height(){return this.source.getSize(Xh).y}get depth(){return this.source.getSize(Xh).z}get image(){return this.source.data}set image(e){this.source.data=e}updateMatrix(){this.matrix.setUvTransform(this.offset.x,this.offset.y,this.repeat.x,this.repeat.y,this.rotation,this.center.x,this.center.y)}addUpdateRange(e,t){this.updateRanges.push({start:e,count:t})}clearUpdateRanges(){this.updateRanges.length=0}clone(){return new this.constructor().copy(this)}copy(e){return this.name=e.name,this.source=e.source,this.mipmaps=e.mipmaps.slice(0),this.mapping=e.mapping,this.channel=e.channel,this.wrapS=e.wrapS,this.wrapT=e.wrapT,this.magFilter=e.magFilter,this.minFilter=e.minFilter,this.anisotropy=e.anisotropy,this.format=e.format,this.internalFormat=e.internalFormat,this.type=e.type,this.normalized=e.normalized,this.offset.copy(e.offset),this.repeat.copy(e.repeat),this.center.copy(e.center),this.rotation=e.rotation,this.matrixAutoUpdate=e.matrixAutoUpdate,this.matrix.copy(e.matrix),this.generateMipmaps=e.generateMipmaps,this.premultiplyAlpha=e.premultiplyAlpha,this.flipY=e.flipY,this.unpackAlignment=e.unpackAlignment,this.colorSpace=e.colorSpace,this.renderTarget=e.renderTarget,this.isRenderTargetTexture=e.isRenderTargetTexture,this.isArrayTexture=e.isArrayTexture,this.userData=JSON.parse(JSON.stringify(e.userData)),this.needsUpdate=!0,this}setValues(e){for(let t in e){let n=e[t];if(n===void 0){Ce(`Texture.setValues(): parameter '${t}' has value of undefined.`);continue}let r=this[t];if(r===void 0){Ce(`Texture.setValues(): property '${t}' does not exist.`);continue}r&&n&&r.isVector2&&n.isVector2||r&&n&&r.isVector3&&n.isVector3||r&&n&&r.isMatrix3&&n.isMatrix3?r.copy(n):this[t]=n}}toJSON(e){let t=e===void 0||typeof e=="string";if(!t&&e.textures[this.uuid]!==void 0)return e.textures[this.uuid];let n={metadata:{version:4.7,type:"Texture",generator:"Texture.toJSON"},uuid:this.uuid,name:this.name,image:this.source.toJSON(e).uuid,mapping:this.mapping,channel:this.channel,repeat:[this.repeat.x,this.repeat.y],offset:[this.offset.x,this.offset.y],center:[this.center.x,this.center.y],rotation:this.rotation,wrap:[this.wrapS,this.wrapT],format:this.format,internalFormat:this.internalFormat,type:this.type,normalized:this.normalized,colorSpace:this.colorSpace,minFilter:this.minFilter,magFilter:this.magFilter,anisotropy:this.anisotropy,flipY:this.flipY,generateMipmaps:this.generateMipmaps,premultiplyAlpha:this.premultiplyAlpha,unpackAlignment:this.unpackAlignment};return Object.keys(this.userData).length>0&&(n.userData=this.userData),t||(e.textures[this.uuid]=n),n}dispose(){this.dispatchEvent({type:"dispose"})}transformUv(e){if(this.mapping!==zu)return e;if(e.applyMatrix3(this.matrix),e.x<0||e.x>1)switch(this.wrapS){case $n:e.x=e.x-Math.floor(e.x);break;case Li:e.x=e.x<0?0:1;break;case vs:Math.abs(Math.floor(e.x)%2)===1?e.x=Math.ceil(e.x)-e.x:e.x=e.x-Math.floor(e.x);break}if(e.y<0||e.y>1)switch(this.wrapT){case $n:e.y=e.y-Math.floor(e.y);break;case Li:e.y=e.y<0?0:1;break;case vs:Math.abs(Math.floor(e.y)%2)===1?e.y=Math.ceil(e.y)-e.y:e.y=e.y-Math.floor(e.y);break}return this.flipY&&(e.y=1-e.y),e}set needsUpdate(e){e===!0&&(this.version++,this.source.needsUpdate=!0)}set needsPMREMUpdate(e){e===!0&&this.pmremVersion++}};Pt.DEFAULT_IMAGE=null;Pt.DEFAULT_MAPPING=zu;Pt.DEFAULT_ANISOTROPY=1;var nd=class nd{constructor(e=0,t=0,n=0,r=1){this.x=e,this.y=t,this.z=n,this.w=r}get width(){return this.z}set width(e){this.z=e}get height(){return this.w}set height(e){this.w=e}set(e,t,n,r){return this.x=e,this.y=t,this.z=n,this.w=r,this}setScalar(e){return this.x=e,this.y=e,this.z=e,this.w=e,this}setX(e){return this.x=e,this}setY(e){return this.y=e,this}setZ(e){return this.z=e,this}setW(e){return this.w=e,this}setComponent(e,t){switch(e){case 0:this.x=t;break;case 1:this.y=t;break;case 2:this.z=t;break;case 3:this.w=t;break;default:throw new Error("THREE.Vector4: index is out of range: "+e)}return this}getComponent(e){switch(e){case 0:return this.x;case 1:return this.y;case 2:return this.z;case 3:return this.w;default:throw new Error("THREE.Vector4: index is out of range: "+e)}}clone(){return new this.constructor(this.x,this.y,this.z,this.w)}copy(e){return this.x=e.x,this.y=e.y,this.z=e.z,this.w=e.w!==void 0?e.w:1,this}add(e){return this.x+=e.x,this.y+=e.y,this.z+=e.z,this.w+=e.w,this}addScalar(e){return this.x+=e,this.y+=e,this.z+=e,this.w+=e,this}addVectors(e,t){return this.x=e.x+t.x,this.y=e.y+t.y,this.z=e.z+t.z,this.w=e.w+t.w,this}addScaledVector(e,t){return this.x+=e.x*t,this.y+=e.y*t,this.z+=e.z*t,this.w+=e.w*t,this}sub(e){return this.x-=e.x,this.y-=e.y,this.z-=e.z,this.w-=e.w,this}subScalar(e){return this.x-=e,this.y-=e,this.z-=e,this.w-=e,this}subVectors(e,t){return this.x=e.x-t.x,this.y=e.y-t.y,this.z=e.z-t.z,this.w=e.w-t.w,this}multiply(e){return this.x*=e.x,this.y*=e.y,this.z*=e.z,this.w*=e.w,this}multiplyScalar(e){return this.x*=e,this.y*=e,this.z*=e,this.w*=e,this}applyMatrix4(e){let t=this.x,n=this.y,r=this.z,s=this.w,a=e.elements;return this.x=a[0]*t+a[4]*n+a[8]*r+a[12]*s,this.y=a[1]*t+a[5]*n+a[9]*r+a[13]*s,this.z=a[2]*t+a[6]*n+a[10]*r+a[14]*s,this.w=a[3]*t+a[7]*n+a[11]*r+a[15]*s,this}divide(e){return this.x/=e.x,this.y/=e.y,this.z/=e.z,this.w/=e.w,this}divideScalar(e){return this.multiplyScalar(1/e)}setAxisAngleFromQuaternion(e){this.w=2*Math.acos(e.w);let t=Math.sqrt(1-e.w*e.w);return t<1e-4?(this.x=1,this.y=0,this.z=0):(this.x=e.x/t,this.y=e.y/t,this.z=e.z/t),this}setAxisAngleFromRotationMatrix(e){let t,n,r,s,l=e.elements,c=l[0],h=l[4],u=l[8],d=l[1],f=l[5],p=l[9],y=l[2],m=l[6],g=l[10];if(Math.abs(h-d)<.01&&Math.abs(u-y)<.01&&Math.abs(p-m)<.01){if(Math.abs(h+d)<.1&&Math.abs(u+y)<.1&&Math.abs(p+m)<.1&&Math.abs(c+f+g-3)<.1)return this.set(1,0,0,0),this;t=Math.PI;let S=(c+1)/2,_=(f+1)/2,M=(g+1)/2,w=(h+d)/4,E=(u+y)/4,x=(p+m)/4;return S>_&&S>M?S<.01?(n=0,r=.707106781,s=.707106781):(n=Math.sqrt(S),r=w/n,s=E/n):_>M?_<.01?(n=.707106781,r=0,s=.707106781):(r=Math.sqrt(_),n=w/r,s=x/r):M<.01?(n=.707106781,r=.707106781,s=0):(s=Math.sqrt(M),n=E/s,r=x/s),this.set(n,r,s,t),this}let v=Math.sqrt((m-p)*(m-p)+(u-y)*(u-y)+(d-h)*(d-h));return Math.abs(v)<.001&&(v=1),this.x=(m-p)/v,this.y=(u-y)/v,this.z=(d-h)/v,this.w=Math.acos((c+f+g-1)/2),this}setFromMatrixPosition(e){let t=e.elements;return this.x=t[12],this.y=t[13],this.z=t[14],this.w=t[15],this}min(e){return this.x=Math.min(this.x,e.x),this.y=Math.min(this.y,e.y),this.z=Math.min(this.z,e.z),this.w=Math.min(this.w,e.w),this}max(e){return this.x=Math.max(this.x,e.x),this.y=Math.max(this.y,e.y),this.z=Math.max(this.z,e.z),this.w=Math.max(this.w,e.w),this}clamp(e,t){return this.x=ze(this.x,e.x,t.x),this.y=ze(this.y,e.y,t.y),this.z=ze(this.z,e.z,t.z),this.w=ze(this.w,e.w,t.w),this}clampScalar(e,t){return this.x=ze(this.x,e,t),this.y=ze(this.y,e,t),this.z=ze(this.z,e,t),this.w=ze(this.w,e,t),this}clampLength(e,t){let n=this.length();return this.divideScalar(n||1).multiplyScalar(ze(n,e,t))}floor(){return this.x=Math.floor(this.x),this.y=Math.floor(this.y),this.z=Math.floor(this.z),this.w=Math.floor(this.w),this}ceil(){return this.x=Math.ceil(this.x),this.y=Math.ceil(this.y),this.z=Math.ceil(this.z),this.w=Math.ceil(this.w),this}round(){return this.x=Math.round(this.x),this.y=Math.round(this.y),this.z=Math.round(this.z),this.w=Math.round(this.w),this}roundToZero(){return this.x=Math.trunc(this.x),this.y=Math.trunc(this.y),this.z=Math.trunc(this.z),this.w=Math.trunc(this.w),this}negate(){return this.x=-this.x,this.y=-this.y,this.z=-this.z,this.w=-this.w,this}dot(e){return this.x*e.x+this.y*e.y+this.z*e.z+this.w*e.w}lengthSq(){return this.x*this.x+this.y*this.y+this.z*this.z+this.w*this.w}length(){return Math.sqrt(this.x*this.x+this.y*this.y+this.z*this.z+this.w*this.w)}manhattanLength(){return Math.abs(this.x)+Math.abs(this.y)+Math.abs(this.z)+Math.abs(this.w)}normalize(){return this.divideScalar(this.length()||1)}setLength(e){return this.normalize().multiplyScalar(e)}lerp(e,t){return this.x+=(e.x-this.x)*t,this.y+=(e.y-this.y)*t,this.z+=(e.z-this.z)*t,this.w+=(e.w-this.w)*t,this}lerpVectors(e,t,n){return this.x=e.x+(t.x-e.x)*n,this.y=e.y+(t.y-e.y)*n,this.z=e.z+(t.z-e.z)*n,this.w=e.w+(t.w-e.w)*n,this}equals(e){return e.x===this.x&&e.y===this.y&&e.z===this.z&&e.w===this.w}fromArray(e,t=0){return this.x=e[t],this.y=e[t+1],this.z=e[t+2],this.w=e[t+3],this}toArray(e=[],t=0){return e[t]=this.x,e[t+1]=this.y,e[t+2]=this.z,e[t+3]=this.w,e}fromBufferAttribute(e,t){return this.x=e.getX(t),this.y=e.getY(t),this.z=e.getZ(t),this.w=e.getW(t),this}random(){return this.x=Math.random(),this.y=Math.random(),this.z=Math.random(),this.w=Math.random(),this}*[Symbol.iterator](){yield this.x,yield this.y,yield this.z,yield this.w}};nd.prototype.isVector4=!0;var Xe=nd,vl=class extends jt{constructor(e=1,t=1,n={}){super(),n=Object.assign({generateMipmaps:!1,internalFormat:null,minFilter:St,depthBuffer:!0,stencilBuffer:!1,resolveColorBuffer:!0,resolveDepthBuffer:!0,resolveStencilBuffer:!0,storeMultisampledColorBuffer:!0,storeMultisampledDepthBuffer:!0,storeMultisampledStencilBuffer:!0,depthTexture:null,samples:0,count:1,depth:1,multiview:!1,useArrayDepthTexture:!1},n),this.isRenderTarget=!0,this.width=e,this.height=t,this.depth=n.depth,this.scissor=new Xe(0,0,e,t),this.scissorTest=!1,this.viewport=new Xe(0,0,e,t),this.textures=[];let r={width:e,height:t,depth:n.depth},s=new Pt(r),a=n.count;for(let o=0;o<a;o++)this.textures[o]=s.clone(),this.textures[o].isRenderTargetTexture=!0,this.textures[o].renderTarget=this;this._setTextureOptions(n),this.depthBuffer=n.depthBuffer,this.stencilBuffer=n.stencilBuffer,this.resolveColorBuffer=n.resolveColorBuffer,this.resolveDepthBuffer=n.resolveDepthBuffer,this.resolveStencilBuffer=n.resolveStencilBuffer,this.storeMultisampledColorBuffer=n.storeMultisampledColorBuffer,this.storeMultisampledDepthBuffer=n.storeMultisampledDepthBuffer,this.storeMultisampledStencilBuffer=n.storeMultisampledStencilBuffer,this._depthTexture=null,this.depthTexture=n.depthTexture,this.samples=n.samples,this.multiview=n.multiview,this.useArrayDepthTexture=n.useArrayDepthTexture}_setTextureOptions(e={}){let t={minFilter:St,generateMipmaps:!1,flipY:!1,internalFormat:null};e.mapping!==void 0&&(t.mapping=e.mapping),e.wrapS!==void 0&&(t.wrapS=e.wrapS),e.wrapT!==void 0&&(t.wrapT=e.wrapT),e.wrapR!==void 0&&(t.wrapR=e.wrapR),e.magFilter!==void 0&&(t.magFilter=e.magFilter),e.minFilter!==void 0&&(t.minFilter=e.minFilter),e.format!==void 0&&(t.format=e.format),e.type!==void 0&&(t.type=e.type),e.anisotropy!==void 0&&(t.anisotropy=e.anisotropy),e.colorSpace!==void 0&&(t.colorSpace=e.colorSpace),e.flipY!==void 0&&(t.flipY=e.flipY),e.generateMipmaps!==void 0&&(t.generateMipmaps=e.generateMipmaps),e.internalFormat!==void 0&&(t.internalFormat=e.internalFormat);for(let n=0;n<this.textures.length;n++)this.textures[n].setValues(t)}get texture(){return this.textures[0]}set texture(e){this.textures[0]=e}set depthTexture(e){this._depthTexture!==null&&this._depthTexture.renderTarget===this&&(this._depthTexture.renderTarget=null),e!==null&&e.renderTarget===null&&(e.renderTarget=this),this._depthTexture=e}get depthTexture(){return this._depthTexture}setSize(e,t,n=1){if(this.width!==e||this.height!==t||this.depth!==n){this.width=e,this.height=t,this.depth=n;for(let r=0,s=this.textures.length;r<s;r++)this.textures[r].image.width=e,this.textures[r].image.height=t,this.textures[r].image.depth=n,this.textures[r].isData3DTexture!==!0&&(this.textures[r].isArrayTexture=this.textures[r].image.depth>1);this.dispose()}this.viewport.set(0,0,e,t),this.scissor.set(0,0,e,t)}clone(){return new this.constructor().copy(this)}copy(e){this.width=e.width,this.height=e.height,this.depth=e.depth,this.scissor.copy(e.scissor),this.scissorTest=e.scissorTest,this.viewport.copy(e.viewport),this.textures.length=0;for(let t=0,n=e.textures.length;t<n;t++){this.textures[t]=e.textures[t].clone(),this.textures[t].isRenderTargetTexture=!0,this.textures[t].renderTarget=this;let r=Object.assign({},e.textures[t].image);this.textures[t].source=new ws(r)}if(this.depthBuffer=e.depthBuffer,this.stencilBuffer=e.stencilBuffer,this.resolveColorBuffer=e.resolveColorBuffer,this.resolveDepthBuffer=e.resolveDepthBuffer,this.resolveStencilBuffer=e.resolveStencilBuffer,this.storeMultisampledColorBuffer=e.storeMultisampledColorBuffer,this.storeMultisampledDepthBuffer=e.storeMultisampledDepthBuffer,this.storeMultisampledStencilBuffer=e.storeMultisampledStencilBuffer,e.depthTexture!==null)if(e.depthTexture.renderTarget===e){let t=e.depthTexture.clone();t.renderTarget=null,this.depthTexture=t}else this.depthTexture=e.depthTexture;return this.samples=e.samples,this.multiview=e.multiview,this.useArrayDepthTexture=e.useArrayDepthTexture,this}dispose(){this.dispatchEvent({type:"dispose"})}},ci=class extends vl{constructor(e=1,t=1,n={}){super(e,t,n),this.isWebGLRenderTarget=!0}},ya=class extends Pt{constructor(e=null,t=1,n=1,r=1){super(null),this.isDataArrayTexture=!0,this.image={data:e,width:t,height:n,depth:r},this.magFilter=At,this.minFilter=At,this.wrapR=Li,this.generateMipmaps=!1,this.flipY=!1,this.unpackAlignment=1,this.layerUpdates=new Set}copy(e){return super.copy(e),this.wrapR=e.wrapR,this}addLayerUpdate(e){this.layerUpdates.add(e)}clearLayerUpdates(){this.layerUpdates.clear()}};var bl=class extends Pt{constructor(e=null,t=1,n=1,r=1){super(null),this.isData3DTexture=!0,this.image={data:e,width:t,height:n,depth:r},this.magFilter=At,this.minFilter=At,this.wrapR=Li,this.generateMipmaps=!1,this.flipY=!1,this.unpackAlignment=1}copy(e){return super.copy(e),this.wrapR=e.wrapR,this}};var Fl=class Fl{constructor(e,t,n,r,s,a,o,l,c,h,u,d,f,p,y,m){this.elements=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1],e!==void 0&&this.set(e,t,n,r,s,a,o,l,c,h,u,d,f,p,y,m)}set(e,t,n,r,s,a,o,l,c,h,u,d,f,p,y,m){let g=this.elements;return g[0]=e,g[4]=t,g[8]=n,g[12]=r,g[1]=s,g[5]=a,g[9]=o,g[13]=l,g[2]=c,g[6]=h,g[10]=u,g[14]=d,g[3]=f,g[7]=p,g[11]=y,g[15]=m,this}identity(){return this.set(1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1),this}clone(){return new Fl().fromArray(this.elements)}copy(e){let t=this.elements,n=e.elements;return t[0]=n[0],t[1]=n[1],t[2]=n[2],t[3]=n[3],t[4]=n[4],t[5]=n[5],t[6]=n[6],t[7]=n[7],t[8]=n[8],t[9]=n[9],t[10]=n[10],t[11]=n[11],t[12]=n[12],t[13]=n[13],t[14]=n[14],t[15]=n[15],this}copyPosition(e){let t=this.elements,n=e.elements;return t[12]=n[12],t[13]=n[13],t[14]=n[14],this}setFromMatrix3(e){let t=e.elements;return this.set(t[0],t[3],t[6],0,t[1],t[4],t[7],0,t[2],t[5],t[8],0,0,0,0,1),this}extractBasis(e,t,n){return this.determinantAffine()===0?(e.set(1,0,0),t.set(0,1,0),n.set(0,0,1),this):(e.setFromMatrixColumn(this,0),t.setFromMatrixColumn(this,1),n.setFromMatrixColumn(this,2),this)}makeBasis(e,t,n){return this.set(e.x,t.x,n.x,0,e.y,t.y,n.y,0,e.z,t.z,n.z,0,0,0,0,1),this}extractRotation(e){if(e.determinantAffine()===0)return this.identity();let t=this.elements,n=e.elements,r=1/ns.setFromMatrixColumn(e,0).length(),s=1/ns.setFromMatrixColumn(e,1).length(),a=1/ns.setFromMatrixColumn(e,2).length();return t[0]=n[0]*r,t[1]=n[1]*r,t[2]=n[2]*r,t[3]=0,t[4]=n[4]*s,t[5]=n[5]*s,t[6]=n[6]*s,t[7]=0,t[8]=n[8]*a,t[9]=n[9]*a,t[10]=n[10]*a,t[11]=0,t[12]=0,t[13]=0,t[14]=0,t[15]=1,this}makeRotationFromEuler(e){let t=this.elements,n=e.x,r=e.y,s=e.z,a=Math.cos(n),o=Math.sin(n),l=Math.cos(r),c=Math.sin(r),h=Math.cos(s),u=Math.sin(s);if(e.order==="XYZ"){let d=a*h,f=a*u,p=o*h,y=o*u;t[0]=l*h,t[4]=-l*u,t[8]=c,t[1]=f+p*c,t[5]=d-y*c,t[9]=-o*l,t[2]=y-d*c,t[6]=p+f*c,t[10]=a*l}else if(e.order==="YXZ"){let d=l*h,f=l*u,p=c*h,y=c*u;t[0]=d+y*o,t[4]=p*o-f,t[8]=a*c,t[1]=a*u,t[5]=a*h,t[9]=-o,t[2]=f*o-p,t[6]=y+d*o,t[10]=a*l}else if(e.order==="ZXY"){let d=l*h,f=l*u,p=c*h,y=c*u;t[0]=d-y*o,t[4]=-a*u,t[8]=p+f*o,t[1]=f+p*o,t[5]=a*h,t[9]=y-d*o,t[2]=-a*c,t[6]=o,t[10]=a*l}else if(e.order==="ZYX"){let d=a*h,f=a*u,p=o*h,y=o*u;t[0]=l*h,t[4]=p*c-f,t[8]=d*c+y,t[1]=l*u,t[5]=y*c+d,t[9]=f*c-p,t[2]=-c,t[6]=o*l,t[10]=a*l}else if(e.order==="YZX"){let d=a*l,f=a*c,p=o*l,y=o*c;t[0]=l*h,t[4]=y-d*u,t[8]=p*u+f,t[1]=u,t[5]=a*h,t[9]=-o*h,t[2]=-c*h,t[6]=f*u+p,t[10]=d-y*u}else if(e.order==="XZY"){let d=a*l,f=a*c,p=o*l,y=o*c;t[0]=l*h,t[4]=-u,t[8]=c*h,t[1]=d*u+y,t[5]=a*h,t[9]=f*u-p,t[2]=p*u-f,t[6]=o*h,t[10]=y*u+d}return t[3]=0,t[7]=0,t[11]=0,t[12]=0,t[13]=0,t[14]=0,t[15]=1,this}makeRotationFromQuaternion(e){return this.compose(q_,e,j_)}lookAt(e,t,n){let r=this.elements;return Ei.subVectors(e,t),Ei.lengthSq()===0&&(Ei.z=1),Ei.normalize(),Hn.crossVectors(n,Ei),Hn.lengthSq()===0&&(Math.abs(n.z)===1?Ei.x+=1e-4:Ei.z+=1e-4,Ei.normalize(),Hn.crossVectors(n,Ei)),Hn.normalize(),Bo.crossVectors(Ei,Hn),r[0]=Hn.x,r[4]=Bo.x,r[8]=Ei.x,r[1]=Hn.y,r[5]=Bo.y,r[9]=Ei.y,r[2]=Hn.z,r[6]=Bo.z,r[10]=Ei.z,this}multiply(e){return this.multiplyMatrices(this,e)}premultiply(e){return this.multiplyMatrices(e,this)}multiplyMatrices(e,t){let n=e.elements,r=t.elements,s=this.elements,a=n[0],o=n[4],l=n[8],c=n[12],h=n[1],u=n[5],d=n[9],f=n[13],p=n[2],y=n[6],m=n[10],g=n[14],v=n[3],S=n[7],_=n[11],M=n[15],w=r[0],E=r[4],x=r[8],A=r[12],C=r[1],D=r[5],U=r[9],I=r[13],L=r[2],k=r[6],H=r[10],X=r[14],Y=r[3],q=r[7],K=r[11],N=r[15];return s[0]=a*w+o*C+l*L+c*Y,s[4]=a*E+o*D+l*k+c*q,s[8]=a*x+o*U+l*H+c*K,s[12]=a*A+o*I+l*X+c*N,s[1]=h*w+u*C+d*L+f*Y,s[5]=h*E+u*D+d*k+f*q,s[9]=h*x+u*U+d*H+f*K,s[13]=h*A+u*I+d*X+f*N,s[2]=p*w+y*C+m*L+g*Y,s[6]=p*E+y*D+m*k+g*q,s[10]=p*x+y*U+m*H+g*K,s[14]=p*A+y*I+m*X+g*N,s[3]=v*w+S*C+_*L+M*Y,s[7]=v*E+S*D+_*k+M*q,s[11]=v*x+S*U+_*H+M*K,s[15]=v*A+S*I+_*X+M*N,this}multiplyScalar(e){let t=this.elements;return t[0]*=e,t[4]*=e,t[8]*=e,t[12]*=e,t[1]*=e,t[5]*=e,t[9]*=e,t[13]*=e,t[2]*=e,t[6]*=e,t[10]*=e,t[14]*=e,t[3]*=e,t[7]*=e,t[11]*=e,t[15]*=e,this}determinant(){let e=this.elements,t=e[0],n=e[4],r=e[8],s=e[12],a=e[1],o=e[5],l=e[9],c=e[13],h=e[2],u=e[6],d=e[10],f=e[14],p=e[3],y=e[7],m=e[11],g=e[15],v=l*f-c*d,S=o*f-c*u,_=o*d-l*u,M=a*f-c*h,w=a*d-l*h,E=a*u-o*h;return t*(y*v-m*S+g*_)-n*(p*v-m*M+g*w)+r*(p*S-y*M+g*E)-s*(p*_-y*w+m*E)}determinantAffine(){let e=this.elements,t=e[0],n=e[4],r=e[8],s=e[1],a=e[5],o=e[9],l=e[2],c=e[6],h=e[10];return t*(a*h-o*c)-n*(s*h-o*l)+r*(s*c-a*l)}transpose(){let e=this.elements,t;return t=e[1],e[1]=e[4],e[4]=t,t=e[2],e[2]=e[8],e[8]=t,t=e[6],e[6]=e[9],e[9]=t,t=e[3],e[3]=e[12],e[12]=t,t=e[7],e[7]=e[13],e[13]=t,t=e[11],e[11]=e[14],e[14]=t,this}setPosition(e,t,n){let r=this.elements;return e.isVector3?(r[12]=e.x,r[13]=e.y,r[14]=e.z):(r[12]=e,r[13]=t,r[14]=n),this}invert(){let e=this.elements,t=e[0],n=e[1],r=e[2],s=e[3],a=e[4],o=e[5],l=e[6],c=e[7],h=e[8],u=e[9],d=e[10],f=e[11],p=e[12],y=e[13],m=e[14],g=e[15],v=t*o-n*a,S=t*l-r*a,_=t*c-s*a,M=n*l-r*o,w=n*c-s*o,E=r*c-s*l,x=h*y-u*p,A=h*m-d*p,C=h*g-f*p,D=u*m-d*y,U=u*g-f*y,I=d*g-f*m,L=v*I-S*U+_*D+M*C-w*A+E*x;if(L===0)return this.set(0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0);let k=1/L;return e[0]=(o*I-l*U+c*D)*k,e[1]=(r*U-n*I-s*D)*k,e[2]=(y*E-m*w+g*M)*k,e[3]=(d*w-u*E-f*M)*k,e[4]=(l*C-a*I-c*A)*k,e[5]=(t*I-r*C+s*A)*k,e[6]=(m*_-p*E-g*S)*k,e[7]=(h*E-d*_+f*S)*k,e[8]=(a*U-o*C+c*x)*k,e[9]=(n*C-t*U-s*x)*k,e[10]=(p*w-y*_+g*v)*k,e[11]=(u*_-h*w-f*v)*k,e[12]=(o*A-a*D-l*x)*k,e[13]=(t*D-n*A+r*x)*k,e[14]=(y*S-p*M-m*v)*k,e[15]=(h*M-u*S+d*v)*k,this}scale(e){let t=this.elements,n=e.x,r=e.y,s=e.z;return t[0]*=n,t[4]*=r,t[8]*=s,t[1]*=n,t[5]*=r,t[9]*=s,t[2]*=n,t[6]*=r,t[10]*=s,t[3]*=n,t[7]*=r,t[11]*=s,this}getMaxScaleOnAxis(){let e=this.elements,t=e[0]*e[0]+e[1]*e[1]+e[2]*e[2],n=e[4]*e[4]+e[5]*e[5]+e[6]*e[6],r=e[8]*e[8]+e[9]*e[9]+e[10]*e[10];return Math.sqrt(Math.max(t,n,r))}makeTranslation(e,t,n){return e.isVector3?this.set(1,0,0,e.x,0,1,0,e.y,0,0,1,e.z,0,0,0,1):this.set(1,0,0,e,0,1,0,t,0,0,1,n,0,0,0,1),this}makeRotationX(e){let t=Math.cos(e),n=Math.sin(e);return this.set(1,0,0,0,0,t,-n,0,0,n,t,0,0,0,0,1),this}makeRotationY(e){let t=Math.cos(e),n=Math.sin(e);return this.set(t,0,n,0,0,1,0,0,-n,0,t,0,0,0,0,1),this}makeRotationZ(e){let t=Math.cos(e),n=Math.sin(e);return this.set(t,-n,0,0,n,t,0,0,0,0,1,0,0,0,0,1),this}makeRotationAxis(e,t){let n=Math.cos(t),r=Math.sin(t),s=1-n,a=e.x,o=e.y,l=e.z,c=s*a,h=s*o;return this.set(c*a+n,c*o-r*l,c*l+r*o,0,c*o+r*l,h*o+n,h*l-r*a,0,c*l-r*o,h*l+r*a,s*l*l+n,0,0,0,0,1),this}makeScale(e,t,n){return this.set(e,0,0,0,0,t,0,0,0,0,n,0,0,0,0,1),this}makeShear(e,t,n,r,s,a){return this.set(1,n,s,0,e,1,a,0,t,r,1,0,0,0,0,1),this}compose(e,t,n){let r=this.elements,s=t._x,a=t._y,o=t._z,l=t._w,c=s+s,h=a+a,u=o+o,d=s*c,f=s*h,p=s*u,y=a*h,m=a*u,g=o*u,v=l*c,S=l*h,_=l*u,M=n.x,w=n.y,E=n.z;return r[0]=(1-(y+g))*M,r[1]=(f+_)*M,r[2]=(p-S)*M,r[3]=0,r[4]=(f-_)*w,r[5]=(1-(d+g))*w,r[6]=(m+v)*w,r[7]=0,r[8]=(p+S)*E,r[9]=(m-v)*E,r[10]=(1-(d+y))*E,r[11]=0,r[12]=e.x,r[13]=e.y,r[14]=e.z,r[15]=1,this}decompose(e,t,n){let r=this.elements;e.x=r[12],e.y=r[13],e.z=r[14];let s=this.determinantAffine();if(s===0)return n.set(1,1,1),t.identity(),this;let a=ns.set(r[0],r[1],r[2]).length(),o=ns.set(r[4],r[5],r[6]).length(),l=ns.set(r[8],r[9],r[10]).length();s<0&&(a=-a),Fi.copy(this);let c=1/a,h=1/o,u=1/l;return Fi.elements[0]*=c,Fi.elements[1]*=c,Fi.elements[2]*=c,Fi.elements[4]*=h,Fi.elements[5]*=h,Fi.elements[6]*=h,Fi.elements[8]*=u,Fi.elements[9]*=u,Fi.elements[10]*=u,t.setFromRotationMatrix(Fi),n.x=a,n.y=o,n.z=l,this}makePerspective(e,t,n,r,s,a,o=Gi,l=!1){let c=this.elements,h=2*s/(t-e),u=2*s/(n-r),d=(t+e)/(t-e),f=(n+r)/(n-r),p,y;if(l)p=s/(a-s),y=a*s/(a-s);else if(o===Gi)p=-(a+s)/(a-s),y=-2*a*s/(a-s);else if(o===bs)p=-a/(a-s),y=-a*s/(a-s);else throw new Error("THREE.Matrix4.makePerspective(): Invalid coordinate system: "+o);return c[0]=h,c[4]=0,c[8]=d,c[12]=0,c[1]=0,c[5]=u,c[9]=f,c[13]=0,c[2]=0,c[6]=0,c[10]=p,c[14]=y,c[3]=0,c[7]=0,c[11]=-1,c[15]=0,this}makeOrthographic(e,t,n,r,s,a,o=Gi,l=!1){let c=this.elements,h=2/(t-e),u=2/(n-r),d=-(t+e)/(t-e),f=-(n+r)/(n-r),p,y;if(l)p=1/(a-s),y=a/(a-s);else if(o===Gi)p=-2/(a-s),y=-(a+s)/(a-s);else if(o===bs)p=-1/(a-s),y=-s/(a-s);else throw new Error("THREE.Matrix4.makeOrthographic(): Invalid coordinate system: "+o);return c[0]=h,c[4]=0,c[8]=0,c[12]=d,c[1]=0,c[5]=u,c[9]=0,c[13]=f,c[2]=0,c[6]=0,c[10]=p,c[14]=y,c[3]=0,c[7]=0,c[11]=0,c[15]=1,this}equals(e){let t=this.elements,n=e.elements;for(let r=0;r<16;r++)if(t[r]!==n[r])return!1;return!0}fromArray(e,t=0){for(let n=0;n<16;n++)this.elements[n]=e[n+t];return this}toArray(e=[],t=0){let n=this.elements;return e[t]=n[0],e[t+1]=n[1],e[t+2]=n[2],e[t+3]=n[3],e[t+4]=n[4],e[t+5]=n[5],e[t+6]=n[6],e[t+7]=n[7],e[t+8]=n[8],e[t+9]=n[9],e[t+10]=n[10],e[t+11]=n[11],e[t+12]=n[12],e[t+13]=n[13],e[t+14]=n[14],e[t+15]=n[15],e}};Fl.prototype.isMatrix4=!0;var ge=Fl,ns=new P,Fi=new ge,q_=new P(0,0,0),j_=new P(1,1,1),Hn=new P,Bo=new P,Ei=new P,Op=new ge,Fp=new Ot,Di=class i{constructor(e=0,t=0,n=0,r=i.DEFAULT_ORDER){this.isEuler=!0,this._x=e,this._y=t,this._z=n,this._order=r}get x(){return this._x}set x(e){this._x=e,this._onChangeCallback()}get y(){return this._y}set y(e){this._y=e,this._onChangeCallback()}get z(){return this._z}set z(e){this._z=e,this._onChangeCallback()}get order(){return this._order}set order(e){this._order=e,this._onChangeCallback()}set(e,t,n,r=this._order){return this._x=e,this._y=t,this._z=n,this._order=r,this._onChangeCallback(),this}clone(){return new this.constructor(this._x,this._y,this._z,this._order)}copy(e){return this._x=e._x,this._y=e._y,this._z=e._z,this._order=e._order,this._onChangeCallback(),this}setFromRotationMatrix(e,t=this._order,n=!0){let r=e.elements,s=r[0],a=r[4],o=r[8],l=r[1],c=r[5],h=r[9],u=r[2],d=r[6],f=r[10];switch(t){case"XYZ":this._y=Math.asin(ze(o,-1,1)),Math.abs(o)<.9999999?(this._x=Math.atan2(-h,f),this._z=Math.atan2(-a,s)):(this._x=Math.atan2(d,c),this._z=0);break;case"YXZ":this._x=Math.asin(-ze(h,-1,1)),Math.abs(h)<.9999999?(this._y=Math.atan2(o,f),this._z=Math.atan2(l,c)):(this._y=Math.atan2(-u,s),this._z=0);break;case"ZXY":this._x=Math.asin(ze(d,-1,1)),Math.abs(d)<.9999999?(this._y=Math.atan2(-u,f),this._z=Math.atan2(-a,c)):(this._y=0,this._z=Math.atan2(l,s));break;case"ZYX":this._y=Math.asin(-ze(u,-1,1)),Math.abs(u)<.9999999?(this._x=Math.atan2(d,f),this._z=Math.atan2(l,s)):(this._x=0,this._z=Math.atan2(-a,c));break;case"YZX":this._z=Math.asin(ze(l,-1,1)),Math.abs(l)<.9999999?(this._x=Math.atan2(-h,c),this._y=Math.atan2(-u,s)):(this._x=0,this._y=Math.atan2(o,f));break;case"XZY":this._z=Math.asin(-ze(a,-1,1)),Math.abs(a)<.9999999?(this._x=Math.atan2(d,c),this._y=Math.atan2(o,s)):(this._x=Math.atan2(-h,f),this._y=0);break;default:Ce("Euler: .setFromRotationMatrix() encountered an unknown order: "+t)}return this._order=t,n===!0&&this._onChangeCallback(),this}setFromQuaternion(e,t,n){return Op.makeRotationFromQuaternion(e),this.setFromRotationMatrix(Op,t,n)}setFromVector3(e,t=this._order){return this.set(e.x,e.y,e.z,t)}reorder(e){return Fp.setFromEuler(this),this.setFromQuaternion(Fp,e)}equals(e){return e._x===this._x&&e._y===this._y&&e._z===this._z&&e._order===this._order}fromArray(e){return this._x=e[0],this._y=e[1],this._z=e[2],e[3]!==void 0&&(this._order=e[3]),this._onChangeCallback(),this}toArray(e=[],t=0){return e[t]=this._x,e[t+1]=this._y,e[t+2]=this._z,e[t+3]=this._order,e}_onChange(e){return this._onChangeCallback=e,this}_onChangeCallback(){}*[Symbol.iterator](){yield this._x,yield this._y,yield this._z,yield this._order}};Di.DEFAULT_ORDER="XYZ";var _a=class{constructor(){this.mask=1}set(e){this.mask=(1<<e|0)>>>0}enable(e){this.mask|=1<<e|0}enableAll(){this.mask=-1}toggle(e){this.mask^=1<<e|0}disable(e){this.mask&=~(1<<e|0)}disableAll(){this.mask=0}test(e){return(this.mask&e.mask)!==0}isEnabled(e){return(this.mask&(1<<e|0))!==0}},Y_=0,Bp=new P,rs=new Ot,mn=new ge,ko=new P,ra=new P,$_=new P,Z_=new Ot,kp=new P(1,0,0),zp=new P(0,1,0),Vp=new P(0,0,1),Gp={type:"added"},K_={type:"removed"},ss={type:"childadded",child:null},qh={type:"childremoved",child:null},Tt=class i extends jt{constructor(){super(),this.isObject3D=!0,Object.defineProperty(this,"id",{value:Y_++}),this.uuid=Hi(),this.name="",this.type="Object3D",this.parent=null,this.children=[],this.up=i.DEFAULT_UP.clone();let e=new P,t=new Di,n=new Ot,r=new P(1,1,1);function s(){n.setFromEuler(t,!1)}function a(){t.setFromQuaternion(n,void 0,!1)}t._onChange(s),n._onChange(a),Object.defineProperties(this,{position:{configurable:!0,enumerable:!0,value:e},rotation:{configurable:!0,enumerable:!0,value:t},quaternion:{configurable:!0,enumerable:!0,value:n},scale:{configurable:!0,enumerable:!0,value:r},modelViewMatrix:{value:new ge},normalMatrix:{value:new Oe}}),this.matrix=new ge,this.matrixWorld=new ge,this.matrixAutoUpdate=i.DEFAULT_MATRIX_AUTO_UPDATE,this.matrixWorldAutoUpdate=i.DEFAULT_MATRIX_WORLD_AUTO_UPDATE,this.matrixWorldNeedsUpdate=!1,this.layers=new _a,this.visible=!0,this.castShadow=!1,this.receiveShadow=!1,this.frustumCulled=!0,this.renderOrder=0,this.animations=[],this.customDepthMaterial=void 0,this.customDistanceMaterial=void 0,this.static=!1,this.userData={},this.pivot=null}onBeforeShadow(){}onAfterShadow(){}onBeforeRender(){}onAfterRender(){}applyMatrix4(e){this.matrixAutoUpdate&&this.updateMatrix(),this.matrix.premultiply(e),this.matrix.decompose(this.position,this.quaternion,this.scale)}applyQuaternion(e){return this.quaternion.premultiply(e),this}setRotationFromAxisAngle(e,t){this.quaternion.setFromAxisAngle(e,t)}setRotationFromEuler(e){this.quaternion.setFromEuler(e,!0)}setRotationFromMatrix(e){this.quaternion.setFromRotationMatrix(e)}setRotationFromQuaternion(e){this.quaternion.copy(e)}rotateOnAxis(e,t){return rs.setFromAxisAngle(e,t),this.quaternion.multiply(rs),this}rotateOnWorldAxis(e,t){return rs.setFromAxisAngle(e,t),this.quaternion.premultiply(rs),this}rotateX(e){return this.rotateOnAxis(kp,e)}rotateY(e){return this.rotateOnAxis(zp,e)}rotateZ(e){return this.rotateOnAxis(Vp,e)}translateOnAxis(e,t){return Bp.copy(e).applyQuaternion(this.quaternion),this.position.add(Bp.multiplyScalar(t)),this}translateX(e){return this.translateOnAxis(kp,e)}translateY(e){return this.translateOnAxis(zp,e)}translateZ(e){return this.translateOnAxis(Vp,e)}localToWorld(e){return this.updateWorldMatrix(!0,!1),e.applyMatrix4(this.matrixWorld)}worldToLocal(e){return this.updateWorldMatrix(!0,!1),e.applyMatrix4(mn.copy(this.matrixWorld).invert())}lookAt(e,t,n){e.isVector3?ko.copy(e):ko.set(e,t,n);let r=this.parent;this.updateWorldMatrix(!0,!1),ra.setFromMatrixPosition(this.matrixWorld),this.isCamera||this.isLight?mn.lookAt(ra,ko,this.up):mn.lookAt(ko,ra,this.up),this.quaternion.setFromRotationMatrix(mn),r&&(mn.extractRotation(r.matrixWorld),rs.setFromRotationMatrix(mn),this.quaternion.premultiply(rs.invert()))}add(e){if(arguments.length>1){for(let t=0;t<arguments.length;t++)this.add(arguments[t]);return this}return e===this?(Fe("Object3D.add: object can't be added as a child of itself.",e),this):(e&&e.isObject3D?(e.removeFromParent(),e.parent=this,this.children.push(e),e.dispatchEvent(Gp),ss.child=e,this.dispatchEvent(ss),ss.child=null):Fe("Object3D.add: object not an instance of THREE.Object3D.",e),this)}remove(e){if(arguments.length>1){for(let n=0;n<arguments.length;n++)this.remove(arguments[n]);return this}let t=this.children.indexOf(e);return t!==-1&&(e.parent=null,this.children.splice(t,1),e.dispatchEvent(K_),qh.child=e,this.dispatchEvent(qh),qh.child=null),this}removeFromParent(){let e=this.parent;return e!==null&&e.remove(this),this}clear(){return this.remove(...this.children)}attach(e){return this.updateWorldMatrix(!0,!1),mn.copy(this.matrixWorld).invert(),e.parent!==null&&(e.parent.updateWorldMatrix(!0,!1),mn.multiply(e.parent.matrixWorld)),e.applyMatrix4(mn),e.removeFromParent(),e.parent=this,this.children.push(e),e.updateWorldMatrix(!1,!0),e.dispatchEvent(Gp),ss.child=e,this.dispatchEvent(ss),ss.child=null,this}getObjectById(e){return this.getObjectByProperty("id",e)}getObjectByName(e){return this.getObjectByProperty("name",e)}getObjectByProperty(e,t){if(this[e]===t)return this;for(let n=0,r=this.children.length;n<r;n++){let a=this.children[n].getObjectByProperty(e,t);if(a!==void 0)return a}}getObjectsByProperty(e,t,n=[]){this[e]===t&&n.push(this);let r=this.children;for(let s=0,a=r.length;s<a;s++)r[s].getObjectsByProperty(e,t,n);return n}getWorldPosition(e){return this.updateWorldMatrix(!0,!1),e.setFromMatrixPosition(this.matrixWorld)}getWorldQuaternion(e){return this.updateWorldMatrix(!0,!1),this.matrixWorld.decompose(ra,e,$_),e}getWorldScale(e){return this.updateWorldMatrix(!0,!1),this.matrixWorld.decompose(ra,Z_,e),e}getWorldDirection(e){this.updateWorldMatrix(!0,!1);let t=this.matrixWorld.elements;return e.set(t[8],t[9],t[10]).normalize()}raycast(){}intersectsFrustum(){}traverse(e){e(this);let t=this.children;for(let n=0,r=t.length;n<r;n++)t[n].traverse(e)}traverseVisible(e){if(this.visible===!1)return;e(this);let t=this.children;for(let n=0,r=t.length;n<r;n++)t[n].traverseVisible(e)}traverseAncestors(e){let t=this.parent;t!==null&&(e(t),t.traverseAncestors(e))}updateMatrix(){this.matrix.compose(this.position,this.quaternion,this.scale);let e=this.pivot;if(e!==null){let t=e.x,n=e.y,r=e.z,s=this.matrix.elements;s[12]+=t-s[0]*t-s[4]*n-s[8]*r,s[13]+=n-s[1]*t-s[5]*n-s[9]*r,s[14]+=r-s[2]*t-s[6]*n-s[10]*r}this.matrixWorldNeedsUpdate=!0}updateMatrixWorld(e){this.matrixAutoUpdate&&this.updateMatrix(),(this.matrixWorldNeedsUpdate||e)&&(this.matrixWorldAutoUpdate===!0&&(this.parent===null?this.matrixWorld.copy(this.matrix):this.matrixWorld.multiplyMatrices(this.parent.matrixWorld,this.matrix)),this.matrixWorldNeedsUpdate=!1,e=!0);let t=this.children;for(let n=0,r=t.length;n<r;n++)t[n].updateMatrixWorld(e)}updateWorldMatrix(e,t,n=!1){let r=this.parent;if(e===!0&&r!==null&&r.updateWorldMatrix(!0,!1),this.matrixAutoUpdate&&this.updateMatrix(),(this.matrixWorldNeedsUpdate||n)&&(this.matrixWorldAutoUpdate===!0&&(this.parent===null?this.matrixWorld.copy(this.matrix):this.matrixWorld.multiplyMatrices(this.parent.matrixWorld,this.matrix)),this.matrixWorldNeedsUpdate=!1,n=!0),t===!0){let s=this.children;for(let a=0,o=s.length;a<o;a++)s[a].updateWorldMatrix(!1,!0,n)}}toJSON(e){let t=e===void 0||typeof e=="string",n={};t&&(e={geometries:{},materials:{},textures:{},images:{},shapes:{},skeletons:{},animations:{},nodes:{}},n.metadata={version:4.7,type:"Object",generator:"Object3D.toJSON"});let r={};r.uuid=this.uuid,r.type=this.type,r.name=this.name,r.castShadow=this.castShadow,r.receiveShadow=this.receiveShadow,r.visible=this.visible,r.frustumCulled=this.frustumCulled,r.renderOrder=this.renderOrder,r.static=this.static,r.matrixAutoUpdate=this.matrixAutoUpdate,Object.keys(this.userData).length>0&&(r.userData=this.userData),r.layers=this.layers.mask,r.matrix=this.matrix.toArray(),r.up=this.up.toArray(),this.pivot!==null&&(r.pivot=this.pivot.toArray()),this.morphTargetDictionary!==void 0&&(r.morphTargetDictionary=Object.assign({},this.morphTargetDictionary)),this.morphTargetInfluences!==void 0&&(r.morphTargetInfluences=this.morphTargetInfluences.slice()),this.isInstancedMesh&&(r.type="InstancedMesh",r.count=this.count,r.instanceMatrix=this.instanceMatrix.toJSON(),this.instanceColor!==null&&(r.instanceColor=this.instanceColor.toJSON())),this.isBatchedMesh&&(r.type="BatchedMesh",r.perObjectFrustumCulled=this.perObjectFrustumCulled,r.sortObjects=this.sortObjects,r.drawRanges=this._drawRanges,r.reservedRanges=this._reservedRanges,r.geometryInfo=this._geometryInfo.map(o=>({...o,boundingBox:o.boundingBox?o.boundingBox.toJSON():void 0,boundingSphere:o.boundingSphere?o.boundingSphere.toJSON():void 0})),r.instanceInfo=this._instanceInfo.map(o=>({...o})),r.availableInstanceIds=this._availableInstanceIds.slice(),r.availableGeometryIds=this._availableGeometryIds.slice(),r.nextIndexStart=this._nextIndexStart,r.nextVertexStart=this._nextVertexStart,r.geometryCount=this._geometryCount,r.maxInstanceCount=this._maxInstanceCount,r.maxVertexCount=this._maxVertexCount,r.maxIndexCount=this._maxIndexCount,r.geometryInitialized=this._geometryInitialized,r.matricesTexture=this._matricesTexture.toJSON(e),r.indirectTexture=this._indirectTexture.toJSON(e),this._colorsTexture!==null&&(r.colorsTexture=this._colorsTexture.toJSON(e)),this.boundingSphere!==null&&(r.boundingSphere=this.boundingSphere.toJSON()),this.boundingBox!==null&&(r.boundingBox=this.boundingBox.toJSON()));function s(o,l){return o[l.uuid]===void 0&&(o[l.uuid]=l.toJSON(e)),l.uuid}if(this.isScene)this.background&&(this.background.isColor?r.background=this.background.toJSON():this.background.isTexture&&(r.background=this.background.toJSON(e).uuid)),this.environment&&this.environment.isTexture&&this.environment.isRenderTargetTexture!==!0&&(r.environment=this.environment.toJSON(e).uuid);else if(this.isMesh||this.isLine||this.isPoints){r.geometry=s(e.geometries,this.geometry);let o=this.geometry.parameters;if(o!==void 0&&o.shapes!==void 0){let l=o.shapes;if(Array.isArray(l))for(let c=0,h=l.length;c<h;c++){let u=l[c];s(e.shapes,u)}else s(e.shapes,l)}}if(this.isSkinnedMesh&&(r.bindMode=this.bindMode,r.bindMatrix=this.bindMatrix.toArray(),this.skeleton!==void 0&&(s(e.skeletons,this.skeleton),r.skeleton=this.skeleton.uuid)),this.material!==void 0)if(Array.isArray(this.material)){let o=[];for(let l=0,c=this.material.length;l<c;l++)o.push(s(e.materials,this.material[l]));r.material=o}else r.material=s(e.materials,this.material);if(this.children.length>0){r.children=[];for(let o=0;o<this.children.length;o++)r.children.push(this.children[o].toJSON(e).object)}if(this.animations.length>0){r.animations=[];for(let o=0;o<this.animations.length;o++){let l=this.animations[o];r.animations.push(s(e.animations,l))}}if(t){let o=a(e.geometries),l=a(e.materials),c=a(e.textures),h=a(e.images),u=a(e.shapes),d=a(e.skeletons),f=a(e.animations),p=a(e.nodes);o.length>0&&(n.geometries=o),l.length>0&&(n.materials=l),c.length>0&&(n.textures=c),h.length>0&&(n.images=h),u.length>0&&(n.shapes=u),d.length>0&&(n.skeletons=d),f.length>0&&(n.animations=f),p.length>0&&(n.nodes=p)}return n.object=r,n;function a(o){let l=[];for(let c in o){let h=o[c];delete h.metadata,l.push(h)}return l}}clone(e){return new this.constructor().copy(this,e)}copy(e,t=!0){if(this.name=e.name,this.up.copy(e.up),this.position.copy(e.position),this.rotation.order=e.rotation.order,this.quaternion.copy(e.quaternion),this.scale.copy(e.scale),this.pivot=e.pivot!==null?e.pivot.clone():null,this.matrix.copy(e.matrix),this.matrixWorld.copy(e.matrixWorld),this.matrixAutoUpdate=e.matrixAutoUpdate,this.matrixWorldAutoUpdate=e.matrixWorldAutoUpdate,this.matrixWorldNeedsUpdate=e.matrixWorldNeedsUpdate,this.layers.mask=e.layers.mask,this.visible=e.visible,this.castShadow=e.castShadow,this.receiveShadow=e.receiveShadow,this.frustumCulled=e.frustumCulled,this.renderOrder=e.renderOrder,this.static=e.static,this.animations=e.animations.slice(),this.userData=JSON.parse(JSON.stringify(e.userData)),t===!0)for(let n=0;n<e.children.length;n++){let r=e.children[n];this.add(r.clone())}return this}dispose(){this.dispatchEvent({type:"dispose"})}};Tt.DEFAULT_UP=new P(0,1,0);Tt.DEFAULT_MATRIX_AUTO_UPDATE=!0;Tt.DEFAULT_MATRIX_WORLD_AUTO_UPDATE=!0;var Xt=class extends Tt{constructor(){super(),this.isGroup=!0,this.type="Group"}},J_={type:"move"},Ts=class{constructor(){this._targetRay=null,this._grip=null,this._hand=null}getHandSpace(){return this._hand===null&&(this._hand=new Xt,this._hand.matrixAutoUpdate=!1,this._hand.visible=!1,this._hand.joints={},this._hand.inputState={pinching:!1}),this._hand}getTargetRaySpace(){return this._targetRay===null&&(this._targetRay=new Xt,this._targetRay.matrixAutoUpdate=!1,this._targetRay.visible=!1,this._targetRay.hasLinearVelocity=!1,this._targetRay.linearVelocity=new P,this._targetRay.hasAngularVelocity=!1,this._targetRay.angularVelocity=new P),this._targetRay}getGripSpace(){return this._grip===null&&(this._grip=new Xt,this._grip.matrixAutoUpdate=!1,this._grip.visible=!1,this._grip.hasLinearVelocity=!1,this._grip.linearVelocity=new P,this._grip.hasAngularVelocity=!1,this._grip.angularVelocity=new P,this._grip.eventsEnabled=!1),this._grip}dispatchEvent(e){return this._targetRay!==null&&this._targetRay.dispatchEvent(e),this._grip!==null&&this._grip.dispatchEvent(e),this._hand!==null&&this._hand.dispatchEvent(e),this}connect(e){if(e&&e.hand){let t=this._hand;if(t)for(let n of e.hand.values())this._getHandJoint(t,n)}return this.dispatchEvent({type:"connected",data:e}),this}disconnect(e){return this.dispatchEvent({type:"disconnected",data:e}),this._targetRay!==null&&(this._targetRay.visible=!1),this._grip!==null&&(this._grip.visible=!1),this._hand!==null&&(this._hand.visible=!1),this}update(e,t,n){let r=null,s=null,a=null,o=this._targetRay,l=this._grip,c=this._hand;if(e&&t.session.visibilityState!=="visible-blurred"){if(c&&e.hand){a=!0;for(let y of e.hand.values()){let m=t.getJointPose(y,n),g=this._getHandJoint(c,y);m!==null&&(g.matrix.fromArray(m.transform.matrix),g.matrix.decompose(g.position,g.rotation,g.scale),g.matrixWorldNeedsUpdate=!0,g.jointRadius=m.radius),g.visible=m!==null}let h=c.joints["index-finger-tip"],u=c.joints["thumb-tip"],d=h.position.distanceTo(u.position),f=.02,p=.005;c.inputState.pinching&&d>f+p?(c.inputState.pinching=!1,this.dispatchEvent({type:"pinchend",handedness:e.handedness,target:this})):!c.inputState.pinching&&d<=f-p&&(c.inputState.pinching=!0,this.dispatchEvent({type:"pinchstart",handedness:e.handedness,target:this}))}else l!==null&&e.gripSpace&&(s=t.getPose(e.gripSpace,n),s!==null&&(l.matrix.fromArray(s.transform.matrix),l.matrix.decompose(l.position,l.rotation,l.scale),l.matrixWorldNeedsUpdate=!0,s.linearVelocity?(l.hasLinearVelocity=!0,l.linearVelocity.copy(s.linearVelocity)):l.hasLinearVelocity=!1,s.angularVelocity?(l.hasAngularVelocity=!0,l.angularVelocity.copy(s.angularVelocity)):l.hasAngularVelocity=!1,l.eventsEnabled&&l.dispatchEvent({type:"gripUpdated",data:e,target:this})));o!==null&&(r=t.getPose(e.targetRaySpace,n),r===null&&s!==null&&(r=s),r!==null&&(o.matrix.fromArray(r.transform.matrix),o.matrix.decompose(o.position,o.rotation,o.scale),o.matrixWorldNeedsUpdate=!0,r.linearVelocity?(o.hasLinearVelocity=!0,o.linearVelocity.copy(r.linearVelocity)):o.hasLinearVelocity=!1,r.angularVelocity?(o.hasAngularVelocity=!0,o.angularVelocity.copy(r.angularVelocity)):o.hasAngularVelocity=!1,this.dispatchEvent(J_)))}return o!==null&&(o.visible=r!==null),l!==null&&(l.visible=s!==null),c!==null&&(c.visible=a!==null),this}_getHandJoint(e,t){if(e.joints[t.jointName]===void 0){let n=new Xt;n.matrixAutoUpdate=!1,n.visible=!1,e.joints[t.jointName]=n,e.add(n)}return e.joints[t.jointName]}},Km={aliceblue:15792383,antiquewhite:16444375,aqua:65535,aquamarine:8388564,azure:15794175,beige:16119260,bisque:16770244,black:0,blanchedalmond:16772045,blue:255,blueviolet:9055202,brown:10824234,burlywood:14596231,cadetblue:6266528,chartreuse:8388352,chocolate:13789470,coral:16744272,cornflowerblue:6591981,cornsilk:16775388,crimson:14423100,cyan:65535,darkblue:139,darkcyan:35723,darkgoldenrod:12092939,darkgray:11119017,darkgreen:25600,darkgrey:11119017,darkkhaki:12433259,darkmagenta:9109643,darkolivegreen:5597999,darkorange:16747520,darkorchid:10040012,darkred:9109504,darksalmon:15308410,darkseagreen:9419919,darkslateblue:4734347,darkslategray:3100495,darkslategrey:3100495,darkturquoise:52945,darkviolet:9699539,deeppink:16716947,deepskyblue:49151,dimgray:6908265,dimgrey:6908265,dodgerblue:2003199,firebrick:11674146,floralwhite:16775920,forestgreen:2263842,fuchsia:16711935,gainsboro:14474460,ghostwhite:16316671,gold:16766720,goldenrod:14329120,gray:8421504,green:32768,greenyellow:11403055,grey:8421504,honeydew:15794160,hotpink:16738740,indianred:13458524,indigo:4915330,ivory:16777200,khaki:15787660,lavender:15132410,lavenderblush:16773365,lawngreen:8190976,lemonchiffon:16775885,lightblue:11393254,lightcoral:15761536,lightcyan:14745599,lightgoldenrodyellow:16448210,lightgray:13882323,lightgreen:9498256,lightgrey:13882323,lightpink:16758465,lightsalmon:16752762,lightseagreen:2142890,lightskyblue:8900346,lightslategray:7833753,lightslategrey:7833753,lightsteelblue:11584734,lightyellow:16777184,lime:65280,limegreen:3329330,linen:16445670,magenta:16711935,maroon:8388608,mediumaquamarine:6737322,mediumblue:205,mediumorchid:12211667,mediumpurple:9662683,mediumseagreen:3978097,mediumslateblue:8087790,mediumspringgreen:64154,mediumturquoise:4772300,mediumvioletred:13047173,midnightblue:1644912,mintcream:16121850,mistyrose:16770273,moccasin:16770229,navajowhite:16768685,navy:128,oldlace:16643558,olive:8421376,olivedrab:7048739,orange:16753920,orangered:16729344,orchid:14315734,palegoldenrod:15657130,palegreen:10025880,paleturquoise:11529966,palevioletred:14381203,papayawhip:16773077,peachpuff:16767673,peru:13468991,pink:16761035,plum:14524637,powderblue:11591910,purple:8388736,rebeccapurple:6697881,red:16711680,rosybrown:12357519,royalblue:4286945,saddlebrown:9127187,salmon:16416882,sandybrown:16032864,seagreen:3050327,seashell:16774638,sienna:10506797,silver:12632256,skyblue:8900331,slateblue:6970061,slategray:7372944,slategrey:7372944,snow:16775930,springgreen:65407,steelblue:4620980,tan:13808780,teal:32896,thistle:14204888,tomato:16737095,turquoise:4251856,violet:15631086,wheat:16113331,white:16777215,whitesmoke:16119285,yellow:16776960,yellowgreen:10145074},Wn={h:0,s:0,l:0},zo={h:0,s:0,l:0};function jh(i,e,t){return t<0&&(t+=1),t>1&&(t-=1),t<1/6?i+(e-i)*6*t:t<1/2?e:t<2/3?i+(e-i)*6*(2/3-t):i}var Ie=class{constructor(e,t,n){return this.isColor=!0,this.r=1,this.g=1,this.b=1,this.set(e,t,n)}set(e,t,n){if(t===void 0&&n===void 0){let r=e;r&&r.isColor?this.copy(r):typeof r=="number"?this.setHex(r):typeof r=="string"&&this.setStyle(r)}else this.setRGB(e,t,n);return this}setScalar(e){return this.r=e,this.g=e,this.b=e,this}setHex(e,t=bt){return e=Math.floor(e),this.r=(e>>16&255)/255,this.g=(e>>8&255)/255,this.b=(e&255)/255,je.colorSpaceToWorking(this,t),this}setRGB(e,t,n,r=je.workingColorSpace){return this.r=e,this.g=t,this.b=n,je.colorSpaceToWorking(this,r),this}setHSL(e,t,n,r=je.workingColorSpace){if(e=Zu(e,1),t=ze(t,0,1),n=ze(n,0,1),t===0)this.r=this.g=this.b=n;else{let s=n<=.5?n*(1+t):n+t-n*t,a=2*n-s;this.r=jh(a,s,e+1/3),this.g=jh(a,s,e),this.b=jh(a,s,e-1/3)}return je.colorSpaceToWorking(this,r),this}setStyle(e,t=bt){function n(s){s!==void 0&&parseFloat(s)<1&&Ce("Color: Alpha component of "+e+" will be ignored.")}let r;if(r=/^(\w+)\(([^\)]*)\)/.exec(e)){let s,a=r[1],o=r[2];switch(a){case"rgb":case"rgba":if(s=/^\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*(\d*\.?\d+)\s*)?$/.exec(o))return n(s[4]),this.setRGB(Math.min(255,parseInt(s[1],10))/255,Math.min(255,parseInt(s[2],10))/255,Math.min(255,parseInt(s[3],10))/255,t);if(s=/^\s*(\d+)\%\s*,\s*(\d+)\%\s*,\s*(\d+)\%\s*(?:,\s*(\d*\.?\d+)\s*)?$/.exec(o))return n(s[4]),this.setRGB(Math.min(100,parseInt(s[1],10))/100,Math.min(100,parseInt(s[2],10))/100,Math.min(100,parseInt(s[3],10))/100,t);break;case"hsl":case"hsla":if(s=/^\s*(\d*\.?\d+)\s*,\s*(\d*\.?\d+)\%\s*,\s*(\d*\.?\d+)\%\s*(?:,\s*(\d*\.?\d+)\s*)?$/.exec(o))return n(s[4]),this.setHSL(parseFloat(s[1])/360,parseFloat(s[2])/100,parseFloat(s[3])/100,t);break;default:Ce("Color: Unknown color model "+e)}}else if(r=/^\#([A-Fa-f\d]+)$/.exec(e)){let s=r[1],a=s.length;if(a===3)return this.setRGB(parseInt(s.charAt(0),16)/15,parseInt(s.charAt(1),16)/15,parseInt(s.charAt(2),16)/15,t);if(a===6)return this.setHex(parseInt(s,16),t);Ce("Color: Invalid hex color "+e)}else if(e&&e.length>0)return this.setColorName(e,t);return this}setColorName(e,t=bt){let n=Km[e.toLowerCase()];return n!==void 0?this.setHex(n,t):Ce("Color: Unknown color "+e),this}clone(){return new this.constructor(this.r,this.g,this.b)}copy(e){return this.r=e.r,this.g=e.g,this.b=e.b,this}copySRGBToLinear(e){return this.r=bn(e.r),this.g=bn(e.g),this.b=bn(e.b),this}copyLinearToSRGB(e){return this.r=_s(e.r),this.g=_s(e.g),this.b=_s(e.b),this}convertSRGBToLinear(){return this.copySRGBToLinear(this),this}convertLinearToSRGB(){return this.copyLinearToSRGB(this),this}getHex(e=bt){return je.workingToColorSpace(ni.copy(this),e),Math.round(ze(ni.r*255,0,255))*65536+Math.round(ze(ni.g*255,0,255))*256+Math.round(ze(ni.b*255,0,255))}getHexString(e=bt){return("000000"+this.getHex(e).toString(16)).slice(-6)}getHSL(e,t=je.workingColorSpace){je.workingToColorSpace(ni.copy(this),t);let n=ni.r,r=ni.g,s=ni.b,a=Math.max(n,r,s),o=Math.min(n,r,s),l,c,h=(o+a)/2;if(o===a)l=0,c=0;else{let u=a-o;switch(c=h<=.5?u/(a+o):u/(2-a-o),a){case n:l=(r-s)/u+(r<s?6:0);break;case r:l=(s-n)/u+2;break;case s:l=(n-r)/u+4;break}l/=6}return e.h=l,e.s=c,e.l=h,e}getRGB(e,t=je.workingColorSpace){return je.workingToColorSpace(ni.copy(this),t),e.r=ni.r,e.g=ni.g,e.b=ni.b,e}getStyle(e=bt){je.workingToColorSpace(ni.copy(this),e);let t=ni.r,n=ni.g,r=ni.b;return e!==bt?`color(${e} ${t.toFixed(3)} ${n.toFixed(3)} ${r.toFixed(3)})`:`rgb(${Math.round(t*255)},${Math.round(n*255)},${Math.round(r*255)})`}offsetHSL(e,t,n){return this.getHSL(Wn),this.setHSL(Wn.h+e,Wn.s+t,Wn.l+n)}add(e){return this.r+=e.r,this.g+=e.g,this.b+=e.b,this}addColors(e,t){return this.r=e.r+t.r,this.g=e.g+t.g,this.b=e.b+t.b,this}addScalar(e){return this.r+=e,this.g+=e,this.b+=e,this}sub(e){return this.r=Math.max(0,this.r-e.r),this.g=Math.max(0,this.g-e.g),this.b=Math.max(0,this.b-e.b),this}multiply(e){return this.r*=e.r,this.g*=e.g,this.b*=e.b,this}multiplyScalar(e){return this.r*=e,this.g*=e,this.b*=e,this}lerp(e,t){return this.r+=(e.r-this.r)*t,this.g+=(e.g-this.g)*t,this.b+=(e.b-this.b)*t,this}lerpColors(e,t,n){return this.r=e.r+(t.r-e.r)*n,this.g=e.g+(t.g-e.g)*n,this.b=e.b+(t.b-e.b)*n,this}lerpHSL(e,t){this.getHSL(Wn),e.getHSL(zo);let n=fa(Wn.h,zo.h,t),r=fa(Wn.s,zo.s,t),s=fa(Wn.l,zo.l,t);return this.setHSL(n,r,s),this}setFromVector3(e){return this.r=e.x,this.g=e.y,this.b=e.z,this}applyMatrix3(e){let t=this.r,n=this.g,r=this.b,s=e.elements;return this.r=s[0]*t+s[3]*n+s[6]*r,this.g=s[1]*t+s[4]*n+s[7]*r,this.b=s[2]*t+s[5]*n+s[8]*r,this}equals(e){return e.r===this.r&&e.g===this.g&&e.b===this.b}fromArray(e,t=0){return this.r=e[t],this.g=e[t+1],this.b=e[t+2],this}toArray(e=[],t=0){return e[t]=this.r,e[t+1]=this.g,e[t+2]=this.b,e}fromBufferAttribute(e,t){return this.r=e.getX(t),this.g=e.getY(t),this.b=e.getZ(t),this}toJSON(){return this.getHex()}*[Symbol.iterator](){yield this.r,yield this.g,yield this.b}},ni=new Ie;Ie.NAMES=Km;var xa=class extends Tt{constructor(){super(),this.isScene=!0,this.type="Scene",this.background=null,this.environment=null,this.fog=null,this.backgroundBlurriness=0,this.backgroundIntensity=1,this.backgroundRotation=new Di,this.environmentIntensity=1,this.environmentRotation=new Di,this.overrideMaterial=null,typeof __THREE_DEVTOOLS__<"u"&&__THREE_DEVTOOLS__.dispatchEvent(new CustomEvent("observe",{detail:this}))}copy(e,t){return super.copy(e,t),e.background!==null&&(this.background=e.background.clone()),e.environment!==null&&(this.environment=e.environment.clone()),e.fog!==null&&(this.fog=e.fog.clone()),this.backgroundBlurriness=e.backgroundBlurriness,this.backgroundIntensity=e.backgroundIntensity,this.backgroundRotation.copy(e.backgroundRotation),this.environmentIntensity=e.environmentIntensity,this.environmentRotation.copy(e.environmentRotation),e.overrideMaterial!==null&&(this.overrideMaterial=e.overrideMaterial.clone()),this.matrixAutoUpdate=e.matrixAutoUpdate,this}toJSON(e){let t=super.toJSON(e);return this.fog!==null&&(t.object.fog=this.fog.toJSON()),t.object.backgroundBlurriness=this.backgroundBlurriness,t.object.backgroundIntensity=this.backgroundIntensity,t.object.backgroundRotation=this.backgroundRotation.toArray(),t.object.environmentIntensity=this.environmentIntensity,t.object.environmentRotation=this.environmentRotation.toArray(),t}},Bi=new P,gn=new P,Yh=new P,yn=new P,as=new P,os=new P,Hp=new P,$h=new P,Zh=new P,Kh=new P,Jh=new Xe,Qh=new Xe,eu=new Xe,Vi=class i{constructor(e=new P,t=new P,n=new P){this.a=e,this.b=t,this.c=n}static getNormal(e,t,n,r){r.subVectors(n,t),Bi.subVectors(e,t),r.cross(Bi);let s=r.lengthSq();return s>0?r.multiplyScalar(1/Math.sqrt(s)):r.set(0,0,0)}static getBarycoord(e,t,n,r,s){Bi.subVectors(r,t),gn.subVectors(n,t),Yh.subVectors(e,t);let a=Bi.dot(Bi),o=Bi.dot(gn),l=Bi.dot(Yh),c=gn.dot(gn),h=gn.dot(Yh),u=a*c-o*o;if(u===0)return s.set(0,0,0),null;let d=1/u,f=(c*l-o*h)*d,p=(a*h-o*l)*d;return s.set(1-f-p,p,f)}static containsPoint(e,t,n,r){return this.getBarycoord(e,t,n,r,yn)===null?!1:yn.x>=0&&yn.y>=0&&yn.x+yn.y<=1}static getInterpolation(e,t,n,r,s,a,o,l){return this.getBarycoord(e,t,n,r,yn)===null?(l.x=0,l.y=0,"z"in l&&(l.z=0),"w"in l&&(l.w=0),null):(l.setScalar(0),l.addScaledVector(s,yn.x),l.addScaledVector(a,yn.y),l.addScaledVector(o,yn.z),l)}static getInterpolatedAttribute(e,t,n,r,s,a){return Jh.setScalar(0),Qh.setScalar(0),eu.setScalar(0),Jh.fromBufferAttribute(e,t),Qh.fromBufferAttribute(e,n),eu.fromBufferAttribute(e,r),a.setScalar(0),a.addScaledVector(Jh,s.x),a.addScaledVector(Qh,s.y),a.addScaledVector(eu,s.z),a}static isFrontFacing(e,t,n,r){return Bi.subVectors(n,t),gn.subVectors(e,t),Bi.cross(gn).dot(r)<0}set(e,t,n){return this.a.copy(e),this.b.copy(t),this.c.copy(n),this}setFromPointsAndIndices(e,t,n,r){return this.a.copy(e[t]),this.b.copy(e[n]),this.c.copy(e[r]),this}setFromAttributeAndIndices(e,t,n,r){return this.a.fromBufferAttribute(e,t),this.b.fromBufferAttribute(e,n),this.c.fromBufferAttribute(e,r),this}clone(){return new this.constructor().copy(this)}copy(e){return this.a.copy(e.a),this.b.copy(e.b),this.c.copy(e.c),this}getArea(){return Bi.subVectors(this.c,this.b),gn.subVectors(this.a,this.b),Bi.cross(gn).length()*.5}getMidpoint(e){return e.addVectors(this.a,this.b).add(this.c).multiplyScalar(1/3)}getNormal(e){return i.getNormal(this.a,this.b,this.c,e)}getPlane(e){return e.setFromCoplanarPoints(this.a,this.b,this.c)}getBarycoord(e,t){return i.getBarycoord(e,this.a,this.b,this.c,t)}getInterpolation(e,t,n,r,s){return i.getInterpolation(e,this.a,this.b,this.c,t,n,r,s)}containsPoint(e){return i.containsPoint(e,this.a,this.b,this.c)}isFrontFacing(e){return i.isFrontFacing(this.a,this.b,this.c,e)}intersectsBox(e){return e.intersectsTriangle(this)}closestPointToPoint(e,t){let n=this.a,r=this.b,s=this.c,a,o;as.subVectors(r,n),os.subVectors(s,n),$h.subVectors(e,n);let l=as.dot($h),c=os.dot($h);if(l<=0&&c<=0)return t.copy(n);Zh.subVectors(e,r);let h=as.dot(Zh),u=os.dot(Zh);if(h>=0&&u<=h)return t.copy(r);let d=l*u-h*c;if(d<=0&&l>=0&&h<=0)return a=l/(l-h),t.copy(n).addScaledVector(as,a);Kh.subVectors(e,s);let f=as.dot(Kh),p=os.dot(Kh);if(p>=0&&f<=p)return t.copy(s);let y=f*c-l*p;if(y<=0&&c>=0&&p<=0)return o=c/(c-p),t.copy(n).addScaledVector(os,o);let m=h*p-f*u;if(m<=0&&u-h>=0&&f-p>=0)return Hp.subVectors(s,r),o=(u-h)/(u-h+(f-p)),t.copy(r).addScaledVector(Hp,o);let g=1/(m+y+d);return a=y*g,o=d*g,t.copy(n).addScaledVector(as,a).addScaledVector(os,o)}equals(e){return e.a.equals(this.a)&&e.b.equals(this.b)&&e.c.equals(this.c)}},Mt=class{constructor(e=new P(1/0,1/0,1/0),t=new P(-1/0,-1/0,-1/0)){this.isBox3=!0,this.min=e,this.max=t}set(e,t){return this.min.copy(e),this.max.copy(t),this}setFromArray(e){this.makeEmpty();for(let t=0,n=e.length;t<n;t+=3)this.expandByPoint(ki.fromArray(e,t));return this}setFromBufferAttribute(e){this.makeEmpty();for(let t=0,n=e.count;t<n;t++)this.expandByPoint(ki.fromBufferAttribute(e,t));return this}setFromPoints(e){this.makeEmpty();for(let t=0,n=e.length;t<n;t++)this.expandByPoint(e[t]);return this}setFromCenterAndSize(e,t){let n=ki.copy(t).multiplyScalar(.5);return this.min.copy(e).sub(n),this.max.copy(e).add(n),this}setFromObject(e,t=!1){return this.makeEmpty(),this.expandByObject(e,t)}clone(){return new this.constructor().copy(this)}copy(e){return this.min.copy(e.min),this.max.copy(e.max),this}makeEmpty(){return this.min.x=this.min.y=this.min.z=1/0,this.max.x=this.max.y=this.max.z=-1/0,this}isEmpty(){return this.max.x<this.min.x||this.max.y<this.min.y||this.max.z<this.min.z}getCenter(e){return this.isEmpty()?e.set(0,0,0):e.addVectors(this.min,this.max).multiplyScalar(.5)}getSize(e){return this.isEmpty()?e.set(0,0,0):e.subVectors(this.max,this.min)}expandByPoint(e){return this.min.min(e),this.max.max(e),this}expandByVector(e){return this.min.sub(e),this.max.add(e),this}expandByScalar(e){return this.min.addScalar(-e),this.max.addScalar(e),this}expandByObject(e,t=!1){e.updateWorldMatrix(!1,!1);let n=e.geometry;if(n!==void 0){let s=n.getAttribute("position");if(t===!0&&s!==void 0&&e.isInstancedMesh!==!0)for(let a=0,o=s.count;a<o;a++)e.isMesh===!0?e.getVertexPosition(a,ki):ki.fromBufferAttribute(s,a),ki.applyMatrix4(e.matrixWorld),this.expandByPoint(ki);else e.boundingBox!==void 0?(e.boundingBox===null&&e.computeBoundingBox(),Vo.copy(e.boundingBox)):(n.boundingBox===null&&n.computeBoundingBox(),Vo.copy(n.boundingBox)),Vo.applyMatrix4(e.matrixWorld),this.union(Vo)}let r=e.children;for(let s=0,a=r.length;s<a;s++)this.expandByObject(r[s],t);return this}containsPoint(e){return e.x>=this.min.x&&e.x<=this.max.x&&e.y>=this.min.y&&e.y<=this.max.y&&e.z>=this.min.z&&e.z<=this.max.z}containsBox(e){return this.min.x<=e.min.x&&e.max.x<=this.max.x&&this.min.y<=e.min.y&&e.max.y<=this.max.y&&this.min.z<=e.min.z&&e.max.z<=this.max.z}getParameter(e,t){return t.set((e.x-this.min.x)/(this.max.x-this.min.x),(e.y-this.min.y)/(this.max.y-this.min.y),(e.z-this.min.z)/(this.max.z-this.min.z))}intersectsBox(e){return e.max.x>=this.min.x&&e.min.x<=this.max.x&&e.max.y>=this.min.y&&e.min.y<=this.max.y&&e.max.z>=this.min.z&&e.min.z<=this.max.z}intersectsSphere(e){return this.clampPoint(e.center,ki),ki.distanceToSquared(e.center)<=e.radius*e.radius}intersectsPlane(e){let t,n;return e.normal.x>0?(t=e.normal.x*this.min.x,n=e.normal.x*this.max.x):(t=e.normal.x*this.max.x,n=e.normal.x*this.min.x),e.normal.y>0?(t+=e.normal.y*this.min.y,n+=e.normal.y*this.max.y):(t+=e.normal.y*this.max.y,n+=e.normal.y*this.min.y),e.normal.z>0?(t+=e.normal.z*this.min.z,n+=e.normal.z*this.max.z):(t+=e.normal.z*this.max.z,n+=e.normal.z*this.min.z),t<=-e.constant&&n>=-e.constant}intersectsTriangle(e){if(this.isEmpty())return!1;this.getCenter(sa),Go.subVectors(this.max,sa),ls.subVectors(e.a,sa),cs.subVectors(e.b,sa),hs.subVectors(e.c,sa),Xn.subVectors(cs,ls),qn.subVectors(hs,cs),xr.subVectors(ls,hs);let t=[0,-Xn.z,Xn.y,0,-qn.z,qn.y,0,-xr.z,xr.y,Xn.z,0,-Xn.x,qn.z,0,-qn.x,xr.z,0,-xr.x,-Xn.y,Xn.x,0,-qn.y,qn.x,0,-xr.y,xr.x,0];return!tu(t,ls,cs,hs,Go)||(t=[1,0,0,0,1,0,0,0,1],!tu(t,ls,cs,hs,Go))?!1:(Ho.crossVectors(Xn,qn),t=[Ho.x,Ho.y,Ho.z],tu(t,ls,cs,hs,Go))}clampPoint(e,t){return t.copy(e).clamp(this.min,this.max)}distanceToPoint(e){return this.clampPoint(e,ki).distanceTo(e)}getBoundingSphere(e){return this.isEmpty()?e.makeEmpty():(this.getCenter(e.center),e.radius=this.getSize(ki).length()*.5),e}intersect(e){return this.min.max(e.min),this.max.min(e.max),this.isEmpty()&&this.makeEmpty(),this}union(e){return this.min.min(e.min),this.max.max(e.max),this}applyMatrix4(e){return this.isEmpty()?this:(_n[0].set(this.min.x,this.min.y,this.min.z).applyMatrix4(e),_n[1].set(this.min.x,this.min.y,this.max.z).applyMatrix4(e),_n[2].set(this.min.x,this.max.y,this.min.z).applyMatrix4(e),_n[3].set(this.min.x,this.max.y,this.max.z).applyMatrix4(e),_n[4].set(this.max.x,this.min.y,this.min.z).applyMatrix4(e),_n[5].set(this.max.x,this.min.y,this.max.z).applyMatrix4(e),_n[6].set(this.max.x,this.max.y,this.min.z).applyMatrix4(e),_n[7].set(this.max.x,this.max.y,this.max.z).applyMatrix4(e),this.setFromPoints(_n),this)}translate(e){return this.min.add(e),this.max.add(e),this}equals(e){return e.min.equals(this.min)&&e.max.equals(this.max)}toJSON(){return{min:this.min.toArray(),max:this.max.toArray()}}fromJSON(e){return this.min.fromArray(e.min),this.max.fromArray(e.max),this}},_n=[new P,new P,new P,new P,new P,new P,new P,new P],ki=new P,Vo=new Mt,ls=new P,cs=new P,hs=new P,Xn=new P,qn=new P,xr=new P,sa=new P,Go=new P,Ho=new P,vr=new P;function tu(i,e,t,n,r){for(let s=0,a=i.length-3;s<=a;s+=3){vr.fromArray(i,s);let o=r.x*Math.abs(vr.x)+r.y*Math.abs(vr.y)+r.z*Math.abs(vr.z),l=e.dot(vr),c=t.dot(vr),h=n.dot(vr);if(Math.max(-Math.max(l,c,h),Math.min(l,c,h))>o)return!1}return!0}var Ut=new P,Wo=new Se,Q_=0,Ye=class extends jt{constructor(e,t,n=!1){if(super(),Array.isArray(e))throw new TypeError("THREE.BufferAttribute: array should be a Typed Array.");this.isBufferAttribute=!0,Object.defineProperty(this,"id",{value:Q_++}),this.name="",this.array=e,this.itemSize=t,this.count=e!==void 0?e.length/t:0,this.normalized=n,this.usage=Yu,this.updateRanges=[],this.gpuType=fi,this.version=0}onUploadCallback(){}set needsUpdate(e){e===!0&&this.version++}setUsage(e){return this.usage=e,this}addUpdateRange(e,t){this.updateRanges.push({start:e,count:t})}clearUpdateRanges(){this.updateRanges.length=0}copy(e){return this.name=e.name,this.array=new e.array.constructor(e.array),this.itemSize=e.itemSize,this.count=e.count,this.normalized=e.normalized,this.usage=e.usage,this.gpuType=e.gpuType,this}copyAt(e,t,n){e*=this.itemSize,n*=t.itemSize;for(let r=0,s=this.itemSize;r<s;r++)this.array[e+r]=t.array[n+r];return this}copyArray(e){return this.array.set(e),this}applyMatrix3(e){if(this.itemSize===2)for(let t=0,n=this.count;t<n;t++)Wo.fromBufferAttribute(this,t),Wo.applyMatrix3(e),this.setXY(t,Wo.x,Wo.y);else if(this.itemSize===3)for(let t=0,n=this.count;t<n;t++)Ut.fromBufferAttribute(this,t),Ut.applyMatrix3(e),this.setXYZ(t,Ut.x,Ut.y,Ut.z);return this}applyMatrix4(e){for(let t=0,n=this.count;t<n;t++)Ut.fromBufferAttribute(this,t),Ut.applyMatrix4(e),this.setXYZ(t,Ut.x,Ut.y,Ut.z);return this}applyNormalMatrix(e){for(let t=0,n=this.count;t<n;t++)Ut.fromBufferAttribute(this,t),Ut.applyNormalMatrix(e),this.setXYZ(t,Ut.x,Ut.y,Ut.z);return this}transformDirection(e){for(let t=0,n=this.count;t<n;t++)Ut.fromBufferAttribute(this,t),Ut.transformDirection(e),this.setXYZ(t,Ut.x,Ut.y,Ut.z);return this}set(e,t=0){return this.array.set(e,t),this}getComponent(e,t){let n=this.array[e*this.itemSize+t];return this.normalized&&(n=zi(n,this.array)),n}setComponent(e,t,n){return this.normalized&&(n=ct(n,this.array)),this.array[e*this.itemSize+t]=n,this}getX(e){let t=this.array[e*this.itemSize];return this.normalized&&(t=zi(t,this.array)),t}setX(e,t){return this.normalized&&(t=ct(t,this.array)),this.array[e*this.itemSize]=t,this}getY(e){let t=this.array[e*this.itemSize+1];return this.normalized&&(t=zi(t,this.array)),t}setY(e,t){return this.normalized&&(t=ct(t,this.array)),this.array[e*this.itemSize+1]=t,this}getZ(e){let t=this.array[e*this.itemSize+2];return this.normalized&&(t=zi(t,this.array)),t}setZ(e,t){return this.normalized&&(t=ct(t,this.array)),this.array[e*this.itemSize+2]=t,this}getW(e){let t=this.array[e*this.itemSize+3];return this.normalized&&(t=zi(t,this.array)),t}setW(e,t){return this.normalized&&(t=ct(t,this.array)),this.array[e*this.itemSize+3]=t,this}setXY(e,t,n){return e*=this.itemSize,this.normalized&&(t=ct(t,this.array),n=ct(n,this.array)),this.array[e+0]=t,this.array[e+1]=n,this}setXYZ(e,t,n,r){return e*=this.itemSize,this.normalized&&(t=ct(t,this.array),n=ct(n,this.array),r=ct(r,this.array)),this.array[e+0]=t,this.array[e+1]=n,this.array[e+2]=r,this}setXYZW(e,t,n,r,s){return e*=this.itemSize,this.normalized&&(t=ct(t,this.array),n=ct(n,this.array),r=ct(r,this.array),s=ct(s,this.array)),this.array[e+0]=t,this.array[e+1]=n,this.array[e+2]=r,this.array[e+3]=s,this}onUpload(e){return this.onUploadCallback=e,this}clone(){return new this.constructor(this.array,this.itemSize).copy(this)}toJSON(){let e={itemSize:this.itemSize,type:this.array.constructor.name,array:Array.from(this.array),normalized:this.normalized};return e.name=this.name,e.usage=this.usage,e.gpuType=this.gpuType,e}dispose(){this.dispatchEvent({type:"dispose"})}};var va=class extends Ye{constructor(e,t,n){super(new Uint16Array(e),t,n)}};var ba=class extends Ye{constructor(e,t,n){super(new Uint32Array(e),t,n)}};var st=class extends Ye{constructor(e,t,n){super(new Float32Array(e),t,n)}},ex=new Mt,aa=new P,iu=new P,Et=class{constructor(e=new P,t=-1){this.isSphere=!0,this.center=e,this.radius=t}set(e,t){return this.center.copy(e),this.radius=t,this}setFromPoints(e,t){let n=this.center;t!==void 0?n.copy(t):ex.setFromPoints(e).getCenter(n);let r=0;for(let s=0,a=e.length;s<a;s++)r=Math.max(r,n.distanceToSquared(e[s]));return this.radius=Math.sqrt(r),this}copy(e){return this.center.copy(e.center),this.radius=e.radius,this}isEmpty(){return this.radius<0}makeEmpty(){return this.center.set(0,0,0),this.radius=-1,this}containsPoint(e){return e.distanceToSquared(this.center)<=this.radius*this.radius}distanceToPoint(e){return e.distanceTo(this.center)-this.radius}intersectsSphere(e){let t=this.radius+e.radius;return e.center.distanceToSquared(this.center)<=t*t}intersectsBox(e){return e.intersectsSphere(this)}intersectsPlane(e){return Math.abs(e.distanceToPoint(this.center))<=this.radius}clampPoint(e,t){let n=this.center.distanceToSquared(e);return t.copy(e),n>this.radius*this.radius&&(t.sub(this.center).normalize(),t.multiplyScalar(this.radius).add(this.center)),t}getBoundingBox(e){return this.isEmpty()?(e.makeEmpty(),e):(e.set(this.center,this.center),e.expandByScalar(this.radius),e)}applyMatrix4(e){return this.center.applyMatrix4(e),this.radius=this.radius*e.getMaxScaleOnAxis(),this}translate(e){return this.center.add(e),this}expandByPoint(e){if(this.isEmpty())return this.center.copy(e),this.radius=0,this;aa.subVectors(e,this.center);let t=aa.lengthSq();if(t>this.radius*this.radius){let n=Math.sqrt(t),r=(n-this.radius)*.5;this.center.addScaledVector(aa,r/n),this.radius+=r}return this}union(e){return e.isEmpty()?this:this.isEmpty()?(this.copy(e),this):(this.center.equals(e.center)===!0?this.radius=Math.max(this.radius,e.radius):(iu.subVectors(e.center,this.center).setLength(e.radius),this.expandByPoint(aa.copy(e.center).add(iu)),this.expandByPoint(aa.copy(e.center).sub(iu))),this)}equals(e){return e.center.equals(this.center)&&e.radius===this.radius}clone(){return new this.constructor().copy(this)}toJSON(){return{radius:this.radius,center:this.center.toArray()}}fromJSON(e){return this.radius=e.radius,this.center.fromArray(e.center),this}},tx=0,Ii=new ge,nu=new Tt,us=new P,Ai=new Mt,oa=new Mt,Wt=new P,ht=class i extends jt{constructor(){super(),this.isBufferGeometry=!0,Object.defineProperty(this,"id",{value:tx++}),this.uuid=Hi(),this.name="",this.type="BufferGeometry",this.index=null,this.indirect=null,this.indirectOffset=0,this.attributes={},this.morphAttributes={},this.morphTargetsRelative=!1,this.groups=[],this.boundingBox=null,this.boundingSphere=null,this.drawRange={start:0,count:1/0},this.userData={},this._transformed=!1}getIndex(){return this.index}setIndex(e){return Array.isArray(e)?this.index=new(T_(e)?ba:va)(e,1):this.index=e,this}setIndirect(e,t=0){return this.indirect=e,this.indirectOffset=t,this}getIndirect(){return this.indirect}getAttribute(e){return this.attributes[e]}setAttribute(e,t){return this.attributes[e]=t,this}deleteAttribute(e){return delete this.attributes[e],this}hasAttribute(e){return this.attributes[e]!==void 0}addGroup(e,t,n=0){this.groups.push({start:e,count:t,materialIndex:n})}clearGroups(){this.groups=[]}setDrawRange(e,t){this.drawRange.start=e,this.drawRange.count=t}applyMatrix4(e){let t=this.attributes.position;t!==void 0&&(t.applyMatrix4(e),t.needsUpdate=!0);let n=this.attributes.normal;if(n!==void 0){let s=new Oe().getNormalMatrix(e);n.applyNormalMatrix(s),n.needsUpdate=!0}let r=this.attributes.tangent;return r!==void 0&&(r.transformDirection(e),r.needsUpdate=!0),this.boundingBox!==null&&this.computeBoundingBox(),this.boundingSphere!==null&&this.computeBoundingSphere(),this._transformed=!0,this}applyQuaternion(e){return Ii.makeRotationFromQuaternion(e),this.applyMatrix4(Ii),this}rotateX(e){return Ii.makeRotationX(e),this.applyMatrix4(Ii),this}rotateY(e){return Ii.makeRotationY(e),this.applyMatrix4(Ii),this}rotateZ(e){return Ii.makeRotationZ(e),this.applyMatrix4(Ii),this}translate(e,t,n){return Ii.makeTranslation(e,t,n),this.applyMatrix4(Ii),this}scale(e,t,n){return Ii.makeScale(e,t,n),this.applyMatrix4(Ii),this}lookAt(e){return nu.lookAt(e),nu.updateMatrix(),this.applyMatrix4(nu.matrix),this}center(){return this.computeBoundingBox(),this.boundingBox.getCenter(us).negate(),this.translate(us.x,us.y,us.z),this}setFromPoints(e){let t=this.getAttribute("position");if(t===void 0){let n=[];for(let r=0,s=e.length;r<s;r++){let a=e[r];n.push(a.x,a.y,a.z||0)}this.setAttribute("position",new st(n,3))}else{let n=Math.min(e.length,t.count);for(let r=0;r<n;r++){let s=e[r];t.setXYZ(r,s.x,s.y,s.z||0)}e.length>t.count&&Ce("BufferGeometry: Buffer size too small for points data. Use .dispose() and create a new geometry."),t.needsUpdate=!0}return this}computeBoundingBox(){this.boundingBox===null&&(this.boundingBox=new Mt);let e=this.attributes.position,t=this.morphAttributes.position;if(e&&e.isGLBufferAttribute){Fe("BufferGeometry.computeBoundingBox(): GLBufferAttribute requires a manual bounding box.",this),this.boundingBox.set(new P(-1/0,-1/0,-1/0),new P(1/0,1/0,1/0));return}if(e!==void 0){if(this.boundingBox.setFromBufferAttribute(e),t)for(let n=0,r=t.length;n<r;n++){let s=t[n];Ai.setFromBufferAttribute(s),this.morphTargetsRelative?(Wt.addVectors(this.boundingBox.min,Ai.min),this.boundingBox.expandByPoint(Wt),Wt.addVectors(this.boundingBox.max,Ai.max),this.boundingBox.expandByPoint(Wt)):(this.boundingBox.expandByPoint(Ai.min),this.boundingBox.expandByPoint(Ai.max))}}else this.boundingBox.makeEmpty();(isNaN(this.boundingBox.min.x)||isNaN(this.boundingBox.min.y)||isNaN(this.boundingBox.min.z))&&Fe('BufferGeometry.computeBoundingBox(): Computed min/max have NaN values. The "position" attribute is likely to have NaN values.',this)}computeBoundingSphere(){this.boundingSphere===null&&(this.boundingSphere=new Et);let e=this.attributes.position,t=this.morphAttributes.position;if(e&&e.isGLBufferAttribute){Fe("BufferGeometry.computeBoundingSphere(): GLBufferAttribute requires a manual bounding sphere.",this),this.boundingSphere.set(new P,1/0);return}if(e){let n=this.boundingSphere.center;if(Ai.setFromBufferAttribute(e),t)for(let s=0,a=t.length;s<a;s++){let o=t[s];oa.setFromBufferAttribute(o),this.morphTargetsRelative?(Wt.addVectors(Ai.min,oa.min),Ai.expandByPoint(Wt),Wt.addVectors(Ai.max,oa.max),Ai.expandByPoint(Wt)):(Ai.expandByPoint(oa.min),Ai.expandByPoint(oa.max))}Ai.getCenter(n);let r=0;for(let s=0,a=e.count;s<a;s++)Wt.fromBufferAttribute(e,s),r=Math.max(r,n.distanceToSquared(Wt));if(t)for(let s=0,a=t.length;s<a;s++){let o=t[s],l=this.morphTargetsRelative;for(let c=0,h=o.count;c<h;c++)Wt.fromBufferAttribute(o,c),l&&(us.fromBufferAttribute(e,c),Wt.add(us)),r=Math.max(r,n.distanceToSquared(Wt))}this.boundingSphere.radius=Math.sqrt(r),isNaN(this.boundingSphere.radius)&&Fe('BufferGeometry.computeBoundingSphere(): Computed radius is NaN. The "position" attribute is likely to have NaN values.',this)}}computeTangents(){let e=this.index,t=this.attributes;if(e===null||t.position===void 0||t.normal===void 0||t.uv===void 0){Fe("BufferGeometry: .computeTangents() failed. Missing required attributes (index, position, normal or uv)");return}let n=t.position,r=t.normal,s=t.uv,a=this.getAttribute("tangent");(a===void 0||a.count!==n.count)&&(a=new Ye(new Float32Array(4*n.count),4),this.setAttribute("tangent",a));let o=[],l=[];for(let x=0;x<n.count;x++)o[x]=new P,l[x]=new P;let c=new P,h=new P,u=new P,d=new Se,f=new Se,p=new Se,y=new P,m=new P;function g(x,A,C){c.fromBufferAttribute(n,x),h.fromBufferAttribute(n,A),u.fromBufferAttribute(n,C),d.fromBufferAttribute(s,x),f.fromBufferAttribute(s,A),p.fromBufferAttribute(s,C),h.sub(c),u.sub(c),f.sub(d),p.sub(d);let D=1/(f.x*p.y-p.x*f.y);isFinite(D)&&(y.copy(h).multiplyScalar(p.y).addScaledVector(u,-f.y).multiplyScalar(D),m.copy(u).multiplyScalar(f.x).addScaledVector(h,-p.x).multiplyScalar(D),o[x].add(y),o[A].add(y),o[C].add(y),l[x].add(m),l[A].add(m),l[C].add(m))}let v=this.groups;v.length===0&&(v=[{start:0,count:e.count}]);for(let x=0,A=v.length;x<A;++x){let C=v[x],D=C.start,U=C.count;for(let I=D,L=D+U;I<L;I+=3)g(e.getX(I+0),e.getX(I+1),e.getX(I+2))}let S=new P,_=new P,M=new P,w=new P;function E(x){M.fromBufferAttribute(r,x),w.copy(M);let A=o[x];S.copy(A),S.sub(M.multiplyScalar(M.dot(A))).normalize(),_.crossVectors(w,A);let D=_.dot(l[x])<0?-1:1;a.setXYZW(x,S.x,S.y,S.z,D)}for(let x=0,A=v.length;x<A;++x){let C=v[x],D=C.start,U=C.count;for(let I=D,L=D+U;I<L;I+=3)E(e.getX(I+0)),E(e.getX(I+1)),E(e.getX(I+2))}this._transformed=!0}computeVertexNormals(){let e=this.index,t=this.getAttribute("position");if(t!==void 0){let n=this.getAttribute("normal");if(n===void 0||n.count!==t.count)n=new Ye(new Float32Array(t.count*3),3),this.setAttribute("normal",n);else for(let d=0,f=n.count;d<f;d++)n.setXYZ(d,0,0,0);let r=new P,s=new P,a=new P,o=new P,l=new P,c=new P,h=new P,u=new P;if(e)for(let d=0,f=e.count;d<f;d+=3){let p=e.getX(d+0),y=e.getX(d+1),m=e.getX(d+2);r.fromBufferAttribute(t,p),s.fromBufferAttribute(t,y),a.fromBufferAttribute(t,m),h.subVectors(a,s),u.subVectors(r,s),h.cross(u),o.fromBufferAttribute(n,p),l.fromBufferAttribute(n,y),c.fromBufferAttribute(n,m),o.add(h),l.add(h),c.add(h),n.setXYZ(p,o.x,o.y,o.z),n.setXYZ(y,l.x,l.y,l.z),n.setXYZ(m,c.x,c.y,c.z)}else for(let d=0,f=t.count;d<f;d+=3)r.fromBufferAttribute(t,d+0),s.fromBufferAttribute(t,d+1),a.fromBufferAttribute(t,d+2),h.subVectors(a,s),u.subVectors(r,s),h.cross(u),n.setXYZ(d+0,h.x,h.y,h.z),n.setXYZ(d+1,h.x,h.y,h.z),n.setXYZ(d+2,h.x,h.y,h.z);this.normalizeNormals(),n.needsUpdate=!0}}normalizeNormals(){let e=this.attributes.normal;for(let t=0,n=e.count;t<n;t++)Wt.fromBufferAttribute(e,t),Wt.normalize(),e.setXYZ(t,Wt.x,Wt.y,Wt.z)}toNonIndexed(){function e(o,l){let c=o.array,h=o.itemSize,u=o.normalized,d=new c.constructor(l.length*h),f=0,p=0;for(let y=0,m=l.length;y<m;y++){o.isInterleavedBufferAttribute?f=l[y]*o.data.stride+o.offset:f=l[y]*h;for(let g=0;g<h;g++)d[p++]=c[f++]}return new Ye(d,h,u)}if(this.index===null)return Ce("BufferGeometry.toNonIndexed(): BufferGeometry is already non-indexed."),this;let t=new i,n=this.index.array,r=this.attributes;for(let o in r){let l=r[o],c=e(l,n);t.setAttribute(o,c)}let s=this.morphAttributes;for(let o in s){let l=[],c=s[o];for(let h=0,u=c.length;h<u;h++){let d=c[h],f=e(d,n);l.push(f)}t.morphAttributes[o]=l}t.morphTargetsRelative=this.morphTargetsRelative;let a=this.groups;for(let o=0,l=a.length;o<l;o++){let c=a[o];t.addGroup(c.start,c.count,c.materialIndex)}return t}toJSON(){let e={metadata:{version:4.7,type:"BufferGeometry",generator:"BufferGeometry.toJSON"}};if(e.uuid=this.uuid,e.type=this.parameters!==void 0&&this._transformed===!0?"BufferGeometry":this.type,e.name=this.name,Object.keys(this.userData).length>0&&(e.userData=this.userData),this.parameters!==void 0&&this._transformed!==!0){let l=this.parameters;for(let c in l)l[c]!==void 0&&(e[c]=l[c]);return e}e.data={attributes:{}};let t=this.index;t!==null&&(e.data.index={type:t.array.constructor.name,array:Array.prototype.slice.call(t.array)});let n=this.attributes;for(let l in n){let c=n[l];e.data.attributes[l]=c.toJSON(e.data)}let r={},s=!1;for(let l in this.morphAttributes){let c=this.morphAttributes[l],h=[];for(let u=0,d=c.length;u<d;u++){let f=c[u];h.push(f.toJSON(e.data))}h.length>0&&(r[l]=h,s=!0)}s&&(e.data.morphAttributes=r,e.data.morphTargetsRelative=this.morphTargetsRelative);let a=this.groups;a.length>0&&(e.data.groups=JSON.parse(JSON.stringify(a)));let o=this.boundingSphere;return o!==null&&(e.data.boundingSphere=o.toJSON()),e}clone(){return new this.constructor().copy(this)}copy(e){this.index=null,this.attributes={},this.morphAttributes={},this.groups=[],this.boundingBox=null,this.boundingSphere=null;let t={};this.name=e.name;let n=e.index;n!==null&&this.setIndex(n.clone());let r=e.attributes;for(let c in r){let h=r[c];this.setAttribute(c,h.clone(t))}let s=e.morphAttributes;for(let c in s){let h=[],u=s[c];for(let d=0,f=u.length;d<f;d++)h.push(u[d].clone(t));this.morphAttributes[c]=h}this.morphTargetsRelative=e.morphTargetsRelative;let a=e.groups;for(let c=0,h=a.length;c<h;c++){let u=a[c];this.addGroup(u.start,u.count,u.materialIndex)}let o=e.boundingBox;o!==null&&(this.boundingBox=o.clone());let l=e.boundingSphere;return l!==null&&(this.boundingSphere=l.clone()),this.drawRange.start=e.drawRange.start,this.drawRange.count=e.drawRange.count,this.userData=e.userData,this._transformed=e._transformed,this}dispose(){this.dispatchEvent({type:"dispose"})}},Ar=class{constructor(e,t){this.isInterleavedBuffer=!0,this.array=e,this.stride=t,this.count=e!==void 0?e.length/t:0,this.usage=Yu,this.updateRanges=[],this.version=0,this.uuid=Hi()}onUploadCallback(){}set needsUpdate(e){e===!0&&this.version++}setUsage(e){return this.usage=e,this}addUpdateRange(e,t){this.updateRanges.push({start:e,count:t})}clearUpdateRanges(){this.updateRanges.length=0}copy(e){return this.array=new e.array.constructor(e.array),this.count=e.count,this.stride=e.stride,this.usage=e.usage,this}copyAt(e,t,n){e*=this.stride,n*=t.stride;for(let r=0,s=this.stride;r<s;r++)this.array[e+r]=t.array[n+r];return this}set(e,t=0){return this.array.set(e,t),this}clone(e){e.arrayBuffers===void 0&&(e.arrayBuffers={}),this.array.buffer._uuid===void 0&&(this.array.buffer._uuid=Hi()),e.arrayBuffers[this.array.buffer._uuid]===void 0&&(e.arrayBuffers[this.array.buffer._uuid]=this.array.slice(0).buffer);let t=new this.array.constructor(e.arrayBuffers[this.array.buffer._uuid]),n=new this.constructor(t,this.stride);return n.setUsage(this.usage),n}onUpload(e){return this.onUploadCallback=e,this}toJSON(e){e.arrayBuffers===void 0&&(e.arrayBuffers={}),this.array.buffer._uuid===void 0&&(this.array.buffer._uuid=Hi()),e.arrayBuffers[this.array.buffer._uuid]===void 0&&(e.arrayBuffers[this.array.buffer._uuid]=Array.from(new Uint32Array(this.array.buffer)));let t={uuid:this.uuid,buffer:this.array.buffer._uuid,type:this.array.constructor.name,stride:this.stride};return t.usage=this.usage,t}},oi=new P,xi=class i{constructor(e,t,n,r=!1){this.isInterleavedBufferAttribute=!0,this.name="",this.data=e,this.itemSize=t,this.offset=n,this.normalized=r}get count(){return this.data.count}get array(){return this.data.array}set needsUpdate(e){this.data.needsUpdate=e}applyMatrix4(e){for(let t=0,n=this.data.count;t<n;t++)oi.fromBufferAttribute(this,t),oi.applyMatrix4(e),this.setXYZ(t,oi.x,oi.y,oi.z);return this}applyNormalMatrix(e){for(let t=0,n=this.count;t<n;t++)oi.fromBufferAttribute(this,t),oi.applyNormalMatrix(e),this.setXYZ(t,oi.x,oi.y,oi.z);return this}transformDirection(e){for(let t=0,n=this.count;t<n;t++)oi.fromBufferAttribute(this,t),oi.transformDirection(e),this.setXYZ(t,oi.x,oi.y,oi.z);return this}getComponent(e,t){let n=this.array[e*this.data.stride+this.offset+t];return this.normalized&&(n=zi(n,this.array)),n}setComponent(e,t,n){return this.normalized&&(n=ct(n,this.array)),this.data.array[e*this.data.stride+this.offset+t]=n,this}setX(e,t){return this.normalized&&(t=ct(t,this.array)),this.data.array[e*this.data.stride+this.offset]=t,this}setY(e,t){return this.normalized&&(t=ct(t,this.array)),this.data.array[e*this.data.stride+this.offset+1]=t,this}setZ(e,t){return this.normalized&&(t=ct(t,this.array)),this.data.array[e*this.data.stride+this.offset+2]=t,this}setW(e,t){return this.normalized&&(t=ct(t,this.array)),this.data.array[e*this.data.stride+this.offset+3]=t,this}getX(e){let t=this.data.array[e*this.data.stride+this.offset];return this.normalized&&(t=zi(t,this.array)),t}getY(e){let t=this.data.array[e*this.data.stride+this.offset+1];return this.normalized&&(t=zi(t,this.array)),t}getZ(e){let t=this.data.array[e*this.data.stride+this.offset+2];return this.normalized&&(t=zi(t,this.array)),t}getW(e){let t=this.data.array[e*this.data.stride+this.offset+3];return this.normalized&&(t=zi(t,this.array)),t}setXY(e,t,n){return e=e*this.data.stride+this.offset,this.normalized&&(t=ct(t,this.array),n=ct(n,this.array)),this.data.array[e+0]=t,this.data.array[e+1]=n,this}setXYZ(e,t,n,r){return e=e*this.data.stride+this.offset,this.normalized&&(t=ct(t,this.array),n=ct(n,this.array),r=ct(r,this.array)),this.data.array[e+0]=t,this.data.array[e+1]=n,this.data.array[e+2]=r,this}setXYZW(e,t,n,r,s){return e=e*this.data.stride+this.offset,this.normalized&&(t=ct(t,this.array),n=ct(n,this.array),r=ct(r,this.array),s=ct(s,this.array)),this.data.array[e+0]=t,this.data.array[e+1]=n,this.data.array[e+2]=r,this.data.array[e+3]=s,this}clone(e){if(e===void 0){ga("InterleavedBufferAttribute.clone(): Cloning an interleaved buffer attribute will de-interleave buffer data.");let t=[];for(let n=0;n<this.count;n++){let r=n*this.data.stride+this.offset;for(let s=0;s<this.itemSize;s++)t.push(this.data.array[r+s])}return new Ye(new this.array.constructor(t),this.itemSize,this.normalized)}else return e.interleavedBuffers===void 0&&(e.interleavedBuffers={}),e.interleavedBuffers[this.data.uuid]===void 0&&(e.interleavedBuffers[this.data.uuid]=this.data.clone(e)),new i(e.interleavedBuffers[this.data.uuid],this.itemSize,this.offset,this.normalized)}toJSON(e){if(e===void 0){ga("InterleavedBufferAttribute.toJSON(): Serializing an interleaved buffer attribute will de-interleave buffer data.");let t=[];for(let n=0;n<this.count;n++){let r=n*this.data.stride+this.offset;for(let s=0;s<this.itemSize;s++)t.push(this.data.array[r+s])}return{itemSize:this.itemSize,type:this.array.constructor.name,array:t,normalized:this.normalized}}else return e.interleavedBuffers===void 0&&(e.interleavedBuffers={}),e.interleavedBuffers[this.data.uuid]===void 0&&(e.interleavedBuffers[this.data.uuid]=this.data.toJSON(e)),{isInterleavedBufferAttribute:!0,itemSize:this.itemSize,data:this.data.uuid,offset:this.offset,normalized:this.normalized}}},ru=new P,ix=new P,nx=new Oe,qt=class{constructor(e=new P(1,0,0),t=0){this.isPlane=!0,this.normal=e,this.constant=t}set(e,t){return this.normal.copy(e),this.constant=t,this}setComponents(e,t,n,r){return this.normal.set(e,t,n),this.constant=r,this}setFromNormalAndCoplanarPoint(e,t){return this.normal.copy(e),this.constant=-t.dot(this.normal),this}setFromCoplanarPoints(e,t,n){let r=ru.subVectors(n,t).cross(ix.subVectors(e,t)).normalize();return this.setFromNormalAndCoplanarPoint(r,e),this}copy(e){return this.normal.copy(e.normal),this.constant=e.constant,this}normalize(){let e=1/this.normal.length();return this.normal.multiplyScalar(e),this.constant*=e,this}negate(){return this.constant*=-1,this.normal.negate(),this}distanceToPoint(e){return this.normal.dot(e)+this.constant}distanceToSphere(e){return this.distanceToPoint(e.center)-e.radius}projectPoint(e,t){return t.copy(e).addScaledVector(this.normal,-this.distanceToPoint(e))}intersectLine(e,t,n=!0){let r=e.delta(ru),s=this.normal.dot(r);if(s===0)return this.distanceToPoint(e.start)===0?t.copy(e.start):null;let a=-(e.start.dot(this.normal)+this.constant)/s;return n===!0&&(a<0||a>1)?null:t.copy(e.start).addScaledVector(r,a)}intersectsLine(e){let t=this.distanceToPoint(e.start),n=this.distanceToPoint(e.end);return t<0&&n>0||n<0&&t>0}intersectsBox(e){return e.intersectsPlane(this)}intersectsSphere(e){return e.intersectsPlane(this)}coplanarPoint(e){return e.copy(this.normal).multiplyScalar(-this.constant)}applyMatrix4(e,t){let n=t||nx.getNormalMatrix(e),r=this.coplanarPoint(ru).applyMatrix4(e),s=this.normal.applyMatrix3(n).normalize();return this.constant=-r.dot(s),this}translate(e){return this.constant-=e.dot(this.normal),this}equals(e){return e.normal.equals(this.normal)&&e.constant===this.constant}clone(){return new this.constructor().copy(this)}toJSON(){return{normal:this.normal.toArray(),constant:this.constant}}fromJSON(e){return this.normal.fromArray(e.normal),this.constant=e.constant,this}},rx=0,hi=class extends jt{constructor(){super(),this.isMaterial=!0,Object.defineProperty(this,"id",{value:rx++}),this.uuid=Hi(),this.name="",this.type="Material",this.blending=Ls,this.side=sn,this.vertexColors=!1,this.opacity=1,this.transparent=!1,this.alphaHash=!1,this.blendSrc=Iu,this.blendDst=Lu,this.blendEquation=Br,this.blendSrcAlpha=null,this.blendDstAlpha=null,this.blendEquationAlpha=null,this.blendColor=new Ie(0,0,0),this.blendAlpha=0,this.depthFunc=xs,this.depthTest=!0,this.depthWrite=!0,this.stencilWriteMask=255,this.stencilFunc=zm,this.stencilRef=0,this.stencilFuncMask=255,this.stencilFail=ul,this.stencilZFail=ul,this.stencilZPass=ul,this.stencilWrite=!1,this.clippingPlanes=null,this.clipIntersection=!1,this.clipShadows=!1,this.shadowSide=null,this.colorWrite=!0,this.precision=null,this.polygonOffset=!1,this.polygonOffsetFactor=0,this.polygonOffsetUnits=0,this.dithering=!1,this.alphaToCoverage=!1,this.premultipliedAlpha=!1,this.forceSinglePass=!1,this.allowOverride=!0,this.visible=!0,this.toneMapped=!0,this.userData={},this.version=0,this._alphaTest=0}get alphaTest(){return this._alphaTest}set alphaTest(e){this._alphaTest>0!=e>0&&this.version++,this._alphaTest=e}onBeforeRender(){}onBeforeCompile(){}customProgramCacheKey(){return this.onBeforeCompile.toString()}setValues(e){if(e!==void 0)for(let t in e){let n=e[t];if(n===void 0){Ce(`Material: parameter '${t}' has value of undefined.`);continue}let r=this[t];if(r===void 0){Ce(`Material: '${t}' is not a property of THREE.${this.type}.`);continue}r&&r.isColor?r.set(n):r&&r.isVector2&&n&&n.isVector2||r&&r.isEuler&&n&&n.isEuler||r&&r.isVector3&&n&&n.isVector3?r.copy(n):this[t]=n}}toJSON(e){let t=e===void 0||typeof e=="string";t&&(e={textures:{},images:{}});let n={metadata:{version:4.7,type:"Material",generator:"Material.toJSON"}};n.uuid=this.uuid,n.type=this.type,n.blending=this.blending,n.side=this.side,n.shadowSide=this.shadowSide,n.vertexColors=this.vertexColors,n.opacity=this.opacity,n.transparent=this.transparent,n.blendSrc=this.blendSrc,n.blendDst=this.blendDst,n.blendEquation=this.blendEquation,n.blendSrcAlpha=this.blendSrcAlpha,n.blendDstAlpha=this.blendDstAlpha,n.blendEquationAlpha=this.blendEquationAlpha,n.blendColor=this.blendColor.getHex(),n.blendAlpha=this.blendAlpha,n.depthFunc=this.depthFunc,n.depthTest=this.depthTest,n.depthWrite=this.depthWrite,n.colorWrite=this.colorWrite,n.clipIntersection=this.clipIntersection,n.clipShadows=this.clipShadows,n.stencilWriteMask=this.stencilWriteMask,n.stencilFunc=this.stencilFunc,n.stencilRef=this.stencilRef,n.stencilFuncMask=this.stencilFuncMask,n.stencilFail=this.stencilFail,n.stencilZFail=this.stencilZFail,n.stencilZPass=this.stencilZPass,n.stencilWrite=this.stencilWrite,n.polygonOffset=this.polygonOffset,n.polygonOffsetFactor=this.polygonOffsetFactor,n.polygonOffsetUnits=this.polygonOffsetUnits,n.dithering=this.dithering,n.alphaTest=this.alphaTest,n.alphaHash=this.alphaHash,n.alphaToCoverage=this.alphaToCoverage,n.premultipliedAlpha=this.premultipliedAlpha,n.forceSinglePass=this.forceSinglePass,n.allowOverride=this.allowOverride,n.visible=this.visible,n.toneMapped=this.toneMapped,n.name=this.name,this.color&&this.color.isColor&&(n.color=this.color.getHex()),this.roughness!==void 0&&(n.roughness=this.roughness),this.metalness!==void 0&&(n.metalness=this.metalness),this.sheen!==void 0&&(n.sheen=this.sheen),this.sheenColor&&this.sheenColor.isColor&&(n.sheenColor=this.sheenColor.getHex()),this.sheenRoughness!==void 0&&(n.sheenRoughness=this.sheenRoughness),this.emissive&&this.emissive.isColor&&(n.emissive=this.emissive.getHex()),this.emissiveIntensity!==void 0&&(n.emissiveIntensity=this.emissiveIntensity),this.specular&&this.specular.isColor&&(n.specular=this.specular.getHex()),this.specularIntensity!==void 0&&(n.specularIntensity=this.specularIntensity),this.specularColor&&this.specularColor.isColor&&(n.specularColor=this.specularColor.getHex()),this.shininess!==void 0&&(n.shininess=this.shininess),this.clearcoat!==void 0&&(n.clearcoat=this.clearcoat),this.clearcoatRoughness!==void 0&&(n.clearcoatRoughness=this.clearcoatRoughness),this.clearcoatMap&&this.clearcoatMap.isTexture&&(n.clearcoatMap=this.clearcoatMap.toJSON(e).uuid),this.clearcoatRoughnessMap&&this.clearcoatRoughnessMap.isTexture&&(n.clearcoatRoughnessMap=this.clearcoatRoughnessMap.toJSON(e).uuid),this.clearcoatNormalMap&&this.clearcoatNormalMap.isTexture&&(n.clearcoatNormalMap=this.clearcoatNormalMap.toJSON(e).uuid,n.clearcoatNormalScale=this.clearcoatNormalScale.toArray()),this.sheenColorMap&&this.sheenColorMap.isTexture&&(n.sheenColorMap=this.sheenColorMap.toJSON(e).uuid),this.sheenRoughnessMap&&this.sheenRoughnessMap.isTexture&&(n.sheenRoughnessMap=this.sheenRoughnessMap.toJSON(e).uuid),this.dispersion!==void 0&&(n.dispersion=this.dispersion),this.retroreflectivity!==void 0&&(n.retroreflectivity=this.retroreflectivity),this.iridescence!==void 0&&(n.iridescence=this.iridescence),this.iridescenceIOR!==void 0&&(n.iridescenceIOR=this.iridescenceIOR),this.iridescenceThicknessRange!==void 0&&(n.iridescenceThicknessRange=this.iridescenceThicknessRange),this.iridescenceMap&&this.iridescenceMap.isTexture&&(n.iridescenceMap=this.iridescenceMap.toJSON(e).uuid),this.iridescenceThicknessMap&&this.iridescenceThicknessMap.isTexture&&(n.iridescenceThicknessMap=this.iridescenceThicknessMap.toJSON(e).uuid),this.anisotropy!==void 0&&(n.anisotropy=this.anisotropy),this.anisotropyRotation!==void 0&&(n.anisotropyRotation=this.anisotropyRotation),this.anisotropyMap&&this.anisotropyMap.isTexture&&(n.anisotropyMap=this.anisotropyMap.toJSON(e).uuid),this.map&&this.map.isTexture&&(n.map=this.map.toJSON(e).uuid),this.matcap&&this.matcap.isTexture&&(n.matcap=this.matcap.toJSON(e).uuid),this.alphaMap&&this.alphaMap.isTexture&&(n.alphaMap=this.alphaMap.toJSON(e).uuid),this.lightMap&&this.lightMap.isTexture&&(n.lightMap=this.lightMap.toJSON(e).uuid,n.lightMapIntensity=this.lightMapIntensity),this.aoMap&&this.aoMap.isTexture&&(n.aoMap=this.aoMap.toJSON(e).uuid,n.aoMapIntensity=this.aoMapIntensity),this.bumpMap&&this.bumpMap.isTexture&&(n.bumpMap=this.bumpMap.toJSON(e).uuid,n.bumpScale=this.bumpScale),this.normalMap&&this.normalMap.isTexture&&(n.normalMap=this.normalMap.toJSON(e).uuid,n.normalMapType=this.normalMapType,n.normalScale=this.normalScale.toArray()),this.displacementMap&&this.displacementMap.isTexture&&(n.displacementMap=this.displacementMap.toJSON(e).uuid,n.displacementScale=this.displacementScale,n.displacementBias=this.displacementBias),this.roughnessMap&&this.roughnessMap.isTexture&&(n.roughnessMap=this.roughnessMap.toJSON(e).uuid),this.metalnessMap&&this.metalnessMap.isTexture&&(n.metalnessMap=this.metalnessMap.toJSON(e).uuid),this.emissiveMap&&this.emissiveMap.isTexture&&(n.emissiveMap=this.emissiveMap.toJSON(e).uuid),this.specularMap&&this.specularMap.isTexture&&(n.specularMap=this.specularMap.toJSON(e).uuid),this.specularIntensityMap&&this.specularIntensityMap.isTexture&&(n.specularIntensityMap=this.specularIntensityMap.toJSON(e).uuid),this.specularColorMap&&this.specularColorMap.isTexture&&(n.specularColorMap=this.specularColorMap.toJSON(e).uuid),this.envMap&&this.envMap.isTexture&&(n.envMap=this.envMap.toJSON(e).uuid,this.combine!==void 0&&(n.combine=this.combine)),this.envMapRotation!==void 0&&(n.envMapRotation=this.envMapRotation.toArray()),this.envMapIntensity!==void 0&&(n.envMapIntensity=this.envMapIntensity),this.reflectivity!==void 0&&(n.reflectivity=this.reflectivity),this.refractionRatio!==void 0&&(n.refractionRatio=this.refractionRatio),this.gradientMap&&this.gradientMap.isTexture&&(n.gradientMap=this.gradientMap.toJSON(e).uuid),this.transmission!==void 0&&(n.transmission=this.transmission),this.transmissionMap&&this.transmissionMap.isTexture&&(n.transmissionMap=this.transmissionMap.toJSON(e).uuid),this.thickness!==void 0&&(n.thickness=this.thickness),this.thicknessMap&&this.thicknessMap.isTexture&&(n.thicknessMap=this.thicknessMap.toJSON(e).uuid),this.attenuationDistance!==void 0&&(n.attenuationDistance=this.attenuationDistance),this.attenuationColor!==void 0&&(n.attenuationColor=this.attenuationColor.getHex()),this.size!==void 0&&(n.size=this.size),this.sizeAttenuation!==void 0&&(n.sizeAttenuation=this.sizeAttenuation),Array.isArray(this.clippingPlanes)&&this.clippingPlanes.length>0&&(n.clippingPlanes=this.clippingPlanes.map(s=>s.toJSON())),this.rotation!==void 0&&(n.rotation=this.rotation),this.depthPacking!==void 0&&(n.depthPacking=this.depthPacking),this.linewidth!==void 0&&(n.linewidth=this.linewidth),this.linecap!==void 0&&(n.linecap=this.linecap),this.linejoin!==void 0&&(n.linejoin=this.linejoin),this.dashSize!==void 0&&(n.dashSize=this.dashSize),this.gapSize!==void 0&&(n.gapSize=this.gapSize),this.scale!==void 0&&(n.scale=this.scale),this.wireframe!==void 0&&(n.wireframe=this.wireframe),this.wireframeLinewidth!==void 0&&(n.wireframeLinewidth=this.wireframeLinewidth),this.wireframeLinecap!==void 0&&(n.wireframeLinecap=this.wireframeLinecap),this.wireframeLinejoin!==void 0&&(n.wireframeLinejoin=this.wireframeLinejoin),this.flatShading!==void 0&&(n.flatShading=this.flatShading),this.fog!==void 0&&(n.fog=this.fog),Object.keys(this.userData).length>0&&(n.userData=this.userData);function r(s){let a=[];for(let o in s){let l=s[o];delete l.metadata,a.push(l)}return a}if(t){let s=r(e.textures),a=r(e.images);s.length>0&&(n.textures=s),a.length>0&&(n.images=a)}return n}fromJSON(e,t){if(e.uuid!==void 0&&(this.uuid=e.uuid),e.name!==void 0&&(this.name=e.name),e.color!==void 0&&this.color!==void 0&&this.color.setHex(e.color),e.roughness!==void 0&&(this.roughness=e.roughness),e.metalness!==void 0&&(this.metalness=e.metalness),e.sheen!==void 0&&(this.sheen=e.sheen),e.sheenColor!==void 0&&(this.sheenColor=new Ie().setHex(e.sheenColor)),e.sheenRoughness!==void 0&&(this.sheenRoughness=e.sheenRoughness),e.emissive!==void 0&&this.emissive!==void 0&&this.emissive.setHex(e.emissive),e.specular!==void 0&&this.specular!==void 0&&this.specular.setHex(e.specular),e.specularIntensity!==void 0&&(this.specularIntensity=e.specularIntensity),e.specularColor!==void 0&&this.specularColor!==void 0&&this.specularColor.setHex(e.specularColor),e.shininess!==void 0&&(this.shininess=e.shininess),e.clearcoat!==void 0&&(this.clearcoat=e.clearcoat),e.clearcoatRoughness!==void 0&&(this.clearcoatRoughness=e.clearcoatRoughness),e.dispersion!==void 0&&(this.dispersion=e.dispersion),e.retroreflectivity!==void 0&&(this.retroreflectivity=e.retroreflectivity),e.iridescence!==void 0&&(this.iridescence=e.iridescence),e.iridescenceIOR!==void 0&&(this.iridescenceIOR=e.iridescenceIOR),e.iridescenceThicknessRange!==void 0&&(this.iridescenceThicknessRange=e.iridescenceThicknessRange),e.transmission!==void 0&&(this.transmission=e.transmission),e.thickness!==void 0&&(this.thickness=e.thickness),e.attenuationDistance!==void 0&&(this.attenuationDistance=e.attenuationDistance),e.attenuationColor!==void 0&&this.attenuationColor!==void 0&&this.attenuationColor.setHex(e.attenuationColor),e.anisotropy!==void 0&&(this.anisotropy=e.anisotropy),e.anisotropyRotation!==void 0&&(this.anisotropyRotation=e.anisotropyRotation),e.fog!==void 0&&(this.fog=e.fog),e.flatShading!==void 0&&(this.flatShading=e.flatShading),e.blending!==void 0&&(this.blending=e.blending),e.combine!==void 0&&(this.combine=e.combine),e.side!==void 0&&(this.side=e.side),e.shadowSide!==void 0&&(this.shadowSide=e.shadowSide),e.opacity!==void 0&&(this.opacity=e.opacity),e.transparent!==void 0&&(this.transparent=e.transparent),e.alphaTest!==void 0&&(this.alphaTest=e.alphaTest),e.alphaHash!==void 0&&(this.alphaHash=e.alphaHash),e.depthFunc!==void 0&&(this.depthFunc=e.depthFunc),e.depthTest!==void 0&&(this.depthTest=e.depthTest),e.depthWrite!==void 0&&(this.depthWrite=e.depthWrite),e.colorWrite!==void 0&&(this.colorWrite=e.colorWrite),e.clippingPlanes!==void 0&&(this.clippingPlanes=e.clippingPlanes.map(n=>new qt().fromJSON(n))),e.clipIntersection!==void 0&&(this.clipIntersection=e.clipIntersection),e.clipShadows!==void 0&&(this.clipShadows=e.clipShadows),e.depthPacking!==void 0&&(this.depthPacking=e.depthPacking),e.blendSrc!==void 0&&(this.blendSrc=e.blendSrc),e.blendDst!==void 0&&(this.blendDst=e.blendDst),e.blendEquation!==void 0&&(this.blendEquation=e.blendEquation),e.blendSrcAlpha!==void 0&&(this.blendSrcAlpha=e.blendSrcAlpha),e.blendDstAlpha!==void 0&&(this.blendDstAlpha=e.blendDstAlpha),e.blendEquationAlpha!==void 0&&(this.blendEquationAlpha=e.blendEquationAlpha),e.blendColor!==void 0&&this.blendColor!==void 0&&this.blendColor.setHex(e.blendColor),e.blendAlpha!==void 0&&(this.blendAlpha=e.blendAlpha),e.stencilWriteMask!==void 0&&(this.stencilWriteMask=e.stencilWriteMask),e.stencilFunc!==void 0&&(this.stencilFunc=e.stencilFunc),e.stencilRef!==void 0&&(this.stencilRef=e.stencilRef),e.stencilFuncMask!==void 0&&(this.stencilFuncMask=e.stencilFuncMask),e.stencilFail!==void 0&&(this.stencilFail=e.stencilFail),e.stencilZFail!==void 0&&(this.stencilZFail=e.stencilZFail),e.stencilZPass!==void 0&&(this.stencilZPass=e.stencilZPass),e.stencilWrite!==void 0&&(this.stencilWrite=e.stencilWrite),e.wireframe!==void 0&&(this.wireframe=e.wireframe),e.wireframeLinewidth!==void 0&&(this.wireframeLinewidth=e.wireframeLinewidth),e.wireframeLinecap!==void 0&&(this.wireframeLinecap=e.wireframeLinecap),e.wireframeLinejoin!==void 0&&(this.wireframeLinejoin=e.wireframeLinejoin),e.rotation!==void 0&&(this.rotation=e.rotation),e.linewidth!==void 0&&(this.linewidth=e.linewidth),e.linecap!==void 0&&(this.linecap=e.linecap),e.linejoin!==void 0&&(this.linejoin=e.linejoin),e.dashSize!==void 0&&(this.dashSize=e.dashSize),e.gapSize!==void 0&&(this.gapSize=e.gapSize),e.scale!==void 0&&(this.scale=e.scale),e.polygonOffset!==void 0&&(this.polygonOffset=e.polygonOffset),e.polygonOffsetFactor!==void 0&&(this.polygonOffsetFactor=e.polygonOffsetFactor),e.polygonOffsetUnits!==void 0&&(this.polygonOffsetUnits=e.polygonOffsetUnits),e.dithering!==void 0&&(this.dithering=e.dithering),e.alphaToCoverage!==void 0&&(this.alphaToCoverage=e.alphaToCoverage),e.premultipliedAlpha!==void 0&&(this.premultipliedAlpha=e.premultipliedAlpha),e.forceSinglePass!==void 0&&(this.forceSinglePass=e.forceSinglePass),e.allowOverride!==void 0&&(this.allowOverride=e.allowOverride),e.visible!==void 0&&(this.visible=e.visible),e.toneMapped!==void 0&&(this.toneMapped=e.toneMapped),e.userData!==void 0&&(this.userData=e.userData),e.vertexColors!==void 0&&(typeof e.vertexColors=="number"?this.vertexColors=e.vertexColors>0:this.vertexColors=e.vertexColors),e.size!==void 0&&(this.size=e.size),e.sizeAttenuation!==void 0&&(this.sizeAttenuation=e.sizeAttenuation),e.map!==void 0&&(this.map=t[e.map]||null),e.matcap!==void 0&&(this.matcap=t[e.matcap]||null),e.alphaMap!==void 0&&(this.alphaMap=t[e.alphaMap]||null),e.bumpMap!==void 0&&(this.bumpMap=t[e.bumpMap]||null),e.bumpScale!==void 0&&(this.bumpScale=e.bumpScale),e.normalMap!==void 0&&(this.normalMap=t[e.normalMap]||null),e.normalMapType!==void 0&&(this.normalMapType=e.normalMapType),e.normalScale!==void 0){let n=e.normalScale;Array.isArray(n)===!1&&(n=[n,n]),this.normalScale=new Se().fromArray(n)}return e.displacementMap!==void 0&&(this.displacementMap=t[e.displacementMap]||null),e.displacementScale!==void 0&&(this.displacementScale=e.displacementScale),e.displacementBias!==void 0&&(this.displacementBias=e.displacementBias),e.roughnessMap!==void 0&&(this.roughnessMap=t[e.roughnessMap]||null),e.metalnessMap!==void 0&&(this.metalnessMap=t[e.metalnessMap]||null),e.emissiveMap!==void 0&&(this.emissiveMap=t[e.emissiveMap]||null),e.emissiveIntensity!==void 0&&(this.emissiveIntensity=e.emissiveIntensity),e.specularMap!==void 0&&(this.specularMap=t[e.specularMap]||null),e.specularIntensityMap!==void 0&&(this.specularIntensityMap=t[e.specularIntensityMap]||null),e.specularColorMap!==void 0&&(this.specularColorMap=t[e.specularColorMap]||null),e.envMap!==void 0&&(this.envMap=t[e.envMap]||null),e.envMapRotation!==void 0&&this.envMapRotation.fromArray(e.envMapRotation),e.envMapIntensity!==void 0&&(this.envMapIntensity=e.envMapIntensity),e.reflectivity!==void 0&&(this.reflectivity=e.reflectivity),e.refractionRatio!==void 0&&(this.refractionRatio=e.refractionRatio),e.lightMap!==void 0&&(this.lightMap=t[e.lightMap]||null),e.lightMapIntensity!==void 0&&(this.lightMapIntensity=e.lightMapIntensity),e.aoMap!==void 0&&(this.aoMap=t[e.aoMap]||null),e.aoMapIntensity!==void 0&&(this.aoMapIntensity=e.aoMapIntensity),e.gradientMap!==void 0&&(this.gradientMap=t[e.gradientMap]||null),e.clearcoatMap!==void 0&&(this.clearcoatMap=t[e.clearcoatMap]||null),e.clearcoatRoughnessMap!==void 0&&(this.clearcoatRoughnessMap=t[e.clearcoatRoughnessMap]||null),e.clearcoatNormalMap!==void 0&&(this.clearcoatNormalMap=t[e.clearcoatNormalMap]||null),e.clearcoatNormalScale!==void 0&&(this.clearcoatNormalScale=new Se().fromArray(e.clearcoatNormalScale)),e.iridescenceMap!==void 0&&(this.iridescenceMap=t[e.iridescenceMap]||null),e.iridescenceThicknessMap!==void 0&&(this.iridescenceThicknessMap=t[e.iridescenceThicknessMap]||null),e.transmissionMap!==void 0&&(this.transmissionMap=t[e.transmissionMap]||null),e.thicknessMap!==void 0&&(this.thicknessMap=t[e.thicknessMap]||null),e.anisotropyMap!==void 0&&(this.anisotropyMap=t[e.anisotropyMap]||null),e.sheenColorMap!==void 0&&(this.sheenColorMap=t[e.sheenColorMap]||null),e.sheenRoughnessMap!==void 0&&(this.sheenRoughnessMap=t[e.sheenRoughnessMap]||null),this}clone(){return new this.constructor().copy(this)}copy(e){this.name=e.name,this.blending=e.blending,this.side=e.side,this.vertexColors=e.vertexColors,this.opacity=e.opacity,this.transparent=e.transparent,this.blendSrc=e.blendSrc,this.blendDst=e.blendDst,this.blendEquation=e.blendEquation,this.blendSrcAlpha=e.blendSrcAlpha,this.blendDstAlpha=e.blendDstAlpha,this.blendEquationAlpha=e.blendEquationAlpha,this.blendColor.copy(e.blendColor),this.blendAlpha=e.blendAlpha,this.depthFunc=e.depthFunc,this.depthTest=e.depthTest,this.depthWrite=e.depthWrite,this.stencilWriteMask=e.stencilWriteMask,this.stencilFunc=e.stencilFunc,this.stencilRef=e.stencilRef,this.stencilFuncMask=e.stencilFuncMask,this.stencilFail=e.stencilFail,this.stencilZFail=e.stencilZFail,this.stencilZPass=e.stencilZPass,this.stencilWrite=e.stencilWrite;let t=e.clippingPlanes,n=null;if(t!==null){let r=t.length;n=new Array(r);for(let s=0;s!==r;++s)n[s]=t[s].clone()}return this.clippingPlanes=n,this.clipIntersection=e.clipIntersection,this.clipShadows=e.clipShadows,this.shadowSide=e.shadowSide,this.colorWrite=e.colorWrite,this.precision=e.precision,this.polygonOffset=e.polygonOffset,this.polygonOffsetFactor=e.polygonOffsetFactor,this.polygonOffsetUnits=e.polygonOffsetUnits,this.dithering=e.dithering,this.alphaTest=e.alphaTest,this.alphaHash=e.alphaHash,this.alphaToCoverage=e.alphaToCoverage,this.premultipliedAlpha=e.premultipliedAlpha,this.forceSinglePass=e.forceSinglePass,this.allowOverride=e.allowOverride,this.visible=e.visible,this.toneMapped=e.toneMapped,this.userData=JSON.parse(JSON.stringify(e.userData)),this}dispose(){this.dispatchEvent({type:"dispose"})}set needsUpdate(e){e===!0&&this.version++}};var xn=new P,su=new P,Xo=new P,qo=new P,vi=class{constructor(e=new P,t=new P(0,0,-1)){this.origin=e,this.direction=t}set(e,t){return this.origin.copy(e),this.direction.copy(t),this}copy(e){return this.origin.copy(e.origin),this.direction.copy(e.direction),this}at(e,t){return t.copy(this.origin).addScaledVector(this.direction,e)}lookAt(e){return this.direction.copy(e).sub(this.origin).normalize(),this}recast(e){return this.origin.copy(this.at(e,xn)),this}closestPointToPoint(e,t){t.subVectors(e,this.origin);let n=t.dot(this.direction);return n<0?t.copy(this.origin):t.copy(this.origin).addScaledVector(this.direction,n)}distanceToPoint(e){return Math.sqrt(this.distanceSqToPoint(e))}distanceSqToPoint(e){let t=xn.subVectors(e,this.origin).dot(this.direction);return t<0?this.origin.distanceToSquared(e):(xn.copy(this.origin).addScaledVector(this.direction,t),xn.distanceToSquared(e))}distanceSqToSegment(e,t,n,r){su.copy(e).add(t).multiplyScalar(.5),Xo.copy(t).sub(e).normalize(),qo.copy(this.origin).sub(su);let s=e.distanceTo(t)*.5,a=-this.direction.dot(Xo),o=qo.dot(this.direction),l=-qo.dot(Xo),c=qo.lengthSq(),h=Math.abs(1-a*a),u,d,f,p;if(h>0)if(u=a*l-o,d=a*o-l,p=s*h,u>=0)if(d>=-p)if(d<=p){let y=1/h;u*=y,d*=y,f=u*(u+a*d+2*o)+d*(a*u+d+2*l)+c}else d=s,u=Math.max(0,-(a*d+o)),f=-u*u+d*(d+2*l)+c;else d=-s,u=Math.max(0,-(a*d+o)),f=-u*u+d*(d+2*l)+c;else d<=-p?(u=Math.max(0,-(-a*s+o)),d=u>0?-s:Math.min(Math.max(-s,-l),s),f=-u*u+d*(d+2*l)+c):d<=p?(u=0,d=Math.min(Math.max(-s,-l),s),f=d*(d+2*l)+c):(u=Math.max(0,-(a*s+o)),d=u>0?s:Math.min(Math.max(-s,-l),s),f=-u*u+d*(d+2*l)+c);else d=a>0?-s:s,u=Math.max(0,-(a*d+o)),f=-u*u+d*(d+2*l)+c;return n&&n.copy(this.origin).addScaledVector(this.direction,u),r&&r.copy(su).addScaledVector(Xo,d),f}intersectSphere(e,t){if(e.radius<0)return null;xn.subVectors(e.center,this.origin);let n=xn.dot(this.direction),r=xn.dot(xn)-n*n,s=e.radius*e.radius;if(r>s)return null;let a=Math.sqrt(s-r),o=n-a,l=n+a;return l<0?null:o<0?this.at(l,t):this.at(o,t)}intersectsSphere(e){return e.radius<0?!1:this.distanceSqToPoint(e.center)<=e.radius*e.radius}distanceToPlane(e){let t=e.normal.dot(this.direction);if(t===0)return e.distanceToPoint(this.origin)===0?0:null;let n=-(this.origin.dot(e.normal)+e.constant)/t;return n>=0?n:null}intersectPlane(e,t){let n=this.distanceToPlane(e);return n===null?null:this.at(n,t)}intersectsPlane(e){let t=e.distanceToPoint(this.origin);return t===0||e.normal.dot(this.direction)*t<0}intersectBox(e,t){let n,r,s,a,o,l,c=1/this.direction.x,h=1/this.direction.y,u=1/this.direction.z,d=this.origin;return c>=0?(n=(e.min.x-d.x)*c,r=(e.max.x-d.x)*c):(n=(e.max.x-d.x)*c,r=(e.min.x-d.x)*c),h>=0?(s=(e.min.y-d.y)*h,a=(e.max.y-d.y)*h):(s=(e.max.y-d.y)*h,a=(e.min.y-d.y)*h),n>a||s>r||((s>n||isNaN(n))&&(n=s),(a<r||isNaN(r))&&(r=a),u>=0?(o=(e.min.z-d.z)*u,l=(e.max.z-d.z)*u):(o=(e.max.z-d.z)*u,l=(e.min.z-d.z)*u),n>l||o>r)||((o>n||n!==n)&&(n=o),(l<r||r!==r)&&(r=l),r<0)?null:this.at(n>=0?n:r,t)}intersectsBox(e){return this.intersectBox(e,xn)!==null}intersectTriangle(e,t,n,r,s){let a=this.origin,o=this.direction,l=o.x,c=o.y,h=o.z,u=e.x-a.x,d=e.y-a.y,f=e.z-a.z,p=t.x-a.x,y=t.y-a.y,m=t.z-a.z,g=n.x-a.x,v=n.y-a.y,S=n.z-a.z,_=Math.abs(l),M=Math.abs(c),w=Math.abs(h),E,x,A,C,D,U,I,L,k,H,X,Y;if(_>=M&&_>=w?(A=l,U=u,k=p,Y=g,l>=0?(E=c,x=h,C=d,D=f,I=y,L=m,H=v,X=S):(E=h,x=c,C=f,D=d,I=m,L=y,H=S,X=v)):M>=w?(A=c,U=d,k=y,Y=v,c>=0?(E=h,x=l,C=f,D=u,I=m,L=p,H=S,X=g):(E=l,x=h,C=u,D=f,I=p,L=m,H=g,X=S)):(A=h,U=f,k=m,Y=S,h>=0?(E=l,x=c,C=u,D=d,I=p,L=y,H=g,X=v):(E=c,x=l,C=d,D=u,I=y,L=p,H=v,X=g)),A===0)return null;let q=E/A,K=x/A,N=1/A,ie=C-q*U,re=D-K*U,De=I-q*k,Te=L-K*k,$e=H-q*Y,$=X-K*Y,ee=$e*Te-$*De,_e=ie*$-re*$e,Be=De*re-Te*ie;if(r){if(ee<0||_e<0||Be<0)return null}else if((ee<0||_e<0||Be<0)&&(ee>0||_e>0||Be>0))return null;let xe=ee+_e+Be;if(xe===0)return null;let Ve=N*(ee*U+_e*k+Be*Y);return(xe>0?Ve<0:Ve>0)?null:this.at(Ve/xe,s)}applyMatrix4(e){return this.origin.applyMatrix4(e),this.direction.transformDirection(e),this}equals(e){return e.origin.equals(this.origin)&&e.direction.equals(this.direction)}clone(){return new this.constructor().copy(this)}},Yt=class extends hi{constructor(e){super(),this.isMeshBasicMaterial=!0,this.type="MeshBasicMaterial",this.color=new Ie(16777215),this.map=null,this.lightMap=null,this.lightMapIntensity=1,this.aoMap=null,this.aoMapIntensity=1,this.specularMap=null,this.alphaMap=null,this.envMap=null,this.envMapRotation=new Di,this.combine=Bl,this.reflectivity=1,this.refractionRatio=.98,this.wireframe=!1,this.wireframeLinewidth=1,this.wireframeLinecap="round",this.wireframeLinejoin="round",this.fog=!0,this.setValues(e)}copy(e){return super.copy(e),this.color.copy(e.color),this.map=e.map,this.lightMap=e.lightMap,this.lightMapIntensity=e.lightMapIntensity,this.aoMap=e.aoMap,this.aoMapIntensity=e.aoMapIntensity,this.specularMap=e.specularMap,this.alphaMap=e.alphaMap,this.envMap=e.envMap,this.envMapRotation.copy(e.envMapRotation),this.combine=e.combine,this.reflectivity=e.reflectivity,this.refractionRatio=e.refractionRatio,this.wireframe=e.wireframe,this.wireframeLinewidth=e.wireframeLinewidth,this.wireframeLinecap=e.wireframeLinecap,this.wireframeLinejoin=e.wireframeLinejoin,this.fog=e.fog,this}},Wp=new ge,br=new vi,jo=new Et,Xp=new P,Yo=new P,$o=new P,Zo=new P,au=new P,Ko=new P,qp=new P,Jo=new P,at=class extends Tt{constructor(e=new ht,t=new Yt){super(),this.isMesh=!0,this.type="Mesh",this.geometry=e,this.material=t,this.morphTargetDictionary=void 0,this.morphTargetInfluences=void 0,this.count=1,this.updateMorphTargets()}copy(e,t){return super.copy(e,t),e.morphTargetInfluences!==void 0&&(this.morphTargetInfluences=e.morphTargetInfluences.slice()),e.morphTargetDictionary!==void 0&&(this.morphTargetDictionary=Object.assign({},e.morphTargetDictionary)),this.material=Array.isArray(e.material)?e.material.slice():e.material,this.geometry=e.geometry,this}updateMorphTargets(){let t=this.geometry.morphAttributes,n=Object.keys(t);if(n.length>0){let r=t[n[0]];if(r!==void 0){this.morphTargetInfluences=[],this.morphTargetDictionary={};for(let s=0,a=r.length;s<a;s++){let o=r[s].name||String(s);this.morphTargetInfluences.push(0),this.morphTargetDictionary[o]=s}}}}getVertexPosition(e,t){let n=this.geometry,r=n.attributes.position,s=n.morphAttributes.position,a=n.morphTargetsRelative;t.fromBufferAttribute(r,e);let o=this.morphTargetInfluences;if(s&&o){Ko.set(0,0,0);for(let l=0,c=s.length;l<c;l++){let h=o[l],u=s[l];h!==0&&(au.fromBufferAttribute(u,e),a?Ko.addScaledVector(au,h):Ko.addScaledVector(au.sub(t),h))}t.add(Ko)}return t}intersectsFrustum(e){return e.intersectsObject(this)}raycast(e,t){let n=this.geometry,r=this.material,s=this.matrixWorld;r!==void 0&&(n.boundingSphere===null&&n.computeBoundingSphere(),jo.copy(n.boundingSphere),jo.applyMatrix4(s),br.copy(e.ray).recast(e.near),!(jo.containsPoint(br.origin)===!1&&(br.intersectSphere(jo,Xp)===null||br.origin.distanceToSquared(Xp)>(e.far-e.near)**2))&&(Wp.copy(s).invert(),br.copy(e.ray).applyMatrix4(Wp),!(n.boundingBox!==null&&br.intersectsBox(n.boundingBox)===!1)&&this._computeIntersections(e,t,br)))}_computeIntersections(e,t,n){let r,s=this.geometry,a=this.material,o=s.index,l=s.attributes.position,c=s.attributes.uv,h=s.attributes.uv1,u=s.attributes.normal,d=s.groups,f=s.drawRange;if(o!==null)if(Array.isArray(a))for(let p=0,y=d.length;p<y;p++){let m=d[p],g=a[m.materialIndex],v=Math.max(m.start,f.start),S=Math.min(o.count,Math.min(m.start+m.count,f.start+f.count));for(let _=v,M=S;_<M;_+=3){let w=o.getX(_),E=o.getX(_+1),x=o.getX(_+2);r=Qo(this,g,e,n,c,h,u,w,E,x),r&&(r.faceIndex=Math.floor(_/3),r.face.materialIndex=m.materialIndex,t.push(r))}}else{let p=Math.max(0,f.start),y=Math.min(o.count,f.start+f.count);for(let m=p,g=y;m<g;m+=3){let v=o.getX(m),S=o.getX(m+1),_=o.getX(m+2);r=Qo(this,a,e,n,c,h,u,v,S,_),r&&(r.faceIndex=Math.floor(m/3),t.push(r))}}else if(l!==void 0)if(Array.isArray(a))for(let p=0,y=d.length;p<y;p++){let m=d[p],g=a[m.materialIndex],v=Math.max(m.start,f.start),S=Math.min(l.count,Math.min(m.start+m.count,f.start+f.count));for(let _=v,M=S;_<M;_+=3){let w=_,E=_+1,x=_+2;r=Qo(this,g,e,n,c,h,u,w,E,x),r&&(r.faceIndex=Math.floor(_/3),r.face.materialIndex=m.materialIndex,t.push(r))}}else{let p=Math.max(0,f.start),y=Math.min(l.count,f.start+f.count);for(let m=p,g=y;m<g;m+=3){let v=m,S=m+1,_=m+2;r=Qo(this,a,e,n,c,h,u,v,S,_),r&&(r.faceIndex=Math.floor(m/3),t.push(r))}}}};function sx(i,e,t,n,r,s,a,o){let l;if(e.side===ui?l=n.intersectTriangle(a,s,r,!0,o):l=n.intersectTriangle(r,s,a,e.side===sn,o),l===null)return null;Jo.copy(o),Jo.applyMatrix4(i.matrixWorld);let c=t.ray.origin.distanceTo(Jo);return c<t.near||c>t.far?null:{distance:c,point:Jo.clone(),object:i}}function Qo(i,e,t,n,r,s,a,o,l,c){i.getVertexPosition(o,Yo),i.getVertexPosition(l,$o),i.getVertexPosition(c,Zo);let h=sx(i,e,t,n,Yo,$o,Zo,qp);if(h){let u=new P;Vi.getBarycoord(qp,Yo,$o,Zo,u),r&&(h.uv=Vi.getInterpolatedAttribute(r,o,l,c,u,new Se)),s&&(h.uv1=Vi.getInterpolatedAttribute(s,o,l,c,u,new Se)),a&&(h.normal=Vi.getInterpolatedAttribute(a,o,l,c,u,new P),h.normal.dot(n.direction)>0&&h.normal.multiplyScalar(-1));let d={a:o,b:l,c,normal:new P,materialIndex:0};Vi.getNormal(Yo,$o,Zo,d.normal),h.face=d,h.barycoord=u}return h}var la=new Xe,jp=new Xe,Yp=new Xe,ax=new Xe,$p=new ge,el=new P,ou=new Et,Zp=new ge,lu=new vi,Sa=class extends at{constructor(e,t){super(e,t),this.isSkinnedMesh=!0,this.type="SkinnedMesh",this.bindMode=fu,this.bindMatrix=new ge,this.bindMatrixInverse=new ge,this.boundingBox=null,this.boundingSphere=null}computeBoundingBox(){let e=this.geometry;this.boundingBox===null&&(this.boundingBox=new Mt),this.boundingBox.makeEmpty();let t=e.getAttribute("position");for(let n=0;n<t.count;n++)this.getVertexPosition(n,el),this.boundingBox.expandByPoint(el)}computeBoundingSphere(){let e=this.geometry;this.boundingSphere===null&&(this.boundingSphere=new Et),this.boundingSphere.makeEmpty();let t=e.getAttribute("position");for(let n=0;n<t.count;n++)this.getVertexPosition(n,el),this.boundingSphere.expandByPoint(el)}copy(e,t){return super.copy(e,t),this.bindMode=e.bindMode,this.bindMatrix.copy(e.bindMatrix),this.bindMatrixInverse.copy(e.bindMatrixInverse),this.skeleton=e.skeleton,e.boundingBox!==null&&(this.boundingBox=e.boundingBox.clone()),e.boundingSphere!==null&&(this.boundingSphere=e.boundingSphere.clone()),this}raycast(e,t){let n=this.material,r=this.matrixWorld;n!==void 0&&(this.boundingSphere===null&&this.computeBoundingSphere(),ou.copy(this.boundingSphere),ou.applyMatrix4(r),e.ray.intersectsSphere(ou)!==!1&&(Zp.copy(r).invert(),lu.copy(e.ray).applyMatrix4(Zp),!(this.boundingBox!==null&&lu.intersectsBox(this.boundingBox)===!1)&&this._computeIntersections(e,t,lu)))}getVertexPosition(e,t){return super.getVertexPosition(e,t),this.applyBoneTransform(e,t),t}bind(e,t){this.skeleton=e,t===void 0&&(this.updateMatrixWorld(!0),this.skeleton.calculateInverses(),t=this.matrixWorld),this.bindMatrix.copy(t),this.bindMatrixInverse.copy(t).invert()}pose(){this.skeleton.pose()}normalizeSkinWeights(){let e=new Xe,t=this.geometry.attributes.skinWeight;for(let n=0,r=t.count;n<r;n++){e.fromBufferAttribute(t,n);let s=1/e.manhattanLength();s!==1/0?e.multiplyScalar(s):e.set(1,0,0,0),t.setXYZW(n,e.x,e.y,e.z,e.w)}}updateMatrixWorld(e){super.updateMatrixWorld(e),this.bindMode===fu?this.bindMatrixInverse.copy(this.matrixWorld).invert():this.bindMode===Om?this.bindMatrixInverse.copy(this.bindMatrix).invert():Ce("SkinnedMesh: Unrecognized bindMode: "+this.bindMode)}applyBoneTransform(e,t){let n=this.skeleton,r=this.geometry;jp.fromBufferAttribute(r.attributes.skinIndex,e),Yp.fromBufferAttribute(r.attributes.skinWeight,e),t.isVector4?(la.copy(t),t.set(0,0,0,0)):(la.set(...t,1),t.set(0,0,0)),la.applyMatrix4(this.bindMatrix);for(let s=0;s<4;s++){let a=Yp.getComponent(s);if(a!==0){let o=jp.getComponent(s);$p.multiplyMatrices(n.bones[o].matrixWorld,n.boneInverses[o]),t.addScaledVector(ax.copy(la).applyMatrix4($p),a)}}return t.isVector4&&(t.w=la.w),t.applyMatrix4(this.bindMatrixInverse)}},Es=class extends Tt{constructor(){super(),this.isBone=!0,this.type="Bone"}},Sn=class extends Pt{constructor(e=null,t=1,n=1,r,s,a,o,l,c=At,h=At,u,d){super(null,a,o,l,c,h,r,s,u,d),this.isDataTexture=!0,this.image={data:e,width:t,height:n},this.generateMipmaps=!1,this.flipY=!1,this.unpackAlignment=1}},Kp=new ge,ox=new ge,Ma=class i{constructor(e=[],t=[]){this.uuid=Hi(),this.bones=e.slice(0),this.boneInverses=t,this.boneMatrices=null,this.boneTexture=null,this.init()}init(){let e=this.bones,t=this.boneInverses;if(this.boneMatrices=new Float32Array(e.length*16),t.length===0)this.calculateInverses();else if(e.length!==t.length){Ce("Skeleton: Number of inverse bone matrices does not match amount of bones."),this.boneInverses=[];for(let n=0,r=this.bones.length;n<r;n++)this.boneInverses.push(new ge)}}calculateInverses(){this.boneInverses.length=0;for(let e=0,t=this.bones.length;e<t;e++){let n=new ge;this.bones[e]&&n.copy(this.bones[e].matrixWorld).invert(),this.boneInverses.push(n)}}pose(){for(let e=0,t=this.bones.length;e<t;e++){let n=this.bones[e];n&&n.matrixWorld.copy(this.boneInverses[e]).invert()}for(let e=0,t=this.bones.length;e<t;e++){let n=this.bones[e];n&&(n.parent&&n.parent.isBone?(n.matrix.copy(n.parent.matrixWorld).invert(),n.matrix.multiply(n.matrixWorld)):n.matrix.copy(n.matrixWorld),n.matrix.decompose(n.position,n.quaternion,n.scale))}}update(){let e=this.bones,t=this.boneInverses,n=this.boneMatrices,r=this.boneTexture;for(let s=0,a=e.length;s<a;s++){let o=e[s]?e[s].matrixWorld:ox;Kp.multiplyMatrices(o,t[s]),Kp.toArray(n,s*16)}r!==null&&(r.needsUpdate=!0)}clone(){return new i(this.bones,this.boneInverses)}computeBoneTexture(){let e=Math.sqrt(this.bones.length*4);e=Math.ceil(e/4)*4,e=Math.max(e,4);let t=new Float32Array(e*e*4);t.set(this.boneMatrices);let n=new Sn(t,e,e,Ri,fi);return n.needsUpdate=!0,this.boneMatrices=t,this.boneTexture=n,this}getBoneByName(e){for(let t=0,n=this.bones.length;t<n;t++){let r=this.bones[t];if(r.name===e)return r}}dispose(){this.boneTexture!==null&&(this.boneTexture.dispose(),this.boneTexture=null)}fromJSON(e,t){this.uuid=e.uuid;for(let n=0,r=e.bones.length;n<r;n++){let s=e.bones[n],a=t[s];a===void 0&&(Ce("Skeleton: No bone found with UUID:",s),a=new Es),this.bones.push(a),this.boneInverses.push(new ge().fromArray(e.boneInverses[n]))}return this.init(),this}toJSON(){let e={metadata:{version:4.7,type:"Skeleton",generator:"Skeleton.toJSON"},bones:[],boneInverses:[]};e.uuid=this.uuid;let t=this.bones,n=this.boneInverses;for(let r=0,s=t.length;r<s;r++){let a=t[r];e.bones.push(a.uuid);let o=n[r];e.boneInverses.push(o.toArray())}return e}},Mn=class extends Ye{constructor(e,t,n,r=1){super(e,t,n),this.isInstancedBufferAttribute=!0,this.meshPerAttribute=r}copy(e){return super.copy(e),this.meshPerAttribute=e.meshPerAttribute,this}toJSON(){let e=super.toJSON();return e.meshPerAttribute=this.meshPerAttribute,e.isInstancedBufferAttribute=!0,e}},ds=new ge,Jp=new ge,tl=[],Qp=new Mt,lx=new ge,ca=new at,ha=new Et,Cr=class extends at{constructor(e,t,n){super(e,t),this.isInstancedMesh=!0,this.instanceMatrix=new Mn(new Float32Array(n*16),16),this.instanceColor=null,this.morphTexture=null,this.count=n,this.boundingBox=null,this.boundingSphere=null;for(let r=0;r<n;r++)this.setMatrixAt(r,lx)}computeBoundingBox(){let e=this.geometry,t=this.count;this.boundingBox===null&&(this.boundingBox=new Mt),e.boundingBox===null&&e.computeBoundingBox(),this.boundingBox.makeEmpty();for(let n=0;n<t;n++)this.getMatrixAt(n,ds),Qp.copy(e.boundingBox).applyMatrix4(ds),this.boundingBox.union(Qp)}computeBoundingSphere(){let e=this.geometry,t=this.count;this.boundingSphere===null&&(this.boundingSphere=new Et),e.boundingSphere===null&&e.computeBoundingSphere(),this.boundingSphere.makeEmpty();for(let n=0;n<t;n++)this.getMatrixAt(n,ds),ha.copy(e.boundingSphere).applyMatrix4(ds),this.boundingSphere.union(ha)}copy(e,t){return super.copy(e,t),this.instanceMatrix.copy(e.instanceMatrix),e.morphTexture!==null&&(this.morphTexture=e.morphTexture.clone()),e.instanceColor!==null&&(this.instanceColor=e.instanceColor.clone()),this.count=e.count,e.boundingBox!==null&&(this.boundingBox=e.boundingBox.clone()),e.boundingSphere!==null&&(this.boundingSphere=e.boundingSphere.clone()),this}getColorAt(e,t){return this.instanceColor===null?t.setRGB(1,1,1):t.fromArray(this.instanceColor.array,e*3)}getMatrixAt(e,t){return t.fromArray(this.instanceMatrix.array,e*16)}getMorphAt(e,t){let n=t.morphTargetInfluences,r=this.morphTexture.source.data.data,s=n.length+1,a=e*s+1;for(let o=0;o<n.length;o++)n[o]=r[a+o]}raycast(e,t){let n=this.matrixWorld,r=this.count;if(ca.geometry=this.geometry,ca.material=this.material,ca.material!==void 0&&(this.boundingSphere===null&&this.computeBoundingSphere(),ha.copy(this.boundingSphere),ha.applyMatrix4(n),e.ray.intersectsSphere(ha)!==!1))for(let s=0;s<r;s++){this.getMatrixAt(s,ds),Jp.multiplyMatrices(n,ds),ca.matrixWorld=Jp,ca.raycast(e,tl);for(let a=0,o=tl.length;a<o;a++){let l=tl[a];l.instanceId=s,l.object=this,t.push(l)}tl.length=0}}setColorAt(e,t){return this.instanceColor===null&&(this.instanceColor=new Mn(new Float32Array(this.instanceMatrix.count*3).fill(1),3)),t.toArray(this.instanceColor.array,e*3),this}setMatrixAt(e,t){return t.toArray(this.instanceMatrix.array,e*16),this}setMorphAt(e,t){let n=t.morphTargetInfluences,r=n.length+1;this.morphTexture===null&&(this.morphTexture=new Sn(new Float32Array(r*this.count),r,this.count,Os,fi));let s=this.morphTexture.source.data.data,a=0;for(let c=0;c<n.length;c++)a+=n[c];let o=this.geometry.morphTargetsRelative?1:1-a,l=r*e;return s[l]=o,s.set(n,l+1),this}updateMorphTargets(){}dispose(){super.dispose(),this.morphTexture!==null&&(this.morphTexture.dispose(),this.morphTexture=null)}},Sr=new Et,cx=new Se(.5,.5),il=new P,wn=class{constructor(e=new qt,t=new qt,n=new qt,r=new qt,s=new qt,a=new qt){this.planes=[e,t,n,r,s,a]}set(e,t,n,r,s,a){let o=this.planes;return o[0].copy(e),o[1].copy(t),o[2].copy(n),o[3].copy(r),o[4].copy(s),o[5].copy(a),this}copy(e){let t=this.planes;for(let n=0;n<6;n++)t[n].copy(e.planes[n]);return this}setFromProjectionMatrix(e,t=Gi,n=!1){let r=this.planes,s=e.elements,a=s[0],o=s[1],l=s[2],c=s[3],h=s[4],u=s[5],d=s[6],f=s[7],p=s[8],y=s[9],m=s[10],g=s[11],v=s[12],S=s[13],_=s[14],M=s[15];if(r[0].setComponents(c-a,f-h,g-p,M-v).normalize(),r[1].setComponents(c+a,f+h,g+p,M+v).normalize(),r[2].setComponents(c+o,f+u,g+y,M+S).normalize(),r[3].setComponents(c-o,f-u,g-y,M-S).normalize(),n)r[4].setComponents(l,d,m,_).normalize(),r[5].setComponents(c-l,f-d,g-m,M-_).normalize();else if(r[4].setComponents(c-l,f-d,g-m,M-_).normalize(),t===Gi)r[5].setComponents(c+l,f+d,g+m,M+_).normalize();else if(t===bs)r[5].setComponents(l,d,m,_).normalize();else throw new Error("THREE.Frustum.setFromProjectionMatrix(): Invalid coordinate system: "+t);return this}intersectsObject(e){if(e.boundingSphere!==void 0)e.boundingSphere===null&&e.computeBoundingSphere(),Sr.copy(e.boundingSphere).applyMatrix4(e.matrixWorld);else{let t=e.geometry;t.boundingSphere===null&&t.computeBoundingSphere(),Sr.copy(t.boundingSphere).applyMatrix4(e.matrixWorld)}return this.intersectsSphere(Sr)}intersectsSprite(e){Sr.center.set(0,0,0);let t=cx.distanceTo(e.center);return Sr.radius=.7071067811865476+t,Sr.applyMatrix4(e.matrixWorld),this.intersectsSphere(Sr)}intersectsSphere(e){let t=this.planes,n=e.center,r=-e.radius;for(let s=0;s<6;s++)if(t[s].distanceToPoint(n)<r)return!1;return!0}intersectsBox(e){let t=this.planes;for(let n=0;n<6;n++){let r=t[n];if(il.x=r.normal.x>0?e.max.x:e.min.x,il.y=r.normal.y>0?e.max.y:e.min.y,il.z=r.normal.z>0?e.max.z:e.min.z,r.distanceToPoint(il)<0)return!1}return!0}containsPoint(e){let t=this.planes;for(let n=0;n<6;n++)if(t[n].distanceToPoint(e)<0)return!1;return!0}clone(){return new this.constructor().copy(this)}};var Rr=class extends hi{constructor(e){super(),this.isLineBasicMaterial=!0,this.type="LineBasicMaterial",this.color=new Ie(16777215),this.map=null,this.linewidth=1,this.linecap="round",this.linejoin="round",this.fog=!0,this.setValues(e)}copy(e){return super.copy(e),this.color.copy(e.color),this.map=e.map,this.linewidth=e.linewidth,this.linecap=e.linecap,this.linejoin=e.linejoin,this.fog=e.fog,this}},Sl=new P,Ml=new P,em=new ge,ua=new vi,nl=new Et,cu=new P,tm=new P,Pr=class extends Tt{constructor(e=new ht,t=new Rr){super(),this.isLine=!0,this.type="Line",this.geometry=e,this.material=t,this.morphTargetDictionary=void 0,this.morphTargetInfluences=void 0,this.updateMorphTargets()}copy(e,t){return super.copy(e,t),this.material=Array.isArray(e.material)?e.material.slice():e.material,this.geometry=e.geometry,this}computeLineDistances(){let e=this.geometry;if(e.index===null){let t=e.attributes.position,n=[0];for(let r=1,s=t.count;r<s;r++)Sl.fromBufferAttribute(t,r-1),Ml.fromBufferAttribute(t,r),n[r]=n[r-1],n[r]+=Sl.distanceTo(Ml);e.setAttribute("lineDistance",new st(n,1))}else Ce("Line.computeLineDistances(): Computation only possible with non-indexed BufferGeometry.");return this}intersectsFrustum(e){return e.intersectsObject(this)}raycast(e,t){let n=this.geometry,r=this.matrixWorld,s=e.params.Line.threshold,a=n.drawRange;if(n.boundingSphere===null&&n.computeBoundingSphere(),nl.copy(n.boundingSphere),nl.applyMatrix4(r),nl.radius+=s,e.ray.intersectsSphere(nl)===!1)return;em.copy(r).invert(),ua.copy(e.ray).applyMatrix4(em);let o=s/((this.scale.x+this.scale.y+this.scale.z)/3),l=o*o,c=this.isLineSegments?2:1,h=n.index,d=n.attributes.position;if(h!==null){let f=Math.max(0,a.start),p=Math.min(h.count,a.start+a.count);for(let y=f,m=p-1;y<m;y+=c){let g=h.getX(y),v=h.getX(y+1),S=rl(this,e,ua,l,g,v,y);S&&t.push(S)}if(this.isLineLoop){let y=h.getX(p-1),m=h.getX(f),g=rl(this,e,ua,l,y,m,p-1);g&&t.push(g)}}else{let f=Math.max(0,a.start),p=Math.min(d.count,a.start+a.count);for(let y=f,m=p-1;y<m;y+=c){let g=rl(this,e,ua,l,y,y+1,y);g&&t.push(g)}if(this.isLineLoop){let y=rl(this,e,ua,l,p-1,f,p-1);y&&t.push(y)}}}updateMorphTargets(){let t=this.geometry.morphAttributes,n=Object.keys(t);if(n.length>0){let r=t[n[0]];if(r!==void 0){this.morphTargetInfluences=[],this.morphTargetDictionary={};for(let s=0,a=r.length;s<a;s++){let o=r[s].name||String(s);this.morphTargetInfluences.push(0),this.morphTargetDictionary[o]=s}}}}};function rl(i,e,t,n,r,s,a){let o=i.geometry.attributes.position;if(Sl.fromBufferAttribute(o,r),Ml.fromBufferAttribute(o,s),t.distanceSqToSegment(Sl,Ml,cu,tm)>n)return;cu.applyMatrix4(i.matrixWorld);let c=e.ray.origin.distanceTo(cu);if(!(c<e.near||c>e.far))return{distance:c,point:tm.clone().applyMatrix4(i.matrixWorld),index:a,face:null,faceIndex:null,barycoord:null,object:i}}var im=new P,nm=new P,As=class extends Pr{constructor(e,t){super(e,t),this.isLineSegments=!0,this.type="LineSegments"}computeLineDistances(){let e=this.geometry;if(e.index===null){let t=e.attributes.position,n=[];for(let r=0,s=t.count;r<s;r+=2)im.fromBufferAttribute(t,r),nm.fromBufferAttribute(t,r+1),n[r]=r===0?0:n[r-1],n[r+1]=n[r]+im.distanceTo(nm);e.setAttribute("lineDistance",new st(n,1))}else Ce("LineSegments.computeLineDistances(): Computation only possible with non-indexed BufferGeometry.");return this}},wa=class extends Pr{constructor(e,t){super(e,t),this.isLineLoop=!0,this.type="LineLoop"}},Tn=class extends hi{constructor(e){super(),this.isPointsMaterial=!0,this.type="PointsMaterial",this.color=new Ie(16777215),this.map=null,this.alphaMap=null,this.size=1,this.sizeAttenuation=!0,this.fog=!0,this.setValues(e)}copy(e){return super.copy(e),this.color.copy(e.color),this.map=e.map,this.alphaMap=e.alphaMap,this.size=e.size,this.sizeAttenuation=e.sizeAttenuation,this.fog=e.fog,this}},rm=new ge,_u=new vi,sl=new Et,al=new P,Zn=class extends Tt{constructor(e=new ht,t=new Tn){super(),this.isPoints=!0,this.type="Points",this.geometry=e,this.material=t,this.morphTargetDictionary=void 0,this.morphTargetInfluences=void 0,this.updateMorphTargets()}copy(e,t){return super.copy(e,t),this.material=Array.isArray(e.material)?e.material.slice():e.material,this.geometry=e.geometry,this}intersectsFrustum(e){return e.intersectsObject(this)}raycast(e,t){let n=this.geometry,r=this.matrixWorld,s=e.params.Points.threshold,a=n.drawRange;if(n.boundingSphere===null&&n.computeBoundingSphere(),sl.copy(n.boundingSphere),sl.applyMatrix4(r),sl.radius+=s,e.ray.intersectsSphere(sl)===!1)return;rm.copy(r).invert(),_u.copy(e.ray).applyMatrix4(rm);let o=s/((this.scale.x+this.scale.y+this.scale.z)/3),l=o*o,c=n.index,u=n.attributes.position;if(c!==null){let d=Math.max(0,a.start),f=Math.min(c.count,a.start+a.count);for(let p=d,y=f;p<y;p++){let m=c.getX(p);al.fromBufferAttribute(u,m),sm(al,m,l,r,e,t,this)}}else{let d=Math.max(0,a.start),f=Math.min(u.count,a.start+a.count);for(let p=d,y=f;p<y;p++)al.fromBufferAttribute(u,p),sm(al,p,l,r,e,t,this)}}updateMorphTargets(){let t=this.geometry.morphAttributes,n=Object.keys(t);if(n.length>0){let r=t[n[0]];if(r!==void 0){this.morphTargetInfluences=[],this.morphTargetDictionary={};for(let s=0,a=r.length;s<a;s++){let o=r[s].name||String(s);this.morphTargetInfluences.push(0),this.morphTargetDictionary[o]=s}}}}};function sm(i,e,t,n,r,s,a){let o=_u.distanceSqToPoint(i);if(o<t){let l=new P;_u.closestPointToPoint(i,l),l.applyMatrix4(n);let c=r.ray.origin.distanceTo(l);if(c<r.near||c>r.far)return;s.push({distance:c,distanceToRay:Math.sqrt(o),point:l,index:e,face:null,faceIndex:null,barycoord:null,object:a})}}var Ta=class extends Pt{constructor(e=[],t=sr,n,r,s,a,o,l,c,h){super(e,t,n,r,s,a,o,l,c,h),this.isCubeTexture=!0,this.flipY=!1}get images(){return this.image}set images(e){this.image=e}},Kn=class extends Pt{constructor(e,t,n,r,s,a,o,l,c){super(e,t,n,r,s,a,o,l,c),this.isCanvasTexture=!0,this.needsUpdate=!0}};var Jn=class extends Pt{constructor(e,t,n=qi,r,s,a,o=At,l=At,c,h=tn,u=1){if(h!==tn&&h!==ar)throw new Error("THREE.DepthTexture: format must be either THREE.DepthFormat or THREE.DepthStencilFormat");let d={width:e,height:t,depth:u};super(d,r,s,a,o,l,h,n,c),this.isDepthTexture=!0,this.flipY=!1,this.generateMipmaps=!1,this.compareFunction=null}copy(e){return super.copy(e),this.source=new ws(Object.assign({},e.image)),this.compareFunction=e.compareFunction,this}toJSON(e){let t=super.toJSON(e);return t.compareFunction=this.compareFunction,t}},wl=class extends Jn{constructor(e,t=qi,n=sr,r,s,a=At,o=At,l,c=tn){let h={width:e,height:e,depth:1},u=[h,h,h,h,h,h];super(e,e,t,n,r,s,a,o,l,c),this.image=u,this.isCubeDepthTexture=!0,this.isCubeTexture=!0}get images(){return this.image}set images(e){this.image=e}},Ea=class extends Pt{constructor(e=null){super(),this.sourceTexture=e,this.isExternalTexture=!0}copy(e){return super.copy(e),this.sourceTexture=e.sourceTexture,this}},Ir=class i extends ht{constructor(e=1,t=1,n=1,r=1,s=1,a=1){super(),this.type="BoxGeometry",this.parameters={width:e,height:t,depth:n,widthSegments:r,heightSegments:s,depthSegments:a};let o=this;r=Math.floor(r),s=Math.floor(s),a=Math.floor(a);let l=[],c=[],h=[],u=[],d=0,f=0;p("z","y","x",-1,-1,n,t,e,a,s,0),p("z","y","x",1,-1,n,t,-e,a,s,1),p("x","z","y",1,1,e,n,t,r,a,2),p("x","z","y",1,-1,e,n,-t,r,a,3),p("x","y","z",1,-1,e,t,n,r,s,4),p("x","y","z",-1,-1,e,t,-n,r,s,5),this.setIndex(l),this.setAttribute("position",new st(c,3)),this.setAttribute("normal",new st(h,3)),this.setAttribute("uv",new st(u,2));function p(y,m,g,v,S,_,M,w,E,x,A){let C=_/E,D=M/x,U=_/2,I=M/2,L=w/2,k=E+1,H=x+1,X=0,Y=0,q=new P;for(let K=0;K<H;K++){let N=K*D-I;for(let ie=0;ie<k;ie++){let re=ie*C-U;q[y]=re*v,q[m]=N*S,q[g]=L,c.push(q.x,q.y,q.z),q[y]=0,q[m]=0,q[g]=w>0?1:-1,h.push(q.x,q.y,q.z),u.push(ie/E),u.push(1-K/x),X+=1}}for(let K=0;K<x;K++)for(let N=0;N<E;N++){let ie=d+N+k*K,re=d+N+k*(K+1),De=d+(N+1)+k*(K+1),Te=d+(N+1)+k*K;l.push(ie,re,Te),l.push(re,De,Te),Y+=6}o.addGroup(f,Y,A),f+=Y,d+=X}}copy(e){return super.copy(e),this.parameters=Object.assign({},e.parameters),this}static fromJSON(e){return new i(e.width,e.height,e.depth,e.widthSegments,e.heightSegments,e.depthSegments)}},Lr=class i extends ht{constructor(e=1,t=1,n=4,r=8,s=1){super(),this.type="CapsuleGeometry",this.parameters={radius:e,height:t,capSegments:n,radialSegments:r,heightSegments:s},t=Math.max(0,t),n=Math.max(1,Math.floor(n)),r=Math.max(3,Math.floor(r)),s=Math.max(1,Math.floor(s));let a=[],o=[],l=[],c=[],h=t/2,u=Math.PI/2*e,d=t,f=2*u+d,p=n*2+s,y=r+1,m=new P,g=new P;for(let v=0;v<=p;v++){let S=0,_=0,M=0,w=0;if(v<=n){let A=v/n,C=A*Math.PI/2;_=-h-e*Math.cos(C),M=e*Math.sin(C),w=-e*Math.cos(C),S=A*u}else if(v<=n+s){let A=(v-n)/s;_=-h+A*t,M=e,w=0,S=u+A*d}else{let A=(v-n-s)/n,C=A*Math.PI/2;_=h+e*Math.sin(C),M=e*Math.cos(C),w=e*Math.sin(C),S=u+d+A*u}let E=Math.max(0,Math.min(1,S/f)),x=0;v===0?x=.5/r:v===p&&(x=-.5/r);for(let A=0;A<=r;A++){let C=A/r,D=C*Math.PI*2,U=Math.sin(D),I=Math.cos(D);g.x=-M*I,g.y=_,g.z=M*U,o.push(g.x,g.y,g.z),m.set(-M*I,w,M*U),m.normalize(),l.push(m.x,m.y,m.z),c.push(C+x,E)}if(v>0){let A=(v-1)*y;for(let C=0;C<r;C++){let D=A+C,U=A+C+1,I=v*y+C,L=v*y+C+1;a.push(D,U,I),a.push(U,L,I)}}}this.setIndex(a),this.setAttribute("position",new st(o,3)),this.setAttribute("normal",new st(l,3)),this.setAttribute("uv",new st(c,2))}copy(e){return super.copy(e),this.parameters=Object.assign({},e.parameters),this}static fromJSON(e){return new i(e.radius,e.height,e.capSegments,e.radialSegments,e.heightSegments)}};var Dr=class i extends ht{constructor(e=1,t=1,n=1,r=1){super(),this.type="PlaneGeometry",this.parameters={width:e,height:t,widthSegments:n,heightSegments:r};let s=e/2,a=t/2,o=Math.floor(n),l=Math.floor(r),c=o+1,h=l+1,u=e/o,d=t/l,f=[],p=[],y=[],m=[];for(let g=0;g<h;g++){let v=g*d-a;for(let S=0;S<c;S++){let _=S*u-s;p.push(_,-v,0),y.push(0,0,1),m.push(S/o),m.push(1-g/l)}}for(let g=0;g<l;g++)for(let v=0;v<o;v++){let S=v+c*g,_=v+c*(g+1),M=v+1+c*(g+1),w=v+1+c*g;f.push(S,_,w),f.push(_,M,w)}this.setIndex(f),this.setAttribute("position",new st(p,3)),this.setAttribute("normal",new st(y,3)),this.setAttribute("uv",new st(m,2))}copy(e){return super.copy(e),this.parameters=Object.assign({},e.parameters),this}static fromJSON(e){return new i(e.width,e.height,e.widthSegments,e.heightSegments)}};var Cs=class i extends ht{constructor(e=1,t=32,n=16,r=0,s=Math.PI*2,a=0,o=Math.PI){super(),this.type="SphereGeometry",this.parameters={radius:e,widthSegments:t,heightSegments:n,phiStart:r,phiLength:s,thetaStart:a,thetaLength:o},t=Math.max(3,Math.floor(t)),n=Math.max(2,Math.floor(n));let l=Math.min(a+o,Math.PI),c=0,h=[],u=new P,d=new P,f=[],p=[],y=[],m=[];for(let g=0;g<=n;g++){let v=[],S=g/n,_=a+S*o,M=e*Math.cos(_),w=Math.sqrt(e*e-M*M),E=0;g===0&&a===0?E=.5/t:g===n&&l===Math.PI&&(E=-.5/t);for(let x=0;x<=t;x++){let A=x/t,C=r+A*s;u.x=-w*Math.cos(C),u.y=M,u.z=w*Math.sin(C),p.push(u.x,u.y,u.z),d.copy(u).normalize(),y.push(d.x,d.y,d.z),m.push(A+E,1-S),v.push(c++)}h.push(v)}for(let g=0;g<n;g++)for(let v=0;v<t;v++){let S=h[g][v+1],_=h[g][v],M=h[g+1][v],w=h[g+1][v+1];(g!==0||a>0)&&f.push(S,_,w),(g!==n-1||l<Math.PI)&&f.push(_,M,w)}this.setIndex(f),this.setAttribute("position",new st(p,3)),this.setAttribute("normal",new st(y,3)),this.setAttribute("uv",new st(m,2))}copy(e){return super.copy(e),this.parameters=Object.assign({},e.parameters),this}static fromJSON(e){return new i(e.radius,e.widthSegments,e.heightSegments,e.phiStart,e.phiLength,e.thetaStart,e.thetaLength)}};var Aa=class extends ht{constructor(e=null){if(super(),this.type="WireframeGeometry",this.parameters={geometry:e},e!==null){let t=[],n=new Set,r=new P,s=new P;if(e.index!==null){let a=e.attributes.position,o=e.index,l=e.groups;l.length===0&&(l=[{start:0,count:o.count,materialIndex:0}]);for(let c=0,h=l.length;c<h;++c){let u=l[c],d=u.start,f=u.count;for(let p=d,y=d+f;p<y;p+=3)for(let m=0;m<3;m++){let g=o.getX(p+m),v=o.getX(p+(m+1)%3);r.fromBufferAttribute(a,g),s.fromBufferAttribute(a,v),am(r,s,n)===!0&&(t.push(r.x,r.y,r.z),t.push(s.x,s.y,s.z))}}}else{let a=e.attributes.position;for(let o=0,l=a.count/3;o<l;o++)for(let c=0;c<3;c++){let h=3*o+c,u=3*o+(c+1)%3;r.fromBufferAttribute(a,h),s.fromBufferAttribute(a,u),am(r,s,n)===!0&&(t.push(r.x,r.y,r.z),t.push(s.x,s.y,s.z))}}this.setAttribute("position",new st(t,3))}}copy(e){return super.copy(e),this.parameters=Object.assign({},e.parameters),this}};function am(i,e,t){let n=`${i.x},${i.y},${i.z}-${e.x},${e.y},${e.z}`,r=`${e.x},${e.y},${e.z}-${i.x},${i.y},${i.z}`;return t.has(n)===!0||t.has(r)===!0?!1:(t.add(n),t.add(r),!0)}function Vr(i){let e={};for(let t in i){e[t]={};for(let n in i[t]){let r=i[t][n];if(om(r))r.isRenderTargetTexture?(Ce("UniformsUtils: Textures of render targets cannot be cloned via cloneUniforms() or mergeUniforms()."),e[t][n]=null):e[t][n]=r.clone();else if(Array.isArray(r))if(om(r[0])){let s=[];for(let a=0,o=r.length;a<o;a++)s[a]=r[a].clone();e[t][n]=s}else e[t][n]=r.slice();else e[t][n]=r}}return e}function si(i){let e={};for(let t=0;t<i.length;t++){let n=Vr(i[t]);for(let r in n)e[r]=n[r]}return e}function om(i){return i&&(i.isColor||i.isMatrix3||i.isMatrix4||i.isVector2||i.isVector3||i.isVector4||i.isTexture||i.isQuaternion)}function hx(i){let e=[];for(let t=0;t<i.length;t++)e.push(i[t].clone());return e}function Ku(i){let e=i.getRenderTarget();return e===null?i.outputColorSpace:e.isXRRenderTarget===!0?e.texture.colorSpace:je.workingColorSpace}var Za={clone:Vr,merge:si},ux=`void main() {
	gl_Position = projectionMatrix * modelViewMatrix * vec4( position, 1.0 );
}`,dx=`void main() {
	gl_FragColor = vec4( 1.0, 0.0, 0.0, 1.0 );
}`,$t=class extends hi{constructor(e){super(),this.isShaderMaterial=!0,this.type="ShaderMaterial",this.defines={},this.uniforms={},this.uniformsGroups=[],this.vertexShader=ux,this.fragmentShader=dx,this.linewidth=1,this.wireframe=!1,this.wireframeLinewidth=1,this.fog=!1,this.lights=!1,this.clipping=!1,this.forceSinglePass=!0,this.extensions={clipCullDistance:!1,multiDraw:!1},this.defaultAttributeValues={color:[1,1,1],uv:[0,0],uv1:[0,0]},this.index0AttributeName=void 0,this.uniformsNeedUpdate=!1,this.glslVersion=null,e!==void 0&&this.setValues(e)}copy(e){return super.copy(e),this.fragmentShader=e.fragmentShader,this.vertexShader=e.vertexShader,this.uniforms=Vr(e.uniforms),this.uniformsGroups=hx(e.uniformsGroups),this.defines=Object.assign({},e.defines),this.wireframe=e.wireframe,this.wireframeLinewidth=e.wireframeLinewidth,this.fog=e.fog,this.lights=e.lights,this.clipping=e.clipping,this.extensions=Object.assign({},e.extensions),this.glslVersion=e.glslVersion,this.defaultAttributeValues=Object.assign({},e.defaultAttributeValues),this.index0AttributeName=e.index0AttributeName,this.uniformsNeedUpdate=e.uniformsNeedUpdate,this}toJSON(e){let t=super.toJSON(e);t.glslVersion=this.glslVersion,t.uniforms={};for(let r in this.uniforms){let a=this.uniforms[r].value;a&&a.isTexture?t.uniforms[r]={type:"t",value:a.toJSON(e).uuid}:a&&a.isColor?t.uniforms[r]={type:"c",value:a.getHex()}:a&&a.isVector2?t.uniforms[r]={type:"v2",value:a.toArray()}:a&&a.isVector3?t.uniforms[r]={type:"v3",value:a.toArray()}:a&&a.isVector4?t.uniforms[r]={type:"v4",value:a.toArray()}:a&&a.isMatrix3?t.uniforms[r]={type:"m3",value:a.toArray()}:a&&a.isMatrix4?t.uniforms[r]={type:"m4",value:a.toArray()}:t.uniforms[r]={value:a}}Object.keys(this.defines).length>0&&(t.defines=this.defines),t.vertexShader=this.vertexShader,t.fragmentShader=this.fragmentShader,t.lights=this.lights,t.clipping=this.clipping;let n={};for(let r in this.extensions)this.extensions[r]===!0&&(n[r]=!0);return Object.keys(n).length>0&&(t.extensions=n),t}fromJSON(e,t){if(super.fromJSON(e,t),e.uniforms!==void 0)for(let n in e.uniforms){let r=e.uniforms[n];switch(this.uniforms[n]={},r.type){case"t":this.uniforms[n].value=t[r.value]||null;break;case"c":this.uniforms[n].value=new Ie().setHex(r.value);break;case"v2":this.uniforms[n].value=new Se().fromArray(r.value);break;case"v3":this.uniforms[n].value=new P().fromArray(r.value);break;case"v4":this.uniforms[n].value=new Xe().fromArray(r.value);break;case"m3":this.uniforms[n].value=new Oe().fromArray(r.value);break;case"m4":this.uniforms[n].value=new ge().fromArray(r.value);break;default:this.uniforms[n].value=r.value}}if(e.defines!==void 0&&(this.defines=e.defines),e.vertexShader!==void 0&&(this.vertexShader=e.vertexShader),e.fragmentShader!==void 0&&(this.fragmentShader=e.fragmentShader),e.glslVersion!==void 0&&(this.glslVersion=e.glslVersion),e.extensions!==void 0)for(let n in e.extensions)this.extensions[n]=e.extensions[n];return e.lights!==void 0&&(this.lights=e.lights),e.clipping!==void 0&&(this.clipping=e.clipping),this}},Tl=class extends $t{constructor(e){super(e),this.isRawShaderMaterial=!0,this.type="RawShaderMaterial"}},Qn=class extends hi{constructor(e){super(),this.isMeshStandardMaterial=!0,this.type="MeshStandardMaterial",this.defines={STANDARD:""},this.color=new Ie(16777215),this.roughness=1,this.metalness=0,this.map=null,this.lightMap=null,this.lightMapIntensity=1,this.aoMap=null,this.aoMapIntensity=1,this.emissive=new Ie(0),this.emissiveIntensity=1,this.emissiveMap=null,this.bumpMap=null,this.bumpScale=1,this.normalMap=null,this.normalMapType=$a,this.normalScale=new Se(1,1),this.displacementMap=null,this.displacementScale=1,this.displacementBias=0,this.roughnessMap=null,this.metalnessMap=null,this.alphaMap=null,this.envMap=null,this.envMapRotation=new Di,this.envMapIntensity=1,this.wireframe=!1,this.wireframeLinewidth=1,this.wireframeLinecap="round",this.wireframeLinejoin="round",this.flatShading=!1,this.fog=!0,this.setValues(e)}copy(e){return super.copy(e),this.defines={STANDARD:""},this.color.copy(e.color),this.roughness=e.roughness,this.metalness=e.metalness,this.map=e.map,this.lightMap=e.lightMap,this.lightMapIntensity=e.lightMapIntensity,this.aoMap=e.aoMap,this.aoMapIntensity=e.aoMapIntensity,this.emissive.copy(e.emissive),this.emissiveMap=e.emissiveMap,this.emissiveIntensity=e.emissiveIntensity,this.bumpMap=e.bumpMap,this.bumpScale=e.bumpScale,this.normalMap=e.normalMap,this.normalMapType=e.normalMapType,this.normalScale.copy(e.normalScale),this.displacementMap=e.displacementMap,this.displacementScale=e.displacementScale,this.displacementBias=e.displacementBias,this.roughnessMap=e.roughnessMap,this.metalnessMap=e.metalnessMap,this.alphaMap=e.alphaMap,this.envMap=e.envMap,this.envMapRotation.copy(e.envMapRotation),this.envMapIntensity=e.envMapIntensity,this.wireframe=e.wireframe,this.wireframeLinewidth=e.wireframeLinewidth,this.wireframeLinecap=e.wireframeLinecap,this.wireframeLinejoin=e.wireframeLinejoin,this.flatShading=e.flatShading,this.fog=e.fog,this}},bi=class extends Qn{constructor(e){super(),this.isMeshPhysicalMaterial=!0,this.defines={STANDARD:"",PHYSICAL:""},this.type="MeshPhysicalMaterial",this.anisotropyRotation=0,this.anisotropyMap=null,this.clearcoatMap=null,this.clearcoatRoughness=0,this.clearcoatRoughnessMap=null,this.clearcoatNormalScale=new Se(1,1),this.clearcoatNormalMap=null,this.ior=1.5,Object.defineProperty(this,"reflectivity",{get:function(){return ze(2.5*(this.ior-1)/(this.ior+1),0,1)},set:function(t){this.ior=(1+.4*t)/(1-.4*t)}}),this.iridescenceMap=null,this.iridescenceIOR=1.3,this.iridescenceThicknessRange=[100,400],this.iridescenceThicknessMap=null,this.sheenColor=new Ie(0),this.sheenColorMap=null,this.sheenRoughness=1,this.sheenRoughnessMap=null,this.transmissionMap=null,this.thickness=0,this.thicknessMap=null,this.attenuationDistance=1/0,this.attenuationColor=new Ie(1,1,1),this.specularIntensity=1,this.specularIntensityMap=null,this.specularColor=new Ie(1,1,1),this.specularColorMap=null,this._anisotropy=0,this._clearcoat=0,this._dispersion=0,this._iridescence=0,this._retroreflectivity=0,this._sheen=0,this._transmission=0,this.setValues(e)}get anisotropy(){return this._anisotropy}set anisotropy(e){this._anisotropy>0!=e>0&&this.version++,this._anisotropy=e}get clearcoat(){return this._clearcoat}set clearcoat(e){this._clearcoat>0!=e>0&&this.version++,this._clearcoat=e}get iridescence(){return this._iridescence}set iridescence(e){this._iridescence>0!=e>0&&this.version++,this._iridescence=e}get dispersion(){return this._dispersion}set dispersion(e){this._dispersion>0!=e>0&&this.version++,this._dispersion=e}get retroreflectivity(){return this._retroreflectivity}set retroreflectivity(e){this._retroreflectivity>0!=e>0&&this.version++,this._retroreflectivity=e}get sheen(){return this._sheen}set sheen(e){this._sheen>0!=e>0&&this.version++,this._sheen=e}get transmission(){return this._transmission}set transmission(e){this._transmission>0!=e>0&&this.version++,this._transmission=e}copy(e){return super.copy(e),this.defines={STANDARD:"",PHYSICAL:""},this.anisotropy=e.anisotropy,this.anisotropyRotation=e.anisotropyRotation,this.anisotropyMap=e.anisotropyMap,this.clearcoat=e.clearcoat,this.clearcoatMap=e.clearcoatMap,this.clearcoatRoughness=e.clearcoatRoughness,this.clearcoatRoughnessMap=e.clearcoatRoughnessMap,this.clearcoatNormalMap=e.clearcoatNormalMap,this.clearcoatNormalScale.copy(e.clearcoatNormalScale),this.dispersion=e.dispersion,this.ior=e.ior,this.iridescence=e.iridescence,this.iridescenceMap=e.iridescenceMap,this.iridescenceIOR=e.iridescenceIOR,this.iridescenceThicknessRange=[...e.iridescenceThicknessRange],this.iridescenceThicknessMap=e.iridescenceThicknessMap,this.retroreflectivity=e.retroreflectivity,this.sheen=e.sheen,this.sheenColor.copy(e.sheenColor),this.sheenColorMap=e.sheenColorMap,this.sheenRoughness=e.sheenRoughness,this.sheenRoughnessMap=e.sheenRoughnessMap,this.transmission=e.transmission,this.transmissionMap=e.transmissionMap,this.thickness=e.thickness,this.thicknessMap=e.thicknessMap,this.attenuationDistance=e.attenuationDistance,this.attenuationColor.copy(e.attenuationColor),this.specularIntensity=e.specularIntensity,this.specularIntensityMap=e.specularIntensityMap,this.specularColor.copy(e.specularColor),this.specularColorMap=e.specularColorMap,this}};var En=class extends hi{constructor(e){super(),this.isMeshLambertMaterial=!0,this.type="MeshLambertMaterial",this.color=new Ie(16777215),this.map=null,this.lightMap=null,this.lightMapIntensity=1,this.aoMap=null,this.aoMapIntensity=1,this.emissive=new Ie(0),this.emissiveIntensity=1,this.emissiveMap=null,this.bumpMap=null,this.bumpScale=1,this.normalMap=null,this.normalMapType=$a,this.normalScale=new Se(1,1),this.displacementMap=null,this.displacementScale=1,this.displacementBias=0,this.specularMap=null,this.alphaMap=null,this.envMap=null,this.envMapRotation=new Di,this.combine=Bl,this.reflectivity=1,this.envMapIntensity=1,this.refractionRatio=.98,this.wireframe=!1,this.wireframeLinewidth=1,this.wireframeLinecap="round",this.wireframeLinejoin="round",this.flatShading=!1,this.fog=!0,this.setValues(e)}copy(e){return super.copy(e),this.color.copy(e.color),this.map=e.map,this.lightMap=e.lightMap,this.lightMapIntensity=e.lightMapIntensity,this.aoMap=e.aoMap,this.aoMapIntensity=e.aoMapIntensity,this.emissive.copy(e.emissive),this.emissiveMap=e.emissiveMap,this.emissiveIntensity=e.emissiveIntensity,this.bumpMap=e.bumpMap,this.bumpScale=e.bumpScale,this.normalMap=e.normalMap,this.normalMapType=e.normalMapType,this.normalScale.copy(e.normalScale),this.displacementMap=e.displacementMap,this.displacementScale=e.displacementScale,this.displacementBias=e.displacementBias,this.specularMap=e.specularMap,this.alphaMap=e.alphaMap,this.envMap=e.envMap,this.envMapRotation.copy(e.envMapRotation),this.combine=e.combine,this.reflectivity=e.reflectivity,this.envMapIntensity=e.envMapIntensity,this.refractionRatio=e.refractionRatio,this.wireframe=e.wireframe,this.wireframeLinewidth=e.wireframeLinewidth,this.wireframeLinecap=e.wireframeLinecap,this.wireframeLinejoin=e.wireframeLinejoin,this.flatShading=e.flatShading,this.fog=e.fog,this}},El=class extends hi{constructor(e){super(),this.isMeshDepthMaterial=!0,this.type="MeshDepthMaterial",this.depthPacking=Bm,this.map=null,this.alphaMap=null,this.displacementMap=null,this.displacementScale=1,this.displacementBias=0,this.wireframe=!1,this.wireframeLinewidth=1,this.setValues(e)}copy(e){return super.copy(e),this.depthPacking=e.depthPacking,this.map=e.map,this.alphaMap=e.alphaMap,this.displacementMap=e.displacementMap,this.displacementScale=e.displacementScale,this.displacementBias=e.displacementBias,this.wireframe=e.wireframe,this.wireframeLinewidth=e.wireframeLinewidth,this}},Al=class extends hi{constructor(e){super(),this.isMeshDistanceMaterial=!0,this.type="MeshDistanceMaterial",this.map=null,this.alphaMap=null,this.displacementMap=null,this.displacementScale=1,this.displacementBias=0,this.setValues(e)}copy(e){return super.copy(e),this.map=e.map,this.alphaMap=e.alphaMap,this.displacementMap=e.displacementMap,this.displacementScale=e.displacementScale,this.displacementBias=e.displacementBias,this}};function Yn(i,e){return!i||i.constructor===e?i:typeof e.BYTES_PER_ELEMENT=="number"?new e(i):Array.prototype.slice.call(i)}function dl(i){return i!==void 0&&i.inTangents!==void 0&&i.outTangents!==void 0}function fx(i){function e(r,s){return i[r]-i[s]}let t=i.length,n=new Array(t);for(let r=0;r!==t;++r)n[r]=r;return n.sort(e),n}function lm(i,e,t){let n=i.length,r=new i.constructor(n);for(let s=0,a=0;a!==n;++s){let o=t[s]*e;for(let l=0;l!==e;++l)r[a++]=i[o+l]}return r}function px(i,e,t,n){let r=1,s=i[0];for(;s!==void 0&&s[n]===void 0;)s=i[r++];if(s===void 0)return;let a=s[n];if(a!==void 0)if(Array.isArray(a))do a=s[n],a!==void 0&&(e.push(s.time),t.push(...a)),s=i[r++];while(s!==void 0);else if(a.toArray!==void 0)do a=s[n],a!==void 0&&(e.push(s.time),a.toArray(t,t.length)),s=i[r++];while(s!==void 0);else do a=s[n],a!==void 0&&(e.push(s.time),t.push(a)),s=i[r++];while(s!==void 0)}var nn=class{constructor(e,t,n,r){this.parameterPositions=e,this._cachedIndex=0,this.resultBuffer=r!==void 0?r:new t.constructor(n),this.sampleValues=t,this.valueSize=n,this.settings=null,this.DefaultSettings_={}}evaluate(e){let t=this.parameterPositions,n=this._cachedIndex,r=t[n],s=t[n-1];i:{e:{let a;t:{n:if(!(e<r)){for(let o=n+2;;){if(r===void 0){if(e<s)break n;return n=t.length,this._cachedIndex=n,this.copySampleValue_(n-1)}if(n===o)break;if(s=r,r=t[++n],e<r)break e}a=t.length;break t}if(!(e>=s)){let o=t[1];e<o&&(n=2,s=o);for(let l=n-2;;){if(s===void 0)return this._cachedIndex=0,this.copySampleValue_(0);if(n===l)break;if(r=s,s=t[--n-1],e>=s)break e}a=n,n=0;break t}break i}for(;n<a;){let o=n+a>>>1;e<t[o]?a=o:n=o+1}if(r=t[n],s=t[n-1],s===void 0)return this._cachedIndex=0,this.copySampleValue_(0);if(r===void 0)return n=t.length,this._cachedIndex=n,this.copySampleValue_(n-1)}this._cachedIndex=n,this.intervalChanged_(n,s,r)}return this.interpolate_(n,s,e,r)}getSettings_(){return this.settings||this.DefaultSettings_}copySampleValue_(e){let t=this.resultBuffer,n=this.sampleValues,r=this.valueSize,s=e*r;for(let a=0;a!==r;++a)t[a]=n[s+a];return t}interpolate_(){throw new Error("THREE.Interpolant: Call to abstract method.")}intervalChanged_(){}},Cl=class extends nn{constructor(e,t,n,r){super(e,t,n,r),this._weightPrev=-0,this._offsetPrev=-0,this._weightNext=-0,this._offsetNext=-0,this.DefaultSettings_={endingStart:mu,endingEnd:mu}}intervalChanged_(e,t,n){let r=this.parameterPositions,s=e-2,a=e+1,o=r[s],l=r[a];if(o===void 0)switch(this.getSettings_().endingStart){case gu:s=e,o=2*t-n;break;case yu:s=r.length-2,o=t+r[s]-r[s+1];break;default:s=e,o=n}if(l===void 0)switch(this.getSettings_().endingEnd){case gu:a=e,l=2*n-t;break;case yu:a=1,l=n+r[1]-r[0];break;default:a=e-1,l=t}let c=(n-t)*.5,h=this.valueSize;this._weightPrev=c/(t-o),this._weightNext=c/(l-n),this._offsetPrev=s*h,this._offsetNext=a*h}interpolate_(e,t,n,r){let s=this.resultBuffer,a=this.sampleValues,o=this.valueSize,l=e*o,c=l-o,h=this._offsetPrev,u=this._offsetNext,d=this._weightPrev,f=this._weightNext,p=(n-t)/(r-t),y=p*p,m=y*p,g=-d*m+2*d*y-d*p,v=(1+d)*m+(-1.5-2*d)*y+(-.5+d)*p+1,S=(-1-f)*m+(1.5+f)*y+.5*p,_=f*m-f*y;for(let M=0;M!==o;++M)s[M]=g*a[h+M]+v*a[c+M]+S*a[l+M]+_*a[u+M];return s}},Rl=class extends nn{constructor(e,t,n,r){super(e,t,n,r)}interpolate_(e,t,n,r){let s=this.resultBuffer,a=this.sampleValues,o=this.valueSize,l=e*o,c=l-o,h=(n-t)/(r-t),u=1-h;for(let d=0;d!==o;++d)s[d]=a[c+d]*u+a[l+d]*h;return s}},Pl=class extends nn{constructor(e,t,n,r){super(e,t,n,r)}interpolate_(e){return this.copySampleValue_(e-1)}},Il=class extends nn{interpolate_(e,t,n,r){let s=this.resultBuffer,a=this.sampleValues,o=this.valueSize,l=e*o,c=l-o,h=this.inTangents,u=this.outTangents;if(!h||!u){let p=(n-t)/(r-t),y=1-p;for(let m=0;m!==o;++m)s[m]=a[c+m]*y+a[l+m]*p;return s}let d=o*2,f=e-1;for(let p=0;p!==o;++p){let y=a[c+p],m=a[l+p],g=f*d+p*2,v=u[g],S=u[g+1],_=e*d+p*2,M=h[_],w=h[_+1],E=gx(n,t,v,M,r);s[p]=Jm(E,y,S,w,m)}return s}};function Jm(i,e,t,n,r){let s=1-i;return s*s*s*e+3*s*s*i*t+3*s*i*i*n+i*i*i*r}function mx(i,e,t,n,r){let s=1-i;return 3*s*s*(t-e)+6*s*i*(n-t)+3*i*i*(r-n)}function gx(i,e,t,n,r){let s=(i-e)/(r-e);for(let a=0;a<8;a++){let o=Jm(s,e,t,n,r)-i;if(Math.abs(o)<1e-10)break;let l=mx(s,e,t,n,r);if(Math.abs(l)<1e-10)break;s=Math.max(0,Math.min(1,s-o/l))}return s}var Si=class{constructor(e,t,n,r){if(e===void 0)throw new Error("THREE.KeyframeTrack: track name is undefined");if(t===void 0||t.length===0)throw new Error("THREE.KeyframeTrack: no keyframes in track named "+e);this.name=e,this.times=Yn(t,this.TimeBufferType),this.values=Yn(n,this.ValueBufferType),this.setInterpolation(r||this.DefaultInterpolation)}static toJSON(e){let t=e.constructor,n;if(t.toJSON!==this.toJSON)n=t.toJSON(e);else{n={name:e.name,times:Yn(e.times,Array),values:Yn(e.values,Array)};let r=e.getInterpolation();r!==e.DefaultInterpolation&&(n.interpolation=r),dl(e.settings)&&(n.settings={inTangents:Yn(e.settings.inTangents,Array),outTangents:Yn(e.settings.outTangents,Array)})}return n.type=e.ValueTypeName,n}InterpolantFactoryMethodDiscrete(e){return new Pl(this.times,this.values,this.getValueSize(),e)}InterpolantFactoryMethodLinear(e){return new Rl(this.times,this.values,this.getValueSize(),e)}InterpolantFactoryMethodSmooth(e){return new Cl(this.times,this.values,this.getValueSize(),e)}InterpolantFactoryMethodBezier(e){let t=new Il(this.times,this.values,this.getValueSize(),e);return this.settings&&(t.inTangents=this.settings.inTangents,t.outTangents=this.settings.outTangents),t}setInterpolation(e){let t;switch(e){case wr:t=this.InterpolantFactoryMethodDiscrete;break;case Tr:t=this.InterpolantFactoryMethodLinear;break;case hl:t=this.InterpolantFactoryMethodSmooth;break;case pu:t=this.InterpolantFactoryMethodBezier;break}if(t===void 0){let n="unsupported interpolation for "+this.ValueTypeName+" keyframe track named "+this.name;if(this.createInterpolant===void 0)if(e!==this.DefaultInterpolation)this.setInterpolation(this.DefaultInterpolation);else throw new Error(n);return Ce("KeyframeTrack:",n),this}return this.createInterpolant=t,this}getInterpolation(){switch(this.createInterpolant){case this.InterpolantFactoryMethodDiscrete:return wr;case this.InterpolantFactoryMethodLinear:return Tr;case this.InterpolantFactoryMethodSmooth:return hl;case this.InterpolantFactoryMethodBezier:return pu}}getValueSize(){return this.values.length/this.times.length}shift(e){if(e!==0){let t=this.times;for(let n=0,r=t.length;n!==r;++n)t[n]+=e}return this}scale(e){if(e!==1){let t=this.times;for(let n=0,r=t.length;n!==r;++n)t[n]*=e;dl(this.settings)&&(cm(this.settings.inTangents,e),cm(this.settings.outTangents,e))}return this}trim(e,t){let n=this.times,r=n.length,s=0,a=r-1;for(;s!==r&&n[s]<e;)++s;for(;a!==-1&&n[a]>t;)--a;if(++a,s!==0||a!==r){s>=a&&(a=Math.max(a,1),s=a-1);let o=this.getValueSize();this.times=n.slice(s,a),this.values=this.values.slice(s*o,a*o)}return this}validate(){let e=!0,t=this.getValueSize();t-Math.floor(t)!==0&&(Fe("KeyframeTrack: Invalid value size in track.",this),e=!1);let n=this.times,r=this.values,s=n.length;s===0&&(Fe("KeyframeTrack: Track is empty.",this),e=!1);let a=null;for(let o=0;o!==s;o++){let l=n[o];if(typeof l=="number"&&isNaN(l)){Fe("KeyframeTrack: Time is not a valid number.",this,o,l),e=!1;break}if(a!==null&&a>l){Fe("KeyframeTrack: Out of order keys.",this,o,l,a),e=!1;break}a=l}if(r!==void 0&&E_(r))for(let o=0,l=r.length;o!==l;++o){let c=r[o];if(isNaN(c)){Fe("KeyframeTrack: Value is not a valid number.",this,o,c),e=!1;break}}return e}optimize(){let e=this.times.slice(),t=this.values.slice(),n=this.getValueSize(),r=this.getInterpolation()===hl,s=e.length-1,a=1;for(let o=1;o<s;++o){let l=!1,c=e[o],h=e[o+1];if(c!==h&&(o!==1||c!==e[0]))if(r)l=!0;else{let u=o*n,d=u-n,f=u+n;for(let p=0;p!==n;++p){let y=t[u+p];if(y!==t[d+p]||y!==t[f+p]){l=!0;break}}}if(l){if(o!==a){e[a]=e[o];let u=o*n,d=a*n;for(let f=0;f!==n;++f)t[d+f]=t[u+f]}++a}}if(s>0){e[a]=e[s];for(let o=s*n,l=a*n,c=0;c!==n;++c)t[l+c]=t[o+c];++a}return a!==e.length?(this.times=e.slice(0,a),this.values=t.slice(0,a*n)):(this.times=e,this.values=t),this}clone(){let e=this.times.slice(),t=this.values.slice(),n=this.constructor,r=new n(this.name,e,t);return r.createInterpolant=this.createInterpolant,dl(this.settings)&&(r.settings={inTangents:this.settings.inTangents.slice(),outTangents:this.settings.outTangents.slice()}),r}};function cm(i,e){for(let t=0,n=i.length;t!==n;t+=2)i[t]*=e}Si.prototype.ValueTypeName="";Si.prototype.TimeBufferType=Float32Array;Si.prototype.ValueBufferType=Float32Array;Si.prototype.DefaultInterpolation=Tr;var An=class extends Si{constructor(e,t,n){super(e,t,n)}};An.prototype.ValueTypeName="bool";An.prototype.ValueBufferType=Array;An.prototype.DefaultInterpolation=wr;An.prototype.InterpolantFactoryMethodLinear=void 0;An.prototype.InterpolantFactoryMethodSmooth=void 0;var Ca=class extends Si{constructor(e,t,n,r){super(e,t,n,r)}};Ca.prototype.ValueTypeName="color";var Cn=class extends Si{constructor(e,t,n,r){super(e,t,n,r)}};Cn.prototype.ValueTypeName="number";var Ll=class extends nn{constructor(e,t,n,r){super(e,t,n,r)}interpolate_(e,t,n,r){let s=this.resultBuffer,a=this.sampleValues,o=this.valueSize,l=(n-t)/(r-t),c=e*o;for(let h=c+o;c!==h;c+=4)Ot.slerpFlat(s,0,a,c-o,a,c,l);return s}},Rn=class extends Si{constructor(e,t,n,r){super(e,t,n,r)}InterpolantFactoryMethodLinear(e){return new Ll(this.times,this.values,this.getValueSize(),e)}};Rn.prototype.ValueTypeName="quaternion";Rn.prototype.InterpolantFactoryMethodSmooth=void 0;var Pn=class extends Si{constructor(e,t,n){super(e,t,n)}};Pn.prototype.ValueTypeName="string";Pn.prototype.ValueBufferType=Array;Pn.prototype.DefaultInterpolation=wr;Pn.prototype.InterpolantFactoryMethodLinear=void 0;Pn.prototype.InterpolantFactoryMethodSmooth=void 0;var er=class extends Si{constructor(e,t,n,r){super(e,t,n,r)}};er.prototype.ValueTypeName="vector";var Ra=class{constructor(e="",t=-1,n=[],r=Fm){this.name=e,this.tracks=n,this.duration=t,this.blendMode=r,this.uuid=Hi(),this.userData={},this.duration<0&&this.resetDuration()}static parse(e){let t=[],n=e.tracks,r=1/(e.fps||1);for(let a=0,o=n.length;a!==o;++a)t.push(_x(n[a]).scale(r));let s=new this(e.name,e.duration,t,e.blendMode);return s.uuid=e.uuid,s.userData=JSON.parse(e.userData||"{}"),s}static toJSON(e){let t=[],n=e.tracks,r={name:e.name,duration:e.duration,tracks:t,uuid:e.uuid,blendMode:e.blendMode,userData:JSON.stringify(e.userData)};for(let s=0,a=n.length;s!==a;++s)t.push(Si.toJSON(n[s]));return r}static CreateFromMorphTargetSequence(e,t,n,r){let s=t.length,a=[];for(let o=0;o<s;o++){let l=[],c=[];l.push((o+s-1)%s,o,(o+1)%s),c.push(0,1,0);let h=fx(l);l=lm(l,1,h),c=lm(c,1,h),!r&&l[0]===0&&(l.push(s),c.push(c[0])),a.push(new Cn(".morphTargetInfluences["+t[o].name+"]",l,c).scale(1/n))}return new this(e,-1,a)}static findByName(e,t){let n=e;if(!Array.isArray(e)){let r=e;n=r.geometry&&r.geometry.animations||r.animations}for(let r=0;r<n.length;r++)if(n[r].name===t)return n[r];return null}static CreateClipsFromMorphTargetSequences(e,t,n){let r={},s=/^([\w-]*?)([\d]+)$/;for(let o=0,l=e.length;o<l;o++){let c=e[o],h=c.name.match(s);if(h&&h.length>1){let u=h[1],d=r[u];d||(r[u]=d=[]),d.push(c)}}let a=[];for(let o in r)a.push(this.CreateFromMorphTargetSequence(o,r[o],t,n));return a}resetDuration(){let e=this.tracks,t=0;for(let n=0,r=e.length;n!==r;++n){let s=this.tracks[n];t=Math.max(t,s.times[s.times.length-1])}return this.duration=t,this}trim(){for(let e=0;e<this.tracks.length;e++)this.tracks[e].trim(0,this.duration);return this}validate(){let e=!0;for(let t=0;t<this.tracks.length;t++)e=e&&this.tracks[t].validate();return e}optimize(){for(let e=0;e<this.tracks.length;e++)this.tracks[e].optimize();return this}clone(){let e=[];for(let n=0;n<this.tracks.length;n++)e.push(this.tracks[n].clone());let t=new this.constructor(this.name,this.duration,e,this.blendMode);return t.userData=JSON.parse(JSON.stringify(this.userData)),t}toJSON(){return this.constructor.toJSON(this)}};function yx(i){switch(i.toLowerCase()){case"scalar":case"double":case"float":case"number":case"integer":return Cn;case"vector":case"vector2":case"vector3":case"vector4":return er;case"color":return Ca;case"quaternion":return Rn;case"bool":case"boolean":return An;case"string":return Pn}throw new Error("THREE.KeyframeTrack: Unsupported typeName: "+i)}function _x(i){if(i.type===void 0)throw new Error("THREE.KeyframeTrack: track type undefined, can not parse");let e=yx(i.type);if(i.times===void 0){let n=[],r=[];px(i.keys,n,r,"value"),i.times=n,i.values=r}let t;return e.parse!==void 0?t=e.parse(i):t=new e(i.name,i.times,i.values,i.interpolation),dl(i.settings)&&(t.settings={inTangents:Yn(i.settings.inTangents,Float32Array),outTangents:Yn(i.settings.outTangents,Float32Array)}),t}var en={enabled:!1,files:{},add:function(i,e){this.enabled!==!1&&(hm(i)||(this.files[i]=e))},get:function(i){if(this.enabled!==!1&&!hm(i))return this.files[i]},remove:function(i){delete this.files[i]},clear:function(){this.files={}}};function hm(i){try{let e=i.slice(i.indexOf(":")+1);return new URL(e).protocol==="blob:"}catch{return!1}}var Rs=class{constructor(e,t,n){let r=this,s=!1,a=0,o=0,l,c=[];this.onStart=void 0,this.onLoad=e,this.onProgress=t,this.onError=n,this._abortController=null,this.itemStart=function(h){o++,s===!1&&r.onStart!==void 0&&r.onStart(h,a,o),s=!0},this.itemEnd=function(h){a++,r.onProgress!==void 0&&r.onProgress(h,a,o),a===o&&(s=!1,r.onLoad!==void 0&&r.onLoad())},this.itemError=function(h){r.onError!==void 0&&r.onError(h)},this.resolveURL=function(h){return h=h.normalize("NFC"),l?l(h):h},this.setURLModifier=function(h){return l=h,this},this.addHandler=function(h,u){return c.push(h,u),this},this.removeHandler=function(h){let u=c.indexOf(h);return u!==-1&&c.splice(u,2),this},this.getHandler=function(h){for(let u=0,d=c.length;u<d;u+=2){let f=c[u],p=c[u+1];if(f.global&&(f.lastIndex=0),f.test(h))return p}return null},this.abort=function(){return this.abortController.abort(),this._abortController=null,this}}get abortController(){return this._abortController||(this._abortController=new AbortController),this._abortController}},or=new Rs,rn=class{constructor(e){this.manager=e!==void 0?e:or,this.crossOrigin="anonymous",this.withCredentials=!1,this.path="",this.resourcePath="",this.requestHeader={},typeof __THREE_DEVTOOLS__<"u"&&__THREE_DEVTOOLS__.dispatchEvent(new CustomEvent("observe",{detail:this}))}load(){}loadAsync(e,t){let n=this;return new Promise(function(r,s){n.load(e,r,t,s)})}parse(){}setCrossOrigin(e){return this.crossOrigin=e,this}setWithCredentials(e){return this.withCredentials=e,this}setPath(e){return this.path=e,this}setResourcePath(e){return this.resourcePath=e,this}setRequestHeader(e){return this.requestHeader=e,this}abort(){return this}};rn.DEFAULT_MATERIAL_NAME="__DEFAULT";var vn={},xu=class extends Error{constructor(e,t){super(e),this.response=t}},Nr=class extends rn{constructor(e){super(e),this.mimeType="",this.responseType="",this._abortController=new AbortController}load(e,t,n,r){e===void 0&&(e=""),this.path!==void 0&&(e=this.path+e),e=this.manager.resolveURL(e);let s=en.get(`file:${e}`);if(s!==void 0){this.manager.itemStart(e),setTimeout(()=>{t&&t(s),this.manager.itemEnd(e)},0);return}if(vn[e]!==void 0){vn[e].push({onLoad:t,onProgress:n,onError:r});return}vn[e]=[],vn[e].push({onLoad:t,onProgress:n,onError:r});let a=new Request(e,{headers:new Headers(this.requestHeader),credentials:this.withCredentials?"include":"same-origin",signal:typeof AbortSignal.any=="function"?AbortSignal.any([this._abortController.signal,this.manager.abortController.signal]):this._abortController.signal}),o=this.mimeType,l=this.responseType;fetch(a).then(c=>{if(c.status===200||c.status===0){if(c.status===0&&Ce("FileLoader: HTTP Status 0 received."),typeof ReadableStream>"u"||c.body===void 0||c.body.getReader===void 0)return c;let h=vn[e],u=c.body.getReader(),d=c.headers.get("X-File-Size")||c.headers.get("Content-Length"),f=d?parseInt(d):0,p=f!==0,y=0,m=new ReadableStream({start(g){v();function v(){u.read().then(({done:S,value:_})=>{if(S)g.close();else{y+=_.byteLength;let M=new ProgressEvent("progress",{lengthComputable:p,loaded:y,total:f});for(let w=0,E=h.length;w<E;w++){let x=h[w];x.onProgress&&x.onProgress(M)}g.enqueue(_),v()}},S=>{g.error(S)})}}});return new Response(m)}else throw new xu(`fetch for "${c.url}" responded with ${c.status}: ${c.statusText}`,c)}).then(c=>{switch(l){case"arraybuffer":return c.arrayBuffer();case"blob":return c.blob();case"document":return c.text().then(h=>new DOMParser().parseFromString(h,o));case"json":return c.json();default:if(o==="")return c.text();{let u=/charset="?([^;"\s]*)"?/i.exec(o),d=u&&u[1]?u[1].toLowerCase():void 0,f=new TextDecoder(d);return c.arrayBuffer().then(p=>f.decode(p))}}}).then(c=>{en.add(`file:${e}`,c);let h=vn[e];delete vn[e];for(let u=0,d=h.length;u<d;u++){let f=h[u];f.onLoad&&f.onLoad(c)}}).catch(c=>{let h=vn[e];if(h===void 0)throw this.manager.itemError(e),c;delete vn[e];for(let u=0,d=h.length;u<d;u++){let f=h[u];f.onError&&f.onError(c)}this.manager.itemError(e)}).finally(()=>{this.manager.itemEnd(e)}),this.manager.itemStart(e)}setResponseType(e){return this.responseType=e,this}setMimeType(e){return this.mimeType=e,this}abort(){return this._abortController.abort(),this._abortController=new AbortController,this}};var fs=new WeakMap,Dl=class extends rn{constructor(e){super(e)}load(e,t,n,r){this.path!==void 0&&(e=this.path+e),e=this.manager.resolveURL(e);let s=this,a=en.get(`image:${e}`);if(a!==void 0){if(a.complete===!0)s.manager.itemStart(e),setTimeout(function(){t&&t(a),s.manager.itemEnd(e)},0);else{let u=fs.get(a);u===void 0&&(u=[],fs.set(a,u)),u.push({onLoad:t,onError:r})}return a}let o=Ss("img");function l(){h(),t&&t(this);let u=fs.get(this)||[];for(let d=0;d<u.length;d++){let f=u[d];f.onLoad&&f.onLoad(this)}fs.delete(this),s.manager.itemEnd(e)}function c(u){h(),r&&r(u),en.remove(`image:${e}`);let d=fs.get(this)||[];for(let f=0;f<d.length;f++){let p=d[f];p.onError&&p.onError(u)}fs.delete(this),s.manager.itemError(e),s.manager.itemEnd(e)}function h(){o.removeEventListener("load",l,!1),o.removeEventListener("error",c,!1)}return o.addEventListener("load",l,!1),o.addEventListener("error",c,!1),e.slice(0,5)!=="data:"&&this.crossOrigin!==void 0&&(o.crossOrigin=this.crossOrigin),en.add(`image:${e}`,o),s.manager.itemStart(e),o.src=e,o}};var Pa=class extends rn{constructor(e){super(e)}load(e,t,n,r){let s=new Pt,a=new Dl(this.manager);return a.setCrossOrigin(this.crossOrigin),a.setPath(this.path),a.load(e,function(o){s.image=o,s.needsUpdate=!0,t!==void 0&&t(s)},n,r),s}},Ur=class extends Tt{constructor(e,t=1){super(),this.isLight=!0,this.type="Light",this.color=new Ie(e),this.intensity=t}copy(e,t){return super.copy(e,t),this.color.copy(e.color),this.intensity=e.intensity,this}toJSON(e){let t=super.toJSON(e);return t.object.color=this.color.getHex(),t.object.intensity=this.intensity,t}};var hu=new ge,um=new P,dm=new P,Ps=class{constructor(e){this.camera=e,this.intensity=1,this.bias=0,this.biasNode=null,this.normalBias=0,this.radius=1,this.blurSamples=8,this.mapSize=new Se(512,512),this.mapType=di,this.map=null,this.mapPass=null,this.matrix=new ge,this.autoUpdate=!0,this.needsUpdate=!1,this._frustum=new wn,this._frameExtents=new Se(1,1),this._viewportCount=1,this._viewports=[new Xe(0,0,1,1)]}getViewportCount(){return this._viewportCount}getCamera(){return this.camera}getFrustum(){return this._frustum}updateMatrices(e){let t=this.camera;um.setFromMatrixPosition(e.matrixWorld),t.position.copy(um),dm.setFromMatrixPosition(e.target.matrixWorld),t.lookAt(dm),t.updateMatrixWorld(),this._updateMatrix(t,this.matrix,this._frustum)}_updateMatrix(e,t,n,r){hu.multiplyMatrices(e.projectionMatrix,e.matrixWorldInverse),n.setFromProjectionMatrix(hu,e.coordinateSystem,e.reversedDepth);let s=this._frameExtents,a=r?r.z/s.x:1,o=r?r.w/s.y:1,l=r?r.x/s.x:0,c=r?r.y/s.y:0;e.coordinateSystem===bs||e.reversedDepth?t.set(.5*a,0,0,.5*a+l,0,.5*o,0,.5*o+c,0,0,1,0,0,0,0,1):t.set(.5*a,0,0,.5*a+l,0,.5*o,0,.5*o+c,0,0,.5,.5,0,0,0,1),t.multiply(hu)}getViewport(e){return this._viewports[e]}getFrameExtents(){return this._frameExtents}dispose(){this.map&&this.map.dispose(),this.mapPass&&this.mapPass.dispose()}copy(e){return this.camera=e.camera.clone(),this.intensity=e.intensity,this.bias=e.bias,this.radius=e.radius,this.autoUpdate=e.autoUpdate,this.needsUpdate=e.needsUpdate,this.normalBias=e.normalBias,this.blurSamples=e.blurSamples,this.mapSize.copy(e.mapSize),this.biasNode=e.biasNode,this}clone(){return new this.constructor().copy(this)}toJSON(){let e={};return e.intensity=this.intensity,e.bias=this.bias,e.normalBias=this.normalBias,e.radius=this.radius,e.blurSamples=this.blurSamples,e.mapSize=this.mapSize.toArray(),e.camera=this.camera.toJSON(!1).object,delete e.camera.matrix,e}},ol=new P,ll=new Ot,Qi=new P,Ia=class extends Tt{constructor(){super(),this.isCamera=!0,this.type="Camera",this.matrixWorldInverse=new ge,this.projectionMatrix=new ge,this.projectionMatrixInverse=new ge,this.coordinateSystem=Gi,this._reversedDepth=!1}get reversedDepth(){return this._reversedDepth}copy(e,t){return super.copy(e,t),this.matrixWorldInverse.copy(e.matrixWorldInverse),this.projectionMatrix.copy(e.projectionMatrix),this.projectionMatrixInverse.copy(e.projectionMatrixInverse),this.coordinateSystem=e.coordinateSystem,this}getWorldDirection(e){return super.getWorldDirection(e).negate()}updateMatrixWorld(e){super.updateMatrixWorld(e),this.matrixWorld.decompose(ol,ll,Qi),Qi.x===1&&Qi.y===1&&Qi.z===1?this.matrixWorldInverse.copy(this.matrixWorld).invert():this.matrixWorldInverse.compose(ol,ll,Qi.set(1,1,1)).invert()}updateWorldMatrix(e,t,n=!1){super.updateWorldMatrix(e,t,n),this.matrixWorld.decompose(ol,ll,Qi),Qi.x===1&&Qi.y===1&&Qi.z===1?this.matrixWorldInverse.copy(this.matrixWorld).invert():this.matrixWorldInverse.compose(ol,ll,Qi.set(1,1,1)).invert()}clone(){return new this.constructor().copy(this)}},jn=new P,fm=new Se,pm=new Se,Rt=class extends Ia{constructor(e=50,t=1,n=.1,r=2e3){super(),this.isPerspectiveCamera=!0,this.type="PerspectiveCamera",this.fov=e,this.zoom=1,this.near=n,this.far=r,this.focus=10,this.aspect=t,this.view=null,this.filmGauge=35,this.filmOffset=0,this.updateProjectionMatrix()}copy(e,t){return super.copy(e,t),this.fov=e.fov,this.zoom=e.zoom,this.near=e.near,this.far=e.far,this.focus=e.focus,this.aspect=e.aspect,this.view=e.view===null?null:Object.assign({},e.view),this.filmGauge=e.filmGauge,this.filmOffset=e.filmOffset,this}setFocalLength(e){let t=.5*this.getFilmHeight()/e;this.fov=Er*2*Math.atan(t),this.updateProjectionMatrix()}getFocalLength(){let e=Math.tan(da*.5*this.fov);return .5*this.getFilmHeight()/e}getEffectiveFOV(){return Er*2*Math.atan(Math.tan(da*.5*this.fov)/this.zoom)}getFilmWidth(){return this.filmGauge*Math.min(this.aspect,1)}getFilmHeight(){return this.filmGauge/Math.max(this.aspect,1)}getViewBounds(e,t,n){jn.set(-1,-1,.5).applyMatrix4(this.projectionMatrixInverse),t.set(jn.x,jn.y).multiplyScalar(-e/jn.z),jn.set(1,1,.5).applyMatrix4(this.projectionMatrixInverse),n.set(jn.x,jn.y).multiplyScalar(-e/jn.z)}getViewSize(e,t){return this.getViewBounds(e,fm,pm),t.subVectors(pm,fm)}setViewOffset(e,t,n,r,s,a){this.aspect=e/t,this.view===null&&(this.view={enabled:!0,fullWidth:1,fullHeight:1,offsetX:0,offsetY:0,width:1,height:1}),this.view.enabled=!0,this.view.fullWidth=e,this.view.fullHeight=t,this.view.offsetX=n,this.view.offsetY=r,this.view.width=s,this.view.height=a,this.updateProjectionMatrix()}clearViewOffset(){this.view!==null&&(this.view.enabled=!1),this.updateProjectionMatrix()}updateProjectionMatrix(){let e=this.near,t=e*Math.tan(da*.5*this.fov)/this.zoom,n=2*t,r=this.aspect*n,s=-.5*r,a=this.view;if(this.view!==null&&this.view.enabled){let l=a.fullWidth,c=a.fullHeight;s+=a.offsetX*r/l,t-=a.offsetY*n/c,r*=a.width/l,n*=a.height/c}let o=this.filmOffset;o!==0&&(s+=e*o/this.getFilmWidth()),this.projectionMatrix.makePerspective(s,s+r,t,t-n,e,this.far,this.coordinateSystem,this.reversedDepth),this.projectionMatrixInverse.copy(this.projectionMatrix).invert()}toJSON(e){let t=super.toJSON(e);return t.object.fov=this.fov,t.object.zoom=this.zoom,t.object.near=this.near,t.object.far=this.far,t.object.focus=this.focus,t.object.aspect=this.aspect,this.view!==null&&(t.object.view=Object.assign({},this.view)),t.object.filmGauge=this.filmGauge,t.object.filmOffset=this.filmOffset,t}},vu=class extends Ps{constructor(){super(new Rt(50,1,.5,500)),this.isSpotLightShadow=!0,this.focus=1,this.aspect=1}updateMatrices(e){let t=this.camera,n=Er*2*e.angle*this.focus,r=this.mapSize.width/this.mapSize.height*this.aspect,s=e.distance||t.far;(n!==t.fov||r!==t.aspect||s!==t.far)&&(t.fov=n,t.aspect=r,t.far=s,t.updateProjectionMatrix()),super.updateMatrices(e)}copy(e){return super.copy(e),this.focus=e.focus,this.aspect=e.aspect,this}toJSON(){let e=super.toJSON();return e.focus=this.focus,e.aspect=this.aspect,e}},La=class extends Ur{constructor(e,t,n=0,r=Math.PI/3,s=0,a=2){super(e,t),this.isSpotLight=!0,this.type="SpotLight",this.position.copy(Tt.DEFAULT_UP),this.updateMatrix(),this.target=new Tt,this.distance=n,this.angle=r,this.penumbra=s,this.decay=a,this.map=null,this.shadow=new vu}get power(){return this.intensity*Math.PI}set power(e){this.intensity=e/Math.PI}dispose(){super.dispose(),this.shadow.dispose()}copy(e,t){return super.copy(e,t),this.distance=e.distance,this.angle=e.angle,this.penumbra=e.penumbra,this.decay=e.decay,this.target=e.target.clone(),this.map=e.map,this.shadow=e.shadow.clone(),this}toJSON(e){let t=super.toJSON(e);return t.object.distance=this.distance,t.object.angle=this.angle,t.object.decay=this.decay,t.object.penumbra=this.penumbra,t.object.target=this.target.uuid,this.map&&this.map.isTexture&&(t.object.map=this.map.toJSON(e).uuid),t.object.shadow=this.shadow.toJSON(),t}},bu=class extends Ps{constructor(){super(new Rt(90,1,.5,500)),this.isPointLightShadow=!0}},Da=class extends Ur{constructor(e,t,n=0,r=2){super(e,t),this.isPointLight=!0,this.type="PointLight",this.distance=n,this.decay=r,this.shadow=new bu}get power(){return this.intensity*4*Math.PI}set power(e){this.intensity=e/(4*Math.PI)}dispose(){super.dispose(),this.shadow.dispose()}copy(e,t){return super.copy(e,t),this.distance=e.distance,this.decay=e.decay,this.shadow=e.shadow.clone(),this}toJSON(e){let t=super.toJSON(e);return t.object.distance=this.distance,t.object.decay=this.decay,t.object.shadow=this.shadow.toJSON(),t}},Wi=class extends Ia{constructor(e=-1,t=1,n=1,r=-1,s=.1,a=2e3){super(),this.isOrthographicCamera=!0,this.type="OrthographicCamera",this.zoom=1,this.view=null,this.left=e,this.right=t,this.top=n,this.bottom=r,this.near=s,this.far=a,this.updateProjectionMatrix()}copy(e,t){return super.copy(e,t),this.left=e.left,this.right=e.right,this.top=e.top,this.bottom=e.bottom,this.near=e.near,this.far=e.far,this.zoom=e.zoom,this.view=e.view===null?null:Object.assign({},e.view),this}setViewOffset(e,t,n,r,s,a){this.view===null&&(this.view={enabled:!0,fullWidth:1,fullHeight:1,offsetX:0,offsetY:0,width:1,height:1}),this.view.enabled=!0,this.view.fullWidth=e,this.view.fullHeight=t,this.view.offsetX=n,this.view.offsetY=r,this.view.width=s,this.view.height=a,this.updateProjectionMatrix()}clearViewOffset(){this.view!==null&&(this.view.enabled=!1),this.updateProjectionMatrix()}updateProjectionMatrix(){let e=(this.right-this.left)/(2*this.zoom),t=(this.top-this.bottom)/(2*this.zoom),n=(this.right+this.left)/2,r=(this.top+this.bottom)/2,s=n-e,a=n+e,o=r+t,l=r-t;if(this.view!==null&&this.view.enabled){let c=(this.right-this.left)/this.view.fullWidth/this.zoom,h=(this.top-this.bottom)/this.view.fullHeight/this.zoom;s+=c*this.view.offsetX,a=s+c*this.view.width,o-=h*this.view.offsetY,l=o-h*this.view.height}this.projectionMatrix.makeOrthographic(s,a,o,l,this.near,this.far,this.coordinateSystem,this.reversedDepth),this.projectionMatrixInverse.copy(this.projectionMatrix).invert()}toJSON(e){let t=super.toJSON(e);return t.object.zoom=this.zoom,t.object.left=this.left,t.object.right=this.right,t.object.top=this.top,t.object.bottom=this.bottom,t.object.near=this.near,t.object.far=this.far,this.view!==null&&(t.object.view=Object.assign({},this.view)),t}},Su=class extends Ps{constructor(){super(new Wi(-5,5,5,-5,.5,500)),this.isDirectionalLightShadow=!0}},Or=class extends Ur{constructor(e,t){super(e,t),this.isDirectionalLight=!0,this.type="DirectionalLight",this.position.copy(Tt.DEFAULT_UP),this.updateMatrix(),this.target=new Tt,this.shadow=new Su}dispose(){super.dispose(),this.shadow.dispose()}copy(e){return super.copy(e),this.target=e.target.clone(),this.shadow=e.shadow.clone(),this}toJSON(e){let t=super.toJSON(e);return t.object.shadow=this.shadow.toJSON(),t.object.target=this.target.uuid,t}},Na=class extends Ur{constructor(e,t){super(e,t),this.isAmbientLight=!0,this.type="AmbientLight"}};var In=class{static extractUrlBase(e){let t=e.lastIndexOf("/");return t===-1?"./":e.slice(0,t+1)}static resolveURL(e,t){return typeof e!="string"||e===""?"":(/^https?:\/\//i.test(t)&&/^\//.test(e)&&(t=t.replace(/(^https?:\/\/[^\/]+).*/i,"$1")),/^(https?:)?\/\//i.test(e)||/^data:.*,.*$/i.test(e)||/^blob:.*$/i.test(e)?e:t+e)}},Ua=class extends ht{constructor(){super(),this.isInstancedBufferGeometry=!0,this.type="InstancedBufferGeometry",this.instanceCount=1/0}copy(e){return super.copy(e),this.instanceCount=e.instanceCount,this}toJSON(){let e=super.toJSON();return e.instanceCount=this.instanceCount,e.isInstancedBufferGeometry=!0,e}};var uu=new WeakMap,Oa=class extends rn{constructor(e){super(e),this.isImageBitmapLoader=!0,typeof createImageBitmap>"u"&&Ce("ImageBitmapLoader: createImageBitmap() not supported."),typeof fetch>"u"&&Ce("ImageBitmapLoader: fetch() not supported."),this.options={premultiplyAlpha:"none"},this._abortController=new AbortController}setOptions(e){return this.options=e,this}load(e,t,n,r){e===void 0&&(e=""),this.path!==void 0&&(e=this.path+e),e=this.manager.resolveURL(e);let s=this,a=en.get(`image-bitmap:${e}`);if(a!==void 0){if(s.manager.itemStart(e),a.then){a.then(c=>{uu.has(a)===!0?(r&&r(uu.get(a)),s.manager.itemError(e),s.manager.itemEnd(e)):(t&&t(c),s.manager.itemEnd(e))});return}setTimeout(function(){t&&t(a),s.manager.itemEnd(e)},0);return}let o={};o.credentials=this.crossOrigin==="anonymous"?"same-origin":"include",o.headers=this.requestHeader,o.signal=typeof AbortSignal.any=="function"?AbortSignal.any([this._abortController.signal,this.manager.abortController.signal]):this._abortController.signal;let l=fetch(e,o).then(function(c){return c.blob()}).then(function(c){return createImageBitmap(c,Object.assign({},s.options,{colorSpaceConversion:"none"}))}).then(function(c){return en.add(`image-bitmap:${e}`,c),t&&t(c),s.manager.itemEnd(e),c}).catch(function(c){r&&r(c),uu.set(l,c),en.remove(`image-bitmap:${e}`),s.manager.itemError(e),s.manager.itemEnd(e)});en.add(`image-bitmap:${e}`,l),s.manager.itemStart(e)}abort(){return this._abortController.abort(),this._abortController=new AbortController,this}};var ps=-90,ms=1,Nl=class extends Tt{constructor(e,t,n){super(),this.type="CubeCamera",this.renderTarget=n,this.coordinateSystem=null,this.activeMipmapLevel=0;let r=new Rt(ps,ms,e,t);r.layers=this.layers,this.add(r);let s=new Rt(ps,ms,e,t);s.layers=this.layers,this.add(s);let a=new Rt(ps,ms,e,t);a.layers=this.layers,this.add(a);let o=new Rt(ps,ms,e,t);o.layers=this.layers,this.add(o);let l=new Rt(ps,ms,e,t);l.layers=this.layers,this.add(l);let c=new Rt(ps,ms,e,t);c.layers=this.layers,this.add(c)}updateCoordinateSystem(){let e=this.coordinateSystem,t=this.children.concat(),[n,r,s,a,o,l]=t;for(let c of t)this.remove(c);if(e===Gi)n.up.set(0,1,0),n.lookAt(1,0,0),r.up.set(0,1,0),r.lookAt(-1,0,0),s.up.set(0,0,-1),s.lookAt(0,1,0),a.up.set(0,0,1),a.lookAt(0,-1,0),o.up.set(0,1,0),o.lookAt(0,0,1),l.up.set(0,1,0),l.lookAt(0,0,-1);else if(e===bs)n.up.set(0,-1,0),n.lookAt(-1,0,0),r.up.set(0,-1,0),r.lookAt(1,0,0),s.up.set(0,0,1),s.lookAt(0,1,0),a.up.set(0,0,-1),a.lookAt(0,-1,0),o.up.set(0,-1,0),o.lookAt(0,0,1),l.up.set(0,-1,0),l.lookAt(0,0,-1);else throw new Error("THREE.CubeCamera.updateCoordinateSystem(): Invalid coordinate system: "+e);for(let c of t)this.add(c),c.updateMatrixWorld()}update(e,t){this.parent===null&&this.updateMatrixWorld();let{renderTarget:n,activeMipmapLevel:r}=this;this.coordinateSystem!==e.coordinateSystem&&(this.coordinateSystem=e.coordinateSystem,this.updateCoordinateSystem());let[s,a,o,l,c,h]=this.children,u=e.getRenderTarget(),d=e.getActiveCubeFace(),f=e.getActiveMipmapLevel(),p=e.xr.enabled;e.xr.enabled=!1;let y=n.texture.generateMipmaps;n.texture.generateMipmaps=!1;let m=!1;e.isWebGLRenderer===!0?m=e.state.buffers.depth.getReversed():m=e.reversedDepthBuffer,e.setRenderTarget(n,0,r),m&&e.autoClear===!1&&e.clearDepth(),e.render(t,s),e.setRenderTarget(n,1,r),m&&e.autoClear===!1&&e.clearDepth(),e.render(t,a),e.setRenderTarget(n,2,r),m&&e.autoClear===!1&&e.clearDepth(),e.render(t,o),e.setRenderTarget(n,3,r),m&&e.autoClear===!1&&e.clearDepth(),e.render(t,l),e.setRenderTarget(n,4,r),m&&e.autoClear===!1&&e.clearDepth(),e.render(t,c),n.texture.generateMipmaps=y,e.setRenderTarget(n,5,r),m&&e.autoClear===!1&&e.clearDepth(),e.render(t,h),e.setRenderTarget(u,d,f),e.xr.enabled=p,n.texture.needsPMREMUpdate=!0}},Ul=class extends Rt{constructor(e=[]){super(),this.isArrayCamera=!0,this.isMultiViewCamera=!1,this.cameras=e}};var Ju="\\[\\]\\.:\\/",xx=new RegExp("["+Ju+"]","g"),Qu="[^"+Ju+"]",vx="[^"+Ju.replace("\\.","")+"]",bx=/((?:WC+[\/:])*)/.source.replace("WC",Qu),Sx=/(WCOD+)?/.source.replace("WCOD",vx),Mx=/(?:\.(WC+)(?:\[(.+)\])?)?/.source.replace("WC",Qu),wx=/\.(WC+)(?:\[(.+)\])?/.source.replace("WC",Qu),Tx=new RegExp("^"+bx+Sx+Mx+wx+"$"),Ex=["material","materials","bones","map"],Mu=class{constructor(e,t,n){let r=n||mt.parseTrackName(t);this._targetGroup=e,this._bindings=e.subscribe_(t,r)}getValue(e,t){this.bind();let n=this._targetGroup.nCachedObjects_,r=this._bindings[n];r!==void 0&&r.getValue(e,t)}setValue(e,t){let n=this._bindings;for(let r=this._targetGroup.nCachedObjects_,s=n.length;r!==s;++r)n[r].setValue(e,t)}bind(){let e=this._bindings;for(let t=this._targetGroup.nCachedObjects_,n=e.length;t!==n;++t)e[t].bind()}unbind(){let e=this._bindings;for(let t=this._targetGroup.nCachedObjects_,n=e.length;t!==n;++t)e[t].unbind()}},mt=class i{constructor(e,t,n){this.path=t,this.parsedPath=n||i.parseTrackName(t),this.node=i.findNode(e,this.parsedPath.nodeName),this.rootNode=e,this.getValue=this._getValue_unbound,this.setValue=this._setValue_unbound}static create(e,t,n){return e&&e.isAnimationObjectGroup?new i.Composite(e,t,n):new i(e,t,n)}static sanitizeNodeName(e){return e.replace(/\s/g,"_").replace(xx,"")}static parseTrackName(e){let t=Tx.exec(e);if(t===null)throw new Error("THREE.PropertyBinding: Cannot parse trackName: "+e);let n={nodeName:t[2],objectName:t[3],objectIndex:t[4],propertyName:t[5],propertyIndex:t[6]},r=n.nodeName&&n.nodeName.lastIndexOf(".");if(r!==void 0&&r!==-1){let s=n.nodeName.substring(r+1);Ex.indexOf(s)!==-1&&(n.nodeName=n.nodeName.substring(0,r),n.objectName=s)}if(n.propertyName===null||n.propertyName.length===0)throw new Error("THREE.PropertyBinding: can not parse propertyName from trackName: "+e);return n}static findNode(e,t){if(t===void 0||t===""||t==="."||t===-1||t===e.name||t===e.uuid)return e;if(e.skeleton){let n=e.skeleton.getBoneByName(t);if(n!==void 0)return n}if(e.children){let n=function(s){for(let a=0;a<s.length;a++){let o=s[a];if(o.name===t||o.uuid===t)return o;let l=n(o.children);if(l)return l}return null},r=n(e.children);if(r)return r}return null}_getValue_unavailable(){}_setValue_unavailable(){}_getValue_direct(e,t){e[t]=this.targetObject[this.propertyName]}_getValue_array(e,t){let n=this.resolvedProperty;for(let r=0,s=n.length;r!==s;++r)e[t++]=n[r]}_getValue_arrayElement(e,t){e[t]=this.resolvedProperty[this.propertyIndex]}_getValue_toArray(e,t){this.resolvedProperty.toArray(e,t)}_setValue_direct(e,t){this.targetObject[this.propertyName]=e[t]}_setValue_direct_setNeedsUpdate(e,t){this.targetObject[this.propertyName]=e[t],this.targetObject.needsUpdate=!0}_setValue_direct_setMatrixWorldNeedsUpdate(e,t){this.targetObject[this.propertyName]=e[t],this.targetObject.matrixWorldNeedsUpdate=!0}_setValue_array(e,t){let n=this.resolvedProperty;for(let r=0,s=n.length;r!==s;++r)n[r]=e[t++]}_setValue_array_setNeedsUpdate(e,t){let n=this.resolvedProperty;for(let r=0,s=n.length;r!==s;++r)n[r]=e[t++];this.targetObject.needsUpdate=!0}_setValue_array_setMatrixWorldNeedsUpdate(e,t){let n=this.resolvedProperty;for(let r=0,s=n.length;r!==s;++r)n[r]=e[t++];this.targetObject.matrixWorldNeedsUpdate=!0}_setValue_arrayElement(e,t){this.resolvedProperty[this.propertyIndex]=e[t]}_setValue_arrayElement_setNeedsUpdate(e,t){this.resolvedProperty[this.propertyIndex]=e[t],this.targetObject.needsUpdate=!0}_setValue_arrayElement_setMatrixWorldNeedsUpdate(e,t){this.resolvedProperty[this.propertyIndex]=e[t],this.targetObject.matrixWorldNeedsUpdate=!0}_setValue_fromArray(e,t){this.resolvedProperty.fromArray(e,t)}_setValue_fromArray_setNeedsUpdate(e,t){this.resolvedProperty.fromArray(e,t),this.targetObject.needsUpdate=!0}_setValue_fromArray_setMatrixWorldNeedsUpdate(e,t){this.resolvedProperty.fromArray(e,t),this.targetObject.matrixWorldNeedsUpdate=!0}_getValue_unbound(e,t){this.bind(),this.getValue(e,t)}_setValue_unbound(e,t){this.bind(),this.setValue(e,t)}bind(){let e=this.node,t=this.parsedPath,n=t.objectName,r=t.propertyName,s=t.propertyIndex;if(e||(e=i.findNode(this.rootNode,t.nodeName),this.node=e),this.getValue=this._getValue_unavailable,this.setValue=this._setValue_unavailable,!e){Ce("PropertyBinding: No target node found for track: "+this.path+".");return}if(n){let c=t.objectIndex;switch(n){case"materials":if(!e.material){Fe("PropertyBinding: Can not bind to material as node does not have a material.",this);return}if(!e.material.materials){Fe("PropertyBinding: Can not bind to material.materials as node.material does not have a materials array.",this);return}e=e.material.materials;break;case"bones":if(!e.skeleton){Fe("PropertyBinding: Can not bind to bones as node does not have a skeleton.",this);return}e=e.skeleton.bones;for(let h=0;h<e.length;h++)if(e[h].name===c){c=h;break}break;case"map":if("map"in e){e=e.map;break}if(!e.material){Fe("PropertyBinding: Can not bind to material as node does not have a material.",this);return}if(!e.material.map){Fe("PropertyBinding: Can not bind to material.map as node.material does not have a map.",this);return}e=e.material.map;break;default:if(e[n]===void 0){Fe("PropertyBinding: Can not bind to objectName of node undefined.",this);return}e=e[n]}if(c!==void 0){if(e[c]===void 0){Fe("PropertyBinding: Trying to bind to objectIndex of objectName, but is undefined.",this,e);return}e=e[c]}}let a=e[r];if(a===void 0){let c=t.nodeName;Fe("PropertyBinding: Trying to update property for track: "+c+"."+r+" but it wasn't found.",e);return}let o=this.Versioning.None;this.targetObject=e,e.isMaterial===!0?o=this.Versioning.NeedsUpdate:e.isObject3D===!0&&(o=this.Versioning.MatrixWorldNeedsUpdate);let l=this.BindingType.Direct;if(s!==void 0){if(r==="morphTargetInfluences"){if(!e.geometry){Fe("PropertyBinding: Can not bind to morphTargetInfluences because node does not have a geometry.",this);return}if(!e.geometry.morphAttributes){Fe("PropertyBinding: Can not bind to morphTargetInfluences because node does not have a geometry.morphAttributes.",this);return}e.morphTargetDictionary[s]!==void 0&&(s=e.morphTargetDictionary[s])}l=this.BindingType.ArrayElement,this.resolvedProperty=a,this.propertyIndex=s}else a.fromArray!==void 0&&a.toArray!==void 0?(l=this.BindingType.HasFromToArray,this.resolvedProperty=a):Array.isArray(a)?(l=this.BindingType.EntireArray,this.resolvedProperty=a):this.propertyName=r;this.getValue=this.GetterByBindingType[l],this.setValue=this.SetterByBindingTypeAndVersioning[l][o]}unbind(){this.node=null,this.getValue=this._getValue_unbound,this.setValue=this._setValue_unbound}};mt.Composite=Mu;mt.prototype.BindingType={Direct:0,EntireArray:1,ArrayElement:2,HasFromToArray:3};mt.prototype.Versioning={None:0,NeedsUpdate:1,MatrixWorldNeedsUpdate:2};mt.prototype.GetterByBindingType=[mt.prototype._getValue_direct,mt.prototype._getValue_array,mt.prototype._getValue_arrayElement,mt.prototype._getValue_toArray];mt.prototype.SetterByBindingTypeAndVersioning=[[mt.prototype._setValue_direct,mt.prototype._setValue_direct_setNeedsUpdate,mt.prototype._setValue_direct_setMatrixWorldNeedsUpdate],[mt.prototype._setValue_array,mt.prototype._setValue_array_setNeedsUpdate,mt.prototype._setValue_array_setMatrixWorldNeedsUpdate],[mt.prototype._setValue_arrayElement,mt.prototype._setValue_arrayElement_setNeedsUpdate,mt.prototype._setValue_arrayElement_setMatrixWorldNeedsUpdate],[mt.prototype._setValue_fromArray,mt.prototype._setValue_fromArray_setNeedsUpdate,mt.prototype._setValue_fromArray_setMatrixWorldNeedsUpdate]];var DE=new Float32Array(1);var tr=class extends Ar{constructor(e,t,n=1){super(e,t),this.isInstancedInterleavedBuffer=!0,this.meshPerAttribute=n}copy(e){return super.copy(e),this.meshPerAttribute=e.meshPerAttribute,this}clone(e){let t=super.clone(e);return t.meshPerAttribute=this.meshPerAttribute,t}toJSON(e){let t=super.toJSON(e);return t.isInstancedInterleavedBuffer=!0,t.meshPerAttribute=this.meshPerAttribute,t}};var ir=class{constructor(e=1,t=0,n=0){this.radius=e,this.phi=t,this.theta=n}set(e,t,n){return this.radius=e,this.phi=t,this.theta=n,this}copy(e){return this.radius=e.radius,this.phi=e.phi,this.theta=e.theta,this}makeSafe(){return this.phi=ze(this.phi,1e-6,Math.PI-1e-6),this}setFromVector3(e){return this.setFromCartesianCoords(e.x,e.y,e.z)}setFromCartesianCoords(e,t,n){return this.radius=Math.sqrt(e*e+t*t+n*n),this.radius===0?(this.theta=0,this.phi=0):(this.theta=Math.atan2(e,n),this.phi=Math.acos(ze(t/this.radius,-1,1))),this}clone(){return new this.constructor().copy(this)}};var rd=class rd{constructor(e,t,n,r){this.elements=[1,0,0,1],e!==void 0&&this.set(e,t,n,r)}identity(){return this.set(1,0,0,1),this}fromArray(e,t=0){for(let n=0;n<4;n++)this.elements[n]=e[n+t];return this}set(e,t,n,r){let s=this.elements;return s[0]=e,s[2]=t,s[1]=n,s[3]=r,this}};rd.prototype.isMatrix2=!0;var Ol=rd;var mm=new P,cl=new P,gs=new P,ys=new P,du=new P,Ax=new P,Cx=new P,Fa=class{constructor(e=new P,t=new P){this.start=e,this.end=t}set(e,t){return this.start.copy(e),this.end.copy(t),this}copy(e){return this.start.copy(e.start),this.end.copy(e.end),this}getCenter(e){return e.addVectors(this.start,this.end).multiplyScalar(.5)}delta(e){return e.subVectors(this.end,this.start)}distanceSq(){return this.start.distanceToSquared(this.end)}distance(){return this.start.distanceTo(this.end)}at(e,t){return this.delta(t).multiplyScalar(e).add(this.start)}closestPointToPointParameter(e,t){mm.subVectors(e,this.start),cl.subVectors(this.end,this.start);let n=cl.dot(cl);if(n===0)return 0;let s=cl.dot(mm)/n;return t&&(s=ze(s,0,1)),s}closestPointToPoint(e,t,n){let r=this.closestPointToPointParameter(e,t);return this.delta(n).multiplyScalar(r).add(this.start)}distanceSqToLine3(e,t=Ax,n=Cx){let r=10000000000000001e-32,s,a,o=this.start,l=e.start,c=this.end,h=e.end;gs.subVectors(c,o),ys.subVectors(h,l),du.subVectors(o,l);let u=gs.dot(gs),d=ys.dot(ys),f=ys.dot(du);if(u<=r&&d<=r)return t.copy(o),n.copy(l),t.sub(n),t.dot(t);if(u<=r)s=0,a=f/d,a=ze(a,0,1);else{let p=gs.dot(du);if(d<=r)a=0,s=ze(-p/u,0,1);else{let y=gs.dot(ys),m=u*d-y*y;m!==0?s=ze((y*f-p*d)/m,0,1):s=0,a=(y*s+f)/d,a<0?(a=0,s=ze(-p/u,0,1)):a>1&&(a=1,s=ze((y-p)/u,0,1))}}return t.copy(o).addScaledVector(gs,s),n.copy(l).addScaledVector(ys,a),t.distanceToSquared(n)}applyMatrix4(e){return this.start.applyMatrix4(e),this.end.applyMatrix4(e),this}equals(e){return e.start.equals(this.start)&&e.end.equals(this.end)}clone(){return new this.constructor().copy(this)}};var Ba=class extends jt{constructor(e,t=null){super(),this.object=e,this.domElement=t,this.enabled=!0,this.state=-1,this.keys={},this.mouseButtons={LEFT:null,MIDDLE:null,RIGHT:null},this.touches={ONE:null,TWO:null}}connect(e){this.domElement!==null&&this.disconnect(),this.domElement=e}disconnect(){}dispose(){}update(){}};function Rx(i,e){let t=i.image&&i.image.width?i.image.width/i.image.height:1;return t>e?(i.repeat.x=1,i.repeat.y=t/e,i.offset.x=0,i.offset.y=(1-i.repeat.y)/2):(i.repeat.x=e/t,i.repeat.y=1,i.offset.x=(1-i.repeat.x)/2,i.offset.y=0),i}function Px(i,e){let t=i.image&&i.image.width?i.image.width/i.image.height:1;return t>e?(i.repeat.x=e/t,i.repeat.y=1,i.offset.x=(1-i.repeat.x)/2,i.offset.y=0):(i.repeat.x=1,i.repeat.y=t/e,i.offset.x=0,i.offset.y=(1-i.repeat.y)/2),i}function Ix(i){return i.repeat.x=1,i.repeat.y=1,i.offset.x=0,i.offset.y=0,i}function Tc(i,e,t,n){let r=Lx(n);switch(t){case Xu:return i*e;case Os:return i*e/r.components*r.byteLength;case Xl:return i*e/r.components*r.byteLength;case Ln:return i*e*2/r.components*r.byteLength;case ql:return i*e*2/r.components*r.byteLength;case qu:return i*e*3/r.components*r.byteLength;case Ri:return i*e*4/r.components*r.byteLength;case Va:return i*e*4/r.components*r.byteLength;case Ga:case Ha:return Math.floor((i+3)/4)*Math.floor((e+3)/4)*8;case Wa:case Xa:return Math.floor((i+3)/4)*Math.floor((e+3)/4)*16;case Yl:case Zl:return Math.max(i,16)*Math.max(e,8)/4;case jl:case $l:return Math.max(i,8)*Math.max(e,8)/2;case Kl:case Jl:case ec:case tc:return Math.floor((i+3)/4)*Math.floor((e+3)/4)*8;case Ql:case qa:case ic:return Math.floor((i+3)/4)*Math.floor((e+3)/4)*16;case nc:return Math.floor((i+3)/4)*Math.floor((e+3)/4)*16;case rc:return Math.floor((i+4)/5)*Math.floor((e+3)/4)*16;case sc:return Math.floor((i+4)/5)*Math.floor((e+4)/5)*16;case ac:return Math.floor((i+5)/6)*Math.floor((e+4)/5)*16;case oc:return Math.floor((i+5)/6)*Math.floor((e+5)/6)*16;case lc:return Math.floor((i+7)/8)*Math.floor((e+4)/5)*16;case cc:return Math.floor((i+7)/8)*Math.floor((e+5)/6)*16;case hc:return Math.floor((i+7)/8)*Math.floor((e+7)/8)*16;case uc:return Math.floor((i+9)/10)*Math.floor((e+4)/5)*16;case dc:return Math.floor((i+9)/10)*Math.floor((e+5)/6)*16;case fc:return Math.floor((i+9)/10)*Math.floor((e+7)/8)*16;case pc:return Math.floor((i+9)/10)*Math.floor((e+9)/10)*16;case mc:return Math.floor((i+11)/12)*Math.floor((e+9)/10)*16;case gc:return Math.floor((i+11)/12)*Math.floor((e+11)/12)*16;case yc:case _c:case xc:return Math.ceil(i/4)*Math.ceil(e/4)*16;case vc:case bc:return Math.ceil(i/4)*Math.ceil(e/4)*8;case ja:case Sc:return Math.ceil(i/4)*Math.ceil(e/4)*16}throw new Error(`Unable to determine texture byte length for ${t} format.`)}function Lx(i){switch(i){case di:case Vu:return{byteLength:1,components:1};case Ns:case Gu:case ji:return{byteLength:2,components:1};case Hl:case Wl:return{byteLength:2,components:4};case qi:case Gl:case fi:return{byteLength:4,components:1};case Hu:case Wu:return{byteLength:4,components:3}}throw new Error(`THREE.TextureUtils: Unknown texture type ${i}.`)}var Fr=class{static contain(e,t){return Rx(e,t)}static cover(e,t){return Px(e,t)}static fill(e){return Ix(e)}static getByteLength(e,t,n,r){return Tc(e,t,n,r)}};typeof __THREE_DEVTOOLS__<"u"&&__THREE_DEVTOOLS__.dispatchEvent(new CustomEvent("register",{detail:{revision:"186"}}));typeof window<"u"&&(window.__THREE__?Ce("WARNING: Multiple instances of Three.js being imported."):window.__THREE__="186");function Sg(){let i=null,e=!1,t=null,n=null;function r(s,a){n=i.requestAnimationFrame(r),t(s,a)}return{start:function(){e!==!0&&t!==null&&i!==null&&(n=i.requestAnimationFrame(r),e=!0)},stop:function(){i!==null&&i.cancelAnimationFrame(n),e=!1},setAnimationLoop:function(s){t=s},setContext:function(s){i=s}}}function zx(i){let e=new WeakMap;function t(o,l){let c=o.array,h=o.usage,u=c.byteLength,d=i.createBuffer();i.bindBuffer(l,d),i.bufferData(l,c,h),o.onUploadCallback();let f;if(c instanceof Float32Array)f=i.FLOAT;else if(typeof Float16Array<"u"&&c instanceof Float16Array)f=i.HALF_FLOAT;else if(c instanceof Uint16Array)o.isFloat16BufferAttribute?f=i.HALF_FLOAT:f=i.UNSIGNED_SHORT;else if(c instanceof Int16Array)f=i.SHORT;else if(c instanceof Uint32Array)f=i.UNSIGNED_INT;else if(c instanceof Int32Array)f=i.INT;else if(c instanceof Int8Array)f=i.BYTE;else if(c instanceof Uint8Array)f=i.UNSIGNED_BYTE;else if(c instanceof Uint8ClampedArray)f=i.UNSIGNED_BYTE;else throw new Error("THREE.WebGLAttributes: Unsupported buffer data format: "+c);return{buffer:d,type:f,bytesPerElement:c.BYTES_PER_ELEMENT,version:o.version,size:u}}function n(o,l,c){let h=l.array,u=l.updateRanges;if(i.bindBuffer(c,o),u.length===0)i.bufferSubData(c,0,h);else{u.sort((f,p)=>f.start-p.start);let d=0;for(let f=1;f<u.length;f++){let p=u[d],y=u[f];y.start<=p.start+p.count+1?p.count=Math.max(p.count,y.start+y.count-p.start):(++d,u[d]=y)}u.length=d+1;for(let f=0,p=u.length;f<p;f++){let y=u[f];i.bufferSubData(c,y.start*h.BYTES_PER_ELEMENT,h,y.start,y.count)}l.clearUpdateRanges()}l.onUploadCallback()}function r(o){return o.isInterleavedBufferAttribute&&(o=o.data),e.get(o)}function s(o){o.isInterleavedBufferAttribute&&(o=o.data);let l=e.get(o);l&&(i.deleteBuffer(l.buffer),e.delete(o))}function a(o,l){if(o.isInterleavedBufferAttribute&&(o=o.data),o.isGLBufferAttribute){let h=e.get(o);(!h||h.version<o.version)&&e.set(o,{buffer:o.buffer,type:o.type,bytesPerElement:o.elementSize,version:o.version});return}let c=e.get(o);if(c===void 0)e.set(o,t(o,l));else if(c.version<o.version){if(c.size!==o.array.byteLength)throw new Error("THREE.WebGLAttributes: The size of the buffer attribute's array buffer does not match the original size. Resizing buffer attributes is not supported.");n(c.buffer,o,l),c.version=o.version}}return{get:r,remove:s,update:a}}var Vx=`#ifdef USE_ALPHAHASH
	if ( diffuseColor.a < getAlphaHashThreshold( vPosition ) ) discard;
#endif`,Gx=`#ifdef USE_ALPHAHASH
	const float ALPHA_HASH_SCALE = 0.05;
	float hash2D( vec2 value ) {
		return fract( 1.0e4 * sin( 17.0 * value.x + 0.1 * value.y ) * ( 0.1 + abs( sin( 13.0 * value.y + value.x ) ) ) );
	}
	float hash3D( vec3 value ) {
		return hash2D( vec2( hash2D( value.xy ), value.z ) );
	}
	float getAlphaHashThreshold( vec3 position ) {
		float maxDeriv = max(
			length( dFdx( position.xyz ) ),
			length( dFdy( position.xyz ) )
		);
		float pixScale = 1.0 / ( ALPHA_HASH_SCALE * maxDeriv );
		vec2 pixScales = vec2(
			exp2( floor( log2( pixScale ) ) ),
			exp2( ceil( log2( pixScale ) ) )
		);
		vec2 alpha = vec2(
			hash3D( floor( pixScales.x * position.xyz ) ),
			hash3D( floor( pixScales.y * position.xyz ) )
		);
		float lerpFactor = fract( log2( pixScale ) );
		float x = ( 1.0 - lerpFactor ) * alpha.x + lerpFactor * alpha.y;
		float a = min( lerpFactor, 1.0 - lerpFactor );
		vec3 cases = vec3(
			x * x / ( 2.0 * a * ( 1.0 - a ) ),
			( x - 0.5 * a ) / ( 1.0 - a ),
			1.0 - ( ( 1.0 - x ) * ( 1.0 - x ) / ( 2.0 * a * ( 1.0 - a ) ) )
		);
		float threshold = ( x < ( 1.0 - a ) )
			? ( ( x < a ) ? cases.x : cases.y )
			: cases.z;
		return clamp( threshold , 1.0e-6, 1.0 );
	}
#endif`,Hx=`#ifdef USE_ALPHAMAP
	diffuseColor.a *= texture2D( alphaMap, vAlphaMapUv ).g;
#endif`,Wx=`#ifdef USE_ALPHAMAP
	uniform sampler2D alphaMap;
#endif`,Xx=`#ifdef USE_ALPHATEST
	#ifdef ALPHA_TO_COVERAGE
	diffuseColor.a = smoothstep( alphaTest, alphaTest + fwidth( diffuseColor.a ), diffuseColor.a );
	if ( diffuseColor.a == 0.0 ) discard;
	#else
	if ( diffuseColor.a < alphaTest ) discard;
	#endif
#endif`,qx=`#ifdef USE_ALPHATEST
	uniform float alphaTest;
#endif`,jx=`#ifdef USE_AOMAP
	float ambientOcclusion = ( texture2D( aoMap, vAoMapUv ).r - 1.0 ) * aoMapIntensity + 1.0;
	reflectedLight.indirectDiffuse *= ambientOcclusion;
	#if defined( USE_CLEARCOAT ) 
		clearcoatSpecularIndirect *= ambientOcclusion;
	#endif
	#if defined( USE_SHEEN ) 
		sheenSpecularIndirect *= ambientOcclusion;
	#endif
	#if defined( USE_ENVMAP ) && defined( STANDARD )
		float dotNV = saturate( dot( geometryNormal, geometryViewDir ) );
		reflectedLight.indirectSpecular *= computeSpecularOcclusion( dotNV, ambientOcclusion, material.roughness );
	#endif
#endif`,Yx=`#ifdef USE_AOMAP
	uniform sampler2D aoMap;
	uniform float aoMapIntensity;
#endif`,$x=`#ifdef USE_BATCHING
	#if ! defined( GL_ANGLE_multi_draw )
	#define gl_DrawID _gl_DrawID
	uniform int _gl_DrawID;
	#endif
	uniform highp sampler2D batchingTexture;
	uniform highp usampler2D batchingIdTexture;
	mat4 getBatchingMatrix( const in float i ) {
		int size = textureSize( batchingTexture, 0 ).x;
		int j = int( i ) * 4;
		int x = j % size;
		int y = j / size;
		vec4 v1 = texelFetch( batchingTexture, ivec2( x, y ), 0 );
		vec4 v2 = texelFetch( batchingTexture, ivec2( x + 1, y ), 0 );
		vec4 v3 = texelFetch( batchingTexture, ivec2( x + 2, y ), 0 );
		vec4 v4 = texelFetch( batchingTexture, ivec2( x + 3, y ), 0 );
		return mat4( v1, v2, v3, v4 );
	}
	float getIndirectIndex( const in int i ) {
		int size = textureSize( batchingIdTexture, 0 ).x;
		int x = i % size;
		int y = i / size;
		return float( texelFetch( batchingIdTexture, ivec2( x, y ), 0 ).r );
	}
#endif
#ifdef USE_BATCHING_COLOR
	uniform sampler2D batchingColorTexture;
	vec4 getBatchingColor( const in float i ) {
		int size = textureSize( batchingColorTexture, 0 ).x;
		int j = int( i );
		int x = j % size;
		int y = j / size;
		return texelFetch( batchingColorTexture, ivec2( x, y ), 0 );
	}
#endif`,Zx=`#ifdef USE_BATCHING
	mat4 batchingMatrix = getBatchingMatrix( getIndirectIndex( gl_DrawID ) );
#endif`,Kx=`vec3 transformed = vec3( position );
#ifdef USE_ALPHAHASH
	vPosition = vec3( position );
#endif`,Jx=`vec3 objectNormal = vec3( normal );
#ifdef USE_TANGENT
	vec3 objectTangent = vec3( tangent.xyz );
#endif`,Qx=`float G_BlinnPhong_Implicit( ) {
	return 0.25;
}
float D_BlinnPhong( const in float shininess, const in float dotNH ) {
	return RECIPROCAL_PI * ( shininess * 0.5 + 1.0 ) * pow( dotNH, shininess );
}
vec3 BRDF_BlinnPhong( const in vec3 lightDir, const in vec3 viewDir, const in vec3 normal, const in vec3 specularColor, const in float shininess ) {
	vec3 halfDir = normalize( lightDir + viewDir );
	float dotNH = saturate( dot( normal, halfDir ) );
	float dotVH = saturate( dot( viewDir, halfDir ) );
	vec3 F = F_Schlick( specularColor, 1.0, dotVH );
	float G = G_BlinnPhong_Implicit( );
	float D = D_BlinnPhong( shininess, dotNH );
	return F * ( G * D );
} // validated`,ev=`#ifdef USE_IRIDESCENCE
	const mat3 XYZ_TO_REC709 = mat3(
		 3.2404542, -0.9692660,  0.0556434,
		-1.5371385,  1.8760108, -0.2040259,
		-0.4985314,  0.0415560,  1.0572252
	);
	vec3 Fresnel0ToIor( vec3 fresnel0 ) {
		vec3 sqrtF0 = sqrt( fresnel0 );
		return ( vec3( 1.0 ) + sqrtF0 ) / ( vec3( 1.0 ) - sqrtF0 );
	}
	vec3 IorToFresnel0( vec3 transmittedIor, float incidentIor ) {
		return pow2( ( transmittedIor - vec3( incidentIor ) ) / ( transmittedIor + vec3( incidentIor ) ) );
	}
	float IorToFresnel0( float transmittedIor, float incidentIor ) {
		return pow2( ( transmittedIor - incidentIor ) / ( transmittedIor + incidentIor ));
	}
	vec3 evalSensitivity( float OPD, vec3 shift ) {
		float phase = 2.0 * PI * OPD * 1.0e-9;
		vec3 val = vec3( 5.4856e-13, 4.4201e-13, 5.2481e-13 );
		vec3 pos = vec3( 1.6810e+06, 1.7953e+06, 2.2084e+06 );
		vec3 var = vec3( 4.3278e+09, 9.3046e+09, 6.6121e+09 );
		vec3 xyz = val * sqrt( 2.0 * PI * var ) * cos( pos * phase + shift ) * exp( - pow2( phase ) * var );
		xyz.x += 9.7470e-14 * sqrt( 2.0 * PI * 4.5282e+09 ) * cos( 2.2399e+06 * phase + shift[ 0 ] ) * exp( - 4.5282e+09 * pow2( phase ) );
		xyz /= 1.0685e-7;
		vec3 rgb = XYZ_TO_REC709 * xyz;
		return rgb;
	}
	vec3 evalIridescence( float outsideIOR, float eta2, float cosTheta1, float thinFilmThickness, vec3 baseF0 ) {
		vec3 I;
		float iridescenceIOR = mix( outsideIOR, eta2, smoothstep( 0.0, 0.03, thinFilmThickness ) );
		float sinTheta2Sq = pow2( outsideIOR / iridescenceIOR ) * ( 1.0 - pow2( cosTheta1 ) );
		float cosTheta2Sq = 1.0 - sinTheta2Sq;
		if ( cosTheta2Sq < 0.0 ) {
			return vec3( 1.0 );
		}
		float cosTheta2 = sqrt( cosTheta2Sq );
		float R0 = IorToFresnel0( iridescenceIOR, outsideIOR );
		float R12 = F_Schlick( R0, 1.0, cosTheta1 );
		float T121 = 1.0 - R12;
		float phi12 = 0.0;
		if ( iridescenceIOR < outsideIOR ) phi12 = PI;
		float phi21 = PI - phi12;
		vec3 baseIOR = Fresnel0ToIor( clamp( baseF0, 0.0, 0.9999 ) );		vec3 R1 = IorToFresnel0( baseIOR, iridescenceIOR );
		vec3 R23 = F_Schlick( R1, 1.0, cosTheta2 );
		vec3 phi23 = vec3( 0.0 );
		if ( baseIOR[ 0 ] < iridescenceIOR ) phi23[ 0 ] = PI;
		if ( baseIOR[ 1 ] < iridescenceIOR ) phi23[ 1 ] = PI;
		if ( baseIOR[ 2 ] < iridescenceIOR ) phi23[ 2 ] = PI;
		float OPD = 2.0 * iridescenceIOR * thinFilmThickness * cosTheta2;
		vec3 phi = vec3( phi21 ) + phi23;
		vec3 R123 = clamp( R12 * R23, 1e-5, 0.9999 );
		vec3 r123 = sqrt( R123 );
		vec3 Rs = pow2( T121 ) * R23 / ( vec3( 1.0 ) - R123 );
		vec3 C0 = R12 + Rs;
		I = C0;
		vec3 Cm = Rs - T121;
		for ( int m = 1; m <= 2; ++ m ) {
			Cm *= r123;
			vec3 Sm = 2.0 * evalSensitivity( float( m ) * OPD, float( m ) * phi );
			I += Cm * Sm;
		}
		return max( I, vec3( 0.0 ) );
	}
#endif`,tv=`#ifdef USE_BUMPMAP
	uniform sampler2D bumpMap;
	uniform float bumpScale;
	vec2 dHdxy_fwd() {
		vec2 dSTdx = dFdx( vBumpMapUv );
		vec2 dSTdy = dFdy( vBumpMapUv );
		float Hll = bumpScale * texture2D( bumpMap, vBumpMapUv ).x;
		float dBx = bumpScale * texture2D( bumpMap, vBumpMapUv + dSTdx ).x - Hll;
		float dBy = bumpScale * texture2D( bumpMap, vBumpMapUv + dSTdy ).x - Hll;
		return vec2( dBx, dBy );
	}
	vec3 perturbNormalArb( vec3 surf_pos, vec3 surf_norm, vec2 dHdxy, float faceDirection ) {
		vec3 vSigmaX = normalize( dFdx( surf_pos.xyz ) );
		vec3 vSigmaY = normalize( dFdy( surf_pos.xyz ) );
		vec3 vN = surf_norm;
		vec3 R1 = cross( vSigmaY, vN );
		vec3 R2 = cross( vN, vSigmaX );
		float fDet = dot( vSigmaX, R1 ) * faceDirection;
		vec3 vGrad = sign( fDet ) * ( dHdxy.x * R1 + dHdxy.y * R2 );
		return normalize( abs( fDet ) * surf_norm - vGrad );
	}
#endif`,iv=`#if NUM_CLIPPING_PLANES > 0
	vec4 plane;
	#ifdef ALPHA_TO_COVERAGE
		float distanceToPlane, distanceGradient;
		float clipOpacity = 1.0;
		#pragma unroll_loop_start
		for ( int i = 0; i < UNION_CLIPPING_PLANES; i ++ ) {
			plane = clippingPlanes[ i ];
			distanceToPlane = - dot( vClipPosition, plane.xyz ) + plane.w;
			distanceGradient = fwidth( distanceToPlane ) / 2.0;
			clipOpacity *= smoothstep( - distanceGradient, distanceGradient, distanceToPlane );
			if ( clipOpacity == 0.0 ) discard;
		}
		#pragma unroll_loop_end
		#if UNION_CLIPPING_PLANES < NUM_CLIPPING_PLANES
			float unionClipOpacity = 1.0;
			#pragma unroll_loop_start
			for ( int i = UNION_CLIPPING_PLANES; i < NUM_CLIPPING_PLANES; i ++ ) {
				plane = clippingPlanes[ i ];
				distanceToPlane = - dot( vClipPosition, plane.xyz ) + plane.w;
				distanceGradient = fwidth( distanceToPlane ) / 2.0;
				unionClipOpacity *= 1.0 - smoothstep( - distanceGradient, distanceGradient, distanceToPlane );
			}
			#pragma unroll_loop_end
			clipOpacity *= 1.0 - unionClipOpacity;
		#endif
		diffuseColor.a *= clipOpacity;
		if ( diffuseColor.a == 0.0 ) discard;
	#else
		#pragma unroll_loop_start
		for ( int i = 0; i < UNION_CLIPPING_PLANES; i ++ ) {
			plane = clippingPlanes[ i ];
			if ( dot( vClipPosition, plane.xyz ) > plane.w ) discard;
		}
		#pragma unroll_loop_end
		#if UNION_CLIPPING_PLANES < NUM_CLIPPING_PLANES
			bool clipped = true;
			#pragma unroll_loop_start
			for ( int i = UNION_CLIPPING_PLANES; i < NUM_CLIPPING_PLANES; i ++ ) {
				plane = clippingPlanes[ i ];
				clipped = ( dot( vClipPosition, plane.xyz ) > plane.w ) && clipped;
			}
			#pragma unroll_loop_end
			if ( clipped ) discard;
		#endif
	#endif
#endif`,nv=`#if NUM_CLIPPING_PLANES > 0
	varying vec3 vClipPosition;
	uniform vec4 clippingPlanes[ NUM_CLIPPING_PLANES ];
#endif`,rv=`#if NUM_CLIPPING_PLANES > 0
	varying vec3 vClipPosition;
#endif`,sv=`#if NUM_CLIPPING_PLANES > 0
	vClipPosition = - mvPosition.xyz;
#endif`,av=`#if defined( USE_COLOR ) || defined( USE_COLOR_ALPHA )
	diffuseColor *= vColor;
#endif`,ov=`#if defined( USE_COLOR ) || defined( USE_COLOR_ALPHA )
	varying vec4 vColor;
#endif`,lv=`#if defined( USE_COLOR ) || defined( USE_COLOR_ALPHA ) || defined( USE_INSTANCING_COLOR ) || defined( USE_BATCHING_COLOR )
	varying vec4 vColor;
#endif`,cv=`#if defined( USE_COLOR ) || defined( USE_COLOR_ALPHA ) || defined( USE_INSTANCING_COLOR ) || defined( USE_BATCHING_COLOR )
	vColor = vec4( 1.0 );
#endif
#ifdef USE_COLOR_ALPHA
	vColor *= color;
#elif defined( USE_COLOR )
	vColor.rgb *= color;
#endif
#ifdef USE_INSTANCING_COLOR
	vColor.rgb *= instanceColor.rgb;
#endif
#ifdef USE_BATCHING_COLOR
	vColor *= getBatchingColor( getIndirectIndex( gl_DrawID ) );
#endif`,hv=`#define PI 3.141592653589793
#define PI2 6.283185307179586
#define PI_HALF 1.5707963267948966
#define RECIPROCAL_PI 0.3183098861837907
#define RECIPROCAL_PI2 0.15915494309189535
#define EPSILON 1e-6
#ifndef saturate
#define saturate( a ) clamp( a, 0.0, 1.0 )
#endif
#define whiteComplement( a ) ( 1.0 - saturate( a ) )
float pow2( const in float x ) { return x*x; }
vec3 pow2( const in vec3 x ) { return x*x; }
float pow3( const in float x ) { return x*x*x; }
float pow4( const in float x ) { float x2 = x*x; return x2*x2; }
float max3( const in vec3 v ) { return max( max( v.x, v.y ), v.z ); }
float average( const in vec3 v ) { return dot( v, vec3( 0.3333333 ) ); }
highp float rand( const in vec2 uv ) {
	const highp float a = 12.9898, b = 78.233, c = 43758.5453;
	highp float dt = dot( uv.xy, vec2( a,b ) ), sn = mod( dt, PI );
	return fract( sin( sn ) * c );
}
#ifdef HIGH_PRECISION
	float precisionSafeLength( vec3 v ) { return length( v ); }
#else
	float precisionSafeLength( vec3 v ) {
		float maxComponent = max3( abs( v ) );
		return length( v / maxComponent ) * maxComponent;
	}
#endif
struct IncidentLight {
	vec3 color;
	vec3 direction;
	bool visible;
};
struct ReflectedLight {
	vec3 directDiffuse;
	vec3 directSpecular;
	vec3 indirectDiffuse;
	vec3 indirectSpecular;
};
#ifdef USE_ALPHAHASH
	varying vec3 vPosition;
#endif
vec3 transformDirection( in vec3 dir, in mat4 matrix ) {
	return normalize( ( matrix * vec4( dir, 0.0 ) ).xyz );
}
#define inverseTransformDirection transformDirectionByInverseViewMatrix
vec3 transformNormalByInverseViewMatrix( in vec3 normal, in mat4 viewMatrix ) {
	return normalize( ( vec4( normal, 0.0 ) * viewMatrix ).xyz );
}
vec3 transformDirectionByInverseViewMatrix( in vec3 dir, in mat4 viewMatrix ) {
	return normalize( ( vec4( dir, 0.0 ) * viewMatrix ).xyz );
}
bool isPerspectiveMatrix( mat4 m ) {
	return m[ 2 ][ 3 ] == - 1.0;
}
vec2 equirectUv( in vec3 dir ) {
	float u = atan( dir.z, dir.x ) * RECIPROCAL_PI2 + 0.5;
	float v = asin( clamp( dir.y, - 1.0, 1.0 ) ) * RECIPROCAL_PI + 0.5;
	return vec2( u, v );
}
vec3 BRDF_Lambert( const in vec3 diffuseColor ) {
	return RECIPROCAL_PI * diffuseColor;
}
vec3 F_Schlick( const in vec3 f0, const in float f90, const in float dotVH ) {
	float fresnel = exp2( ( - 5.55473 * dotVH - 6.98316 ) * dotVH );
	return f0 * ( 1.0 - fresnel ) + ( f90 * fresnel );
}
float F_Schlick( const in float f0, const in float f90, const in float dotVH ) {
	float fresnel = exp2( ( - 5.55473 * dotVH - 6.98316 ) * dotVH );
	return f0 * ( 1.0 - fresnel ) + ( f90 * fresnel );
} // validated`,uv=`#ifdef ENVMAP_TYPE_CUBE_UV
	#define cubeUV_minMipLevel 4.0
	#define cubeUV_minTileSize 16.0
	float getFace( vec3 direction ) {
		vec3 absDirection = abs( direction );
		float face = - 1.0;
		if ( absDirection.x > absDirection.z ) {
			if ( absDirection.x > absDirection.y )
				face = direction.x > 0.0 ? 0.0 : 3.0;
			else
				face = direction.y > 0.0 ? 1.0 : 4.0;
		} else {
			if ( absDirection.z > absDirection.y )
				face = direction.z > 0.0 ? 2.0 : 5.0;
			else
				face = direction.y > 0.0 ? 1.0 : 4.0;
		}
		return face;
	}
	vec2 getUV( vec3 direction, float face ) {
		vec2 uv;
		if ( face == 0.0 ) {
			uv = vec2( direction.z, direction.y ) / abs( direction.x );
		} else if ( face == 1.0 ) {
			uv = vec2( - direction.x, - direction.z ) / abs( direction.y );
		} else if ( face == 2.0 ) {
			uv = vec2( - direction.x, direction.y ) / abs( direction.z );
		} else if ( face == 3.0 ) {
			uv = vec2( - direction.z, direction.y ) / abs( direction.x );
		} else if ( face == 4.0 ) {
			uv = vec2( - direction.x, direction.z ) / abs( direction.y );
		} else {
			uv = vec2( direction.x, direction.y ) / abs( direction.z );
		}
		return 0.5 * ( uv + 1.0 );
	}
	vec3 bilinearCubeUV( sampler2D envMap, vec3 direction, float mipInt ) {
		float face = getFace( direction );
		float filterInt = max( cubeUV_minMipLevel - mipInt, 0.0 );
		mipInt = max( mipInt, cubeUV_minMipLevel );
		float faceSize = exp2( mipInt );
		highp vec2 uv = getUV( direction, face ) * ( faceSize - 2.0 ) + 1.0;
		if ( face > 2.0 ) {
			uv.y += faceSize;
			face -= 3.0;
		}
		uv.x += face * faceSize;
		uv.x += filterInt * 3.0 * cubeUV_minTileSize;
		uv.y += 4.0 * ( exp2( CUBEUV_MAX_MIP ) - faceSize );
		uv.x *= CUBEUV_TEXEL_WIDTH;
		uv.y *= CUBEUV_TEXEL_HEIGHT;
		#ifdef texture2DGradEXT
			return texture2DGradEXT( envMap, uv, vec2( 0.0 ), vec2( 0.0 ) ).rgb;
		#else
			return texture2D( envMap, uv ).rgb;
		#endif
	}
	#define cubeUV_r0 1.0
	#define cubeUV_m0 - 2.0
	#define cubeUV_r1 0.8
	#define cubeUV_m1 - 1.0
	#define cubeUV_r4 0.4
	#define cubeUV_m4 2.0
	#define cubeUV_r5 0.305
	#define cubeUV_m5 3.0
	#define cubeUV_r6 0.21
	#define cubeUV_m6 4.0
	float roughnessToMip( float roughness ) {
		float mip = 0.0;
		if ( roughness >= cubeUV_r1 ) {
			mip = ( cubeUV_r0 - roughness ) * ( cubeUV_m1 - cubeUV_m0 ) / ( cubeUV_r0 - cubeUV_r1 ) + cubeUV_m0;
		} else if ( roughness >= cubeUV_r4 ) {
			mip = ( cubeUV_r1 - roughness ) * ( cubeUV_m4 - cubeUV_m1 ) / ( cubeUV_r1 - cubeUV_r4 ) + cubeUV_m1;
		} else if ( roughness >= cubeUV_r5 ) {
			mip = ( cubeUV_r4 - roughness ) * ( cubeUV_m5 - cubeUV_m4 ) / ( cubeUV_r4 - cubeUV_r5 ) + cubeUV_m4;
		} else if ( roughness >= cubeUV_r6 ) {
			mip = ( cubeUV_r5 - roughness ) * ( cubeUV_m6 - cubeUV_m5 ) / ( cubeUV_r5 - cubeUV_r6 ) + cubeUV_m5;
		} else {
			mip = - 2.0 * log2( 1.16 * roughness );		}
		return mip;
	}
	vec4 textureCubeUV( sampler2D envMap, vec3 sampleDir, float roughness ) {
		float mip = clamp( roughnessToMip( roughness ), cubeUV_m0, CUBEUV_MAX_MIP );
		float mipF = fract( mip );
		float mipInt = floor( mip );
		vec3 color0 = bilinearCubeUV( envMap, sampleDir, mipInt );
		if ( mipF == 0.0 ) {
			return vec4( color0, 1.0 );
		} else {
			vec3 color1 = bilinearCubeUV( envMap, sampleDir, mipInt + 1.0 );
			return vec4( mix( color0, color1, mipF ), 1.0 );
		}
	}
#endif`,dv=`vec3 transformedNormal = objectNormal;
#ifdef USE_TANGENT
	vec3 transformedTangent = objectTangent;
#endif
#ifdef USE_BATCHING
	mat3 bm = mat3( batchingMatrix );
	transformedNormal /= vec3( dot( bm[ 0 ], bm[ 0 ] ), dot( bm[ 1 ], bm[ 1 ] ), dot( bm[ 2 ], bm[ 2 ] ) );
	transformedNormal = bm * transformedNormal;
	#ifdef USE_TANGENT
		transformedTangent = bm * transformedTangent;
	#endif
#endif
#ifdef USE_INSTANCING
	mat3 im = mat3( instanceMatrix );
	transformedNormal /= vec3( dot( im[ 0 ], im[ 0 ] ), dot( im[ 1 ], im[ 1 ] ), dot( im[ 2 ], im[ 2 ] ) );
	transformedNormal = im * transformedNormal;
	#ifdef USE_TANGENT
		transformedTangent = im * transformedTangent;
	#endif
#endif
transformedNormal = normalMatrix * transformedNormal;
#ifdef FLIP_SIDED
	transformedNormal = - transformedNormal;
#endif
#ifdef USE_TANGENT
	transformedTangent = ( modelViewMatrix * vec4( transformedTangent, 0.0 ) ).xyz;
#endif`,fv=`#ifdef USE_DISPLACEMENTMAP
	uniform sampler2D displacementMap;
	uniform float displacementScale;
	uniform float displacementBias;
#endif`,pv=`#ifdef USE_DISPLACEMENTMAP
	transformed += normalize( objectNormal ) * ( texture2D( displacementMap, vDisplacementMapUv ).x * displacementScale + displacementBias );
#endif`,mv=`#ifdef USE_EMISSIVEMAP
	vec4 emissiveColor = texture2D( emissiveMap, vEmissiveMapUv );
	#ifdef DECODE_VIDEO_TEXTURE_EMISSIVE
		emissiveColor = sRGBTransferEOTF( emissiveColor );
	#endif
	totalEmissiveRadiance *= emissiveColor.rgb;
#endif`,gv=`#ifdef USE_EMISSIVEMAP
	uniform sampler2D emissiveMap;
#endif`,yv="gl_FragColor = linearToOutputTexel( gl_FragColor );",_v=`vec4 LinearTransferOETF( in vec4 value ) {
	return value;
}
vec4 sRGBTransferEOTF( in vec4 value ) {
	return vec4( mix( pow( value.rgb * 0.9478672986 + vec3( 0.0521327014 ), vec3( 2.4 ) ), value.rgb * 0.0773993808, vec3( lessThanEqual( value.rgb, vec3( 0.04045 ) ) ) ), value.a );
}
vec4 sRGBTransferOETF( in vec4 value ) {
	return vec4( mix( pow( value.rgb, vec3( 0.41666 ) ) * 1.055 - vec3( 0.055 ), value.rgb * 12.92, vec3( lessThanEqual( value.rgb, vec3( 0.0031308 ) ) ) ), value.a );
}`,xv=`#ifdef USE_ENVMAP
	#ifdef ENV_WORLDPOS
		vec3 cameraToFrag;
		if ( isOrthographic ) {
			cameraToFrag = normalize( vec3( - viewMatrix[ 0 ][ 2 ], - viewMatrix[ 1 ][ 2 ], - viewMatrix[ 2 ][ 2 ] ) );
		} else {
			cameraToFrag = normalize( vWorldPosition - cameraPosition );
		}
		vec3 worldNormal = transformNormalByInverseViewMatrix( normal, viewMatrix );
		#ifdef ENVMAP_MODE_REFLECTION
			vec3 reflectVec = reflect( cameraToFrag, worldNormal );
		#else
			vec3 reflectVec = refract( cameraToFrag, worldNormal, refractionRatio );
		#endif
	#else
		vec3 reflectVec = vReflect;
	#endif
	#ifdef ENVMAP_TYPE_CUBE
		vec4 envColor = textureCube( envMap, envMapRotation * reflectVec );
		#ifdef ENVMAP_BLENDING_MULTIPLY
			outgoingLight = mix( outgoingLight, outgoingLight * envColor.xyz, specularStrength * reflectivity );
		#elif defined( ENVMAP_BLENDING_MIX )
			outgoingLight = mix( outgoingLight, envColor.xyz, specularStrength * reflectivity );
		#elif defined( ENVMAP_BLENDING_ADD )
			outgoingLight += envColor.xyz * specularStrength * reflectivity;
		#endif
	#endif
#endif`,vv=`#ifdef USE_ENVMAP
	uniform float envMapIntensity;
	uniform mat3 envMapRotation;
	#ifdef ENVMAP_TYPE_CUBE
		uniform samplerCube envMap;
	#else
		uniform sampler2D envMap;
	#endif
#endif`,bv=`#ifdef USE_ENVMAP
	uniform float reflectivity;
	#if defined( USE_BUMPMAP ) || defined( USE_NORMALMAP ) || defined( PHONG ) || defined( LAMBERT )
		#define ENV_WORLDPOS
	#endif
	#ifdef ENV_WORLDPOS
		varying vec3 vWorldPosition;
		uniform float refractionRatio;
	#else
		varying vec3 vReflect;
	#endif
#endif`,Sv=`#ifdef USE_ENVMAP
	#if defined( USE_BUMPMAP ) || defined( USE_NORMALMAP ) || defined( PHONG ) || defined( LAMBERT )
		#define ENV_WORLDPOS
	#endif
	#ifdef ENV_WORLDPOS
		
		varying vec3 vWorldPosition;
	#else
		varying vec3 vReflect;
		uniform float refractionRatio;
	#endif
#endif`,Mv=`#ifdef USE_ENVMAP
	#ifdef ENV_WORLDPOS
		vWorldPosition = worldPosition.xyz;
	#else
		vec3 cameraToVertex;
		if ( isOrthographic ) {
			cameraToVertex = normalize( vec3( - viewMatrix[ 0 ][ 2 ], - viewMatrix[ 1 ][ 2 ], - viewMatrix[ 2 ][ 2 ] ) );
		} else {
			cameraToVertex = normalize( worldPosition.xyz - cameraPosition );
		}
		vec3 worldNormal = transformNormalByInverseViewMatrix( transformedNormal, viewMatrix );
		#ifdef ENVMAP_MODE_REFLECTION
			vReflect = reflect( cameraToVertex, worldNormal );
		#else
			vReflect = refract( cameraToVertex, worldNormal, refractionRatio );
		#endif
	#endif
#endif`,wv=`#ifdef USE_FOG
	vFogDepth = - mvPosition.z;
#endif`,Tv=`#ifdef USE_FOG
	varying float vFogDepth;
#endif`,Ev=`#ifdef USE_FOG
	#ifdef FOG_EXP2
		float fogFactor = 1.0 - exp( - fogDensity * fogDensity * vFogDepth * vFogDepth );
	#else
		float fogFactor = smoothstep( fogNear, fogFar, vFogDepth );
	#endif
	gl_FragColor.rgb = mix( gl_FragColor.rgb, fogColor, fogFactor );
#endif`,Av=`#ifdef USE_FOG
	uniform vec3 fogColor;
	varying float vFogDepth;
	#ifdef FOG_EXP2
		uniform float fogDensity;
	#else
		uniform float fogNear;
		uniform float fogFar;
	#endif
#endif`,Cv=`#ifdef USE_GRADIENTMAP
	uniform sampler2D gradientMap;
#endif
vec3 getGradientIrradiance( vec3 normal, vec3 lightDirection ) {
	float dotNL = dot( normal, lightDirection );
	vec2 coord = vec2( dotNL * 0.5 + 0.5, 0.0 );
	#ifdef USE_GRADIENTMAP
		return vec3( texture2D( gradientMap, coord ).r );
	#else
		vec2 fw = fwidth( coord ) * 0.5;
		return mix( vec3( 0.7 ), vec3( 1.0 ), smoothstep( 0.7 - fw.x, 0.7 + fw.x, coord.x ) );
	#endif
}`,Rv=`#ifdef USE_LIGHTMAP
	uniform sampler2D lightMap;
	uniform float lightMapIntensity;
#endif`,Pv=`LambertMaterial material;
material.diffuseColor = diffuseColor.rgb;
material.specularStrength = specularStrength;`,Iv=`varying vec3 vViewPosition;
struct LambertMaterial {
	vec3 diffuseColor;
	float specularStrength;
};
void RE_Direct_Lambert( const in IncidentLight directLight, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in LambertMaterial material, inout ReflectedLight reflectedLight ) {
	float dotNL = saturate( dot( geometryNormal, directLight.direction ) );
	vec3 irradiance = dotNL * directLight.color;
	reflectedLight.directDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
}
void RE_IndirectDiffuse_Lambert( const in vec3 irradiance, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in LambertMaterial material, inout ReflectedLight reflectedLight ) {
	reflectedLight.indirectDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
}
#define RE_Direct				RE_Direct_Lambert
#define RE_IndirectDiffuse		RE_IndirectDiffuse_Lambert`,Lv=`uniform bool receiveShadow;
uniform vec3 ambientLightColor;
#if defined( USE_LIGHT_PROBES )
	uniform vec3 lightProbe[ 9 ];
#endif
vec3 shGetIrradianceAt( in vec3 normal, in vec3 shCoefficients[ 9 ] ) {
	float x = normal.x, y = normal.y, z = normal.z;
	vec3 result = shCoefficients[ 0 ] * 0.886227;
	result += shCoefficients[ 1 ] * 2.0 * 0.511664 * y;
	result += shCoefficients[ 2 ] * 2.0 * 0.511664 * z;
	result += shCoefficients[ 3 ] * 2.0 * 0.511664 * x;
	result += shCoefficients[ 4 ] * 2.0 * 0.429043 * x * y;
	result += shCoefficients[ 5 ] * 2.0 * 0.429043 * y * z;
	result += shCoefficients[ 6 ] * ( 0.743125 * z * z - 0.247708 );
	result += shCoefficients[ 7 ] * 2.0 * 0.429043 * x * z;
	result += shCoefficients[ 8 ] * 0.429043 * ( x * x - y * y );
	return result;
}
vec3 getLightProbeIrradiance( const in vec3 lightProbe[ 9 ], const in vec3 normal ) {
	vec3 worldNormal = transformNormalByInverseViewMatrix( normal, viewMatrix );
	vec3 irradiance = shGetIrradianceAt( worldNormal, lightProbe );
	return irradiance;
}
vec3 getAmbientLightIrradiance( const in vec3 ambientLightColor ) {
	vec3 irradiance = ambientLightColor;
	return irradiance;
}
float getDistanceAttenuation( const in float lightDistance, const in float cutoffDistance, const in float decayExponent ) {
	float distanceFalloff = 1.0 / max( pow( lightDistance, decayExponent ), 0.01 );
	if ( cutoffDistance > 0.0 ) {
		distanceFalloff *= pow2( saturate( 1.0 - pow4( lightDistance / cutoffDistance ) ) );
	}
	return distanceFalloff;
}
float getSpotAttenuation( const in float coneCosine, const in float penumbraCosine, const in float angleCosine ) {
	return smoothstep( coneCosine, penumbraCosine, angleCosine );
}
#if NUM_SUN_LIGHTS > 0
	struct SunLight {
		vec3 direction;
		vec3 color;
	};
	uniform SunLight sunLights[ NUM_SUN_LIGHTS ];
	void getSunLightInfo( const in SunLight sunLight, out IncidentLight light ) {
		light.color = sunLight.color;
		light.direction = sunLight.direction;
		light.visible = true;
	}
#endif
#if NUM_DIR_LIGHTS > 0
	struct DirectionalLight {
		vec3 direction;
		vec3 color;
	};
	uniform DirectionalLight directionalLights[ NUM_DIR_LIGHTS ];
	void getDirectionalLightInfo( const in DirectionalLight directionalLight, out IncidentLight light ) {
		light.color = directionalLight.color;
		light.direction = directionalLight.direction;
		light.visible = true;
	}
#endif
#if NUM_POINT_LIGHTS > 0
	struct PointLight {
		vec3 position;
		vec3 color;
		float distance;
		float decay;
	};
	uniform PointLight pointLights[ NUM_POINT_LIGHTS ];
	void getPointLightInfo( const in PointLight pointLight, const in vec3 geometryPosition, out IncidentLight light ) {
		vec3 lVector = pointLight.position - geometryPosition;
		light.direction = normalize( lVector );
		float lightDistance = length( lVector );
		light.color = pointLight.color;
		light.color *= getDistanceAttenuation( lightDistance, pointLight.distance, pointLight.decay );
		light.visible = ( light.color != vec3( 0.0 ) );
	}
#endif
#if NUM_SPOT_LIGHTS > 0
	struct SpotLight {
		vec3 position;
		vec3 direction;
		vec3 color;
		float distance;
		float decay;
		float coneCos;
		float penumbraCos;
	};
	uniform SpotLight spotLights[ NUM_SPOT_LIGHTS ];
	void getSpotLightInfo( const in SpotLight spotLight, const in vec3 geometryPosition, out IncidentLight light ) {
		vec3 lVector = spotLight.position - geometryPosition;
		light.direction = normalize( lVector );
		float angleCos = dot( light.direction, spotLight.direction );
		float spotAttenuation = getSpotAttenuation( spotLight.coneCos, spotLight.penumbraCos, angleCos );
		if ( spotAttenuation > 0.0 ) {
			float lightDistance = length( lVector );
			light.color = spotLight.color * spotAttenuation;
			light.color *= getDistanceAttenuation( lightDistance, spotLight.distance, spotLight.decay );
			light.visible = ( light.color != vec3( 0.0 ) );
		} else {
			light.color = vec3( 0.0 );
			light.visible = false;
		}
	}
#endif
#if NUM_RECT_AREA_LIGHTS > 0
	struct RectAreaLight {
		vec3 color;
		vec3 position;
		vec3 halfWidth;
		vec3 halfHeight;
	};
	uniform sampler2D ltc_1;	uniform sampler2D ltc_2;
	uniform RectAreaLight rectAreaLights[ NUM_RECT_AREA_LIGHTS ];
#endif
#if NUM_HEMI_LIGHTS > 0
	struct HemisphereLight {
		vec3 direction;
		vec3 skyColor;
		vec3 groundColor;
	};
	uniform HemisphereLight hemisphereLights[ NUM_HEMI_LIGHTS ];
	vec3 getHemisphereLightIrradiance( const in HemisphereLight hemiLight, const in vec3 normal ) {
		float dotNL = dot( normal, hemiLight.direction );
		float hemiDiffuseWeight = 0.5 * dotNL + 0.5;
		vec3 irradiance = mix( hemiLight.groundColor, hemiLight.skyColor, hemiDiffuseWeight );
		return irradiance;
	}
#endif
#include <lightprobes_pars_fragment>`,Dv=`#ifdef USE_ENVMAP
	vec3 getIBLIrradiance( const in vec3 normal ) {
		#ifdef ENVMAP_TYPE_CUBE_UV
			vec3 worldNormal = transformNormalByInverseViewMatrix( normal, viewMatrix );
			vec4 envMapColor = textureCubeUV( envMap, envMapRotation * worldNormal, 1.0 );
			return PI * envMapColor.rgb * envMapIntensity;
		#else
			return vec3( 0.0 );
		#endif
	}
	vec3 getIBLRadiance( const in vec3 viewDir, const in vec3 normal, const in float roughness ) {
		#ifdef ENVMAP_TYPE_CUBE_UV
			vec3 reflectVec = reflect( - viewDir, normal );
			reflectVec = normalize( mix( reflectVec, normal, pow4( roughness ) ) );
			reflectVec = transformDirectionByInverseViewMatrix( reflectVec, viewMatrix );
			vec4 envMapColor = textureCubeUV( envMap, envMapRotation * reflectVec, roughness );
			return envMapColor.rgb * envMapIntensity;
		#else
			return vec3( 0.0 );
		#endif
	}
	#ifdef USE_RETROREFLECTION
		vec3 getIBLRetroRadiance( const in vec3 viewDir, const in vec3 normal, const in float roughness ) {
			#ifdef ENVMAP_TYPE_CUBE_UV
				vec3 retroVec = normalize( mix( viewDir, normal, pow4( roughness ) ) );
				retroVec = transformDirectionByInverseViewMatrix( retroVec, viewMatrix );
				vec4 envMapColor = textureCubeUV( envMap, envMapRotation * retroVec, roughness );
				return envMapColor.rgb * envMapIntensity;
			#else
				return vec3( 0.0 );
			#endif
		}
	#endif
	#ifdef USE_ANISOTROPY
		vec3 getIBLAnisotropyRadiance( const in vec3 viewDir, const in vec3 normal, const in float roughness, const in vec3 bitangent, const in float anisotropy ) {
			#ifdef ENVMAP_TYPE_CUBE_UV
				vec3 bentNormal = cross( bitangent, viewDir );
				bentNormal = normalize( cross( bentNormal, bitangent ) );
				bentNormal = normalize( mix( bentNormal, normal, pow2( pow2( 1.0 - anisotropy * ( 1.0 - roughness ) ) ) ) );
				return getIBLRadiance( viewDir, bentNormal, roughness );
			#else
				return vec3( 0.0 );
			#endif
		}
		#ifdef USE_RETROREFLECTION
			vec3 getIBLAnisotropyRetroRadiance( const in vec3 viewDir, const in vec3 normal, const in float roughness, const in vec3 bitangent, const in float anisotropy ) {
				#ifdef ENVMAP_TYPE_CUBE_UV
					vec3 bentNormal = cross( bitangent, viewDir );
					bentNormal = normalize( cross( bentNormal, bitangent ) );
					bentNormal = normalize( mix( bentNormal, normal, pow2( pow2( 1.0 - anisotropy * ( 1.0 - roughness ) ) ) ) );
					return getIBLRetroRadiance( viewDir, bentNormal, roughness );
				#else
					return vec3( 0.0 );
				#endif
			}
		#endif
	#endif
#endif`,Nv=`ToonMaterial material;
material.diffuseColor = diffuseColor.rgb;`,Uv=`varying vec3 vViewPosition;
struct ToonMaterial {
	vec3 diffuseColor;
};
void RE_Direct_Toon( const in IncidentLight directLight, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in ToonMaterial material, inout ReflectedLight reflectedLight ) {
	vec3 irradiance = getGradientIrradiance( geometryNormal, directLight.direction ) * directLight.color;
	reflectedLight.directDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
}
void RE_IndirectDiffuse_Toon( const in vec3 irradiance, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in ToonMaterial material, inout ReflectedLight reflectedLight ) {
	reflectedLight.indirectDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
}
#define RE_Direct				RE_Direct_Toon
#define RE_IndirectDiffuse		RE_IndirectDiffuse_Toon`,Ov=`BlinnPhongMaterial material;
material.diffuseColor = diffuseColor.rgb;
material.specularColor = specular;
material.specularShininess = shininess;
material.specularStrength = specularStrength;`,Fv=`varying vec3 vViewPosition;
struct BlinnPhongMaterial {
	vec3 diffuseColor;
	vec3 specularColor;
	float specularShininess;
	float specularStrength;
};
void RE_Direct_BlinnPhong( const in IncidentLight directLight, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in BlinnPhongMaterial material, inout ReflectedLight reflectedLight ) {
	float dotNL = saturate( dot( geometryNormal, directLight.direction ) );
	vec3 irradiance = dotNL * directLight.color;
	reflectedLight.directDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
	reflectedLight.directSpecular += irradiance * BRDF_BlinnPhong( directLight.direction, geometryViewDir, geometryNormal, material.specularColor, material.specularShininess ) * material.specularStrength;
}
void RE_IndirectDiffuse_BlinnPhong( const in vec3 irradiance, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in BlinnPhongMaterial material, inout ReflectedLight reflectedLight ) {
	reflectedLight.indirectDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
}
#define RE_Direct				RE_Direct_BlinnPhong
#define RE_IndirectDiffuse		RE_IndirectDiffuse_BlinnPhong`,Bv=`PhysicalMaterial material;
material.diffuseColor = diffuseColor.rgb;
material.diffuseContribution = diffuseColor.rgb * ( 1.0 - metalnessFactor );
material.metalness = metalnessFactor;
vec3 dxy = max( abs( dFdx( nonPerturbedNormal ) ), abs( dFdy( nonPerturbedNormal ) ) );
float geometryRoughness = max( max( dxy.x, dxy.y ), dxy.z );
material.roughness = max( roughnessFactor, 0.0525 );material.roughness += geometryRoughness;
material.roughness = min( material.roughness, 1.0 );
#ifdef IOR
	material.ior = ior;
	#ifdef USE_SPECULAR
		float specularIntensityFactor = specularIntensity;
		vec3 specularColorFactor = specularColor;
		#ifdef USE_SPECULAR_COLORMAP
			specularColorFactor *= texture2D( specularColorMap, vSpecularColorMapUv ).rgb;
		#endif
		#ifdef USE_SPECULAR_INTENSITYMAP
			specularIntensityFactor *= texture2D( specularIntensityMap, vSpecularIntensityMapUv ).a;
		#endif
		material.specularF90 = mix( specularIntensityFactor, 1.0, metalnessFactor );
	#else
		float specularIntensityFactor = 1.0;
		vec3 specularColorFactor = vec3( 1.0 );
		material.specularF90 = 1.0;
	#endif
	material.specularColor = min( pow2( ( material.ior - 1.0 ) / ( material.ior + 1.0 ) ) * specularColorFactor, vec3( 1.0 ) ) * specularIntensityFactor;
	material.specularColorBlended = mix( material.specularColor, diffuseColor.rgb, metalnessFactor );
#else
	material.specularColor = vec3( 0.04 );
	material.specularColorBlended = mix( material.specularColor, diffuseColor.rgb, metalnessFactor );
	material.specularF90 = 1.0;
#endif
#ifdef USE_CLEARCOAT
	material.clearcoat = clearcoat;
	material.clearcoatRoughness = clearcoatRoughness;
	material.clearcoatF0 = vec3( 0.04 );
	material.clearcoatF90 = 1.0;
	#ifdef USE_CLEARCOATMAP
		material.clearcoat *= texture2D( clearcoatMap, vClearcoatMapUv ).x;
	#endif
	#ifdef USE_CLEARCOAT_ROUGHNESSMAP
		material.clearcoatRoughness *= texture2D( clearcoatRoughnessMap, vClearcoatRoughnessMapUv ).y;
	#endif
	material.clearcoat = saturate( material.clearcoat );	material.clearcoatRoughness = max( material.clearcoatRoughness, 0.0525 );
	material.clearcoatRoughness += geometryRoughness;
	material.clearcoatRoughness = min( material.clearcoatRoughness, 1.0 );
#endif
#ifdef USE_DISPERSION
	material.dispersion = dispersion;
#endif
#ifdef USE_RETROREFLECTION
	material.retroreflectivity = retroreflectivity;
#endif
#ifdef USE_IRIDESCENCE
	material.iridescence = iridescence;
	material.iridescenceIOR = iridescenceIOR;
	#ifdef USE_IRIDESCENCEMAP
		material.iridescence *= texture2D( iridescenceMap, vIridescenceMapUv ).r;
	#endif
	#ifdef USE_IRIDESCENCE_THICKNESSMAP
		material.iridescenceThickness = (iridescenceThicknessMaximum - iridescenceThicknessMinimum) * texture2D( iridescenceThicknessMap, vIridescenceThicknessMapUv ).g + iridescenceThicknessMinimum;
	#else
		material.iridescenceThickness = iridescenceThicknessMaximum;
	#endif
#endif
#ifdef USE_SHEEN
	material.sheenColor = sheenColor;
	#ifdef USE_SHEEN_COLORMAP
		material.sheenColor *= texture2D( sheenColorMap, vSheenColorMapUv ).rgb;
	#endif
	material.sheenRoughness = clamp( sheenRoughness, 0.0001, 1.0 );
	#ifdef USE_SHEEN_ROUGHNESSMAP
		material.sheenRoughness *= texture2D( sheenRoughnessMap, vSheenRoughnessMapUv ).a;
	#endif
#endif
#ifdef USE_ANISOTROPY
	#ifdef USE_ANISOTROPYMAP
		mat2 anisotropyMat = mat2( anisotropyVector.x, anisotropyVector.y, - anisotropyVector.y, anisotropyVector.x );
		vec3 anisotropyPolar = texture2D( anisotropyMap, vAnisotropyMapUv ).rgb;
		vec2 anisotropyV = anisotropyMat * normalize( 2.0 * anisotropyPolar.rg - vec2( 1.0 ) ) * anisotropyPolar.b;
	#else
		vec2 anisotropyV = anisotropyVector;
	#endif
	material.anisotropy = length( anisotropyV );
	if( material.anisotropy == 0.0 ) {
		anisotropyV = vec2( 1.0, 0.0 );
	} else {
		anisotropyV /= material.anisotropy;
		material.anisotropy = saturate( material.anisotropy );
	}
	material.alphaT = mix( pow2( material.roughness ), 1.0, pow2( material.anisotropy ) );
	material.anisotropyT = tbn[ 0 ] * anisotropyV.x + tbn[ 1 ] * anisotropyV.y;
	material.anisotropyB = tbn[ 1 ] * anisotropyV.x - tbn[ 0 ] * anisotropyV.y;
#endif`,kv=`uniform sampler2D dfgLUT;
struct PhysicalMaterial {
	vec3 diffuseColor;
	vec3 diffuseContribution;
	vec3 specularColor;
	vec3 specularColorBlended;
	float roughness;
	float metalness;
	float specularF90;
	float dispersion;
	vec2 dfg;
	vec3 multiScatteringCompensation;
	#ifdef USE_RETROREFLECTION
		float retroreflectivity;
	#endif
	#ifdef USE_CLEARCOAT
		float clearcoat;
		float clearcoatRoughness;
		vec3 clearcoatF0;
		float clearcoatF90;
	#endif
	#ifdef USE_IRIDESCENCE
		float iridescence;
		float iridescenceIOR;
		float iridescenceThickness;
		vec3 iridescenceFresnel;
		vec3 iridescenceF0Dielectric;
		vec3 iridescenceF0Metallic;
	#endif
	#ifdef USE_SHEEN
		vec3 sheenColor;
		float sheenRoughness;
	#endif
	#ifdef IOR
		float ior;
	#endif
	#ifdef USE_TRANSMISSION
		float transmission;
		float transmissionAlpha;
		float thickness;
		float attenuationDistance;
		vec3 attenuationColor;
	#endif
	#ifdef USE_ANISOTROPY
		float anisotropy;
		float alphaT;
		vec3 anisotropyT;
		vec3 anisotropyB;
	#endif
};
vec3 clearcoatSpecularDirect = vec3( 0.0 );
vec3 clearcoatSpecularIndirect = vec3( 0.0 );
vec3 sheenSpecularDirect = vec3( 0.0 );
vec3 sheenSpecularIndirect = vec3(0.0 );
vec3 Schlick_to_F0( const in vec3 f, const in float f90, const in float dotVH ) {
    float x = clamp( 1.0 - dotVH, 0.0, 1.0 );
    float x2 = x * x;
    float x5 = clamp( x * x2 * x2, 0.0, 0.9999 );
    return ( f - vec3( f90 ) * x5 ) / ( 1.0 - x5 );
}
float V_GGX_SmithCorrelated( const in float alpha, const in float dotNL, const in float dotNV ) {
	float a2 = pow2( alpha );
	float gv = dotNL * sqrt( a2 + ( 1.0 - a2 ) * pow2( dotNV ) );
	float gl = dotNV * sqrt( a2 + ( 1.0 - a2 ) * pow2( dotNL ) );
	return 0.5 / max( gv + gl, EPSILON );
}
float D_GGX( const in float alpha, const in float dotNH ) {
	float a2 = pow2( alpha );
	float denom = pow2( dotNH ) * ( a2 - 1.0 ) + 1.0;
	return RECIPROCAL_PI * a2 / pow2( denom );
}
#ifdef USE_ANISOTROPY
	float V_GGX_SmithCorrelated_Anisotropic( const in float alphaT, const in float alphaB, const in float dotTV, const in float dotBV, const in float dotTL, const in float dotBL, const in float dotNV, const in float dotNL ) {
		float gv = dotNL * length( vec3( alphaT * dotTV, alphaB * dotBV, dotNV ) );
		float gl = dotNV * length( vec3( alphaT * dotTL, alphaB * dotBL, dotNL ) );
		return 0.5 / max( gv + gl, EPSILON );
	}
	float D_GGX_Anisotropic( const in float alphaT, const in float alphaB, const in float dotNH, const in float dotTH, const in float dotBH ) {
		float a2 = alphaT * alphaB;
		highp vec3 v = vec3( alphaB * dotTH, alphaT * dotBH, a2 * dotNH );
		highp float v2 = dot( v, v );
		float w2 = a2 / v2;
		return RECIPROCAL_PI * a2 * pow2 ( w2 );
	}
#endif
#ifdef USE_CLEARCOAT
	vec3 BRDF_GGX_Clearcoat( const in vec3 lightDir, const in vec3 viewDir, const in vec3 normal, const in PhysicalMaterial material) {
		vec3 f0 = material.clearcoatF0;
		float f90 = material.clearcoatF90;
		float roughness = material.clearcoatRoughness;
		float alpha = pow2( roughness );
		vec3 halfDir = normalize( lightDir + viewDir );
		float dotNL = saturate( dot( normal, lightDir ) );
		float dotNV = saturate( dot( normal, viewDir ) );
		float dotNH = saturate( dot( normal, halfDir ) );
		float dotVH = saturate( dot( viewDir, halfDir ) );
		vec3 F = F_Schlick( f0, f90, dotVH );
		float V = V_GGX_SmithCorrelated( alpha, dotNL, dotNV );
		float D = D_GGX( alpha, dotNH );
		return F * ( V * D );
	}
#endif
vec3 BRDF_GGX( const in vec3 lightDir, const in vec3 viewDir, const in vec3 normal, const in PhysicalMaterial material ) {
	vec3 f0 = material.specularColorBlended;
	float f90 = material.specularF90;
	float roughness = material.roughness;
	float alpha = pow2( roughness );
	vec3 halfDir = normalize( lightDir + viewDir );
	float dotNL = saturate( dot( normal, lightDir ) );
	float dotNV = saturate( dot( normal, viewDir ) );
	float dotNH = saturate( dot( normal, halfDir ) );
	float dotVH = saturate( dot( viewDir, halfDir ) );
	vec3 F = F_Schlick( f0, f90, dotVH );
	#ifdef USE_IRIDESCENCE
		F = mix( F, material.iridescenceFresnel, material.iridescence );
	#endif
	#ifdef USE_ANISOTROPY
		float dotTL = dot( material.anisotropyT, lightDir );
		float dotTV = dot( material.anisotropyT, viewDir );
		float dotTH = dot( material.anisotropyT, halfDir );
		float dotBL = dot( material.anisotropyB, lightDir );
		float dotBV = dot( material.anisotropyB, viewDir );
		float dotBH = dot( material.anisotropyB, halfDir );
		float V = V_GGX_SmithCorrelated_Anisotropic( material.alphaT, alpha, dotTV, dotBV, dotTL, dotBL, dotNV, dotNL );
		float D = D_GGX_Anisotropic( material.alphaT, alpha, dotNH, dotTH, dotBH );
	#else
		float V = V_GGX_SmithCorrelated( alpha, dotNL, dotNV );
		float D = D_GGX( alpha, dotNH );
	#endif
	return F * ( V * D );
}
vec2 LTC_Uv( const in vec3 N, const in vec3 V, const in float roughness ) {
	const float LUT_SIZE = 64.0;
	const float LUT_SCALE = ( LUT_SIZE - 1.0 ) / LUT_SIZE;
	const float LUT_BIAS = 0.5 / LUT_SIZE;
	float dotNV = saturate( dot( N, V ) );
	vec2 uv = vec2( roughness, sqrt( 1.0 - dotNV ) );
	uv = uv * LUT_SCALE + LUT_BIAS;
	return uv;
}
float LTC_ClippedSphereFormFactor( const in vec3 f ) {
	float l = length( f );
	return max( ( l * l + f.z ) / ( l + 1.0 ), 0.0 );
}
vec3 LTC_EdgeVectorFormFactor( const in vec3 v1, const in vec3 v2 ) {
	float x = dot( v1, v2 );
	float y = abs( x );
	float a = 0.8543985 + ( 0.4965155 + 0.0145206 * y ) * y;
	float b = 3.4175940 + ( 4.1616724 + y ) * y;
	float v = a / b;
	float theta_sintheta = ( x > 0.0 ) ? v : 0.5 * inversesqrt( max( 1.0 - x * x, 1e-7 ) ) - v;
	return cross( v1, v2 ) * theta_sintheta;
}
vec3 LTC_Evaluate( const in vec3 N, const in vec3 V, const in vec3 P, const in mat3 mInv, const in vec3 rectCoords[ 4 ] ) {
	vec3 v1 = rectCoords[ 1 ] - rectCoords[ 0 ];
	vec3 v2 = rectCoords[ 3 ] - rectCoords[ 0 ];
	vec3 lightNormal = cross( v1, v2 );
	if( dot( lightNormal, P - rectCoords[ 0 ] ) < 0.0 ) return vec3( 0.0 );
	vec3 T1, T2;
	T1 = normalize( V - N * dot( V, N ) );
	T2 = - cross( N, T1 );
	mat3 mat = mInv * transpose( mat3( T1, T2, N ) );
	vec3 coords[ 4 ];
	coords[ 0 ] = mat * ( rectCoords[ 0 ] - P );
	coords[ 1 ] = mat * ( rectCoords[ 1 ] - P );
	coords[ 2 ] = mat * ( rectCoords[ 2 ] - P );
	coords[ 3 ] = mat * ( rectCoords[ 3 ] - P );
	coords[ 0 ] = normalize( coords[ 0 ] );
	coords[ 1 ] = normalize( coords[ 1 ] );
	coords[ 2 ] = normalize( coords[ 2 ] );
	coords[ 3 ] = normalize( coords[ 3 ] );
	vec3 vectorFormFactor = vec3( 0.0 );
	vectorFormFactor += LTC_EdgeVectorFormFactor( coords[ 0 ], coords[ 1 ] );
	vectorFormFactor += LTC_EdgeVectorFormFactor( coords[ 1 ], coords[ 2 ] );
	vectorFormFactor += LTC_EdgeVectorFormFactor( coords[ 2 ], coords[ 3 ] );
	vectorFormFactor += LTC_EdgeVectorFormFactor( coords[ 3 ], coords[ 0 ] );
	float result = LTC_ClippedSphereFormFactor( vectorFormFactor );
	return vec3( result );
}
#if defined( USE_SHEEN )
float D_Charlie( float roughness, float dotNH ) {
	float alpha = pow2( roughness );
	float invAlpha = 1.0 / alpha;
	float cos2h = dotNH * dotNH;
	float sin2h = max( 1.0 - cos2h, 0.0078125 );
	return ( 2.0 + invAlpha ) * pow( sin2h, invAlpha * 0.5 ) / ( 2.0 * PI );
}
float V_Neubelt( float dotNV, float dotNL ) {
	return saturate( 1.0 / ( 4.0 * ( dotNL + dotNV - dotNL * dotNV ) ) );
}
vec3 BRDF_Sheen( const in vec3 lightDir, const in vec3 viewDir, const in vec3 normal, vec3 sheenColor, const in float sheenRoughness ) {
	vec3 halfDir = normalize( lightDir + viewDir );
	float dotNL = saturate( dot( normal, lightDir ) );
	float dotNV = saturate( dot( normal, viewDir ) );
	float dotNH = saturate( dot( normal, halfDir ) );
	float D = D_Charlie( sheenRoughness, dotNH );
	float V = V_Neubelt( dotNV, dotNL );
	return sheenColor * ( D * V );
}
#endif
float IBLSheenBRDF( const in vec3 normal, const in vec3 viewDir, const in float roughness ) {
	float dotNV = saturate( dot( normal, viewDir ) );
	float r2 = roughness * roughness;
	float rInv = 1.0 / ( roughness + 0.1 );
	float a = -1.9362 + 1.0678 * roughness + 0.4573 * r2 - 0.8469 * rInv;
	float b = -0.6014 + 0.5538 * roughness - 0.4670 * r2 - 0.1255 * rInv;
	float DG = exp( a * dotNV + b );
	return saturate( DG );
}
vec3 EnvironmentBRDF( const in vec3 normal, const in vec3 viewDir, const in vec3 specularColor, const in float specularF90, const in float roughness ) {
	float dotNV = saturate( dot( normal, viewDir ) );
	vec2 fab = texture2D( dfgLUT, vec2( roughness, dotNV ) ).rg;
	return specularColor * fab.x + specularF90 * fab.y;
}
#ifdef USE_IRIDESCENCE
void computeMultiscatteringIridescence( const in vec2 fab, const in vec3 specularColor, const in float specularF90, const in float iridescence, const in vec3 iridescenceF0, inout vec3 singleScatter, inout vec3 multiScatter ) {
#else
void computeMultiscattering( const in vec2 fab, const in vec3 specularColor, const in float specularF90, inout vec3 singleScatter, inout vec3 multiScatter ) {
#endif
	#ifdef USE_IRIDESCENCE
		vec3 Fr = mix( specularColor, iridescenceF0, iridescence );
	#else
		vec3 Fr = specularColor;
	#endif
	vec3 FssEss = Fr * fab.x + specularF90 * fab.y;
	float Ess = fab.x + fab.y;
	float Ems = 1.0 - Ess;
	vec3 Favg = Fr + ( 1.0 - Fr ) * 0.047619;	vec3 Fms = FssEss * Favg / ( 1.0 - Ems * Favg );
	singleScatter += FssEss;
	multiScatter += Fms * Ems;
}
#if NUM_RECT_AREA_LIGHTS > 0
	void RE_Direct_RectArea_Physical( const in RectAreaLight rectAreaLight, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in PhysicalMaterial material, inout ReflectedLight reflectedLight ) {
		vec3 normal = geometryNormal;
		vec3 viewDir = geometryViewDir;
		vec3 position = geometryPosition;
		vec3 lightPos = rectAreaLight.position;
		vec3 halfWidth = rectAreaLight.halfWidth;
		vec3 halfHeight = rectAreaLight.halfHeight;
		vec3 lightColor = rectAreaLight.color;
		float roughness = material.roughness;
		vec3 rectCoords[ 4 ];
		rectCoords[ 0 ] = lightPos + halfWidth - halfHeight;		rectCoords[ 1 ] = lightPos - halfWidth - halfHeight;
		rectCoords[ 2 ] = lightPos - halfWidth + halfHeight;
		rectCoords[ 3 ] = lightPos + halfWidth + halfHeight;
		vec2 uv = LTC_Uv( normal, viewDir, roughness );
		vec4 t1 = texture2D( ltc_1, uv );
		vec4 t2 = texture2D( ltc_2, uv );
		mat3 mInv = mat3(
			vec3( t1.x, 0, t1.y ),
			vec3(    0, 1,    0 ),
			vec3( t1.z, 0, t1.w )
		);
		vec3 fresnel = ( material.specularColorBlended * t2.x + ( material.specularF90 - material.specularColorBlended ) * t2.y );
		reflectedLight.directSpecular += lightColor * fresnel * LTC_Evaluate( normal, viewDir, position, mInv, rectCoords );
		reflectedLight.directDiffuse += lightColor * material.diffuseContribution * LTC_Evaluate( normal, viewDir, position, mat3( 1.0 ), rectCoords );
		#ifdef USE_CLEARCOAT
			vec3 Ncc = geometryClearcoatNormal;
			vec2 uvClearcoat = LTC_Uv( Ncc, viewDir, material.clearcoatRoughness );
			vec4 t1Clearcoat = texture2D( ltc_1, uvClearcoat );
			vec4 t2Clearcoat = texture2D( ltc_2, uvClearcoat );
			mat3 mInvClearcoat = mat3(
				vec3( t1Clearcoat.x, 0, t1Clearcoat.y ),
				vec3(             0, 1,             0 ),
				vec3( t1Clearcoat.z, 0, t1Clearcoat.w )
			);
			vec3 fresnelClearcoat = material.clearcoatF0 * t2Clearcoat.x + ( material.clearcoatF90 - material.clearcoatF0 ) * t2Clearcoat.y;
			clearcoatSpecularDirect += lightColor * fresnelClearcoat * LTC_Evaluate( Ncc, viewDir, position, mInvClearcoat, rectCoords );
		#endif
	}
#endif
void RE_Direct_Physical( const in IncidentLight directLight, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in PhysicalMaterial material, inout ReflectedLight reflectedLight ) {
	float dotNL = saturate( dot( geometryNormal, directLight.direction ) );
	vec3 irradiance = dotNL * directLight.color;
	#ifdef USE_CLEARCOAT
		float dotNLcc = saturate( dot( geometryClearcoatNormal, directLight.direction ) );
		vec3 ccIrradiance = dotNLcc * directLight.color;
		clearcoatSpecularDirect += ccIrradiance * BRDF_GGX_Clearcoat( directLight.direction, geometryViewDir, geometryClearcoatNormal, material );
	#endif
	#ifdef USE_SHEEN
 
 		sheenSpecularDirect += irradiance * BRDF_Sheen( directLight.direction, geometryViewDir, geometryNormal, material.sheenColor, material.sheenRoughness );
 
 		float sheenAlbedoV = IBLSheenBRDF( geometryNormal, geometryViewDir, material.sheenRoughness );
 		float sheenAlbedoL = IBLSheenBRDF( geometryNormal, directLight.direction, material.sheenRoughness );
 
 		float sheenEnergyComp = 1.0 - max3( material.sheenColor ) * max( sheenAlbedoV, sheenAlbedoL );
 
 		irradiance *= sheenEnergyComp;
 
 	#endif
	vec3 specularBRDF = BRDF_GGX( directLight.direction, geometryViewDir, geometryNormal, material );
	#ifdef USE_RETROREFLECTION
		vec3 retroViewDir = reflect( - geometryViewDir, geometryNormal );
		vec3 retroSpecularBRDF = BRDF_GGX( directLight.direction, retroViewDir, geometryNormal, material );
		specularBRDF = mix( specularBRDF, retroSpecularBRDF, saturate( material.retroreflectivity ) );
	#endif
	reflectedLight.directSpecular += irradiance * specularBRDF * material.multiScatteringCompensation;
	vec3 halfDir = normalize( directLight.direction + geometryViewDir );
	float dotVH = saturate( dot( geometryViewDir, halfDir ) );
	vec3 F = F_Schlick( material.specularColor, material.specularF90, dotVH );
	#ifdef USE_RETROREFLECTION
		vec3 retroHalfDir = normalize( directLight.direction + retroViewDir );
		float dotRetroVH = saturate( dot( retroViewDir, retroHalfDir ) );
		vec3 retroF = F_Schlick( material.specularColor, material.specularF90, dotRetroVH );
		F = mix( F, retroF, saturate( material.retroreflectivity ) );
	#endif
	reflectedLight.directDiffuse += irradiance * BRDF_Lambert( material.diffuseContribution ) * ( 1.0 - F );
}
void RE_IndirectDiffuse_Physical( const in vec3 irradiance, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in PhysicalMaterial material, inout ReflectedLight reflectedLight ) {
	vec3 singleScattering = vec3( 0.0 );
	vec3 multiScattering = vec3( 0.0 );
	#ifdef USE_IRIDESCENCE
		computeMultiscatteringIridescence( material.dfg, material.specularColor, material.specularF90, material.iridescence, material.iridescenceF0Dielectric, singleScattering, multiScattering );
	#else
		computeMultiscattering( material.dfg, material.specularColor, material.specularF90, singleScattering, multiScattering );
	#endif
	vec3 diffuse = irradiance * BRDF_Lambert( material.diffuseContribution ) * ( 1.0 - singleScattering - multiScattering );
	#ifdef USE_SHEEN
		float sheenAlbedo = IBLSheenBRDF( geometryNormal, geometryViewDir, material.sheenRoughness );
		sheenSpecularIndirect += irradiance * material.sheenColor * sheenAlbedo * RECIPROCAL_PI;
		float sheenEnergyComp = 1.0 - max3( material.sheenColor ) * sheenAlbedo;
		diffuse *= sheenEnergyComp;
	#endif
	reflectedLight.indirectDiffuse += diffuse;
}
void RE_IndirectSpecular_Physical( const in vec3 radiance, const in vec3 irradiance, const in vec3 clearcoatRadiance, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in PhysicalMaterial material, inout ReflectedLight reflectedLight) {
	#ifdef USE_CLEARCOAT
		clearcoatSpecularIndirect += clearcoatRadiance * EnvironmentBRDF( geometryClearcoatNormal, geometryViewDir, material.clearcoatF0, material.clearcoatF90, material.clearcoatRoughness );
	#endif
	#ifdef USE_SHEEN
		sheenSpecularIndirect += irradiance * material.sheenColor * IBLSheenBRDF( geometryNormal, geometryViewDir, material.sheenRoughness ) * RECIPROCAL_PI;
 	#endif
	vec3 singleScatteringDielectric = vec3( 0.0 );
	vec3 multiScatteringDielectric = vec3( 0.0 );
	vec3 singleScatteringMetallic = vec3( 0.0 );
	vec3 multiScatteringMetallic = vec3( 0.0 );
	#ifdef USE_IRIDESCENCE
		computeMultiscatteringIridescence( material.dfg, material.specularColor, material.specularF90, material.iridescence, material.iridescenceF0Dielectric, singleScatteringDielectric, multiScatteringDielectric );
		computeMultiscatteringIridescence( material.dfg, material.diffuseColor, material.specularF90, material.iridescence, material.iridescenceF0Metallic, singleScatteringMetallic, multiScatteringMetallic );
	#else
		computeMultiscattering( material.dfg, material.specularColor, material.specularF90, singleScatteringDielectric, multiScatteringDielectric );
		computeMultiscattering( material.dfg, material.diffuseColor, material.specularF90, singleScatteringMetallic, multiScatteringMetallic );
	#endif
	vec3 singleScattering = mix( singleScatteringDielectric, singleScatteringMetallic, material.metalness );
	vec3 multiScattering = mix( multiScatteringDielectric, multiScatteringMetallic, material.metalness );
	vec3 totalScatteringDielectric = singleScatteringDielectric + multiScatteringDielectric;
	vec3 diffuse = material.diffuseContribution * ( 1.0 - totalScatteringDielectric );
	vec3 cosineWeightedIrradiance = irradiance * RECIPROCAL_PI;
	vec3 indirectSpecular = radiance * singleScattering;
	indirectSpecular += multiScattering * cosineWeightedIrradiance;
	vec3 indirectDiffuse = diffuse * cosineWeightedIrradiance;
	#ifdef USE_SHEEN
		float sheenAlbedo = IBLSheenBRDF( geometryNormal, geometryViewDir, material.sheenRoughness );
		float sheenEnergyComp = 1.0 - max3( material.sheenColor ) * sheenAlbedo;
		indirectSpecular *= sheenEnergyComp;
		indirectDiffuse *= sheenEnergyComp;
	#endif
	reflectedLight.indirectSpecular += indirectSpecular;
	reflectedLight.indirectDiffuse += indirectDiffuse;
}
#define RE_Direct				RE_Direct_Physical
#define RE_Direct_RectArea		RE_Direct_RectArea_Physical
#define RE_IndirectDiffuse		RE_IndirectDiffuse_Physical
#define RE_IndirectSpecular		RE_IndirectSpecular_Physical
float computeSpecularOcclusion( const in float dotNV, const in float ambientOcclusion, const in float roughness ) {
	return saturate( pow( dotNV + ambientOcclusion, exp2( - 16.0 * roughness - 1.0 ) ) - 1.0 + ambientOcclusion );
}`,zv=`
vec3 geometryPosition = - vViewPosition;
vec3 geometryNormal = normal;
vec3 geometryViewDir = ( isOrthographic ) ? vec3( 0, 0, 1 ) : normalize( vViewPosition );
vec3 geometryClearcoatNormal = vec3( 0.0 );
#ifdef USE_CLEARCOAT
	geometryClearcoatNormal = clearcoatNormal;
#endif
#ifdef USE_IRIDESCENCE
	float dotNVi = saturate( dot( normal, geometryViewDir ) );
	if ( material.iridescenceThickness == 0.0 ) {
		material.iridescence = 0.0;
	} else {
		material.iridescence = saturate( material.iridescence );
	}
	if ( material.iridescence > 0.0 ) {
		vec3 iridescenceFresnelDielectric = evalIridescence( 1.0, material.iridescenceIOR, dotNVi, material.iridescenceThickness, material.specularColor );
		vec3 iridescenceFresnelMetallic = evalIridescence( 1.0, material.iridescenceIOR, dotNVi, material.iridescenceThickness, material.diffuseColor );
		material.iridescenceFresnel = mix( iridescenceFresnelDielectric, iridescenceFresnelMetallic, material.metalness );
		material.iridescenceF0Dielectric = Schlick_to_F0( iridescenceFresnelDielectric, 1.0, dotNVi );
		material.iridescenceF0Metallic = Schlick_to_F0( iridescenceFresnelMetallic, 1.0, dotNVi );
	}
#endif
#ifdef STANDARD
	float dotNVms = saturate( dot( geometryNormal, geometryViewDir ) );
	material.dfg = texture2D( dfgLUT, vec2( material.roughness, dotNVms ) ).rg;
	#if ( NUM_SUN_LIGHTS > 0 || NUM_DIR_LIGHTS > 0 || NUM_POINT_LIGHTS > 0 || NUM_SPOT_LIGHTS > 0 )
		float EssMs = material.dfg.x + material.dfg.y;
		material.multiScatteringCompensation = 1.0 + material.specularColorBlended * ( 1.0 / EssMs - 1.0 );
	#endif
#endif
IncidentLight directLight;
#if ( NUM_POINT_LIGHTS > 0 ) && defined( RE_Direct )
	PointLight pointLight;
	#if defined( USE_SHADOWMAP ) && NUM_POINT_LIGHT_SHADOWS > 0
	PointLightShadow pointLightShadow;
	#endif
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_POINT_LIGHTS; i ++ ) {
		pointLight = pointLights[ i ];
		getPointLightInfo( pointLight, geometryPosition, directLight );
		#if defined( USE_SHADOWMAP ) && ( UNROLLED_LOOP_INDEX < NUM_POINT_LIGHT_SHADOWS ) && ( defined( SHADOWMAP_TYPE_PCF ) || defined( SHADOWMAP_TYPE_BASIC ) )
		pointLightShadow = pointLightShadows[ i ];
		directLight.color *= ( directLight.visible && receiveShadow ) ? getPointShadow( pointShadowMap[ i ], pointLightShadow.shadowMapSize, pointLightShadow.shadowIntensity, pointLightShadow.shadowBias, pointLightShadow.shadowRadius, vPointShadowCoord[ i ], pointLightShadow.shadowCameraNear, pointLightShadow.shadowCameraFar ) : 1.0;
		#endif
		RE_Direct( directLight, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
	}
	#pragma unroll_loop_end
#endif
#if ( NUM_SPOT_LIGHTS > 0 ) && defined( RE_Direct )
	SpotLight spotLight;
	vec4 spotColor;
	vec3 spotLightCoord;
	bool inSpotLightMap;
	#if defined( USE_SHADOWMAP ) && NUM_SPOT_LIGHT_SHADOWS > 0
	SpotLightShadow spotLightShadow;
	#endif
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_SPOT_LIGHTS; i ++ ) {
		spotLight = spotLights[ i ];
		getSpotLightInfo( spotLight, geometryPosition, directLight );
		#if ( UNROLLED_LOOP_INDEX < NUM_SPOT_LIGHT_SHADOWS_WITH_MAPS )
		#define SPOT_LIGHT_MAP_INDEX UNROLLED_LOOP_INDEX
		#elif ( UNROLLED_LOOP_INDEX < NUM_SPOT_LIGHT_SHADOWS )
		#define SPOT_LIGHT_MAP_INDEX NUM_SPOT_LIGHT_MAPS
		#else
		#define SPOT_LIGHT_MAP_INDEX ( UNROLLED_LOOP_INDEX - NUM_SPOT_LIGHT_SHADOWS + NUM_SPOT_LIGHT_SHADOWS_WITH_MAPS )
		#endif
		#if ( SPOT_LIGHT_MAP_INDEX < NUM_SPOT_LIGHT_MAPS )
			spotLightCoord = vSpotLightCoord[ i ].xyz / vSpotLightCoord[ i ].w;
			inSpotLightMap = all( lessThan( abs( spotLightCoord * 2. - 1. ), vec3( 1.0 ) ) );
			spotColor = texture2D( spotLightMap[ SPOT_LIGHT_MAP_INDEX ], spotLightCoord.xy );
			directLight.color = inSpotLightMap ? directLight.color * spotColor.rgb : directLight.color;
		#endif
		#undef SPOT_LIGHT_MAP_INDEX
		#if defined( USE_SHADOWMAP ) && ( UNROLLED_LOOP_INDEX < NUM_SPOT_LIGHT_SHADOWS )
		spotLightShadow = spotLightShadows[ i ];
		directLight.color *= ( directLight.visible && receiveShadow ) ? getShadow( spotShadowMap[ i ], spotLightShadow.shadowMapSize, spotLightShadow.shadowIntensity, spotLightShadow.shadowBias, spotLightShadow.shadowRadius, vSpotLightCoord[ i ] ) : 1.0;
		#endif
		RE_Direct( directLight, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
	}
	#pragma unroll_loop_end
#endif
#if ( NUM_SUN_LIGHTS > 0 ) && defined( RE_Direct )
	SunLight sunLight;
	#if defined( USE_SHADOWMAP ) && NUM_SUN_LIGHT_SHADOWS > 0
	SunLightShadow sunLightShadow;
	#endif
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_SUN_LIGHTS; i ++ ) {
		sunLight = sunLights[ i ];
		getSunLightInfo( sunLight, directLight );
		#if defined( USE_SHADOWMAP ) && ( UNROLLED_LOOP_INDEX < NUM_SUN_LIGHT_SHADOWS )
		sunLightShadow = sunLightShadows[ i ];
		directLight.color *= ( directLight.visible && receiveShadow ) ? getSunShadow( sunShadowMap[ i ], sunLightShadow, UNROLLED_LOOP_INDEX ) : 1.0;
		#endif
		RE_Direct( directLight, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
	}
	#pragma unroll_loop_end
#endif
#if ( NUM_DIR_LIGHTS > 0 ) && defined( RE_Direct )
	DirectionalLight directionalLight;
	#if defined( USE_SHADOWMAP ) && NUM_DIR_LIGHT_SHADOWS > 0
	DirectionalLightShadow directionalLightShadow;
	#endif
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_DIR_LIGHTS; i ++ ) {
		directionalLight = directionalLights[ i ];
		getDirectionalLightInfo( directionalLight, directLight );
		#if defined( USE_SHADOWMAP ) && ( UNROLLED_LOOP_INDEX < NUM_DIR_LIGHT_SHADOWS )
		directionalLightShadow = directionalLightShadows[ i ];
		directLight.color *= ( directLight.visible && receiveShadow ) ? getShadow( directionalShadowMap[ i ], directionalLightShadow.shadowMapSize, directionalLightShadow.shadowIntensity, directionalLightShadow.shadowBias, directionalLightShadow.shadowRadius, vDirectionalShadowCoord[ i ] ) : 1.0;
		#endif
		RE_Direct( directLight, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
	}
	#pragma unroll_loop_end
#endif
#if ( NUM_RECT_AREA_LIGHTS > 0 ) && defined( RE_Direct_RectArea )
	RectAreaLight rectAreaLight;
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_RECT_AREA_LIGHTS; i ++ ) {
		rectAreaLight = rectAreaLights[ i ];
		RE_Direct_RectArea( rectAreaLight, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
	}
	#pragma unroll_loop_end
#endif
#if defined( RE_IndirectDiffuse )
	vec3 iblIrradiance = vec3( 0.0 );
	vec3 irradiance = getAmbientLightIrradiance( ambientLightColor );
	#if defined( USE_LIGHT_PROBES )
		irradiance += getLightProbeIrradiance( lightProbe, geometryNormal );
	#endif
	#if ( NUM_HEMI_LIGHTS > 0 )
		#pragma unroll_loop_start
		for ( int i = 0; i < NUM_HEMI_LIGHTS; i ++ ) {
			irradiance += getHemisphereLightIrradiance( hemisphereLights[ i ], geometryNormal );
		}
		#pragma unroll_loop_end
	#endif
	#ifdef USE_LIGHT_PROBES_GRID
		vec3 probeWorldPos = ( ( vec4( geometryPosition, 1.0 ) - viewMatrix[ 3 ] ) * viewMatrix ).xyz;
		vec3 probeWorldNormal = transformNormalByInverseViewMatrix( geometryNormal, viewMatrix );
		irradiance += getLightProbeGridIrradiance( probeWorldPos, probeWorldNormal );
	#endif
#endif
#if defined( RE_IndirectSpecular )
	vec3 radiance = vec3( 0.0 );
	vec3 clearcoatRadiance = vec3( 0.0 );
#endif`,Vv=`#if defined( RE_IndirectDiffuse )
	#ifdef USE_LIGHTMAP
		vec4 lightMapTexel = texture2D( lightMap, vLightMapUv );
		vec3 lightMapIrradiance = lightMapTexel.rgb * lightMapIntensity;
		irradiance += lightMapIrradiance;
	#endif
	#if defined( USE_ENVMAP ) && defined( ENVMAP_TYPE_CUBE_UV )
		#if defined( STANDARD ) || defined( LAMBERT ) || defined( PHONG )
			iblIrradiance += getIBLIrradiance( geometryNormal );
		#endif
	#endif
#endif
#if defined( USE_ENVMAP ) && defined( RE_IndirectSpecular )
	#ifdef USE_ANISOTROPY
		vec3 iblRadiance = getIBLAnisotropyRadiance( geometryViewDir, geometryNormal, material.roughness, material.anisotropyB, material.anisotropy );
	#else
		vec3 iblRadiance = getIBLRadiance( geometryViewDir, geometryNormal, material.roughness );
	#endif
	#ifdef USE_RETROREFLECTION
		#ifdef USE_ANISOTROPY
			vec3 retroIBLRadiance = getIBLAnisotropyRetroRadiance( geometryViewDir, geometryNormal, material.roughness, material.anisotropyB, material.anisotropy );
		#else
			vec3 retroIBLRadiance = getIBLRetroRadiance( geometryViewDir, geometryNormal, material.roughness );
		#endif
		iblRadiance = mix( iblRadiance, retroIBLRadiance, saturate( material.retroreflectivity ) );
	#endif
	radiance += iblRadiance;
	#ifdef USE_CLEARCOAT
		clearcoatRadiance += getIBLRadiance( geometryViewDir, geometryClearcoatNormal, material.clearcoatRoughness );
	#endif
#endif`,Gv=`#if defined( RE_IndirectDiffuse )
	#if defined( LAMBERT ) || defined( PHONG )
		irradiance += iblIrradiance;
	#endif
	RE_IndirectDiffuse( irradiance, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
#endif
#if defined( RE_IndirectSpecular )
	RE_IndirectSpecular( radiance, iblIrradiance, clearcoatRadiance, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
#endif`,Hv=`#ifdef USE_LIGHT_PROBES_GRID
uniform highp sampler3D probesSH;
uniform vec3 probesMin;
uniform vec3 probesMax;
uniform vec3 probesResolution;
vec3 getLightProbeGridIrradiance( vec3 worldPos, vec3 worldNormal ) {
	vec3 res = probesResolution;
	vec3 gridRange = probesMax - probesMin;
	vec3 resMinusOne = res - 1.0;
	vec3 probeSpacing = gridRange / resMinusOne;
	vec3 samplePos = worldPos + worldNormal * probeSpacing * 0.5;
	vec3 uvw = clamp( ( samplePos - probesMin ) / gridRange, 0.0, 1.0 );
	uvw = uvw * resMinusOne / res + 0.5 / res;
	float nz          = res.z;
	float paddedSlices = nz + 2.0;
	float atlasDepth  = 7.0 * paddedSlices;
	float uvZBase     = uvw.z * nz + 1.0;
	vec4 s0 = texture( probesSH, vec3( uvw.xy, ( uvZBase                       ) / atlasDepth ) );
	vec4 s1 = texture( probesSH, vec3( uvw.xy, ( uvZBase +       paddedSlices   ) / atlasDepth ) );
	vec4 s2 = texture( probesSH, vec3( uvw.xy, ( uvZBase + 2.0 * paddedSlices   ) / atlasDepth ) );
	vec4 s3 = texture( probesSH, vec3( uvw.xy, ( uvZBase + 3.0 * paddedSlices   ) / atlasDepth ) );
	vec4 s4 = texture( probesSH, vec3( uvw.xy, ( uvZBase + 4.0 * paddedSlices   ) / atlasDepth ) );
	vec4 s5 = texture( probesSH, vec3( uvw.xy, ( uvZBase + 5.0 * paddedSlices   ) / atlasDepth ) );
	vec4 s6 = texture( probesSH, vec3( uvw.xy, ( uvZBase + 6.0 * paddedSlices   ) / atlasDepth ) );
	vec3 c0 = s0.xyz;
	vec3 c1 = vec3( s0.w, s1.xy );
	vec3 c2 = vec3( s1.zw, s2.x );
	vec3 c3 = s2.yzw;
	vec3 c4 = s3.xyz;
	vec3 c5 = vec3( s3.w, s4.xy );
	vec3 c6 = vec3( s4.zw, s5.x );
	vec3 c7 = s5.yzw;
	vec3 c8 = s6.xyz;
	float x = worldNormal.x, y = worldNormal.y, z = worldNormal.z;
	vec3 result = c0 * 0.886227;
	result += c1 * 2.0 * 0.511664 * y;
	result += c2 * 2.0 * 0.511664 * z;
	result += c3 * 2.0 * 0.511664 * x;
	result += c4 * 2.0 * 0.429043 * x * y;
	result += c5 * 2.0 * 0.429043 * y * z;
	result += c6 * ( 0.743125 * z * z - 0.247708 );
	result += c7 * 2.0 * 0.429043 * x * z;
	result += c8 * 0.429043 * ( x * x - y * y );
	return max( result, vec3( 0.0 ) );
}
#endif`,Wv=`#if defined( USE_LOGARITHMIC_DEPTH_BUFFER )
	gl_FragDepth = vIsPerspective == 0.0 ? gl_FragCoord.z : log2( vFragDepth ) * logDepthBufFC * 0.5;
#endif`,Xv=`#if defined( USE_LOGARITHMIC_DEPTH_BUFFER )
	uniform float logDepthBufFC;
	varying float vFragDepth;
	varying float vIsPerspective;
#endif`,qv=`#ifdef USE_LOGARITHMIC_DEPTH_BUFFER
	varying float vFragDepth;
	varying float vIsPerspective;
#endif`,jv=`#ifdef USE_LOGARITHMIC_DEPTH_BUFFER
	vFragDepth = 1.0 + gl_Position.w;
	vIsPerspective = float( isPerspectiveMatrix( projectionMatrix ) );
#endif`,Yv=`#ifdef USE_MAP
	vec4 sampledDiffuseColor = texture2D( map, vMapUv );
	#ifdef DECODE_VIDEO_TEXTURE
		sampledDiffuseColor = sRGBTransferEOTF( sampledDiffuseColor );
	#endif
	diffuseColor *= sampledDiffuseColor;
#endif`,$v=`#ifdef USE_MAP
	uniform sampler2D map;
#endif`,Zv=`#if defined( USE_MAP ) || defined( USE_ALPHAMAP )
	#if defined( USE_POINTS_UV )
		vec2 uv = vUv;
	#else
		vec2 uv = ( uvTransform * vec3( gl_PointCoord.x, 1.0 - gl_PointCoord.y, 1 ) ).xy;
	#endif
#endif
#ifdef USE_MAP
	diffuseColor *= texture2D( map, uv );
#endif
#ifdef USE_ALPHAMAP
	diffuseColor.a *= texture2D( alphaMap, uv ).g;
#endif`,Kv=`#if defined( USE_POINTS_UV )
	varying vec2 vUv;
#else
	#if defined( USE_MAP ) || defined( USE_ALPHAMAP )
		uniform mat3 uvTransform;
	#endif
#endif
#ifdef USE_MAP
	uniform sampler2D map;
#endif
#ifdef USE_ALPHAMAP
	uniform sampler2D alphaMap;
#endif`,Jv=`float metalnessFactor = metalness;
#ifdef USE_METALNESSMAP
	vec4 texelMetalness = texture2D( metalnessMap, vMetalnessMapUv );
	metalnessFactor *= texelMetalness.b;
#endif`,Qv=`#ifdef USE_METALNESSMAP
	uniform sampler2D metalnessMap;
#endif`,eb=`#ifdef USE_INSTANCING_MORPH
	float morphTargetInfluences[ MORPHTARGETS_COUNT ];
	float morphTargetBaseInfluence = texelFetch( morphTexture, ivec2( 0, gl_InstanceID ), 0 ).r;
	for ( int i = 0; i < MORPHTARGETS_COUNT; i ++ ) {
		morphTargetInfluences[i] =  texelFetch( morphTexture, ivec2( i + 1, gl_InstanceID ), 0 ).r;
	}
#endif`,tb=`#if defined( USE_MORPHCOLORS )
	vColor *= morphTargetBaseInfluence;
	for ( int i = 0; i < MORPHTARGETS_COUNT; i ++ ) {
		#if defined( USE_COLOR_ALPHA )
			if ( morphTargetInfluences[ i ] != 0.0 ) vColor += getMorph( gl_VertexID, i, 2 ) * morphTargetInfluences[ i ];
		#elif defined( USE_COLOR )
			if ( morphTargetInfluences[ i ] != 0.0 ) vColor += getMorph( gl_VertexID, i, 2 ).rgb * morphTargetInfluences[ i ];
		#endif
	}
#endif`,ib=`#ifdef USE_MORPHNORMALS
	objectNormal *= morphTargetBaseInfluence;
	for ( int i = 0; i < MORPHTARGETS_COUNT; i ++ ) {
		if ( morphTargetInfluences[ i ] != 0.0 ) objectNormal += getMorph( gl_VertexID, i, 1 ).xyz * morphTargetInfluences[ i ];
	}
#endif`,nb=`#ifdef USE_MORPHTARGETS
	#ifndef USE_INSTANCING_MORPH
		uniform float morphTargetBaseInfluence;
		uniform float morphTargetInfluences[ MORPHTARGETS_COUNT ];
	#endif
	uniform sampler2DArray morphTargetsTexture;
	uniform ivec2 morphTargetsTextureSize;
	vec4 getMorph( const in int vertexIndex, const in int morphTargetIndex, const in int offset ) {
		int texelIndex = vertexIndex * MORPHTARGETS_TEXTURE_STRIDE + offset;
		int y = texelIndex / morphTargetsTextureSize.x;
		int x = texelIndex - y * morphTargetsTextureSize.x;
		ivec3 morphUV = ivec3( x, y, morphTargetIndex );
		return texelFetch( morphTargetsTexture, morphUV, 0 );
	}
#endif`,rb=`#ifdef USE_MORPHTARGETS
	transformed *= morphTargetBaseInfluence;
	for ( int i = 0; i < MORPHTARGETS_COUNT; i ++ ) {
		if ( morphTargetInfluences[ i ] != 0.0 ) transformed += getMorph( gl_VertexID, i, 0 ).xyz * morphTargetInfluences[ i ];
	}
#endif`,sb=`float faceDirection = gl_FrontFacing ? 1.0 : - 1.0;
#ifdef FLAT_SHADED
	vec3 fdx = dFdx( vViewPosition );
	vec3 fdy = dFdy( vViewPosition );
	vec3 normal = normalize( cross( fdx, fdy ) );
#else
	vec3 normal = normalize( vNormal );
	#ifdef DOUBLE_SIDED
		normal *= faceDirection;
	#endif
#endif
#if defined( USE_NORMALMAP_TANGENTSPACE ) || defined( USE_CLEARCOAT_NORMALMAP ) || defined( USE_ANISOTROPY )
	#ifdef USE_TANGENT
		mat3 tbn = mat3( normalize( vTangent ), normalize( vBitangent ), normal );
	#else
		mat3 tbn = getTangentFrame( - vViewPosition, normal,
		#if defined( USE_NORMALMAP )
			vNormalMapUv
		#elif defined( USE_CLEARCOAT_NORMALMAP )
			vClearcoatNormalMapUv
		#else
			vUv
		#endif
		);
	#endif
	#ifdef DOUBLE_SIDED
		tbn[0] *= faceDirection;
		tbn[1] *= faceDirection;
	#endif
#endif
#ifdef USE_CLEARCOAT_NORMALMAP
	#ifdef USE_TANGENT
		mat3 tbn2 = mat3( normalize( vTangent ), normalize( vBitangent ), normal );
	#else
		mat3 tbn2 = getTangentFrame( - vViewPosition, normal, vClearcoatNormalMapUv );
	#endif
	#ifdef DOUBLE_SIDED
		tbn2[0] *= faceDirection;
		tbn2[1] *= faceDirection;
	#endif
#endif
vec3 nonPerturbedNormal = normal;`,ab=`#ifdef USE_NORMALMAP_OBJECTSPACE
	normal = texture2D( normalMap, vNormalMapUv ).xyz * 2.0 - 1.0;
	#ifdef FLIP_SIDED
		normal = - normal;
	#endif
	#ifdef DOUBLE_SIDED
		normal = normal * faceDirection;
	#endif
	normal = normalize( normalMatrix * normal );
#elif defined( USE_NORMALMAP_TANGENTSPACE )
	vec3 mapN = texture2D( normalMap, vNormalMapUv ).xyz * 2.0 - 1.0;
	#if defined( USE_PACKED_NORMALMAP )
		mapN = vec3( mapN.xy, sqrt( saturate( 1.0 - dot( mapN.xy, mapN.xy ) ) ) );
	#endif
	mapN.xy *= normalScale;
	normal = normalize( tbn * mapN );
#elif defined( USE_BUMPMAP )
	normal = perturbNormalArb( - vViewPosition, normal, dHdxy_fwd(), faceDirection );
#endif`,ob=`#ifndef FLAT_SHADED
	varying vec3 vNormal;
	#ifdef USE_TANGENT
		varying vec3 vTangent;
		varying vec3 vBitangent;
	#endif
#endif`,lb=`#ifndef FLAT_SHADED
	varying vec3 vNormal;
	#ifdef USE_TANGENT
		varying vec3 vTangent;
		varying vec3 vBitangent;
	#endif
#endif`,cb=`#ifndef FLAT_SHADED
	vNormal = normalize( transformedNormal );
	#ifdef USE_TANGENT
		vTangent = normalize( transformedTangent );
		vBitangent = normalize( cross( vNormal, vTangent ) * tangent.w );
		#ifdef FLIP_SIDED
			vBitangent = - vBitangent;
		#endif
	#endif
#endif`,hb=`#ifdef USE_NORMALMAP
	uniform sampler2D normalMap;
	uniform vec2 normalScale;
#endif
#ifdef USE_NORMALMAP_OBJECTSPACE
	uniform mat3 normalMatrix;
#endif
#if ! defined ( USE_TANGENT ) && ( defined ( USE_NORMALMAP_TANGENTSPACE ) || defined ( USE_CLEARCOAT_NORMALMAP ) || defined( USE_ANISOTROPY ) )
	mat3 getTangentFrame( vec3 eye_pos, vec3 surf_norm, vec2 uv ) {
		vec3 q0 = dFdx( eye_pos.xyz );
		vec3 q1 = dFdy( eye_pos.xyz );
		vec2 st0 = dFdx( uv.st );
		vec2 st1 = dFdy( uv.st );
		vec3 N = surf_norm;
		vec3 q1perp = cross( q1, N );
		vec3 q0perp = cross( N, q0 );
		vec3 T = q1perp * st0.x + q0perp * st1.x;
		vec3 B = q1perp * st0.y + q0perp * st1.y;
		float det = max( dot( T, T ), dot( B, B ) );
		float scale = ( det == 0.0 ) ? 0.0 : inversesqrt( det );
		return mat3( T * scale, B * scale, N );
	}
#endif`,ub=`#ifdef USE_CLEARCOAT
	vec3 clearcoatNormal = nonPerturbedNormal;
#endif`,db=`#ifdef USE_CLEARCOAT_NORMALMAP
	vec3 clearcoatMapN = texture2D( clearcoatNormalMap, vClearcoatNormalMapUv ).xyz * 2.0 - 1.0;
	clearcoatMapN.xy *= clearcoatNormalScale;
	clearcoatNormal = normalize( tbn2 * clearcoatMapN );
#endif`,fb=`#ifdef USE_CLEARCOATMAP
	uniform sampler2D clearcoatMap;
#endif
#ifdef USE_CLEARCOAT_NORMALMAP
	uniform sampler2D clearcoatNormalMap;
	uniform vec2 clearcoatNormalScale;
#endif
#ifdef USE_CLEARCOAT_ROUGHNESSMAP
	uniform sampler2D clearcoatRoughnessMap;
#endif`,pb=`#ifdef USE_IRIDESCENCEMAP
	uniform sampler2D iridescenceMap;
#endif
#ifdef USE_IRIDESCENCE_THICKNESSMAP
	uniform sampler2D iridescenceThicknessMap;
#endif`,mb=`#ifdef OPAQUE
diffuseColor.a = 1.0;
#endif
#ifdef USE_TRANSMISSION
diffuseColor.a *= material.transmissionAlpha;
#endif
gl_FragColor = vec4( outgoingLight, diffuseColor.a );`,gb=`vec3 packNormalToRGB( const in vec3 normal ) {
	return normalize( normal ) * 0.5 + 0.5;
}
vec3 unpackRGBToNormal( const in vec3 rgb ) {
	return 2.0 * rgb.xyz - 1.0;
}
const float PackUpscale = 256. / 255.;const float UnpackDownscale = 255. / 256.;const float ShiftRight8 = 1. / 256.;
const float Inv255 = 1. / 255.;
const vec4 PackFactors = vec4( 1.0, 256.0, 256.0 * 256.0, 256.0 * 256.0 * 256.0 );
const vec2 UnpackFactors2 = vec2( UnpackDownscale, 1.0 / PackFactors.g );
const vec3 UnpackFactors3 = vec3( UnpackDownscale / PackFactors.rg, 1.0 / PackFactors.b );
const vec4 UnpackFactors4 = vec4( UnpackDownscale / PackFactors.rgb, 1.0 / PackFactors.a );
vec4 packDepthToRGBA( const in float v ) {
	if( v <= 0.0 )
		return vec4( 0., 0., 0., 0. );
	if( v >= 1.0 )
		return vec4( 1., 1., 1., 1. );
	float vuf;
	float af = modf( v * PackFactors.a, vuf );
	float bf = modf( vuf * ShiftRight8, vuf );
	float gf = modf( vuf * ShiftRight8, vuf );
	return vec4( vuf * Inv255, gf * PackUpscale, bf * PackUpscale, af );
}
vec3 packDepthToRGB( const in float v ) {
	if( v <= 0.0 )
		return vec3( 0., 0., 0. );
	if( v >= 1.0 )
		return vec3( 1., 1., 1. );
	float vuf;
	float bf = modf( v * PackFactors.b, vuf );
	float gf = modf( vuf * ShiftRight8, vuf );
	return vec3( vuf * Inv255, gf * PackUpscale, bf );
}
vec2 packDepthToRG( const in float v ) {
	if( v <= 0.0 )
		return vec2( 0., 0. );
	if( v >= 1.0 )
		return vec2( 1., 1. );
	float vuf;
	float gf = modf( v * 256., vuf );
	return vec2( vuf * Inv255, gf );
}
float unpackRGBAToDepth( const in vec4 v ) {
	return dot( v, UnpackFactors4 );
}
float unpackRGBToDepth( const in vec3 v ) {
	return dot( v, UnpackFactors3 );
}
float unpackRGToDepth( const in vec2 v ) {
	return v.r * UnpackFactors2.r + v.g * UnpackFactors2.g;
}
vec4 pack2HalfToRGBA( const in vec2 v ) {
	vec4 r = vec4( v.x, fract( v.x * 255.0 ), v.y, fract( v.y * 255.0 ) );
	return vec4( r.x - r.y / 255.0, r.y, r.z - r.w / 255.0, r.w );
}
vec2 unpackRGBATo2Half( const in vec4 v ) {
	return vec2( v.x + ( v.y / 255.0 ), v.z + ( v.w / 255.0 ) );
}
float viewZToOrthographicDepth( const in float viewZ, const in float near, const in float far ) {
	return ( viewZ + near ) / ( near - far );
}
float orthographicDepthToViewZ( const in float depth, const in float near, const in float far ) {
	#ifdef USE_REVERSED_DEPTH_BUFFER
	
		return depth * ( far - near ) - far;
	#else
		return depth * ( near - far ) - near;
	#endif
}
float viewZToPerspectiveDepth( const in float viewZ, const in float near, const in float far ) {
	return ( ( near + viewZ ) * far ) / ( ( far - near ) * viewZ );
}
float perspectiveDepthToViewZ( const in float depth, const in float near, const in float far ) {
	
	#ifdef USE_REVERSED_DEPTH_BUFFER
		return ( near * far ) / ( ( near - far ) * depth - near );
	#else
		return ( near * far ) / ( ( far - near ) * depth - far );
	#endif
}`,yb=`#ifdef PREMULTIPLIED_ALPHA
	gl_FragColor.rgb *= gl_FragColor.a;
#endif`,_b=`vec4 mvPosition = vec4( transformed, 1.0 );
#ifdef USE_BATCHING
	mvPosition = batchingMatrix * mvPosition;
#endif
#ifdef USE_INSTANCING
	mvPosition = instanceMatrix * mvPosition;
#endif
mvPosition = modelViewMatrix * mvPosition;
gl_Position = projectionMatrix * mvPosition;`,xb=`#ifdef DITHERING
	gl_FragColor.rgb = dithering( gl_FragColor.rgb );
#endif`,vb=`#ifdef DITHERING
	vec3 dithering( vec3 color ) {
		float grid_position = rand( gl_FragCoord.xy );
		vec3 dither_shift_RGB = vec3( 0.25 / 255.0, -0.25 / 255.0, 0.25 / 255.0 );
		dither_shift_RGB = mix( 2.0 * dither_shift_RGB, -2.0 * dither_shift_RGB, grid_position );
		return color + dither_shift_RGB;
	}
#endif`,bb=`float roughnessFactor = roughness;
#ifdef USE_ROUGHNESSMAP
	vec4 texelRoughness = texture2D( roughnessMap, vRoughnessMapUv );
	roughnessFactor *= texelRoughness.g;
#endif`,Sb=`#ifdef USE_ROUGHNESSMAP
	uniform sampler2D roughnessMap;
#endif`,Mb=`#if NUM_SPOT_LIGHT_COORDS > 0
	varying vec4 vSpotLightCoord[ NUM_SPOT_LIGHT_COORDS ];
#endif
#if NUM_SPOT_LIGHT_MAPS > 0
	uniform sampler2D spotLightMap[ NUM_SPOT_LIGHT_MAPS ];
#endif
#ifdef USE_SHADOWMAP
	#if NUM_SUN_LIGHT_SHADOWS > 0
		#define SUN_LIGHT_CASCADES 2
		#if defined( SHADOWMAP_TYPE_PCF )
			uniform sampler2DShadow sunShadowMap[ NUM_SUN_LIGHT_SHADOWS ];
		#else
			uniform sampler2D sunShadowMap[ NUM_SUN_LIGHT_SHADOWS ];
		#endif
		uniform mat4 sunShadowMatrix[ NUM_SUN_LIGHT_SHADOWS * SUN_LIGHT_CASCADES ];
		uniform vec4 sunShadowCascade[ NUM_SUN_LIGHT_SHADOWS * SUN_LIGHT_CASCADES ];
		varying vec4 vSunShadowWorldPosition;
		varying vec3 vSunShadowWorldNormal;
		struct SunLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
		};
		uniform SunLightShadow sunLightShadows[ NUM_SUN_LIGHT_SHADOWS ];
	#endif
	#if NUM_DIR_LIGHT_SHADOWS > 0
		#if defined( SHADOWMAP_TYPE_PCF )
			uniform sampler2DShadow directionalShadowMap[ NUM_DIR_LIGHT_SHADOWS ];
		#else
			uniform sampler2D directionalShadowMap[ NUM_DIR_LIGHT_SHADOWS ];
		#endif
		varying vec4 vDirectionalShadowCoord[ NUM_DIR_LIGHT_SHADOWS ];
		struct DirectionalLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
		};
		uniform DirectionalLightShadow directionalLightShadows[ NUM_DIR_LIGHT_SHADOWS ];
	#endif
	#if NUM_SPOT_LIGHT_SHADOWS > 0
		#if defined( SHADOWMAP_TYPE_PCF )
			uniform sampler2DShadow spotShadowMap[ NUM_SPOT_LIGHT_SHADOWS ];
		#else
			uniform sampler2D spotShadowMap[ NUM_SPOT_LIGHT_SHADOWS ];
		#endif
		struct SpotLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
		};
		uniform SpotLightShadow spotLightShadows[ NUM_SPOT_LIGHT_SHADOWS ];
	#endif
	#if NUM_POINT_LIGHT_SHADOWS > 0
		#if defined( SHADOWMAP_TYPE_PCF )
			uniform samplerCubeShadow pointShadowMap[ NUM_POINT_LIGHT_SHADOWS ];
		#elif defined( SHADOWMAP_TYPE_BASIC )
			uniform samplerCube pointShadowMap[ NUM_POINT_LIGHT_SHADOWS ];
		#endif
		varying vec4 vPointShadowCoord[ NUM_POINT_LIGHT_SHADOWS ];
		struct PointLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
			float shadowCameraNear;
			float shadowCameraFar;
		};
		uniform PointLightShadow pointLightShadows[ NUM_POINT_LIGHT_SHADOWS ];
	#endif
	#if defined( SHADOWMAP_TYPE_PCF )
		float interleavedGradientNoise( vec2 position ) {
			return fract( 52.9829189 * fract( dot( position, vec2( 0.06711056, 0.00583715 ) ) ) );
		}
		vec2 vogelDiskSample( int sampleIndex, int samplesCount, float phi ) {
			const float goldenAngle = 2.399963229728653;
			float r = sqrt( ( float( sampleIndex ) + 0.5 ) / float( samplesCount ) );
			float theta = float( sampleIndex ) * goldenAngle + phi;
			return vec2( cos( theta ), sin( theta ) ) * r;
		}
	#endif
	#if defined( SHADOWMAP_TYPE_PCF )
		float getShadow( sampler2DShadow shadowMap, vec2 shadowMapSize, float shadowIntensity, float shadowBias, float shadowRadius, vec4 shadowCoord ) {
			float shadow = 1.0;
			shadowCoord.xyz /= shadowCoord.w;
			shadowCoord.z += shadowBias;
			bool inFrustum = shadowCoord.x >= 0.0 && shadowCoord.x <= 1.0 && shadowCoord.y >= 0.0 && shadowCoord.y <= 1.0;
			bool frustumTest = inFrustum && shadowCoord.z <= 1.0;
			if ( frustumTest ) {
				vec2 texelSize = vec2( 1.0 ) / shadowMapSize;
				float radius = shadowRadius * texelSize.x;
				float phi = interleavedGradientNoise( gl_FragCoord.xy ) * PI2;
				shadow = (
					texture( shadowMap, vec3( shadowCoord.xy + vogelDiskSample( 0, 5, phi ) * radius, shadowCoord.z ) ) +
					texture( shadowMap, vec3( shadowCoord.xy + vogelDiskSample( 1, 5, phi ) * radius, shadowCoord.z ) ) +
					texture( shadowMap, vec3( shadowCoord.xy + vogelDiskSample( 2, 5, phi ) * radius, shadowCoord.z ) ) +
					texture( shadowMap, vec3( shadowCoord.xy + vogelDiskSample( 3, 5, phi ) * radius, shadowCoord.z ) ) +
					texture( shadowMap, vec3( shadowCoord.xy + vogelDiskSample( 4, 5, phi ) * radius, shadowCoord.z ) )
				) * 0.2;
			}
			return mix( 1.0, shadow, shadowIntensity );
		}
	#elif defined( SHADOWMAP_TYPE_VSM )
		float getShadow( sampler2D shadowMap, vec2 shadowMapSize, float shadowIntensity, float shadowBias, float shadowRadius, vec4 shadowCoord ) {
			float shadow = 1.0;
			shadowCoord.xyz /= shadowCoord.w;
			#ifdef USE_REVERSED_DEPTH_BUFFER
				shadowCoord.z -= shadowBias;
			#else
				shadowCoord.z += shadowBias;
			#endif
			bool inFrustum = shadowCoord.x >= 0.0 && shadowCoord.x <= 1.0 && shadowCoord.y >= 0.0 && shadowCoord.y <= 1.0;
			bool frustumTest = inFrustum && shadowCoord.z <= 1.0;
			if ( frustumTest ) {
				vec2 distribution = texture2D( shadowMap, shadowCoord.xy ).rg;
				float mean = distribution.x;
				float variance = distribution.y * distribution.y;
				#ifdef USE_REVERSED_DEPTH_BUFFER
					float hard_shadow = step( mean, shadowCoord.z );
				#else
					float hard_shadow = step( shadowCoord.z, mean );
				#endif
				
				if ( hard_shadow == 1.0 ) {
					shadow = 1.0;
				} else {
					variance = max( variance, 0.0000001 );
					float d = shadowCoord.z - mean;
					float p_max = variance / ( variance + d * d );
					p_max = clamp( ( p_max - 0.3 ) / 0.65, 0.0, 1.0 );
					shadow = max( hard_shadow, p_max );
				}
			}
			return mix( 1.0, shadow, shadowIntensity );
		}
	#else
		float getShadow( sampler2D shadowMap, vec2 shadowMapSize, float shadowIntensity, float shadowBias, float shadowRadius, vec4 shadowCoord ) {
			float shadow = 1.0;
			shadowCoord.xyz /= shadowCoord.w;
			#ifdef USE_REVERSED_DEPTH_BUFFER
				shadowCoord.z -= shadowBias;
			#else
				shadowCoord.z += shadowBias;
			#endif
			bool inFrustum = shadowCoord.x >= 0.0 && shadowCoord.x <= 1.0 && shadowCoord.y >= 0.0 && shadowCoord.y <= 1.0;
			bool frustumTest = inFrustum && shadowCoord.z <= 1.0;
			if ( frustumTest ) {
				float depth = texture2D( shadowMap, shadowCoord.xy ).r;
				#ifdef USE_REVERSED_DEPTH_BUFFER
					shadow = step( depth, shadowCoord.z );
				#else
					shadow = step( shadowCoord.z, depth );
				#endif
			}
			return mix( 1.0, shadow, shadowIntensity );
		}
	#endif
	#if NUM_SUN_LIGHT_SHADOWS > 0
		float getSunShadow(
			#if defined( SHADOWMAP_TYPE_PCF )
				sampler2DShadow shadowMap,
			#else
				sampler2D shadowMap,
			#endif
			SunLightShadow sunLightShadow,
			int shadowIndex
		) {
			vec4 shadowWorldPosition = vec4( vSunShadowWorldPosition.xyz + vSunShadowWorldNormal * sunLightShadow.shadowNormalBias, 1.0 );
			float viewDepth = vSunShadowWorldPosition.w;
			int cascadeOffset = shadowIndex * SUN_LIGHT_CASCADES;
			float shadow = 1.0;
			for ( int i = SUN_LIGHT_CASCADES - 1; i >= 0; i -- ) {
				vec4 cascade = sunShadowCascade[ cascadeOffset + i ];
				if ( viewDepth >= cascade.x && viewDepth < cascade.y ) {
					float cascadeShadow = getShadow(
						shadowMap,
						sunLightShadow.shadowMapSize,
						sunLightShadow.shadowIntensity,
						sunLightShadow.shadowBias,
						sunLightShadow.shadowRadius,
						sunShadowMatrix[ cascadeOffset + i ] * shadowWorldPosition
					);
					shadow = mix( cascadeShadow, shadow, smoothstep( cascade.z, cascade.y, viewDepth ) );
				}
			}
			return shadow;
		}
	#endif
	#if NUM_POINT_LIGHT_SHADOWS > 0
	#if defined( SHADOWMAP_TYPE_PCF )
	float getPointShadow( samplerCubeShadow shadowMap, vec2 shadowMapSize, float shadowIntensity, float shadowBias, float shadowRadius, vec4 shadowCoord, float shadowCameraNear, float shadowCameraFar ) {
		float shadow = 1.0;
		vec3 lightToPosition = shadowCoord.xyz;
		vec3 bd3D = normalize( lightToPosition );
		vec3 absVec = abs( lightToPosition );
		float viewSpaceZ = max( max( absVec.x, absVec.y ), absVec.z );
		if ( viewSpaceZ - shadowCameraFar <= 0.0 && viewSpaceZ - shadowCameraNear >= 0.0 ) {
			#ifdef USE_REVERSED_DEPTH_BUFFER
				float dp = ( shadowCameraNear * ( shadowCameraFar - viewSpaceZ ) ) / ( viewSpaceZ * ( shadowCameraFar - shadowCameraNear ) );
				dp -= shadowBias;
			#else
				float dp = ( shadowCameraFar * ( viewSpaceZ - shadowCameraNear ) ) / ( viewSpaceZ * ( shadowCameraFar - shadowCameraNear ) );
				dp += shadowBias;
			#endif
			float texelSize = shadowRadius / shadowMapSize.x;
			vec3 absDir = abs( bd3D );
			vec3 tangent = absDir.x > absDir.z ? vec3( 0.0, 1.0, 0.0 ) : vec3( 1.0, 0.0, 0.0 );
			tangent = normalize( cross( bd3D, tangent ) );
			vec3 bitangent = cross( bd3D, tangent );
			float phi = interleavedGradientNoise( gl_FragCoord.xy ) * PI2;
			vec2 sample0 = vogelDiskSample( 0, 5, phi );
			vec2 sample1 = vogelDiskSample( 1, 5, phi );
			vec2 sample2 = vogelDiskSample( 2, 5, phi );
			vec2 sample3 = vogelDiskSample( 3, 5, phi );
			vec2 sample4 = vogelDiskSample( 4, 5, phi );
			shadow = (
				texture( shadowMap, vec4( bd3D + ( tangent * sample0.x + bitangent * sample0.y ) * texelSize, dp ) ) +
				texture( shadowMap, vec4( bd3D + ( tangent * sample1.x + bitangent * sample1.y ) * texelSize, dp ) ) +
				texture( shadowMap, vec4( bd3D + ( tangent * sample2.x + bitangent * sample2.y ) * texelSize, dp ) ) +
				texture( shadowMap, vec4( bd3D + ( tangent * sample3.x + bitangent * sample3.y ) * texelSize, dp ) ) +
				texture( shadowMap, vec4( bd3D + ( tangent * sample4.x + bitangent * sample4.y ) * texelSize, dp ) )
			) * 0.2;
		}
		return mix( 1.0, shadow, shadowIntensity );
	}
	#elif defined( SHADOWMAP_TYPE_BASIC )
	float getPointShadow( samplerCube shadowMap, vec2 shadowMapSize, float shadowIntensity, float shadowBias, float shadowRadius, vec4 shadowCoord, float shadowCameraNear, float shadowCameraFar ) {
		float shadow = 1.0;
		vec3 lightToPosition = shadowCoord.xyz;
		vec3 absVec = abs( lightToPosition );
		float viewSpaceZ = max( max( absVec.x, absVec.y ), absVec.z );
		if ( viewSpaceZ - shadowCameraFar <= 0.0 && viewSpaceZ - shadowCameraNear >= 0.0 ) {
			float dp = ( shadowCameraFar * ( viewSpaceZ - shadowCameraNear ) ) / ( viewSpaceZ * ( shadowCameraFar - shadowCameraNear ) );
			dp += shadowBias;
			vec3 bd3D = normalize( lightToPosition );
			float depth = textureCube( shadowMap, bd3D ).r;
			#ifdef USE_REVERSED_DEPTH_BUFFER
				depth = 1.0 - depth;
			#endif
			shadow = step( dp, depth );
		}
		return mix( 1.0, shadow, shadowIntensity );
	}
	#endif
	#endif
#endif`,wb=`#if NUM_SPOT_LIGHT_COORDS > 0
	uniform mat4 spotLightMatrix[ NUM_SPOT_LIGHT_COORDS ];
	varying vec4 vSpotLightCoord[ NUM_SPOT_LIGHT_COORDS ];
#endif
#ifdef USE_SHADOWMAP
	#if NUM_SUN_LIGHT_SHADOWS > 0
		varying vec4 vSunShadowWorldPosition;
		varying vec3 vSunShadowWorldNormal;
	#endif
	#if NUM_DIR_LIGHT_SHADOWS > 0
		uniform mat4 directionalShadowMatrix[ NUM_DIR_LIGHT_SHADOWS ];
		varying vec4 vDirectionalShadowCoord[ NUM_DIR_LIGHT_SHADOWS ];
		struct DirectionalLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
		};
		uniform DirectionalLightShadow directionalLightShadows[ NUM_DIR_LIGHT_SHADOWS ];
	#endif
	#if NUM_SPOT_LIGHT_SHADOWS > 0
		struct SpotLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
		};
		uniform SpotLightShadow spotLightShadows[ NUM_SPOT_LIGHT_SHADOWS ];
	#endif
	#if NUM_POINT_LIGHT_SHADOWS > 0
		uniform mat4 pointShadowMatrix[ NUM_POINT_LIGHT_SHADOWS ];
		varying vec4 vPointShadowCoord[ NUM_POINT_LIGHT_SHADOWS ];
		struct PointLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
			float shadowCameraNear;
			float shadowCameraFar;
		};
		uniform PointLightShadow pointLightShadows[ NUM_POINT_LIGHT_SHADOWS ];
	#endif
#endif`,Tb=`#if ( defined( USE_SHADOWMAP ) && ( NUM_DIR_LIGHT_SHADOWS > 0 || NUM_SUN_LIGHT_SHADOWS > 0 || NUM_POINT_LIGHT_SHADOWS > 0 ) ) || ( NUM_SPOT_LIGHT_COORDS > 0 )
	#ifdef HAS_NORMAL
		vec3 shadowWorldNormal = transformNormalByInverseViewMatrix( transformedNormal, viewMatrix );
	#else
		vec3 shadowWorldNormal = vec3( 0.0 );
	#endif
	vec4 shadowWorldPosition;
#endif
#if defined( USE_SHADOWMAP )
	#if NUM_SUN_LIGHT_SHADOWS > 0
		vSunShadowWorldPosition = vec4( worldPosition.xyz, - mvPosition.z );
		vSunShadowWorldNormal = shadowWorldNormal;
	#endif
	#if NUM_DIR_LIGHT_SHADOWS > 0
		#pragma unroll_loop_start
		for ( int i = 0; i < NUM_DIR_LIGHT_SHADOWS; i ++ ) {
			shadowWorldPosition = worldPosition + vec4( shadowWorldNormal * directionalLightShadows[ i ].shadowNormalBias, 0 );
			vDirectionalShadowCoord[ i ] = directionalShadowMatrix[ i ] * shadowWorldPosition;
		}
		#pragma unroll_loop_end
	#endif
	#if NUM_POINT_LIGHT_SHADOWS > 0
		#pragma unroll_loop_start
		for ( int i = 0; i < NUM_POINT_LIGHT_SHADOWS; i ++ ) {
			shadowWorldPosition = worldPosition + vec4( shadowWorldNormal * pointLightShadows[ i ].shadowNormalBias, 0 );
			vPointShadowCoord[ i ] = pointShadowMatrix[ i ] * shadowWorldPosition;
		}
		#pragma unroll_loop_end
	#endif
#endif
#if NUM_SPOT_LIGHT_COORDS > 0
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_SPOT_LIGHT_COORDS; i ++ ) {
		shadowWorldPosition = worldPosition;
		#if ( defined( USE_SHADOWMAP ) && UNROLLED_LOOP_INDEX < NUM_SPOT_LIGHT_SHADOWS )
			shadowWorldPosition.xyz += shadowWorldNormal * spotLightShadows[ i ].shadowNormalBias;
		#endif
		vSpotLightCoord[ i ] = spotLightMatrix[ i ] * shadowWorldPosition;
	}
	#pragma unroll_loop_end
#endif`,Eb=`float getShadowMask() {
	float shadow = 1.0;
	#ifdef USE_SHADOWMAP
	#if NUM_SUN_LIGHT_SHADOWS > 0
	SunLightShadow sunLight;
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_SUN_LIGHT_SHADOWS; i ++ ) {
		sunLight = sunLightShadows[ i ];
		shadow *= receiveShadow ? getSunShadow( sunShadowMap[ i ], sunLight, UNROLLED_LOOP_INDEX ) : 1.0;
	}
	#pragma unroll_loop_end
	#endif
	#if NUM_DIR_LIGHT_SHADOWS > 0
	DirectionalLightShadow directionalLight;
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_DIR_LIGHT_SHADOWS; i ++ ) {
		directionalLight = directionalLightShadows[ i ];
		shadow *= receiveShadow ? getShadow( directionalShadowMap[ i ], directionalLight.shadowMapSize, directionalLight.shadowIntensity, directionalLight.shadowBias, directionalLight.shadowRadius, vDirectionalShadowCoord[ i ] ) : 1.0;
	}
	#pragma unroll_loop_end
	#endif
	#if NUM_SPOT_LIGHT_SHADOWS > 0
	SpotLightShadow spotLight;
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_SPOT_LIGHT_SHADOWS; i ++ ) {
		spotLight = spotLightShadows[ i ];
		shadow *= receiveShadow ? getShadow( spotShadowMap[ i ], spotLight.shadowMapSize, spotLight.shadowIntensity, spotLight.shadowBias, spotLight.shadowRadius, vSpotLightCoord[ i ] ) : 1.0;
	}
	#pragma unroll_loop_end
	#endif
	#if NUM_POINT_LIGHT_SHADOWS > 0 && ( defined( SHADOWMAP_TYPE_PCF ) || defined( SHADOWMAP_TYPE_BASIC ) )
	PointLightShadow pointLight;
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_POINT_LIGHT_SHADOWS; i ++ ) {
		pointLight = pointLightShadows[ i ];
		shadow *= receiveShadow ? getPointShadow( pointShadowMap[ i ], pointLight.shadowMapSize, pointLight.shadowIntensity, pointLight.shadowBias, pointLight.shadowRadius, vPointShadowCoord[ i ], pointLight.shadowCameraNear, pointLight.shadowCameraFar ) : 1.0;
	}
	#pragma unroll_loop_end
	#endif
	#endif
	return shadow;
}`,Ab=`#ifdef USE_SKINNING
	mat4 boneMatX = getBoneMatrix( skinIndex.x );
	mat4 boneMatY = getBoneMatrix( skinIndex.y );
	mat4 boneMatZ = getBoneMatrix( skinIndex.z );
	mat4 boneMatW = getBoneMatrix( skinIndex.w );
#endif`,Cb=`#ifdef USE_SKINNING
	uniform mat4 bindMatrix;
	uniform mat4 bindMatrixInverse;
	uniform highp sampler2D boneTexture;
	mat4 getBoneMatrix( const in float i ) {
		int size = textureSize( boneTexture, 0 ).x;
		int j = int( i ) * 4;
		int x = j % size;
		int y = j / size;
		vec4 v1 = texelFetch( boneTexture, ivec2( x, y ), 0 );
		vec4 v2 = texelFetch( boneTexture, ivec2( x + 1, y ), 0 );
		vec4 v3 = texelFetch( boneTexture, ivec2( x + 2, y ), 0 );
		vec4 v4 = texelFetch( boneTexture, ivec2( x + 3, y ), 0 );
		return mat4( v1, v2, v3, v4 );
	}
#endif`,Rb=`#ifdef USE_SKINNING
	vec4 skinVertex = bindMatrix * vec4( transformed, 1.0 );
	vec4 skinned = vec4( 0.0 );
	skinned += boneMatX * skinVertex * skinWeight.x;
	skinned += boneMatY * skinVertex * skinWeight.y;
	skinned += boneMatZ * skinVertex * skinWeight.z;
	skinned += boneMatW * skinVertex * skinWeight.w;
	transformed = ( bindMatrixInverse * skinned ).xyz;
#endif`,Pb=`#ifdef USE_SKINNING
	mat4 skinMatrix = mat4( 0.0 );
	skinMatrix += skinWeight.x * boneMatX;
	skinMatrix += skinWeight.y * boneMatY;
	skinMatrix += skinWeight.z * boneMatZ;
	skinMatrix += skinWeight.w * boneMatW;
	skinMatrix = bindMatrixInverse * skinMatrix * bindMatrix;
	objectNormal = vec4( skinMatrix * vec4( objectNormal, 0.0 ) ).xyz;
	#ifdef USE_TANGENT
		objectTangent = vec4( skinMatrix * vec4( objectTangent, 0.0 ) ).xyz;
	#endif
#endif`,Ib=`float specularStrength;
#ifdef USE_SPECULARMAP
	vec4 texelSpecular = texture2D( specularMap, vSpecularMapUv );
	specularStrength = texelSpecular.r;
#else
	specularStrength = 1.0;
#endif`,Lb=`#ifdef USE_SPECULARMAP
	uniform sampler2D specularMap;
#endif`,Db=`#if defined( TONE_MAPPING )
	gl_FragColor.rgb = toneMapping( gl_FragColor.rgb );
#endif`,Nb=`#ifndef saturate
#define saturate( a ) clamp( a, 0.0, 1.0 )
#endif
uniform float toneMappingExposure;
vec3 LinearToneMapping( vec3 color ) {
	return saturate( toneMappingExposure * color );
}
vec3 ReinhardToneMapping( vec3 color ) {
	color *= toneMappingExposure;
	return saturate( color / ( vec3( 1.0 ) + color ) );
}
vec3 CineonToneMapping( vec3 color ) {
	color *= toneMappingExposure;
	color = max( vec3( 0.0 ), color - 0.004 );
	return pow( ( color * ( 6.2 * color + 0.5 ) ) / ( color * ( 6.2 * color + 1.7 ) + 0.06 ), vec3( 2.2 ) );
}
vec3 RRTAndODTFit( vec3 v ) {
	vec3 a = v * ( v + 0.0245786 ) - 0.000090537;
	vec3 b = v * ( 0.983729 * v + 0.4329510 ) + 0.238081;
	return a / b;
}
vec3 ACESFilmicToneMapping( vec3 color ) {
	const mat3 ACESInputMat = mat3(
		vec3( 0.59719, 0.07600, 0.02840 ),		vec3( 0.35458, 0.90834, 0.13383 ),
		vec3( 0.04823, 0.01566, 0.83777 )
	);
	const mat3 ACESOutputMat = mat3(
		vec3(  1.60475, -0.10208, -0.00327 ),		vec3( -0.53108,  1.10813, -0.07276 ),
		vec3( -0.07367, -0.00605,  1.07602 )
	);
	color *= toneMappingExposure / 0.6;
	color = ACESInputMat * color;
	color = RRTAndODTFit( color );
	color = ACESOutputMat * color;
	return saturate( color );
}
const mat3 LINEAR_REC2020_TO_LINEAR_SRGB = mat3(
	vec3( 1.6605, - 0.1246, - 0.0182 ),
	vec3( - 0.5876, 1.1329, - 0.1006 ),
	vec3( - 0.0728, - 0.0083, 1.1187 )
);
const mat3 LINEAR_SRGB_TO_LINEAR_REC2020 = mat3(
	vec3( 0.6274, 0.0691, 0.0164 ),
	vec3( 0.3293, 0.9195, 0.0880 ),
	vec3( 0.0433, 0.0113, 0.8956 )
);
vec3 agxDefaultContrastApprox( vec3 x ) {
	vec3 x2 = x * x;
	vec3 x4 = x2 * x2;
	return + 15.5 * x4 * x2
		- 40.14 * x4 * x
		+ 31.96 * x4
		- 6.868 * x2 * x
		+ 0.4298 * x2
		+ 0.1191 * x
		- 0.00232;
}
vec3 AgXToneMapping( vec3 color ) {
	const mat3 AgXInsetMatrix = mat3(
		vec3( 0.856627153315983, 0.137318972929847, 0.11189821299995 ),
		vec3( 0.0951212405381588, 0.761241990602591, 0.0767994186031903 ),
		vec3( 0.0482516061458583, 0.101439036467562, 0.811302368396859 )
	);
	const mat3 AgXOutsetMatrix = mat3(
		vec3( 1.1271005818144368, - 0.1413297634984383, - 0.14132976349843826 ),
		vec3( - 0.11060664309660323, 1.157823702216272, - 0.11060664309660294 ),
		vec3( - 0.016493938717834573, - 0.016493938717834257, 1.2519364065950405 )
	);
	const float AgxMinEv = - 12.47393;	const float AgxMaxEv = 4.026069;
	color *= toneMappingExposure;
	color = LINEAR_SRGB_TO_LINEAR_REC2020 * color;
	color = AgXInsetMatrix * color;
	color = max( color, 1e-10 );	color = log2( color );
	color = ( color - AgxMinEv ) / ( AgxMaxEv - AgxMinEv );
	color = clamp( color, 0.0, 1.0 );
	color = agxDefaultContrastApprox( color );
	color = AgXOutsetMatrix * color;
	color = pow( max( vec3( 0.0 ), color ), vec3( 2.2 ) );
	color = LINEAR_REC2020_TO_LINEAR_SRGB * color;
	color = clamp( color, 0.0, 1.0 );
	return color;
}
vec3 NeutralToneMapping( vec3 color ) {
	const float StartCompression = 0.8 - 0.04;
	const float Desaturation = 0.15;
	color *= toneMappingExposure;
	float x = min( color.r, min( color.g, color.b ) );
	float offset = x < 0.08 ? x - 6.25 * x * x : 0.04;
	color -= offset;
	float peak = max( color.r, max( color.g, color.b ) );
	if ( peak < StartCompression ) return color;
	float d = 1. - StartCompression;
	float newPeak = 1. - d * d / ( peak + d - StartCompression );
	color *= newPeak / peak;
	float g = 1. - 1. / ( Desaturation * ( peak - newPeak ) + 1. );
	return mix( color, vec3( newPeak ), g );
}
vec3 CustomToneMapping( vec3 color ) { return color; }`,Ub=`#ifdef USE_TRANSMISSION
	material.transmission = transmission;
	material.transmissionAlpha = 1.0;
	material.thickness = thickness;
	material.attenuationDistance = attenuationDistance;
	material.attenuationColor = attenuationColor;
	#ifdef USE_TRANSMISSIONMAP
		material.transmission *= texture2D( transmissionMap, vTransmissionMapUv ).r;
	#endif
	#ifdef USE_THICKNESSMAP
		material.thickness *= texture2D( thicknessMap, vThicknessMapUv ).g;
	#endif
	vec3 pos = vWorldPosition;
	vec3 v = normalize( cameraPosition - pos );
	vec3 n = transformNormalByInverseViewMatrix( normal, viewMatrix );
	vec4 transmitted = getIBLVolumeRefraction(
		n, v, material.roughness, material.diffuseContribution, material.specularColorBlended, material.specularF90,
		pos, modelMatrix, viewMatrix, projectionMatrix, material.dispersion, material.ior, material.thickness,
		material.attenuationColor, material.attenuationDistance );
	material.transmissionAlpha = mix( material.transmissionAlpha, transmitted.a, material.transmission );
	totalDiffuse = mix( totalDiffuse, transmitted.rgb, material.transmission );
#endif`,Ob=`#ifdef USE_TRANSMISSION
	uniform float transmission;
	uniform float thickness;
	uniform float attenuationDistance;
	uniform vec3 attenuationColor;
	#ifdef USE_TRANSMISSIONMAP
		uniform sampler2D transmissionMap;
	#endif
	#ifdef USE_THICKNESSMAP
		uniform sampler2D thicknessMap;
	#endif
	uniform vec2 transmissionSamplerSize;
	uniform sampler2D transmissionSamplerMap;
	uniform mat4 modelMatrix;
	uniform mat4 projectionMatrix;
	varying vec3 vWorldPosition;
	float w0( float a ) {
		return ( 1.0 / 6.0 ) * ( a * ( a * ( - a + 3.0 ) - 3.0 ) + 1.0 );
	}
	float w1( float a ) {
		return ( 1.0 / 6.0 ) * ( a *  a * ( 3.0 * a - 6.0 ) + 4.0 );
	}
	float w2( float a ){
		return ( 1.0 / 6.0 ) * ( a * ( a * ( - 3.0 * a + 3.0 ) + 3.0 ) + 1.0 );
	}
	float w3( float a ) {
		return ( 1.0 / 6.0 ) * ( a * a * a );
	}
	float g0( float a ) {
		return w0( a ) + w1( a );
	}
	float g1( float a ) {
		return w2( a ) + w3( a );
	}
	float h0( float a ) {
		return - 1.0 + w1( a ) / ( w0( a ) + w1( a ) );
	}
	float h1( float a ) {
		return 1.0 + w3( a ) / ( w2( a ) + w3( a ) );
	}
	vec4 bicubic( sampler2D tex, vec2 uv, vec4 texelSize, float lod ) {
		uv = uv * texelSize.zw + 0.5;
		vec2 iuv = floor( uv );
		vec2 fuv = fract( uv );
		float g0x = g0( fuv.x );
		float g1x = g1( fuv.x );
		float h0x = h0( fuv.x );
		float h1x = h1( fuv.x );
		float h0y = h0( fuv.y );
		float h1y = h1( fuv.y );
		vec2 p0 = ( vec2( iuv.x + h0x, iuv.y + h0y ) - 0.5 ) * texelSize.xy;
		vec2 p1 = ( vec2( iuv.x + h1x, iuv.y + h0y ) - 0.5 ) * texelSize.xy;
		vec2 p2 = ( vec2( iuv.x + h0x, iuv.y + h1y ) - 0.5 ) * texelSize.xy;
		vec2 p3 = ( vec2( iuv.x + h1x, iuv.y + h1y ) - 0.5 ) * texelSize.xy;
		return g0( fuv.y ) * ( g0x * textureLod( tex, p0, lod ) + g1x * textureLod( tex, p1, lod ) ) +
			g1( fuv.y ) * ( g0x * textureLod( tex, p2, lod ) + g1x * textureLod( tex, p3, lod ) );
	}
	vec4 textureBicubic( sampler2D sampler, vec2 uv, float lod ) {
		vec2 fLodSize = vec2( textureSize( sampler, int( lod ) ) );
		vec2 cLodSize = vec2( textureSize( sampler, int( lod + 1.0 ) ) );
		vec2 fLodSizeInv = 1.0 / fLodSize;
		vec2 cLodSizeInv = 1.0 / cLodSize;
		vec4 fSample = bicubic( sampler, uv, vec4( fLodSizeInv, fLodSize ), floor( lod ) );
		vec4 cSample = bicubic( sampler, uv, vec4( cLodSizeInv, cLodSize ), ceil( lod ) );
		return mix( fSample, cSample, fract( lod ) );
	}
	vec3 getVolumeTransmissionRay( const in vec3 n, const in vec3 v, const in float thickness, const in float ior, const in mat4 modelMatrix ) {
		vec3 refractionVector = refract( - v, normalize( n ), 1.0 / ior );
		vec3 modelScale;
		modelScale.x = length( vec3( modelMatrix[ 0 ].xyz ) );
		modelScale.y = length( vec3( modelMatrix[ 1 ].xyz ) );
		modelScale.z = length( vec3( modelMatrix[ 2 ].xyz ) );
		return normalize( refractionVector ) * thickness * modelScale;
	}
	float applyIorToRoughness( const in float roughness, const in float ior ) {
		return roughness * clamp( ior * 2.0 - 2.0, 0.0, 1.0 );
	}
	vec4 getTransmissionSample( const in vec2 fragCoord, const in float roughness, const in float ior ) {
		float lod = log2( transmissionSamplerSize.x ) * applyIorToRoughness( roughness, ior );
		return textureBicubic( transmissionSamplerMap, fragCoord.xy, lod );
	}
	vec3 volumeAttenuation( const in float transmissionDistance, const in vec3 attenuationColor, const in float attenuationDistance ) {
		if ( isinf( attenuationDistance ) ) {
			return vec3( 1.0 );
		} else {
			vec3 attenuationCoefficient = -log( attenuationColor ) / attenuationDistance;
			vec3 transmittance = exp( - attenuationCoefficient * transmissionDistance );			return transmittance;
		}
	}
	vec4 getIBLVolumeRefraction( const in vec3 n, const in vec3 v, const in float roughness, const in vec3 diffuseColor,
		const in vec3 specularColor, const in float specularF90, const in vec3 position, const in mat4 modelMatrix,
		const in mat4 viewMatrix, const in mat4 projMatrix, const in float dispersion, const in float ior, const in float thickness,
		const in vec3 attenuationColor, const in float attenuationDistance ) {
		vec4 transmittedLight;
		vec3 transmittance;
		#ifdef USE_DISPERSION
			float halfSpread = ( ior - 1.0 ) * 0.025 * dispersion;
			vec3 iors = vec3( ior - halfSpread, ior, ior + halfSpread );
			for ( int i = 0; i < 3; i ++ ) {
				vec3 transmissionRay = getVolumeTransmissionRay( n, v, thickness, iors[ i ], modelMatrix );
				vec3 refractedRayExit = position + transmissionRay;
				vec4 ndcPos = projMatrix * viewMatrix * vec4( refractedRayExit, 1.0 );
				vec2 refractionCoords = ndcPos.xy / ndcPos.w;
				refractionCoords += 1.0;
				refractionCoords /= 2.0;
				vec4 transmissionSample = getTransmissionSample( refractionCoords, roughness, iors[ i ] );
				transmittedLight[ i ] = transmissionSample[ i ];
				transmittedLight.a += transmissionSample.a;
				transmittance[ i ] = diffuseColor[ i ] * volumeAttenuation( length( transmissionRay ), attenuationColor, attenuationDistance )[ i ];
			}
			transmittedLight.a /= 3.0;
		#else
			vec3 transmissionRay = getVolumeTransmissionRay( n, v, thickness, ior, modelMatrix );
			vec3 refractedRayExit = position + transmissionRay;
			vec4 ndcPos = projMatrix * viewMatrix * vec4( refractedRayExit, 1.0 );
			vec2 refractionCoords = ndcPos.xy / ndcPos.w;
			refractionCoords += 1.0;
			refractionCoords /= 2.0;
			transmittedLight = getTransmissionSample( refractionCoords, roughness, ior );
			transmittance = diffuseColor * volumeAttenuation( length( transmissionRay ), attenuationColor, attenuationDistance );
		#endif
		vec3 attenuatedColor = transmittance * transmittedLight.rgb;
		vec3 F = EnvironmentBRDF( n, v, specularColor, specularF90, roughness );
		float transmittanceFactor = ( transmittance.r + transmittance.g + transmittance.b ) / 3.0;
		return vec4( ( 1.0 - F ) * attenuatedColor, 1.0 - ( 1.0 - transmittedLight.a ) * transmittanceFactor );
	}
#endif`,Fb=`#if defined( USE_UV ) || defined( USE_ANISOTROPY )
	varying vec2 vUv;
#endif
#ifdef USE_MAP
	varying vec2 vMapUv;
#endif
#ifdef USE_ALPHAMAP
	varying vec2 vAlphaMapUv;
#endif
#ifdef USE_LIGHTMAP
	varying vec2 vLightMapUv;
#endif
#ifdef USE_AOMAP
	varying vec2 vAoMapUv;
#endif
#ifdef USE_BUMPMAP
	varying vec2 vBumpMapUv;
#endif
#ifdef USE_NORMALMAP
	varying vec2 vNormalMapUv;
#endif
#ifdef USE_EMISSIVEMAP
	varying vec2 vEmissiveMapUv;
#endif
#ifdef USE_METALNESSMAP
	varying vec2 vMetalnessMapUv;
#endif
#ifdef USE_ROUGHNESSMAP
	varying vec2 vRoughnessMapUv;
#endif
#ifdef USE_ANISOTROPYMAP
	varying vec2 vAnisotropyMapUv;
#endif
#ifdef USE_CLEARCOATMAP
	varying vec2 vClearcoatMapUv;
#endif
#ifdef USE_CLEARCOAT_NORMALMAP
	varying vec2 vClearcoatNormalMapUv;
#endif
#ifdef USE_CLEARCOAT_ROUGHNESSMAP
	varying vec2 vClearcoatRoughnessMapUv;
#endif
#ifdef USE_IRIDESCENCEMAP
	varying vec2 vIridescenceMapUv;
#endif
#ifdef USE_IRIDESCENCE_THICKNESSMAP
	varying vec2 vIridescenceThicknessMapUv;
#endif
#ifdef USE_SHEEN_COLORMAP
	varying vec2 vSheenColorMapUv;
#endif
#ifdef USE_SHEEN_ROUGHNESSMAP
	varying vec2 vSheenRoughnessMapUv;
#endif
#ifdef USE_SPECULARMAP
	varying vec2 vSpecularMapUv;
#endif
#ifdef USE_SPECULAR_COLORMAP
	varying vec2 vSpecularColorMapUv;
#endif
#ifdef USE_SPECULAR_INTENSITYMAP
	varying vec2 vSpecularIntensityMapUv;
#endif
#ifdef USE_TRANSMISSIONMAP
	uniform mat3 transmissionMapTransform;
	varying vec2 vTransmissionMapUv;
#endif
#ifdef USE_THICKNESSMAP
	uniform mat3 thicknessMapTransform;
	varying vec2 vThicknessMapUv;
#endif`,Bb=`#if defined( USE_UV ) || defined( USE_ANISOTROPY )
	varying vec2 vUv;
#endif
#ifdef USE_MAP
	uniform mat3 mapTransform;
	varying vec2 vMapUv;
#endif
#ifdef USE_ALPHAMAP
	uniform mat3 alphaMapTransform;
	varying vec2 vAlphaMapUv;
#endif
#ifdef USE_LIGHTMAP
	uniform mat3 lightMapTransform;
	varying vec2 vLightMapUv;
#endif
#ifdef USE_AOMAP
	uniform mat3 aoMapTransform;
	varying vec2 vAoMapUv;
#endif
#ifdef USE_BUMPMAP
	uniform mat3 bumpMapTransform;
	varying vec2 vBumpMapUv;
#endif
#ifdef USE_NORMALMAP
	uniform mat3 normalMapTransform;
	varying vec2 vNormalMapUv;
#endif
#ifdef USE_DISPLACEMENTMAP
	uniform mat3 displacementMapTransform;
	varying vec2 vDisplacementMapUv;
#endif
#ifdef USE_EMISSIVEMAP
	uniform mat3 emissiveMapTransform;
	varying vec2 vEmissiveMapUv;
#endif
#ifdef USE_METALNESSMAP
	uniform mat3 metalnessMapTransform;
	varying vec2 vMetalnessMapUv;
#endif
#ifdef USE_ROUGHNESSMAP
	uniform mat3 roughnessMapTransform;
	varying vec2 vRoughnessMapUv;
#endif
#ifdef USE_ANISOTROPYMAP
	uniform mat3 anisotropyMapTransform;
	varying vec2 vAnisotropyMapUv;
#endif
#ifdef USE_CLEARCOATMAP
	uniform mat3 clearcoatMapTransform;
	varying vec2 vClearcoatMapUv;
#endif
#ifdef USE_CLEARCOAT_NORMALMAP
	uniform mat3 clearcoatNormalMapTransform;
	varying vec2 vClearcoatNormalMapUv;
#endif
#ifdef USE_CLEARCOAT_ROUGHNESSMAP
	uniform mat3 clearcoatRoughnessMapTransform;
	varying vec2 vClearcoatRoughnessMapUv;
#endif
#ifdef USE_SHEEN_COLORMAP
	uniform mat3 sheenColorMapTransform;
	varying vec2 vSheenColorMapUv;
#endif
#ifdef USE_SHEEN_ROUGHNESSMAP
	uniform mat3 sheenRoughnessMapTransform;
	varying vec2 vSheenRoughnessMapUv;
#endif
#ifdef USE_IRIDESCENCEMAP
	uniform mat3 iridescenceMapTransform;
	varying vec2 vIridescenceMapUv;
#endif
#ifdef USE_IRIDESCENCE_THICKNESSMAP
	uniform mat3 iridescenceThicknessMapTransform;
	varying vec2 vIridescenceThicknessMapUv;
#endif
#ifdef USE_SPECULARMAP
	uniform mat3 specularMapTransform;
	varying vec2 vSpecularMapUv;
#endif
#ifdef USE_SPECULAR_COLORMAP
	uniform mat3 specularColorMapTransform;
	varying vec2 vSpecularColorMapUv;
#endif
#ifdef USE_SPECULAR_INTENSITYMAP
	uniform mat3 specularIntensityMapTransform;
	varying vec2 vSpecularIntensityMapUv;
#endif
#ifdef USE_TRANSMISSIONMAP
	uniform mat3 transmissionMapTransform;
	varying vec2 vTransmissionMapUv;
#endif
#ifdef USE_THICKNESSMAP
	uniform mat3 thicknessMapTransform;
	varying vec2 vThicknessMapUv;
#endif`,kb=`#if defined( USE_UV ) || defined( USE_ANISOTROPY )
	vUv = vec3( uv, 1 ).xy;
#endif
#ifdef USE_MAP
	vMapUv = ( mapTransform * vec3( MAP_UV, 1 ) ).xy;
#endif
#ifdef USE_ALPHAMAP
	vAlphaMapUv = ( alphaMapTransform * vec3( ALPHAMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_LIGHTMAP
	vLightMapUv = ( lightMapTransform * vec3( LIGHTMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_AOMAP
	vAoMapUv = ( aoMapTransform * vec3( AOMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_BUMPMAP
	vBumpMapUv = ( bumpMapTransform * vec3( BUMPMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_NORMALMAP
	vNormalMapUv = ( normalMapTransform * vec3( NORMALMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_DISPLACEMENTMAP
	vDisplacementMapUv = ( displacementMapTransform * vec3( DISPLACEMENTMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_EMISSIVEMAP
	vEmissiveMapUv = ( emissiveMapTransform * vec3( EMISSIVEMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_METALNESSMAP
	vMetalnessMapUv = ( metalnessMapTransform * vec3( METALNESSMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_ROUGHNESSMAP
	vRoughnessMapUv = ( roughnessMapTransform * vec3( ROUGHNESSMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_ANISOTROPYMAP
	vAnisotropyMapUv = ( anisotropyMapTransform * vec3( ANISOTROPYMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_CLEARCOATMAP
	vClearcoatMapUv = ( clearcoatMapTransform * vec3( CLEARCOATMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_CLEARCOAT_NORMALMAP
	vClearcoatNormalMapUv = ( clearcoatNormalMapTransform * vec3( CLEARCOAT_NORMALMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_CLEARCOAT_ROUGHNESSMAP
	vClearcoatRoughnessMapUv = ( clearcoatRoughnessMapTransform * vec3( CLEARCOAT_ROUGHNESSMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_IRIDESCENCEMAP
	vIridescenceMapUv = ( iridescenceMapTransform * vec3( IRIDESCENCEMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_IRIDESCENCE_THICKNESSMAP
	vIridescenceThicknessMapUv = ( iridescenceThicknessMapTransform * vec3( IRIDESCENCE_THICKNESSMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_SHEEN_COLORMAP
	vSheenColorMapUv = ( sheenColorMapTransform * vec3( SHEEN_COLORMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_SHEEN_ROUGHNESSMAP
	vSheenRoughnessMapUv = ( sheenRoughnessMapTransform * vec3( SHEEN_ROUGHNESSMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_SPECULARMAP
	vSpecularMapUv = ( specularMapTransform * vec3( SPECULARMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_SPECULAR_COLORMAP
	vSpecularColorMapUv = ( specularColorMapTransform * vec3( SPECULAR_COLORMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_SPECULAR_INTENSITYMAP
	vSpecularIntensityMapUv = ( specularIntensityMapTransform * vec3( SPECULAR_INTENSITYMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_TRANSMISSIONMAP
	vTransmissionMapUv = ( transmissionMapTransform * vec3( TRANSMISSIONMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_THICKNESSMAP
	vThicknessMapUv = ( thicknessMapTransform * vec3( THICKNESSMAP_UV, 1 ) ).xy;
#endif`,zb=`#if defined( USE_ENVMAP ) || defined( DISTANCE ) || defined ( USE_SHADOWMAP ) || defined ( USE_TRANSMISSION ) || NUM_SPOT_LIGHT_COORDS > 0
	vec4 worldPosition = vec4( transformed, 1.0 );
	#ifdef USE_BATCHING
		worldPosition = batchingMatrix * worldPosition;
	#endif
	#ifdef USE_INSTANCING
		worldPosition = instanceMatrix * worldPosition;
	#endif
	worldPosition = modelMatrix * worldPosition;
#endif`,Vb=`varying vec2 vUv;
uniform mat3 uvTransform;
void main() {
	vUv = ( uvTransform * vec3( uv, 1 ) ).xy;
	gl_Position = vec4( position.xy, 1.0, 1.0 );
}`,Gb=`uniform sampler2D t2D;
uniform float backgroundIntensity;
varying vec2 vUv;
void main() {
	vec4 texColor = texture2D( t2D, vUv );
	#ifdef DECODE_VIDEO_TEXTURE
		texColor = vec4( mix( pow( texColor.rgb * 0.9478672986 + vec3( 0.0521327014 ), vec3( 2.4 ) ), texColor.rgb * 0.0773993808, vec3( lessThanEqual( texColor.rgb, vec3( 0.04045 ) ) ) ), texColor.w );
	#endif
	texColor.rgb *= backgroundIntensity;
	gl_FragColor = texColor;
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
}`,Hb=`varying vec3 vWorldDirection;
#include <common>
void main() {
	vWorldDirection = transformDirection( position, modelMatrix );
	#include <begin_vertex>
	#include <project_vertex>
	gl_Position.z = gl_Position.w;
}`,Wb=`#ifdef ENVMAP_TYPE_CUBE
	uniform samplerCube envMap;
#elif defined( ENVMAP_TYPE_CUBE_UV )
	uniform sampler2D envMap;
#endif
uniform float backgroundBlurriness;
uniform float backgroundIntensity;
uniform mat3 backgroundRotation;
varying vec3 vWorldDirection;
#include <cube_uv_reflection_fragment>
void main() {
	#ifdef ENVMAP_TYPE_CUBE
		vec4 texColor = textureCube( envMap, backgroundRotation * vWorldDirection );
	#elif defined( ENVMAP_TYPE_CUBE_UV )
		vec4 texColor = textureCubeUV( envMap, backgroundRotation * vWorldDirection, backgroundBlurriness );
	#else
		vec4 texColor = vec4( 0.0, 0.0, 0.0, 1.0 );
	#endif
	texColor.rgb *= backgroundIntensity;
	gl_FragColor = texColor;
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
}`,Xb=`varying vec3 vWorldDirection;
#include <common>
void main() {
	vWorldDirection = transformDirection( position, modelMatrix );
	#include <begin_vertex>
	#include <project_vertex>
	gl_Position.z = gl_Position.w;
}`,qb=`uniform samplerCube tCube;
uniform float tFlip;
uniform float opacity;
varying vec3 vWorldDirection;
void main() {
	vec4 texColor = textureCube( tCube, vec3( tFlip * vWorldDirection.x, vWorldDirection.yz ) );
	gl_FragColor = texColor;
	gl_FragColor.a *= opacity;
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
}`,jb=`#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
varying vec2 vHighPrecisionZW;
void main() {
	#include <uv_vertex>
	#include <batching_vertex>
	#include <skinbase_vertex>
	#include <morphinstance_vertex>
	#ifdef USE_DISPLACEMENTMAP
		#include <beginnormal_vertex>
		#include <morphnormal_vertex>
		#include <skinnormal_vertex>
	#endif
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	vHighPrecisionZW = gl_Position.zw;
}`,Yb=`#if DEPTH_PACKING == 3200
	uniform float opacity;
#endif
#include <common>
#include <packing>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
varying vec2 vHighPrecisionZW;
void main() {
	vec4 diffuseColor = vec4( 1.0 );
	#include <clipping_planes_fragment>
	#if DEPTH_PACKING == 3200
		diffuseColor.a = opacity;
	#endif
	#include <map_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <logdepthbuf_fragment>
	#ifdef USE_REVERSED_DEPTH_BUFFER
		float fragCoordZ = vHighPrecisionZW[ 0 ] / vHighPrecisionZW[ 1 ];
	#else
		float fragCoordZ = 0.5 * vHighPrecisionZW[ 0 ] / vHighPrecisionZW[ 1 ] + 0.5;
	#endif
	#if DEPTH_PACKING == 3200
		gl_FragColor = vec4( vec3( 1.0 - fragCoordZ ), opacity );
	#elif DEPTH_PACKING == 3201
		gl_FragColor = packDepthToRGBA( fragCoordZ );
	#elif DEPTH_PACKING == 3202
		gl_FragColor = vec4( packDepthToRGB( fragCoordZ ), 1.0 );
	#elif DEPTH_PACKING == 3203
		gl_FragColor = vec4( packDepthToRG( fragCoordZ ), 0.0, 1.0 );
	#endif
}`,$b=`#define DISTANCE
varying vec3 vWorldPosition;
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <batching_vertex>
	#include <skinbase_vertex>
	#include <morphinstance_vertex>
	#ifdef USE_DISPLACEMENTMAP
		#include <beginnormal_vertex>
		#include <morphnormal_vertex>
		#include <skinnormal_vertex>
	#endif
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <worldpos_vertex>
	#include <clipping_planes_vertex>
	vWorldPosition = worldPosition.xyz;
}`,Zb=`#define DISTANCE
uniform vec3 referencePosition;
uniform float nearDistance;
uniform float farDistance;
varying vec3 vWorldPosition;
#include <common>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( 1.0 );
	#include <clipping_planes_fragment>
	#include <map_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	float dist = length( vWorldPosition - referencePosition );
	dist = ( dist - nearDistance ) / ( farDistance - nearDistance );
	dist = saturate( dist );
	gl_FragColor = vec4( dist, 0.0, 0.0, 1.0 );
}`,Kb=`varying vec3 vWorldDirection;
#include <common>
void main() {
	vWorldDirection = transformDirection( position, modelMatrix );
	#include <begin_vertex>
	#include <project_vertex>
}`,Jb=`uniform sampler2D tEquirect;
varying vec3 vWorldDirection;
#include <common>
void main() {
	vec3 direction = normalize( vWorldDirection );
	vec2 sampleUV = equirectUv( direction );
	gl_FragColor = texture2D( tEquirect, sampleUV );
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
}`,Qb=`uniform float scale;
attribute float lineDistance;
varying float vLineDistance;
#include <common>
#include <uv_pars_vertex>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <morphtarget_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	vLineDistance = scale * lineDistance;
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	#include <fog_vertex>
}`,eS=`uniform vec3 diffuse;
uniform float opacity;
uniform float dashSize;
uniform float totalSize;
varying float vLineDistance;
#include <common>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <fog_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	if ( mod( vLineDistance, totalSize ) > dashSize ) {
		discard;
	}
	vec3 outgoingLight = vec3( 0.0 );
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	outgoingLight = diffuseColor.rgb;
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
}`,tS=`#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <envmap_pars_vertex>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <batching_vertex>
	#if defined ( USE_ENVMAP ) || defined ( USE_SKINNING )
		#include <beginnormal_vertex>
		#include <morphnormal_vertex>
		#include <skinbase_vertex>
		#include <skinnormal_vertex>
		#include <defaultnormal_vertex>
	#endif
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	#include <worldpos_vertex>
	#include <envmap_vertex>
	#include <fog_vertex>
}`,iS=`uniform vec3 diffuse;
uniform float opacity;
#ifndef FLAT_SHADED
	varying vec3 vNormal;
#endif
#include <common>
#include <dithering_pars_fragment>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <aomap_pars_fragment>
#include <lightmap_pars_fragment>
#include <envmap_common_pars_fragment>
#include <envmap_pars_fragment>
#include <fog_pars_fragment>
#include <specularmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <specularmap_fragment>
	ReflectedLight reflectedLight = ReflectedLight( vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ) );
	#ifdef USE_LIGHTMAP
		vec4 lightMapTexel = texture2D( lightMap, vLightMapUv );
		reflectedLight.indirectDiffuse += lightMapTexel.rgb * lightMapIntensity * RECIPROCAL_PI;
	#else
		reflectedLight.indirectDiffuse += vec3( 1.0 );
	#endif
	#include <aomap_fragment>
	reflectedLight.indirectDiffuse *= diffuseColor.rgb;
	vec3 outgoingLight = reflectedLight.indirectDiffuse;
	#include <envmap_fragment>
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
	#include <dithering_fragment>
}`,nS=`#define LAMBERT
varying vec3 vViewPosition;
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <envmap_pars_vertex>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <normal_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <shadowmap_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <normal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	vViewPosition = - mvPosition.xyz;
	#include <worldpos_vertex>
	#include <envmap_vertex>
	#include <shadowmap_vertex>
	#include <fog_vertex>
}`,rS=`#define LAMBERT
uniform vec3 diffuse;
uniform vec3 emissive;
uniform float opacity;
#include <common>
#include <dithering_pars_fragment>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <aomap_pars_fragment>
#include <lightmap_pars_fragment>
#include <emissivemap_pars_fragment>
#include <cube_uv_reflection_fragment>
#include <envmap_common_pars_fragment>
#include <envmap_pars_fragment>
#include <envmap_physical_pars_fragment>
#include <fog_pars_fragment>
#include <bsdfs>
#include <lights_pars_begin>
#include <normal_pars_fragment>
#include <lights_lambert_pars_fragment>
#include <shadowmap_pars_fragment>
#include <bumpmap_pars_fragment>
#include <normalmap_pars_fragment>
#include <specularmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	ReflectedLight reflectedLight = ReflectedLight( vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ) );
	vec3 totalEmissiveRadiance = emissive;
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <specularmap_fragment>
	#include <normal_fragment_begin>
	#include <normal_fragment_maps>
	#include <emissivemap_fragment>
	#include <lights_lambert_fragment>
	#include <lights_fragment_begin>
	#include <lights_fragment_maps>
	#include <lights_fragment_end>
	#include <aomap_fragment>
	vec3 outgoingLight = reflectedLight.directDiffuse + reflectedLight.indirectDiffuse + totalEmissiveRadiance;
	#include <envmap_fragment>
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
	#include <dithering_fragment>
}`,sS=`#define MATCAP
varying vec3 vViewPosition;
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <color_pars_vertex>
#include <displacementmap_pars_vertex>
#include <fog_pars_vertex>
#include <normal_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <normal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	#include <fog_vertex>
	vViewPosition = - mvPosition.xyz;
}`,aS=`#define MATCAP
uniform vec3 diffuse;
uniform float opacity;
uniform sampler2D matcap;
varying vec3 vViewPosition;
#include <common>
#include <dithering_pars_fragment>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <fog_pars_fragment>
#include <normal_pars_fragment>
#include <bumpmap_pars_fragment>
#include <normalmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <normal_fragment_begin>
	#include <normal_fragment_maps>
	vec3 viewDir = normalize( vViewPosition );
	vec3 x = normalize( vec3( viewDir.z, 0.0, - viewDir.x ) );
	vec3 y = cross( viewDir, x );
	vec2 uv = vec2( dot( x, normal ), dot( y, normal ) ) * 0.495 + 0.5;
	#ifdef USE_MATCAP
		vec4 matcapColor = texture2D( matcap, uv );
	#else
		vec4 matcapColor = vec4( vec3( mix( 0.2, 0.8, uv.y ) ), 1.0 );
	#endif
	vec3 outgoingLight = diffuseColor.rgb * matcapColor.rgb;
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
	#include <dithering_fragment>
}`,oS=`#define NORMAL
#if defined( FLAT_SHADED ) || defined( USE_BUMPMAP ) || defined( USE_NORMALMAP_TANGENTSPACE )
	varying vec3 vViewPosition;
#endif
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <normal_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphinstance_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <normal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
#if defined( FLAT_SHADED ) || defined( USE_BUMPMAP ) || defined( USE_NORMALMAP_TANGENTSPACE )
	vViewPosition = - mvPosition.xyz;
#endif
}`,lS=`#define NORMAL
uniform float opacity;
#if defined( FLAT_SHADED ) || defined( USE_BUMPMAP ) || defined( USE_NORMALMAP_TANGENTSPACE )
	varying vec3 vViewPosition;
#endif
#include <uv_pars_fragment>
#include <normal_pars_fragment>
#include <bumpmap_pars_fragment>
#include <normalmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( 0.0, 0.0, 0.0, opacity );
	#include <clipping_planes_fragment>
	#include <logdepthbuf_fragment>
	#include <normal_fragment_begin>
	#include <normal_fragment_maps>
	gl_FragColor = vec4( normalize( normal ) * 0.5 + 0.5, diffuseColor.a );
	#ifdef OPAQUE
		gl_FragColor.a = 1.0;
	#endif
}`,cS=`#define PHONG
varying vec3 vViewPosition;
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <envmap_pars_vertex>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <normal_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <shadowmap_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphcolor_vertex>
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphinstance_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <normal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	vViewPosition = - mvPosition.xyz;
	#include <worldpos_vertex>
	#include <envmap_vertex>
	#include <shadowmap_vertex>
	#include <fog_vertex>
}`,hS=`#define PHONG
uniform vec3 diffuse;
uniform vec3 emissive;
uniform vec3 specular;
uniform float shininess;
uniform float opacity;
#include <common>
#include <dithering_pars_fragment>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <aomap_pars_fragment>
#include <lightmap_pars_fragment>
#include <emissivemap_pars_fragment>
#include <cube_uv_reflection_fragment>
#include <envmap_common_pars_fragment>
#include <envmap_pars_fragment>
#include <envmap_physical_pars_fragment>
#include <fog_pars_fragment>
#include <bsdfs>
#include <lights_pars_begin>
#include <normal_pars_fragment>
#include <lights_phong_pars_fragment>
#include <shadowmap_pars_fragment>
#include <bumpmap_pars_fragment>
#include <normalmap_pars_fragment>
#include <specularmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	ReflectedLight reflectedLight = ReflectedLight( vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ) );
	vec3 totalEmissiveRadiance = emissive;
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <specularmap_fragment>
	#include <normal_fragment_begin>
	#include <normal_fragment_maps>
	#include <emissivemap_fragment>
	#include <lights_phong_fragment>
	#include <lights_fragment_begin>
	#include <lights_fragment_maps>
	#include <lights_fragment_end>
	#include <aomap_fragment>
	vec3 outgoingLight = reflectedLight.directDiffuse + reflectedLight.indirectDiffuse + reflectedLight.directSpecular + reflectedLight.indirectSpecular + totalEmissiveRadiance;
	#include <envmap_fragment>
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
	#include <dithering_fragment>
}`,uS=`#define STANDARD
varying vec3 vViewPosition;
#ifdef USE_TRANSMISSION
	varying vec3 vWorldPosition;
#endif
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <normal_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <shadowmap_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <normal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	vViewPosition = - mvPosition.xyz;
	#include <worldpos_vertex>
	#include <shadowmap_vertex>
	#include <fog_vertex>
#ifdef USE_TRANSMISSION
	vWorldPosition = worldPosition.xyz;
#endif
}`,dS=`#define STANDARD
#ifdef PHYSICAL
	#define IOR
	#define USE_SPECULAR
#endif
uniform vec3 diffuse;
uniform vec3 emissive;
uniform float roughness;
uniform float metalness;
uniform float opacity;
#ifdef IOR
	uniform float ior;
#endif
#ifdef USE_SPECULAR
	uniform float specularIntensity;
	uniform vec3 specularColor;
	#ifdef USE_SPECULAR_COLORMAP
		uniform sampler2D specularColorMap;
	#endif
	#ifdef USE_SPECULAR_INTENSITYMAP
		uniform sampler2D specularIntensityMap;
	#endif
#endif
#ifdef USE_CLEARCOAT
	uniform float clearcoat;
	uniform float clearcoatRoughness;
#endif
#ifdef USE_DISPERSION
	uniform float dispersion;
#endif
#ifdef USE_RETROREFLECTION
	uniform float retroreflectivity;
#endif
#ifdef USE_IRIDESCENCE
	uniform float iridescence;
	uniform float iridescenceIOR;
	uniform float iridescenceThicknessMinimum;
	uniform float iridescenceThicknessMaximum;
#endif
#ifdef USE_SHEEN
	uniform vec3 sheenColor;
	uniform float sheenRoughness;
	#ifdef USE_SHEEN_COLORMAP
		uniform sampler2D sheenColorMap;
	#endif
	#ifdef USE_SHEEN_ROUGHNESSMAP
		uniform sampler2D sheenRoughnessMap;
	#endif
#endif
#ifdef USE_ANISOTROPY
	uniform vec2 anisotropyVector;
	#ifdef USE_ANISOTROPYMAP
		uniform sampler2D anisotropyMap;
	#endif
#endif
varying vec3 vViewPosition;
#include <common>
#include <dithering_pars_fragment>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <aomap_pars_fragment>
#include <lightmap_pars_fragment>
#include <emissivemap_pars_fragment>
#include <iridescence_fragment>
#include <cube_uv_reflection_fragment>
#include <envmap_common_pars_fragment>
#include <envmap_physical_pars_fragment>
#include <fog_pars_fragment>
#include <lights_pars_begin>
#include <normal_pars_fragment>
#include <lights_physical_pars_fragment>
#include <transmission_pars_fragment>
#include <shadowmap_pars_fragment>
#include <bumpmap_pars_fragment>
#include <normalmap_pars_fragment>
#include <clearcoat_pars_fragment>
#include <iridescence_pars_fragment>
#include <roughnessmap_pars_fragment>
#include <metalnessmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	ReflectedLight reflectedLight = ReflectedLight( vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ) );
	vec3 totalEmissiveRadiance = emissive;
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <roughnessmap_fragment>
	#include <metalnessmap_fragment>
	#include <normal_fragment_begin>
	#include <normal_fragment_maps>
	#include <clearcoat_normal_fragment_begin>
	#include <clearcoat_normal_fragment_maps>
	#include <emissivemap_fragment>
	#include <lights_physical_fragment>
	#include <lights_fragment_begin>
	#include <lights_fragment_maps>
	#include <lights_fragment_end>
	#include <aomap_fragment>
	vec3 totalDiffuse = reflectedLight.directDiffuse + reflectedLight.indirectDiffuse;
	vec3 totalSpecular = reflectedLight.directSpecular + reflectedLight.indirectSpecular;
	#include <transmission_fragment>
	vec3 outgoingLight = totalDiffuse + totalSpecular + totalEmissiveRadiance;
	#ifdef USE_SHEEN
 
		outgoingLight = outgoingLight + sheenSpecularDirect + sheenSpecularIndirect;
 
 	#endif
	#ifdef USE_CLEARCOAT
		float dotNVcc = saturate( dot( geometryClearcoatNormal, geometryViewDir ) );
		vec3 Fcc = F_Schlick( material.clearcoatF0, material.clearcoatF90, dotNVcc );
		outgoingLight = outgoingLight * ( 1.0 - material.clearcoat * Fcc ) + ( clearcoatSpecularDirect + clearcoatSpecularIndirect ) * material.clearcoat;
	#endif
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
	#include <dithering_fragment>
}`,fS=`#define TOON
varying vec3 vViewPosition;
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <normal_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <shadowmap_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <normal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	vViewPosition = - mvPosition.xyz;
	#include <worldpos_vertex>
	#include <shadowmap_vertex>
	#include <fog_vertex>
}`,pS=`#define TOON
uniform vec3 diffuse;
uniform vec3 emissive;
uniform float opacity;
#include <common>
#include <dithering_pars_fragment>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <aomap_pars_fragment>
#include <lightmap_pars_fragment>
#include <emissivemap_pars_fragment>
#include <gradientmap_pars_fragment>
#include <fog_pars_fragment>
#include <bsdfs>
#include <lights_pars_begin>
#include <normal_pars_fragment>
#include <lights_toon_pars_fragment>
#include <shadowmap_pars_fragment>
#include <bumpmap_pars_fragment>
#include <normalmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	ReflectedLight reflectedLight = ReflectedLight( vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ) );
	vec3 totalEmissiveRadiance = emissive;
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <normal_fragment_begin>
	#include <normal_fragment_maps>
	#include <emissivemap_fragment>
	#include <lights_toon_fragment>
	#include <lights_fragment_begin>
	#include <lights_fragment_maps>
	#include <lights_fragment_end>
	#include <aomap_fragment>
	vec3 outgoingLight = reflectedLight.directDiffuse + reflectedLight.indirectDiffuse + totalEmissiveRadiance;
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
	#include <dithering_fragment>
}`,mS=`uniform float size;
uniform float scale;
#include <common>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <morphtarget_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
#ifdef USE_POINTS_UV
	varying vec2 vUv;
	uniform mat3 uvTransform;
#endif
void main() {
	#ifdef USE_POINTS_UV
		vUv = ( uvTransform * vec3( uv, 1 ) ).xy;
	#endif
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <project_vertex>
	gl_PointSize = size;
	#ifdef USE_SIZEATTENUATION
		bool isPerspective = isPerspectiveMatrix( projectionMatrix );
		if ( isPerspective ) gl_PointSize *= ( scale / - mvPosition.z );
	#endif
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	#include <worldpos_vertex>
	#include <fog_vertex>
}`,gS=`uniform vec3 diffuse;
uniform float opacity;
#include <common>
#include <color_pars_fragment>
#include <map_particle_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <fog_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	vec3 outgoingLight = vec3( 0.0 );
	#include <logdepthbuf_fragment>
	#include <map_particle_fragment>
	#include <color_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	outgoingLight = diffuseColor.rgb;
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
}`,yS=`#include <common>
#include <batching_pars_vertex>
#include <fog_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <shadowmap_pars_vertex>
void main() {
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphinstance_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <worldpos_vertex>
	#include <shadowmap_vertex>
	#include <fog_vertex>
}`,_S=`uniform vec3 color;
uniform float opacity;
#include <common>
#include <fog_pars_fragment>
#include <bsdfs>
#include <lights_pars_begin>
#include <logdepthbuf_pars_fragment>
#include <shadowmap_pars_fragment>
#include <shadowmask_pars_fragment>
void main() {
	#include <logdepthbuf_fragment>
	gl_FragColor = vec4( color, opacity * ( 1.0 - getShadowMask() ) );
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
}`,xS=`uniform float rotation;
uniform vec2 center;
#include <common>
#include <uv_pars_vertex>
#include <fog_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	vec4 mvPosition = modelViewMatrix[ 3 ];
	vec2 scale = vec2( length( modelMatrix[ 0 ].xyz ), length( modelMatrix[ 1 ].xyz ) );
	#ifndef USE_SIZEATTENUATION
		bool isPerspective = isPerspectiveMatrix( projectionMatrix );
		if ( isPerspective ) scale *= - mvPosition.z;
	#endif
	vec2 alignedPosition = ( position.xy - ( center - vec2( 0.5 ) ) ) * scale;
	vec2 rotatedPosition;
	rotatedPosition.x = cos( rotation ) * alignedPosition.x - sin( rotation ) * alignedPosition.y;
	rotatedPosition.y = sin( rotation ) * alignedPosition.x + cos( rotation ) * alignedPosition.y;
	mvPosition.xy += rotatedPosition;
	gl_Position = projectionMatrix * mvPosition;
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	#include <fog_vertex>
}`,vS=`uniform vec3 diffuse;
uniform float opacity;
#include <common>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <fog_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	vec3 outgoingLight = vec3( 0.0 );
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	outgoingLight = diffuseColor.rgb;
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
}`,qe={alphahash_fragment:Vx,alphahash_pars_fragment:Gx,alphamap_fragment:Hx,alphamap_pars_fragment:Wx,alphatest_fragment:Xx,alphatest_pars_fragment:qx,aomap_fragment:jx,aomap_pars_fragment:Yx,batching_pars_vertex:$x,batching_vertex:Zx,begin_vertex:Kx,beginnormal_vertex:Jx,bsdfs:Qx,iridescence_fragment:ev,bumpmap_pars_fragment:tv,clipping_planes_fragment:iv,clipping_planes_pars_fragment:nv,clipping_planes_pars_vertex:rv,clipping_planes_vertex:sv,color_fragment:av,color_pars_fragment:ov,color_pars_vertex:lv,color_vertex:cv,common:hv,cube_uv_reflection_fragment:uv,defaultnormal_vertex:dv,displacementmap_pars_vertex:fv,displacementmap_vertex:pv,emissivemap_fragment:mv,emissivemap_pars_fragment:gv,colorspace_fragment:yv,colorspace_pars_fragment:_v,envmap_fragment:xv,envmap_common_pars_fragment:vv,envmap_pars_fragment:bv,envmap_pars_vertex:Sv,envmap_physical_pars_fragment:Dv,envmap_vertex:Mv,fog_vertex:wv,fog_pars_vertex:Tv,fog_fragment:Ev,fog_pars_fragment:Av,gradientmap_pars_fragment:Cv,lightmap_pars_fragment:Rv,lights_lambert_fragment:Pv,lights_lambert_pars_fragment:Iv,lights_pars_begin:Lv,lights_toon_fragment:Nv,lights_toon_pars_fragment:Uv,lights_phong_fragment:Ov,lights_phong_pars_fragment:Fv,lights_physical_fragment:Bv,lights_physical_pars_fragment:kv,lights_fragment_begin:zv,lights_fragment_maps:Vv,lights_fragment_end:Gv,lightprobes_pars_fragment:Hv,logdepthbuf_fragment:Wv,logdepthbuf_pars_fragment:Xv,logdepthbuf_pars_vertex:qv,logdepthbuf_vertex:jv,map_fragment:Yv,map_pars_fragment:$v,map_particle_fragment:Zv,map_particle_pars_fragment:Kv,metalnessmap_fragment:Jv,metalnessmap_pars_fragment:Qv,morphinstance_vertex:eb,morphcolor_vertex:tb,morphnormal_vertex:ib,morphtarget_pars_vertex:nb,morphtarget_vertex:rb,normal_fragment_begin:sb,normal_fragment_maps:ab,normal_pars_fragment:ob,normal_pars_vertex:lb,normal_vertex:cb,normalmap_pars_fragment:hb,clearcoat_normal_fragment_begin:ub,clearcoat_normal_fragment_maps:db,clearcoat_pars_fragment:fb,iridescence_pars_fragment:pb,opaque_fragment:mb,packing:gb,premultiplied_alpha_fragment:yb,project_vertex:_b,dithering_fragment:xb,dithering_pars_fragment:vb,roughnessmap_fragment:bb,roughnessmap_pars_fragment:Sb,shadowmap_pars_fragment:Mb,shadowmap_pars_vertex:wb,shadowmap_vertex:Tb,shadowmask_pars_fragment:Eb,skinbase_vertex:Ab,skinning_pars_vertex:Cb,skinning_vertex:Rb,skinnormal_vertex:Pb,specularmap_fragment:Ib,specularmap_pars_fragment:Lb,tonemapping_fragment:Db,tonemapping_pars_fragment:Nb,transmission_fragment:Ub,transmission_pars_fragment:Ob,uv_pars_fragment:Fb,uv_pars_vertex:Bb,uv_vertex:kb,worldpos_vertex:zb,background_vert:Vb,background_frag:Gb,backgroundCube_vert:Hb,backgroundCube_frag:Wb,cube_vert:Xb,cube_frag:qb,depth_vert:jb,depth_frag:Yb,distance_vert:$b,distance_frag:Zb,equirect_vert:Kb,equirect_frag:Jb,linedashed_vert:Qb,linedashed_frag:eS,meshbasic_vert:tS,meshbasic_frag:iS,meshlambert_vert:nS,meshlambert_frag:rS,meshmatcap_vert:sS,meshmatcap_frag:aS,meshnormal_vert:oS,meshnormal_frag:lS,meshphong_vert:cS,meshphong_frag:hS,meshphysical_vert:uS,meshphysical_frag:dS,meshtoon_vert:fS,meshtoon_frag:pS,points_vert:mS,points_frag:gS,shadow_vert:yS,shadow_frag:_S,sprite_vert:xS,sprite_frag:vS},ae={common:{diffuse:{value:new Ie(16777215)},opacity:{value:1},map:{value:null},mapTransform:{value:new Oe},alphaMap:{value:null},alphaMapTransform:{value:new Oe},alphaTest:{value:0}},specularmap:{specularMap:{value:null},specularMapTransform:{value:new Oe}},envmap:{envMap:{value:null},envMapRotation:{value:new Oe},reflectivity:{value:1},ior:{value:1.5},refractionRatio:{value:.98},dfgLUT:{value:null}},aomap:{aoMap:{value:null},aoMapIntensity:{value:1},aoMapTransform:{value:new Oe}},lightmap:{lightMap:{value:null},lightMapIntensity:{value:1},lightMapTransform:{value:new Oe}},bumpmap:{bumpMap:{value:null},bumpMapTransform:{value:new Oe},bumpScale:{value:1}},normalmap:{normalMap:{value:null},normalMapTransform:{value:new Oe},normalScale:{value:new Se(1,1)}},displacementmap:{displacementMap:{value:null},displacementMapTransform:{value:new Oe},displacementScale:{value:1},displacementBias:{value:0}},emissivemap:{emissiveMap:{value:null},emissiveMapTransform:{value:new Oe}},metalnessmap:{metalnessMap:{value:null},metalnessMapTransform:{value:new Oe}},roughnessmap:{roughnessMap:{value:null},roughnessMapTransform:{value:new Oe}},gradientmap:{gradientMap:{value:null}},fog:{fogDensity:{value:25e-5},fogNear:{value:1},fogFar:{value:2e3},fogColor:{value:new Ie(16777215)}},lights:{ambientLightColor:{value:[]},lightProbe:{value:[]},sunLights:{value:[],properties:{direction:{},color:{}}},sunLightShadows:{value:[],properties:{shadowIntensity:1,shadowBias:{},shadowNormalBias:{},shadowRadius:{},shadowMapSize:{}}},sunShadowMatrix:{value:[]},sunShadowCascade:{value:[]},directionalLights:{value:[],properties:{direction:{},color:{}}},directionalLightShadows:{value:[],properties:{shadowIntensity:1,shadowBias:{},shadowNormalBias:{},shadowRadius:{},shadowMapSize:{}}},directionalShadowMatrix:{value:[]},spotLights:{value:[],properties:{color:{},position:{},direction:{},distance:{},coneCos:{},penumbraCos:{},decay:{}}},spotLightShadows:{value:[],properties:{shadowIntensity:1,shadowBias:{},shadowNormalBias:{},shadowRadius:{},shadowMapSize:{}}},spotLightMap:{value:[]},spotLightMatrix:{value:[]},pointLights:{value:[],properties:{color:{},position:{},decay:{},distance:{}}},pointLightShadows:{value:[],properties:{shadowIntensity:1,shadowBias:{},shadowNormalBias:{},shadowRadius:{},shadowMapSize:{},shadowCameraNear:{},shadowCameraFar:{}}},pointShadowMatrix:{value:[]},hemisphereLights:{value:[],properties:{direction:{},skyColor:{},groundColor:{}}},rectAreaLights:{value:[],properties:{color:{},position:{},width:{},height:{}}},ltc_1:{value:null},ltc_2:{value:null},probesSH:{value:null},probesMin:{value:new P},probesMax:{value:new P},probesResolution:{value:new P}},points:{diffuse:{value:new Ie(16777215)},opacity:{value:1},size:{value:1},scale:{value:1},map:{value:null},alphaMap:{value:null},alphaMapTransform:{value:new Oe},alphaTest:{value:0},uvTransform:{value:new Oe}},sprite:{diffuse:{value:new Ie(16777215)},opacity:{value:1},center:{value:new Se(.5,.5)},rotation:{value:0},map:{value:null},mapTransform:{value:new Oe},alphaMap:{value:null},alphaMapTransform:{value:new Oe},alphaTest:{value:0}}},pi={basic:{uniforms:si([ae.common,ae.specularmap,ae.envmap,ae.aomap,ae.lightmap,ae.fog]),vertexShader:qe.meshbasic_vert,fragmentShader:qe.meshbasic_frag},lambert:{uniforms:si([ae.common,ae.specularmap,ae.envmap,ae.aomap,ae.lightmap,ae.emissivemap,ae.bumpmap,ae.normalmap,ae.displacementmap,ae.fog,ae.lights,{emissive:{value:new Ie(0)},envMapIntensity:{value:1}}]),vertexShader:qe.meshlambert_vert,fragmentShader:qe.meshlambert_frag},phong:{uniforms:si([ae.common,ae.specularmap,ae.envmap,ae.aomap,ae.lightmap,ae.emissivemap,ae.bumpmap,ae.normalmap,ae.displacementmap,ae.fog,ae.lights,{emissive:{value:new Ie(0)},specular:{value:new Ie(1118481)},shininess:{value:30},envMapIntensity:{value:1}}]),vertexShader:qe.meshphong_vert,fragmentShader:qe.meshphong_frag},standard:{uniforms:si([ae.common,ae.envmap,ae.aomap,ae.lightmap,ae.emissivemap,ae.bumpmap,ae.normalmap,ae.displacementmap,ae.roughnessmap,ae.metalnessmap,ae.fog,ae.lights,{emissive:{value:new Ie(0)},roughness:{value:1},metalness:{value:0},envMapIntensity:{value:1}}]),vertexShader:qe.meshphysical_vert,fragmentShader:qe.meshphysical_frag},toon:{uniforms:si([ae.common,ae.aomap,ae.lightmap,ae.emissivemap,ae.bumpmap,ae.normalmap,ae.displacementmap,ae.gradientmap,ae.fog,ae.lights,{emissive:{value:new Ie(0)}}]),vertexShader:qe.meshtoon_vert,fragmentShader:qe.meshtoon_frag},matcap:{uniforms:si([ae.common,ae.bumpmap,ae.normalmap,ae.displacementmap,ae.fog,{matcap:{value:null}}]),vertexShader:qe.meshmatcap_vert,fragmentShader:qe.meshmatcap_frag},points:{uniforms:si([ae.points,ae.fog]),vertexShader:qe.points_vert,fragmentShader:qe.points_frag},dashed:{uniforms:si([ae.common,ae.fog,{scale:{value:1},dashSize:{value:1},totalSize:{value:2}}]),vertexShader:qe.linedashed_vert,fragmentShader:qe.linedashed_frag},depth:{uniforms:si([ae.common,ae.displacementmap]),vertexShader:qe.depth_vert,fragmentShader:qe.depth_frag},normal:{uniforms:si([ae.common,ae.bumpmap,ae.normalmap,ae.displacementmap,{opacity:{value:1}}]),vertexShader:qe.meshnormal_vert,fragmentShader:qe.meshnormal_frag},sprite:{uniforms:si([ae.sprite,ae.fog]),vertexShader:qe.sprite_vert,fragmentShader:qe.sprite_frag},background:{uniforms:{uvTransform:{value:new Oe},t2D:{value:null},backgroundIntensity:{value:1}},vertexShader:qe.background_vert,fragmentShader:qe.background_frag},backgroundCube:{uniforms:{envMap:{value:null},backgroundBlurriness:{value:0},backgroundIntensity:{value:1},backgroundRotation:{value:new Oe}},vertexShader:qe.backgroundCube_vert,fragmentShader:qe.backgroundCube_frag},cube:{uniforms:{tCube:{value:null},tFlip:{value:-1},opacity:{value:1}},vertexShader:qe.cube_vert,fragmentShader:qe.cube_frag},equirect:{uniforms:{tEquirect:{value:null}},vertexShader:qe.equirect_vert,fragmentShader:qe.equirect_frag},distance:{uniforms:si([ae.common,ae.displacementmap,{referencePosition:{value:new P},nearDistance:{value:1},farDistance:{value:1e3}}]),vertexShader:qe.distance_vert,fragmentShader:qe.distance_frag},shadow:{uniforms:si([ae.lights,ae.fog,{color:{value:new Ie(0)},opacity:{value:1}}]),vertexShader:qe.shadow_vert,fragmentShader:qe.shadow_frag}};pi.physical={uniforms:si([pi.standard.uniforms,{clearcoat:{value:0},clearcoatMap:{value:null},clearcoatMapTransform:{value:new Oe},clearcoatNormalMap:{value:null},clearcoatNormalMapTransform:{value:new Oe},clearcoatNormalScale:{value:new Se(1,1)},clearcoatRoughness:{value:0},clearcoatRoughnessMap:{value:null},clearcoatRoughnessMapTransform:{value:new Oe},dispersion:{value:0},retroreflectivity:{value:0},iridescence:{value:0},iridescenceMap:{value:null},iridescenceMapTransform:{value:new Oe},iridescenceIOR:{value:1.3},iridescenceThicknessMinimum:{value:100},iridescenceThicknessMaximum:{value:400},iridescenceThicknessMap:{value:null},iridescenceThicknessMapTransform:{value:new Oe},sheen:{value:0},sheenColor:{value:new Ie(0)},sheenColorMap:{value:null},sheenColorMapTransform:{value:new Oe},sheenRoughness:{value:1},sheenRoughnessMap:{value:null},sheenRoughnessMapTransform:{value:new Oe},transmission:{value:0},transmissionMap:{value:null},transmissionMapTransform:{value:new Oe},transmissionSamplerSize:{value:new Se},transmissionSamplerMap:{value:null},thickness:{value:0},thicknessMap:{value:null},thicknessMapTransform:{value:new Oe},attenuationDistance:{value:0},attenuationColor:{value:new Ie(0)},specularColor:{value:new Ie(1,1,1)},specularColorMap:{value:null},specularColorMapTransform:{value:new Oe},specularIntensity:{value:1},specularIntensityMap:{value:null},specularIntensityMapTransform:{value:new Oe},anisotropyVector:{value:new Se},anisotropyMap:{value:null},anisotropyMapTransform:{value:new Oe}}]),vertexShader:qe.meshphysical_vert,fragmentShader:qe.meshphysical_frag};var Ec={r:0,b:0,g:0},bS=new ge,Mg=new Oe;Mg.set(-1,0,0,0,1,0,0,0,1);function SS(i,e,t,n,r,s){let a=new Ie(0),o=r===!0?0:1,l,c,h=null,u=0,d=null;function f(v){let S=v.isScene===!0?v.background:null;if(S&&S.isTexture){let _=v.backgroundBlurriness>0;S=e.get(S,_)}return S}function p(v){let S=!1,_=f(v);_===null?m(a,o):_&&_.isColor&&(m(_,1),S=!0);let M=i.xr.getEnvironmentBlendMode();M==="additive"?t.buffers.color.setClear(0,0,0,1,s):M==="alpha-blend"&&t.buffers.color.setClear(0,0,0,0,s),(i.autoClear||S)&&(t.buffers.depth.setTest(!0),t.buffers.depth.setMask(!0),t.buffers.color.setMask(!0),i.clear(i.autoClearColor,i.autoClearDepth,i.autoClearStencil))}function y(v,S){let _=f(S);_&&(_.isCubeTexture||_.mapping===za)?(c===void 0&&(c=new at(new Ir(1,1,1),new $t({name:"BackgroundCubeMaterial",uniforms:Vr(pi.backgroundCube.uniforms),vertexShader:pi.backgroundCube.vertexShader,fragmentShader:pi.backgroundCube.fragmentShader,side:ui,depthTest:!1,depthWrite:!1,fog:!1,allowOverride:!1})),c.geometry.deleteAttribute("normal"),c.geometry.deleteAttribute("uv"),c.onBeforeRender=function(M,w,E){this.matrixWorld.copyPosition(E.matrixWorld)},Object.defineProperty(c.material,"envMap",{get:function(){return this.uniforms.envMap.value}}),n.update(c)),c.material.uniforms.envMap.value=_,c.material.uniforms.backgroundBlurriness.value=S.backgroundBlurriness,c.material.uniforms.backgroundIntensity.value=S.backgroundIntensity,c.material.uniforms.backgroundRotation.value.setFromMatrix4(bS.makeRotationFromEuler(S.backgroundRotation)).transpose(),_.isCubeTexture&&_.isRenderTargetTexture===!1&&c.material.uniforms.backgroundRotation.value.premultiply(Mg),c.material.toneMapped=je.getTransfer(_.colorSpace)!==rt,(h!==_||u!==_.version||d!==i.toneMapping)&&(c.material.needsUpdate=!0,h=_,u=_.version,d=i.toneMapping),c.layers.enableAll(),v.unshift(c,c.geometry,c.material,0,0,null)):_&&_.isTexture&&(l===void 0&&(l=new at(new Dr(2,2),new $t({name:"BackgroundMaterial",uniforms:Vr(pi.background.uniforms),vertexShader:pi.background.vertexShader,fragmentShader:pi.background.fragmentShader,side:sn,depthTest:!1,depthWrite:!1,fog:!1,allowOverride:!1})),l.geometry.deleteAttribute("normal"),Object.defineProperty(l.material,"map",{get:function(){return this.uniforms.t2D.value}}),n.update(l)),l.material.uniforms.t2D.value=_,l.material.uniforms.backgroundIntensity.value=S.backgroundIntensity,l.material.toneMapped=je.getTransfer(_.colorSpace)!==rt,_.matrixAutoUpdate===!0&&_.updateMatrix(),l.material.uniforms.uvTransform.value.copy(_.matrix),(h!==_||u!==_.version||d!==i.toneMapping)&&(l.material.needsUpdate=!0,h=_,u=_.version,d=i.toneMapping),l.layers.enableAll(),v.unshift(l,l.geometry,l.material,0,0,null))}function m(v,S){v.getRGB(Ec,Ku(i)),t.buffers.color.setClear(Ec.r,Ec.g,Ec.b,S,s)}function g(){c!==void 0&&(c.geometry.dispose(),c.material.dispose(),c=void 0),l!==void 0&&(l.geometry.dispose(),l.material.dispose(),l=void 0)}return{getClearColor:function(){return a},setClearColor:function(v,S=1){a.set(v),o=S,m(a,o)},getClearAlpha:function(){return o},setClearAlpha:function(v){o=v,m(a,o)},render:p,addToRenderList:y,dispose:g}}function MS(i,e){let t=i.getParameter(i.MAX_VERTEX_ATTRIBS),n={},r=d(null),s=r,a=!1;function o(D,U,I,L,k){let H=!1,X=u(D,L,I,U);s!==X&&(s=X,c(s.object)),H=f(D,L,I,k),H&&p(D,L,I,k),k!==null&&e.update(k,i.ELEMENT_ARRAY_BUFFER),(H||a)&&(a=!1,_(D,U,I,L),k!==null&&i.bindBuffer(i.ELEMENT_ARRAY_BUFFER,e.get(k).buffer))}function l(){return i.createVertexArray()}function c(D){return i.bindVertexArray(D)}function h(D){return i.deleteVertexArray(D)}function u(D,U,I,L){let k=L.wireframe===!0,H=n[U.id];H===void 0&&(H={},n[U.id]=H);let X=D.isInstancedMesh===!0?D.id:0,Y=H[X];Y===void 0&&(Y={},H[X]=Y);let q=Y[I.id];q===void 0&&(q={},Y[I.id]=q);let K=q[k];return K===void 0&&(K=d(l()),q[k]=K),K}function d(D){let U=[],I=[],L=[];for(let k=0;k<t;k++)U[k]=0,I[k]=0,L[k]=0;return{geometry:null,program:null,wireframe:!1,newAttributes:U,enabledAttributes:I,attributeDivisors:L,object:D,attributes:{},index:null}}function f(D,U,I,L){let k=s.attributes,H=U.attributes,X=0,Y=I.getAttributes();for(let q in Y)if(Y[q].location>=0){let N=k[q],ie=H[q];if(ie===void 0&&(q==="instanceMatrix"&&D.instanceMatrix&&(ie=D.instanceMatrix),q==="instanceColor"&&D.instanceColor&&(ie=D.instanceColor)),N===void 0||N.attribute!==ie||ie&&N.data!==ie.data)return!0;X++}return s.attributesNum!==X||s.index!==L}function p(D,U,I,L){let k={},H=U.attributes,X=0,Y=I.getAttributes();for(let q in Y)if(Y[q].location>=0){let N=H[q];N===void 0&&(q==="instanceMatrix"&&D.instanceMatrix&&(N=D.instanceMatrix),q==="instanceColor"&&D.instanceColor&&(N=D.instanceColor));let ie={};ie.attribute=N,N&&N.data&&(ie.data=N.data),k[q]=ie,X++}s.attributes=k,s.attributesNum=X,s.index=L}function y(){let D=s.newAttributes;for(let U=0,I=D.length;U<I;U++)D[U]=0}function m(D){g(D,0)}function g(D,U){let I=s.newAttributes,L=s.enabledAttributes,k=s.attributeDivisors;I[D]=1,L[D]===0&&(i.enableVertexAttribArray(D),L[D]=1),k[D]!==U&&(i.vertexAttribDivisor(D,U),k[D]=U)}function v(){let D=s.newAttributes,U=s.enabledAttributes;for(let I=0,L=U.length;I<L;I++)U[I]!==D[I]&&(i.disableVertexAttribArray(I),U[I]=0)}function S(D,U,I,L,k,H,X){X===!0?i.vertexAttribIPointer(D,U,I,k,H):i.vertexAttribPointer(D,U,I,L,k,H)}function _(D,U,I,L){y();let k=L.attributes,H=I.getAttributes(),X=U.defaultAttributeValues;for(let Y in H){let q=H[Y];if(q.location>=0){let K=k[Y];if(K===void 0&&(Y==="instanceMatrix"&&D.instanceMatrix&&(K=D.instanceMatrix),Y==="instanceColor"&&D.instanceColor&&(K=D.instanceColor)),K!==void 0){let N=K.normalized,ie=K.itemSize,re=e.get(K);if(re===void 0)continue;let De=re.buffer,Te=re.type,$e=re.bytesPerElement,$=Te===i.INT||Te===i.UNSIGNED_INT||K.gpuType===Gl;if(K.isInterleavedBufferAttribute){let ee=K.data,_e=ee.stride,Be=K.offset;if(ee.isInstancedInterleavedBuffer){for(let xe=0;xe<q.locationSize;xe++)g(q.location+xe,ee.meshPerAttribute);D.isInstancedMesh!==!0&&L._maxInstanceCount===void 0&&(L._maxInstanceCount=ee.meshPerAttribute*ee.count)}else for(let xe=0;xe<q.locationSize;xe++)m(q.location+xe);i.bindBuffer(i.ARRAY_BUFFER,De);for(let xe=0;xe<q.locationSize;xe++)S(q.location+xe,ie/q.locationSize,Te,N,_e*$e,(Be+ie/q.locationSize*xe)*$e,$)}else{if(K.isInstancedBufferAttribute){for(let ee=0;ee<q.locationSize;ee++)g(q.location+ee,K.meshPerAttribute);D.isInstancedMesh!==!0&&L._maxInstanceCount===void 0&&(L._maxInstanceCount=K.meshPerAttribute*K.count)}else for(let ee=0;ee<q.locationSize;ee++)m(q.location+ee);i.bindBuffer(i.ARRAY_BUFFER,De);for(let ee=0;ee<q.locationSize;ee++)S(q.location+ee,ie/q.locationSize,Te,N,ie*$e,ie/q.locationSize*ee*$e,$)}}else if(X!==void 0){let N=X[Y];if(N!==void 0)switch(N.length){case 2:i.vertexAttrib2fv(q.location,N);break;case 3:i.vertexAttrib3fv(q.location,N);break;case 4:i.vertexAttrib4fv(q.location,N);break;default:i.vertexAttrib1fv(q.location,N)}}}}v()}function M(){A();for(let D in n){let U=n[D];for(let I in U){let L=U[I];for(let k in L){let H=L[k];for(let X in H)h(H[X].object),delete H[X];delete L[k]}}delete n[D]}}function w(D){if(n[D.id]===void 0)return;let U=n[D.id];for(let I in U){let L=U[I];for(let k in L){let H=L[k];for(let X in H)h(H[X].object),delete H[X];delete L[k]}}delete n[D.id]}function E(D){for(let U in n){let I=n[U];for(let L in I){let k=I[L];if(k[D.id]===void 0)continue;let H=k[D.id];for(let X in H)h(H[X].object),delete H[X];delete k[D.id]}}}function x(D){for(let U in n){let I=n[U],L=D.isInstancedMesh===!0?D.id:0,k=I[L];if(k!==void 0){for(let H in k){let X=k[H];for(let Y in X)h(X[Y].object),delete X[Y];delete k[H]}delete I[L],Object.keys(I).length===0&&delete n[U]}}}function A(){C(),a=!0,s!==r&&(s=r,c(s.object))}function C(){r.geometry=null,r.program=null,r.wireframe=!1}return{setup:o,reset:A,resetDefaultState:C,dispose:M,releaseStatesOfGeometry:w,releaseStatesOfObject:x,releaseStatesOfProgram:E,initAttributes:y,enableAttribute:m,disableUnusedAttributes:v}}function wS(i,e,t){let n;function r(l){n=l}function s(l,c){i.drawArrays(n,l,c),t.update(c,n,1)}function a(l,c,h){h!==0&&(i.drawArraysInstanced(n,l,c,h),t.update(c,n,h))}function o(l,c,h){if(h===0)return;e.get("WEBGL_multi_draw").multiDrawArraysWEBGL(n,l,0,c,0,h);let d=0;for(let f=0;f<h;f++)d+=c[f];t.update(d,n,1)}this.setMode=r,this.render=s,this.renderInstances=a,this.renderMultiDraw=o}function TS(i,e,t,n){let r;function s(){if(r!==void 0)return r;if(e.has("EXT_texture_filter_anisotropic")===!0){let E=e.get("EXT_texture_filter_anisotropic");r=i.getParameter(E.MAX_TEXTURE_MAX_ANISOTROPY_EXT)}else r=0;return r}function a(E){return!(E!==Ri&&n.convert(E)!==i.getParameter(i.IMPLEMENTATION_COLOR_READ_FORMAT))}function o(E){let x=E===ji&&(e.has("EXT_color_buffer_half_float")||e.has("EXT_color_buffer_float"));return!(E!==di&&E!==fi&&!x&&n.convert(E)!==i.getParameter(i.IMPLEMENTATION_COLOR_READ_TYPE))}function l(E){if(E==="highp"){if(i.getShaderPrecisionFormat(i.VERTEX_SHADER,i.HIGH_FLOAT).precision>0&&i.getShaderPrecisionFormat(i.FRAGMENT_SHADER,i.HIGH_FLOAT).precision>0)return"highp";E="mediump"}return E==="mediump"&&i.getShaderPrecisionFormat(i.VERTEX_SHADER,i.MEDIUM_FLOAT).precision>0&&i.getShaderPrecisionFormat(i.FRAGMENT_SHADER,i.MEDIUM_FLOAT).precision>0?"mediump":"lowp"}let c=t.precision!==void 0?t.precision:"highp",h=l(c);h!==c&&(Ce("WebGLRenderer:",c,"not supported, using",h,"instead."),c=h);let u=t.logarithmicDepthBuffer===!0,d=t.reversedDepthBuffer===!0&&e.has("EXT_clip_control");t.reversedDepthBuffer===!0&&d===!1&&Ce("WebGLRenderer: Unable to use reversed depth buffer due to missing EXT_clip_control extension. Fallback to default depth buffer.");let f=i.getParameter(i.MAX_TEXTURE_IMAGE_UNITS),p=i.getParameter(i.MAX_VERTEX_TEXTURE_IMAGE_UNITS),y=i.getParameter(i.MAX_TEXTURE_SIZE),m=i.getParameter(i.MAX_CUBE_MAP_TEXTURE_SIZE),g=i.getParameter(i.MAX_VERTEX_ATTRIBS),v=i.getParameter(i.MAX_VERTEX_UNIFORM_VECTORS),S=i.getParameter(i.MAX_VARYING_VECTORS),_=i.getParameter(i.MAX_FRAGMENT_UNIFORM_VECTORS),M=i.getParameter(i.MAX_SAMPLES),w=i.getParameter(i.SAMPLES);return{isWebGL2:!0,getMaxAnisotropy:s,getMaxPrecision:l,textureFormatReadable:a,textureTypeReadable:o,precision:c,logarithmicDepthBuffer:u,reversedDepthBuffer:d,maxTextures:f,maxVertexTextures:p,maxTextureSize:y,maxCubemapSize:m,maxAttributes:g,maxVertexUniforms:v,maxVaryings:S,maxFragmentUniforms:_,maxSamples:M,samples:w}}function ES(i){let e=this,t=null,n=0,r=!1,s=!1,a=new qt,o=new Oe,l={value:null,needsUpdate:!1};this.uniform=l,this.numPlanes=0,this.numIntersection=0,this.init=function(u,d){let f=u.length!==0||d||n!==0||r;return r=d,n=u.length,f},this.beginShadows=function(){s=!0,h(null)},this.endShadows=function(){s=!1},this.setGlobalState=function(u,d){t=h(u,d,0)},this.setState=function(u,d,f){let p=u.clippingPlanes,y=u.clipIntersection,m=u.clipShadows,g=i.get(u);if(!r||p===null||p.length===0||s&&!m)s?h(null):c();else{let v=s?0:n,S=v*4,_=g.clippingState||null;l.value=_,_=h(p,d,S,f);for(let M=0;M!==S;++M)_[M]=t[M];g.clippingState=_,this.numIntersection=y?this.numPlanes:0,this.numPlanes+=v}};function c(){l.value!==t&&(l.value=t,l.needsUpdate=n>0),e.numPlanes=n,e.numIntersection=0}function h(u,d,f,p){let y=u!==null?u.length:0,m=null;if(y!==0){if(m=l.value,p!==!0||m===null){let g=f+y*4,v=d.matrixWorldInverse;o.getNormalMatrix(v),(m===null||m.length<g)&&(m=new Float32Array(g));for(let S=0,_=f;S!==y;++S,_+=4)a.copy(u[S]).applyMatrix4(v,o),a.normal.toArray(m,_),m[_+3]=a.constant}l.value=m,l.needsUpdate=!0}return e.numPlanes=y,e.numIntersection=0,m}}var ks=4,AS=6,CS=20,RS=256,Ka=new Wi,Qm=new Ie,sd=null,ad=0,od=0,ld=!1,PS=new P,Gr=new P,Cc=class{constructor(e){this._renderer=e,this._pingPongRenderTarget=null,this._lodMax=0,this._cubeSize=0,this._sizeLods=[],this._lodMeshes=[],this._backgroundBox=null,this._cubemapMaterial=null,this._equirectMaterial=null,this._blurMaterial=null,this._ggxMaterial=null}fromScene(e,t=0,n=.1,r=100,s={}){let{size:a=256,position:o=PS}=s;sd=this._renderer.getRenderTarget(),ad=this._renderer.getActiveCubeFace(),od=this._renderer.getActiveMipmapLevel(),ld=this._renderer.xr.enabled,this._renderer.xr.enabled=!1,this._setSize(a);let l=this._allocateTargets();return l.depthBuffer=!0,this._sceneToCubeUV(e,n,r,l,o),t>0&&this._blur(l,0,0,t),this._applyPMREM(l),this._cleanup(l),l}fromEquirectangular(e,t=null){return this._fromTexture(e,t)}fromCubemap(e,t=null){return this._fromTexture(e,t)}compileCubemapShader(){this._cubemapMaterial===null&&(this._cubemapMaterial=ig(),this._compileMaterial(this._cubemapMaterial))}compileEquirectangularShader(){this._equirectMaterial===null&&(this._equirectMaterial=tg(),this._compileMaterial(this._equirectMaterial))}dispose(){this._dispose(),this._cubemapMaterial!==null&&this._cubemapMaterial.dispose(),this._equirectMaterial!==null&&this._equirectMaterial.dispose(),this._backgroundBox!==null&&(this._backgroundBox.geometry.dispose(),this._backgroundBox.material.dispose())}_setSize(e){this._lodMax=Math.floor(Math.log2(e)),this._cubeSize=Math.pow(2,this._lodMax)}_dispose(){this._blurMaterial!==null&&this._blurMaterial.dispose(),this._ggxMaterial!==null&&this._ggxMaterial.dispose(),this._pingPongRenderTarget!==null&&this._pingPongRenderTarget.dispose();for(let e=0;e<this._lodMeshes.length;e++)this._lodMeshes[e].geometry.dispose()}_cleanup(e){this._renderer.setRenderTarget(sd,ad,od),this._renderer.xr.enabled=ld,e.scissorTest=!1,Bs(e,0,0,e.width,e.height)}_fromTexture(e,t){e.mapping===sr||e.mapping===kr?this._setSize(e.image.length===0?16:e.image[0].width||e.image[0].image.width):this._setSize(e.image.width/4),sd=this._renderer.getRenderTarget(),ad=this._renderer.getActiveCubeFace(),od=this._renderer.getActiveMipmapLevel(),ld=this._renderer.xr.enabled,this._renderer.xr.enabled=!1;let n=t||this._allocateTargets();return this._textureToCubeUV(e,n),this._applyPMREM(n),this._cleanup(n),n}_allocateTargets(){let e=3*Math.max(this._cubeSize,112),t=4*this._cubeSize,n={magFilter:St,minFilter:St,generateMipmaps:!1,type:ji,format:Ri,colorSpace:li,depthBuffer:!1},r=eg(e,t,n);if(this._pingPongRenderTarget===null||this._pingPongRenderTarget.width!==e||this._pingPongRenderTarget.height!==t){this._pingPongRenderTarget!==null&&this._dispose(),this._pingPongRenderTarget=eg(e,t,n);let{_lodMax:s}=this;({lodMeshes:this._lodMeshes,sizeLods:this._sizeLods}=IS(s)),this._blurMaterial=DS(s,e,t),this._ggxMaterial=LS(s,e,t)}return r}_compileMaterial(e){let t=new at(new ht,e);this._renderer.compile(t,Ka)}_sceneToCubeUV(e,t,n,r,s){let l=new Rt(90,1,t,n),c=[1,-1,1,1,1,1],h=[1,1,1,-1,-1,-1],u=this._renderer,d=u.autoClear,f=u.toneMapping;u.getClearColor(Qm),u.toneMapping=Xi,u.autoClear=!1,u.state.buffers.depth.getReversed()&&(u.setRenderTarget(r),u.clearDepth(),u.setRenderTarget(null)),this._backgroundBox===null&&(this._backgroundBox=new at(new Ir,new Yt({name:"PMREM.Background",side:ui,depthWrite:!1,depthTest:!1})));let y=this._backgroundBox,m=y.material,g=!1,v=e.background;v?v.isColor&&(m.color.copy(v),e.background=null,g=!0):(m.color.copy(Qm),g=!0);for(let S=0;S<6;S++){let _=S%3;_===0?(l.up.set(0,c[S],0),l.position.set(s.x,s.y,s.z),l.lookAt(s.x+h[S],s.y,s.z)):_===1?(l.up.set(0,0,c[S]),l.position.set(s.x,s.y,s.z),l.lookAt(s.x,s.y+h[S],s.z)):(l.up.set(0,c[S],0),l.position.set(s.x,s.y,s.z),l.lookAt(s.x,s.y,s.z+h[S]));let M=this._cubeSize;Bs(r,_*M,S>2?M:0,M,M),u.setRenderTarget(r),g&&u.render(y,l),u.render(e,l)}u.toneMapping=f,u.autoClear=d,e.background=v}_textureToCubeUV(e,t){let n=this._renderer,r=e.mapping===sr||e.mapping===kr;r?(this._cubemapMaterial===null&&(this._cubemapMaterial=ig()),this._cubemapMaterial.uniforms.flipEnvMap.value=e.isRenderTargetTexture===!1?-1:1):this._equirectMaterial===null&&(this._equirectMaterial=tg());let s=r?this._cubemapMaterial:this._equirectMaterial,a=this._lodMeshes[0];a.material=s;let o=s.uniforms;o.envMap.value=e;let l=this._cubeSize;Bs(t,0,0,3*l,2*l),n.setRenderTarget(t),n.render(a,Ka)}_applyPMREM(e){let t=this._renderer,n=t.autoClear;t.autoClear=!1;let r=this._lodMeshes.length;for(let s=1;s<r;s++)this._applyGGXFilter(e,s-1,s);t.autoClear=n}_applyGGXFilter(e,t,n){let r=this._renderer,s=this._pingPongRenderTarget,a=this._ggxMaterial,o=this._lodMeshes[n];o.material=a;let l=a.uniforms,c=n/(this._lodMeshes.length-1),h=t/(this._lodMeshes.length-1),u=Math.sqrt(c*c-h*h),d=c*1.25,f=u*d,{_lodMax:p}=this,y=this._sizeLods[n],m=3*y*(n>p-ks?n-p+ks:0),g=4*(this._cubeSize-y);l.envMap.value=e.texture,l.roughness.value=f,l.mipInt.value=p-t,Bs(s,m,g,3*y,2*y),r.setRenderTarget(s),r.render(o,Ka),l.envMap.value=s.texture,l.roughness.value=0,l.mipInt.value=p-n,Bs(e,m,g,3*y,2*y),r.setRenderTarget(e),r.render(o,Ka)}_blur(e,t,n,r){let s=this._pingPongRenderTarget,a=Math.min(r,Math.PI)/Math.SQRT2;this._blurPass(e,s,t,n,a),this._blurPass(s,e,n,n,a)}_blurPass(e,t,n,r,s){let a=this._renderer,o=this._blurMaterial,l=this._lodMeshes[r];l.material=o;let c=o.uniforms;c.envMap.value=e.texture,c.sigma.value=s,c.mipInt.value=this._lodMax-n;let h=this._sizeLods[r],u=3*h*(r>this._lodMax-ks?r-this._lodMax+ks:0),d=4*(this._cubeSize-h);Bs(t,u,d,3*h,2*h),a.setRenderTarget(t),a.render(l,Ka)}};function IS(i){let e=[],t=[],n=i,r=i-ks+1+AS;for(let s=0;s<r;s++){let a=Math.pow(2,n);e.push(a);let o=1/(a-2),l=-o,c=1+o,h=[l,l,c,l,c,c,l,l,c,c,l,c],u=6,d=6,f=3,p=new Float32Array(f*d*u),y=new Float32Array(f*d*u);for(let g=0;g<u;g++){let v=g%3*2/3-1,S=g>2?0:-1,_=[v,S,0,v+2/3,S,0,v+2/3,S+1,0,v,S,0,v+2/3,S+1,0,v,S+1,0];p.set(_,f*d*g);for(let M=0;M<d;M++){let w=h[M*2]*2-1,E=h[M*2+1]*2-1;g===0?Gr.set(1,E,w):g===1?Gr.set(-w,1,-E):g===2?Gr.set(-w,E,1):g===3?Gr.set(-1,E,-w):g===4?Gr.set(-w,-1,E):Gr.set(w,E,-1),Gr.toArray(y,(g*d+M)*f)}}let m=new ht;m.setAttribute("position",new Ye(p,f)),m.setAttribute("outputDirection",new Ye(y,f)),t.push(new at(m,null)),n>ks&&n--}return{lodMeshes:t,sizeLods:e}}function eg(i,e,t){let n=new ci(i,e,t);return n.texture.mapping=za,n.texture.name="PMREM.cubeUv",n.scissorTest=!0,n}function Bs(i,e,t,n,r){i.viewport.set(e,t,n,r),i.scissor.set(e,t,n,r)}function LS(i,e,t){return new $t({name:"PMREMGGXConvolution",defines:{GGX_SAMPLES:RS,CUBEUV_TEXEL_WIDTH:1/e,CUBEUV_TEXEL_HEIGHT:1/t,CUBEUV_MAX_MIP:`${i}.0`},uniforms:{envMap:{value:null},roughness:{value:0},mipInt:{value:0}},vertexShader:Pc(),fragmentShader:`

			precision highp float;
			precision highp int;

			varying vec3 vOutputDirection;

			uniform sampler2D envMap;
			uniform float roughness;
			uniform float mipInt;

			#define ENVMAP_TYPE_CUBE_UV
			#include <cube_uv_reflection_fragment>

			#define PI 3.14159265359

			// Van der Corput radical inverse
			float radicalInverse_VdC(uint bits) {
				bits = (bits << 16u) | (bits >> 16u);
				bits = ((bits & 0x55555555u) << 1u) | ((bits & 0xAAAAAAAAu) >> 1u);
				bits = ((bits & 0x33333333u) << 2u) | ((bits & 0xCCCCCCCCu) >> 2u);
				bits = ((bits & 0x0F0F0F0Fu) << 4u) | ((bits & 0xF0F0F0F0u) >> 4u);
				bits = ((bits & 0x00FF00FFu) << 8u) | ((bits & 0xFF00FF00u) >> 8u);
				return float(bits) * 2.3283064365386963e-10; // / 0x100000000
			}

			// Hammersley sequence
			vec2 hammersley(uint i, uint N) {
				return vec2(float(i) / float(N), radicalInverse_VdC(i));
			}

			// GGX VNDF importance sampling (Eric Heitz 2018)
			// "Sampling the GGX Distribution of Visible Normals"
			// https://jcgt.org/published/0007/04/01/
			vec3 importanceSampleGGX_VNDF(vec2 Xi, vec3 V, float roughness) {
				float alpha = roughness * roughness;

				// Section 4.1: Orthonormal basis
				vec3 T1 = vec3(1.0, 0.0, 0.0);
				vec3 T2 = cross(V, T1);

				// Section 4.2: Parameterization of projected area
				float r = sqrt(Xi.x);
				float phi = 2.0 * PI * Xi.y;
				float t1 = r * cos(phi);
				float t2 = r * sin(phi);
				float s = 0.5 * (1.0 + V.z);
				t2 = (1.0 - s) * sqrt(1.0 - t1 * t1) + s * t2;

				// Section 4.3: Reprojection onto hemisphere
				vec3 Nh = t1 * T1 + t2 * T2 + sqrt(max(0.0, 1.0 - t1 * t1 - t2 * t2)) * V;

				// Section 3.4: Transform back to ellipsoid configuration
				return normalize(vec3(alpha * Nh.x, alpha * Nh.y, max(0.0, Nh.z)));
			}

			void main() {
				vec3 N = normalize(vOutputDirection);
				vec3 V = N; // Assume view direction equals normal for pre-filtering

				vec3 prefilteredColor = vec3(0.0);
				float totalWeight = 0.0;

				// For very low roughness, just sample the environment directly
				if (roughness < 0.001) {
					gl_FragColor = vec4(bilinearCubeUV(envMap, N, mipInt), 1.0);
					return;
				}

				// Tangent space basis for VNDF sampling
				vec3 up = abs(N.z) < 0.999 ? vec3(0.0, 0.0, 1.0) : vec3(1.0, 0.0, 0.0);
				vec3 tangent = normalize(cross(up, N));
				vec3 bitangent = cross(N, tangent);

				for(uint i = 0u; i < uint(GGX_SAMPLES); i++) {
					vec2 Xi = hammersley(i, uint(GGX_SAMPLES));

					// For PMREM, V = N, so in tangent space V is always (0, 0, 1)
					vec3 H_tangent = importanceSampleGGX_VNDF(Xi, vec3(0.0, 0.0, 1.0), roughness);

					// Transform H back to world space
					vec3 H = normalize(tangent * H_tangent.x + bitangent * H_tangent.y + N * H_tangent.z);
					vec3 L = normalize(2.0 * dot(V, H) * H - V);

					float NdotL = max(dot(N, L), 0.0);

					if(NdotL > 0.0) {
						// Sample environment at fixed mip level
						// VNDF importance sampling handles the distribution filtering
						vec3 sampleColor = bilinearCubeUV(envMap, L, mipInt);

						// Weight by NdotL for the split-sum approximation
						// VNDF PDF naturally accounts for the visible microfacet distribution
						prefilteredColor += sampleColor * NdotL;
						totalWeight += NdotL;
					}
				}

				if (totalWeight > 0.0) {
					prefilteredColor = prefilteredColor / totalWeight;
				}

				gl_FragColor = vec4(prefilteredColor, 1.0);
			}
		`,blending:an,depthTest:!1,depthWrite:!1})}function DS(i,e,t){return new $t({name:"SphericalGaussianBlur",defines:{SAMPLES:CS,CUBEUV_TEXEL_WIDTH:1/e,CUBEUV_TEXEL_HEIGHT:1/t,CUBEUV_MAX_MIP:`${i}.0`},uniforms:{envMap:{value:null},sigma:{value:0},mipInt:{value:0}},vertexShader:Pc(),fragmentShader:`

			precision highp float;
			precision highp int;

			varying vec3 vOutputDirection;

			uniform sampler2D envMap;
			uniform float sigma;
			uniform float mipInt;

			#define ENVMAP_TYPE_CUBE_UV
			#include <cube_uv_reflection_fragment>

			#define PI 3.14159265359
			#define GOLDEN_ANGLE 2.39996322973

			void main() {

				if ( sigma == 0.0 ) {

					gl_FragColor = vec4( bilinearCubeUV( envMap, vOutputDirection, mipInt ), 1.0 );
					return;

				}

				vec3 outputDirection = normalize( vOutputDirection );

				vec3 up = abs( outputDirection.z ) < 0.999 ? vec3( 0.0, 0.0, 1.0 ) : vec3( 1.0, 0.0, 0.0 );
				vec3 tangent = normalize( cross( up, outputDirection ) );
				vec3 bitangent = cross( outputDirection, tangent );

				// Truncate the kernel at three standard deviations or at the antipode.
				float thetaMax = min( 3.0 * sigma, PI );
				float truncation = 1.0 - exp( - 0.5 * thetaMax * thetaMax / ( sigma * sigma ) );

				vec3 accumColor = vec3( 0.0 );
				float accumWeight = 0.0;

				for ( int i = 0; i < SAMPLES; i ++ ) {

					// Stratified inverse-CDF sampling of the Gaussian, placed on a golden-angle spiral.
					float stratum = ( float( i ) + 0.5 ) / float( SAMPLES );
					float theta = sigma * sqrt( - 2.0 * log( 1.0 - stratum * truncation ) );
					float phi = float( i ) * GOLDEN_ANGLE;

					vec3 offset = cos( phi ) * tangent + sin( phi ) * bitangent;
					vec3 sampleDirection = cos( theta ) * outputDirection + sin( theta ) * offset;

					// Correct the planar sample density to solid angle.
					float weight = sin( theta ) / theta;

					accumColor += weight * bilinearCubeUV( envMap, sampleDirection, mipInt );
					accumWeight += weight;

				}

				gl_FragColor = vec4( accumColor / accumWeight, 1.0 );

			}
		`,blending:an,depthTest:!1,depthWrite:!1})}function tg(){return new $t({name:"EquirectangularToCubeUV",uniforms:{envMap:{value:null}},vertexShader:Pc(),fragmentShader:`

			precision mediump float;
			precision mediump int;

			varying vec3 vOutputDirection;

			uniform sampler2D envMap;

			#include <common>

			void main() {

				vec3 outputDirection = normalize( vOutputDirection );
				vec2 uv = equirectUv( outputDirection );

				gl_FragColor = vec4( texture2D ( envMap, uv ).rgb, 1.0 );

			}
		`,blending:an,depthTest:!1,depthWrite:!1})}function ig(){return new $t({name:"CubemapToCubeUV",uniforms:{envMap:{value:null},flipEnvMap:{value:-1}},vertexShader:Pc(),fragmentShader:`

			precision mediump float;
			precision mediump int;

			uniform float flipEnvMap;

			varying vec3 vOutputDirection;

			uniform samplerCube envMap;

			void main() {

				gl_FragColor = textureCube( envMap, vec3( flipEnvMap * vOutputDirection.x, vOutputDirection.yz ) );

			}
		`,blending:an,depthTest:!1,depthWrite:!1})}function Pc(){return`

		precision mediump float;
		precision mediump int;

		attribute vec3 outputDirection;

		varying vec3 vOutputDirection;

		void main() {

			vOutputDirection = outputDirection;
			gl_Position = vec4( position, 1.0 );

		}
	`}var Rc=class extends ci{constructor(e=1,t={}){super(e,e,t),this.isWebGLCubeRenderTarget=!0;let n={width:e,height:e,depth:1},r=[n,n,n,n,n,n];this.texture=new Ta(r),this._setTextureOptions(t),this.texture.isRenderTargetTexture=!0}fromEquirectangularTexture(e,t){this.texture.type=t.type,this.texture.colorSpace=t.colorSpace,this.texture.generateMipmaps=t.generateMipmaps,this.texture.minFilter=t.minFilter,this.texture.magFilter=t.magFilter;let n={uniforms:{tEquirect:{value:null}},vertexShader:`

				varying vec3 vWorldDirection;

				vec3 transformDirection( in vec3 dir, in mat4 matrix ) {

					return normalize( ( matrix * vec4( dir, 0.0 ) ).xyz );

				}

				void main() {

					vWorldDirection = transformDirection( position, modelMatrix );

					#include <begin_vertex>
					#include <project_vertex>

				}
			`,fragmentShader:`

				uniform sampler2D tEquirect;

				varying vec3 vWorldDirection;

				#include <common>

				void main() {

					vec3 direction = normalize( vWorldDirection );

					vec2 sampleUV = equirectUv( direction );

					gl_FragColor = texture2D( tEquirect, sampleUV );

				}
			`},r=new Ir(5,5,5),s=new $t({name:"CubemapFromEquirect",uniforms:Vr(n.uniforms),vertexShader:n.vertexShader,fragmentShader:n.fragmentShader,side:ui,blending:an});s.uniforms.tEquirect.value=t;let a=new at(r,s),o=t.minFilter;return t.minFilter===Ci&&(t.minFilter=St),new Nl(1,10,this).update(e,a),t.minFilter=o,a.geometry.dispose(),a.material.dispose(),this}clear(e,t=!0,n=!0,r=!0){let s=e.getRenderTarget();for(let a=0;a<6;a++)e.setRenderTarget(this,a),e.clear(t,n,r);e.setRenderTarget(s)}};function NS(i){let e=new WeakMap,t=new WeakMap,n=null;function r(d,f=!1){return d==null?null:f?a(d):s(d)}function s(d){if(d&&d.isTexture){let f=d.mapping;if(f===kl||f===zl)if(e.has(d)){let p=e.get(d).texture;return o(p,d.mapping)}else{let p=d.image;if(p&&p.height>0){let y=new Rc(p.height);return y.fromEquirectangularTexture(i,d),e.set(d,y),d.addEventListener("dispose",c),o(y.texture,d.mapping)}else return null}}return d}function a(d){if(d&&d.isTexture){let f=d.mapping,p=f===kl||f===zl,y=f===sr||f===kr;if(p||y){let m=t.get(d),g=m!==void 0?m.texture.pmremVersion:0;if(d.isRenderTargetTexture&&d.pmremVersion!==g)return n===null&&(n=new Cc(i)),m=p?n.fromEquirectangular(d,m):n.fromCubemap(d,m),m.texture.pmremVersion=d.pmremVersion,t.set(d,m),m.texture;if(m!==void 0)return m.texture;{let v=d.image;return p&&v&&v.height>0||y&&v&&l(v)?(n===null&&(n=new Cc(i)),m=p?n.fromEquirectangular(d):n.fromCubemap(d),m.texture.pmremVersion=d.pmremVersion,t.set(d,m),d.addEventListener("dispose",h),m.texture):null}}}return d}function o(d,f){return f===kl?d.mapping=sr:f===zl&&(d.mapping=kr),d}function l(d){let f=0,p=6;for(let y=0;y<p;y++)d[y]!==void 0&&f++;return f===p}function c(d){let f=d.target;f.removeEventListener("dispose",c);let p=e.get(f);p!==void 0&&(e.delete(f),p.dispose())}function h(d){let f=d.target;f.removeEventListener("dispose",h);let p=t.get(f);p!==void 0&&(t.delete(f),p.dispose())}function u(){e=new WeakMap,t=new WeakMap,n!==null&&(n.dispose(),n=null)}return{get:r,dispose:u}}function US(i){let e={};function t(n){if(e[n]!==void 0)return e[n];let r=i.getExtension(n);return e[n]=r,r}return{has:function(n){return t(n)!==null},init:function(){t("EXT_color_buffer_float"),t("WEBGL_clip_cull_distance"),t("OES_texture_float_linear"),t("EXT_color_buffer_half_float"),t("WEBGL_multisampled_render_to_texture"),t("WEBGL_render_shared_exponent")},get:function(n){let r=t(n);return r===null&&Mr("WebGLRenderer: "+n+" extension not supported."),r}}}function OS(i,e,t,n){let r={},s=new WeakMap;function a(u){let d=u.target;d.index!==null&&e.remove(d.index);for(let p in d.attributes)e.remove(d.attributes[p]);d.removeEventListener("dispose",a),delete r[d.id];let f=s.get(d);f&&(e.remove(f),s.delete(d)),n.releaseStatesOfGeometry(d),d.isInstancedBufferGeometry===!0&&delete d._maxInstanceCount,t.memory.geometries--}function o(u,d){return r[d.id]===!0||(d.addEventListener("dispose",a),r[d.id]=!0,t.memory.geometries++),d}function l(u){let d=u.attributes;for(let f in d)e.update(d[f],i.ARRAY_BUFFER)}function c(u){let d=[],f=u.index,p=u.attributes.position,y=0;if(p===void 0)return;if(f!==null){let v=f.array;y=f.version;for(let S=0,_=v.length;S<_;S+=3){let M=v[S+0],w=v[S+1],E=v[S+2];d.push(M,w,w,E,E,M)}}else{let v=p.array;y=p.version;for(let S=0,_=v.length/3-1;S<_;S+=3){let M=S+0,w=S+1,E=S+2;d.push(M,w,w,E,E,M)}}let m=new(p.count>=65535?ba:va)(d,1);m.version=y;let g=s.get(u);g&&e.remove(g),s.set(u,m)}function h(u){let d=s.get(u);if(d){let f=u.index;f!==null&&d.version<f.version&&c(u)}else c(u);return s.get(u)}return{get:o,update:l,getWireframeAttribute:h}}function FS(i,e,t){let n;function r(u){n=u}let s,a;function o(u){s=u.type,a=u.bytesPerElement}function l(u,d){i.drawElements(n,d,s,u*a),t.update(d,n,1)}function c(u,d,f){f!==0&&(i.drawElementsInstanced(n,d,s,u*a,f),t.update(d,n,f))}function h(u,d,f){if(f===0)return;e.get("WEBGL_multi_draw").multiDrawElementsWEBGL(n,d,0,s,u,0,f);let y=0;for(let m=0;m<f;m++)y+=d[m];t.update(y,n,1)}this.setMode=r,this.setIndex=o,this.render=l,this.renderInstances=c,this.renderMultiDraw=h}function BS(i){let e={geometries:0,textures:0},t={frame:0,calls:0,triangles:0,points:0,lines:0};function n(s,a,o){switch(t.calls++,a){case i.TRIANGLES:t.triangles+=o*(s/3);break;case i.LINES:t.lines+=o*(s/2);break;case i.LINE_STRIP:t.lines+=o*(s-1);break;case i.LINE_LOOP:t.lines+=o*s;break;case i.POINTS:t.points+=o*s;break;default:Fe("WebGLInfo: Unknown draw mode:",a);break}}function r(){t.calls=0,t.triangles=0,t.points=0,t.lines=0}return{memory:e,render:t,programs:null,autoReset:!0,reset:r,update:n}}function kS(i,e,t){let n=new WeakMap,r=new Xe;function s(a,o,l){let c=a.morphTargetInfluences,h=o.morphAttributes.position||o.morphAttributes.normal||o.morphAttributes.color,u=h!==void 0?h.length:0,d=n.get(o);if(d===void 0||d.count!==u){let A=function(){E.dispose(),n.delete(o),o.removeEventListener("dispose",A)};d!==void 0&&d.texture.dispose();let f=o.morphAttributes.position!==void 0,p=o.morphAttributes.normal!==void 0,y=o.morphAttributes.color!==void 0,m=o.morphAttributes.position||[],g=o.morphAttributes.normal||[],v=o.morphAttributes.color||[],S=0;f===!0&&(S=1),p===!0&&(S=2),y===!0&&(S=3);let _=o.attributes.position.count*S,M=1;_>e.maxTextureSize&&(M=Math.ceil(_/e.maxTextureSize),_=e.maxTextureSize);let w=new Float32Array(_*M*4*u),E=new ya(w,_,M,u);E.type=fi,E.needsUpdate=!0;let x=S*4;for(let C=0;C<u;C++){let D=m[C],U=g[C],I=v[C],L=_*M*4*C;for(let k=0;k<D.count;k++){let H=k*x;f===!0&&(r.fromBufferAttribute(D,k),w[L+H+0]=r.x,w[L+H+1]=r.y,w[L+H+2]=r.z,w[L+H+3]=0),p===!0&&(r.fromBufferAttribute(U,k),w[L+H+4]=r.x,w[L+H+5]=r.y,w[L+H+6]=r.z,w[L+H+7]=0),y===!0&&(r.fromBufferAttribute(I,k),w[L+H+8]=r.x,w[L+H+9]=r.y,w[L+H+10]=r.z,w[L+H+11]=I.itemSize===4?r.w:1)}}d={count:u,texture:E,size:new Se(_,M)},n.set(o,d),o.addEventListener("dispose",A)}if(a.isInstancedMesh===!0&&a.morphTexture!==null)l.getUniforms().setValue(i,"morphTexture",a.morphTexture,t);else{let f=0;for(let y=0;y<c.length;y++)f+=c[y];let p=o.morphTargetsRelative?1:1-f;l.getUniforms().setValue(i,"morphTargetBaseInfluence",p),l.getUniforms().setValue(i,"morphTargetInfluences",c)}l.getUniforms().setValue(i,"morphTargetsTexture",d.texture,t),l.getUniforms().setValue(i,"morphTargetsTextureSize",d.size)}return{update:s}}function zS(i,e,t,n,r){let s=new WeakMap;function a(c){let h=r.render.frame,u=c.geometry,d=e.get(c,u);if(s.get(d)!==h&&(e.update(d),s.set(d,h)),c.isInstancedMesh&&(c.hasEventListener("dispose",l)===!1&&c.addEventListener("dispose",l),s.get(c)!==h&&(t.update(c.instanceMatrix,i.ARRAY_BUFFER),c.instanceColor!==null&&t.update(c.instanceColor,i.ARRAY_BUFFER),s.set(c,h))),c.isSkinnedMesh){let f=c.skeleton;s.get(f)!==h&&(f.update(),s.set(f,h))}return d}function o(){s=new WeakMap}function l(c){let h=c.target;h.removeEventListener("dispose",l),n.releaseStatesOfObject(h),t.remove(h.instanceMatrix),h.instanceColor!==null&&t.remove(h.instanceColor)}return{update:a,dispose:o}}var VS={[Du]:"LINEAR_TONE_MAPPING",[Nu]:"REINHARD_TONE_MAPPING",[Uu]:"CINEON_TONE_MAPPING",[Ou]:"ACES_FILMIC_TONE_MAPPING",[Bu]:"AGX_TONE_MAPPING",[ku]:"NEUTRAL_TONE_MAPPING",[Fu]:"CUSTOM_TONE_MAPPING"};function GS(i,e,t,n,r,s){let a=new ci(e,t,{type:i,depthBuffer:r,stencilBuffer:s,samples:n?4:0,storeMultisampledDepthBuffer:!1,storeMultisampledStencilBuffer:!1,resolveDepthBuffer:!1,resolveStencilBuffer:!1}),o=null,l=null,c=new ht;c.setAttribute("position",new st([-1,3,0,-1,-1,0,3,-1,0],3)),c.setAttribute("uv",new st([0,2,0,0,2,0],2));let h=new Tl({uniforms:{tDiffuse:{value:null}},vertexShader:`
			precision highp float;

			uniform mat4 modelViewMatrix;
			uniform mat4 projectionMatrix;

			attribute vec3 position;
			attribute vec2 uv;

			varying vec2 vUv;

			void main() {
				vUv = uv;
				gl_Position = projectionMatrix * modelViewMatrix * vec4( position, 1.0 );
			}`,fragmentShader:`
			precision highp float;

			uniform sampler2D tDiffuse;

			varying vec2 vUv;

			#include <tonemapping_pars_fragment>
			#include <colorspace_pars_fragment>

			void main() {
				gl_FragColor = texture2D( tDiffuse, vUv );

				#ifdef LINEAR_TONE_MAPPING
					gl_FragColor.rgb = LinearToneMapping( gl_FragColor.rgb );
				#elif defined( REINHARD_TONE_MAPPING )
					gl_FragColor.rgb = ReinhardToneMapping( gl_FragColor.rgb );
				#elif defined( CINEON_TONE_MAPPING )
					gl_FragColor.rgb = CineonToneMapping( gl_FragColor.rgb );
				#elif defined( ACES_FILMIC_TONE_MAPPING )
					gl_FragColor.rgb = ACESFilmicToneMapping( gl_FragColor.rgb );
				#elif defined( AGX_TONE_MAPPING )
					gl_FragColor.rgb = AgXToneMapping( gl_FragColor.rgb );
				#elif defined( NEUTRAL_TONE_MAPPING )
					gl_FragColor.rgb = NeutralToneMapping( gl_FragColor.rgb );
				#elif defined( CUSTOM_TONE_MAPPING )
					gl_FragColor.rgb = CustomToneMapping( gl_FragColor.rgb );
				#endif

				#ifdef SRGB_TRANSFER
					gl_FragColor = sRGBTransferOETF( gl_FragColor );
				#endif
			}`,depthTest:!1,depthWrite:!1}),u=new at(c,h),d=new Wi(-1,1,1,-1,0,1),f=null,p=null,y=!1,m,g=null,v=[],S=!1;this.setSize=function(_,M){a.setSize(_,M),o!==null&&o.setSize(_,M),l!==null&&l.setSize(_,M);for(let w=0;w<v.length;w++){let E=v[w];E.setSize&&E.setSize(_,M)}},this.setEffects=function(_){v=_,S=v.length>0&&v[0].isRenderPass===!0;let M=a.width,w=a.height;v.length>0&&o===null&&(o=new ci(M,w,{type:ji,depthBuffer:!1,stencilBuffer:!1}),l=new ci(M,w,{type:ji,depthBuffer:!1,stencilBuffer:!1}));for(let E=0;E<v.length;E++){let x=v[E];x.setSize&&x.setSize(M,w)}},this.begin=function(_,M){if(y||_.toneMapping===Xi&&v.length===0)return!1;if(g=M,M!==null){let w=M.width,E=M.height;(a.width!==w||a.height!==E)&&this.setSize(w,E)}return S===!1&&_.setRenderTarget(a),m=_.toneMapping,_.toneMapping=Xi,!0},this.hasRenderPass=function(){return S},this.end=function(_,M){_.toneMapping=m,y=!0;let w=a,E=o;for(let x=0;x<v.length;x++){let A=v[x];A.enabled!==!1&&(A.render(_,E,w,M),A.needsSwap!==!1&&(w=E,E=E===o?l:o))}if(f!==_.outputColorSpace||p!==_.toneMapping){f=_.outputColorSpace,p=_.toneMapping,h.defines={},je.getTransfer(f)===rt&&(h.defines.SRGB_TRANSFER="");let x=VS[p];x&&(h.defines[x]=""),h.needsUpdate=!0}h.uniforms.tDiffuse.value=w.texture,_.setRenderTarget(g),_.render(u,d),g=null,y=!1},this.isCompositing=function(){return y},this.dispose=function(){a.dispose(),o!==null&&o.dispose(),l!==null&&l.dispose(),c.dispose(),h.dispose()}}var wg=new Pt,ud=new Jn(1,1),Tg=new ya,Eg=new bl,Ag=new Ta,ng=[],rg=[],sg=new Float32Array(16),ag=new Float32Array(9),og=new Float32Array(4);function Vs(i,e,t){let n=i[0];if(n<=0||n>0)return i;let r=e*t,s=ng[r];if(s===void 0&&(s=new Float32Array(r),ng[r]=s),e!==0){n.toArray(s,0);for(let a=1,o=0;a!==e;++a)o+=t,i[a].toArray(s,o)}return s}function Ft(i,e){if(i.length!==e.length)return!1;for(let t=0,n=i.length;t<n;t++)if(i[t]!==e[t])return!1;return!0}function Bt(i,e){for(let t=0,n=e.length;t<n;t++)i[t]=e[t]}function Ic(i,e){let t=rg[e];t===void 0&&(t=new Int32Array(e),rg[e]=t);for(let n=0;n!==e;++n)t[n]=i.allocateTextureUnit();return t}function HS(i,e){let t=this.cache;t[0]!==e&&(i.uniform1f(this.addr,e),t[0]=e)}function WS(i,e){let t=this.cache;if(e.x!==void 0)(t[0]!==e.x||t[1]!==e.y)&&(i.uniform2f(this.addr,e.x,e.y),t[0]=e.x,t[1]=e.y);else{if(Ft(t,e))return;i.uniform2fv(this.addr,e),Bt(t,e)}}function XS(i,e){let t=this.cache;if(e.x!==void 0)(t[0]!==e.x||t[1]!==e.y||t[2]!==e.z)&&(i.uniform3f(this.addr,e.x,e.y,e.z),t[0]=e.x,t[1]=e.y,t[2]=e.z);else if(e.r!==void 0)(t[0]!==e.r||t[1]!==e.g||t[2]!==e.b)&&(i.uniform3f(this.addr,e.r,e.g,e.b),t[0]=e.r,t[1]=e.g,t[2]=e.b);else{if(Ft(t,e))return;i.uniform3fv(this.addr,e),Bt(t,e)}}function qS(i,e){let t=this.cache;if(e.x!==void 0)(t[0]!==e.x||t[1]!==e.y||t[2]!==e.z||t[3]!==e.w)&&(i.uniform4f(this.addr,e.x,e.y,e.z,e.w),t[0]=e.x,t[1]=e.y,t[2]=e.z,t[3]=e.w);else{if(Ft(t,e))return;i.uniform4fv(this.addr,e),Bt(t,e)}}function jS(i,e){let t=this.cache,n=e.elements;if(n===void 0){if(Ft(t,e))return;i.uniformMatrix2fv(this.addr,!1,e),Bt(t,e)}else{if(Ft(t,n))return;og.set(n),i.uniformMatrix2fv(this.addr,!1,og),Bt(t,n)}}function YS(i,e){let t=this.cache,n=e.elements;if(n===void 0){if(Ft(t,e))return;i.uniformMatrix3fv(this.addr,!1,e),Bt(t,e)}else{if(Ft(t,n))return;ag.set(n),i.uniformMatrix3fv(this.addr,!1,ag),Bt(t,n)}}function $S(i,e){let t=this.cache,n=e.elements;if(n===void 0){if(Ft(t,e))return;i.uniformMatrix4fv(this.addr,!1,e),Bt(t,e)}else{if(Ft(t,n))return;sg.set(n),i.uniformMatrix4fv(this.addr,!1,sg),Bt(t,n)}}function ZS(i,e){let t=this.cache;t[0]!==e&&(i.uniform1i(this.addr,e),t[0]=e)}function KS(i,e){let t=this.cache;if(e.x!==void 0)(t[0]!==e.x||t[1]!==e.y)&&(i.uniform2i(this.addr,e.x,e.y),t[0]=e.x,t[1]=e.y);else{if(Ft(t,e))return;i.uniform2iv(this.addr,e),Bt(t,e)}}function JS(i,e){let t=this.cache;if(e.x!==void 0)(t[0]!==e.x||t[1]!==e.y||t[2]!==e.z)&&(i.uniform3i(this.addr,e.x,e.y,e.z),t[0]=e.x,t[1]=e.y,t[2]=e.z);else{if(Ft(t,e))return;i.uniform3iv(this.addr,e),Bt(t,e)}}function QS(i,e){let t=this.cache;if(e.x!==void 0)(t[0]!==e.x||t[1]!==e.y||t[2]!==e.z||t[3]!==e.w)&&(i.uniform4i(this.addr,e.x,e.y,e.z,e.w),t[0]=e.x,t[1]=e.y,t[2]=e.z,t[3]=e.w);else{if(Ft(t,e))return;i.uniform4iv(this.addr,e),Bt(t,e)}}function eM(i,e){let t=this.cache;t[0]!==e&&(i.uniform1ui(this.addr,e),t[0]=e)}function tM(i,e){let t=this.cache;if(e.x!==void 0)(t[0]!==e.x||t[1]!==e.y)&&(i.uniform2ui(this.addr,e.x,e.y),t[0]=e.x,t[1]=e.y);else{if(Ft(t,e))return;i.uniform2uiv(this.addr,e),Bt(t,e)}}function iM(i,e){let t=this.cache;if(e.x!==void 0)(t[0]!==e.x||t[1]!==e.y||t[2]!==e.z)&&(i.uniform3ui(this.addr,e.x,e.y,e.z),t[0]=e.x,t[1]=e.y,t[2]=e.z);else{if(Ft(t,e))return;i.uniform3uiv(this.addr,e),Bt(t,e)}}function nM(i,e){let t=this.cache;if(e.x!==void 0)(t[0]!==e.x||t[1]!==e.y||t[2]!==e.z||t[3]!==e.w)&&(i.uniform4ui(this.addr,e.x,e.y,e.z,e.w),t[0]=e.x,t[1]=e.y,t[2]=e.z,t[3]=e.w);else{if(Ft(t,e))return;i.uniform4uiv(this.addr,e),Bt(t,e)}}function rM(i,e,t){let n=this.cache,r=t.allocateTextureUnit();n[0]!==r&&(i.uniform1i(this.addr,r),n[0]=r);let s;this.type===i.SAMPLER_2D_SHADOW?(ud.compareFunction=t.isReversedDepthBuffer()?wc:Mc,s=ud):s=wg,t.setTexture2D(e||s,r)}function sM(i,e,t){let n=this.cache,r=t.allocateTextureUnit();n[0]!==r&&(i.uniform1i(this.addr,r),n[0]=r),t.setTexture3D(e||Eg,r)}function aM(i,e,t){let n=this.cache,r=t.allocateTextureUnit();n[0]!==r&&(i.uniform1i(this.addr,r),n[0]=r),t.setTextureCube(e||Ag,r)}function oM(i,e,t){let n=this.cache,r=t.allocateTextureUnit();n[0]!==r&&(i.uniform1i(this.addr,r),n[0]=r),t.setTexture2DArray(e||Tg,r)}function lM(i){switch(i){case 5126:return HS;case 35664:return WS;case 35665:return XS;case 35666:return qS;case 35674:return jS;case 35675:return YS;case 35676:return $S;case 5124:case 35670:return ZS;case 35667:case 35671:return KS;case 35668:case 35672:return JS;case 35669:case 35673:return QS;case 5125:return eM;case 36294:return tM;case 36295:return iM;case 36296:return nM;case 35678:case 36198:case 36298:case 36306:case 35682:return rM;case 35679:case 36299:case 36307:return sM;case 35680:case 36300:case 36308:case 36293:return aM;case 36289:case 36303:case 36311:case 36292:return oM}}function cM(i,e){i.uniform1fv(this.addr,e)}function hM(i,e){let t=Vs(e,this.size,2);i.uniform2fv(this.addr,t)}function uM(i,e){let t=Vs(e,this.size,3);i.uniform3fv(this.addr,t)}function dM(i,e){let t=Vs(e,this.size,4);i.uniform4fv(this.addr,t)}function fM(i,e){let t=Vs(e,this.size,4);i.uniformMatrix2fv(this.addr,!1,t)}function pM(i,e){let t=Vs(e,this.size,9);i.uniformMatrix3fv(this.addr,!1,t)}function mM(i,e){let t=Vs(e,this.size,16);i.uniformMatrix4fv(this.addr,!1,t)}function gM(i,e){i.uniform1iv(this.addr,e)}function yM(i,e){i.uniform2iv(this.addr,e)}function _M(i,e){i.uniform3iv(this.addr,e)}function xM(i,e){i.uniform4iv(this.addr,e)}function vM(i,e){i.uniform1uiv(this.addr,e)}function bM(i,e){i.uniform2uiv(this.addr,e)}function SM(i,e){i.uniform3uiv(this.addr,e)}function MM(i,e){i.uniform4uiv(this.addr,e)}function wM(i,e,t){let n=this.cache,r=e.length,s=Ic(t,r);Ft(n,s)||(i.uniform1iv(this.addr,s),Bt(n,s));let a;this.type===i.SAMPLER_2D_SHADOW?a=ud:a=wg;for(let o=0;o!==r;++o)t.setTexture2D(e[o]||a,s[o])}function TM(i,e,t){let n=this.cache,r=e.length,s=Ic(t,r);Ft(n,s)||(i.uniform1iv(this.addr,s),Bt(n,s));for(let a=0;a!==r;++a)t.setTexture3D(e[a]||Eg,s[a])}function EM(i,e,t){let n=this.cache,r=e.length,s=Ic(t,r);Ft(n,s)||(i.uniform1iv(this.addr,s),Bt(n,s));for(let a=0;a!==r;++a)t.setTextureCube(e[a]||Ag,s[a])}function AM(i,e,t){let n=this.cache,r=e.length,s=Ic(t,r);Ft(n,s)||(i.uniform1iv(this.addr,s),Bt(n,s));for(let a=0;a!==r;++a)t.setTexture2DArray(e[a]||Tg,s[a])}function CM(i){switch(i){case 5126:return cM;case 35664:return hM;case 35665:return uM;case 35666:return dM;case 35674:return fM;case 35675:return pM;case 35676:return mM;case 5124:case 35670:return gM;case 35667:case 35671:return yM;case 35668:case 35672:return _M;case 35669:case 35673:return xM;case 5125:return vM;case 36294:return bM;case 36295:return SM;case 36296:return MM;case 35678:case 36198:case 36298:case 36306:case 35682:return wM;case 35679:case 36299:case 36307:return TM;case 35680:case 36300:case 36308:case 36293:return EM;case 36289:case 36303:case 36311:case 36292:return AM}}var dd=class{constructor(e,t,n){this.id=e,this.addr=n,this.cache=[],this.type=t.type,this.setValue=lM(t.type)}},fd=class{constructor(e,t,n){this.id=e,this.addr=n,this.cache=[],this.type=t.type,this.size=t.size,this.setValue=CM(t.type)}},pd=class{constructor(e){this.id=e,this.seq=[],this.map={}}setValue(e,t,n){let r=this.seq;for(let s=0,a=r.length;s!==a;++s){let o=r[s];o.setValue(e,t[o.id],n)}}},cd=/(\w+)(\])?(\[|\.)?/g;function lg(i,e){i.seq.push(e),i.map[e.id]=e}function RM(i,e,t){let n=i.name,r=n.length;for(cd.lastIndex=0;;){let s=cd.exec(n),a=cd.lastIndex,o=s[1],l=s[2]==="]",c=s[3];if(l&&(o=o|0),c===void 0||c==="["&&a+2===r){lg(t,c===void 0?new dd(o,i,e):new fd(o,i,e));break}else{let u=t.map[o];u===void 0&&(u=new pd(o),lg(t,u)),t=u}}}var zs=class{constructor(e,t){this.seq=[],this.map={};let n=e.getProgramParameter(t,e.ACTIVE_UNIFORMS);for(let a=0;a<n;++a){let o=e.getActiveUniform(t,a),l=e.getUniformLocation(t,o.name);RM(o,l,this)}let r=[],s=[];for(let a of this.seq)a.type===e.SAMPLER_2D_SHADOW||a.type===e.SAMPLER_CUBE_SHADOW||a.type===e.SAMPLER_2D_ARRAY_SHADOW?r.push(a):s.push(a);r.length>0&&(this.seq=r.concat(s))}setValue(e,t,n,r){let s=this.map[t];s!==void 0&&s.setValue(e,n,r)}setOptional(e,t,n){let r=t[n];r!==void 0&&this.setValue(e,n,r)}static upload(e,t,n,r){for(let s=0,a=t.length;s!==a;++s){let o=t[s],l=n[o.id];l.needsUpdate!==!1&&o.setValue(e,l.value,r)}}static seqWithValue(e,t){let n=[];for(let r=0,s=e.length;r!==s;++r){let a=e[r];a.id in t&&n.push(a)}return n}};function cg(i,e,t){let n=i.createShader(e);return i.shaderSource(n,t),i.compileShader(n),n}var PM=37297,IM=0;function LM(i,e){let t=i.split(`
`),n=[],r=Math.max(e-6,0),s=Math.min(e+6,t.length);for(let a=r;a<s;a++){let o=a+1;n.push(`${o===e?">":" "} ${o}: ${t[a]}`)}return n.join(`
`)}var hg=new Oe;function DM(i){je._getMatrix(hg,je.workingColorSpace,i);let e=`mat3( ${hg.elements.map(t=>t.toFixed(4))} )`;switch(je.getTransfer(i)){case ma:return[e,"LinearTransferOETF"];case rt:return[e,"sRGBTransferOETF"];default:return Ce("WebGLProgram: Unsupported color space: ",i),[e,"LinearTransferOETF"]}}function ug(i,e,t){let n=i.getShaderParameter(e,i.COMPILE_STATUS),s=(i.getShaderInfoLog(e)||"").trim();if(n&&s==="")return"";let a=/ERROR: 0:(\d+)/.exec(s);if(a){let o=parseInt(a[1]);return t.toUpperCase()+`

`+s+`

`+LM(i.getShaderSource(e),o)}else return s}function NM(i,e){let t=DM(e);return[`vec4 ${i}( vec4 value ) {`,`	return ${t[1]}( vec4( value.rgb * ${t[0]}, value.a ) );`,"}"].join(`
`)}var UM={[Du]:"Linear",[Nu]:"Reinhard",[Uu]:"Cineon",[Ou]:"ACESFilmic",[Bu]:"AgX",[ku]:"Neutral",[Fu]:"Custom"};function OM(i,e){let t=UM[e];return t===void 0?(Ce("WebGLProgram: Unsupported toneMapping:",e),"vec3 "+i+"( vec3 color ) { return LinearToneMapping( color ); }"):"vec3 "+i+"( vec3 color ) { return "+t+"ToneMapping( color ); }"}var Ac=new P;function FM(){je.getLuminanceCoefficients(Ac);let i=Ac.x.toFixed(4),e=Ac.y.toFixed(4),t=Ac.z.toFixed(4);return["float luminance( const in vec3 rgb ) {",`	const vec3 weights = vec3( ${i}, ${e}, ${t} );`,"	return dot( weights, rgb );","}"].join(`
`)}function BM(i){return[i.extensionClipCullDistance?"#extension GL_ANGLE_clip_cull_distance : require":"",i.extensionMultiDraw?"#extension GL_ANGLE_multi_draw : require":""].filter(Qa).join(`
`)}function kM(i){let e=[];for(let t in i){let n=i[t];n!==!1&&e.push("#define "+t+" "+n)}return e.join(`
`)}function zM(i,e){let t={},n=i.getProgramParameter(e,i.ACTIVE_ATTRIBUTES);for(let r=0;r<n;r++){let s=i.getActiveAttrib(e,r),a=s.name,o=1;s.type===i.FLOAT_MAT2&&(o=2),s.type===i.FLOAT_MAT3&&(o=3),s.type===i.FLOAT_MAT4&&(o=4),t[a]={type:s.type,location:i.getAttribLocation(e,a),locationSize:o}}return t}function Qa(i){return i!==""}function dg(i,e){let t=e.numSpotLightShadows+e.numSpotLightMaps-e.numSpotLightShadowsWithMaps;return i.replace(/NUM_SUN_LIGHTS/g,e.numSunLights).replace(/NUM_DIR_LIGHTS/g,e.numDirLights).replace(/NUM_SPOT_LIGHTS/g,e.numSpotLights).replace(/NUM_SPOT_LIGHT_MAPS/g,e.numSpotLightMaps).replace(/NUM_SPOT_LIGHT_COORDS/g,t).replace(/NUM_RECT_AREA_LIGHTS/g,e.numRectAreaLights).replace(/NUM_POINT_LIGHTS/g,e.numPointLights).replace(/NUM_HEMI_LIGHTS/g,e.numHemiLights).replace(/NUM_SUN_LIGHT_SHADOWS/g,e.numSunLightShadows).replace(/NUM_DIR_LIGHT_SHADOWS/g,e.numDirLightShadows).replace(/NUM_SPOT_LIGHT_SHADOWS_WITH_MAPS/g,e.numSpotLightShadowsWithMaps).replace(/NUM_SPOT_LIGHT_SHADOWS/g,e.numSpotLightShadows).replace(/NUM_POINT_LIGHT_SHADOWS/g,e.numPointLightShadows)}function fg(i,e){return i.replace(/NUM_CLIPPING_PLANES/g,e.numClippingPlanes).replace(/UNION_CLIPPING_PLANES/g,e.numClippingPlanes-e.numClipIntersection)}var VM=/^[ \t]*#include +<([\w\d./]+)>/gm;function md(i){return i.replace(VM,HM)}var GM=new Map;function HM(i,e){let t=qe[e];if(t===void 0){let n=GM.get(e);if(n!==void 0)t=qe[n],Ce('WebGLRenderer: Shader chunk "%s" has been deprecated. Use "%s" instead.',e,n);else throw new Error("THREE.WebGLProgram: Can not resolve #include <"+e+">")}return md(t)}var WM=/#pragma unroll_loop_start\s+for\s*\(\s*int\s+i\s*=\s*(\d+)\s*;\s*i\s*<\s*(\d+)\s*;\s*i\s*\+\+\s*\)\s*{([\s\S]+?)}\s+#pragma unroll_loop_end/g;function pg(i){return i.replace(WM,XM)}function XM(i,e,t,n){let r="";for(let s=parseInt(e);s<parseInt(t);s++)r+=n.replace(/\[\s*i\s*\]/g,"[ "+s+" ]").replace(/UNROLLED_LOOP_INDEX/g,s);return r}function mg(i){let e=`precision ${i.precision} float;
	precision ${i.precision} int;
	precision ${i.precision} sampler2D;
	precision ${i.precision} samplerCube;
	precision ${i.precision} sampler3D;
	precision ${i.precision} sampler2DArray;
	precision ${i.precision} sampler2DShadow;
	precision ${i.precision} samplerCubeShadow;
	precision ${i.precision} sampler2DArrayShadow;
	precision ${i.precision} isampler2D;
	precision ${i.precision} isampler3D;
	precision ${i.precision} isamplerCube;
	precision ${i.precision} isampler2DArray;
	precision ${i.precision} usampler2D;
	precision ${i.precision} usampler3D;
	precision ${i.precision} usamplerCube;
	precision ${i.precision} usampler2DArray;
	`;return i.precision==="highp"?e+=`
#define HIGH_PRECISION`:i.precision==="mediump"?e+=`
#define MEDIUM_PRECISION`:i.precision==="lowp"&&(e+=`
#define LOW_PRECISION`),e}var qM={[ka]:"SHADOWMAP_TYPE_PCF",[Is]:"SHADOWMAP_TYPE_VSM"};function jM(i){return qM[i.shadowMapType]||"SHADOWMAP_TYPE_BASIC"}var YM={[sr]:"ENVMAP_TYPE_CUBE",[kr]:"ENVMAP_TYPE_CUBE",[za]:"ENVMAP_TYPE_CUBE_UV"};function $M(i){return i.envMap===!1?"ENVMAP_TYPE_CUBE":YM[i.envMapMode]||"ENVMAP_TYPE_CUBE"}var ZM={[kr]:"ENVMAP_MODE_REFRACTION"};function KM(i){return i.envMap===!1?"ENVMAP_MODE_REFLECTION":ZM[i.envMapMode]||"ENVMAP_MODE_REFLECTION"}var JM={[Bl]:"ENVMAP_BLENDING_MULTIPLY",[Nm]:"ENVMAP_BLENDING_MIX",[Um]:"ENVMAP_BLENDING_ADD"};function QM(i){return i.envMap===!1?"ENVMAP_BLENDING_NONE":JM[i.combine]||"ENVMAP_BLENDING_NONE"}function ew(i){let e=i.envMapCubeUVHeight;if(e===null)return null;let t=Math.log2(e)-2,n=1/e;return{texelWidth:1/(3*Math.max(Math.pow(2,t),112)),texelHeight:n,maxMip:t}}function tw(i,e,t,n){let r=i.getContext(),s=t.defines,a=t.vertexShader,o=t.fragmentShader,l=jM(t),c=$M(t),h=KM(t),u=QM(t),d=ew(t),f=BM(t),p=kM(s),y=r.createProgram(),m,g,v=t.glslVersion?"#version "+t.glslVersion+`
`:"";t.isRawShaderMaterial?(m=["#define SHADER_TYPE "+t.shaderType,"#define SHADER_NAME "+t.shaderName,p].filter(Qa).join(`
`),m.length>0&&(m+=`
`),g=["#define SHADER_TYPE "+t.shaderType,"#define SHADER_NAME "+t.shaderName,p].filter(Qa).join(`
`),g.length>0&&(g+=`
`)):(m=[mg(t),"#define SHADER_TYPE "+t.shaderType,"#define SHADER_NAME "+t.shaderName,p,t.extensionClipCullDistance?"#define USE_CLIP_DISTANCE":"",t.batching?"#define USE_BATCHING":"",t.batchingColor?"#define USE_BATCHING_COLOR":"",t.instancing?"#define USE_INSTANCING":"",t.instancingColor?"#define USE_INSTANCING_COLOR":"",t.instancingMorph?"#define USE_INSTANCING_MORPH":"",t.useFog&&t.fog?"#define USE_FOG":"",t.useFog&&t.fogExp2?"#define FOG_EXP2":"",t.map?"#define USE_MAP":"",t.envMap?"#define USE_ENVMAP":"",t.envMap?"#define "+h:"",t.lightMap?"#define USE_LIGHTMAP":"",t.aoMap?"#define USE_AOMAP":"",t.bumpMap?"#define USE_BUMPMAP":"",t.normalMap?"#define USE_NORMALMAP":"",t.normalMapObjectSpace?"#define USE_NORMALMAP_OBJECTSPACE":"",t.normalMapTangentSpace?"#define USE_NORMALMAP_TANGENTSPACE":"",t.displacementMap?"#define USE_DISPLACEMENTMAP":"",t.emissiveMap?"#define USE_EMISSIVEMAP":"",t.anisotropy?"#define USE_ANISOTROPY":"",t.anisotropyMap?"#define USE_ANISOTROPYMAP":"",t.clearcoatMap?"#define USE_CLEARCOATMAP":"",t.clearcoatRoughnessMap?"#define USE_CLEARCOAT_ROUGHNESSMAP":"",t.clearcoatNormalMap?"#define USE_CLEARCOAT_NORMALMAP":"",t.iridescenceMap?"#define USE_IRIDESCENCEMAP":"",t.iridescenceThicknessMap?"#define USE_IRIDESCENCE_THICKNESSMAP":"",t.specularMap?"#define USE_SPECULARMAP":"",t.specularColorMap?"#define USE_SPECULAR_COLORMAP":"",t.specularIntensityMap?"#define USE_SPECULAR_INTENSITYMAP":"",t.roughnessMap?"#define USE_ROUGHNESSMAP":"",t.metalnessMap?"#define USE_METALNESSMAP":"",t.alphaMap?"#define USE_ALPHAMAP":"",t.alphaHash?"#define USE_ALPHAHASH":"",t.transmission?"#define USE_TRANSMISSION":"",t.transmissionMap?"#define USE_TRANSMISSIONMAP":"",t.thicknessMap?"#define USE_THICKNESSMAP":"",t.sheenColorMap?"#define USE_SHEEN_COLORMAP":"",t.sheenRoughnessMap?"#define USE_SHEEN_ROUGHNESSMAP":"",t.mapUv?"#define MAP_UV "+t.mapUv:"",t.alphaMapUv?"#define ALPHAMAP_UV "+t.alphaMapUv:"",t.lightMapUv?"#define LIGHTMAP_UV "+t.lightMapUv:"",t.aoMapUv?"#define AOMAP_UV "+t.aoMapUv:"",t.emissiveMapUv?"#define EMISSIVEMAP_UV "+t.emissiveMapUv:"",t.bumpMapUv?"#define BUMPMAP_UV "+t.bumpMapUv:"",t.normalMapUv?"#define NORMALMAP_UV "+t.normalMapUv:"",t.displacementMapUv?"#define DISPLACEMENTMAP_UV "+t.displacementMapUv:"",t.metalnessMapUv?"#define METALNESSMAP_UV "+t.metalnessMapUv:"",t.roughnessMapUv?"#define ROUGHNESSMAP_UV "+t.roughnessMapUv:"",t.anisotropyMapUv?"#define ANISOTROPYMAP_UV "+t.anisotropyMapUv:"",t.clearcoatMapUv?"#define CLEARCOATMAP_UV "+t.clearcoatMapUv:"",t.clearcoatNormalMapUv?"#define CLEARCOAT_NORMALMAP_UV "+t.clearcoatNormalMapUv:"",t.clearcoatRoughnessMapUv?"#define CLEARCOAT_ROUGHNESSMAP_UV "+t.clearcoatRoughnessMapUv:"",t.iridescenceMapUv?"#define IRIDESCENCEMAP_UV "+t.iridescenceMapUv:"",t.iridescenceThicknessMapUv?"#define IRIDESCENCE_THICKNESSMAP_UV "+t.iridescenceThicknessMapUv:"",t.sheenColorMapUv?"#define SHEEN_COLORMAP_UV "+t.sheenColorMapUv:"",t.sheenRoughnessMapUv?"#define SHEEN_ROUGHNESSMAP_UV "+t.sheenRoughnessMapUv:"",t.specularMapUv?"#define SPECULARMAP_UV "+t.specularMapUv:"",t.specularColorMapUv?"#define SPECULAR_COLORMAP_UV "+t.specularColorMapUv:"",t.specularIntensityMapUv?"#define SPECULAR_INTENSITYMAP_UV "+t.specularIntensityMapUv:"",t.transmissionMapUv?"#define TRANSMISSIONMAP_UV "+t.transmissionMapUv:"",t.thicknessMapUv?"#define THICKNESSMAP_UV "+t.thicknessMapUv:"",t.vertexTangents&&t.flatShading===!1?"#define USE_TANGENT":"",t.vertexNormals?"#define HAS_NORMAL":"",t.vertexColors?"#define USE_COLOR":"",t.vertexAlphas?"#define USE_COLOR_ALPHA":"",t.vertexUv1s?"#define USE_UV1":"",t.vertexUv2s?"#define USE_UV2":"",t.vertexUv3s?"#define USE_UV3":"",t.pointsUvs?"#define USE_POINTS_UV":"",t.flatShading?"#define FLAT_SHADED":"",t.skinning?"#define USE_SKINNING":"",t.morphTargets?"#define USE_MORPHTARGETS":"",t.morphNormals&&t.flatShading===!1?"#define USE_MORPHNORMALS":"",t.morphColors?"#define USE_MORPHCOLORS":"",t.morphTargetsCount>0?"#define MORPHTARGETS_TEXTURE_STRIDE "+t.morphTextureStride:"",t.morphTargetsCount>0?"#define MORPHTARGETS_COUNT "+t.morphTargetsCount:"",t.doubleSided?"#define DOUBLE_SIDED":"",t.flipSided?"#define FLIP_SIDED":"",t.shadowMapEnabled?"#define USE_SHADOWMAP":"",t.shadowMapEnabled?"#define "+l:"",t.sizeAttenuation?"#define USE_SIZEATTENUATION":"",t.numLightProbes>0?"#define USE_LIGHT_PROBES":"",t.logarithmicDepthBuffer?"#define USE_LOGARITHMIC_DEPTH_BUFFER":"",t.reversedDepthBuffer?"#define USE_REVERSED_DEPTH_BUFFER":"","uniform mat4 modelMatrix;","uniform mat4 modelViewMatrix;","uniform mat4 projectionMatrix;","uniform mat4 viewMatrix;","uniform mat3 normalMatrix;","uniform vec3 cameraPosition;","uniform bool isOrthographic;","#ifdef USE_INSTANCING","	attribute mat4 instanceMatrix;","#endif","#ifdef USE_INSTANCING_COLOR","	attribute vec3 instanceColor;","#endif","#ifdef USE_INSTANCING_MORPH","	uniform sampler2D morphTexture;","#endif","attribute vec3 position;","attribute vec3 normal;","attribute vec2 uv;","#ifdef USE_UV1","	attribute vec2 uv1;","#endif","#ifdef USE_UV2","	attribute vec2 uv2;","#endif","#ifdef USE_UV3","	attribute vec2 uv3;","#endif","#ifdef USE_TANGENT","	attribute vec4 tangent;","#endif","#if defined( USE_COLOR_ALPHA )","	attribute vec4 color;","#elif defined( USE_COLOR )","	attribute vec3 color;","#endif","#ifdef USE_SKINNING","	attribute vec4 skinIndex;","	attribute vec4 skinWeight;","#endif",`
`].filter(Qa).join(`
`),g=[mg(t),"#define SHADER_TYPE "+t.shaderType,"#define SHADER_NAME "+t.shaderName,p,t.useFog&&t.fog?"#define USE_FOG":"",t.useFog&&t.fogExp2?"#define FOG_EXP2":"",t.alphaToCoverage?"#define ALPHA_TO_COVERAGE":"",t.map?"#define USE_MAP":"",t.matcap?"#define USE_MATCAP":"",t.envMap?"#define USE_ENVMAP":"",t.envMap?"#define "+c:"",t.envMap?"#define "+h:"",t.envMap?"#define "+u:"",d?"#define CUBEUV_TEXEL_WIDTH "+d.texelWidth:"",d?"#define CUBEUV_TEXEL_HEIGHT "+d.texelHeight:"",d?"#define CUBEUV_MAX_MIP "+d.maxMip+".0":"",t.lightMap?"#define USE_LIGHTMAP":"",t.aoMap?"#define USE_AOMAP":"",t.bumpMap?"#define USE_BUMPMAP":"",t.normalMap?"#define USE_NORMALMAP":"",t.normalMapObjectSpace?"#define USE_NORMALMAP_OBJECTSPACE":"",t.normalMapTangentSpace?"#define USE_NORMALMAP_TANGENTSPACE":"",t.packedNormalMap?"#define USE_PACKED_NORMALMAP":"",t.emissiveMap?"#define USE_EMISSIVEMAP":"",t.anisotropy?"#define USE_ANISOTROPY":"",t.anisotropyMap?"#define USE_ANISOTROPYMAP":"",t.clearcoat?"#define USE_CLEARCOAT":"",t.clearcoatMap?"#define USE_CLEARCOATMAP":"",t.clearcoatRoughnessMap?"#define USE_CLEARCOAT_ROUGHNESSMAP":"",t.clearcoatNormalMap?"#define USE_CLEARCOAT_NORMALMAP":"",t.dispersion?"#define USE_DISPERSION":"",t.retroreflection?"#define USE_RETROREFLECTION":"",t.iridescence?"#define USE_IRIDESCENCE":"",t.iridescenceMap?"#define USE_IRIDESCENCEMAP":"",t.iridescenceThicknessMap?"#define USE_IRIDESCENCE_THICKNESSMAP":"",t.specularMap?"#define USE_SPECULARMAP":"",t.specularColorMap?"#define USE_SPECULAR_COLORMAP":"",t.specularIntensityMap?"#define USE_SPECULAR_INTENSITYMAP":"",t.roughnessMap?"#define USE_ROUGHNESSMAP":"",t.metalnessMap?"#define USE_METALNESSMAP":"",t.alphaMap?"#define USE_ALPHAMAP":"",t.alphaTest?"#define USE_ALPHATEST":"",t.alphaHash?"#define USE_ALPHAHASH":"",t.sheen?"#define USE_SHEEN":"",t.sheenColorMap?"#define USE_SHEEN_COLORMAP":"",t.sheenRoughnessMap?"#define USE_SHEEN_ROUGHNESSMAP":"",t.transmission?"#define USE_TRANSMISSION":"",t.transmissionMap?"#define USE_TRANSMISSIONMAP":"",t.thicknessMap?"#define USE_THICKNESSMAP":"",t.vertexTangents&&t.flatShading===!1?"#define USE_TANGENT":"",t.vertexColors||t.instancingColor?"#define USE_COLOR":"",t.vertexAlphas||t.batchingColor?"#define USE_COLOR_ALPHA":"",t.vertexUv1s?"#define USE_UV1":"",t.vertexUv2s?"#define USE_UV2":"",t.vertexUv3s?"#define USE_UV3":"",t.pointsUvs?"#define USE_POINTS_UV":"",t.gradientMap?"#define USE_GRADIENTMAP":"",t.flatShading?"#define FLAT_SHADED":"",t.doubleSided?"#define DOUBLE_SIDED":"",t.flipSided?"#define FLIP_SIDED":"",t.shadowMapEnabled?"#define USE_SHADOWMAP":"",t.shadowMapEnabled?"#define "+l:"",t.premultipliedAlpha?"#define PREMULTIPLIED_ALPHA":"",t.numLightProbes>0?"#define USE_LIGHT_PROBES":"",t.numLightProbeGrids>0?"#define USE_LIGHT_PROBES_GRID":"",t.decodeVideoTexture?"#define DECODE_VIDEO_TEXTURE":"",t.decodeVideoTextureEmissive?"#define DECODE_VIDEO_TEXTURE_EMISSIVE":"",t.logarithmicDepthBuffer?"#define USE_LOGARITHMIC_DEPTH_BUFFER":"",t.reversedDepthBuffer?"#define USE_REVERSED_DEPTH_BUFFER":"","uniform mat4 viewMatrix;","uniform vec3 cameraPosition;","uniform bool isOrthographic;",t.toneMapping!==Xi?"#define TONE_MAPPING":"",t.toneMapping!==Xi?qe.tonemapping_pars_fragment:"",t.toneMapping!==Xi?OM("toneMapping",t.toneMapping):"",t.dithering?"#define DITHERING":"",t.opaque?"#define OPAQUE":"",qe.colorspace_pars_fragment,NM("linearToOutputTexel",t.outputColorSpace),FM(),t.useDepthPacking?"#define DEPTH_PACKING "+t.depthPacking:"",`
`].filter(Qa).join(`
`)),a=md(a),a=dg(a,t),a=fg(a,t),o=md(o),o=dg(o,t),o=fg(o,t),a=pg(a),o=pg(o),t.isRawShaderMaterial!==!0&&(v=`#version 300 es
`,m=[f,"#define attribute in","#define varying out","#define texture2D texture"].join(`
`)+`
`+m,g=["#define varying in",t.glslVersion===$u?"":"layout(location = 0) out highp vec4 pc_fragColor;",t.glslVersion===$u?"":"#define gl_FragColor pc_fragColor","#define gl_FragDepthEXT gl_FragDepth","#define texture2D texture","#define textureCube texture","#define texture2DProj textureProj","#define texture2DLodEXT textureLod","#define texture2DProjLodEXT textureProjLod","#define textureCubeLodEXT textureLod","#define texture2DGradEXT textureGrad","#define texture2DProjGradEXT textureProjGrad","#define textureCubeGradEXT textureGrad"].join(`
`)+`
`+g);let S=v+m+a,_=v+g+o,M=cg(r,r.VERTEX_SHADER,S),w=cg(r,r.FRAGMENT_SHADER,_);r.attachShader(y,M),r.attachShader(y,w),t.index0AttributeName!==void 0?r.bindAttribLocation(y,0,t.index0AttributeName):t.hasPositionAttribute===!0&&r.bindAttribLocation(y,0,"position"),r.linkProgram(y);function E(D){if(i.debug.checkShaderErrors){let U=r.getProgramInfoLog(y)||"",I=r.getShaderInfoLog(M)||"",L=r.getShaderInfoLog(w)||"",k=U.trim(),H=I.trim(),X=L.trim(),Y=!0,q=!0;if(r.getProgramParameter(y,r.LINK_STATUS)===!1)if(Y=!1,typeof i.debug.onShaderError=="function")i.debug.onShaderError(r,y,M,w);else{let K=ug(r,M,"vertex"),N=ug(r,w,"fragment");Fe("WebGLProgram: Shader Error "+r.getError()+" - VALIDATE_STATUS "+r.getProgramParameter(y,r.VALIDATE_STATUS)+`

Material Name: `+D.name+`
Material Type: `+D.type+`

Program Info Log: `+k+`
`+K+`
`+N)}else k!==""?Ce("WebGLProgram: Program Info Log:",k):(H===""||X==="")&&(q=!1);q&&(D.diagnostics={runnable:Y,programLog:k,vertexShader:{log:H,prefix:m},fragmentShader:{log:X,prefix:g}})}r.deleteShader(M),r.deleteShader(w),x=new zs(r,y),A=zM(r,y)}let x;this.getUniforms=function(){return x===void 0&&E(this),x};let A;this.getAttributes=function(){return A===void 0&&E(this),A};let C=t.rendererExtensionParallelShaderCompile===!1;return this.isReady=function(){return C===!1&&(C=r.getProgramParameter(y,PM)),C},this.destroy=function(){n.releaseStatesOfProgram(this),r.deleteProgram(y),this.program=void 0},this.type=t.shaderType,this.name=t.shaderName,this.id=IM++,this.cacheKey=e,this.usedTimes=1,this.program=y,this.vertexShader=M,this.fragmentShader=w,this}var iw=0,gd=class{constructor(){this.shaderCache=new Map,this.materialCache=new Map}update(e,t,n){let r=this._getShaderCacheForMaterial(e);return r.has(t)===!1&&(r.add(t),t.usedTimes++),r.has(n)===!1&&(r.add(n),n.usedTimes++),this}remove(e){let t=this.materialCache.get(e);for(let n of t)n.usedTimes--,n.usedTimes===0&&this.shaderCache.delete(n.code);return this.materialCache.delete(e),this}getVertexShaderStage(e){return this._getShaderStage(e.vertexShader)}getFragmentShaderStage(e){return this._getShaderStage(e.fragmentShader)}dispose(){this.shaderCache.clear(),this.materialCache.clear()}_getShaderCacheForMaterial(e){let t=this.materialCache,n=t.get(e);return n===void 0&&(n=new Set,t.set(e,n)),n}_getShaderStage(e){let t=this.shaderCache,n=t.get(e);return n===void 0&&(n=new yd(e),t.set(e,n)),n}},yd=class{constructor(e){this.id=iw++,this.code=e,this.usedTimes=0}};function nw(i){return i===Ln||i===qa||i===ja}function rw(i,e,t,n,r,s){let a=new _a,o=new gd,l=new Set,c=[],h=new Map,u=n.logarithmicDepthBuffer,d=n.precision,f={MeshDepthMaterial:"depth",MeshDistanceMaterial:"distance",MeshNormalMaterial:"normal",MeshBasicMaterial:"basic",MeshLambertMaterial:"lambert",MeshPhongMaterial:"phong",MeshToonMaterial:"toon",MeshStandardMaterial:"physical",MeshPhysicalMaterial:"physical",MeshMatcapMaterial:"matcap",LineBasicMaterial:"basic",LineDashedMaterial:"dashed",PointsMaterial:"points",ShadowMaterial:"shadow",SpriteMaterial:"sprite"};function p(x){return l.add(x),x===0?"uv":`uv${x}`}function y(x,A,C,D,U,I){let L=D.fog,k=U.geometry,H=x.isMeshStandardMaterial||x.isMeshLambertMaterial||x.isMeshPhongMaterial?D.environment:null,X=x.isMeshStandardMaterial||x.isMeshLambertMaterial&&!x.envMap||x.isMeshPhongMaterial&&!x.envMap,Y=e.get(x.envMap||H,X),q=Y&&Y.mapping===za?Y.image.height:null,K=f[x.type];x.precision!==null&&(d=n.getMaxPrecision(x.precision),d!==x.precision&&Ce("WebGLProgram.getParameters:",x.precision,"not supported, using",d,"instead."));let N=k.morphAttributes.position||k.morphAttributes.normal||k.morphAttributes.color,ie=N!==void 0?N.length:0,re=0;k.morphAttributes.position!==void 0&&(re=1),k.morphAttributes.normal!==void 0&&(re=2),k.morphAttributes.color!==void 0&&(re=3);let De,Te,$e,$;if(K){let yt=pi[K];De=yt.vertexShader,Te=yt.fragmentShader}else{De=x.vertexShader,Te=x.fragmentShader;let yt=o.getVertexShaderStage(x),it=o.getFragmentShaderStage(x);o.update(x,yt,it),$e=yt.id,$=it.id}let ee=i.getRenderTarget(),_e=i.state.buffers.depth.getReversed(),Be=U.isInstancedMesh===!0,xe=U.isBatchedMesh===!0,Ve=!!x.map,gt=!!x.matcap,He=!!Y,Qe=!!x.aoMap,dt=!!x.lightMap,Je=!!x.bumpMap&&x.wireframe===!1,vt=!!x.normalMap,Ht=!!x.displacementMap,_i=!!x.emissiveMap,wt=!!x.metalnessMap,Dt=!!x.roughnessMap,B=x.anisotropy>0,Qt=x.clearcoat>0,lt=x.dispersion>0,R=x.retroreflectivity>0,b=x.iridescence>0,z=x.sheen>0,W=x.transmission>0,Z=B&&!!x.anisotropyMap,se=Qt&&!!x.clearcoatMap,oe=Qt&&!!x.clearcoatNormalMap,J=Qt&&!!x.clearcoatRoughnessMap,te=b&&!!x.iridescenceMap,le=b&&!!x.iridescenceThicknessMap,Re=z&&!!x.sheenColorMap,de=z&&!!x.sheenRoughnessMap,ce=!!x.specularMap,Pe=!!x.specularColorMap,Ne=!!x.specularIntensityMap,Ge=W&&!!x.transmissionMap,F=W&&!!x.thicknessMap,he=!!x.gradientMap,Q=!!x.alphaMap,ue=x.alphaTest>0,me=!!x.alphaHash,ne=!!x.extensions,Le=Xi;x.toneMapped&&(ee===null||ee.isXRRenderTarget===!0)&&(Le=i.toneMapping);let Ee={shaderID:K,shaderType:x.type,shaderName:x.name,vertexShader:De,fragmentShader:Te,defines:x.defines,customVertexShaderID:$e,customFragmentShaderID:$,isRawShaderMaterial:x.isRawShaderMaterial===!0,glslVersion:x.glslVersion,precision:d,batching:xe,batchingColor:xe&&U._colorsTexture!==null,instancing:Be,instancingColor:Be&&U.instanceColor!==null,instancingMorph:Be&&U.morphTexture!==null,outputColorSpace:ee===null?i.outputColorSpace:ee.isXRRenderTarget===!0?ee.texture.colorSpace:je.workingColorSpace,alphaToCoverage:!!x.alphaToCoverage,map:Ve,matcap:gt,envMap:He,envMapMode:He&&Y.mapping,envMapCubeUVHeight:q,aoMap:Qe,lightMap:dt,bumpMap:Je,normalMap:vt,displacementMap:Ht,emissiveMap:_i,normalMapObjectSpace:vt&&x.normalMapType===km,normalMapTangentSpace:vt&&x.normalMapType===$a,packedNormalMap:vt&&x.normalMapType===$a&&nw(x.normalMap.format),metalnessMap:wt,roughnessMap:Dt,anisotropy:B,anisotropyMap:Z,clearcoat:Qt,clearcoatMap:se,clearcoatNormalMap:oe,clearcoatRoughnessMap:J,dispersion:lt,retroreflection:R,iridescence:b,iridescenceMap:te,iridescenceThicknessMap:le,sheen:z,sheenColorMap:Re,sheenRoughnessMap:de,specularMap:ce,specularColorMap:Pe,specularIntensityMap:Ne,transmission:W,transmissionMap:Ge,thicknessMap:F,gradientMap:he,opaque:x.transparent===!1&&x.blending===Ls&&x.alphaToCoverage===!1,alphaMap:Q,alphaTest:ue,alphaHash:me,combine:x.combine,mapUv:Ve&&p(x.map.channel),aoMapUv:Qe&&p(x.aoMap.channel),lightMapUv:dt&&p(x.lightMap.channel),bumpMapUv:Je&&p(x.bumpMap.channel),normalMapUv:vt&&p(x.normalMap.channel),displacementMapUv:Ht&&p(x.displacementMap.channel),emissiveMapUv:_i&&p(x.emissiveMap.channel),metalnessMapUv:wt&&p(x.metalnessMap.channel),roughnessMapUv:Dt&&p(x.roughnessMap.channel),anisotropyMapUv:Z&&p(x.anisotropyMap.channel),clearcoatMapUv:se&&p(x.clearcoatMap.channel),clearcoatNormalMapUv:oe&&p(x.clearcoatNormalMap.channel),clearcoatRoughnessMapUv:J&&p(x.clearcoatRoughnessMap.channel),iridescenceMapUv:te&&p(x.iridescenceMap.channel),iridescenceThicknessMapUv:le&&p(x.iridescenceThicknessMap.channel),sheenColorMapUv:Re&&p(x.sheenColorMap.channel),sheenRoughnessMapUv:de&&p(x.sheenRoughnessMap.channel),specularMapUv:ce&&p(x.specularMap.channel),specularColorMapUv:Pe&&p(x.specularColorMap.channel),specularIntensityMapUv:Ne&&p(x.specularIntensityMap.channel),transmissionMapUv:Ge&&p(x.transmissionMap.channel),thicknessMapUv:F&&p(x.thicknessMap.channel),alphaMapUv:Q&&p(x.alphaMap.channel),vertexTangents:!!k.attributes.tangent&&(vt||B),vertexNormals:!!k.attributes.normal,vertexColors:x.vertexColors,vertexAlphas:x.vertexColors===!0&&!!k.attributes.color&&k.attributes.color.itemSize===4,pointsUvs:U.isPoints===!0&&!!k.attributes.uv&&(Ve||Q),fog:!!L,useFog:x.fog===!0,fogExp2:!!L&&L.isFogExp2,flatShading:x.wireframe===!1&&(x.flatShading===!0||k.attributes.normal===void 0&&vt===!1&&(x.isMeshLambertMaterial||x.isMeshPhongMaterial||x.isMeshStandardMaterial||x.isMeshPhysicalMaterial)),sizeAttenuation:x.sizeAttenuation===!0,logarithmicDepthBuffer:u,reversedDepthBuffer:_e,skinning:U.isSkinnedMesh===!0,hasPositionAttribute:k.attributes.position!==void 0,morphTargets:k.morphAttributes.position!==void 0,morphNormals:k.morphAttributes.normal!==void 0,morphColors:k.morphAttributes.color!==void 0,morphTargetsCount:ie,morphTextureStride:re,numSunLights:A.sun.length,numDirLights:A.directional.length,numPointLights:A.point.length,numSpotLights:A.spot.length,numSpotLightMaps:A.spotLightMap.length,numRectAreaLights:A.rectArea.length,numHemiLights:A.hemi.length,numSunLightShadows:A.sunShadowMap.length,numDirLightShadows:A.directionalShadowMap.length,numPointLightShadows:A.pointShadowMap.length,numSpotLightShadows:A.spotShadowMap.length,numSpotLightShadowsWithMaps:A.numSpotLightShadowsWithMaps,numLightProbes:A.numLightProbes,numLightProbeGrids:I.length,numClippingPlanes:s.numPlanes,numClipIntersection:s.numIntersection,dithering:x.dithering,shadowMapEnabled:i.shadowMap.enabled&&C.length>0,shadowMapType:i.shadowMap.type,toneMapping:Le,decodeVideoTexture:Ve&&x.map.isVideoTexture===!0&&je.getTransfer(x.map.colorSpace)===rt,decodeVideoTextureEmissive:_i&&x.emissiveMap.isVideoTexture===!0&&je.getTransfer(x.emissiveMap.colorSpace)===rt,premultipliedAlpha:x.premultipliedAlpha,doubleSided:x.side===ri,flipSided:x.side===ui,useDepthPacking:x.depthPacking>=0,depthPacking:x.depthPacking||0,index0AttributeName:x.index0AttributeName,extensionClipCullDistance:ne&&x.extensions.clipCullDistance===!0&&t.has("WEBGL_clip_cull_distance"),extensionMultiDraw:(ne&&x.extensions.multiDraw===!0||xe)&&t.has("WEBGL_multi_draw"),rendererExtensionParallelShaderCompile:t.has("KHR_parallel_shader_compile"),customProgramCacheKey:x.customProgramCacheKey()};return Ee.vertexUv1s=l.has(1),Ee.vertexUv2s=l.has(2),Ee.vertexUv3s=l.has(3),l.clear(),Ee}function m(x){let A=[];if(x.shaderID?A.push(x.shaderID):(A.push(x.customVertexShaderID),A.push(x.customFragmentShaderID)),x.defines!==void 0)for(let C in x.defines)A.push(C),A.push(x.defines[C]);return x.isRawShaderMaterial===!1&&(g(A,x),v(A,x),A.push(i.outputColorSpace)),A.push(x.customProgramCacheKey),A.join()}function g(x,A){x.push(A.precision),x.push(A.outputColorSpace),x.push(A.envMapMode),x.push(A.envMapCubeUVHeight),x.push(A.mapUv),x.push(A.alphaMapUv),x.push(A.lightMapUv),x.push(A.aoMapUv),x.push(A.bumpMapUv),x.push(A.normalMapUv),x.push(A.displacementMapUv),x.push(A.emissiveMapUv),x.push(A.metalnessMapUv),x.push(A.roughnessMapUv),x.push(A.anisotropyMapUv),x.push(A.clearcoatMapUv),x.push(A.clearcoatNormalMapUv),x.push(A.clearcoatRoughnessMapUv),x.push(A.iridescenceMapUv),x.push(A.iridescenceThicknessMapUv),x.push(A.sheenColorMapUv),x.push(A.sheenRoughnessMapUv),x.push(A.specularMapUv),x.push(A.specularColorMapUv),x.push(A.specularIntensityMapUv),x.push(A.transmissionMapUv),x.push(A.thicknessMapUv),x.push(A.combine),x.push(A.fogExp2),x.push(A.sizeAttenuation),x.push(A.morphTargetsCount),x.push(A.morphAttributeCount),x.push(A.numSunLights),x.push(A.numDirLights),x.push(A.numPointLights),x.push(A.numSpotLights),x.push(A.numSpotLightMaps),x.push(A.numHemiLights),x.push(A.numRectAreaLights),x.push(A.numSunLightShadows),x.push(A.numDirLightShadows),x.push(A.numPointLightShadows),x.push(A.numSpotLightShadows),x.push(A.numSpotLightShadowsWithMaps),x.push(A.numLightProbes),x.push(A.shadowMapType),x.push(A.toneMapping),x.push(A.numClippingPlanes),x.push(A.numClipIntersection),x.push(A.depthPacking)}function v(x,A){a.disableAll(),A.instancing&&a.enable(0),A.instancingColor&&a.enable(1),A.instancingMorph&&a.enable(2),A.matcap&&a.enable(3),A.envMap&&a.enable(4),A.normalMapObjectSpace&&a.enable(5),A.normalMapTangentSpace&&a.enable(6),A.clearcoat&&a.enable(7),A.iridescence&&a.enable(8),A.alphaTest&&a.enable(9),A.vertexColors&&a.enable(10),A.vertexAlphas&&a.enable(11),A.vertexUv1s&&a.enable(12),A.vertexUv2s&&a.enable(13),A.vertexUv3s&&a.enable(14),A.vertexTangents&&a.enable(15),A.anisotropy&&a.enable(16),A.alphaHash&&a.enable(17),A.batching&&a.enable(18),A.dispersion&&a.enable(19),A.retroreflection&&a.enable(24),A.batchingColor&&a.enable(20),A.gradientMap&&a.enable(21),A.packedNormalMap&&a.enable(22),A.vertexNormals&&a.enable(23),x.push(a.mask),a.disableAll(),A.fog&&a.enable(0),A.useFog&&a.enable(1),A.flatShading&&a.enable(2),A.logarithmicDepthBuffer&&a.enable(3),A.reversedDepthBuffer&&a.enable(4),A.skinning&&a.enable(5),A.morphTargets&&a.enable(6),A.morphNormals&&a.enable(7),A.morphColors&&a.enable(8),A.premultipliedAlpha&&a.enable(9),A.shadowMapEnabled&&a.enable(10),A.doubleSided&&a.enable(11),A.flipSided&&a.enable(12),A.useDepthPacking&&a.enable(13),A.dithering&&a.enable(14),A.transmission&&a.enable(15),A.sheen&&a.enable(16),A.opaque&&a.enable(17),A.pointsUvs&&a.enable(18),A.decodeVideoTexture&&a.enable(19),A.decodeVideoTextureEmissive&&a.enable(20),A.alphaToCoverage&&a.enable(21),A.numLightProbeGrids>0&&a.enable(22),A.hasPositionAttribute&&a.enable(23),x.push(a.mask)}function S(x){let A=f[x.type],C;if(A){let D=pi[A];C=Za.clone(D.uniforms)}else C=x.uniforms;return C}function _(x,A){let C=h.get(A);return C!==void 0?++C.usedTimes:(C=new tw(i,A,x,r),c.push(C),h.set(A,C)),C}function M(x){if(--x.usedTimes===0){let A=c.indexOf(x);c[A]=c[c.length-1],c.pop(),h.delete(x.cacheKey),x.destroy()}}function w(x){o.remove(x)}function E(){o.dispose()}return{getParameters:y,getProgramCacheKey:m,getUniforms:S,acquireProgram:_,releaseProgram:M,releaseShaderCache:w,programs:c,dispose:E}}function sw(){let i=new WeakMap;function e(a){return i.has(a)}function t(a){let o=i.get(a);return o===void 0&&(o={},i.set(a,o)),o}function n(a){i.delete(a)}function r(a,o,l){i.get(a)[o]=l}function s(){i=new WeakMap}return{has:e,get:t,remove:n,update:r,dispose:s}}function aw(i,e){return i.groupOrder!==e.groupOrder?i.groupOrder-e.groupOrder:i.renderOrder!==e.renderOrder?i.renderOrder-e.renderOrder:i.material.id!==e.material.id?i.material.id-e.material.id:i.materialVariant!==e.materialVariant?i.materialVariant-e.materialVariant:i.z!==e.z?i.z-e.z:i.id-e.id}function gg(i,e){return i.groupOrder!==e.groupOrder?i.groupOrder-e.groupOrder:i.renderOrder!==e.renderOrder?i.renderOrder-e.renderOrder:i.z!==e.z?e.z-i.z:i.id-e.id}function yg(){let i=[],e=0,t=[],n=[],r=[];function s(){e=0,t.length=0,n.length=0,r.length=0}function a(d){let f=0;return d.isInstancedMesh&&(f+=2),d.isSkinnedMesh&&(f+=1),f}function o(d,f,p,y,m,g){let v=i[e];return v===void 0?(v={id:d.id,object:d,geometry:f,material:p,materialVariant:a(d),groupOrder:y,renderOrder:d.renderOrder,z:m,group:g},i[e]=v):(v.id=d.id,v.object=d,v.geometry=f,v.material=p,v.materialVariant=a(d),v.groupOrder=y,v.renderOrder=d.renderOrder,v.z=m,v.group=g),e++,v}function l(d,f,p,y,m,g,v){v.reversedDepth===!0&&(m=-m);let S=o(d,f,p,y,m,g);p.transmission>0?n.push(S):p.transparent===!0?r.push(S):t.push(S)}function c(d,f,p,y,m,g){let v=o(d,f,p,y,m,g);p.transmission>0?n.unshift(v):p.transparent===!0?r.unshift(v):t.unshift(v)}function h(d,f){t.length>1&&t.sort(d||aw),n.length>1&&n.sort(f||gg),r.length>1&&r.sort(f||gg)}function u(){for(let d=e,f=i.length;d<f;d++){let p=i[d];if(p.id===null)break;p.id=null,p.object=null,p.geometry=null,p.material=null,p.group=null}}return{opaque:t,transmissive:n,transparent:r,init:s,push:l,unshift:c,finish:u,sort:h}}function ow(){let i=new WeakMap;function e(n,r){let s=i.get(n),a;return s===void 0?(a=new yg,i.set(n,[a])):r>=s.length?(a=new yg,s.push(a)):a=s[r],a}function t(){i=new WeakMap}return{get:e,dispose:t}}function lw(){let i={};return{get:function(e){if(i[e.id]!==void 0)return i[e.id];let t;switch(e.type){case"SunLight":case"DirectionalLight":t={direction:new P,color:new Ie};break;case"SpotLight":t={position:new P,direction:new P,color:new Ie,distance:0,coneCos:0,penumbraCos:0,decay:0};break;case"PointLight":t={position:new P,color:new Ie,distance:0,decay:0};break;case"HemisphereLight":t={direction:new P,skyColor:new Ie,groundColor:new Ie};break;case"RectAreaLight":t={color:new Ie,position:new P,halfWidth:new P,halfHeight:new P};break}return i[e.id]=t,t}}}function cw(){let i={};return{get:function(e){if(i[e.id]!==void 0)return i[e.id];let t;switch(e.type){case"SunLight":case"DirectionalLight":t={shadowIntensity:1,shadowBias:0,shadowNormalBias:0,shadowRadius:1,shadowMapSize:new Se};break;case"SpotLight":t={shadowIntensity:1,shadowBias:0,shadowNormalBias:0,shadowRadius:1,shadowMapSize:new Se};break;case"PointLight":t={shadowIntensity:1,shadowBias:0,shadowNormalBias:0,shadowRadius:1,shadowMapSize:new Se,shadowCameraNear:1,shadowCameraFar:1e3};break}return i[e.id]=t,t}}}var hw=0;function uw(i,e){return(e.castShadow?2:0)-(i.castShadow?2:0)+(e.map?1:0)-(i.map?1:0)}function dw(i){let e=new lw,t=cw(),n={version:0,hash:{sunLength:-1,directionalLength:-1,pointLength:-1,spotLength:-1,rectAreaLength:-1,hemiLength:-1,numSunShadows:-1,numDirectionalShadows:-1,numPointShadows:-1,numSpotShadows:-1,numSpotMaps:-1,numLightProbes:-1},ambient:[0,0,0],probe:[],sun:[],sunShadow:[],sunShadowMap:[],sunShadowMatrix:[],sunShadowCascade:[],directional:[],directionalShadow:[],directionalShadowMap:[],directionalShadowMatrix:[],spot:[],spotLightMap:[],spotShadow:[],spotShadowMap:[],spotLightMatrix:[],rectArea:[],rectAreaLTC1:null,rectAreaLTC2:null,point:[],pointShadow:[],pointShadowMap:[],pointShadowMatrix:[],hemi:[],numSpotLightShadowsWithMaps:0,numLightProbes:0};for(let c=0;c<9;c++)n.probe.push(new P);let r=new P,s=new ge,a=new ge;function o(c){let h=0,u=0,d=0;for(let U=0;U<9;U++)n.probe[U].set(0,0,0);let f=0,p=0,y=0,m=0,g=0,v=0,S=0,_=0,M=0,w=0,E=0,x=0,A=0,C=0;c.sort(uw);for(let U=0,I=c.length;U<I;U++){let L=c[U],k=L.color,H=L.intensity,X=L.distance,Y=null;if(L.shadow&&L.shadow.map&&(L.shadow.map.texture.format===Ln?Y=L.shadow.map.texture:Y=L.shadow.map.depthTexture||L.shadow.map.texture),L.isAmbientLight)h+=k.r*H,u+=k.g*H,d+=k.b*H;else if(L.isLightProbe){for(let q=0;q<9;q++)n.probe[q].addScaledVector(L.sh.coefficients[q],H);C++}else if(L.isSunLight){let q=e.get(L);if(q.color.copy(L.color).multiplyScalar(L.intensity),L.castShadow){let K=L.shadow,N=t.get(L);N.shadowIntensity=K.intensity,N.shadowBias=K.bias,N.shadowNormalBias=K.normalBias,N.shadowRadius=K.radius,N.shadowMapSize.copy(K.mapSize).multiply(K.getFrameExtents()),n.sunShadow[p]=N,n.sunShadowMap[p]=Y;let ie=K.getViewportCount();for(let re=0;re<ie;re++)n.sunShadowMatrix[y+re]=K.getMatrix(re),n.sunShadowCascade[y+re]=K._cascadeData[re];y+=ie,p++}n.sun[f]=q,f++}else if(L.isDirectionalLight){let q=e.get(L);if(q.color.copy(L.color).multiplyScalar(L.intensity),L.castShadow){let K=L.shadow,N=t.get(L);N.shadowIntensity=K.intensity,N.shadowBias=K.bias,N.shadowNormalBias=K.normalBias,N.shadowRadius=K.radius,N.shadowMapSize=K.mapSize,n.directionalShadow[m]=N,n.directionalShadowMap[m]=Y,n.directionalShadowMatrix[m]=L.shadow.matrix,M++}n.directional[m]=q,m++}else if(L.isSpotLight){let q=e.get(L);q.position.setFromMatrixPosition(L.matrixWorld),q.color.copy(k).multiplyScalar(H),q.distance=X,q.coneCos=Math.cos(L.angle),q.penumbraCos=Math.cos(L.angle*(1-L.penumbra)),q.decay=L.decay,n.spot[v]=q;let K=L.shadow;if(L.map&&(n.spotLightMap[x]=L.map,x++,K.updateMatrices(L),L.castShadow&&A++),n.spotLightMatrix[v]=K.matrix,L.castShadow){let N=t.get(L);N.shadowIntensity=K.intensity,N.shadowBias=K.bias,N.shadowNormalBias=K.normalBias,N.shadowRadius=K.radius,N.shadowMapSize=K.mapSize,n.spotShadow[v]=N,n.spotShadowMap[v]=Y,E++}v++}else if(L.isRectAreaLight){let q=e.get(L);q.color.copy(k).multiplyScalar(H),q.halfWidth.set(L.width*.5,0,0),q.halfHeight.set(0,L.height*.5,0),n.rectArea[S]=q,S++}else if(L.isPointLight){let q=e.get(L);if(q.color.copy(L.color).multiplyScalar(L.intensity),q.distance=L.distance,q.decay=L.decay,L.castShadow){let K=L.shadow,N=t.get(L);N.shadowIntensity=K.intensity,N.shadowBias=K.bias,N.shadowNormalBias=K.normalBias,N.shadowRadius=K.radius,N.shadowMapSize=K.mapSize,N.shadowCameraNear=K.camera.near,N.shadowCameraFar=K.camera.far,n.pointShadow[g]=N,n.pointShadowMap[g]=Y,n.pointShadowMatrix[g]=L.shadow.matrix,w++}n.point[g]=q,g++}else if(L.isHemisphereLight){let q=e.get(L);q.skyColor.copy(L.color).multiplyScalar(H),q.groundColor.copy(L.groundColor).multiplyScalar(H),n.hemi[_]=q,_++}}S>0&&(i.has("OES_texture_float_linear")===!0?(n.rectAreaLTC1=ae.LTC_FLOAT_1,n.rectAreaLTC2=ae.LTC_FLOAT_2):(n.rectAreaLTC1=ae.LTC_HALF_1,n.rectAreaLTC2=ae.LTC_HALF_2)),n.ambient[0]=h,n.ambient[1]=u,n.ambient[2]=d;let D=n.hash;(D.sunLength!==f||D.directionalLength!==m||D.pointLength!==g||D.spotLength!==v||D.rectAreaLength!==S||D.hemiLength!==_||D.numSunShadows!==p||D.numDirectionalShadows!==M||D.numPointShadows!==w||D.numSpotShadows!==E||D.numSpotMaps!==x||D.numLightProbes!==C)&&(n.sun.length=f,n.directional.length=m,n.spot.length=v,n.rectArea.length=S,n.point.length=g,n.hemi.length=_,n.sunShadow.length=p,n.sunShadowMap.length=p,n.sunShadowMatrix.length=y,n.sunShadowCascade.length=y,n.directionalShadow.length=M,n.directionalShadowMap.length=M,n.directionalShadowMatrix.length=M,n.pointShadow.length=w,n.pointShadowMap.length=w,n.pointShadowMatrix.length=w,n.spotShadow.length=E,n.spotShadowMap.length=E,n.spotLightMatrix.length=E+x-A,n.spotLightMap.length=x,n.numSpotLightShadowsWithMaps=A,n.numLightProbes=C,D.sunLength=f,D.directionalLength=m,D.pointLength=g,D.spotLength=v,D.rectAreaLength=S,D.hemiLength=_,D.numSunShadows=p,D.numDirectionalShadows=M,D.numPointShadows=w,D.numSpotShadows=E,D.numSpotMaps=x,D.numLightProbes=C,n.version=hw++)}function l(c,h){let u=0,d=0,f=0,p=0,y=0,m=0,g=h.matrixWorldInverse;for(let v=0,S=c.length;v<S;v++){let _=c[v];if(_.isSunLight){let M=n.sun[u];M.direction.setFromMatrixPosition(_.matrixWorld),M.direction.transformDirection(g),u++}else if(_.isDirectionalLight){let M=n.directional[d];M.direction.setFromMatrixPosition(_.matrixWorld),r.setFromMatrixPosition(_.target.matrixWorld),M.direction.sub(r),M.direction.transformDirection(g),d++}else if(_.isSpotLight){let M=n.spot[p];M.position.setFromMatrixPosition(_.matrixWorld),M.position.applyMatrix4(g),M.direction.setFromMatrixPosition(_.matrixWorld),r.setFromMatrixPosition(_.target.matrixWorld),M.direction.sub(r),M.direction.transformDirection(g),p++}else if(_.isRectAreaLight){let M=n.rectArea[y];M.position.setFromMatrixPosition(_.matrixWorld),M.position.applyMatrix4(g),a.identity(),s.copy(_.matrixWorld),s.premultiply(g),a.extractRotation(s),M.halfWidth.set(_.width*.5,0,0),M.halfHeight.set(0,_.height*.5,0),M.halfWidth.applyMatrix4(a),M.halfHeight.applyMatrix4(a),y++}else if(_.isPointLight){let M=n.point[f];M.position.setFromMatrixPosition(_.matrixWorld),M.position.applyMatrix4(g),f++}else if(_.isHemisphereLight){let M=n.hemi[m];M.direction.setFromMatrixPosition(_.matrixWorld),M.direction.transformDirection(g),m++}}}return{setup:o,setupView:l,state:n}}function _g(i){let e=new dw(i),t=[],n=[],r=[];function s(d){u.camera=d,t.length=0,n.length=0,r.length=0}function a(d){t.push(d)}function o(d){n.push(d)}function l(d){r.push(d)}function c(){e.setup(t)}function h(d){e.setupView(t,d)}let u={lightsArray:t,shadowsArray:n,lightProbeGridArray:r,camera:null,lights:e,transmissionRenderTarget:{},textureUnits:0};return{init:s,state:u,setupLights:c,setupLightsView:h,pushLight:a,pushShadow:o,pushLightProbeGrid:l}}function fw(i){let e=new WeakMap;function t(r,s=0){let a=e.get(r),o;return a===void 0?(o=new _g(i),e.set(r,[o])):s>=a.length?(o=new _g(i),a.push(o)):o=a[s],o}function n(){e=new WeakMap}return{get:t,dispose:n}}var pw=`void main() {
	gl_Position = vec4( position, 1.0 );
}`,mw=`uniform sampler2D shadow_pass;
uniform vec2 resolution;
uniform float radius;
void main() {
	const float samples = float( VSM_SAMPLES );
	float mean = 0.0;
	float squared_mean = 0.0;
	float uvStride = samples <= 1.0 ? 0.0 : 2.0 / ( samples - 1.0 );
	float uvStart = samples <= 1.0 ? 0.0 : - 1.0;
	for ( float i = 0.0; i < samples; i ++ ) {
		float uvOffset = uvStart + i * uvStride;
		#ifdef HORIZONTAL_PASS
			vec2 distribution = texture2D( shadow_pass, ( gl_FragCoord.xy + vec2( uvOffset, 0.0 ) * radius ) / resolution ).rg;
			mean += distribution.x;
			squared_mean += distribution.y * distribution.y + distribution.x * distribution.x;
		#else
			float depth = texture2D( shadow_pass, ( gl_FragCoord.xy + vec2( 0.0, uvOffset ) * radius ) / resolution ).r;
			mean += depth;
			squared_mean += depth * depth;
		#endif
	}
	mean = mean / samples;
	squared_mean = squared_mean / samples;
	float std_dev = sqrt( max( 0.0, squared_mean - mean * mean ) );
	gl_FragColor = vec4( mean, std_dev, 0.0, 1.0 );
}`,gw=[new P(1,0,0),new P(-1,0,0),new P(0,1,0),new P(0,-1,0),new P(0,0,1),new P(0,0,-1)],yw=[new P(0,-1,0),new P(0,-1,0),new P(0,0,1),new P(0,0,-1),new P(0,-1,0),new P(0,-1,0)],xg=new ge,Ja=new P,hd=new P;function _w(i,e,t){let n=new wn,r=new Se,s=new Se,a=new Xe,o=new El,l=new Al,c={},h=t.maxTextureSize,u={[sn]:ui,[ui]:sn,[ri]:ri},d=new $t({defines:{VSM_SAMPLES:8},uniforms:{shadow_pass:{value:null},resolution:{value:new Se},radius:{value:4}},vertexShader:pw,fragmentShader:mw}),f=d.clone();f.defines.HORIZONTAL_PASS=1;let p=new ht;p.setAttribute("position",new Ye(new Float32Array([-1,-1,.5,3,-1,.5,-1,3,.5]),3));let y=new at(p,d),m=this;this.enabled=!1,this.autoUpdate=!0,this.needsUpdate=!1,this.type=ka;let g=this.type;this.render=function(w,E,x){if(m.enabled===!1||m.autoUpdate===!1&&m.needsUpdate===!1||w.length===0)return;this.type===_m&&(Ce("WebGLShadowMap: PCFSoftShadowMap has been removed. Using PCFShadowMap instead."),this.type=ka);let A=i.getRenderTarget(),C=i.getActiveCubeFace(),D=i.getActiveMipmapLevel(),U=i.state;U.setBlending(an),U.buffers.depth.getReversed()===!0?U.buffers.color.setClear(0,0,0,0):U.buffers.color.setClear(1,1,1,1),U.buffers.depth.setTest(!0),U.setScissorTest(!1);let I=g!==this.type;I&&E.traverse(function(L){L.material&&(Array.isArray(L.material)?L.material.forEach(k=>k.needsUpdate=!0):L.material.needsUpdate=!0)});for(let L=0,k=w.length;L<k;L++){let H=w[L],X=H.shadow;if(X===void 0){Ce("WebGLShadowMap:",H,"has no shadow.");continue}if(X.autoUpdate===!1&&X.needsUpdate===!1)continue;r.copy(X.mapSize);let Y=X.getFrameExtents();r.multiply(Y),s.copy(X.mapSize),(r.x>h||r.y>h)&&(r.x>h&&(s.x=Math.floor(h/Y.x),r.x=s.x*Y.x,X.mapSize.x=s.x),r.y>h&&(s.y=Math.floor(h/Y.y),r.y=s.y*Y.y,X.mapSize.y=s.y));let q=i.state.buffers.depth.getReversed();if(X.camera._reversedDepth=q,X.map===null||I===!0){if(X.map!==null&&(X.map.depthTexture!==null&&(X.map.depthTexture.dispose(),X.map.depthTexture=null),X.map.dispose()),this.type===Is){if(H.isPointLight){Ce("WebGLShadowMap: VSM shadow maps are not supported for PointLights. Use PCF or BasicShadowMap instead.");continue}X.map=new ci(r.x,r.y,{format:Ln,type:ji,minFilter:St,magFilter:St,generateMipmaps:!1}),X.map.texture.name=H.name+".shadowMap",X.map.depthTexture=new Jn(r.x,r.y,fi),X.map.depthTexture.name=H.name+".shadowMapDepth",X.map.depthTexture.format=tn,X.map.depthTexture.compareFunction=null,X.map.depthTexture.minFilter=At,X.map.depthTexture.magFilter=At}else H.isPointLight?(X.map=new Rc(r.x),X.map.depthTexture=new wl(r.x,qi)):(X.map=new ci(r.x,r.y),X.map.depthTexture=new Jn(r.x,r.y,qi)),X.map.depthTexture.name=H.name+".shadowMap",X.map.depthTexture.format=tn,this.type===ka?(X.map.depthTexture.compareFunction=q?wc:Mc,X.map.depthTexture.minFilter=St,X.map.depthTexture.magFilter=St):(X.map.depthTexture.compareFunction=null,X.map.depthTexture.minFilter=At,X.map.depthTexture.magFilter=At);X.camera.updateProjectionMatrix()}X.map.isWebGLCubeRenderTarget!==!0&&(X.map.width!==r.x||X.map.height!==r.y)&&X.map.setSize(r.x,r.y);let K=X.map.isWebGLCubeRenderTarget?6:X.getViewportCount();H.isPointLight!==!0&&X.updateMatrices(H,x);for(let N=0;N<K;N++){let ie=X.getCamera(N);if(H.isPointLight){let re=X.camera,De=X.matrix,Te=H.distance||re.far;Te!==re.far&&(re.far=Te,re.updateProjectionMatrix()),Ja.setFromMatrixPosition(H.matrixWorld),re.position.copy(Ja),hd.copy(re.position),hd.add(gw[N]),re.up.copy(yw[N]),re.lookAt(hd),re.updateMatrixWorld(),De.makeTranslation(-Ja.x,-Ja.y,-Ja.z),xg.multiplyMatrices(re.projectionMatrix,re.matrixWorldInverse),X._frustum.setFromProjectionMatrix(xg,re.coordinateSystem,re.reversedDepth)}if(X.map.isWebGLCubeRenderTarget)i.setRenderTarget(X.map,N),i.clear();else{N===0&&(i.setRenderTarget(X.map),i.clear());let re=X.getViewport(N);a.set(s.x*re.x,s.y*re.y,s.x*re.z,s.y*re.w),U.viewport(a)}n=X.getFrustum(N),_(E,x,ie,H,this.type)}X.isPointLightShadow!==!0&&this.type===Is&&v(X,x),X.needsUpdate=!1}g=this.type,m.needsUpdate=!1,i.setRenderTarget(A,C,D)};function v(w,E){let x=e.update(y);d.defines.VSM_SAMPLES!==w.blurSamples&&(d.defines.VSM_SAMPLES=w.blurSamples,f.defines.VSM_SAMPLES=w.blurSamples,d.needsUpdate=!0,f.needsUpdate=!0),w.mapPass===null?w.mapPass=new ci(r.x,r.y,{format:Ln,type:ji}):(w.mapPass.width!==w.map.width||w.mapPass.height!==w.map.height)&&w.mapPass.setSize(w.map.width,w.map.height),d.uniforms.shadow_pass.value=w.map.depthTexture,d.uniforms.resolution.value.set(w.map.width,w.map.height),d.uniforms.radius.value=w.radius,i.setRenderTarget(w.mapPass),i.clear(),i.renderBufferDirect(E,null,x,d,y,null),f.uniforms.shadow_pass.value=w.mapPass.texture,f.uniforms.resolution.value.set(w.map.width,w.map.height),f.uniforms.radius.value=w.radius,i.setRenderTarget(w.map),i.clear(),i.renderBufferDirect(E,null,x,f,y,null)}function S(w,E,x,A){let C=null,D=x.isPointLight===!0?w.customDistanceMaterial:w.customDepthMaterial;if(D!==void 0)C=D;else if(C=x.isPointLight===!0?l:o,i.localClippingEnabled&&E.clipShadows===!0&&Array.isArray(E.clippingPlanes)&&E.clippingPlanes.length!==0||E.displacementMap&&E.displacementScale!==0||E.alphaMap&&E.alphaTest>0||E.map&&E.alphaTest>0||E.alphaToCoverage===!0){let U=C.uuid,I=E.uuid,L=c[U];L===void 0&&(L={},c[U]=L);let k=L[I];k===void 0&&(k=C.clone(),L[I]=k,E.addEventListener("dispose",M)),C=k}if(C.visible=E.visible,C.wireframe=E.wireframe,A===Is?C.side=E.shadowSide!==null?E.shadowSide:E.side:C.side=E.shadowSide!==null?E.shadowSide:u[E.side],C.alphaMap=E.alphaMap,C.alphaTest=E.alphaToCoverage===!0?.5:E.alphaTest,C.map=E.map,C.clipShadows=E.clipShadows,C.clippingPlanes=E.clippingPlanes,C.clipIntersection=E.clipIntersection,C.displacementMap=E.displacementMap,C.displacementScale=E.displacementScale,C.displacementBias=E.displacementBias,C.wireframeLinewidth=E.wireframeLinewidth,C.linewidth=E.linewidth,x.isPointLight===!0&&C.isMeshDistanceMaterial===!0){let U=i.properties.get(C);U.light=x}return C}function _(w,E,x,A,C){if(w.visible===!1)return;if(w.layers.test(E.layers)&&(w.isMesh||w.isLine||w.isPoints)&&(w.castShadow||w.receiveShadow&&C===Is)&&(!w.frustumCulled||w.intersectsFrustum(n))){w.modelViewMatrix.multiplyMatrices(x.matrixWorldInverse,w.matrixWorld);let I=e.update(w),L=w.material;if(Array.isArray(L)){let k=I.groups;for(let H=0,X=k.length;H<X;H++){let Y=k[H],q=L[Y.materialIndex];if(q&&q.visible){let K=S(w,q,A,C);w.onBeforeShadow(i,w,E,x,I,K,Y),i.renderBufferDirect(x,null,I,K,w,Y),w.onAfterShadow(i,w,E,x,I,K,Y)}}}else if(L.visible){let k=S(w,L,A,C);w.onBeforeShadow(i,w,E,x,I,k,null),i.renderBufferDirect(x,null,I,k,w,null),w.onAfterShadow(i,w,E,x,I,k,null)}}let U=w.children;for(let I=0,L=U.length;I<L;I++)_(U[I],E,x,A,C)}function M(w){w.target.removeEventListener("dispose",M);for(let x in c){let A=c[x],C=w.target.uuid;C in A&&(A[C].dispose(),delete A[C])}}}function xw(i,e){function t(){let F=!1,he=new Xe,Q=null,ue=new Xe(0,0,0,0);return{setMask:function(me){Q!==me&&!F&&(i.colorMask(me,me,me,me),Q=me)},setLocked:function(me){F=me},setClear:function(me,ne,Le,Ee,yt){yt===!0&&(me*=Ee,ne*=Ee,Le*=Ee),he.set(me,ne,Le,Ee),ue.equals(he)===!1&&(i.clearColor(me,ne,Le,Ee),ue.copy(he))},reset:function(){F=!1,Q=null,ue.set(-1,0,0,0)}}}function n(){let F=!1,he=!1,Q=null,ue=null,me=null;return{setReversed:function(ne){if(he!==ne){let Le=e.get("EXT_clip_control");ne?Le.clipControlEXT(Le.LOWER_LEFT_EXT,Le.ZERO_TO_ONE_EXT):Le.clipControlEXT(Le.LOWER_LEFT_EXT,Le.NEGATIVE_ONE_TO_ONE_EXT),he=ne;let Ee=me;me=null,this.setClear(Ee)}},getReversed:function(){return he},setTest:function(ne){ne?ee(i.DEPTH_TEST):_e(i.DEPTH_TEST)},setMask:function(ne){Q!==ne&&!F&&(i.depthMask(ne),Q=ne)},setFunc:function(ne){if(he&&(ne=Zm[ne]),ue!==ne){switch(ne){case fl:i.depthFunc(i.NEVER);break;case pl:i.depthFunc(i.ALWAYS);break;case ml:i.depthFunc(i.LESS);break;case xs:i.depthFunc(i.LEQUAL);break;case gl:i.depthFunc(i.EQUAL);break;case yl:i.depthFunc(i.GEQUAL);break;case pa:i.depthFunc(i.GREATER);break;case _l:i.depthFunc(i.NOTEQUAL);break;default:i.depthFunc(i.LEQUAL)}ue=ne}},setLocked:function(ne){F=ne},setClear:function(ne){me!==ne&&(me=ne,he&&(ne=1-ne),i.clearDepth(ne))},reset:function(){F=!1,Q=null,ue=null,me=null,he=!1}}}function r(){let F=!1,he=null,Q=null,ue=null,me=null,ne=null,Le=null,Ee=null,yt=null;return{setTest:function(it){F||(it?ee(i.STENCIL_TEST):_e(i.STENCIL_TEST))},setMask:function(it){he!==it&&!F&&(i.stencilMask(it),he=it)},setFunc:function(it,Oi,Zi){(Q!==it||ue!==Oi||me!==Zi)&&(i.stencilFunc(it,Oi,Zi),Q=it,ue=Oi,me=Zi)},setOp:function(it,Oi,Zi){(ne!==it||Le!==Oi||Ee!==Zi)&&(i.stencilOp(it,Oi,Zi),ne=it,Le=Oi,Ee=Zi)},setLocked:function(it){F=it},setClear:function(it){yt!==it&&(i.clearStencil(it),yt=it)},reset:function(){F=!1,he=null,Q=null,ue=null,me=null,ne=null,Le=null,Ee=null,yt=null}}}let s=new t,a=new n,o=new r,l=new WeakMap,c=new WeakMap,h={},u={},d={},f=new WeakMap,p=[],y=null,m=!1,g=null,v=null,S=null,_=null,M=null,w=null,E=null,x=new Ie(0,0,0),A=0,C=!1,D=null,U=null,I=null,L=null,k=null,H=i.getParameter(i.MAX_COMBINED_TEXTURE_IMAGE_UNITS),X=!1,Y=0,q=i.getParameter(i.VERSION);q.indexOf("WebGL")!==-1?(Y=parseFloat(/^WebGL (\d)/.exec(q)[1]),X=Y>=1):q.indexOf("OpenGL ES")!==-1&&(Y=parseFloat(/^OpenGL ES (\d)/.exec(q)[1]),X=Y>=2);let K=null,N={},ie=i.getParameter(i.SCISSOR_BOX),re=i.getParameter(i.VIEWPORT),De=new Xe().fromArray(ie),Te=new Xe().fromArray(re);function $e(F,he,Q,ue){let me=new Uint8Array(4),ne=i.createTexture();i.bindTexture(F,ne),i.texParameteri(F,i.TEXTURE_MIN_FILTER,i.NEAREST),i.texParameteri(F,i.TEXTURE_MAG_FILTER,i.NEAREST);for(let Le=0;Le<Q;Le++)F===i.TEXTURE_3D||F===i.TEXTURE_2D_ARRAY?i.texImage3D(he,0,i.RGBA,1,1,ue,0,i.RGBA,i.UNSIGNED_BYTE,me):i.texImage2D(he+Le,0,i.RGBA,1,1,0,i.RGBA,i.UNSIGNED_BYTE,me);return ne}let $={};$[i.TEXTURE_2D]=$e(i.TEXTURE_2D,i.TEXTURE_2D,1),$[i.TEXTURE_CUBE_MAP]=$e(i.TEXTURE_CUBE_MAP,i.TEXTURE_CUBE_MAP_POSITIVE_X,6),$[i.TEXTURE_2D_ARRAY]=$e(i.TEXTURE_2D_ARRAY,i.TEXTURE_2D_ARRAY,1,1),$[i.TEXTURE_3D]=$e(i.TEXTURE_3D,i.TEXTURE_3D,1,1),s.setClear(0,0,0,1),a.setClear(1),o.setClear(0),ee(i.DEPTH_TEST),a.setFunc(xs),Je(!1),vt(wu),ee(i.CULL_FACE),Qe(an);function ee(F){h[F]!==!0&&(i.enable(F),h[F]=!0)}function _e(F){h[F]!==!1&&(i.disable(F),h[F]=!1)}function Be(F,he){return d[F]!==he?(i.bindFramebuffer(F,he),d[F]=he,F===i.DRAW_FRAMEBUFFER&&(d[i.FRAMEBUFFER]=he),F===i.FRAMEBUFFER&&(d[i.DRAW_FRAMEBUFFER]=he),!0):!1}function xe(F,he){let Q=p,ue=!1;if(F){Q=f.get(he),Q===void 0&&(Q=[],f.set(he,Q));let me=F.textures;if(Q.length!==me.length||Q[0]!==i.COLOR_ATTACHMENT0){for(let ne=0,Le=me.length;ne<Le;ne++)Q[ne]=i.COLOR_ATTACHMENT0+ne;Q.length=me.length,ue=!0}}else Q[0]!==i.BACK&&(Q[0]=i.BACK,ue=!0);ue&&i.drawBuffers(Q)}function Ve(F){return y!==F?(i.useProgram(F),y=F,!0):!1}let gt={[Br]:i.FUNC_ADD,[xm]:i.FUNC_SUBTRACT,[vm]:i.FUNC_REVERSE_SUBTRACT};gt[bm]=i.MIN,gt[Sm]=i.MAX;let He={[Ru]:i.ZERO,[Pu]:i.ONE,[Mm]:i.SRC_COLOR,[Iu]:i.SRC_ALPHA,[Rm]:i.SRC_ALPHA_SATURATE,[Am]:i.DST_COLOR,[Tm]:i.DST_ALPHA,[wm]:i.ONE_MINUS_SRC_COLOR,[Lu]:i.ONE_MINUS_SRC_ALPHA,[Cm]:i.ONE_MINUS_DST_COLOR,[Em]:i.ONE_MINUS_DST_ALPHA,[Pm]:i.CONSTANT_COLOR,[Im]:i.ONE_MINUS_CONSTANT_COLOR,[Lm]:i.CONSTANT_ALPHA,[Dm]:i.ONE_MINUS_CONSTANT_ALPHA};function Qe(F,he,Q,ue,me,ne,Le,Ee,yt,it){if(F===an){m===!0&&(_e(i.BLEND),m=!1);return}if(m===!1&&(ee(i.BLEND),m=!0),F!==Cu){if(F!==g||it!==C){if((v!==Br||M!==Br)&&(i.blendEquation(i.FUNC_ADD),v=Br,M=Br),it)switch(F){case Ls:i.blendFuncSeparate(i.ONE,i.ONE_MINUS_SRC_ALPHA,i.ONE,i.ONE_MINUS_SRC_ALPHA);break;case Tu:i.blendFunc(i.ONE,i.ONE);break;case Eu:i.blendFuncSeparate(i.ZERO,i.ONE_MINUS_SRC_COLOR,i.ZERO,i.ONE);break;case Au:i.blendFuncSeparate(i.DST_COLOR,i.ONE_MINUS_SRC_ALPHA,i.ZERO,i.ONE);break;default:Fe("WebGLState: Invalid blending: ",F);break}else switch(F){case Ls:i.blendFuncSeparate(i.SRC_ALPHA,i.ONE_MINUS_SRC_ALPHA,i.ONE,i.ONE_MINUS_SRC_ALPHA);break;case Tu:i.blendFuncSeparate(i.SRC_ALPHA,i.ONE,i.ONE,i.ONE);break;case Eu:Fe("WebGLState: SubtractiveBlending requires material.premultipliedAlpha = true");break;case Au:Fe("WebGLState: MultiplyBlending requires material.premultipliedAlpha = true");break;default:Fe("WebGLState: Invalid blending: ",F);break}S=null,_=null,w=null,E=null,x.set(0,0,0),A=0,g=F,C=it}return}me=me||he,ne=ne||Q,Le=Le||ue,(he!==v||me!==M)&&(i.blendEquationSeparate(gt[he],gt[me]),v=he,M=me),(Q!==S||ue!==_||ne!==w||Le!==E)&&(i.blendFuncSeparate(He[Q],He[ue],He[ne],He[Le]),S=Q,_=ue,w=ne,E=Le),(Ee.equals(x)===!1||yt!==A)&&(i.blendColor(Ee.r,Ee.g,Ee.b,yt),x.copy(Ee),A=yt),g=F,C=!1}function dt(F,he){F.side===ri?_e(i.CULL_FACE):ee(i.CULL_FACE);let Q=F.side===ui;he&&(Q=!Q),Je(Q),F.blending===Ls&&F.transparent===!1?Qe(an):Qe(F.blending,F.blendEquation,F.blendSrc,F.blendDst,F.blendEquationAlpha,F.blendSrcAlpha,F.blendDstAlpha,F.blendColor,F.blendAlpha,F.premultipliedAlpha),a.setFunc(F.depthFunc),a.setTest(F.depthTest),a.setMask(F.depthWrite),s.setMask(F.colorWrite);let ue=F.stencilWrite;o.setTest(ue),ue&&(o.setMask(F.stencilWriteMask),o.setFunc(F.stencilFunc,F.stencilRef,F.stencilFuncMask),o.setOp(F.stencilFail,F.stencilZFail,F.stencilZPass)),_i(F.polygonOffset,F.polygonOffsetFactor,F.polygonOffsetUnits),F.alphaToCoverage===!0?ee(i.SAMPLE_ALPHA_TO_COVERAGE):_e(i.SAMPLE_ALPHA_TO_COVERAGE)}function Je(F){D!==F&&(F?i.frontFace(i.CW):i.frontFace(i.CCW),D=F)}function vt(F){F!==gm?(ee(i.CULL_FACE),F!==U&&(F===wu?i.cullFace(i.BACK):F===ym?i.cullFace(i.FRONT):i.cullFace(i.FRONT_AND_BACK))):_e(i.CULL_FACE),U=F}function Ht(F){F!==I&&(X&&i.lineWidth(F),I=F)}function _i(F,he,Q){F?(ee(i.POLYGON_OFFSET_FILL),(L!==he||k!==Q)&&(L=he,k=Q,a.getReversed()&&(he=-he),i.polygonOffset(he,Q))):_e(i.POLYGON_OFFSET_FILL)}function wt(F){F?ee(i.SCISSOR_TEST):_e(i.SCISSOR_TEST)}function Dt(F){F===void 0&&(F=i.TEXTURE0+H-1),K!==F&&(i.activeTexture(F),K=F)}function B(F,he,Q){Q===void 0&&(K===null?Q=i.TEXTURE0+H-1:Q=K);let ue=N[Q];ue===void 0&&(ue={type:void 0,texture:void 0},N[Q]=ue),(ue.type!==F||ue.texture!==he)&&(K!==Q&&(i.activeTexture(Q),K=Q),i.bindTexture(F,he||$[F]),ue.type=F,ue.texture=he)}function Qt(){let F=N[K];F!==void 0&&F.type!==void 0&&(i.bindTexture(F.type,null),F.type=void 0,F.texture=void 0)}function lt(){try{i.compressedTexImage2D(...arguments)}catch(F){Fe("WebGLState:",F)}}function R(){try{i.compressedTexImage3D(...arguments)}catch(F){Fe("WebGLState:",F)}}function b(){try{i.texSubImage2D(...arguments)}catch(F){Fe("WebGLState:",F)}}function z(){try{i.texSubImage3D(...arguments)}catch(F){Fe("WebGLState:",F)}}function W(){try{i.compressedTexSubImage2D(...arguments)}catch(F){Fe("WebGLState:",F)}}function Z(){try{i.compressedTexSubImage3D(...arguments)}catch(F){Fe("WebGLState:",F)}}function se(){try{i.texStorage2D(...arguments)}catch(F){Fe("WebGLState:",F)}}function oe(){try{i.texStorage3D(...arguments)}catch(F){Fe("WebGLState:",F)}}function J(){try{i.texImage2D(...arguments)}catch(F){Fe("WebGLState:",F)}}function te(){try{i.texImage3D(...arguments)}catch(F){Fe("WebGLState:",F)}}function le(F){return u[F]!==void 0?u[F]:i.getParameter(F)}function Re(F,he){u[F]!==he&&(i.pixelStorei(F,he),u[F]=he)}function de(F){De.equals(F)===!1&&(i.scissor(F.x,F.y,F.z,F.w),De.copy(F))}function ce(F){Te.equals(F)===!1&&(i.viewport(F.x,F.y,F.z,F.w),Te.copy(F))}function Pe(F,he){let Q=c.get(he);Q===void 0&&(Q=new WeakMap,c.set(he,Q));let ue=Q.get(F);ue===void 0&&(ue=i.getUniformBlockIndex(he,F.name),Q.set(F,ue))}function Ne(F,he){let ue=c.get(he).get(F);l.get(he)!==ue&&(i.uniformBlockBinding(he,ue,F.__bindingPointIndex),l.set(he,ue))}function Ge(){i.disable(i.BLEND),i.disable(i.CULL_FACE),i.disable(i.DEPTH_TEST),i.disable(i.POLYGON_OFFSET_FILL),i.disable(i.SCISSOR_TEST),i.disable(i.STENCIL_TEST),i.disable(i.SAMPLE_ALPHA_TO_COVERAGE),i.blendEquation(i.FUNC_ADD),i.blendFunc(i.ONE,i.ZERO),i.blendFuncSeparate(i.ONE,i.ZERO,i.ONE,i.ZERO),i.blendColor(0,0,0,0),i.colorMask(!0,!0,!0,!0),i.clearColor(0,0,0,0),i.depthMask(!0),i.depthFunc(i.LESS),a.setReversed(!1),i.clearDepth(1),i.stencilMask(4294967295),i.stencilFunc(i.ALWAYS,0,4294967295),i.stencilOp(i.KEEP,i.KEEP,i.KEEP),i.clearStencil(0),i.cullFace(i.BACK),i.frontFace(i.CCW),i.polygonOffset(0,0),i.activeTexture(i.TEXTURE0),i.bindFramebuffer(i.FRAMEBUFFER,null),i.bindFramebuffer(i.DRAW_FRAMEBUFFER,null),i.bindFramebuffer(i.READ_FRAMEBUFFER,null),i.useProgram(null),i.lineWidth(1),i.scissor(0,0,i.canvas.width,i.canvas.height),i.viewport(0,0,i.canvas.width,i.canvas.height),i.pixelStorei(i.PACK_ALIGNMENT,4),i.pixelStorei(i.UNPACK_ALIGNMENT,4),i.pixelStorei(i.UNPACK_FLIP_Y_WEBGL,!1),i.pixelStorei(i.UNPACK_PREMULTIPLY_ALPHA_WEBGL,!1),i.pixelStorei(i.UNPACK_COLORSPACE_CONVERSION_WEBGL,i.BROWSER_DEFAULT_WEBGL),i.pixelStorei(i.PACK_ROW_LENGTH,0),i.pixelStorei(i.PACK_SKIP_PIXELS,0),i.pixelStorei(i.PACK_SKIP_ROWS,0),i.pixelStorei(i.UNPACK_ROW_LENGTH,0),i.pixelStorei(i.UNPACK_IMAGE_HEIGHT,0),i.pixelStorei(i.UNPACK_SKIP_PIXELS,0),i.pixelStorei(i.UNPACK_SKIP_ROWS,0),i.pixelStorei(i.UNPACK_SKIP_IMAGES,0),h={},u={},K=null,N={},d={},f=new WeakMap,p=[],y=null,m=!1,g=null,v=null,S=null,_=null,M=null,w=null,E=null,x=new Ie(0,0,0),A=0,C=!1,D=null,U=null,I=null,L=null,k=null,De.set(0,0,i.canvas.width,i.canvas.height),Te.set(0,0,i.canvas.width,i.canvas.height),s.reset(),a.reset(),o.reset()}return{buffers:{color:s,depth:a,stencil:o},enable:ee,disable:_e,bindFramebuffer:Be,drawBuffers:xe,useProgram:Ve,setBlending:Qe,setMaterial:dt,setFlipSided:Je,setCullFace:vt,setLineWidth:Ht,setPolygonOffset:_i,setScissorTest:wt,activeTexture:Dt,bindTexture:B,unbindTexture:Qt,compressedTexImage2D:lt,compressedTexImage3D:R,texImage2D:J,texImage3D:te,pixelStorei:Re,getParameter:le,updateUBOMapping:Pe,uniformBlockBinding:Ne,texStorage2D:se,texStorage3D:oe,texSubImage2D:b,texSubImage3D:z,compressedTexSubImage2D:W,compressedTexSubImage3D:Z,scissor:de,viewport:ce,reset:Ge}}function vw(i,e,t,n,r,s,a){let o=e.has("WEBGL_multisampled_render_to_texture")?e.get("WEBGL_multisampled_render_to_texture"):null,l=typeof navigator>"u"?!1:/OculusBrowser/g.test(navigator.userAgent),c=new Se,h=new WeakMap,u=new Set,d,f=new WeakMap,p=!1;try{p=typeof OffscreenCanvas<"u"&&new OffscreenCanvas(1,1).getContext("2d")!==null}catch{}function y(R,b){return p?new OffscreenCanvas(R,b):Ss("canvas")}function m(R,b,z){let W=1,Z=lt(R);if((Z.width>z||Z.height>z)&&(W=z/Math.max(Z.width,Z.height)),W<1)if(typeof HTMLImageElement<"u"&&R instanceof HTMLImageElement||typeof HTMLCanvasElement<"u"&&R instanceof HTMLCanvasElement||typeof ImageBitmap<"u"&&R instanceof ImageBitmap||typeof VideoFrame<"u"&&R instanceof VideoFrame){let se=Math.floor(W*Z.width),oe=Math.floor(W*Z.height);d===void 0&&(d=y(se,oe));let J=b?y(se,oe):d;return J.width=se,J.height=oe,J.getContext("2d").drawImage(R,0,0,se,oe),Ce("WebGLRenderer: Texture has been resized from ("+Z.width+"x"+Z.height+") to ("+se+"x"+oe+")."),J}else return"data"in R&&Ce("WebGLRenderer: Image in DataTexture is too big ("+Z.width+"x"+Z.height+")."),R;return R}function g(R){return R.generateMipmaps}function v(R){i.generateMipmap(R)}function S(R){return R.isWebGLCubeRenderTarget?i.TEXTURE_CUBE_MAP:R.isWebGL3DRenderTarget?i.TEXTURE_3D:R.isWebGLArrayRenderTarget||R.isCompressedArrayTexture?i.TEXTURE_2D_ARRAY:i.TEXTURE_2D}function _(R,b,z,W,Z,se=!1){if(R!==null){if(i[R]!==void 0)return i[R];Ce("WebGLRenderer: Attempt to use non-existing WebGL internal format '"+R+"'")}let oe;W&&(oe=e.get("EXT_texture_norm16"),oe||Ce("WebGLRenderer: Unable to use normalized textures without EXT_texture_norm16 extension"));let J=b;if(b===i.RED&&(z===i.FLOAT&&(J=i.R32F),z===i.HALF_FLOAT&&(J=i.R16F),z===i.UNSIGNED_BYTE&&(J=i.R8),z===i.UNSIGNED_SHORT&&oe&&(J=oe.R16_EXT),z===i.SHORT&&oe&&(J=oe.R16_SNORM_EXT)),b===i.RED_INTEGER&&(z===i.UNSIGNED_BYTE&&(J=i.R8UI),z===i.UNSIGNED_SHORT&&(J=i.R16UI),z===i.UNSIGNED_INT&&(J=i.R32UI),z===i.BYTE&&(J=i.R8I),z===i.SHORT&&(J=i.R16I),z===i.INT&&(J=i.R32I)),b===i.RG&&(z===i.FLOAT&&(J=i.RG32F),z===i.HALF_FLOAT&&(J=i.RG16F),z===i.UNSIGNED_BYTE&&(J=i.RG8),z===i.UNSIGNED_SHORT&&oe&&(J=oe.RG16_EXT),z===i.SHORT&&oe&&(J=oe.RG16_SNORM_EXT)),b===i.RG_INTEGER&&(z===i.UNSIGNED_BYTE&&(J=i.RG8UI),z===i.UNSIGNED_SHORT&&(J=i.RG16UI),z===i.UNSIGNED_INT&&(J=i.RG32UI),z===i.BYTE&&(J=i.RG8I),z===i.SHORT&&(J=i.RG16I),z===i.INT&&(J=i.RG32I)),b===i.RGB_INTEGER&&(z===i.UNSIGNED_BYTE&&(J=i.RGB8UI),z===i.UNSIGNED_SHORT&&(J=i.RGB16UI),z===i.UNSIGNED_INT&&(J=i.RGB32UI),z===i.BYTE&&(J=i.RGB8I),z===i.SHORT&&(J=i.RGB16I),z===i.INT&&(J=i.RGB32I)),b===i.RGBA_INTEGER&&(z===i.UNSIGNED_BYTE&&(J=i.RGBA8UI),z===i.UNSIGNED_SHORT&&(J=i.RGBA16UI),z===i.UNSIGNED_INT&&(J=i.RGBA32UI),z===i.BYTE&&(J=i.RGBA8I),z===i.SHORT&&(J=i.RGBA16I),z===i.INT&&(J=i.RGBA32I)),b===i.RGB&&(z===i.UNSIGNED_SHORT&&oe&&(J=oe.RGB16_EXT),z===i.SHORT&&oe&&(J=oe.RGB16_SNORM_EXT),z===i.UNSIGNED_INT_5_9_9_9_REV&&(J=i.RGB9_E5),z===i.UNSIGNED_INT_10F_11F_11F_REV&&(J=i.R11F_G11F_B10F)),b===i.RGBA){let te=se?ma:je.getTransfer(Z);z===i.FLOAT&&(J=i.RGBA32F),z===i.HALF_FLOAT&&(J=i.RGBA16F),z===i.UNSIGNED_BYTE&&(J=te===rt?i.SRGB8_ALPHA8:i.RGBA8),z===i.UNSIGNED_SHORT&&oe&&(J=oe.RGBA16_EXT),z===i.SHORT&&oe&&(J=oe.RGBA16_SNORM_EXT),z===i.UNSIGNED_SHORT_4_4_4_4&&(J=i.RGBA4),z===i.UNSIGNED_SHORT_5_5_5_1&&(J=i.RGB5_A1)}return(J===i.R16F||J===i.R32F||J===i.RG16F||J===i.RG32F||J===i.RGBA16F||J===i.RGBA32F)&&e.get("EXT_color_buffer_float"),J}function M(R,b){let z;return R?b===null||b===qi||b===Us?z=i.DEPTH24_STENCIL8:b===fi?z=i.DEPTH32F_STENCIL8:b===Ns&&(z=i.DEPTH24_STENCIL8,Ce("DepthTexture: 16 bit depth attachment is not supported with stencil. Using 24-bit attachment.")):b===null||b===qi||b===Us?z=i.DEPTH_COMPONENT24:b===fi?z=i.DEPTH_COMPONENT32F:b===Ns&&(z=i.DEPTH_COMPONENT16),z}function w(R,b){return g(R)===!0||R.isFramebufferTexture&&R.minFilter!==At&&R.minFilter!==St?Math.log2(Math.max(b.width,b.height))+1:R.mipmaps!==void 0&&R.mipmaps.length>0?R.mipmaps.length:R.isCompressedTexture&&Array.isArray(R.image)?b.mipmaps.length:1}function E(R){let b=R.target;b.removeEventListener("dispose",E),A(b),b.isVideoTexture&&h.delete(b),b.isHTMLTexture&&u.delete(b)}function x(R){let b=R.target;b.removeEventListener("dispose",x),D(b)}function A(R){let b=n.get(R);if(b.__webglInit===void 0)return;let z=R.source,W=f.get(z);if(W){let Z=W[b.__cacheKey];Z.usedTimes--,Z.usedTimes===0&&C(R),Object.keys(W).length===0&&f.delete(z)}n.remove(R)}function C(R){let b=n.get(R);i.deleteTexture(b.__webglTexture);let z=R.source,W=f.get(z);delete W[b.__cacheKey],a.memory.textures--}function D(R){let b=n.get(R);if(R.depthTexture&&(R.depthTexture.dispose(),n.remove(R.depthTexture)),R.isWebGLCubeRenderTarget)for(let W=0;W<6;W++){if(Array.isArray(b.__webglFramebuffer[W]))for(let Z=0;Z<b.__webglFramebuffer[W].length;Z++)i.deleteFramebuffer(b.__webglFramebuffer[W][Z]);else i.deleteFramebuffer(b.__webglFramebuffer[W]);b.__webglDepthbuffer&&i.deleteRenderbuffer(b.__webglDepthbuffer[W])}else{if(Array.isArray(b.__webglFramebuffer))for(let W=0;W<b.__webglFramebuffer.length;W++)i.deleteFramebuffer(b.__webglFramebuffer[W]);else i.deleteFramebuffer(b.__webglFramebuffer);if(b.__webglDepthbuffer&&i.deleteRenderbuffer(b.__webglDepthbuffer),b.__webglMultisampledFramebuffer&&i.deleteFramebuffer(b.__webglMultisampledFramebuffer),b.__webglColorRenderbuffer)for(let W=0;W<b.__webglColorRenderbuffer.length;W++)b.__webglColorRenderbuffer[W]&&i.deleteRenderbuffer(b.__webglColorRenderbuffer[W]);b.__webglDepthRenderbuffer&&i.deleteRenderbuffer(b.__webglDepthRenderbuffer)}let z=R.textures;for(let W=0,Z=z.length;W<Z;W++){let se=n.get(z[W]);se.__webglTexture&&(i.deleteTexture(se.__webglTexture),a.memory.textures--),n.remove(z[W])}n.remove(R)}let U=0;function I(){U=0}function L(){return U}function k(R){U=R}function H(){let R=U;return R>=r.maxTextures&&Ce("WebGLTextures: Trying to use "+(R+1)+" texture units while this GPU supports only "+r.maxTextures),U+=1,R}function X(R){let b=[];return b.push(R.wrapS),b.push(R.wrapT),b.push(R.wrapR||0),b.push(R.magFilter),b.push(R.minFilter),b.push(R.anisotropy),b.push(R.internalFormat),b.push(R.format),b.push(R.type),b.push(R.generateMipmaps),b.push(R.premultiplyAlpha),b.push(R.flipY),b.push(R.unpackAlignment),b.push(R.colorSpace),b.join()}function Y(R,b){let z=n.get(R);if(R.isVideoTexture&&B(R),R.isRenderTargetTexture===!1&&R.isExternalTexture!==!0&&R.version>0&&z.__version!==R.version){let W=R.image;if(W===null)Ce("WebGLRenderer: Texture marked for update but no image data found.");else if(W.complete===!1)Ce("WebGLRenderer: Texture marked for update but image is incomplete");else{_e(z,R,b);return}}else R.isExternalTexture&&(z.__webglTexture=R.sourceTexture?R.sourceTexture:null);t.bindTexture(i.TEXTURE_2D,z.__webglTexture,i.TEXTURE0+b)}function q(R,b){let z=n.get(R);if(R.isRenderTargetTexture===!1&&R.version>0&&z.__version!==R.version){_e(z,R,b);return}else R.isExternalTexture&&(z.__webglTexture=R.sourceTexture?R.sourceTexture:null);t.bindTexture(i.TEXTURE_2D_ARRAY,z.__webglTexture,i.TEXTURE0+b)}function K(R,b){let z=n.get(R);if(R.isRenderTargetTexture===!1&&R.version>0&&z.__version!==R.version){_e(z,R,b);return}t.bindTexture(i.TEXTURE_3D,z.__webglTexture,i.TEXTURE0+b)}function N(R,b){let z=n.get(R);if(R.isCubeDepthTexture!==!0&&R.version>0&&z.__version!==R.version){Be(z,R,b);return}t.bindTexture(i.TEXTURE_CUBE_MAP,z.__webglTexture,i.TEXTURE0+b)}let ie={[$n]:i.REPEAT,[Li]:i.CLAMP_TO_EDGE,[vs]:i.MIRRORED_REPEAT},re={[At]:i.NEAREST,[Vl]:i.NEAREST_MIPMAP_NEAREST,[zr]:i.NEAREST_MIPMAP_LINEAR,[St]:i.LINEAR,[Ds]:i.LINEAR_MIPMAP_NEAREST,[Ci]:i.LINEAR_MIPMAP_LINEAR},De={[Vm]:i.NEVER,[qm]:i.ALWAYS,[Gm]:i.LESS,[Mc]:i.LEQUAL,[Hm]:i.EQUAL,[wc]:i.GEQUAL,[Wm]:i.GREATER,[Xm]:i.NOTEQUAL};function Te(R,b){if(b.type===fi&&e.has("OES_texture_float_linear")===!1&&(b.magFilter===St||b.magFilter===Ds||b.magFilter===zr||b.magFilter===Ci||b.minFilter===St||b.minFilter===Ds||b.minFilter===zr||b.minFilter===Ci)&&Ce("WebGLRenderer: Unable to use linear filtering with floating point textures. OES_texture_float_linear not supported on this device."),i.texParameteri(R,i.TEXTURE_WRAP_S,ie[b.wrapS]),i.texParameteri(R,i.TEXTURE_WRAP_T,ie[b.wrapT]),(R===i.TEXTURE_3D||R===i.TEXTURE_2D_ARRAY)&&i.texParameteri(R,i.TEXTURE_WRAP_R,ie[b.wrapR]),i.texParameteri(R,i.TEXTURE_MAG_FILTER,re[b.magFilter]),i.texParameteri(R,i.TEXTURE_MIN_FILTER,re[b.minFilter]),b.compareFunction&&(i.texParameteri(R,i.TEXTURE_COMPARE_MODE,i.COMPARE_REF_TO_TEXTURE),i.texParameteri(R,i.TEXTURE_COMPARE_FUNC,De[b.compareFunction])),e.has("EXT_texture_filter_anisotropic")===!0){if(b.magFilter===At||b.minFilter!==zr&&b.minFilter!==Ci||b.type===fi&&e.has("OES_texture_float_linear")===!1)return;if(b.anisotropy>1||n.get(b).__currentAnisotropy){let z=e.get("EXT_texture_filter_anisotropic");i.texParameterf(R,z.TEXTURE_MAX_ANISOTROPY_EXT,Math.min(b.anisotropy,r.getMaxAnisotropy())),n.get(b).__currentAnisotropy=b.anisotropy}}}function $e(R,b){let z=!1;R.__webglInit===void 0&&(R.__webglInit=!0,b.addEventListener("dispose",E));let W=b.source,Z=f.get(W);Z===void 0&&(Z={},f.set(W,Z));let se=X(b);if(se!==R.__cacheKey){Z[se]===void 0&&(Z[se]={texture:i.createTexture(),usedTimes:0},a.memory.textures++,z=!0),Z[se].usedTimes++;let oe=Z[R.__cacheKey];oe!==void 0&&(Z[R.__cacheKey].usedTimes--,oe.usedTimes===0&&C(b)),R.__cacheKey=se,R.__webglTexture=Z[se].texture}return z}function $(R,b,z){return Math.floor(Math.floor(R/z)/b)}function ee(R,b,z,W){let se=R.updateRanges;if(se.length===0)t.texSubImage2D(i.TEXTURE_2D,0,0,0,b.width,b.height,z,W,b.data);else{se.sort((Re,de)=>Re.start-de.start);let oe=0;for(let Re=1;Re<se.length;Re++){let de=se[oe],ce=se[Re],Pe=de.start+de.count,Ne=$(ce.start,b.width,4),Ge=$(de.start,b.width,4);ce.start<=Pe+1&&Ne===Ge&&$(ce.start+ce.count-1,b.width,4)===Ne?de.count=Math.max(de.count,ce.start+ce.count-de.start):(++oe,se[oe]=ce)}se.length=oe+1;let J=t.getParameter(i.UNPACK_ROW_LENGTH),te=t.getParameter(i.UNPACK_SKIP_PIXELS),le=t.getParameter(i.UNPACK_SKIP_ROWS);t.pixelStorei(i.UNPACK_ROW_LENGTH,b.width);for(let Re=0,de=se.length;Re<de;Re++){let ce=se[Re],Pe=Math.floor(ce.start/4),Ne=Math.ceil(ce.count/4),Ge=Pe%b.width,F=Math.floor(Pe/b.width),he=Ne,Q=1;t.pixelStorei(i.UNPACK_SKIP_PIXELS,Ge),t.pixelStorei(i.UNPACK_SKIP_ROWS,F),t.texSubImage2D(i.TEXTURE_2D,0,Ge,F,he,Q,z,W,b.data)}R.clearUpdateRanges(),t.pixelStorei(i.UNPACK_ROW_LENGTH,J),t.pixelStorei(i.UNPACK_SKIP_PIXELS,te),t.pixelStorei(i.UNPACK_SKIP_ROWS,le)}}function _e(R,b,z){let W=i.TEXTURE_2D;(b.isDataArrayTexture||b.isCompressedArrayTexture)&&(W=i.TEXTURE_2D_ARRAY),b.isData3DTexture&&(W=i.TEXTURE_3D);let Z=$e(R,b),se=b.source;t.bindTexture(W,R.__webglTexture,i.TEXTURE0+z);let oe=n.get(se);if(se.version!==oe.__version||Z===!0){if(t.activeTexture(i.TEXTURE0+z),(typeof ImageBitmap<"u"&&b.image instanceof ImageBitmap)===!1){let Q=je.getPrimaries(je.workingColorSpace),ue=b.colorSpace===Dn?null:je.getPrimaries(b.colorSpace),me=b.colorSpace===Dn||Q===ue?i.NONE:i.BROWSER_DEFAULT_WEBGL;t.pixelStorei(i.UNPACK_FLIP_Y_WEBGL,b.flipY),t.pixelStorei(i.UNPACK_PREMULTIPLY_ALPHA_WEBGL,b.premultiplyAlpha),t.pixelStorei(i.UNPACK_COLORSPACE_CONVERSION_WEBGL,me)}t.pixelStorei(i.UNPACK_ALIGNMENT,b.unpackAlignment);let te=m(b.image,!1,r.maxTextureSize);te=Qt(b,te);let le=s.convert(b.format,b.colorSpace),Re=s.convert(b.type),de=_(b.internalFormat,le,Re,b.normalized,b.colorSpace,b.isVideoTexture);Te(W,b);let ce,Pe=b.mipmaps,Ne=b.isVideoTexture!==!0,Ge=oe.__version===void 0||Z===!0,F=se.dataReady,he=w(b,te);if(b.isDepthTexture)de=M(b.format===ar,b.type),Ge&&(Ne?t.texStorage2D(i.TEXTURE_2D,1,de,te.width,te.height):t.texImage2D(i.TEXTURE_2D,0,de,te.width,te.height,0,le,Re,null));else if(b.isDataTexture)if(Pe.length>0){Ne&&Ge&&t.texStorage2D(i.TEXTURE_2D,he,de,Pe[0].width,Pe[0].height);for(let Q=0,ue=Pe.length;Q<ue;Q++)ce=Pe[Q],Ne?F&&t.texSubImage2D(i.TEXTURE_2D,Q,0,0,ce.width,ce.height,le,Re,ce.data):t.texImage2D(i.TEXTURE_2D,Q,de,ce.width,ce.height,0,le,Re,ce.data);b.generateMipmaps=!1}else Ne?(Ge&&t.texStorage2D(i.TEXTURE_2D,he,de,te.width,te.height),F&&ee(b,te,le,Re)):t.texImage2D(i.TEXTURE_2D,0,de,te.width,te.height,0,le,Re,te.data);else if(b.isCompressedTexture)if(b.isCompressedArrayTexture){Ne&&Ge&&t.texStorage3D(i.TEXTURE_2D_ARRAY,he,de,Pe[0].width,Pe[0].height,te.depth);for(let Q=0,ue=Pe.length;Q<ue;Q++)if(ce=Pe[Q],b.format!==Ri)if(le!==null)if(Ne){if(F)if(b.layerUpdates.size>0){let me=Tc(ce.width,ce.height,b.format,b.type);for(let ne of b.layerUpdates){let Le=ce.data.subarray(ne*me/ce.data.BYTES_PER_ELEMENT,(ne+1)*me/ce.data.BYTES_PER_ELEMENT);t.compressedTexSubImage3D(i.TEXTURE_2D_ARRAY,Q,0,0,ne,ce.width,ce.height,1,le,Le)}}else t.compressedTexSubImage3D(i.TEXTURE_2D_ARRAY,Q,0,0,0,ce.width,ce.height,te.depth,le,ce.data)}else t.compressedTexImage3D(i.TEXTURE_2D_ARRAY,Q,de,ce.width,ce.height,te.depth,0,ce.data,0,0);else Ce("WebGLRenderer: Attempt to load unsupported compressed texture format in .uploadTexture()");else Ne?F&&t.texSubImage3D(i.TEXTURE_2D_ARRAY,Q,0,0,0,ce.width,ce.height,te.depth,le,Re,ce.data):t.texImage3D(i.TEXTURE_2D_ARRAY,Q,de,ce.width,ce.height,te.depth,0,le,Re,ce.data);b.layerUpdates.size>0&&b.clearLayerUpdates()}else{Ne&&Ge&&t.texStorage2D(i.TEXTURE_2D,he,de,Pe[0].width,Pe[0].height);for(let Q=0,ue=Pe.length;Q<ue;Q++)ce=Pe[Q],b.format!==Ri?le!==null?Ne?F&&t.compressedTexSubImage2D(i.TEXTURE_2D,Q,0,0,ce.width,ce.height,le,ce.data):t.compressedTexImage2D(i.TEXTURE_2D,Q,de,ce.width,ce.height,0,ce.data):Ce("WebGLRenderer: Attempt to load unsupported compressed texture format in .uploadTexture()"):Ne?F&&t.texSubImage2D(i.TEXTURE_2D,Q,0,0,ce.width,ce.height,le,Re,ce.data):t.texImage2D(i.TEXTURE_2D,Q,de,ce.width,ce.height,0,le,Re,ce.data)}else if(b.isDataArrayTexture)if(Ne){if(Ge&&t.texStorage3D(i.TEXTURE_2D_ARRAY,he,de,te.width,te.height,te.depth),F)if(b.layerUpdates.size>0){let Q=Tc(te.width,te.height,b.format,b.type);for(let ue of b.layerUpdates){let me=te.data.subarray(ue*Q/te.data.BYTES_PER_ELEMENT,(ue+1)*Q/te.data.BYTES_PER_ELEMENT);t.texSubImage3D(i.TEXTURE_2D_ARRAY,0,0,0,ue,te.width,te.height,1,le,Re,me)}b.clearLayerUpdates()}else t.texSubImage3D(i.TEXTURE_2D_ARRAY,0,0,0,0,te.width,te.height,te.depth,le,Re,te.data)}else t.texImage3D(i.TEXTURE_2D_ARRAY,0,de,te.width,te.height,te.depth,0,le,Re,te.data);else if(b.isData3DTexture)Ne?(Ge&&t.texStorage3D(i.TEXTURE_3D,he,de,te.width,te.height,te.depth),F&&t.texSubImage3D(i.TEXTURE_3D,0,0,0,0,te.width,te.height,te.depth,le,Re,te.data)):t.texImage3D(i.TEXTURE_3D,0,de,te.width,te.height,te.depth,0,le,Re,te.data);else if(b.isFramebufferTexture){if(Ge)if(Ne)t.texStorage2D(i.TEXTURE_2D,he,de,te.width,te.height);else{let Q=te.width,ue=te.height;for(let me=0;me<he;me++)t.texImage2D(i.TEXTURE_2D,me,de,Q,ue,0,le,Re,null),Q>>=1,ue>>=1}}else if(b.isHTMLTexture){if("texElementImage2D"in i){let Q=i.canvas;if(Q.hasAttribute("layoutsubtree")||Q.setAttribute("layoutsubtree","true"),te.parentNode!==Q){Q.appendChild(te),u.add(b),Q.onpaint=ue=>{let me=ue.changedElements;for(let ne of u)me.includes(ne.image)&&(ne.needsUpdate=!0)},Q.requestPaint();return}if(i.texElementImage2D.length===3)i.texElementImage2D(i.TEXTURE_2D,i.RGBA8,te);else{let me=i.RGBA,ne=i.RGBA,Le=i.UNSIGNED_BYTE;i.texElementImage2D(i.TEXTURE_2D,0,me,ne,Le,te)}i.texParameteri(i.TEXTURE_2D,i.TEXTURE_MIN_FILTER,i.LINEAR),i.texParameteri(i.TEXTURE_2D,i.TEXTURE_WRAP_S,i.CLAMP_TO_EDGE),i.texParameteri(i.TEXTURE_2D,i.TEXTURE_WRAP_T,i.CLAMP_TO_EDGE)}}else if(Pe.length>0){if(Ne&&Ge){let Q=lt(Pe[0]);t.texStorage2D(i.TEXTURE_2D,he,de,Q.width,Q.height)}for(let Q=0,ue=Pe.length;Q<ue;Q++)ce=Pe[Q],Ne?F&&t.texSubImage2D(i.TEXTURE_2D,Q,0,0,le,Re,ce):t.texImage2D(i.TEXTURE_2D,Q,de,le,Re,ce);b.generateMipmaps=!1}else if(Ne){if(Ge){let Q=lt(te);t.texStorage2D(i.TEXTURE_2D,he,de,Q.width,Q.height)}F&&t.texSubImage2D(i.TEXTURE_2D,0,0,0,le,Re,te)}else t.texImage2D(i.TEXTURE_2D,0,de,le,Re,te);g(b)&&v(W),oe.__version=se.version,b.onUpdate&&b.onUpdate(b)}R.__version=b.version}function Be(R,b,z){if(b.image.length!==6)return;let W=$e(R,b),Z=b.source;t.bindTexture(i.TEXTURE_CUBE_MAP,R.__webglTexture,i.TEXTURE0+z);let se=n.get(Z);if(Z.version!==se.__version||W===!0){t.activeTexture(i.TEXTURE0+z);let oe=je.getPrimaries(je.workingColorSpace),J=b.colorSpace===Dn?null:je.getPrimaries(b.colorSpace),te=b.colorSpace===Dn||oe===J?i.NONE:i.BROWSER_DEFAULT_WEBGL;t.pixelStorei(i.UNPACK_FLIP_Y_WEBGL,b.flipY),t.pixelStorei(i.UNPACK_PREMULTIPLY_ALPHA_WEBGL,b.premultiplyAlpha),t.pixelStorei(i.UNPACK_ALIGNMENT,b.unpackAlignment),t.pixelStorei(i.UNPACK_COLORSPACE_CONVERSION_WEBGL,te);let le=b.isCompressedTexture||b.image[0].isCompressedTexture,Re=b.image[0]&&b.image[0].isDataTexture,de=[];for(let ne=0;ne<6;ne++)!le&&!Re?de[ne]=m(b.image[ne],!0,r.maxCubemapSize):de[ne]=Re?b.image[ne].image:b.image[ne],de[ne]=Qt(b,de[ne]);let ce=de[0],Pe=s.convert(b.format,b.colorSpace),Ne=s.convert(b.type),Ge=_(b.internalFormat,Pe,Ne,b.normalized,b.colorSpace),F=b.isVideoTexture!==!0,he=se.__version===void 0||W===!0,Q=Z.dataReady,ue=w(b,ce);Te(i.TEXTURE_CUBE_MAP,b);let me;if(le){F&&he&&t.texStorage2D(i.TEXTURE_CUBE_MAP,ue,Ge,ce.width,ce.height);for(let ne=0;ne<6;ne++){me=de[ne].mipmaps;for(let Le=0;Le<me.length;Le++){let Ee=me[Le];b.format!==Ri?Pe!==null?F?Q&&t.compressedTexSubImage2D(i.TEXTURE_CUBE_MAP_POSITIVE_X+ne,Le,0,0,Ee.width,Ee.height,Pe,Ee.data):t.compressedTexImage2D(i.TEXTURE_CUBE_MAP_POSITIVE_X+ne,Le,Ge,Ee.width,Ee.height,0,Ee.data):Ce("WebGLRenderer: Attempt to load unsupported compressed texture format in .setTextureCube()"):F?Q&&t.texSubImage2D(i.TEXTURE_CUBE_MAP_POSITIVE_X+ne,Le,0,0,Ee.width,Ee.height,Pe,Ne,Ee.data):t.texImage2D(i.TEXTURE_CUBE_MAP_POSITIVE_X+ne,Le,Ge,Ee.width,Ee.height,0,Pe,Ne,Ee.data)}}}else{if(me=b.mipmaps,F&&he){me.length>0&&ue++;let ne=lt(de[0]);t.texStorage2D(i.TEXTURE_CUBE_MAP,ue,Ge,ne.width,ne.height)}for(let ne=0;ne<6;ne++)if(Re){F?Q&&t.texSubImage2D(i.TEXTURE_CUBE_MAP_POSITIVE_X+ne,0,0,0,de[ne].width,de[ne].height,Pe,Ne,de[ne].data):t.texImage2D(i.TEXTURE_CUBE_MAP_POSITIVE_X+ne,0,Ge,de[ne].width,de[ne].height,0,Pe,Ne,de[ne].data);for(let Le=0;Le<me.length;Le++){let yt=me[Le].image[ne].image;F?Q&&t.texSubImage2D(i.TEXTURE_CUBE_MAP_POSITIVE_X+ne,Le+1,0,0,yt.width,yt.height,Pe,Ne,yt.data):t.texImage2D(i.TEXTURE_CUBE_MAP_POSITIVE_X+ne,Le+1,Ge,yt.width,yt.height,0,Pe,Ne,yt.data)}}else{F?Q&&t.texSubImage2D(i.TEXTURE_CUBE_MAP_POSITIVE_X+ne,0,0,0,Pe,Ne,de[ne]):t.texImage2D(i.TEXTURE_CUBE_MAP_POSITIVE_X+ne,0,Ge,Pe,Ne,de[ne]);for(let Le=0;Le<me.length;Le++){let Ee=me[Le];F?Q&&t.texSubImage2D(i.TEXTURE_CUBE_MAP_POSITIVE_X+ne,Le+1,0,0,Pe,Ne,Ee.image[ne]):t.texImage2D(i.TEXTURE_CUBE_MAP_POSITIVE_X+ne,Le+1,Ge,Pe,Ne,Ee.image[ne])}}}g(b)&&v(i.TEXTURE_CUBE_MAP),se.__version=Z.version,b.onUpdate&&b.onUpdate(b)}R.__version=b.version}function xe(R,b,z,W,Z,se){let oe=s.convert(z.format,z.colorSpace),J=s.convert(z.type),te=_(z.internalFormat,oe,J,z.normalized,z.colorSpace),le=n.get(b),Re=n.get(z);if(Re.__renderTarget=b,!le.__hasExternalTextures){let de=Math.max(1,b.width>>se),ce=Math.max(1,b.height>>se);Z===i.TEXTURE_3D||Z===i.TEXTURE_2D_ARRAY?t.texImage3D(Z,se,te,de,ce,b.depth,0,oe,J,null):t.texImage2D(Z,se,te,de,ce,0,oe,J,null)}t.bindFramebuffer(i.FRAMEBUFFER,R),Dt(b)?o.framebufferTexture2DMultisampleEXT(i.FRAMEBUFFER,W,Z,Re.__webglTexture,0,wt(b)):(Z===i.TEXTURE_2D||Z>=i.TEXTURE_CUBE_MAP_POSITIVE_X&&Z<=i.TEXTURE_CUBE_MAP_NEGATIVE_Z)&&i.framebufferTexture2D(i.FRAMEBUFFER,W,Z,Re.__webglTexture,se),t.bindFramebuffer(i.FRAMEBUFFER,null)}function Ve(R,b,z){if(i.bindRenderbuffer(i.RENDERBUFFER,R),b.depthBuffer){let W=b.depthTexture,Z=W&&W.isDepthTexture?W.type:null,se=M(b.stencilBuffer,Z),oe=b.stencilBuffer?i.DEPTH_STENCIL_ATTACHMENT:i.DEPTH_ATTACHMENT;Dt(b)?o.renderbufferStorageMultisampleEXT(i.RENDERBUFFER,wt(b),se,b.width,b.height):z?i.renderbufferStorageMultisample(i.RENDERBUFFER,wt(b),se,b.width,b.height):i.renderbufferStorage(i.RENDERBUFFER,se,b.width,b.height),i.framebufferRenderbuffer(i.FRAMEBUFFER,oe,i.RENDERBUFFER,R)}else{let W=b.textures;for(let Z=0;Z<W.length;Z++){let se=W[Z],oe=s.convert(se.format,se.colorSpace),J=s.convert(se.type),te=_(se.internalFormat,oe,J,se.normalized,se.colorSpace);Dt(b)?o.renderbufferStorageMultisampleEXT(i.RENDERBUFFER,wt(b),te,b.width,b.height):z?i.renderbufferStorageMultisample(i.RENDERBUFFER,wt(b),te,b.width,b.height):i.renderbufferStorage(i.RENDERBUFFER,te,b.width,b.height)}}i.bindRenderbuffer(i.RENDERBUFFER,null)}function gt(R,b,z){let W=b.isWebGLCubeRenderTarget===!0;if(t.bindFramebuffer(i.FRAMEBUFFER,R),!(b.depthTexture&&b.depthTexture.isDepthTexture))throw new Error("THREE.WebGLTextures: renderTarget.depthTexture must be an instance of THREE.DepthTexture.");let Z=n.get(b.depthTexture);if(Z.__renderTarget=b,(!Z.__webglTexture||b.depthTexture.image.width!==b.width||b.depthTexture.image.height!==b.height)&&(b.depthTexture.image.width=b.width,b.depthTexture.image.height=b.height,b.depthTexture.needsUpdate=!0),W){if(Z.__webglInit===void 0&&(Z.__webglInit=!0,b.depthTexture.addEventListener("dispose",E)),Z.__webglTexture===void 0){Z.__webglTexture=i.createTexture(),t.bindTexture(i.TEXTURE_CUBE_MAP,Z.__webglTexture),Te(i.TEXTURE_CUBE_MAP,b.depthTexture);let le=s.convert(b.depthTexture.format),Re=s.convert(b.depthTexture.type),de;b.depthTexture.format===tn?de=i.DEPTH_COMPONENT24:b.depthTexture.format===ar&&(de=i.DEPTH24_STENCIL8);for(let ce=0;ce<6;ce++)i.texImage2D(i.TEXTURE_CUBE_MAP_POSITIVE_X+ce,0,de,b.width,b.height,0,le,Re,null)}}else Y(b.depthTexture,0);let se=Z.__webglTexture,oe=wt(b),J=W?i.TEXTURE_CUBE_MAP_POSITIVE_X+z:i.TEXTURE_2D,te=b.depthTexture.format===ar?i.DEPTH_STENCIL_ATTACHMENT:i.DEPTH_ATTACHMENT;if(b.depthTexture.format===tn)Dt(b)?o.framebufferTexture2DMultisampleEXT(i.FRAMEBUFFER,te,J,se,0,oe):i.framebufferTexture2D(i.FRAMEBUFFER,te,J,se,0);else if(b.depthTexture.format===ar)Dt(b)?o.framebufferTexture2DMultisampleEXT(i.FRAMEBUFFER,te,J,se,0,oe):i.framebufferTexture2D(i.FRAMEBUFFER,te,J,se,0);else throw new Error("THREE.WebGLTextures: Unknown depthTexture format.")}function He(R){let b=n.get(R),z=R.isWebGLCubeRenderTarget===!0;if(b.__boundDepthTexture!==R.depthTexture){let W=R.depthTexture;if(b.__depthDisposeCallback&&b.__depthDisposeCallback(),W){let Z=()=>{delete b.__boundDepthTexture,delete b.__depthDisposeCallback,W.removeEventListener("dispose",Z)};W.addEventListener("dispose",Z),b.__depthDisposeCallback=Z}b.__boundDepthTexture=W}if(R.depthTexture&&!b.__autoAllocateDepthBuffer)if(z)for(let W=0;W<6;W++)gt(b.__webglFramebuffer[W],R,W);else{let W=R.texture.mipmaps;W&&W.length>0?gt(b.__webglFramebuffer[0],R,0):gt(b.__webglFramebuffer,R,0)}else if(z){b.__webglDepthbuffer=[];for(let W=0;W<6;W++)if(t.bindFramebuffer(i.FRAMEBUFFER,b.__webglFramebuffer[W]),b.__webglDepthbuffer[W]===void 0)b.__webglDepthbuffer[W]=i.createRenderbuffer(),Ve(b.__webglDepthbuffer[W],R,!1);else{let Z=R.stencilBuffer?i.DEPTH_STENCIL_ATTACHMENT:i.DEPTH_ATTACHMENT,se=b.__webglDepthbuffer[W];i.bindRenderbuffer(i.RENDERBUFFER,se),i.framebufferRenderbuffer(i.FRAMEBUFFER,Z,i.RENDERBUFFER,se)}}else{let W=R.texture.mipmaps;if(W&&W.length>0?t.bindFramebuffer(i.FRAMEBUFFER,b.__webglFramebuffer[0]):t.bindFramebuffer(i.FRAMEBUFFER,b.__webglFramebuffer),b.__webglDepthbuffer===void 0)b.__webglDepthbuffer=i.createRenderbuffer(),Ve(b.__webglDepthbuffer,R,!1);else{let Z=R.stencilBuffer?i.DEPTH_STENCIL_ATTACHMENT:i.DEPTH_ATTACHMENT,se=b.__webglDepthbuffer;i.bindRenderbuffer(i.RENDERBUFFER,se),i.framebufferRenderbuffer(i.FRAMEBUFFER,Z,i.RENDERBUFFER,se)}}t.bindFramebuffer(i.FRAMEBUFFER,null)}function Qe(R,b,z){let W=n.get(R);b!==void 0&&xe(W.__webglFramebuffer,R,R.texture,i.COLOR_ATTACHMENT0,i.TEXTURE_2D,0),z!==void 0&&He(R)}function dt(R){let b=R.texture,z=n.get(R),W=n.get(b);R.addEventListener("dispose",x);let Z=R.textures,se=R.isWebGLCubeRenderTarget===!0,oe=Z.length>1;if(oe||(W.__webglTexture===void 0&&(W.__webglTexture=i.createTexture()),W.__version=b.version,a.memory.textures++),se){z.__webglFramebuffer=[];for(let J=0;J<6;J++)if(b.mipmaps&&b.mipmaps.length>0){z.__webglFramebuffer[J]=[];for(let te=0;te<b.mipmaps.length;te++)z.__webglFramebuffer[J][te]=i.createFramebuffer()}else z.__webglFramebuffer[J]=i.createFramebuffer()}else{if(b.mipmaps&&b.mipmaps.length>0){z.__webglFramebuffer=[];for(let J=0;J<b.mipmaps.length;J++)z.__webglFramebuffer[J]=i.createFramebuffer()}else z.__webglFramebuffer=i.createFramebuffer();if(oe)for(let J=0,te=Z.length;J<te;J++){let le=n.get(Z[J]);le.__webglTexture===void 0&&(le.__webglTexture=i.createTexture(),a.memory.textures++)}if(R.samples>0&&Dt(R)===!1){z.__webglMultisampledFramebuffer=i.createFramebuffer(),z.__webglColorRenderbuffer=[],t.bindFramebuffer(i.FRAMEBUFFER,z.__webglMultisampledFramebuffer);for(let J=0;J<Z.length;J++){let te=Z[J];z.__webglColorRenderbuffer[J]=i.createRenderbuffer(),i.bindRenderbuffer(i.RENDERBUFFER,z.__webglColorRenderbuffer[J]);let le=s.convert(te.format,te.colorSpace),Re=s.convert(te.type),de=_(te.internalFormat,le,Re,te.normalized,te.colorSpace,R.isXRRenderTarget===!0),ce=wt(R);i.renderbufferStorageMultisample(i.RENDERBUFFER,ce,de,R.width,R.height),i.framebufferRenderbuffer(i.FRAMEBUFFER,i.COLOR_ATTACHMENT0+J,i.RENDERBUFFER,z.__webglColorRenderbuffer[J])}i.bindRenderbuffer(i.RENDERBUFFER,null),R.depthBuffer&&(z.__webglDepthRenderbuffer=i.createRenderbuffer(),Ve(z.__webglDepthRenderbuffer,R,!0)),t.bindFramebuffer(i.FRAMEBUFFER,null)}}if(se){t.bindTexture(i.TEXTURE_CUBE_MAP,W.__webglTexture),Te(i.TEXTURE_CUBE_MAP,b);for(let J=0;J<6;J++)if(b.mipmaps&&b.mipmaps.length>0)for(let te=0;te<b.mipmaps.length;te++)xe(z.__webglFramebuffer[J][te],R,b,i.COLOR_ATTACHMENT0,i.TEXTURE_CUBE_MAP_POSITIVE_X+J,te);else xe(z.__webglFramebuffer[J],R,b,i.COLOR_ATTACHMENT0,i.TEXTURE_CUBE_MAP_POSITIVE_X+J,0);g(b)&&v(i.TEXTURE_CUBE_MAP),t.unbindTexture()}else if(oe){for(let J=0,te=Z.length;J<te;J++){let le=Z[J],Re=n.get(le),de=i.TEXTURE_2D;(R.isWebGL3DRenderTarget||R.isWebGLArrayRenderTarget)&&(de=R.isWebGL3DRenderTarget?i.TEXTURE_3D:i.TEXTURE_2D_ARRAY),t.bindTexture(de,Re.__webglTexture),Te(de,le),xe(z.__webglFramebuffer,R,le,i.COLOR_ATTACHMENT0+J,de,0),g(le)&&v(de)}t.unbindTexture()}else{let J=i.TEXTURE_2D;if((R.isWebGL3DRenderTarget||R.isWebGLArrayRenderTarget)&&(J=R.isWebGL3DRenderTarget?i.TEXTURE_3D:i.TEXTURE_2D_ARRAY),t.bindTexture(J,W.__webglTexture),Te(J,b),b.mipmaps&&b.mipmaps.length>0)for(let te=0;te<b.mipmaps.length;te++)xe(z.__webglFramebuffer[te],R,b,i.COLOR_ATTACHMENT0,J,te);else xe(z.__webglFramebuffer,R,b,i.COLOR_ATTACHMENT0,J,0);g(b)&&v(J),t.unbindTexture()}R.depthBuffer&&He(R)}function Je(R){let b=R.textures;for(let z=0,W=b.length;z<W;z++){let Z=b[z];if(g(Z)){let se=S(R),oe=n.get(Z).__webglTexture;t.bindTexture(se,oe),v(se),t.unbindTexture()}}}let vt=[],Ht=[];function _i(R){if(R.samples>0){if(Dt(R)===!1){let b=R.textures,z=R.width,W=R.height,Z=i.COLOR_BUFFER_BIT,se=R.stencilBuffer?i.DEPTH_STENCIL_ATTACHMENT:i.DEPTH_ATTACHMENT,oe=n.get(R),J=b.length>1;if(J)for(let le=0;le<b.length;le++)t.bindFramebuffer(i.FRAMEBUFFER,oe.__webglMultisampledFramebuffer),i.framebufferRenderbuffer(i.FRAMEBUFFER,i.COLOR_ATTACHMENT0+le,i.RENDERBUFFER,null),t.bindFramebuffer(i.FRAMEBUFFER,oe.__webglFramebuffer),i.framebufferTexture2D(i.DRAW_FRAMEBUFFER,i.COLOR_ATTACHMENT0+le,i.TEXTURE_2D,null,0);t.bindFramebuffer(i.READ_FRAMEBUFFER,oe.__webglMultisampledFramebuffer);let te=R.texture.mipmaps;te&&te.length>0?t.bindFramebuffer(i.DRAW_FRAMEBUFFER,oe.__webglFramebuffer[0]):t.bindFramebuffer(i.DRAW_FRAMEBUFFER,oe.__webglFramebuffer);for(let le=0;le<b.length;le++){if(R.resolveDepthBuffer&&(R.depthBuffer&&(Z|=i.DEPTH_BUFFER_BIT),R.stencilBuffer&&R.resolveStencilBuffer&&(Z|=i.STENCIL_BUFFER_BIT)),J){i.framebufferRenderbuffer(i.READ_FRAMEBUFFER,i.COLOR_ATTACHMENT0,i.RENDERBUFFER,oe.__webglColorRenderbuffer[le]);let Re=n.get(b[le]).__webglTexture;i.framebufferTexture2D(i.DRAW_FRAMEBUFFER,i.COLOR_ATTACHMENT0,i.TEXTURE_2D,Re,0)}i.blitFramebuffer(0,0,z,W,0,0,z,W,Z,i.NEAREST),l===!0&&(vt.length=0,Ht.length=0,vt.push(i.COLOR_ATTACHMENT0+le),R.depthBuffer&&R.storeMultisampledDepthBuffer===!1&&(vt.push(se),Ht.push(se),i.invalidateFramebuffer(i.DRAW_FRAMEBUFFER,Ht)),i.invalidateFramebuffer(i.READ_FRAMEBUFFER,vt))}if(t.bindFramebuffer(i.READ_FRAMEBUFFER,null),t.bindFramebuffer(i.DRAW_FRAMEBUFFER,null),J)for(let le=0;le<b.length;le++){t.bindFramebuffer(i.FRAMEBUFFER,oe.__webglMultisampledFramebuffer),i.framebufferRenderbuffer(i.FRAMEBUFFER,i.COLOR_ATTACHMENT0+le,i.RENDERBUFFER,oe.__webglColorRenderbuffer[le]);let Re=n.get(b[le]).__webglTexture;t.bindFramebuffer(i.FRAMEBUFFER,oe.__webglFramebuffer),i.framebufferTexture2D(i.DRAW_FRAMEBUFFER,i.COLOR_ATTACHMENT0+le,i.TEXTURE_2D,Re,0)}t.bindFramebuffer(i.DRAW_FRAMEBUFFER,oe.__webglMultisampledFramebuffer)}else if(R.depthBuffer&&R.storeMultisampledDepthBuffer===!1&&l){let b=R.stencilBuffer?i.DEPTH_STENCIL_ATTACHMENT:i.DEPTH_ATTACHMENT;i.invalidateFramebuffer(i.DRAW_FRAMEBUFFER,[b])}}}function wt(R){return Math.min(r.maxSamples,R.samples)}function Dt(R){let b=n.get(R);return R.samples>0&&e.has("WEBGL_multisampled_render_to_texture")===!0&&b.__useRenderToTexture!==!1}function B(R){let b=a.render.frame;h.get(R)!==b&&(h.set(R,b),R.update())}function Qt(R,b){let z=R.colorSpace,W=R.format,Z=R.type;return R.isCompressedTexture===!0||R.isVideoTexture===!0||z!==li&&z!==Dn&&(je.getTransfer(z)===rt?(W!==Ri||Z!==di)&&Ce("WebGLTextures: sRGB encoded textures have to use RGBAFormat and UnsignedByteType."):Fe("WebGLTextures: Unsupported texture color space:",z)),b}function lt(R){return typeof HTMLImageElement<"u"&&R instanceof HTMLImageElement?(c.width=R.naturalWidth||R.width,c.height=R.naturalHeight||R.height):typeof VideoFrame<"u"&&R instanceof VideoFrame?(c.width=R.displayWidth,c.height=R.displayHeight):(c.width=R.width,c.height=R.height),c}this.allocateTextureUnit=H,this.resetTextureUnits=I,this.getTextureUnits=L,this.setTextureUnits=k,this.setTexture2D=Y,this.setTexture2DArray=q,this.setTexture3D=K,this.setTextureCube=N,this.rebindTextures=Qe,this.setupRenderTarget=dt,this.updateRenderTargetMipmap=Je,this.updateMultisampleRenderTarget=_i,this.setupDepthRenderbuffer=He,this.setupFrameBufferTexture=xe,this.useMultisampledRTT=Dt,this.isReversedDepthBuffer=function(){return t.buffers.depth.getReversed()}}function bw(i,e){function t(n,r=Dn){let s,a=je.getTransfer(r);if(n===di)return i.UNSIGNED_BYTE;if(n===Hl)return i.UNSIGNED_SHORT_4_4_4_4;if(n===Wl)return i.UNSIGNED_SHORT_5_5_5_1;if(n===Hu)return i.UNSIGNED_INT_5_9_9_9_REV;if(n===Wu)return i.UNSIGNED_INT_10F_11F_11F_REV;if(n===Vu)return i.BYTE;if(n===Gu)return i.SHORT;if(n===Ns)return i.UNSIGNED_SHORT;if(n===Gl)return i.INT;if(n===qi)return i.UNSIGNED_INT;if(n===fi)return i.FLOAT;if(n===ji)return i.HALF_FLOAT;if(n===Xu)return i.ALPHA;if(n===qu)return i.RGB;if(n===Ri)return i.RGBA;if(n===tn)return i.DEPTH_COMPONENT;if(n===ar)return i.DEPTH_STENCIL;if(n===Os)return i.RED;if(n===Xl)return i.RED_INTEGER;if(n===Ln)return i.RG;if(n===ql)return i.RG_INTEGER;if(n===Va)return i.RGBA_INTEGER;if(n===Ga||n===Ha||n===Wa||n===Xa)if(a===rt)if(s=e.get("WEBGL_compressed_texture_s3tc_srgb"),s!==null){if(n===Ga)return s.COMPRESSED_SRGB_S3TC_DXT1_EXT;if(n===Ha)return s.COMPRESSED_SRGB_ALPHA_S3TC_DXT1_EXT;if(n===Wa)return s.COMPRESSED_SRGB_ALPHA_S3TC_DXT3_EXT;if(n===Xa)return s.COMPRESSED_SRGB_ALPHA_S3TC_DXT5_EXT}else return null;else if(s=e.get("WEBGL_compressed_texture_s3tc"),s!==null){if(n===Ga)return s.COMPRESSED_RGB_S3TC_DXT1_EXT;if(n===Ha)return s.COMPRESSED_RGBA_S3TC_DXT1_EXT;if(n===Wa)return s.COMPRESSED_RGBA_S3TC_DXT3_EXT;if(n===Xa)return s.COMPRESSED_RGBA_S3TC_DXT5_EXT}else return null;if(n===jl||n===Yl||n===$l||n===Zl)if(s=e.get("WEBGL_compressed_texture_pvrtc"),s!==null){if(n===jl)return s.COMPRESSED_RGB_PVRTC_4BPPV1_IMG;if(n===Yl)return s.COMPRESSED_RGB_PVRTC_2BPPV1_IMG;if(n===$l)return s.COMPRESSED_RGBA_PVRTC_4BPPV1_IMG;if(n===Zl)return s.COMPRESSED_RGBA_PVRTC_2BPPV1_IMG}else return null;if(n===Kl||n===Jl||n===Ql||n===ec||n===tc||n===qa||n===ic)if(s=e.get("WEBGL_compressed_texture_etc"),s!==null){if(n===Kl||n===Jl)return a===rt?s.COMPRESSED_SRGB8_ETC2:s.COMPRESSED_RGB8_ETC2;if(n===Ql)return a===rt?s.COMPRESSED_SRGB8_ALPHA8_ETC2_EAC:s.COMPRESSED_RGBA8_ETC2_EAC;if(n===ec)return s.COMPRESSED_R11_EAC;if(n===tc)return s.COMPRESSED_SIGNED_R11_EAC;if(n===qa)return s.COMPRESSED_RG11_EAC;if(n===ic)return s.COMPRESSED_SIGNED_RG11_EAC}else return null;if(n===nc||n===rc||n===sc||n===ac||n===oc||n===lc||n===cc||n===hc||n===uc||n===dc||n===fc||n===pc||n===mc||n===gc)if(s=e.get("WEBGL_compressed_texture_astc"),s!==null){if(n===nc)return a===rt?s.COMPRESSED_SRGB8_ALPHA8_ASTC_4x4_KHR:s.COMPRESSED_RGBA_ASTC_4x4_KHR;if(n===rc)return a===rt?s.COMPRESSED_SRGB8_ALPHA8_ASTC_5x4_KHR:s.COMPRESSED_RGBA_ASTC_5x4_KHR;if(n===sc)return a===rt?s.COMPRESSED_SRGB8_ALPHA8_ASTC_5x5_KHR:s.COMPRESSED_RGBA_ASTC_5x5_KHR;if(n===ac)return a===rt?s.COMPRESSED_SRGB8_ALPHA8_ASTC_6x5_KHR:s.COMPRESSED_RGBA_ASTC_6x5_KHR;if(n===oc)return a===rt?s.COMPRESSED_SRGB8_ALPHA8_ASTC_6x6_KHR:s.COMPRESSED_RGBA_ASTC_6x6_KHR;if(n===lc)return a===rt?s.COMPRESSED_SRGB8_ALPHA8_ASTC_8x5_KHR:s.COMPRESSED_RGBA_ASTC_8x5_KHR;if(n===cc)return a===rt?s.COMPRESSED_SRGB8_ALPHA8_ASTC_8x6_KHR:s.COMPRESSED_RGBA_ASTC_8x6_KHR;if(n===hc)return a===rt?s.COMPRESSED_SRGB8_ALPHA8_ASTC_8x8_KHR:s.COMPRESSED_RGBA_ASTC_8x8_KHR;if(n===uc)return a===rt?s.COMPRESSED_SRGB8_ALPHA8_ASTC_10x5_KHR:s.COMPRESSED_RGBA_ASTC_10x5_KHR;if(n===dc)return a===rt?s.COMPRESSED_SRGB8_ALPHA8_ASTC_10x6_KHR:s.COMPRESSED_RGBA_ASTC_10x6_KHR;if(n===fc)return a===rt?s.COMPRESSED_SRGB8_ALPHA8_ASTC_10x8_KHR:s.COMPRESSED_RGBA_ASTC_10x8_KHR;if(n===pc)return a===rt?s.COMPRESSED_SRGB8_ALPHA8_ASTC_10x10_KHR:s.COMPRESSED_RGBA_ASTC_10x10_KHR;if(n===mc)return a===rt?s.COMPRESSED_SRGB8_ALPHA8_ASTC_12x10_KHR:s.COMPRESSED_RGBA_ASTC_12x10_KHR;if(n===gc)return a===rt?s.COMPRESSED_SRGB8_ALPHA8_ASTC_12x12_KHR:s.COMPRESSED_RGBA_ASTC_12x12_KHR}else return null;if(n===yc||n===_c||n===xc)if(s=e.get("EXT_texture_compression_bptc"),s!==null){if(n===yc)return a===rt?s.COMPRESSED_SRGB_ALPHA_BPTC_UNORM_EXT:s.COMPRESSED_RGBA_BPTC_UNORM_EXT;if(n===_c)return s.COMPRESSED_RGB_BPTC_SIGNED_FLOAT_EXT;if(n===xc)return s.COMPRESSED_RGB_BPTC_UNSIGNED_FLOAT_EXT}else return null;if(n===vc||n===bc||n===ja||n===Sc)if(s=e.get("EXT_texture_compression_rgtc"),s!==null){if(n===vc)return s.COMPRESSED_RED_RGTC1_EXT;if(n===bc)return s.COMPRESSED_SIGNED_RED_RGTC1_EXT;if(n===ja)return s.COMPRESSED_RED_GREEN_RGTC2_EXT;if(n===Sc)return s.COMPRESSED_SIGNED_RED_GREEN_RGTC2_EXT}else return null;return n===Us?i.UNSIGNED_INT_24_8:i[n]!==void 0?i[n]:null}return{convert:t}}var Sw=`
void main() {

	gl_Position = vec4( position, 1.0 );

}`,Mw=`
uniform sampler2DArray depthColor;
uniform float depthWidth;
uniform float depthHeight;

void main() {

	vec2 coord = vec2( gl_FragCoord.x / depthWidth, gl_FragCoord.y / depthHeight );

	if ( coord.x >= 1.0 ) {

		gl_FragDepth = texture( depthColor, vec3( coord.x - 1.0, coord.y, 1 ) ).r;

	} else {

		gl_FragDepth = texture( depthColor, vec3( coord.x, coord.y, 0 ) ).r;

	}

}`,_d=class{constructor(){this.texture=null,this.mesh=null,this.depthNear=0,this.depthFar=0}init(e,t){if(this.texture===null){let n=new Ea(e.texture);(e.depthNear!==t.depthNear||e.depthFar!==t.depthFar)&&(this.depthNear=e.depthNear,this.depthFar=e.depthFar),this.texture=n}}getMesh(e){if(this.texture!==null&&this.mesh===null){let t=e.cameras[0].viewport,n=new $t({vertexShader:Sw,fragmentShader:Mw,uniforms:{depthColor:{value:this.texture},depthWidth:{value:t.z},depthHeight:{value:t.w}}});this.mesh=new at(new Dr(20,20),n)}return this.mesh}reset(){this.texture=null,this.mesh=null}getDepthTexture(){return this.texture}},xd=class extends jt{constructor(e,t){super();let n=this,r=null,s=1,a=null,o="local-floor",l=1,c=null,h=null,u=null,d=null,f=null,p=null,y=typeof XRWebGLBinding<"u",m=new _d,g={},v=t.getContextAttributes(),S=null,_=null,M=[],w=[],E=new Se,x=null,A=null,C=new Rt;C.viewport=new Xe;let D=new Rt;D.viewport=new Xe;let U=[C,D],I=new Ul,L=null,k=null;this.cameraAutoUpdate=!0,this.enabled=!1,this.isPresenting=!1,this.getController=function($){let ee=M[$];return ee===void 0&&(ee=new Ts,M[$]=ee),ee.getTargetRaySpace()},this.getControllerGrip=function($){let ee=M[$];return ee===void 0&&(ee=new Ts,M[$]=ee),ee.getGripSpace()},this.getHand=function($){let ee=M[$];return ee===void 0&&(ee=new Ts,M[$]=ee),ee.getHandSpace()};function H($){let ee=w.indexOf($.inputSource);if(ee===-1)return;let _e=M[ee];_e!==void 0&&(_e.update($.inputSource,$.frame,c||a),_e.dispatchEvent({type:$.type,data:$.inputSource}))}function X(){r.removeEventListener("select",H),r.removeEventListener("selectstart",H),r.removeEventListener("selectend",H),r.removeEventListener("squeeze",H),r.removeEventListener("squeezestart",H),r.removeEventListener("squeezeend",H),r.removeEventListener("end",X),r.removeEventListener("inputsourceschange",Y);for(let $=0;$<M.length;$++){let ee=w[$];ee!==null&&(w[$]=null,M[$].disconnect(ee))}L=null,k=null,m.reset();for(let $ in g)delete g[$];if(e.setRenderTarget(S),f=null,d=null,u=null,r=null,_=null,$e.stop(),n.isPresenting=!1,e.setPixelRatio(x),e.setSize(E.width,E.height,!1),A!==null){let $=A.camera;$.fov=A.fov,$.zoom=A.zoom,$.updateProjectionMatrix(),A=null}n.dispatchEvent({type:"sessionend"})}this.setFramebufferScaleFactor=function($){s=$,n.isPresenting===!0&&Ce("WebXRManager: Cannot change framebuffer scale while presenting.")},this.setReferenceSpaceType=function($){o=$,n.isPresenting===!0&&Ce("WebXRManager: Cannot change reference space type while presenting.")},this.getReferenceSpace=function(){return c||a},this.setReferenceSpace=function($){c=$},this.getBaseLayer=function(){return d!==null?d:f},this.getBinding=function(){return u===null&&y&&(u=new XRWebGLBinding(r,t)),u},this.getFrame=function(){return p},this.getSession=function(){return r},this.setSession=async function($){if(r=$,r!==null){if(S=e.getRenderTarget(),r.addEventListener("select",H),r.addEventListener("selectstart",H),r.addEventListener("selectend",H),r.addEventListener("squeeze",H),r.addEventListener("squeezestart",H),r.addEventListener("squeezeend",H),r.addEventListener("end",X),r.addEventListener("inputsourceschange",Y),v.xrCompatible!==!0&&await t.makeXRCompatible(),x=e.getPixelRatio(),e.getSize(E),y&&"createProjectionLayer"in XRWebGLBinding.prototype){let _e=null,Be=null,xe=null;v.depth&&(xe=v.stencil?t.DEPTH24_STENCIL8:t.DEPTH_COMPONENT24,_e=v.stencil?ar:tn,Be=v.stencil?Us:qi);let Ve={colorFormat:t.RGBA8,depthFormat:xe,scaleFactor:s};u=this.getBinding(),d=u.createProjectionLayer(Ve),r.updateRenderState({layers:[d]}),e.setPixelRatio(1),e.setSize(d.textureWidth,d.textureHeight,!1),_=new ci(d.textureWidth,d.textureHeight,{format:Ri,type:di,depthTexture:new Jn(d.textureWidth,d.textureHeight,Be,void 0,void 0,void 0,void 0,void 0,void 0,_e),stencilBuffer:v.stencil,colorSpace:e.outputColorSpace,samples:v.antialias?4:0,resolveDepthBuffer:d.ignoreDepthValues===!1,resolveStencilBuffer:d.ignoreDepthValues===!1,storeMultisampledDepthBuffer:d.ignoreDepthValues===!1,storeMultisampledStencilBuffer:d.ignoreDepthValues===!1})}else{let _e={antialias:v.antialias,alpha:!0,depth:v.depth,stencil:v.stencil,framebufferScaleFactor:s};f=new XRWebGLLayer(r,t,_e),r.updateRenderState({baseLayer:f}),e.setPixelRatio(1),e.setSize(f.framebufferWidth,f.framebufferHeight,!1),_=new ci(f.framebufferWidth,f.framebufferHeight,{format:Ri,type:di,colorSpace:e.outputColorSpace,stencilBuffer:v.stencil,resolveDepthBuffer:f.ignoreDepthValues===!1,resolveStencilBuffer:f.ignoreDepthValues===!1,storeMultisampledDepthBuffer:f.ignoreDepthValues===!1,storeMultisampledStencilBuffer:f.ignoreDepthValues===!1})}_.isXRRenderTarget=!0,this.setFoveation(l),c=null,a=await r.requestReferenceSpace(o),$e.setContext(r),$e.start(),n.isPresenting=!0,n.dispatchEvent({type:"sessionstart"})}},this.getEnvironmentBlendMode=function(){if(r!==null)return r.environmentBlendMode},this.getDepthTexture=function(){return m.getDepthTexture()};function Y($){for(let ee=0;ee<$.removed.length;ee++){let _e=$.removed[ee],Be=w.indexOf(_e);Be>=0&&(w[Be]=null,M[Be].disconnect(_e))}for(let ee=0;ee<$.added.length;ee++){let _e=$.added[ee],Be=w.indexOf(_e);if(Be===-1){for(let Ve=0;Ve<M.length;Ve++)if(Ve>=w.length){w.push(_e),Be=Ve;break}else if(w[Ve]===null){w[Ve]=_e,Be=Ve;break}if(Be===-1)break}let xe=M[Be];xe&&xe.connect(_e)}}let q=new P,K=new P;function N($,ee,_e){q.setFromMatrixPosition(ee.matrixWorld),K.setFromMatrixPosition(_e.matrixWorld);let Be=q.distanceTo(K),xe=ee.projectionMatrix.elements,Ve=_e.projectionMatrix.elements,gt=xe[14]/(xe[10]-1),He=xe[14]/(xe[10]+1),Qe=(xe[9]+1)/xe[5],dt=(xe[9]-1)/xe[5],Je=(xe[8]-1)/xe[0],vt=(Ve[8]+1)/Ve[0],Ht=gt*Je,_i=gt*vt,wt=Be/(-Je+vt),Dt=wt*-Je;if(ee.matrixWorld.decompose($.position,$.quaternion,$.scale),$.translateX(Dt),$.translateZ(wt),$.matrixWorld.compose($.position,$.quaternion,$.scale),$.matrixWorldInverse.copy($.matrixWorld).invert(),xe[10]===-1)$.projectionMatrix.copy(ee.projectionMatrix),$.projectionMatrixInverse.copy(ee.projectionMatrixInverse);else{let B=gt+wt,Qt=He+wt,lt=Ht-Dt,R=_i+(Be-Dt),b=Qe*He/Qt*B,z=dt*He/Qt*B;$.projectionMatrix.makePerspective(lt,R,b,z,B,Qt),$.projectionMatrixInverse.copy($.projectionMatrix).invert()}}function ie($,ee){ee===null?$.matrixWorld.copy($.matrix):$.matrixWorld.multiplyMatrices(ee.matrixWorld,$.matrix),$.matrixWorldInverse.copy($.matrixWorld).invert()}this.updateCamera=function($){if(r===null)return;let ee=$.near,_e=$.far;m.texture!==null&&(m.depthNear>0&&(ee=m.depthNear),m.depthFar>0&&(_e=m.depthFar)),I.near=D.near=C.near=ee,I.far=D.far=C.far=_e,(L!==I.near||k!==I.far)&&(r.updateRenderState({depthNear:I.near,depthFar:I.far}),L=I.near,k=I.far),I.layers.mask=$.layers.mask|6,C.layers.mask=I.layers.mask&-5,D.layers.mask=I.layers.mask&-3;let Be=$.parent,xe=I.cameras;ie(I,Be);for(let Ve=0;Ve<xe.length;Ve++)ie(xe[Ve],Be);xe.length===2?N(I,C,D):I.projectionMatrix.copy(C.projectionMatrix),A===null&&$.isPerspectiveCamera&&(A={camera:$,fov:$.fov,zoom:$.zoom}),re($,I,Be)};function re($,ee,_e){_e===null?$.matrix.copy(ee.matrixWorld):($.matrix.copy(_e.matrixWorld),$.matrix.invert(),$.matrix.multiply(ee.matrixWorld)),$.matrix.decompose($.position,$.quaternion,$.scale),$.updateMatrixWorld(!0),$.projectionMatrix.copy(ee.projectionMatrix),$.projectionMatrixInverse.copy(ee.projectionMatrixInverse),$.isPerspectiveCamera&&($.fov=Er*2*Math.atan(1/$.projectionMatrix.elements[5]),$.zoom=1)}this.getCamera=function(){return I},this.getFoveation=function(){if(!(d===null&&f===null))return l},this.setFoveation=function($){l=$,d!==null&&(d.fixedFoveation=$),f!==null&&f.fixedFoveation!==void 0&&(f.fixedFoveation=$)},this.hasDepthSensing=function(){return m.texture!==null},this.getDepthSensingMesh=function(){return m.getMesh(I)},this.getCameraTexture=function($){return g[$]};let De=null;function Te($,ee){if(h=ee.getViewerPose(c||a),p=ee,h!==null){let _e=h.views;f!==null&&(e.setRenderTargetFramebuffer(_,f.framebuffer),e.setRenderTarget(_));let Be=!1;_e.length!==I.cameras.length&&(I.cameras.length=0,Be=!0);for(let He=0;He<_e.length;He++){let Qe=_e[He],dt=null;if(f!==null)dt=f.getViewport(Qe);else{let vt=u.getViewSubImage(d,Qe);dt=vt.viewport,He===0&&(e.setRenderTargetTextures(_,vt.colorTexture,vt.depthStencilTexture),e.setRenderTarget(_))}let Je=U[He];Je===void 0&&(Je=new Rt,Je.layers.enable(He),Je.viewport=new Xe,U[He]=Je),Je.matrix.fromArray(Qe.transform.matrix),Je.matrix.decompose(Je.position,Je.quaternion,Je.scale),Je.projectionMatrix.fromArray(Qe.projectionMatrix),Je.projectionMatrixInverse.copy(Je.projectionMatrix).invert(),Je.viewport.set(dt.x,dt.y,dt.width,dt.height),He===0&&(I.matrix.copy(Je.matrix),I.matrix.decompose(I.position,I.quaternion,I.scale)),Be===!0&&I.cameras.push(Je)}let xe=r.enabledFeatures;if(xe&&xe.includes("depth-sensing")&&r.depthUsage=="gpu-optimized"&&y){u=n.getBinding();let He=u.getDepthInformation(_e[0]);He&&He.isValid&&He.texture&&m.init(He,r.renderState)}if(xe&&xe.includes("camera-access")&&y){e.state.unbindTexture(),u=n.getBinding();for(let He=0;He<_e.length;He++){let Qe=_e[He].camera;if(Qe){let dt=g[Qe];dt||(dt=new Ea,g[Qe]=dt);let Je=u.getCameraImage(Qe);dt.sourceTexture=Je}}}}for(let _e=0;_e<M.length;_e++){let Be=w[_e],xe=M[_e];Be!==null&&xe!==void 0&&xe.update(Be,ee,c||a)}De&&De($,ee),ee.detectedPlanes&&n.dispatchEvent({type:"planesdetected",data:ee}),p=null}let $e=new Sg;$e.setAnimationLoop(Te),this.setAnimationLoop=function($){De=$},this.dispose=function(){}}},ww=new ge,Cg=new Oe;Cg.set(-1,0,0,0,1,0,0,0,1);function Tw(i,e){function t(m,g){m.matrixAutoUpdate===!0&&m.updateMatrix(),g.value.copy(m.matrix)}function n(m,g){g.color.getRGB(m.fogColor.value,Ku(i)),g.isFog?(m.fogNear.value=g.near,m.fogFar.value=g.far):g.isFogExp2&&(m.fogDensity.value=g.density)}function r(m,g,v,S,_){g.isNodeMaterial?g.uniformsNeedUpdate=!1:g.isMeshBasicMaterial?s(m,g):g.isMeshLambertMaterial?(s(m,g),g.envMap&&(m.envMapIntensity.value=g.envMapIntensity)):g.isMeshToonMaterial?(s(m,g),u(m,g)):g.isMeshPhongMaterial?(s(m,g),h(m,g),g.envMap&&(m.envMapIntensity.value=g.envMapIntensity)):g.isMeshStandardMaterial?(s(m,g),d(m,g),g.isMeshPhysicalMaterial&&f(m,g,_)):g.isMeshMatcapMaterial?(s(m,g),p(m,g)):g.isMeshDepthMaterial?s(m,g):g.isMeshDistanceMaterial?(s(m,g),y(m,g)):g.isMeshNormalMaterial?s(m,g):g.isLineBasicMaterial?(a(m,g),g.isLineDashedMaterial&&o(m,g)):g.isPointsMaterial?l(m,g,v,S):g.isSpriteMaterial?c(m,g):g.isShadowMaterial?(m.color.value.copy(g.color),m.opacity.value=g.opacity):g.isShaderMaterial&&(g.uniformsNeedUpdate=!1)}function s(m,g){m.opacity.value=g.opacity,g.color&&m.diffuse.value.copy(g.color),g.emissive&&m.emissive.value.copy(g.emissive).multiplyScalar(g.emissiveIntensity),g.map&&(m.map.value=g.map,t(g.map,m.mapTransform)),g.alphaMap&&(m.alphaMap.value=g.alphaMap,t(g.alphaMap,m.alphaMapTransform)),g.bumpMap&&(m.bumpMap.value=g.bumpMap,t(g.bumpMap,m.bumpMapTransform),m.bumpScale.value=g.bumpScale,g.side===ui&&(m.bumpScale.value*=-1)),g.normalMap&&(m.normalMap.value=g.normalMap,t(g.normalMap,m.normalMapTransform),m.normalScale.value.copy(g.normalScale),g.side===ui&&m.normalScale.value.negate()),g.displacementMap&&(m.displacementMap.value=g.displacementMap,t(g.displacementMap,m.displacementMapTransform),m.displacementScale.value=g.displacementScale,m.displacementBias.value=g.displacementBias),g.emissiveMap&&(m.emissiveMap.value=g.emissiveMap,t(g.emissiveMap,m.emissiveMapTransform)),g.specularMap&&(m.specularMap.value=g.specularMap,t(g.specularMap,m.specularMapTransform)),g.alphaTest>0&&(m.alphaTest.value=g.alphaTest);let v=e.get(g),S=v.envMap,_=v.envMapRotation;S&&(m.envMap.value=S,m.envMapRotation.value.setFromMatrix4(ww.makeRotationFromEuler(_)).transpose(),S.isCubeTexture&&S.isRenderTargetTexture===!1&&m.envMapRotation.value.premultiply(Cg),m.reflectivity.value=g.reflectivity,m.ior.value=g.ior,m.refractionRatio.value=g.refractionRatio),g.lightMap&&(m.lightMap.value=g.lightMap,m.lightMapIntensity.value=g.lightMapIntensity,t(g.lightMap,m.lightMapTransform)),g.aoMap&&(m.aoMap.value=g.aoMap,m.aoMapIntensity.value=g.aoMapIntensity,t(g.aoMap,m.aoMapTransform))}function a(m,g){m.diffuse.value.copy(g.color),m.opacity.value=g.opacity,g.map&&(m.map.value=g.map,t(g.map,m.mapTransform))}function o(m,g){m.dashSize.value=g.dashSize,m.totalSize.value=g.dashSize+g.gapSize,m.scale.value=g.scale}function l(m,g,v,S){m.diffuse.value.copy(g.color),m.opacity.value=g.opacity,m.size.value=g.size*v,m.scale.value=S*.5,g.map&&(m.map.value=g.map,t(g.map,m.uvTransform)),g.alphaMap&&(m.alphaMap.value=g.alphaMap,t(g.alphaMap,m.alphaMapTransform)),g.alphaTest>0&&(m.alphaTest.value=g.alphaTest)}function c(m,g){m.diffuse.value.copy(g.color),m.opacity.value=g.opacity,m.rotation.value=g.rotation,g.map&&(m.map.value=g.map,t(g.map,m.mapTransform)),g.alphaMap&&(m.alphaMap.value=g.alphaMap,t(g.alphaMap,m.alphaMapTransform)),g.alphaTest>0&&(m.alphaTest.value=g.alphaTest)}function h(m,g){m.specular.value.copy(g.specular),m.shininess.value=Math.max(g.shininess,1e-4)}function u(m,g){g.gradientMap&&(m.gradientMap.value=g.gradientMap)}function d(m,g){m.metalness.value=g.metalness,g.metalnessMap&&(m.metalnessMap.value=g.metalnessMap,t(g.metalnessMap,m.metalnessMapTransform)),m.roughness.value=g.roughness,g.roughnessMap&&(m.roughnessMap.value=g.roughnessMap,t(g.roughnessMap,m.roughnessMapTransform)),g.envMap&&(m.envMapIntensity.value=g.envMapIntensity)}function f(m,g,v){m.ior.value=g.ior,g.sheen>0&&(m.sheenColor.value.copy(g.sheenColor).multiplyScalar(g.sheen),m.sheenRoughness.value=g.sheenRoughness,g.sheenColorMap&&(m.sheenColorMap.value=g.sheenColorMap,t(g.sheenColorMap,m.sheenColorMapTransform)),g.sheenRoughnessMap&&(m.sheenRoughnessMap.value=g.sheenRoughnessMap,t(g.sheenRoughnessMap,m.sheenRoughnessMapTransform))),g.clearcoat>0&&(m.clearcoat.value=g.clearcoat,m.clearcoatRoughness.value=g.clearcoatRoughness,g.clearcoatMap&&(m.clearcoatMap.value=g.clearcoatMap,t(g.clearcoatMap,m.clearcoatMapTransform)),g.clearcoatRoughnessMap&&(m.clearcoatRoughnessMap.value=g.clearcoatRoughnessMap,t(g.clearcoatRoughnessMap,m.clearcoatRoughnessMapTransform)),g.clearcoatNormalMap&&(m.clearcoatNormalMap.value=g.clearcoatNormalMap,t(g.clearcoatNormalMap,m.clearcoatNormalMapTransform),m.clearcoatNormalScale.value.copy(g.clearcoatNormalScale),g.side===ui&&m.clearcoatNormalScale.value.negate())),g.dispersion>0&&(m.dispersion.value=g.dispersion),g.retroreflectivity>0&&(m.retroreflectivity.value=g.retroreflectivity),g.iridescence>0&&(m.iridescence.value=g.iridescence,m.iridescenceIOR.value=g.iridescenceIOR,m.iridescenceThicknessMinimum.value=g.iridescenceThicknessRange[0],m.iridescenceThicknessMaximum.value=g.iridescenceThicknessRange[1],g.iridescenceMap&&(m.iridescenceMap.value=g.iridescenceMap,t(g.iridescenceMap,m.iridescenceMapTransform)),g.iridescenceThicknessMap&&(m.iridescenceThicknessMap.value=g.iridescenceThicknessMap,t(g.iridescenceThicknessMap,m.iridescenceThicknessMapTransform))),g.transmission>0&&(m.transmission.value=g.transmission,m.transmissionSamplerMap.value=v.texture,m.transmissionSamplerSize.value.set(v.width,v.height),g.transmissionMap&&(m.transmissionMap.value=g.transmissionMap,t(g.transmissionMap,m.transmissionMapTransform)),m.thickness.value=g.thickness,g.thicknessMap&&(m.thicknessMap.value=g.thicknessMap,t(g.thicknessMap,m.thicknessMapTransform)),m.attenuationDistance.value=g.attenuationDistance,m.attenuationColor.value.copy(g.attenuationColor)),g.anisotropy>0&&(m.anisotropyVector.value.set(g.anisotropy*Math.cos(g.anisotropyRotation),g.anisotropy*Math.sin(g.anisotropyRotation)),g.anisotropyMap&&(m.anisotropyMap.value=g.anisotropyMap,t(g.anisotropyMap,m.anisotropyMapTransform))),m.specularIntensity.value=g.specularIntensity,m.specularColor.value.copy(g.specularColor),g.specularColorMap&&(m.specularColorMap.value=g.specularColorMap,t(g.specularColorMap,m.specularColorMapTransform)),g.specularIntensityMap&&(m.specularIntensityMap.value=g.specularIntensityMap,t(g.specularIntensityMap,m.specularIntensityMapTransform))}function p(m,g){g.matcap&&(m.matcap.value=g.matcap)}function y(m,g){let v=e.get(g).light;m.referencePosition.value.setFromMatrixPosition(v.matrixWorld),m.nearDistance.value=v.shadow.camera.near,m.farDistance.value=v.shadow.camera.far}return{refreshFogUniforms:n,refreshMaterialUniforms:r}}function Ew(i,e,t,n){let r={},s={},a=[],o=i.getParameter(i.MAX_UNIFORM_BUFFER_BINDINGS);function l(_,M){let w=M.program;n.uniformBlockBinding(_,w)}function c(_,M){let w=r[_.id];w===void 0&&(m(_),w=h(_),r[_.id]=w,_.addEventListener("dispose",v));let E=M.program;n.updateUBOMapping(_,E);let x=e.render.frame;s[_.id]!==x&&(d(_),s[_.id]=x)}function h(_){let M=u();_.__bindingPointIndex=M;let w=i.createBuffer(),E=_.__size,x=_.usage;return i.bindBuffer(i.UNIFORM_BUFFER,w),i.bufferData(i.UNIFORM_BUFFER,E,x),i.bindBuffer(i.UNIFORM_BUFFER,null),i.bindBufferBase(i.UNIFORM_BUFFER,M,w),w}function u(){for(let _=0;_<o;_++)if(a.indexOf(_)===-1)return a.push(_),_;return Fe("WebGLRenderer: Maximum number of simultaneously usable uniforms groups reached."),0}function d(_){let M=r[_.id],w=_.uniforms,E=_.__cache;i.bindBuffer(i.UNIFORM_BUFFER,M);for(let x=0,A=w.length;x<A;x++){let C=w[x];if(Array.isArray(C))for(let D=0,U=C.length;D<U;D++)f(C[D],x,D,E);else f(C,x,0,E)}i.bindBuffer(i.UNIFORM_BUFFER,null)}function f(_,M,w,E){if(y(_,M,w,E)===!0){let x=_.__offset,A=_.value;if(Array.isArray(A)){let C=0;for(let D=0;D<A.length;D++){let U=A[D],I=g(U);p(U,_.__data,C),typeof U!="number"&&typeof U!="boolean"&&!U.isMatrix3&&!ArrayBuffer.isView(U)&&(C+=I.storage/Float32Array.BYTES_PER_ELEMENT)}}else p(A,_.__data,0);i.bufferSubData(i.UNIFORM_BUFFER,x,_.__data)}}function p(_,M,w){typeof _=="number"||typeof _=="boolean"?M[0]=_:_.isMatrix3?(M[0]=_.elements[0],M[1]=_.elements[1],M[2]=_.elements[2],M[3]=0,M[4]=_.elements[3],M[5]=_.elements[4],M[6]=_.elements[5],M[7]=0,M[8]=_.elements[6],M[9]=_.elements[7],M[10]=_.elements[8],M[11]=0):ArrayBuffer.isView(_)?M.set(new _.constructor(_.buffer,_.byteOffset,M.length)):_.toArray(M,w)}function y(_,M,w,E){let x=_.value,A=M+"_"+w;if(E[A]===void 0)return typeof x=="number"||typeof x=="boolean"?E[A]=x:ArrayBuffer.isView(x)?E[A]=x.slice():E[A]=x.clone(),!0;{let C=E[A];if(typeof x=="number"||typeof x=="boolean"){if(C!==x)return E[A]=x,!0}else{if(ArrayBuffer.isView(x))return!0;if(C.equals(x)===!1)return C.copy(x),!0}}return!1}function m(_){let M=_.uniforms,w=0,E=16;for(let A=0,C=M.length;A<C;A++){let D=Array.isArray(M[A])?M[A]:[M[A]];for(let U=0,I=D.length;U<I;U++){let L=D[U],k=Array.isArray(L.value)?L.value:[L.value];for(let H=0,X=k.length;H<X;H++){let Y=k[H],q=g(Y),K=w%E,N=K%q.boundary,ie=K+N;w+=N,ie!==0&&E-ie<q.storage&&(w+=E-ie),L.__data=new Float32Array(q.storage/Float32Array.BYTES_PER_ELEMENT),L.__offset=w,w+=q.storage}}}let x=w%E;return x>0&&(w+=E-x),_.__size=w,_.__cache={},this}function g(_){let M={boundary:0,storage:0};return typeof _=="number"||typeof _=="boolean"?(M.boundary=4,M.storage=4):_.isVector2?(M.boundary=8,M.storage=8):_.isVector3||_.isColor?(M.boundary=16,M.storage=12):_.isVector4?(M.boundary=16,M.storage=16):_.isMatrix3?(M.boundary=48,M.storage=48):_.isMatrix4?(M.boundary=64,M.storage=64):_.isTexture?Ce("WebGLRenderer: Texture samplers can not be part of an uniforms group."):ArrayBuffer.isView(_)?(M.boundary=16,M.storage=_.byteLength):Ce("WebGLRenderer: Unsupported uniform value type.",_),M}function v(_){let M=_.target;M.removeEventListener("dispose",v);let w=a.indexOf(M.__bindingPointIndex);a.splice(w,1),i.deleteBuffer(r[M.id]),delete r[M.id],delete s[M.id]}function S(){for(let _ in r)i.deleteBuffer(r[_]);a=[],r={},s={}}return{bind:l,update:c,dispose:S}}var Aw=new Uint16Array([12469,15057,12620,14925,13266,14620,13807,14376,14323,13990,14545,13625,14713,13328,14840,12882,14931,12528,14996,12233,15039,11829,15066,11525,15080,11295,15085,10976,15082,10705,15073,10495,13880,14564,13898,14542,13977,14430,14158,14124,14393,13732,14556,13410,14702,12996,14814,12596,14891,12291,14937,11834,14957,11489,14958,11194,14943,10803,14921,10506,14893,10278,14858,9960,14484,14039,14487,14025,14499,13941,14524,13740,14574,13468,14654,13106,14743,12678,14818,12344,14867,11893,14889,11509,14893,11180,14881,10751,14852,10428,14812,10128,14765,9754,14712,9466,14764,13480,14764,13475,14766,13440,14766,13347,14769,13070,14786,12713,14816,12387,14844,11957,14860,11549,14868,11215,14855,10751,14825,10403,14782,10044,14729,9651,14666,9352,14599,9029,14967,12835,14966,12831,14963,12804,14954,12723,14936,12564,14917,12347,14900,11958,14886,11569,14878,11247,14859,10765,14828,10401,14784,10011,14727,9600,14660,9289,14586,8893,14508,8533,15111,12234,15110,12234,15104,12216,15092,12156,15067,12010,15028,11776,14981,11500,14942,11205,14902,10752,14861,10393,14812,9991,14752,9570,14682,9252,14603,8808,14519,8445,14431,8145,15209,11449,15208,11451,15202,11451,15190,11438,15163,11384,15117,11274,15055,10979,14994,10648,14932,10343,14871,9936,14803,9532,14729,9218,14645,8742,14556,8381,14461,8020,14365,7603,15273,10603,15272,10607,15267,10619,15256,10631,15231,10614,15182,10535,15118,10389,15042,10167,14963,9787,14883,9447,14800,9115,14710,8665,14615,8318,14514,7911,14411,7507,14279,7198,15314,9675,15313,9683,15309,9712,15298,9759,15277,9797,15229,9773,15166,9668,15084,9487,14995,9274,14898,8910,14800,8539,14697,8234,14590,7790,14479,7409,14367,7067,14178,6621,15337,8619,15337,8631,15333,8677,15325,8769,15305,8871,15264,8940,15202,8909,15119,8775,15022,8565,14916,8328,14804,8009,14688,7614,14569,7287,14448,6888,14321,6483,14088,6171,15350,7402,15350,7419,15347,7480,15340,7613,15322,7804,15287,7973,15229,8057,15148,8012,15046,7846,14933,7611,14810,7357,14682,7069,14552,6656,14421,6316,14251,5948,14007,5528,15356,5942,15356,5977,15353,6119,15348,6294,15332,6551,15302,6824,15249,7044,15171,7122,15070,7050,14949,6861,14818,6611,14679,6349,14538,6067,14398,5651,14189,5311,13935,4958,15359,4123,15359,4153,15356,4296,15353,4646,15338,5160,15311,5508,15263,5829,15188,6042,15088,6094,14966,6001,14826,5796,14678,5543,14527,5287,14377,4985,14133,4586,13869,4257,15360,1563,15360,1642,15358,2076,15354,2636,15341,3350,15317,4019,15273,4429,15203,4732,15105,4911,14981,4932,14836,4818,14679,4621,14517,4386,14359,4156,14083,3795,13808,3437,15360,122,15360,137,15358,285,15355,636,15344,1274,15322,2177,15281,2765,15215,3223,15120,3451,14995,3569,14846,3567,14681,3466,14511,3305,14344,3121,14037,2800,13753,2467,15360,0,15360,1,15359,21,15355,89,15346,253,15325,479,15287,796,15225,1148,15133,1492,15008,1749,14856,1882,14685,1886,14506,1783,14324,1608,13996,1398,13702,1183]),on=null;function Cw(){return on===null&&(on=new Sn(Aw,16,16,Ln,ji),on.name="DFG_LUT",on.minFilter=St,on.magFilter=St,on.wrapS=Li,on.wrapT=Li,on.generateMipmaps=!1,on.needsUpdate=!0),on}var eo=class{constructor(e={}){let{canvas:t=jm(),context:n=null,depth:r=!0,stencil:s=!1,alpha:a=!1,antialias:o=!1,premultipliedAlpha:l=!0,preserveDrawingBuffer:c=!1,powerPreference:h="default",failIfMajorPerformanceCaveat:u=!1,reversedDepthBuffer:d=!1,outputBufferType:f=di}=e;this.isWebGLRenderer=!0;let p;if(n!==null){if(typeof WebGLRenderingContext<"u"&&n instanceof WebGLRenderingContext)throw new Error("THREE.WebGLRenderer: WebGL 1 is not supported since r163.");p=n.getContextAttributes().alpha}else p=a;let y=f,m=new Set([Va,ql,Xl]),g=new Set([di,qi,Ns,Us,Hl,Wl]),v=new Uint32Array(4),S=new Int32Array(4),_=new P,M=null,w=null,E=[],x=[],A=null;this.domElement=t,this.debug={checkShaderErrors:!0,diagnostics:{keywords:!1},onShaderError:null},this.autoClear=!0,this.autoClearColor=!0,this.autoClearDepth=!0,this.autoClearStencil=!0,this.sortObjects=!0,this.clippingPlanes=[],this.localClippingEnabled=!1,this.toneMapping=Xi,this.toneMappingExposure=1,this.transmissionResolutionScale=1;let C=this,D=!1,U=null,I=null,L=null,k=null;this._outputColorSpace=bt;let H=0,X=0,Y=null,q=-1,K=null,N=new Xe,ie=new Xe,re=null,De=new Ie(0),Te=0,$e=t.width,$=t.height,ee=1,_e=null,Be=null,xe=new Xe(0,0,$e,$),Ve=new Xe(0,0,$e,$),gt=!1,He=new wn,Qe=!1,dt=!1,Je=new ge,vt=new P,Ht=new Xe,_i={background:null,fog:null,environment:null,overrideMaterial:null,isScene:!0},wt=!1;function Dt(){return Y===null?ee:1}let B=n;function Qt(T,O){return t.getContext(T,O)}let lt,R,b,z,W,Z,se,oe,J,te,le,Re,de,ce,Pe,Ne,Ge,F,he,Q,ue,me,ne;try{let T={alpha:!0,depth:r,stencil:s,antialias:o,premultipliedAlpha:l,preserveDrawingBuffer:c,powerPreference:h,failIfMajorPerformanceCaveat:u};if("setAttribute"in t&&t.setAttribute("data-engine",`three.js r${"186"}`),t.addEventListener("webglcontextlost",yt,!1),t.addEventListener("webglcontextrestored",it,!1),t.addEventListener("webglcontextcreationerror",Oi,!1),B===null){let O="webgl2";if(B=Qt(O,T),B===null)throw Qt(O)?new Error("THREE.WebGLRenderer: Error creating WebGL context with your selected attributes."):new Error("THREE.WebGLRenderer: Error creating WebGL context.")}Le()}catch(T){throw t.removeEventListener("webglcontextlost",yt,!1),t.removeEventListener("webglcontextrestored",it,!1),t.removeEventListener("webglcontextcreationerror",Oi,!1),Fe("WebGLRenderer: "+T.message),T}function Le(){lt=new US(B),lt.init(),ue=new bw(B,lt),R=new TS(B,lt,e,ue),b=new xw(B,lt),R.reversedDepthBuffer&&d&&b.buffers.depth.setReversed(!0),I=B.createFramebuffer(),L=B.createFramebuffer(),k=B.createFramebuffer(),z=new BS(B),W=new sw,Z=new vw(B,lt,b,W,R,ue,z),se=new NS(C),oe=new zx(B),me=new MS(B,oe),J=new OS(B,oe,z,me),te=new zS(B,J,oe,me,z),F=new kS(B,R,Z),Pe=new ES(W),le=new rw(C,se,lt,R,me,Pe),Re=new Tw(C,W),de=new ow,ce=new fw(lt),Ge=new SS(C,se,b,te,p,l),Ne=new _w(C,te,R),ne=new Ew(B,z,R,b),he=new wS(B,lt,z),Q=new FS(B,lt,z),z.programs=le.programs,C.capabilities=R,C.extensions=lt,C.properties=W,C.renderLists=de,C.shadowMap=Ne,C.state=b,C.info=z}y!==di&&(A=new GS(y,t.width,t.height,o,r,s));let Ee=new xd(C,B);this.xr=Ee,this.getContext=function(){return B},this.getContextAttributes=function(){return B.getContextAttributes()},this.forceContextLoss=function(){let T=lt.get("WEBGL_lose_context");T&&T.loseContext()},this.forceContextRestore=function(){let T=lt.get("WEBGL_lose_context");T&&T.restoreContext()},this.getPixelRatio=function(){return ee},this.setPixelRatio=function(T){T!==void 0&&(ee=T,this.setSize($e,$,!1))},this.getSize=function(T){return T.set($e,$)},this.setSize=function(T,O,j=!0){if(Ee.isPresenting){Ce("WebGLRenderer: Can't change size while VR device is presenting.");return}$e=T,$=O,t.width=Math.floor(T*ee),t.height=Math.floor(O*ee),j===!0&&(t.style.width=T+"px",t.style.height=O+"px"),A!==null&&A.setSize(t.width,t.height),this.setViewport(0,0,T,O)},this.getDrawingBufferSize=function(T){return T.set($e*ee,$*ee).floor()},this.setDrawingBufferSize=function(T,O,j){$e=T,$=O,ee=j,t.width=Math.floor(T*j),t.height=Math.floor(O*j),this.setViewport(0,0,T,O)},this.setEffects=function(T){if(y===di){Fe("WebGLRenderer: setEffects() requires outputBufferType set to HalfFloatType or FloatType.");return}if(T){for(let O=0;O<T.length;O++)if(T[O].isOutputPass===!0){Ce("WebGLRenderer: OutputPass is not needed in setEffects(). Tone mapping and color space conversion are applied automatically.");break}}A.setEffects(T||[])},this.getCurrentViewport=function(T){return T.copy(N)},this.getViewport=function(T){return T.copy(xe)},this.setViewport=function(T,O,j,V){T.isVector4?xe.set(T.x,T.y,T.z,T.w):xe.set(T,O,j,V),b.viewport(N.copy(xe).multiplyScalar(ee).round())},this.getScissor=function(T){return T.copy(Ve)},this.setScissor=function(T,O,j,V){T.isVector4?Ve.set(T.x,T.y,T.z,T.w):Ve.set(T,O,j,V),b.scissor(ie.copy(Ve).multiplyScalar(ee).round())},this.getScissorTest=function(){return gt},this.setScissorTest=function(T){b.setScissorTest(gt=T)},this.setOpaqueSort=function(T){_e=T},this.setTransparentSort=function(T){Be=T},this.getClearColor=function(T){return T.copy(Ge.getClearColor())},this.setClearColor=function(){Ge.setClearColor(...arguments)},this.getClearAlpha=function(){return Ge.getClearAlpha()},this.setClearAlpha=function(){Ge.setClearAlpha(...arguments)},this.clear=function(T=!0,O=!0,j=!0){let V=0;if(T){let G=!1;if(Y!==null){let pe=Y.texture.format;G=m.has(pe)}if(G){let pe=Y.texture.type,be=g.has(pe),fe=Ge.getClearColor(),Me=Ge.getClearAlpha(),Ae=fe.r,We=fe.g,Ke=fe.b;be?(v[0]=Ae,v[1]=We,v[2]=Ke,v[3]=Me,B.clearBufferuiv(B.COLOR,0,v)):(S[0]=Ae,S[1]=We,S[2]=Ke,S[3]=Me,B.clearBufferiv(B.COLOR,0,S))}else V|=B.COLOR_BUFFER_BIT}O&&(V|=B.DEPTH_BUFFER_BIT,this.state.buffers.depth.setMask(!0)),j&&(V|=B.STENCIL_BUFFER_BIT,this.state.buffers.stencil.setMask(4294967295)),V!==0&&B.clear(V)},this.clearColor=function(){this.clear(!0,!1,!1)},this.clearDepth=function(){this.clear(!1,!0,!1)},this.clearStencil=function(){this.clear(!1,!1,!0)},this.setNodesHandler=function(T){T.setRenderer(this),U=T},this.dispose=function(){t.removeEventListener("webglcontextlost",yt,!1),t.removeEventListener("webglcontextrestored",it,!1),t.removeEventListener("webglcontextcreationerror",Oi,!1),Ge.dispose(),de.dispose(),ce.dispose(),W.dispose(),se.dispose(),te.dispose(),me.dispose(),ne.dispose(),le.dispose(),Ee.dispose(),Ee.removeEventListener("sessionstart",tp),Ee.removeEventListener("sessionend",ip),_r.stop()};function yt(T){T.preventDefault(),ga("WebGLRenderer: Context Lost."),D=!0}function it(){ga("WebGLRenderer: Context Restored."),D=!1;let T=z.autoReset,O=Ne.enabled,j=Ne.autoUpdate,V=Ne.needsUpdate,G=Ne.type;Le(),z.autoReset=T,Ne.enabled=O,Ne.autoUpdate=j,Ne.needsUpdate=V,Ne.type=G}function Oi(T){Fe("WebGLRenderer: A WebGL context could not be created. Reason: ",T.statusMessage)}function Zi(T){let O=T.target;O.removeEventListener("dispose",Zi),Yy(O)}function Yy(T){$y(T),W.remove(T)}function $y(T){let O=W.get(T).programs;O!==void 0&&(O.forEach(function(j){le.releaseProgram(j)}),T.isShaderMaterial&&le.releaseShaderCache(T))}this.renderBufferDirect=function(T,O,j,V,G,pe){O===null&&(O=_i);let be=G.isMesh&&G.matrixWorld.determinantAffine()<0,fe=Jy(T,O,j,V,G);b.setMaterial(V,be);let Me=j.index,Ae=1;if(V.wireframe===!0){if(Me=J.getWireframeAttribute(j),Me===void 0)return;Ae=2}let We=j.drawRange,Ke=j.attributes.position,we=We.start*Ae,nt=(We.start+We.count)*Ae;pe!==null&&(we=Math.max(we,pe.start*Ae),nt=Math.min(nt,(pe.start+pe.count)*Ae)),Me!==null?(we=Math.max(we,0),nt=Math.min(nt,Me.count)):Ke!=null&&(we=Math.max(we,0),nt=Math.min(nt,Ke.count));let Nt=nt-we;if(Nt<0||Nt===1/0)return;me.setup(G,V,fe,j,Me);let xt,pt=he;if(Me!==null&&(xt=oe.get(Me),pt=Q,pt.setIndex(xt)),G.isMesh)V.wireframe===!0?(b.setLineWidth(V.wireframeLinewidth*Dt()),pt.setMode(B.LINES)):pt.setMode(B.TRIANGLES);else if(G.isLine){let ei=V.linewidth;ei===void 0&&(ei=1),b.setLineWidth(ei*Dt()),G.isLineSegments?pt.setMode(B.LINES):G.isLineLoop?pt.setMode(B.LINE_LOOP):pt.setMode(B.LINE_STRIP)}else G.isPoints?pt.setMode(B.POINTS):G.isSprite&&pt.setMode(B.TRIANGLES);if(G.isBatchedMesh)if(lt.get("WEBGL_multi_draw"))pt.renderMultiDraw(G._multiDrawStarts,G._multiDrawCounts,G._multiDrawCount);else{let ei=G._multiDrawStarts,ve=G._multiDrawCounts,ai=G._multiDrawCount,et=Me?oe.get(Me).bytesPerElement:1,Pi=W.get(V).currentProgram.getUniforms();for(let Ki=0;Ki<ai;Ki++)Pi.setValue(B,"_gl_DrawID",Ki),pt.render(ei[Ki]/et,ve[Ki])}else if(G.isInstancedMesh)pt.renderInstances(we,Nt,G.count);else if(j.isInstancedBufferGeometry){let ei=j._maxInstanceCount!==void 0?j._maxInstanceCount:1/0,ve=Math.min(j.instanceCount,ei);pt.renderInstances(we,Nt,ve)}else pt.render(we,Nt)};function ep(T,O,j,V){U!==null&&T.isNodeMaterial&&U.setObject(V,T),Qe===!0&&Pe.setState(T,j,!1),T.transparent===!0&&T.side===ri&&T.forceSinglePass===!1?(T.side=ui,T.needsUpdate=!0,Co(T,O,V),T.side=sn,T.needsUpdate=!0,Co(T,O,V),T.side=ri):Co(T,O,V)}this.compile=function(T,O,j=null){j===null&&(j=T),U!==null&&U.renderStart(T,O,j),w=ce.get(j),w.init(O),x.push(w),j.traverseVisible(function(G){G.isLight&&G.layers.test(O.layers)&&(w.pushLight(G),G.castShadow&&w.pushShadow(G))}),T!==j&&T.traverseVisible(function(G){G.isLight&&G.layers.test(O.layers)&&(w.pushLight(G),G.castShadow&&w.pushShadow(G))}),w.setupLights(),U!==null&&U.updateLights(w.state.lightsArray),dt=this.localClippingEnabled,Qe=Pe.init(this.clippingPlanes,dt),Qe===!0&&Pe.setGlobalState(this.clippingPlanes,O),U!==null&&Ne.render(w.state.shadowsArray,j,O);let V=new Set;return T.traverse(function(G){if(!(G.isMesh||G.isPoints||G.isLine||G.isSprite))return;let pe=G.material;if(pe)if(Array.isArray(pe))for(let be=0;be<pe.length;be++){let fe=pe[be];ep(fe,j,O,G),V.add(fe)}else ep(pe,j,O,G),V.add(pe)}),w=x.pop(),U!==null&&U.renderEnd(),V},this.compileAsync=function(T,O,j=null){let V=this.compile(T,O,j);return new Promise(G=>{function pe(){if(V.forEach(function(be){let Me=W.get(be).currentProgram;(Me===void 0||Me.isReady())&&V.delete(be)}),V.size===0){G(T);return}setTimeout(pe,10)}lt.get("KHR_parallel_shader_compile")!==null?pe():setTimeout(pe,10)})};let Eh=null;function Zy(T){Eh&&Eh(T)}function tp(){_r.stop()}function ip(){_r.start()}let _r=new Sg;_r.setAnimationLoop(Zy),typeof self<"u"&&_r.setContext(self),this.setAnimationLoop=function(T){Eh=T,Ee.setAnimationLoop(T),T===null?_r.stop():_r.start()},Ee.addEventListener("sessionstart",tp),Ee.addEventListener("sessionend",ip),this.render=function(T,O){if(O!==void 0&&O.isCamera!==!0){Fe("WebGLRenderer.render: camera is not an instance of THREE.Camera.");return}if(D===!0)return;U!==null&&U.renderStart(T,O);let j=Ee.enabled===!0&&Ee.isPresenting===!0,V=A!==null&&(Y===null||j)&&A.begin(C,Y);if(T.matrixWorldAutoUpdate===!0&&T.updateMatrixWorld(),O.parent===null&&O.matrixWorldAutoUpdate===!0&&O.updateMatrixWorld(),Ee.enabled===!0&&Ee.isPresenting===!0&&(A===null||A.isCompositing()===!1)&&(Ee.cameraAutoUpdate===!0&&Ee.updateCamera(O),O=Ee.getCamera()),T.isScene===!0&&T.onBeforeRender(C,T,O,Y),w=ce.get(T,x.length),w.init(O),w.state.textureUnits=Z.getTextureUnits(),x.push(w),Je.multiplyMatrices(O.projectionMatrix,O.matrixWorldInverse),He.setFromProjectionMatrix(Je,Gi,O.reversedDepth),dt=this.localClippingEnabled,Qe=Pe.init(this.clippingPlanes,dt),M=de.get(T,E.length),M.init(),E.push(M),Ee.enabled===!0&&Ee.isPresenting===!0){let be=C.xr.getDepthSensingMesh();be!==null&&Ah(be,O,-1/0,C.sortObjects)}Ah(T,O,0,C.sortObjects),M.finish(),U!==null&&U.updateLights(w.state.lightsArray),C.sortObjects===!0&&M.sort(_e,Be),wt=Ee.enabled===!1||Ee.isPresenting===!1||Ee.hasDepthSensing()===!1,wt&&Ge.addToRenderList(M,T),this.info.render.frame++,this.info.autoReset===!0&&this.info.reset(),Qe===!0&&Pe.beginShadows();let G=w.state.shadowsArray;if(Ne.render(G,T,O),Qe===!0&&Pe.endShadows(),(V&&A.hasRenderPass())===!1){let be=M.opaque,fe=M.transmissive;if(w.setupLights(),O.isArrayCamera){let Me=O.cameras;if(fe.length>0)for(let Ae=0,We=Me.length;Ae<We;Ae++){let Ke=Me[Ae];rp(be,fe,T,Ke)}wt&&Ge.render(T);for(let Ae=0,We=Me.length;Ae<We;Ae++){let Ke=Me[Ae];np(M,T,Ke,Ke.viewport)}}else fe.length>0&&rp(be,fe,T,O),wt&&Ge.render(T),np(M,T,O)}Y!==null&&X===0&&(Z.updateMultisampleRenderTarget(Y),Z.updateRenderTargetMipmap(Y)),V&&A.end(C),T.isScene===!0&&T.onAfterRender(C,T,O),me.resetDefaultState(),q=-1,K=null,x.pop(),x.length>0?(w=x[x.length-1],Z.setTextureUnits(w.state.textureUnits),Qe===!0&&Pe.setGlobalState(C.clippingPlanes,w.state.camera)):w=null,E.pop(),E.length>0?M=E[E.length-1]:M=null,U!==null&&U.renderEnd()};function Ah(T,O,j,V){if(T.visible===!1)return;if(T.layers.test(O.layers)){if(T.isGroup)j=T.renderOrder;else if(T.isLOD)T.autoUpdate===!0&&T.update(O);else if(T.isLightProbeGrid)w.pushLightProbeGrid(T);else if(T.isLight)w.pushLight(T),T.castShadow&&w.pushShadow(T);else if(T.isSprite){if(!T.frustumCulled||T.intersectsFrustum(He)){V&&Ht.setFromMatrixPosition(T.matrixWorld).applyMatrix4(Je);let be=te.update(T),fe=T.material;fe.visible&&M.push(T,be,fe,j,Ht.z,null,O)}}else if((T.isMesh||T.isLine||T.isPoints)&&(!T.frustumCulled||T.intersectsFrustum(He))){let be=te.update(T),fe=T.material;if(V&&(T.boundingSphere!==void 0?(T.boundingSphere===null&&T.computeBoundingSphere(),Ht.copy(T.boundingSphere.center)):(be.boundingSphere===null&&be.computeBoundingSphere(),Ht.copy(be.boundingSphere.center)),Ht.applyMatrix4(T.matrixWorld).applyMatrix4(Je)),Array.isArray(fe)){let Me=be.groups;for(let Ae=0,We=Me.length;Ae<We;Ae++){let Ke=Me[Ae],we=fe[Ke.materialIndex];we&&we.visible&&M.push(T,be,we,j,Ht.z,Ke,O)}}else fe.visible&&M.push(T,be,fe,j,Ht.z,null,O)}}let pe=T.children;for(let be=0,fe=pe.length;be<fe;be++)Ah(pe[be],O,j,V)}function np(T,O,j,V){let{opaque:G,transmissive:pe,transparent:be}=T;w.setupLightsView(j),Qe===!0&&Pe.setGlobalState(C.clippingPlanes,j),V&&b.viewport(N.copy(V)),G.length>0&&Ao(G,O,j),pe.length>0&&Ao(pe,O,j),be.length>0&&Ao(be,O,j),b.buffers.depth.setTest(!0),b.buffers.depth.setMask(!0),b.buffers.color.setMask(!0),b.setPolygonOffset(!1)}function rp(T,O,j,V){if((j.isScene===!0?j.overrideMaterial:null)!==null)return;if(w.state.transmissionRenderTarget[V.id]===void 0){let we=lt.has("EXT_color_buffer_half_float")||lt.has("EXT_color_buffer_float");w.state.transmissionRenderTarget[V.id]=new ci(1,1,{generateMipmaps:!0,type:we?ji:di,minFilter:Ci,samples:Math.max(4,R.samples),stencilBuffer:s,resolveDepthBuffer:!1,resolveStencilBuffer:!1,storeMultisampledDepthBuffer:!1,storeMultisampledStencilBuffer:!1,colorSpace:je.workingColorSpace})}let pe=w.state.transmissionRenderTarget[V.id],be=V.viewport||N;pe.setSize(be.z*C.transmissionResolutionScale,be.w*C.transmissionResolutionScale);let fe=C.getRenderTarget(),Me=C.getActiveCubeFace(),Ae=C.getActiveMipmapLevel();C.setRenderTarget(pe),C.getClearColor(De),Te=C.getClearAlpha(),Te<1&&C.setClearColor(16777215,.5),C.clear(),wt&&Ge.render(j);let We=C.toneMapping;C.toneMapping=Xi;let Ke=V.viewport;if(V.viewport!==void 0&&(V.viewport=void 0),w.setupLightsView(V),Qe===!0&&Pe.setGlobalState(C.clippingPlanes,V),Ao(T,j,V),Z.updateMultisampleRenderTarget(pe),Z.updateRenderTargetMipmap(pe),lt.has("WEBGL_multisampled_render_to_texture")===!1){let we=!1;for(let nt=0,Nt=O.length;nt<Nt;nt++){let xt=O[nt],{object:pt,geometry:ei,material:ve,group:ai}=xt;if(ve.side===ri&&pt.layers.test(V.layers)){let et=ve.side;ve.side=ui,ve.needsUpdate=!0,sp(pt,j,V,ei,ve,ai),ve.side=et,ve.needsUpdate=!0,we=!0}}we===!0&&(Z.updateMultisampleRenderTarget(pe),Z.updateRenderTargetMipmap(pe))}C.setRenderTarget(fe,Me,Ae),C.setClearColor(De,Te),Ke!==void 0&&(V.viewport=Ke),C.toneMapping=We}function Ao(T,O,j){let V=O.isScene===!0?O.overrideMaterial:null;for(let G=0,pe=T.length;G<pe;G++){let be=T[G],{object:fe,geometry:Me,group:Ae}=be,We=be.material;We.allowOverride===!0&&V!==null&&(We=V),fe.layers.test(j.layers)&&sp(fe,O,j,Me,We,Ae)}}function sp(T,O,j,V,G,pe){U!==null&&G.isNodeMaterial&&U.setObject(T,G),T.onBeforeRender(C,O,j,V,G,pe),T.modelViewMatrix.multiplyMatrices(j.matrixWorldInverse,T.matrixWorld),T.normalMatrix.getNormalMatrix(T.modelViewMatrix),G.onBeforeRender(C,O,j,V,T,pe),G.transparent===!0&&G.side===ri&&G.forceSinglePass===!1?(G.side=ui,G.needsUpdate=!0,C.renderBufferDirect(j,O,V,G,T,pe),G.side=sn,G.needsUpdate=!0,C.renderBufferDirect(j,O,V,G,T,pe),G.side=ri):C.renderBufferDirect(j,O,V,G,T,pe),T.onAfterRender(C,O,j,V,G,pe)}function Co(T,O,j){O.isScene!==!0&&(O=_i);let V=W.get(T),G=w.state.lights,pe=w.state.shadowsArray,be=G.state.version,fe=le.getParameters(T,G.state,pe,O,j,w.state.lightProbeGridArray),Me=le.getProgramCacheKey(fe),Ae=V.programs;V.environment=T.isMeshStandardMaterial||T.isMeshLambertMaterial||T.isMeshPhongMaterial?O.environment:null,V.fog=O.fog;let We=T.isMeshStandardMaterial||T.isMeshLambertMaterial&&!T.envMap||T.isMeshPhongMaterial&&!T.envMap;V.envMap=se.get(T.envMap||V.environment,We),V.envMapRotation=V.environment!==null&&T.envMap===null?O.environmentRotation:T.envMapRotation,Ae===void 0&&(T.addEventListener("dispose",Zi),Ae=new Map,V.programs=Ae);let Ke=Ae.get(Me);if(Ke!==void 0){if(V.currentProgram===Ke&&V.lightsStateVersion===be)return op(T,fe),Ke}else fe.uniforms=le.getUniforms(T),U!==null&&T.isNodeMaterial&&U.build(T,j,fe),T.onBeforeCompile(fe,C),Ke=le.acquireProgram(fe,Me),Ae.set(Me,Ke),V.uniforms=fe.uniforms;let we=V.uniforms;return(!T.isShaderMaterial&&!T.isRawShaderMaterial||T.clipping===!0)&&(we.clippingPlanes=Pe.uniform),op(T,fe),V.needsLights=e_(T),V.lightsStateVersion=be,V.needsLights&&(we.ambientLightColor.value=G.state.ambient,we.lightProbe.value=G.state.probe,we.sunLights.value=G.state.sun,we.sunLightShadows.value=G.state.sunShadow,we.directionalLights.value=G.state.directional,we.directionalLightShadows.value=G.state.directionalShadow,we.spotLights.value=G.state.spot,we.spotLightShadows.value=G.state.spotShadow,we.rectAreaLights.value=G.state.rectArea,we.ltc_1.value=G.state.rectAreaLTC1,we.ltc_2.value=G.state.rectAreaLTC2,we.pointLights.value=G.state.point,we.pointLightShadows.value=G.state.pointShadow,we.hemisphereLights.value=G.state.hemi,we.sunShadowMatrix.value=G.state.sunShadowMatrix,we.sunShadowCascade.value=G.state.sunShadowCascade,we.directionalShadowMatrix.value=G.state.directionalShadowMatrix,we.spotLightMatrix.value=G.state.spotLightMatrix,we.spotLightMap.value=G.state.spotLightMap,we.pointShadowMatrix.value=G.state.pointShadowMatrix),V.lightProbeGrid=w.state.lightProbeGridArray.length>0,V.currentProgram=Ke,V.uniformsList=null,Ke}function ap(T){if(T.uniformsList===null){let O=T.currentProgram.getUniforms();T.uniformsList=zs.seqWithValue(O.seq,T.uniforms)}return T.uniformsList}function op(T,O){let j=W.get(T);j.outputColorSpace=O.outputColorSpace,j.batching=O.batching,j.batchingColor=O.batchingColor,j.instancing=O.instancing,j.instancingColor=O.instancingColor,j.instancingMorph=O.instancingMorph,j.skinning=O.skinning,j.morphTargets=O.morphTargets,j.morphNormals=O.morphNormals,j.morphColors=O.morphColors,j.morphTargetsCount=O.morphTargetsCount,j.numClippingPlanes=O.numClippingPlanes,j.numIntersection=O.numClipIntersection,j.vertexAlphas=O.vertexAlphas,j.vertexTangents=O.vertexTangents,j.toneMapping=O.toneMapping}function Ky(T,O){if(T.length===0)return null;if(T.length===1)return T[0].texture!==null?T[0]:null;_.setFromMatrixPosition(O.matrixWorld);for(let j=0,V=T.length;j<V;j++){let G=T[j];if(G.texture!==null&&G.boundingBox.containsPoint(_))return G}return null}function Jy(T,O,j,V,G){O.isScene!==!0&&(O=_i),Z.resetTextureUnits();let pe=O.fog,be=V.isMeshStandardMaterial||V.isMeshLambertMaterial||V.isMeshPhongMaterial?O.environment:null,fe=Y===null?C.outputColorSpace:Y.isXRRenderTarget===!0?Y.texture.colorSpace:je.workingColorSpace,Me=V.isMeshStandardMaterial||V.isMeshLambertMaterial&&!V.envMap||V.isMeshPhongMaterial&&!V.envMap,Ae=se.get(V.envMap||be,Me),We=V.vertexColors===!0&&!!j.attributes.color&&j.attributes.color.itemSize===4,Ke=!!j.attributes.tangent&&(!!V.normalMap||V.anisotropy>0),we=!!j.morphAttributes.position,nt=!!j.morphAttributes.normal,Nt=!!j.morphAttributes.color,xt=Xi;V.toneMapped&&(Y===null||Y.isXRRenderTarget===!0)&&(xt=C.toneMapping);let pt=j.morphAttributes.position||j.morphAttributes.normal||j.morphAttributes.color,ei=pt!==void 0?pt.length:0,ve=W.get(V),ai=w.state.lights;if(Qe===!0&&(dt===!0||T!==K)){let _t=T===K&&V.id===q;Pe.setState(V,T,_t)}let et=!1;V.version===ve.__version?(ve.needsLights&&ve.lightsStateVersion!==ai.state.version||ve.outputColorSpace!==fe||G.isBatchedMesh&&ve.batching===!1||!G.isBatchedMesh&&ve.batching===!0||G.isBatchedMesh&&ve.batchingColor===!0&&G._colorsTexture===null||G.isBatchedMesh&&ve.batchingColor===!1&&G._colorsTexture!==null||G.isInstancedMesh&&ve.instancing===!1||!G.isInstancedMesh&&ve.instancing===!0||G.isSkinnedMesh&&ve.skinning===!1||!G.isSkinnedMesh&&ve.skinning===!0||G.isInstancedMesh&&ve.instancingColor===!0&&G.instanceColor===null||G.isInstancedMesh&&ve.instancingColor===!1&&G.instanceColor!==null||G.isInstancedMesh&&ve.instancingMorph===!0&&G.morphTexture===null||G.isInstancedMesh&&ve.instancingMorph===!1&&G.morphTexture!==null||ve.envMap!==Ae||V.fog===!0&&ve.fog!==pe||ve.numClippingPlanes!==void 0&&(ve.numClippingPlanes!==Pe.numPlanes||ve.numIntersection!==Pe.numIntersection)||ve.vertexAlphas!==We||ve.vertexTangents!==Ke||ve.morphTargets!==we||ve.morphNormals!==nt||ve.morphColors!==Nt||ve.toneMapping!==xt||ve.morphTargetsCount!==ei||!!ve.lightProbeGrid!=w.state.lightProbeGridArray.length>0)&&(et=!0):(et=!0,ve.__version=V.version);let Pi=ve.currentProgram;et===!0&&(Pi=Co(V,O,G),U&&V.isNodeMaterial&&U.onUpdateProgram(V,Pi,ve));let Ki=!1,kn=!1,Jr=!1,ft=Pi.getUniforms(),Ct=ve.uniforms;if(b.useProgram(Pi.program)&&(Ki=!0,kn=!0,Jr=!0),V.id!==q&&(q=V.id,kn=!0),ve.needsLights){let _t=Ky(w.state.lightProbeGridArray,G);ve.lightProbeGrid!==_t&&(ve.lightProbeGrid=_t,kn=!0)}if(Ki||K!==T){b.buffers.depth.getReversed()&&T.reversedDepth!==!0&&(T._reversedDepth=!0,T.updateProjectionMatrix()),ft.setValue(B,"projectionMatrix",T.projectionMatrix),ft.setValue(B,"viewMatrix",T.matrixWorldInverse);let Vn=ft.map.cameraPosition;Vn!==void 0&&Vn.setValue(B,vt.setFromMatrixPosition(T.matrixWorld)),R.logarithmicDepthBuffer&&ft.setValue(B,"logDepthBufFC",2/(Math.log(T.far+1)/Math.LN2)),(V.isMeshPhongMaterial||V.isMeshToonMaterial||V.isMeshLambertMaterial||V.isMeshBasicMaterial||V.isMeshStandardMaterial||V.isShaderMaterial)&&ft.setValue(B,"isOrthographic",T.isOrthographicCamera===!0),K!==T&&(K=T,kn=!0,Jr=!0)}if(ve.needsLights&&(ai.state.sunShadowMap.length>0&&ft.setValue(B,"sunShadowMap",ai.state.sunShadowMap,Z),ai.state.directionalShadowMap.length>0&&ft.setValue(B,"directionalShadowMap",ai.state.directionalShadowMap,Z),ai.state.spotShadowMap.length>0&&ft.setValue(B,"spotShadowMap",ai.state.spotShadowMap,Z),ai.state.pointShadowMap.length>0&&ft.setValue(B,"pointShadowMap",ai.state.pointShadowMap,Z)),G.isSkinnedMesh){ft.setOptional(B,G,"bindMatrix"),ft.setOptional(B,G,"bindMatrixInverse");let _t=G.skeleton;_t&&(_t.boneTexture===null&&_t.computeBoneTexture(),ft.setValue(B,"boneTexture",_t.boneTexture,Z))}G.isBatchedMesh&&(ft.setOptional(B,G,"batchingTexture"),ft.setValue(B,"batchingTexture",G._matricesTexture,Z),ft.setOptional(B,G,"batchingIdTexture"),ft.setValue(B,"batchingIdTexture",G._indirectTexture,Z),ft.setOptional(B,G,"batchingColorTexture"),G._colorsTexture!==null&&ft.setValue(B,"batchingColorTexture",G._colorsTexture,Z));let zn=j.morphAttributes;if((zn.position!==void 0||zn.normal!==void 0||zn.color!==void 0)&&F.update(G,j,Pi),(kn||ve.receiveShadow!==G.receiveShadow)&&(ve.receiveShadow=G.receiveShadow,ft.setValue(B,"receiveShadow",G.receiveShadow)),(V.isMeshStandardMaterial||V.isMeshLambertMaterial||V.isMeshPhongMaterial)&&V.envMap===null&&O.environment!==null&&(Ct.envMapIntensity.value=O.environmentIntensity),Ct.dfgLUT!==void 0&&(Ct.dfgLUT.value=Cw()),kn){if(ft.setValue(B,"toneMappingExposure",C.toneMappingExposure),ve.needsLights&&Qy(Ct,Jr),pe&&V.fog===!0&&Re.refreshFogUniforms(Ct,pe),Re.refreshMaterialUniforms(Ct,V,ee,$,w.state.transmissionRenderTarget[T.id]),ve.needsLights&&ve.lightProbeGrid){let _t=ve.lightProbeGrid;Ct.probesSH.value=_t.texture,Ct.probesMin.value.copy(_t.boundingBox.min),Ct.probesMax.value.copy(_t.boundingBox.max),Ct.probesResolution.value.copy(_t.resolution)}zs.upload(B,ap(ve),Ct,Z)}if(V.isShaderMaterial&&V.uniformsNeedUpdate===!0&&(zs.upload(B,ap(ve),Ct,Z),V.uniformsNeedUpdate=!1),V.isSpriteMaterial&&ft.setValue(B,"center",G.center),ft.setValue(B,"modelViewMatrix",G.modelViewMatrix),ft.setValue(B,"normalMatrix",G.normalMatrix),ft.setValue(B,"modelMatrix",G.matrixWorld),V.uniformsGroups!==void 0){let _t=V.uniformsGroups;for(let Vn=0,Qr=_t.length;Vn<Qr;Vn++){let cp=_t[Vn];ne.update(cp,Pi),ne.bind(cp,Pi)}}return Pi}function Qy(T,O){T.ambientLightColor.needsUpdate=O,T.lightProbe.needsUpdate=O,T.sunLights.needsUpdate=O,T.sunLightShadows.needsUpdate=O,T.directionalLights.needsUpdate=O,T.directionalLightShadows.needsUpdate=O,T.pointLights.needsUpdate=O,T.pointLightShadows.needsUpdate=O,T.spotLights.needsUpdate=O,T.spotLightShadows.needsUpdate=O,T.rectAreaLights.needsUpdate=O,T.hemisphereLights.needsUpdate=O}function e_(T){return T.isMeshLambertMaterial||T.isMeshToonMaterial||T.isMeshPhongMaterial||T.isMeshStandardMaterial||T.isShadowMaterial||T.isShaderMaterial&&T.lights===!0}this.getActiveCubeFace=function(){return H},this.getActiveMipmapLevel=function(){return X},this.getRenderTarget=function(){return Y},this.setRenderTargetTextures=function(T,O,j){let V=W.get(T);V.__autoAllocateDepthBuffer=T.resolveDepthBuffer===!1,V.__autoAllocateDepthBuffer===!1&&(V.__useRenderToTexture=!1),W.get(T.texture).__webglTexture=O,W.get(T.depthTexture).__webglTexture=V.__autoAllocateDepthBuffer?void 0:j,V.__hasExternalTextures=!0},this.setRenderTargetFramebuffer=function(T,O){let j=W.get(T);j.__webglFramebuffer=O,j.__useDefaultFramebuffer=O===void 0},this.setRenderTarget=function(T,O=0,j=0){Y=T,H=O,X=j;let V=null,G=!1,pe=!1;if(T){let fe=W.get(T);if(fe.__useDefaultFramebuffer!==void 0){b.bindFramebuffer(B.FRAMEBUFFER,fe.__webglFramebuffer),N.copy(T.viewport),ie.copy(T.scissor),re=T.scissorTest,b.viewport(N),b.scissor(ie),b.setScissorTest(re),q=-1;return}else if(fe.__webglFramebuffer===void 0)Z.setupRenderTarget(T);else if(fe.__hasExternalTextures)Z.rebindTextures(T,W.get(T.texture).__webglTexture,W.get(T.depthTexture).__webglTexture);else if(T.depthBuffer){let We=T.depthTexture;if(fe.__boundDepthTexture!==We){if(We!==null&&W.has(We)&&(T.width!==We.image.width||T.height!==We.image.height))throw new Error("THREE.WebGLRenderer: Attached DepthTexture is initialized to the incorrect size.");Z.setupDepthRenderbuffer(T)}}let Me=T.texture;(Me.isData3DTexture||Me.isDataArrayTexture||Me.isCompressedArrayTexture)&&(pe=!0);let Ae=W.get(T).__webglFramebuffer;T.isWebGLCubeRenderTarget?(Array.isArray(Ae[O])?V=Ae[O][j]:V=Ae[O],G=!0):T.samples>0&&Z.useMultisampledRTT(T)===!1?V=W.get(T).__webglMultisampledFramebuffer:Array.isArray(Ae)?V=Ae[j]:V=Ae,N.copy(T.viewport),ie.copy(T.scissor),re=T.scissorTest}else N.copy(xe).multiplyScalar(ee).floor(),ie.copy(Ve).multiplyScalar(ee).floor(),re=gt;if(j!==0&&(V=I),b.bindFramebuffer(B.FRAMEBUFFER,V)&&b.drawBuffers(T,V),b.viewport(N),b.scissor(ie),b.setScissorTest(re),G){let fe=W.get(T.texture);B.framebufferTexture2D(B.FRAMEBUFFER,B.COLOR_ATTACHMENT0,B.TEXTURE_CUBE_MAP_POSITIVE_X+O,fe.__webglTexture,j)}else if(pe){let fe=O;for(let Me=0;Me<T.textures.length;Me++){let Ae=W.get(T.textures[Me]);B.framebufferTextureLayer(B.FRAMEBUFFER,B.COLOR_ATTACHMENT0+Me,Ae.__webglTexture,j,fe)}}else if(T!==null&&j!==0){let fe=W.get(T.texture);B.framebufferTexture2D(B.FRAMEBUFFER,B.COLOR_ATTACHMENT0,B.TEXTURE_2D,fe.__webglTexture,j)}q=-1};function lp(T){let O=W.get(T);return(O.__readFormat!==T.format||O.__readType!==T.type)&&(O.__readFormat=T.format,O.__readType=T.type,O.__formatReadable=R.textureFormatReadable(T.format),O.__typeReadable=R.textureTypeReadable(T.type)),O}this.readRenderTargetPixels=function(T,O,j,V,G,pe,be,fe=0){if(!(T&&T.isWebGLRenderTarget)){Fe("WebGLRenderer.readRenderTargetPixels: renderTarget is not THREE.WebGLRenderTarget.");return}let Me=W.get(T).__webglFramebuffer;if(T.isWebGLCubeRenderTarget&&be!==void 0&&(Me=Me[be]),Me){b.bindFramebuffer(B.FRAMEBUFFER,Me);try{let Ae=T.textures[fe],We=Ae.format,Ke=Ae.type;T.textures.length>1&&B.readBuffer(B.COLOR_ATTACHMENT0+fe);let we=lp(Ae);if(we.__formatReadable===!1){Fe("WebGLRenderer.readRenderTargetPixels: renderTarget is not in RGBA or implementation defined format.");return}if(we.__typeReadable===!1){Fe("WebGLRenderer.readRenderTargetPixels: renderTarget is not in UnsignedByteType or implementation defined type.");return}O>=0&&O<=T.width-V&&j>=0&&j<=T.height-G&&B.readPixels(O,j,V,G,ue.convert(We),ue.convert(Ke),pe)}finally{let Ae=Y!==null?W.get(Y).__webglFramebuffer:null;b.bindFramebuffer(B.FRAMEBUFFER,Ae)}}},this.readRenderTargetPixelsAsync=async function(T,O,j,V,G,pe,be,fe=0){if(!(T&&T.isWebGLRenderTarget))throw new Error("THREE.WebGLRenderer.readRenderTargetPixels: renderTarget is not THREE.WebGLRenderTarget.");let Me=W.get(T).__webglFramebuffer;if(T.isWebGLCubeRenderTarget&&be!==void 0&&(Me=Me[be]),Me)if(O>=0&&O<=T.width-V&&j>=0&&j<=T.height-G){b.bindFramebuffer(B.FRAMEBUFFER,Me);let Ae=T.textures[fe],We=Ae.format,Ke=Ae.type;T.textures.length>1&&B.readBuffer(B.COLOR_ATTACHMENT0+fe);let we=lp(Ae);if(we.__formatReadable===!1)throw new Error("THREE.WebGLRenderer.readRenderTargetPixelsAsync: renderTarget is not in RGBA or implementation defined format.");if(we.__typeReadable===!1)throw new Error("THREE.WebGLRenderer.readRenderTargetPixelsAsync: renderTarget is not in UnsignedByteType or implementation defined type.");let nt=B.createBuffer();B.bindBuffer(B.PIXEL_PACK_BUFFER,nt),B.bufferData(B.PIXEL_PACK_BUFFER,pe.byteLength,B.STREAM_READ),B.readPixels(O,j,V,G,ue.convert(We),ue.convert(Ke),0),B.bindBuffer(B.PIXEL_PACK_BUFFER,null);let Nt=Y!==null?W.get(Y).__webglFramebuffer:null;b.bindFramebuffer(B.FRAMEBUFFER,Nt);let xt=B.fenceSync(B.SYNC_GPU_COMMANDS_COMPLETE,0);return B.flush(),await $m(B,xt,4),B.bindBuffer(B.PIXEL_PACK_BUFFER,nt),B.getBufferSubData(B.PIXEL_PACK_BUFFER,0,pe),B.bindBuffer(B.PIXEL_PACK_BUFFER,null),B.deleteBuffer(nt),B.deleteSync(xt),pe}else throw new Error("THREE.WebGLRenderer.readRenderTargetPixelsAsync: requested read bounds are out of range.")},this.copyFramebufferToTexture=function(T,O=null,j=0){let V=Math.pow(2,-j),G=Math.floor(T.image.width*V),pe=Math.floor(T.image.height*V),be=O!==null?O.x:0,fe=O!==null?O.y:0;Z.setTexture2D(T,0),B.copyTexSubImage2D(B.TEXTURE_2D,j,0,0,be,fe,G,pe),b.unbindTexture()},this.copyTextureToTexture=function(T,O,j=null,V=null,G=0,pe=0){let be,fe,Me,Ae,We,Ke,we,nt,Nt,xt=T.isCompressedTexture?T.mipmaps[pe]:T.image;if(j!==null)be=j.max.x-j.min.x,fe=j.max.y-j.min.y,Me=j.isBox3?j.max.z-j.min.z:1,Ae=j.min.x,We=j.min.y,Ke=j.isBox3?j.min.z:0;else{let Ct=Math.pow(2,-G);be=Math.floor(xt.width*Ct),fe=Math.floor(xt.height*Ct),T.isDataArrayTexture?Me=xt.depth:T.isData3DTexture?Me=Math.floor(xt.depth*Ct):Me=1,Ae=0,We=0,Ke=0}V!==null?(we=V.x,nt=V.y,Nt=V.z):(we=0,nt=0,Nt=0);let pt=ue.convert(O.format),ei=ue.convert(O.type),ve;O.isData3DTexture?(Z.setTexture3D(O,0),ve=B.TEXTURE_3D):O.isDataArrayTexture||O.isCompressedArrayTexture?(Z.setTexture2DArray(O,0),ve=B.TEXTURE_2D_ARRAY):(Z.setTexture2D(O,0),ve=B.TEXTURE_2D),b.activeTexture(B.TEXTURE0),b.pixelStorei(B.UNPACK_FLIP_Y_WEBGL,O.flipY),b.pixelStorei(B.UNPACK_PREMULTIPLY_ALPHA_WEBGL,O.premultiplyAlpha),b.pixelStorei(B.UNPACK_ALIGNMENT,O.unpackAlignment);let ai=b.getParameter(B.UNPACK_ROW_LENGTH),et=b.getParameter(B.UNPACK_IMAGE_HEIGHT),Pi=b.getParameter(B.UNPACK_SKIP_PIXELS),Ki=b.getParameter(B.UNPACK_SKIP_ROWS),kn=b.getParameter(B.UNPACK_SKIP_IMAGES);b.pixelStorei(B.UNPACK_ROW_LENGTH,xt.width),b.pixelStorei(B.UNPACK_IMAGE_HEIGHT,xt.height),b.pixelStorei(B.UNPACK_SKIP_PIXELS,Ae),b.pixelStorei(B.UNPACK_SKIP_ROWS,We),b.pixelStorei(B.UNPACK_SKIP_IMAGES,Ke);let Jr=T.isDataArrayTexture||T.isData3DTexture,ft=O.isDataArrayTexture||O.isData3DTexture;if(T.isDepthTexture){let Ct=W.get(T),zn=W.get(O),_t=W.get(Ct.__renderTarget),Vn=W.get(zn.__renderTarget);b.bindFramebuffer(B.READ_FRAMEBUFFER,_t.__webglFramebuffer),b.bindFramebuffer(B.DRAW_FRAMEBUFFER,Vn.__webglFramebuffer);for(let Qr=0;Qr<Me;Qr++)Jr&&(B.framebufferTextureLayer(B.READ_FRAMEBUFFER,B.COLOR_ATTACHMENT0,W.get(T).__webglTexture,G,Ke+Qr),B.framebufferTextureLayer(B.DRAW_FRAMEBUFFER,B.COLOR_ATTACHMENT0,W.get(O).__webglTexture,pe,Nt+Qr)),B.blitFramebuffer(Ae,We,be,fe,we,nt,be,fe,B.DEPTH_BUFFER_BIT,B.NEAREST);b.bindFramebuffer(B.READ_FRAMEBUFFER,null),b.bindFramebuffer(B.DRAW_FRAMEBUFFER,null)}else if(G!==0||T.isRenderTargetTexture||W.has(T)){let Ct=W.get(T),zn=W.get(O);b.bindFramebuffer(B.READ_FRAMEBUFFER,L),b.bindFramebuffer(B.DRAW_FRAMEBUFFER,k);for(let _t=0;_t<Me;_t++)Jr?B.framebufferTextureLayer(B.READ_FRAMEBUFFER,B.COLOR_ATTACHMENT0,Ct.__webglTexture,G,Ke+_t):B.framebufferTexture2D(B.READ_FRAMEBUFFER,B.COLOR_ATTACHMENT0,B.TEXTURE_2D,Ct.__webglTexture,G),ft?B.framebufferTextureLayer(B.DRAW_FRAMEBUFFER,B.COLOR_ATTACHMENT0,zn.__webglTexture,pe,Nt+_t):B.framebufferTexture2D(B.DRAW_FRAMEBUFFER,B.COLOR_ATTACHMENT0,B.TEXTURE_2D,zn.__webglTexture,pe),G!==0?B.blitFramebuffer(Ae,We,be,fe,we,nt,be,fe,B.COLOR_BUFFER_BIT,B.NEAREST):ft?B.copyTexSubImage3D(ve,pe,we,nt,Nt+_t,Ae,We,be,fe):B.copyTexSubImage2D(ve,pe,we,nt,Ae,We,be,fe);b.bindFramebuffer(B.READ_FRAMEBUFFER,null),b.bindFramebuffer(B.DRAW_FRAMEBUFFER,null)}else ft?T.isDataTexture||T.isData3DTexture?B.texSubImage3D(ve,pe,we,nt,Nt,be,fe,Me,pt,ei,xt.data):O.isCompressedArrayTexture?B.compressedTexSubImage3D(ve,pe,we,nt,Nt,be,fe,Me,pt,xt.data):B.texSubImage3D(ve,pe,we,nt,Nt,be,fe,Me,pt,ei,xt):T.isDataTexture?B.texSubImage2D(B.TEXTURE_2D,pe,we,nt,be,fe,pt,ei,xt.data):T.isCompressedTexture?B.compressedTexSubImage2D(B.TEXTURE_2D,pe,we,nt,xt.width,xt.height,pt,xt.data):B.texSubImage2D(B.TEXTURE_2D,pe,we,nt,be,fe,pt,ei,xt);b.pixelStorei(B.UNPACK_ROW_LENGTH,ai),b.pixelStorei(B.UNPACK_IMAGE_HEIGHT,et),b.pixelStorei(B.UNPACK_SKIP_PIXELS,Pi),b.pixelStorei(B.UNPACK_SKIP_ROWS,Ki),b.pixelStorei(B.UNPACK_SKIP_IMAGES,kn),pe===0&&O.generateMipmaps&&B.generateMipmap(ve),b.unbindTexture()},this.initRenderTarget=function(T){W.get(T).__webglFramebuffer===void 0&&Z.setupRenderTarget(T)},this.initTexture=function(T){T.isCubeTexture?Z.setTextureCube(T,0):T.isData3DTexture?Z.setTexture3D(T,0):T.isDataArrayTexture||T.isCompressedArrayTexture?Z.setTexture2DArray(T,0):Z.setTexture2D(T,0),b.unbindTexture()},this.resetState=function(){H=0,X=0,Y=null,b.reset(),me.reset()},typeof __THREE_DEVTOOLS__<"u"&&__THREE_DEVTOOLS__.dispatchEvent(new CustomEvent("observe",{detail:this}))}get coordinateSystem(){return Gi}get outputColorSpace(){return this._outputColorSpace}set outputColorSpace(e){this._outputColorSpace=e;let t=this.getContext();t.drawingBufferColorSpace=je._getDrawingBufferColorSpace(e),t.unpackColorSpace=je._getUnpackColorSpace()}};function Rg(i,e,t="/runs/"){if(!i||!i.cache)return i;let n=`${location.origin}${t}${encodeURIComponent(e)}/map.html`;return{...i,cache:new URL(i.cache,n).pathname}}var vd="data",Lc="imagery",Pg=1,Ig=2;function Rw(i,e="/runs/"){return e+encodeURIComponent(i)+"/ATTRIBUTION.txt"}function Pw(i){let e=i;return!!e&&typeof e=="object"&&typeof e.attribution=="string"&&typeof e.licence=="string"}function Lg(i,e){let t=Array.isArray(i)?i.filter(Pw):[];return t.length?Tp(t.map(n=>({...n,url:typeof n.url=="string"?n.url:""})),Rw(e)):null}function Dg(i,e){return i==="ortho"&&e?wp(e):i==="esri"?Mp():null}var bd="ring",Ng=3,Ug='<a href="https://mapterhorn.com/attribution">\xA9 Mapterhorn</a>';function Iw(i){return{H0:i.pretension*1e3,EA:1e4/(i.stretch/100),w:Math.max(i.webbing_weight/1e3*9.80665,1e-6),P:i.athlete_mass*9.80665}}function lr(i,e,t,n,r){let s=e-n*t;return[i*t/r+i/n*(Math.asinh(e/i)-Math.asinh(s/i)),(e*t-.5*n*t*t)/r+(Math.hypot(i,e)-Math.hypot(i,s))/n,s]}function Sd(i){return Math.sqrt(i.reduce((e,t)=>e+t*t,0))}function Og(i){return i.every(e=>isFinite(e))}function Lw(i,e){let t=e.length,n=i.map((s,a)=>s.concat([e[a]]));for(let s=0;s<t;s++){let a=s;for(let l=s+1;l<t;l++)Math.abs(n[l][s])>Math.abs(n[a][s])&&(a=l);if(Math.abs(n[a][s])<1e-300)return null;let o=n[s];n[s]=n[a],n[a]=o;for(let l=s+1;l<t;l++){let c=n[l][s]/n[s][s];for(let h=s;h<=t;h++)n[l][h]-=c*n[s][h]}}let r=new Array(t);for(let s=t-1;s>=0;s--){let a=n[s][t];for(let o=s+1;o<t;o++)a-=n[s][o]*r[o];r[s]=a/n[s][s]}return r}function Md(i,e,t){let n=e.slice(),r=i(n);if(!Og(r))return null;for(let s=0;s<60;s++){let a=Sd(r);if(a<1e-9)return n;let o=r.map(()=>[]);for(let d=0;d<n.length;d++){let f=1e-7*Math.max(Math.abs(n[d]),t[d]),p=n.slice();p[d]+=f;let y=i(p);for(let m=0;m<r.length;m++)o[m][d]=(y[m]-r[m])/f}let l=Lw(o,r.map(d=>-d));if(!l)return null;let c=1,h=n,u=r;for(;c>1e-4&&(h=n.map((d,f)=>d+c*l[f]),u=i(h),!(Og(u)&&Sd(u)<a));)c/=2;if(c<=1e-4)return a<1e-6?n:null;n=h,r=u}return Sd(r)<1e-6?n:null}function Fg(i,e,t){let n=Math.hypot(i,e),r=Md(s=>{let a=lr(t.H0,s[0],s[1],t.w,t.EA);return[a[0]-i,a[1]-e]},[.5*t.w*n+t.H0*e/i,n/(1+t.H0/t.EA)],[t.H0,i]);return r&&{L0:r[1],V:r[0]}}function to(i,e,t,n,r,s){let a=h=>u=>{let d=lr(u[0],u[1],u[2],t.w,t.EA),f=lr(u[0],d[2]-h,r-u[2],t.w,t.EA);return[d[0]+f[0]-i,d[1]+f[1]-e,d[0]-n]},o=[t.H0,t.H0,i],l;if(s)l=Md(a(t.P),s,o);else{let h=Fg(i,e,t);if(!h)return null;l=[t.H0,h.V,r*n/i];for(let u=1;u<=8&&l;u++)l=Md(a(t.P*u/8),l,o)}if(!l)return null;let c=lr(l[0],l[1],l[2],t.w,t.EA)[1];return{H:l[0],sag:c-e/i*n,solution:l}}function Dw(i,e,t,n){let[r,s,a]=e.solution,o=Math.max(1,Math.round(n*a/t)),l=[];for(let u=0;u<=o;u++){let d=lr(r,s,a*u/o,i.w,i.EA);l.push([d[0],d[1]])}let c=lr(r,s,a,i.w,i.EA),h=Math.max(1,n-o);for(let u=1;u<=h;u++){let d=lr(r,c[2]-i.P,(t-a)*u/h,i.w,i.EA);l.push([c[0]+d[0],c[1]+d[1]])}return l}function Bg(i,e,t){let n=Iw(t),r=Fg(i,e,n);if(!r)return null;let s=[];for(let f=0;f<=50;f++){let p=lr(n.H0,r.V,r.L0*f/50,n.w,n.EA);s.push([p[0],p[1]])}let a=42,o=[],l=[],c=[],h=[],u=Math.floor(a/2);for(let f=0;f<a;f++)o.push(f/(a-1)),l.push(0),c.push(n.H0),h.push(null);let d=to(i,e,n,o[u]*i,r.L0);if(!d)return null;l[u]=d.sag,c[u]=d.H,h[u]=d.solution;for(let f=-1;f<=1;f+=2){let p=d.solution;for(let y=u+f;f<0?y>0:y<a-1;y+=f){let m=to(i,e,n,o[y]*i,r.L0,p)||to(i,e,n,o[y]*i,r.L0);if(!m)return null;l[y]=m.sag,c[y]=m.H,h[y]=m.solution,p=m.solution}}return{L0:r.L0,unloaded:s,f:o,sag:l,H:c,sagAt(f){let p=Math.min(a-2,Math.floor(f*(a-1))),y=f*(a-1)-p;return l[p]*(1-y)+l[p+1]*y},athlete(f){let p=f/i,y=Math.max(1,Math.min(a-2,Math.round(p*(a-1)))),m=to(i,e,n,f,r.L0,h[y])||to(i,e,n,f,r.L0);return m&&{sag:m.sag,H:m.H,curve:Dw(n,m,r.L0,60)}}}}function zg(i){return{cx:i.left+i.width*i.res/2,cy:i.top-i.height*i.res/2,h0:i.base_dm/10}}function Hr(i,e,t,n){return[e-i.cx,n-i.h0,-(t-i.cy)]}function wd(i,e,t,n,r){let s=t>0?n/t:0;return[i.x+(e.x-i.x)*s,i.y+(e.y-i.y)*s,i.h-r]}function Td(i,e){let[t,n]=i,r=Math.hypot(n.x-t.x,n.y-t.y),s=t.h-n.h;if(!(r>0))return null;let a=Bg(r,s,e);if(!a)return null;let o=0;for(let l=1;l<a.sag.length;l++)a.sag[l]>a.sag[o]&&(o=l);return{span:r,dh:s,estimate:a,unloaded:a.unloaded.map(([l,c])=>wd(t,n,r,l,c)),start:{s:a.f[o]*r,sag:a.sag[o]}}}function Vg(i,e,t){let[n,r]=e,s=Math.min(i.span,Math.max(0,t)),a=i.estimate.athlete(s);if(!a)return null;let o=i.dh/i.span*s;return{points:a.curve.map(([l,c])=>wd(n,r,i.span,l,c)),walker:wd(n,r,i.span,s,o+a.sag),sag:a.sag}}function Dc(i,e,t){let[n,r,s,a,o,l]=i;return[n+r*e+s*t,a+o*e+l*t]}var kg=6378137;function Gg(i,e){let t=Math.max(-85.0511287798,Math.min(85.0511287798,e))*Math.PI/180;return[kg*i*Math.PI/180,kg*Math.log(Math.tan(Math.PI/4+t/2))]}var It=256,Hg=2048,Nw={full:6e7,phone:18e6},Wg=17,Uw=19,Ow=60,Ed=Math.PI*6378137;function io(i,e,t,n){let[r,s]=Dc(i,e,t),[a,o]=Gg(r,s),l=It*2**n/(2*Ed);return[(a+Ed)*l,(Ed-o)*l]}function Xg(i,e){let t=Math.max(e.x0,i.left),n=Math.min(e.x1,i.left+i.width*i.res),r=Math.max(e.y0,i.top-i.height*i.res),s=Math.min(e.y1,i.top);return n>t&&s>r?{x0:t,y0:r,x1:n,y1:s}:null}function Cd(i,e,t){let n=1/0,r=1/0,s=-1/0,a=-1/0;for(let[c,h]of[[e.x0,e.y0],[e.x1,e.y0],[e.x0,e.y1],[e.x1,e.y1]]){let[u,d]=io(i,c,h,t);n=Math.min(n,u),s=Math.max(s,u),r=Math.min(r,d),a=Math.max(a,d)}let o=Math.floor(n),l=Math.floor(r);return{z:t,px0:o,py0:l,width:Math.max(1,Math.ceil(s)-o),height:Math.max(1,Math.ceil(a)-l)}}function Fw(i,e,t){let n=Cd(i,e,t);for(;n.z>0&&(n.width>Hg||n.height>Hg);)n=Cd(i,e,n.z-1);return n}function Ad(i){return i.width*i.height*4*4/3}function Bw(i,e){return e==="full"&&i?Uw:Wg}function qg(i,e,t){let n=e.map(s=>s.bounds?Fw(i,s.bounds,Bw(s.hasLine,t)):null),r=()=>n.reduce((s,a)=>s+(a?Ad(a):0),0);for(;r()>Nw[t];){let s=-1;if(n.forEach((a,o)=>{a&&a.z>0&&(s<0||Ad(a)>Ad(n[s]))&&(s=o)}),s<0)break;n[s]=Cd(i,e[s].bounds,n[s].z-1)}return n}function jg(i){let e=2**i.z,t=[],n=Math.floor(i.px0/It),r=Math.floor((i.px0+i.width-1)/It),s=Math.max(0,Math.floor(i.py0/It)),a=Math.min(e-1,Math.floor((i.py0+i.height-1)/It));for(let o=s;o<=a;o++)for(let l=n;l<=r;l++)t.push([l,o]);return t}function Yg(i,e){return(t,n)=>{let[r,s]=io(i,t,n,e.z);return[(r-e.px0)/e.width,1-(s-e.py0)/e.height]}}function $g(i,e,t,n,r){let s=Math.max(0,e-r),a=i.replace(/\{z\}/g,String(e-s)).replace(/\{x\}/g,String(t>>s)).replace(/\{y\}/g,String(n>>s));if(!s)return{url:a};let o=2**s,l=It/o;return{url:a,crop:[t%o*l,n%o*l,l]}}function kw(i,e,t){let n=2**i,r=s=>Math.atan(Math.sinh(Math.PI*(1-2*s/n)))*180/Math.PI;return[r(t+1),e/n*360-180,r(t),(e+1)/n*360-180].join(",")}function zw(i,e,t,n){let r=!!i.base,s=i.url,a=[["service","WMS"],["request","GetMap"],["layers",i.layer],["styles",""],["format",r?"image/png":"image/jpeg"],["transparent",String(r)],["version","1.3.0"],["width",String(It)],["height",String(It)],["crs","EPSG:4326"]];return{url:s+(s.includes("?")?"&":"?")+a.map(([o,l])=>o+"="+encodeURIComponent(l)).join("&")+"&bbox="+kw(e,t,n)}}function Vw(i,e,t,n){let r=[];return i.base&&r.push($g(i.base.url,e,t,n,i.base.max_zoom)),i.url&&r.push(zw(i,e,t,n)),r}function Gw(i,e,t,n){return`${i}/${e}/${t}/${n}.jpg`}function Zg(i,e,t){let[n,r]=e,s=io(i,n.x,n.y,t),a=io(i,r.x,r.y,t),o=Math.hypot(r.x-n.x,r.y-n.y),l=io(i,n.x+1,n.y,t),c=o>0?Math.hypot(a[0]-s[0],a[1]-s[1])/o:Math.hypot(l[0]-s[0],l[1]-s[1]);return{a:s,b:a,half:Ow*c}}function Hw(i,e,t,n){let r=n[0]-t[0],s=n[1]-t[1],a=r*r+s*s,o=a>0?Math.max(0,Math.min(1,((i-t[0])*r+(e-t[1])*s)/a)):0;return Math.hypot(i-t[0]-o*r,e-t[1]-o*s)}function Ww(i,e,t){let n=e*It,r=t*It,s=n+It,a=r+It,o=u=>u[0]>=n&&u[0]<=s&&u[1]>=r&&u[1]<=a;if(o(i.a)||o(i.b))return 0;let l=[[n,r],[s,r],[s,a],[n,a]],c=(u,d,f,p)=>{let y=(d[0]-u[0])*(p[1]-f[1])-(d[1]-u[1])*(p[0]-f[0]);if(y===0)return!1;let m=((f[0]-u[0])*(p[1]-f[1])-(f[1]-u[1])*(p[0]-f[0]))/y,g=((f[0]-u[0])*(d[1]-u[1])-(f[1]-u[1])*(d[0]-u[0]))/y;return m>=0&&m<=1&&g>=0&&g<=1};if(l.some((u,d)=>c(i.a,i.b,u,l[(d+1)%4])))return 0;let h=(u,d,f)=>Math.max(d,Math.min(f,u));return Math.min(...l.map(([u,d])=>Hw(u,d,i.a,i.b)),...[i.a,i.b].map(([u,d])=>Math.hypot(u-h(u,n,s),d-h(d,r,a))))}function Xw(i,e,t,n){return i<=16?!0:i===Wg||!n?!1:Ww(n,e,t)<=n.half}function Kg(i,e,t){return jg(e).map(([n,r])=>({x:n,y:r,cache:i.cache&&Xw(e.z,n,r,t)?Gw(i.cache,e.z,n,r):null,layers:Vw(i,e.z,n,r)}))}function Jg(i,e){let t=Fo(i);return jg(e).map(([n,r])=>({x:n,y:r,cache:null,layers:[$g(t,e.z,n,r,Oo)]}))}function Qg(i,e=1){return i+(i.includes("?")?"&":"?")+"_fal3d="+e}function Nc(i){let e=i;return!e||typeof e!="object"||typeof e.name!="string"||typeof e.attribution!="string"||!e.url&&!(e.base&&typeof e.base.url=="string")?null:e}var qw=6,jw={ortho:"ui.view3d.imagery_ortho",esri:"ui.view3d.imagery_esri",shaded:"ui.view3d.imagery_shaded"},Rd=class{constructor(){this.waiting=[];this.active=new Set;this.running=0;this.stopped=!1}load(e){return new Promise(t=>{let n=()=>{if(this.stopped){t(null);return}this.running++;let r=new Image;this.active.add(r);let s=a=>{r.onload=r.onerror=null,this.active.delete(r),this.running--,this.waiting.shift()?.(),t(a&&!this.stopped?r:null)};r.onload=()=>s(!0),r.onerror=()=>s(!1),r.crossOrigin="anonymous",r.decoding="async",r.src=e};this.running<qw?n():this.waiting.push(n)})}async service(e){return await this.load(e)??(this.stopped?null:await this.load(Qg(e)))}stop(){this.stopped=!0;for(let e of this.waiting.splice(0))e();for(let e of this.active)e.src=""}};function Yw(i,e,t,n,r){if(t.crop){let[s,a,o]=t.crop;i.drawImage(e,s,a,o,o,n,r,It,It)}else i.drawImage(e,n,r,It,It)}async function $w(i,e,t,n){let r=document.createElement("canvas");r.width=i.width,r.height=i.height;let s=r.getContext("2d");return s?(s.fillStyle=n,s.fillRect(0,0,i.width,i.height),await Promise.all(e.map(async a=>{let o=a.x*It-i.px0,l=a.y*It-i.py0,c=a.cache?await t.load(a.cache):null;if(c){s.drawImage(c,o,l,It,It);return}(await Promise.all(a.layers.map(u=>t.service(u.url)))).forEach((u,d)=>{u&&Yw(s,u,a.layers[d],o,l)})})),t.stopped?null:r):null}function e0(i,e){let{meta:t}=i,n=Rg(Nc(t.ortho),e.runId),r=[...n?["ortho"]:[],...e.esriKey?["esri"]:[],"shaded"],s=Lg(t.attribution,e.runId);s&&i.credits.set(vd,s,Pg);let a=i.chunks.map((_,M)=>M).sort((_,M)=>Number(i.chunks[M].hasLine)-Number(i.chunks[_].hasLine)),o=qg(t.affine,i.chunks.map(_=>({bounds:Xg(t,_.bounds),hasLine:_.hasLine})),i.level),l=new Map,c=_=>(l.has(_)||l.set(_,Zg(t.affine,t.anchors,_)),l.get(_)),h=new Map,u=new Set,d=null,f=document.createElement("div");f.className="u-row";let p=new Map;if(r.length>1){let _=document.createElement("div");_.className="u-seg",_.setAttribute("role","radiogroup"),_.setAttribute("aria-label",tt("ui.view3d.imagery"));for(let M of r){let w=document.createElement("button");w.type="button",w.setAttribute("role","radio"),w.textContent=tt(jw[M]),w.onclick=()=>{S.set(M)},p.set(M,w),_.append(w)}f.append(_)}else{let _=document.createElement("span");_.className="u-small",_.textContent=tt("ui.view3d.no_imagery"),f.append(_)}let y=document.createElement("span");y.className="u-small",y.setAttribute("role","status"),y.hidden=!0,y.textContent=tt("ui.view3d.loading_imagery"),f.append(y),i.toolbar.append(f);let m=_=>p.forEach((M,w)=>{M.className=w===_?"u-on":"",M.setAttribute("aria-checked",String(w===_))}),g=(_,M,w)=>{_.setTexture(M,w),h.get(_)?.dispose(),M?h.set(_,M):h.delete(_)},v=()=>getComputedStyle(i.toolbar).getPropertyValue("--terrain").trim()||"#bba680",S={available:r,current:r[0],async set(_){if(!r.includes(_))return;d?.stop();let M=S.current!==_;if(S.current=_,m(_),M)for(let A of[...u])A(_);let w=Dg(_,n);if(w?i.credits.set(Lc,w,Ig):i.credits.remove(Lc),_==="shaded"){d=null,y.hidden=!0;for(let A of i.chunks)g(A,null);i.invalidate();return}let E=d=new Rd,x=v();y.hidden=!1,await Promise.all(a.map(async A=>{let C=o[A],D=i.chunks[A];if(!C){g(D,null);return}let U=_==="esri"?Jg(e.esriKey,C):Kg(n,C,D.hasLine?c(C.z):null),I=await $w(C,U,E,x);if(!I||E.stopped)return;let L=new Kn(I);L.colorSpace=bt,L.minFilter=Ci,L.generateMipmaps=!0,L.flipY=!0,g(D,L,Yg(t.affine,C)),i.invalidate()})),d===E&&(y.hidden=!0,d=null)},onChange(_){return u.add(_),()=>{u.delete(_)}},dispose(){u.clear(),d?.stop(),d=null;for(let _ of[...h.keys()])g(_,null);i.credits.remove(Lc),i.credits.remove(vd),f.remove()}};return m(S.current),S.set(S.current),S}var t0=new Mt,Uc=new P,Gs=class extends Ua{constructor(){super(),this.isLineSegmentsGeometry=!0,this.type="LineSegmentsGeometry";let e=[-1,2,0,1,2,0,-1,1,0,1,1,0,-1,0,0,1,0,0,-1,-1,0,1,-1,0],t=[-1,2,1,2,-1,1,1,1,-1,-1,1,-1,-1,-2,1,-2],n=[0,2,1,2,3,1,2,4,3,4,5,3,4,6,5,6,7,5];this.setIndex(n),this.setAttribute("position",new st(e,3)),this.setAttribute("uv",new st(t,2))}applyMatrix4(e){let t=this.attributes.instanceStart,n=this.attributes.instanceEnd;return t!==void 0&&(t.applyMatrix4(e),n.applyMatrix4(e),t.needsUpdate=!0),this.boundingBox!==null&&this.computeBoundingBox(),this.boundingSphere!==null&&this.computeBoundingSphere(),this}setPositions(e){let t;e instanceof Float32Array?t=e:Array.isArray(e)&&(t=new Float32Array(e));let n=new tr(t,6,1);return this.setAttribute("instanceStart",new xi(n,3,0)),this.setAttribute("instanceEnd",new xi(n,3,3)),this.instanceCount=this.attributes.instanceStart.count,this.computeBoundingBox(),this.computeBoundingSphere(),this}setColors(e){let t;e instanceof Float32Array?t=e:Array.isArray(e)&&(t=new Float32Array(e));let n=new tr(t,6,1);return this.setAttribute("instanceColorStart",new xi(n,3,0)),this.setAttribute("instanceColorEnd",new xi(n,3,3)),this}fromWireframeGeometry(e){return this.setPositions(e.attributes.position.array),this}fromEdgesGeometry(e){return this.setPositions(e.attributes.position.array),this}fromMesh(e){return this.fromWireframeGeometry(new Aa(e.geometry)),this}fromLineSegments(e){let t=e.geometry;return this.setPositions(t.attributes.position.array),this}computeBoundingBox(){this.boundingBox===null&&(this.boundingBox=new Mt);let e=this.attributes.instanceStart,t=this.attributes.instanceEnd;e!==void 0&&t!==void 0&&(this.boundingBox.setFromBufferAttribute(e),t0.setFromBufferAttribute(t),this.boundingBox.union(t0))}computeBoundingSphere(){this.boundingSphere===null&&(this.boundingSphere=new Et),this.boundingBox===null&&this.computeBoundingBox();let e=this.attributes.instanceStart,t=this.attributes.instanceEnd;if(e!==void 0&&t!==void 0){let n=this.boundingSphere.center;this.boundingBox.getCenter(n);let r=0;for(let s=0,a=e.count;s<a;s++)Uc.fromBufferAttribute(e,s),r=Math.max(r,n.distanceToSquared(Uc)),Uc.fromBufferAttribute(t,s),r=Math.max(r,n.distanceToSquared(Uc));this.boundingSphere.radius=Math.sqrt(r),isNaN(this.boundingSphere.radius)&&console.error("THREE.LineSegmentsGeometry.computeBoundingSphere(): Computed radius is NaN. The instanced position data is likely to have NaN values.",this)}}toJSON(){}};ae.line={worldUnits:{value:1},linewidth:{value:1},resolution:{value:new Se},dashOffset:{value:0},dashScale:{value:1},dashSize:{value:1},gapSize:{value:1}};pi.line={uniforms:Za.merge([ae.common,ae.fog,ae.line]),vertexShader:`
		#include <common>
		#include <color_pars_vertex>
		#include <fog_pars_vertex>
		#include <logdepthbuf_pars_vertex>
		#include <clipping_planes_pars_vertex>

		uniform float linewidth;
		uniform vec2 resolution;

		attribute vec3 instanceStart;
		attribute vec3 instanceEnd;

		attribute vec3 instanceColorStart;
		attribute vec3 instanceColorEnd;

		#ifdef WORLD_UNITS

			varying vec4 worldPos;
			varying vec3 worldStart;
			varying vec3 worldEnd;

			#ifdef USE_DASH

				varying vec2 vUv;

			#endif

		#else

			varying vec2 vUv;

		#endif

		#ifdef USE_DASH

			uniform float dashScale;
			attribute float instanceDistanceStart;
			attribute float instanceDistanceEnd;
			varying float vLineDistance;

		#endif

		float trimSegmentAlpha( const in vec4 start, const in vec4 end ) {

			// compute the interpolation factor needed to trim the segment so it terminates
			// between the camera plane and the near plane

			// conservative estimate of the near plane
			float a = projectionMatrix[ 2 ][ 2 ]; // 3nd entry in 3th column
			float b = projectionMatrix[ 3 ][ 2 ]; // 3nd entry in 4th column

			// we need different nearEstimate formula for reversed and default depth buffer
			// a is positive with a reversed depth buffer so it can be used for controlling the code flow
			float nearEstimate = ( a > 0.0 ) ? ( - b / ( a + 1.0 ) ) : ( - 0.5 * b / a );

			return ( nearEstimate - start.z ) / ( end.z - start.z );

		}

		void main() {

			#ifdef USE_COLOR

				vColor.xyz = ( position.y < 0.5 ) ? instanceColorStart : instanceColorEnd;

			#endif

			float aspect = resolution.x / resolution.y;

			// camera space
			vec4 start = modelViewMatrix * vec4( instanceStart, 1.0 );
			vec4 end = modelViewMatrix * vec4( instanceEnd, 1.0 );

			#ifdef USE_DASH

				float lineDistanceStart = dashScale * instanceDistanceStart;
				float lineDistanceEnd = dashScale * instanceDistanceEnd;

			#endif

			#ifdef WORLD_UNITS

				worldStart = start.xyz;
				worldEnd = end.xyz;

			#else

				vUv = uv;

			#endif

			// special case for perspective projection, and segments that terminate either in, or behind, the camera plane
			// clearly the gpu firmware has a way of addressing this issue when projecting into ndc space
			// but we need to perform ndc-space calculations in the shader, so we must address this issue directly
			// perhaps there is a more elegant solution -- WestLangley

			bool perspective = ( projectionMatrix[ 2 ][ 3 ] == - 1.0 ); // 4th entry in the 3rd column

			if ( perspective ) {

				if ( start.z < 0.0 && end.z >= 0.0 ) {

					float alpha = trimSegmentAlpha( start, end );
					end.xyz = mix( start.xyz, end.xyz, alpha );

					#ifdef USE_DASH

						lineDistanceEnd = mix( lineDistanceStart, lineDistanceEnd, alpha );

					#endif

				} else if ( end.z < 0.0 && start.z >= 0.0 ) {

					float alpha = trimSegmentAlpha( end, start );
					start.xyz = mix( end.xyz, start.xyz, alpha );

					#ifdef USE_DASH

						lineDistanceStart = mix( lineDistanceEnd, lineDistanceStart, alpha );

					#endif

				}

			}

			#ifdef USE_DASH

				vLineDistance = ( position.y < 0.5 ) ? lineDistanceStart : lineDistanceEnd;
				vUv = uv;

			#endif

			// clip space
			vec4 clipStart = projectionMatrix * start;
			vec4 clipEnd = projectionMatrix * end;

			// ndc space
			vec3 ndcStart = clipStart.xyz / clipStart.w;
			vec3 ndcEnd = clipEnd.xyz / clipEnd.w;

			// direction
			vec2 dir = ndcEnd.xy - ndcStart.xy;

			// account for clip-space aspect ratio
			dir.x *= aspect;
			dir = normalize( dir );

			#ifdef WORLD_UNITS

				vec3 worldDir = normalize( end.xyz - start.xyz );
				vec3 tmpFwd = normalize( mix( start.xyz, end.xyz, 0.5 ) );
				vec3 worldUp = normalize( cross( worldDir, tmpFwd ) );
				vec3 worldFwd = cross( worldDir, worldUp );
				worldPos = position.y < 0.5 ? start: end;

				// height offset
				float hw = linewidth * 0.5;
				worldPos.xyz += position.x < 0.0 ? hw * worldUp : - hw * worldUp;

				// don't extend the line if we're rendering dashes because we
				// won't be rendering the endcaps
				#ifndef USE_DASH

					// cap extension
					worldPos.xyz += position.y < 0.5 ? - hw * worldDir : hw * worldDir;

					// add width to the box
					worldPos.xyz += worldFwd * hw;

					// endcaps
					if ( position.y > 1.0 || position.y < 0.0 ) {

						worldPos.xyz -= worldFwd * 2.0 * hw;

					}

				#endif

				// project the worldpos
				vec4 clip = projectionMatrix * worldPos;

				// shift the depth of the projected points so the line
				// segments overlap neatly
				vec3 clipPose = ( position.y < 0.5 ) ? ndcStart : ndcEnd;
				clip.z = clipPose.z * clip.w;

			#else

				vec2 offset = vec2( dir.y, - dir.x );
				// undo aspect ratio adjustment
				dir.x /= aspect;
				offset.x /= aspect;

				// sign flip
				if ( position.x < 0.0 ) offset *= - 1.0;

				// endcaps
				if ( position.y < 0.0 ) {

					offset += - dir;

				} else if ( position.y > 1.0 ) {

					offset += dir;

				}

				// adjust for linewidth
				offset *= linewidth;

				// adjust for clip-space to screen-space conversion // maybe resolution should be based on viewport ...
				offset /= resolution.y;

				// select end
				vec4 clip = ( position.y < 0.5 ) ? clipStart : clipEnd;

				// back to clip space
				offset *= clip.w;

				clip.xy += offset;

			#endif

			gl_Position = clip;

			vec4 mvPosition = ( position.y < 0.5 ) ? start : end; // this is an approximation

			#include <logdepthbuf_vertex>
			#include <clipping_planes_vertex>
			#include <fog_vertex>

		}
		`,fragmentShader:`
		uniform vec3 diffuse;
		uniform float opacity;
		uniform float linewidth;

		#ifdef USE_DASH

			uniform float dashOffset;
			uniform float dashSize;
			uniform float gapSize;

		#endif

		varying float vLineDistance;

		#ifdef WORLD_UNITS

			varying vec4 worldPos;
			varying vec3 worldStart;
			varying vec3 worldEnd;

			#ifdef USE_DASH

				varying vec2 vUv;

			#endif

		#else

			varying vec2 vUv;

		#endif

		#include <common>
		#include <color_pars_fragment>
		#include <fog_pars_fragment>
		#include <logdepthbuf_pars_fragment>
		#include <clipping_planes_pars_fragment>

		vec2 closestLineToLine(vec3 p1, vec3 p2, vec3 p3, vec3 p4) {

			float mua;
			float mub;

			vec3 p13 = p1 - p3;
			vec3 p43 = p4 - p3;

			vec3 p21 = p2 - p1;

			float d1343 = dot( p13, p43 );
			float d4321 = dot( p43, p21 );
			float d1321 = dot( p13, p21 );
			float d4343 = dot( p43, p43 );
			float d2121 = dot( p21, p21 );

			float denom = d2121 * d4343 - d4321 * d4321;

			float numer = d1343 * d4321 - d1321 * d4343;

			mua = numer / denom;
			mua = clamp( mua, 0.0, 1.0 );
			mub = ( d1343 + d4321 * ( mua ) ) / d4343;
			mub = clamp( mub, 0.0, 1.0 );

			return vec2( mua, mub );

		}

		void main() {

			float alpha = opacity;
			vec4 diffuseColor = vec4( diffuse, alpha );

			#include <clipping_planes_fragment>

			#ifdef USE_DASH

				if ( vUv.y < - 1.0 || vUv.y > 1.0 ) discard; // discard endcaps

				if ( mod( vLineDistance + dashOffset, dashSize + gapSize ) > dashSize ) discard; // todo - FIX

			#endif

			#ifdef WORLD_UNITS

				// Find the closest points on the view ray and the line segment
				vec3 rayEnd = normalize( worldPos.xyz ) * 1e5;
				vec3 lineDir = worldEnd - worldStart;
				vec2 params = closestLineToLine( worldStart, worldEnd, vec3( 0.0, 0.0, 0.0 ), rayEnd );

				vec3 p1 = worldStart + lineDir * params.x;
				vec3 p2 = rayEnd * params.y;
				vec3 delta = p1 - p2;
				float len = length( delta );
				float norm = len / linewidth;

				#ifndef USE_DASH

					#ifdef USE_ALPHA_TO_COVERAGE

						float dnorm = fwidth( norm );
						alpha = 1.0 - smoothstep( 0.5 - dnorm, 0.5 + dnorm, norm );

					#else

						if ( norm > 0.5 ) {

							discard;

						}

					#endif

				#endif

			#else

				#ifdef USE_ALPHA_TO_COVERAGE

					// artifacts appear on some hardware if a derivative is taken within a conditional
					float a = vUv.x;
					float b = ( vUv.y > 0.0 ) ? vUv.y - 1.0 : vUv.y + 1.0;
					float len2 = a * a + b * b;
					float dlen = fwidth( len2 );

					if ( abs( vUv.y ) > 1.0 ) {

						alpha = 1.0 - smoothstep( 1.0 - dlen, 1.0 + dlen, len2 );

					}

				#else

					if ( abs( vUv.y ) > 1.0 ) {

						float a = vUv.x;
						float b = ( vUv.y > 0.0 ) ? vUv.y - 1.0 : vUv.y + 1.0;
						float len2 = a * a + b * b;

						if ( len2 > 1.0 ) discard;

					}

				#endif

			#endif

			#include <logdepthbuf_fragment>
			#include <color_fragment>

			gl_FragColor = vec4( diffuseColor.rgb, alpha );

			#include <tonemapping_fragment>
			#include <colorspace_fragment>
			#include <fog_fragment>
			#include <premultiplied_alpha_fragment>

		}
		`};var Nn=class extends $t{constructor(e){super({type:"LineMaterial",uniforms:Za.clone(pi.line.uniforms),vertexShader:pi.line.vertexShader,fragmentShader:pi.line.fragmentShader,clipping:!0}),this.isLineMaterial=!0,this.setValues(e)}get color(){return this.uniforms.diffuse.value}set color(e){this.uniforms.diffuse.value=e}get worldUnits(){return"WORLD_UNITS"in this.defines}set worldUnits(e){e===!0!==this.worldUnits&&(this.needsUpdate=!0),e===!0?this.defines.WORLD_UNITS="":delete this.defines.WORLD_UNITS}get linewidth(){return this.uniforms.linewidth.value}set linewidth(e){this.uniforms.linewidth&&(this.uniforms.linewidth.value=e)}get dashed(){return"USE_DASH"in this.defines}set dashed(e){e===!0!==this.dashed&&(this.needsUpdate=!0),e===!0?this.defines.USE_DASH="":delete this.defines.USE_DASH}get dashScale(){return this.uniforms.dashScale.value}set dashScale(e){this.uniforms.dashScale.value=e}get dashSize(){return this.uniforms.dashSize.value}set dashSize(e){this.uniforms.dashSize.value=e}get dashOffset(){return this.uniforms.dashOffset.value}set dashOffset(e){this.uniforms.dashOffset.value=e}get gapSize(){return this.uniforms.gapSize.value}set gapSize(e){this.uniforms.gapSize.value=e}get opacity(){return this.uniforms.opacity.value}set opacity(e){this.uniforms&&(this.uniforms.opacity.value=e)}get resolution(){return this.uniforms.resolution.value}set resolution(e){this.uniforms.resolution.value.copy(e)}get alphaToCoverage(){return"USE_ALPHA_TO_COVERAGE"in this.defines}set alphaToCoverage(e){this.defines&&(e===!0!==this.alphaToCoverage&&(this.needsUpdate=!0),e===!0?this.defines.USE_ALPHA_TO_COVERAGE="":delete this.defines.USE_ALPHA_TO_COVERAGE)}};var Pd=new Xe,i0=new P,n0=new P,Zt=new Xe,Kt=new Xe,ln=new Xe,Id=new P,Ld=new ge,Jt=new Fa,r0=new P,Oc=new Mt,Fc=new Et,cn=new Xe,hn,Wr;function s0(i,e,t){return cn.set(0,0,-e,1).applyMatrix4(i.projectionMatrix),cn.multiplyScalar(1/cn.w),cn.x=Wr/t.width,cn.y=Wr/t.height,cn.applyMatrix4(i.projectionMatrixInverse),cn.multiplyScalar(1/cn.w),Math.abs(Math.max(cn.x,cn.y))}function Zw(i,e){let t=i.matrixWorld,n=i.geometry,r=n.attributes.instanceStart,s=n.attributes.instanceEnd,a=Math.min(n.instanceCount,r.count);for(let o=0,l=a;o<l;o++){Jt.start.fromBufferAttribute(r,o),Jt.end.fromBufferAttribute(s,o),Jt.applyMatrix4(t);let c=new P,h=new P;hn.distanceSqToSegment(Jt.start,Jt.end,h,c),h.distanceTo(c)<Wr*.5&&e.push({point:h,pointOnLine:c,distance:hn.origin.distanceTo(h),object:i,face:null,faceIndex:o,uv:null,uv1:null})}}function Kw(i,e,t){let n=e.projectionMatrix,s=i.material.resolution,a=i.matrixWorld,o=i.geometry,l=o.attributes.instanceStart,c=o.attributes.instanceEnd,h=Math.min(o.instanceCount,l.count),u=-e.near;hn.at(1,ln),ln.w=1,ln.applyMatrix4(e.matrixWorldInverse),ln.applyMatrix4(n),ln.multiplyScalar(1/ln.w),ln.x*=s.x/2,ln.y*=s.y/2,ln.z=0,Id.copy(ln),Ld.multiplyMatrices(e.matrixWorldInverse,a);for(let d=0,f=h;d<f;d++){if(Zt.fromBufferAttribute(l,d),Kt.fromBufferAttribute(c,d),Zt.w=1,Kt.w=1,Zt.applyMatrix4(Ld),Kt.applyMatrix4(Ld),Zt.z>u&&Kt.z>u)continue;if(Zt.z>u){let S=Zt.z-Kt.z,_=(Zt.z-u)/S;Zt.lerp(Kt,_)}else if(Kt.z>u){let S=Kt.z-Zt.z,_=(Kt.z-u)/S;Kt.lerp(Zt,_)}Zt.applyMatrix4(n),Kt.applyMatrix4(n),Zt.multiplyScalar(1/Zt.w),Kt.multiplyScalar(1/Kt.w),Zt.x*=s.x/2,Zt.y*=s.y/2,Kt.x*=s.x/2,Kt.y*=s.y/2,Jt.start.copy(Zt),Jt.start.z=0,Jt.end.copy(Kt),Jt.end.z=0;let y=Jt.closestPointToPointParameter(Id,!0);Jt.at(y,r0);let m=ye.lerp(Zt.z,Kt.z,y),g=m>=-1&&m<=1,v=Id.distanceTo(r0)<Wr*.5;if(g&&v){Jt.start.fromBufferAttribute(l,d),Jt.end.fromBufferAttribute(c,d),Jt.start.applyMatrix4(a),Jt.end.applyMatrix4(a);let S=new P,_=new P;hn.distanceSqToSegment(Jt.start,Jt.end,_,S),t.push({point:_,pointOnLine:S,distance:hn.origin.distanceTo(_),object:i,face:null,faceIndex:d,uv:null,uv1:null})}}}var Bc=class extends at{constructor(e=new Gs,t=new Nn({color:Math.random()*16777215})){super(e,t),this.isLineSegments2=!0,this.type="LineSegments2"}computeLineDistances(){let e=this.geometry,t=e.attributes.instanceStart,n=e.attributes.instanceEnd,r=new Float32Array(2*t.count);for(let a=0,o=0,l=t.count;a<l;a++,o+=2)i0.fromBufferAttribute(t,a),n0.fromBufferAttribute(n,a),r[o]=o===0?0:r[o-1],r[o+1]=r[o]+i0.distanceTo(n0);let s=new tr(r,2,1);return e.setAttribute("instanceDistanceStart",new xi(s,1,0)),e.setAttribute("instanceDistanceEnd",new xi(s,1,1)),this}raycast(e,t){let n=this.material.worldUnits,r=e.camera;if(r===null&&!n&&console.error('LineSegments2: "Raycaster.camera" needs to be set in order to raycast against LineSegments2 while worldUnits is set to false.'),n===!1&&(this.material.resolution.x===0||this.material.resolution.y===0))return;let s=e.params.Line2!==void 0&&e.params.Line2.threshold||0;hn=e.ray;let a=this.matrixWorld,o=this.geometry,l=this.material;Wr=l.linewidth+s,o.boundingSphere===null&&o.computeBoundingSphere(),Fc.copy(o.boundingSphere).applyMatrix4(a);let c;if(n)c=Wr*.5;else{let u=Math.max(r.near,Fc.distanceToPoint(hn.origin));c=s0(r,u,l.resolution)}if(Fc.radius+=c,hn.intersectsSphere(Fc)===!1)return;o.boundingBox===null&&o.computeBoundingBox(),Oc.copy(o.boundingBox).applyMatrix4(a);let h;if(n)h=Wr*.5;else{let u=Math.max(r.near,Oc.distanceToPoint(hn.origin));h=s0(r,u,l.resolution)}Oc.expandByScalar(h),hn.intersectsBox(Oc)!==!1&&(n?Zw(this,t):Kw(this,r,t))}onBeforeRender(e){let t=this.material.uniforms;t&&t.resolution&&(e.getViewport(Pd),this.material.uniforms.resolution.value.set(Pd.z,Pd.w))}};var Hs=class extends Gs{constructor(){super(),this.isLineGeometry=!0,this.type="LineGeometry"}setPositions(e){let t=e.length-3,n=new Float32Array(2*t);for(let r=0;r<t;r+=3)n[2*r]=e[r],n[2*r+1]=e[r+1],n[2*r+2]=e[r+2],n[2*r+3]=e[r+3],n[2*r+4]=e[r+4],n[2*r+5]=e[r+5];return super.setPositions(n),this}setColors(e){let t=e.length-3,n=new Float32Array(2*t);for(let r=0;r<t;r+=3)n[2*r]=e[r],n[2*r+1]=e[r+1],n[2*r+2]=e[r+2],n[2*r+3]=e[r+3],n[2*r+4]=e[r+4],n[2*r+5]=e[r+5];return super.setColors(n),this}setFromPoints(e){let t=e.length-1,n=new Float32Array(6*t);for(let r=0;r<t;r++)n[6*r]=e[r].x,n[6*r+1]=e[r].y,n[6*r+2]=e[r].z||0,n[6*r+3]=e[r+1].x,n[6*r+4]=e[r+1].y,n[6*r+5]=e[r+1].z||0;return super.setPositions(n),this}fromLine(e){let t=e.geometry;return this.setPositions(t.attributes.position.array),this}};var kc=class extends Bc{constructor(e=new Hs,t=new Nn({color:Math.random()*16777215})){super(e,t),this.isLine2=!0,this.type="Line2"}};var Jw=61,a0=1.7;function zc(i,e=Jw){if(i.length===e)return i.map(n=>[n[0],n[1],n[2]]);let t=[];for(let n=0;n<e;n++){let r=n/(e-1)*(i.length-1),s=Math.min(i.length-2,Math.floor(r)),a=r-s,o=i[s],l=i[s+1];t.push([o[0]+(l[0]-o[0])*a,o[1]+(l[1]-o[1])*a,o[2]+(l[2]-o[2])*a])}return t}function o0(i,e,t){for(let n=0;n+1<i.length;n++){let r=Hr(e,...i[n]),s=Hr(e,...i[n+1]);t.set(r,6*n),t.set(s,6*n+3)}}function Dd(i,e,t){let n=Vg(i,e,t);if(!n)return null;let[r,s]=e,a=Math.atan2(s.x-r.x,-(s.y-r.y));return{at:n.walker,points:zc(n.points),sag:n.sag,yaw:a}}function l0(i){return{length:i.d[i.d.length-1],clearance:i.min[1],overTrees:!!i.min_nmpt&&i.min_nmpt[1]<=0}}function no(i){return i.toFixed(1)}function c0(i){let e=new Xt,t=new En({color:i}),n=[],r=(l,c,h,u,d=0)=>{n.push(l);let f=new at(l,t);return f.position.set(c,h,u),f.rotation.z=d,e.add(f),f},s=a0/1.7,a=()=>new Lr(.06*s,.73*s,4,8);r(a(),-.09*s,.425*s,0,.06),r(a(),.09*s,.425*s,0,-.06),r(new Lr(.15*s,.32*s,4,10),0,1.16*s,0),r(new Cs(.11*s,14,10),0,1.59*s,0);let o=()=>new Lr(.045*s,.55*s,4,8);return r(o(),-.42*s,1.3*s,0,Math.PI/2-.35),r(o(),.42*s,1.3*s,0,-(Math.PI/2-.35)),{group:e,dispose(){for(let l of n)l.dispose();t.dispose()}}}function cr(i,e,t){let n=document.createElement(i);return n.className=e,t!==void 0&&(n.textContent=t),n}function h0(i,e,t){let n=new Hs,r=[];for(let o of i)r.push(...e.toScene(...o).toArray());n.setPositions(r);let s=new kc(n,t);s.computeLineDistances();let a=n.getAttribute("instanceStart").data;return{line:s,write(o){o0(o,e.origin,a.array),a.needsUpdate=!0,n.computeBoundingBox(),n.computeBoundingSphere()},dispose(){n.dispose()}}}function u0(i,e){let t=i.meta.anchors,n=Td(t,i.meta.rigging);if(!n)return null;let r=i.token("--muted"),s=new Nn({color:r,linewidth:i.level==="phone"?3:4}),a=new Nn({color:r,linewidth:2,transparent:!0,opacity:.4});i.view.onResize(S=>{s.resolution.copy(S),a.resolution.copy(S)});let o=Dd(n,t,n.start.s),l=h0(zc(n.unloaded),i,a),c=h0(o?o.points:zc(n.unloaded),i,s);c.line.renderOrder=1;let h=c0(i.token("--ink"));i.add(l.line),i.add(c.line),i.add(h.group);let u=cr("span","v3-read"),d=cr("span","v3-read"),f=cr("span","v3-read"),p=cr("span","v3-read v3-trees v3-hidden",tt("ui.view3d.over_trees")),y=cr("span","v3-read v3-wait",tt("ui.view3d.loading_profile"));e.replaceChildren(u,d,f,p,y),u.textContent=tt("ui.view3d.length",{m:no(n.span)});let m=cr("label","v3-field"),g=cr("input","v3-slider");g.type="range",g.min="0",g.max=String(n.span),g.step=String(Math.max(.05,n.span/1e3)),g.value=String(n.start.s),g.setAttribute("aria-label",tt("ui.view3d.walker_position")),m.append(cr("span","v3-field-label",tt("ui.view3d.walker")),g),i.toolbar.append(m);let v={readout:null,s:n.start.s,span:n.span,setWalker(S){let _=Dd(n,t,S);_&&(v.s=S,c.write(_.points),h.group.position.copy(i.toScene(..._.at)),h.group.rotation.y=_.yaw,d.textContent=tt("ui.view3d.sag",{m:no(_.sag)}),String(S)!==g.value&&document.activeElement!==g&&(g.value=String(S)),i.invalidate())},setProfile(S){if(y.remove(),!S)return;let _=v.readout=l0(S),M=i.token(_.overTrees?"--trees":"--clear");s.color.set(M),a.color.set(M),u.textContent=tt("ui.view3d.length",{m:no(_.length)}),f.textContent=tt("ui.view3d.clearance",{m:no(_.clearance)}),p.classList.toggle("v3-hidden",!_.overTrees),e.dataset.filled="1",i.invalidate()}};return g.addEventListener("input",()=>v.setWalker(Number(g.value))),v.setWalker(n.start.s),i.onDispose(()=>{l.dispose(),c.dispose(),s.dispose(),a.dispose(),h.dispose()}),v}function Qw(i,e,t){let n=new URLSearchParams(i),r=new URLSearchParams(e.replace(/^#/,"")),s=n.get("level"),a=s==="phone"||s==="full"?s:t?"phone":"full",o=r.get("line")||"",l=o.split(","),c=l.length===4&&l.every(h=>h.trim()!==""&&isFinite(Number(h)));return{run:r.get("run")||"",line:c?o:null,level:a}}function d0(){let i=typeof matchMedia=="function"&&matchMedia("(pointer: coarse)").matches;return Qw(location.search,location.hash,i)}function f0(i){return`/api/patch?run=${encodeURIComponent(i.run)}&line=${encodeURIComponent(i.line||"")}&step=${i.level==="phone"?2:1}`}function p0(i){return`/#run=${encodeURIComponent(i.run)}`+(i.line?`&line=${encodeURIComponent(i.line)}`:"")}function eT(i){try{let e=typeof location<"u"?location.href:void 0;return new URL(i,e).origin}catch{return null}}function m0(i){if(!i)return null;let e=i.length,t=i.indexOf("?"),n=i.indexOf("#");t!==-1&&(e=Math.min(e,t)),n!==-1&&(e=Math.min(e,n));let r=i.lastIndexOf(".",e),s=i.lastIndexOf("/",e),a=i.indexOf("://");return a!==-1&&a+2===s||r===-1||r<s?null:i.substring(r+1,e)||null}var Gc,Hc=(Gc=class{static setXRSession(i){i!==this.session&&(this.flushPending(),this.session=i)}static requestAnimationFrame(i){let{session:e,pending:t}=this,n,r=()=>{t.delete(n),i()};return n=e?e.requestAnimationFrame(r):requestAnimationFrame(r),t.set(n,i),n}static cancelAnimationFrame(i){let{pending:e,session:t}=this;e.delete(i),t?t.cancelAnimationFrame(i):cancelAnimationFrame(i)}static flushPending(){this.pending.forEach((i,e)=>{i(),this.cancelAnimationFrame(e)})}},Ch(Gc,"pending",new Map),Ch(Gc,"session",null),Gc),g0=2**30,x0=class{get unloadPriorityCallback(){return this._unloadPriorityCallback}set unloadPriorityCallback(i){i.length===1?(console.warn('LRUCache: "unloadPriorityCallback" function has been changed to take two arguments.'),this._unloadPriorityCallback=(e,t)=>{let n=i(e),r=i(t);return n<r?-1:+(n>r)}):this._unloadPriorityCallback=i}constructor(){this.minSize=6e3,this.maxSize=8e3,this.minBytesSize=.3*g0,this.maxBytesSize=.4*g0,this.unloadPercent=.05,this.autoMarkUnused=!0,this.cachedBytes=0,this.itemSet=new Map,this.itemList=[],this.usedSet=new Set,this.callbacks=new Map,this.unloadingHandle=-1,this.bytesMap=new Map,this.loadedSet=new Set,this._unloadPriorityCallback=null;let i=this.itemSet;this.defaultPriorityCallback=e=>i.get(e)}isFull(){return this.itemSet.size>=this.maxSize||this.cachedBytes>=this.maxBytesSize}getMemoryUsage(i){return this.bytesMap.get(i)||0}setMemoryUsage(i,e){let{bytesMap:t,itemSet:n}=this;n.has(i)&&(e=Math.round(e),this.cachedBytes-=t.get(i)||0,t.set(i,e),this.cachedBytes+=e)}add(i,e){let t=this.itemSet;if(t.has(i)||this.isFull())return!1;let n=this.usedSet,r=this.itemList,s=this.callbacks;return r.push(i),n.add(i),t.set(i,Date.now()),s.set(i,e),!0}has(i){return this.itemSet.has(i)}remove(i){let e=this.usedSet,t=this.itemSet,n=this.itemList,r=this.bytesMap,s=this.callbacks,a=this.loadedSet;if(t.has(i)){this.cachedBytes-=r.get(i)||0,r.delete(i),s.get(i)(i);let o=n.indexOf(i);return n.splice(o,1),e.delete(i),t.delete(i),s.delete(i),a.delete(i),!0}return!1}setLoaded(i,e){let{itemSet:t,loadedSet:n}=this;t.has(i)&&(e===!0?n.add(i):n.delete(i))}markUsed(i){let e=this.itemSet,t=this.usedSet;e.has(i)&&!t.has(i)&&(e.set(i,Date.now()),t.add(i))}markUnused(i){this.usedSet.delete(i)}markAllUnused(){this.usedSet.clear()}isUsed(i){return this.usedSet.has(i)}unloadUnusedContent(){let{unloadPercent:i,minSize:e,maxSize:t,itemList:n,itemSet:r,usedSet:s,loadedSet:a,callbacks:o,bytesMap:l,minBytesSize:c,maxBytesSize:h}=this,u=n.length-s.size,d=n.length-a.size,f=Math.max(Math.min(n.length-e,u),0),p=this.cachedBytes-c,y=this.unloadPriorityCallback||this.defaultPriorityCallback,m=!1,g=f>0&&u>0||d&&n.length>t;if(u&&this.cachedBytes>c||d&&this.cachedBytes>h||g){n.sort((x,A)=>{let C=s.has(x);if(C===s.has(A)){let D=a.has(x);return D===a.has(A)?-y(x,A):D?1:-1}else return C?1:-1});let v=Math.max(e*i,f*i),S=Math.ceil(Math.min(v,u,f)),_=Math.max(i*p,i*c),M=Math.min(_,p),w=0,E=0;for(;w<n.length&&(this.cachedBytes-E>h||n.length-w>t);){let x=n[w],A=l.get(x)||0;if(s.has(x)&&a.has(x)||this.cachedBytes-E-A<h&&n.length-w<=t)break;E+=A,w++}for(;w<n.length&&(E<M||w<S);){let x=n[w],A=l.get(x)||0;if(s.has(x)||this.cachedBytes-E-A<c&&w>=S)break;E+=A,w++}n.splice(0,w).forEach(x=>{this.cachedBytes-=l.get(x)||0,o.get(x)(x),l.delete(x),r.delete(x),o.delete(x),a.delete(x),s.delete(x)}),m=w<f||E<p&&w<u,m&&(m=w>0)}m&&(this.unloadingHandle=Hc.requestAnimationFrame(()=>this.scheduleUnload()))}scheduleUnload(){Hc.cancelAnimationFrame(this.unloadingHandle),this.scheduled||(this.scheduled=!0,queueMicrotask(()=>{this.scheduled=!1,this.unloadUnusedContent()}))}},tT=class extends DOMException{constructor(){super("PriorityQueue: Item removed","AbortError")}},jr=class{get running(){return this.items.length!==0||this.currJobs!==0}constructor(){this.maxJobs=6,this.items=[],this.callbacks=new Map,this.currJobs=0,this.scheduled=!1,this.autoUpdate=!0,this.priorityCallback=null,this._schedulingCallback=i=>{Hc.requestAnimationFrame(i)},this._runjobs=()=>{this.scheduled=!1,this.tryRunJobs()}}sort(){let i=this.priorityCallback,e=this.items;i!==null&&e.sort(i)}has(i){return this.callbacks.has(i)}add(i,e){let t={callback:e,reject:null,resolve:null,promise:null};return t.promise=new Promise((n,r)=>{let s=this.items,a=this.callbacks;t.resolve=n,t.reject=r,s.unshift(i),a.set(i,t),this.autoUpdate&&this.scheduleJobRun()}),t.promise}remove(i){let e=this.items,t=this.callbacks,n=e.indexOf(i);if(n!==-1){let r=t.get(i);r.promise.catch(s=>{if(s.name!=="AbortError")throw s}),r.reject(new tT),e.splice(n,1),t.delete(i)}}removeByFilter(i){let{items:e}=this;for(let t=0;t<e.length;t++){let n=e[t];i(n)&&(this.remove(n),t--)}}tryRunJobs(){this.sort();let i=this.items,e=this.callbacks,t=this.maxJobs,n=0,r=()=>{this.currJobs--,this.autoUpdate&&this.scheduleJobRun()};for(;t>this.currJobs&&i.length>0&&n<t;){this.currJobs++,n++;let s=i.pop(),{callback:a,resolve:o,reject:l}=e.get(s);e.delete(s);let c;try{c=a(s)}catch(h){l(h),r();continue}c instanceof Promise?c.then(o).catch(l).finally(r):(o(c),r())}}flush(i){let{items:e,callbacks:t}=this,n=e.indexOf(i);if(!t.has(i))return;let{callback:r,resolve:s,reject:a}=t.get(i);t.delete(i),e.splice(n,1);let o;try{o=r(i)}catch(l){a(l);return}return o instanceof Promise?o.then(s).catch(a):s(o),o}scheduleJobRun(){this.scheduled||(this.scheduled=(this._schedulingCallback(this._runjobs),!0))}},iT=class{get running(){for(let i of this.originQueues.values())if(i.running)return!0;return!1}get maxJobsPerOrigin(){return this._maxJobsPerOrigin}set maxJobsPerOrigin(i){this._maxJobsPerOrigin=i,this.originQueues.forEach(e=>e.maxJobs=i)}get maxJobs(){return this.maxJobsPerOrigin}set maxJobs(i){console.warn('DownloadPriorityQueue: "maxJobs" is no longer valid and limits jobs per server origin. Use "maxJobsPerOrigin", instead.'),this.maxJobsPerOrigin=i}get priorityCallback(){return this._priorityCallback}set priorityCallback(i){this._priorityCallback=i,this.originQueues.forEach(e=>e.priorityCallback=i)}constructor(){this.originQueues=new Map,this._itemQueues=new WeakMap,this._maxJobsPerOrigin=6,this._priorityCallback=null}add(i,e,t,n=null){this.originQueues.forEach((l,c)=>{l.running||this.originQueues.delete(c)});let r=i===null?null:eT(i),s=this.originQueues.get(r);s||(s=new jr,s.maxJobs=this._maxJobsPerOrigin,s.priorityCallback=this._priorityCallback,this.originQueues.set(r,s));let a=this._itemQueues.get(e);if(a&&a!==s&&a.has(e))throw Error("DownloadPriorityQueue: Item is already queued with a different url origin.");this._itemQueues.set(e,s);let o=s.add(e,t);return n!==null&&(n.aborted?this.remove(e):n.addEventListener("abort",()=>this.remove(e),{once:!0})),o}remove(i){let e=this._itemQueues.get(i);e&&(e.remove(i),this._itemQueues.delete(i))}has(i){let e=this._itemQueues.get(i);return!!(e&&e.has(i))}};var Ws=6378137,dP=1/298.257223563,v0=6356752314245179e-9,Vc={inView:!1,error:1/0,distanceFromCamera:1/0};function Xc(i){return i===4||i===-1}function Un(i,e){return qc(i)&&i.traversal.lastFrameVisited===e&&i.traversal.used}function qc(i){return!!i.traversal}function ao(i){let{children:e}=i,t=e.length===0||qc(e[e.length-1]),n=!i.internal.hasUnrenderableContent||Xc(i.internal.loadingState);return t&&n}function Xr(i){return i.traversal.unconditionallyRefine}function ro(i,e,t=!0){if(qc(i)&&(e.ensureChildrenArePreprocessed(i),i.traversal.lastFrameVisited!==e.frameCount&&(i.traversal.wasInFrustum=i.traversal.inFrustum,i.traversal.wasSetActive=i.traversal.active,i.traversal.wasSetVisible=i.traversal.visible,i.traversal.usedLastFrame=i.traversal.used,i.traversal.lastFrameVisited=e.frameCount,i.traversal.used=!1,i.traversal.inFrustum=!1,i.traversal.isLeaf=!1,i.traversal.visible=!1,i.traversal.active=!1,i.traversal.error=1/0,i.traversal.distanceFromCamera=1/0,i.traversal.allChildrenReady=!1,i.traversal.allChildrenLoaded=!1,i.traversal.kicked=!1,i.traversal.allUsedChildrenProcessed=!1,t&&(e.calculateTileViewErrorWithPlugin(i,Vc),i.traversal.inFrustum=Vc.inView,i.traversal.error=Vc.error,i.traversal.distanceFromCamera=Vc.distanceFromCamera),i.traversal.unconditionallyRefine=i.internal.hasUnrenderableContent,!i.traversal.unconditionallyRefine))){let n=i.parent;for(;n&&n.traversal.unconditionallyRefine;)n=n.parent;n&&n.geometricError<=i.geometricError&&(i.traversal.unconditionallyRefine=!0)}}function Nd(i,e,t=!1){if(ro(i,e),t?e.markTileUsed(i):Wc(i),Xr(i)&&ao(i)){let n=i.children;for(let r=0,s=n.length;r<s;r++)Nd(n[r],e,t)}}function b0(i,e){if(ro(i,e),i.traversal.usedLastFrame&&(Wc(i),i.traversal.wasSetActive&&(i.traversal.active=!0),(!i.traversal.active||Xr(i))&&ao(i))){let t=i.children;for(let n=0,r=t.length;n<r;n++)b0(t[n],e)}}function Wc(i){i.traversal.used=!0}function nT(i,e){return!(i.traversal.error<=e.errorTarget&&!Xr(i)||e.maxDepth>0&&i.internal.depth+1>=e.maxDepth||!ao(i))}function S0(i,e){let{frameCount:t}=e,{children:n}=i;for(let r=0,s=n.length;r<s;r++){let a=n[r];Un(a,t)&&(a.traversal.active&&(a.traversal.kicked=!0,a.traversal.active=!1),S0(a,e))}}function y0(i){return!Xr(i)&&(!i.internal.hasContent||Xc(i.internal.loadingState))}function M0(i,e){if(ro(i,e),!i.traversal.inFrustum)return;let t=i.parent;if(t&&t.refine==="ADD"&&i.geometricError>0&&i.traversal.error*(t.geometricError/i.geometricError)<=e.errorTarget)return;if(!nT(i,e)){Wc(i);return}let n=!1,r=!1,s=i.children;for(let a=0,o=s.length;a<o;a++){let l=s[a];M0(l,e),n||(n=Un(l,e.frameCount)),r||(r=l.traversal.inFrustum)}if(i.refine==="REPLACE"&&!r&&s.length!==0){i.traversal.inFrustum=!1,e.markTileUsed(i);for(let a=0,o=s.length;a<o;a++)Nd(s[a],e,!0);return}if(Wc(i),i.refine==="REPLACE"&&n&&(e.loadSiblings||e.loadAncestors))for(let a=0,o=s.length;a<o;a++)Nd(s[a],e)}function w0(i,e){let t=e.frameCount;if(!Un(i,t))return;let n=i.children,r=!1;for(let a=0,o=n.length;a<o;a++){let l=n[a];r||(r=Un(l,t))}if(!r)i.traversal.isLeaf=!0;else{for(let o=0,l=n.length;o<l;o++)w0(n[o],e);let a=!0;for(let o=0,l=n.length;o<l;o++){let c=n[o];if(Un(c,t)){let h=!Xr(c),u=!c.internal.hasContent||Xc(c.internal.loadingState);h&&u||c.traversal.allChildrenLoaded||(a=!1)}}i.traversal.allChildrenLoaded=a}let s=!0;for(let a=0,o=n.length;a<o;a++){let l=n[a];Un(l,e.frameCount)&&!l.traversal.allUsedChildrenProcessed&&(s=!1)}i.traversal.allUsedChildrenProcessed=s&&ao(i)}function T0(i,e){if(!Un(i,e.frameCount))return;let t=i.children;if(i.refine==="REPLACE"&&e.loadAncestors&&!i.traversal.allChildrenLoaded&&!Xr(i)&&(i.traversal.isLeaf=!0),i.traversal.isLeaf){if(!Xr(i)&&(i.traversal.active=!0,ao(i)&&i.internal.hasContent&&!Xc(i.internal.loadingState)))for(let r=0,s=t.length;r<s;r++)b0(t[r],e);return}let n=t.length>0;for(let r=0,s=t.length;r<s;r++){let a=t[r];T0(a,e),Un(a,e.frameCount)&&!(a.traversal.active&&y0(a))&&!a.traversal.allChildrenReady&&(n=!1)}i.traversal.allChildrenReady=n,i.refine==="REPLACE"&&!n&&i.traversal.wasSetActive&&y0(i)&&(i.traversal.active=!0,S0(i,e))}function E0(i,e){ro(i,e,!1);let t=Un(i,e.frameCount);if(t&&(i.internal.hasUnrenderableContent&&(e.markTileUsed(i),e.queueTileForDownload(i)),i.internal.hasRenderableContent&&i.refine==="ADD"&&(i.traversal.active=!0),(i.traversal.active||i.traversal.kicked)&&i.internal.hasContent&&(e.markTileUsed(i),i.traversal.allUsedChildrenProcessed&&e.queueTileForDownload(i),i.internal.loadingState!==4&&(i.traversal.active=!1)),e.loadAncestors&&i.internal.hasContent&&(e.markTileUsed(i),e.queueTileForDownload(i)),i.internal.virtualChildCount>0&&i.internal.hasContent&&e.markTileUsed(i),i.traversal.visible=i.internal.hasRenderableContent&&i.traversal.active&&i.traversal.inFrustum&&i.internal.loadingState===4,e.stats.used++,i.traversal.inFrustum&&e.stats.inFrustum++),t||qc(i)&&i.traversal.usedLastFrame){let n=!1,r=!1;t?(n=i.traversal.active,r=e.displayActiveTiles&&i.traversal.active||i.traversal.visible):ro(i,e,!1),i.internal.hasRenderableContent&&i.internal.loadingState===4?(n&&e.stats.active++,r&&e.stats.visible++,i.traversal.wasSetActive!==n&&e.invokeOnePlugin(a=>a.setTileActive&&a.setTileActive(i,n)),i.traversal.wasSetVisible!==r&&e.invokeOnePlugin(a=>a.setTileVisible&&a.setTileVisible(i,r))):i.internal.hasRenderableContent||(r=i.traversal.isLeaf,i.traversal.wasSetVisible!==r&&e.invokeOnePlugin(a=>a.setEmptyTileVisible&&a.setEmptyTileVisible(i,r))),i.traversal.visible=r,i.traversal.active=n;let s=i.children;for(let a=0,o=s.length;a<o;a++){let l=s[a];E0(l,e)}}}function rT(i,e){M0(i,e),w0(i,e),T0(i,e),E0(i,e)}function sT(i){let e=null;return()=>{e===null&&(e=Hc.requestAnimationFrame(()=>{e=null,i()}))}}function aT(i,e=null,t=null){let n=[];for(n.push(i),n.push(null),n.push(0);n.length>0;){let r=n.pop(),s=n.pop(),a=n.pop();if(e&&e(a,s,r)){t&&t(a,s,r);return}let o=a.children;if(o)for(let l=o.length-1;l>=0;l--)n.push(o[l]),n.push(a),n.push(r+1);t&&t(a,s,r)}}var _0=Symbol("PLUGIN_REGISTERED"),hr={inView:!0,error:0,distance:1/0},oT=(i,e)=>{let t=i.priority||0,n=e.priority||0;return t===n?!i.traversal||!e.traversal?0:i.traversal.used===e.traversal.used?i.traversal.error===e.traversal.error?i.traversal.distanceFromCamera===e.traversal.distanceFromCamera?i.internal.depthFromRenderedParent===e.internal.depthFromRenderedParent?0:i.internal.depthFromRenderedParent>e.internal.depthFromRenderedParent?-1:1:i.traversal.distanceFromCamera>e.traversal.distanceFromCamera?-1:1:i.traversal.error>e.traversal.error?1:-1:i.traversal.used?1:-1:t>n?1:-1},lT=(i,e)=>i.traversal.used===e.traversal.used?i.traversal.inFrustum===e.traversal.inFrustum?i.internal.hasUnrenderableContent===e.internal.hasUnrenderableContent?i.traversal.distanceFromCamera===e.traversal.distanceFromCamera?i.internal.depthFromRenderedParent===e.internal.depthFromRenderedParent?0:i.internal.depthFromRenderedParent>e.internal.depthFromRenderedParent?-1:1:i.traversal.distanceFromCamera>e.traversal.distanceFromCamera?-1:1:i.internal.hasUnrenderableContent?1:-1:i.traversal.inFrustum?1:-1:i.traversal.used?1:-1,cT=(i,e)=>i.traversal.lastFrameVisited===e.traversal.lastFrameVisited?i.internal.depthFromRenderedParent===e.internal.depthFromRenderedParent?i.internal.loadingState===e.internal.loadingState?i.internal.hasUnrenderableContent===e.internal.hasUnrenderableContent?i.traversal.error===e.traversal.error?0:i.traversal.error>e.traversal.error?-1:1:i.internal.hasUnrenderableContent?-1:1:i.internal.loadingState>e.internal.loadingState?-1:1:i.internal.depthFromRenderedParent>e.internal.depthFromRenderedParent?1:-1:i.traversal.lastFrameVisited>e.traversal.lastFrameVisited?-1:1,oo=(i,e)=>{let t=i.priority??1/0,n=e.priority??1/0;if(t!==n)return t>n?1:-1;if(!i.internal||!e.internal)return 0;let r=i.internal.renderer,s=e.internal.renderer,a=!r.loadAncestors,o=!s.loadAncestors;return a&&o?lT(i,e):oT(i,e)},A0=new x0;A0.unloadPriorityCallback=cT;var so=new iT;so.maxJobsPerOrigin=25,so.priorityCallback=oo;var Ud=new jr;Ud.maxJobs=5,Ud.priorityCallback=oo;var Od=new jr;Od.maxJobs=25,Od.priorityCallback=(i,e)=>{let t=i.parent,n=e.parent;return t===n?0:t?n?oo(t,n):-1:1};var C0=class{get root(){let i=this.rootTileset;return i?i.root:null}get loadProgress(){let{stats:i,isLoading:e}=this,t=i.queued+i.downloading+i.parsing,n=i.inCacheSinceLoad+ +!!e;return n===0?1:1-t/n}get downloadQueue(){return this._downloadQueue}set downloadQueue(i){if(i instanceof jr){console.warn('TilesRenderer: "downloadQueue" is no longer valid as a PriorityQueue. Use a DownloadPriorityQueue, instead.');return}this._downloadQueue=i}constructor(i=null){this.rootLoadingState=0,this.rootTileset=null,this.rootURL=i,this.fetchOptions={},this.plugins=[],this.queuedTiles=[],this.queuedTileSet=new Set,this.cachedSinceLoadComplete=new Set,this.isLoading=!1,this.processedTiles=new WeakSet,this.visibleTiles=new Set,this.activeTiles=new Set,this.usedSet=new Set,this.loadingTiles=new Set,this.lruCache=A0,this.downloadQueue=so,this.parseQueue=Ud,this.processNodeQueue=Od,this.stats={inCacheSinceLoad:0,inCache:0,queued:0,downloading:0,parsing:0,loaded:0,failed:0,inFrustum:0,used:0,active:0,visible:0,refused:0,tilesProcessed:0},this.frameCount=0,this._dispatchNeedsUpdateEvent=sT(()=>{this.dispatchEvent({type:"needs-update"})}),this.errorTarget=16,this.errorFalloff=0,this.errorFalloffDensity=2e-4,this.displayActiveTiles=!1,this.maxDepth=1/0,this.loadSiblings=!0,this.loadAncestors=!0,this.maxTilesProcessed=250}registerPlugin(i){if(i[_0]===!0)throw Error("TilesRendererBase: A plugin can only be registered to a single tileset");let e=this.plugins,t=i.priority||0,n=e.length;for(let r=0;r<e.length;r++)if((e[r].priority||0)>t){n=r;break}e.splice(n,0,i),i[_0]=!0,i.init&&i.init(this)}unregisterPlugin(i){let e=this.plugins;if(typeof i=="string"&&(i=this.getPluginByName(i)),e.includes(i)){let t=e.indexOf(i);return e.splice(t,1),i.dispose&&i.dispose(),!0}return!1}getPluginByName(i){return this.plugins.find(e=>e.name===i)||null}invokeOnePlugin(i){let e=[...this.plugins,this];for(let t=0;t<e.length;t++){let n=i(e[t]);if(n)return n}return null}invokeAllPlugins(i){let e=[...this.plugins,this],t=[];for(let n=0;n<e.length;n++){let r=i(e[n]);r&&t.push(r)}return t.length===0?null:Promise.all(t)}traverse(i,e,t=!0){this.root&&aT(this.root,(n,...r)=>(t&&this.ensureChildrenArePreprocessed(n,!0),i?i(n,...r):!1),e)}getAttributions(i=[]){return this.invokeAllPlugins(e=>e!==this&&e.getAttributions&&e.getAttributions(i)),i}update(){let{lruCache:i,usedSet:e,stats:t,root:n,downloadQueue:r,parseQueue:s,processNodeQueue:a,queuedTiles:o,queuedTileSet:l}=this;if(this.rootLoadingState===0&&(this.rootLoadingState=2,this.invokeOnePlugin(d=>d.loadRootTileset&&d.loadRootTileset()).then(d=>{let f=this.rootURL;f!==null&&this.invokeAllPlugins(p=>f=p.preprocessURL?p.preprocessURL(f,null):f),this.rootLoadingState=4,this.rootTileset=d,this.dispatchEvent({type:"needs-update"}),this.dispatchEvent({type:"load-tileset",tileset:d,url:f}),this.dispatchEvent({type:"load-root-tileset",tileset:d,url:f})}).catch(d=>{this.rootLoadingState=-1,console.error(d),this.rootTileset=null,this.dispatchEvent({type:"load-error",tile:null,error:d,url:this.rootURL})})),!n)return;let c=null;if(this.invokeAllPlugins(d=>{if(d.doTilesNeedUpdate){let f=d.doTilesNeedUpdate();c=c===null?f:!!(c||f)}}),c===!1){this.dispatchEvent({type:"update-before"}),this.dispatchEvent({type:"update-after"});return}this.dispatchEvent({type:"update-before"}),t.inFrustum=0,t.used=0,t.active=0,t.visible=0,t.refused=0,t.tilesProcessed=0,this.frameCount++,e.forEach(d=>i.markUnused(d)),e.clear(),this.prepareForTraversal(),rT(n,this),this.removeUnusedPendingTiles(),o.sort(i.unloadPriorityCallback);let h=0,u=o.length;for(;h<u&&!i.isFull();h++)this.requestTileContents(o[h]);t.refused+=o.length-h,o.length=0,l.clear(),i.scheduleUnload(),(r.running||s.running||a.running)===!1&&this.isLoading===!0&&(this.cachedSinceLoadComplete.clear(),t.inCacheSinceLoad=0,this.dispatchEvent({type:"tiles-load-end"}),this.isLoading=!1),this.dispatchEvent({type:"update-after"})}resetFailedTiles(){this.rootLoadingState===-1&&(this.rootLoadingState=0);let i=this.stats;i.failed!==0&&(this.traverse(e=>{e.internal.loadingState===-1&&(e.internal.loadingState=0)},null,!1),i.failed=0)}calculateTileViewErrorWithPlugin(i,e){this.calculateTileViewError(i,e);let{errorFalloff:t,errorFalloffDensity:n}=this;if(t>0&&Number.isFinite(e.distanceFromCamera)){let o=e.distanceFromCamera*n;e.error-=t*(1-Math.exp(-o*o))}let r=null,s=0,a=1/0;this.invokeAllPlugins(o=>{o!==this&&o.calculateTileViewError&&(hr.inView=!0,hr.error=0,hr.distance=1/0,o.calculateTileViewError(i,hr)&&(r===null&&(r=!0),r&&(r=hr.inView),hr.inView&&(a=Math.min(a,hr.distance),s=Math.max(s,hr.error))))}),e.inView&&r!==!1?(e.error=Math.max(e.error,s),e.distanceFromCamera=Math.min(e.distanceFromCamera,a)):r?(e.inView=!0,e.error=s,e.distanceFromCamera=a):e.inView=!1}dispose(){[...this.plugins].forEach(t=>{this.unregisterPlugin(t)});let i=this.lruCache,e=[];this.traverse(t=>(e.push(t),!1),null,!1);for(let t=0,n=e.length;t<n;t++)i.remove(e[t]);this.stats={queued:0,parsing:0,downloading:0,failed:0,inFrustum:0,traversed:0,used:0,active:0,visible:0},this.frameCount=0,this.loadingTiles.clear()}calculateBytesUsed(i,e){return 0}dispatchEvent(i){}addEventListener(i,e){}removeEventListener(i,e){}parseTile(i,e,t){return null}prepareForTraversal(){}disposeTile(i){i.traversal.visible&&(i.internal.hasRenderableContent?this.invokeOnePlugin(t=>t.setTileVisible&&t.setTileVisible(i,!1)):this.invokeOnePlugin(t=>t.setEmptyTileVisible&&t.setEmptyTileVisible(i,!1)),i.traversal.visible=!1),i.traversal.active&&i.internal.hasRenderableContent&&this.invokeOnePlugin(t=>t.setTileActive&&t.setTileActive(i,!1)),i.traversal.active=!1;let{scene:e}=i.engineData;e&&this.dispatchEvent({type:"dispose-model",scene:e,tile:i})}preprocessNode(i,e,t=null){if(this.processedTiles.add(i),this.stats.tilesProcessed++,i.content&&(!("uri"in i.content)&&"url"in i.content&&(i.content.uri=i.content.url,delete i.content.url),i.content.boundingVolume&&!("box"in i.content.boundingVolume||"sphere"in i.content.boundingVolume||"region"in i.content.boundingVolume)&&delete i.content.boundingVolume),i.parent=t,i.children=i.children||[],i.internal={hasContent:!1,hasRenderableContent:!1,hasUnrenderableContent:!1,loadingState:0,basePath:e,depth:-1,depthFromRenderedParent:-1,isVirtual:!1,virtualChildCount:0,renderer:this,...i.internal},i.content?.uri){let n=m0(i.content.uri),r=!!(n&&/json$/.test(n));i.internal.hasContent=!0,i.internal.hasUnrenderableContent=r,i.internal.hasRenderableContent=!r}else i.internal.hasContent=!1,i.internal.hasUnrenderableContent=!1,i.internal.hasRenderableContent=!1;t?(i.internal.depth=t.internal.depth+1,i.internal.depthFromRenderedParent=t.internal.depthFromRenderedParent+ +!!i.internal.hasRenderableContent):(i.internal.depth=0,i.internal.depthFromRenderedParent=+!!i.internal.hasRenderableContent),i.traversal={distanceFromCamera:1/0,error:1/0,inFrustum:!1,wasInFrustum:!1,isLeaf:!1,used:!1,usedLastFrame:!1,visible:!1,wasSetVisible:!1,active:!1,wasSetActive:!1,allChildrenReady:!1,allChildrenLoaded:!1,kicked:!1,allUsedChildrenProcessed:!1,lastFrameVisited:-1},t===null?i.refine=i.refine||"REPLACE":i.refine=i.refine||t.refine,i.engineData={scene:null,metadata:null,boundingVolume:null},Object.defineProperty(i,"cached",{get(){return console.warn('TilesRenderer: "tile.cached" field has been renamed to "tile.engineData".'),this.engineData},enumerable:!1,configurable:!0}),this.invokeAllPlugins(n=>{n!==this&&n.preprocessNode&&n.preprocessNode(i,e,t)})}setTileActive(i,e){e?this.activeTiles.add(i):this.activeTiles.delete(i)}setTileVisible(i,e){e?this.visibleTiles.add(i):this.visibleTiles.delete(i),this.dispatchEvent({type:"tile-visibility-change",scene:i.engineData.scene,tile:i,visible:e})}calculateTileViewError(i,e){}removeUnusedPendingTiles(){let{lruCache:i,loadingTiles:e}=this,t=[];for(let n of e)!i.isUsed(n)&&n.internal.loadingState===1&&t.push(n);for(let n=0;n<t.length;n++)i.remove(t[n])}queueTileForDownload(i){let{queuedTileSet:e}=this;if(!(i.internal.loadingState!==0||e.has(i))){if(e.add(i),this.lruCache.isFull()){this.stats.refused++;return}this.queuedTiles.push(i)}}markTileUsed(i){this.usedSet.add(i),this.lruCache.markUsed(i)}fetchData(i,e){return fetch(i,e)}ensureChildrenArePreprocessed(i,e=this.stats.tilesProcessed<this.maxTilesProcessed){let t=i.children;if(t.length===0||t[t.length-1].traversal)return;let n=r=>{for(let s=0,a=r.length;s<a;s++){let o=r[s];o&&!o.traversal&&this.preprocessNode(o,i.internal.basePath,i)}};e?(this.processNodeQueue.remove(i),n(t)):this.processNodeQueue.has(i)||this.processNodeQueue.add(i,r=>{n(r.children),this._dispatchNeedsUpdateEvent()})}getBytesUsed(i){let e=0;return this.invokeAllPlugins(t=>{t.calculateBytesUsed&&(e+=t.calculateBytesUsed(i,i.engineData.scene)||0)}),e}recalculateBytesUsed(i=null){let{lruCache:e,processedTiles:t}=this;i===null?e.itemSet.forEach(n=>{t.has(n)&&e.setMemoryUsage(n,this.getBytesUsed(n))}):e.setMemoryUsage(i,this.getBytesUsed(i))}preprocessTileset(i,e,t=null){let[n,r]=i.asset.version.split(".").map(a=>parseInt(a));console.assert(n<=1,"TilesRenderer: asset.version is expected to be a 1.x or a compatible version."),n===1&&r>0&&console.warn("TilesRenderer: tiles versions at 1.1 or higher have limited support. Some new extensions and features may not be supported.");let s=e.replace(/\/[^/]*$/,"");s=new URL(s,window.location.href).toString(),this.preprocessNode(i.root,s,t)}loadRootTileset(){let i=this.rootURL;return this.invokeAllPlugins(e=>i=e.preprocessURL?e.preprocessURL(i,null):i),this.invokeOnePlugin(e=>e.fetchData&&e.fetchData(i,this.fetchOptions)).then(e=>{if(!(e instanceof Response))return e;if(e.ok)return e.json();throw Error(`TilesRenderer: Failed to load tileset "${i}" with status ${e.status} : ${e.statusText}`)}).then(e=>(this.preprocessTileset(e,i),e))}requestTileContents(i){if(i.internal.loadingState!==0)return;let e=!1,t=null,n=new URL(i.content.uri,i.internal.basePath+"/").toString();this.invokeAllPlugins(d=>n=d.preprocessURL?d.preprocessURL(n,i):n);let r=this.stats,s=this.lruCache,a=this.downloadQueue,o=this.parseQueue,l=this.loadingTiles,c=m0(n),h=new AbortController,u=h.signal;if(s.add(i,d=>{h.abort(),e?d.children.length=0:this.invokeAllPlugins(f=>{f.disposeTile&&f.disposeTile(d)}),r.inCache--,this.cachedSinceLoadComplete.has(i)&&(this.cachedSinceLoadComplete.delete(i),r.inCacheSinceLoad--),d.internal.loadingState===1?r.queued--:d.internal.loadingState===2?r.downloading--:d.internal.loadingState===3?r.parsing--:d.internal.loadingState===4&&r.loaded--,d.internal.loadingState=0,o.remove(d),a.remove(d),l.delete(d)}))return this.isLoading||(this.isLoading=!0,this.dispatchEvent({type:"tiles-load-start"})),s.setMemoryUsage(i,this.getBytesUsed(i)),this.cachedSinceLoadComplete.add(i),r.inCacheSinceLoad++,r.inCache++,r.queued++,i.internal.loadingState=1,l.add(i),a.add(n,i,d=>{if(u.aborted)return Promise.resolve();i.internal.loadingState=2,r.downloading++,r.queued--;let f=this.invokeOnePlugin(p=>p.fetchData&&p.fetchData(n,{...this.fetchOptions,signal:u}));return this.dispatchEvent({type:"tile-download-start",tile:i,url:n,get uri(){return console.warn('tile-download-start event: "uri" has been renamed to "url".'),this.url}}),f}).then(d=>{if(!u.aborted){if(!(d instanceof Response))return d;if(d.ok)return c==="json"?d.json():d.arrayBuffer();throw Error(`Failed to load model with error code ${d.status}`)}}).then(d=>{if(!u.aborted)return r.downloading--,r.parsing++,i.internal.loadingState=3,o.add(i,f=>u.aborted?Promise.resolve():c==="json"&&d.root?(this.preprocessTileset(d,n,i),i.children.push(d.root),t=d,e=!0,Promise.resolve()):this.invokeOnePlugin(p=>p.parseTile&&p.parseTile(d,f,c,n,u)))}).then(()=>{if(u.aborted)return;r.parsing--,r.loaded++,i.internal.loadingState=4,l.delete(i),s.setLoaded(i,!0);let d=this.getBytesUsed(i);if(s.getMemoryUsage(i)===0&&d>0&&s.isFull()){s.remove(i);return}s.setMemoryUsage(i,d),this.dispatchEvent({type:"needs-update"}),e&&this.dispatchEvent({type:"load-tileset",tileset:t,url:n}),i.engineData.scene&&this.dispatchEvent({type:"load-model",scene:i.engineData.scene,tile:i,url:n})}).catch(d=>{u.aborted||(d.name==="AbortError"?s.remove(i):(o.remove(i),a.remove(i),i.internal.loadingState===1?r.queued--:i.internal.loadingState===2?r.downloading--:i.internal.loadingState===3?r.parsing--:i.internal.loadingState===4&&r.loaded--,r.failed++,console.error(`TilesRenderer : Failed to load tile at url "${i.content.uri}".`),console.error(d),i.internal.loadingState=-1,l.delete(i),s.setLoaded(i,!0),this.dispatchEvent({type:"load-error",tile:i,error:d,url:n})))})}};function qr(i){if(i===null||i.byteLength<4)return"";let e;if(e=i instanceof DataView?i:new DataView(i),String.fromCharCode(e.getUint8(0))==="{")return null;let t="";for(let n=0;n<4;n++)t+=String.fromCharCode(e.getUint8(n));return t}var hT=new TextDecoder;function R0(i){return hT.decode(i)}function jc(i){return i.replace(/[\\/][^\\/]+$/,"")+"/"}var lo=class{constructor(){this.fetchOptions={},this.workingPath=""}loadAsync(i){return fetch(i,this.fetchOptions).then(e=>{if(!e.ok)throw Error(`Failed to load file "${i}" with status ${e.status} : ${e.statusText}`);return e.arrayBuffer()}).then(e=>(this.workingPath===""&&(this.workingPath=jc(i)),this.parse(e)))}resolveExternalURL(i){return new URL(i,this.workingPath).href}parse(i){throw Error("LoaderBase: Parse not implemented.")}};function P0(i,e,t,n,r,s){let a;switch(n){case"SCALAR":a=1;break;case"VEC2":a=2;break;case"VEC3":a=3;break;case"VEC4":a=4;break;default:throw Error(`FeatureTable : Feature type not provided for "${s}".`)}let o,l=t*a;switch(r){case"BYTE":o=new Int8Array(i,e,l);break;case"UNSIGNED_BYTE":o=new Uint8Array(i,e,l);break;case"SHORT":o=new Int16Array(i,e,l);break;case"UNSIGNED_SHORT":o=new Uint16Array(i,e,l);break;case"INT":o=new Int32Array(i,e,l);break;case"UNSIGNED_INT":o=new Uint32Array(i,e,l);break;case"FLOAT":o=new Float32Array(i,e,l);break;case"DOUBLE":o=new Float64Array(i,e,l);break;default:throw Error(`FeatureTable : Feature component type not provided for "${s}".`)}return o}var Yc=class{constructor(i,e,t,n){this.buffer=i,this.binOffset=e+t,this.binLength=n;let r=null;if(t!==0){let s=new Uint8Array(i,e,t);r=JSON.parse(R0(s))}else r={};this.header=r}getKeys(){return Object.keys(this.header).filter(i=>i!=="extensions")}getData(i,e,t=null,n=null){let r=this.header;if(!(i in r))return null;let s=r[i];if(!(s instanceof Object)||Array.isArray(s))return s;{let{buffer:a,binOffset:o,binLength:l}=this,c=s.byteOffset||0,h=s.type||n,u=s.componentType||t;if("type"in s&&n&&s.type!==n)throw Error("FeatureTable: Specified type does not match expected type.");let d=o+c,f=P0(a,d,e,h,u,i);if(d+f.byteLength>o+l)throw Error("FeatureTable: Feature data read outside binary body length.");return f}}getBuffer(i,e){let{buffer:t,binOffset:n}=this;return t.slice(n+i,n+i+e)}},uT=class{constructor(i){this.batchTable=i;let e=i.header.extensions["3DTILES_batch_table_hierarchy"];this.classes=e.classes;for(let n of this.classes){let r=n.instances;for(let s in r)n.instances[s]=this._parseProperty(r[s],n.length,s)}if(this.instancesLength=e.instancesLength,this.classIds=this._parseProperty(e.classIds,this.instancesLength,"classIds"),e.parentCounts?this.parentCounts=this._parseProperty(e.parentCounts,this.instancesLength,"parentCounts"):this.parentCounts=Array(this.instancesLength).fill(1),e.parentIds){let n=this.parentCounts.reduce((r,s)=>r+s,0);this.parentIds=this._parseProperty(e.parentIds,n,"parentIds")}else this.parentIds=null;this.instancesIds=[];let t={};for(let n of this.classIds)t[n]=t[n]??0,this.instancesIds.push(t[n]),t[n]++}_parseProperty(i,e,t){if(Array.isArray(i))return i;{let{buffer:n,binOffset:r}=this.batchTable,s=i.byteOffset,a=i.componentType||"UNSIGNED_SHORT";return P0(n,r+s,e,"SCALAR",a,t)}}getDataFromId(i,e={}){let t=this.parentCounts[i];if(this.parentIds&&t>0){let o=0;for(let l=0;l<i;l++)o+=this.parentCounts[l];for(let l=0;l<t;l++){let c=this.parentIds[o+l];c!==i&&this.getDataFromId(c,e)}}let n=this.classIds[i],r=this.classes[n].instances,s=this.classes[n].name,a=this.instancesIds[i];for(let o in r)e[s]=e[s]||{},e[s][o]=r[o][a];return e}},Fd=class extends Yc{constructor(i,e,t,n,r){super(i,t,n,r),this.count=e,this.extensions={};let s=this.header.extensions;s&&s["3DTILES_batch_table_hierarchy"]&&(this.extensions["3DTILES_batch_table_hierarchy"]=new uT(this))}getDataFromId(i,e={}){if(i<0||i>=this.count)throw Error(`BatchTable: id value "${i}" out of bounds for "${this.count}" features number.`);for(let t of this.getKeys())e[t]=super.getData(t,this.count)[i];for(let t in this.extensions){let n=this.extensions[t];n.getDataFromId instanceof Function&&(e[t]=e[t]||{},n.getDataFromId(i,e[t]))}return e}getPropertyArray(i){return super.getData(i,this.count)}},I0=class extends lo{parse(i){let e=new DataView(i),t=qr(e);console.assert(t==="b3dm");let n=e.getUint32(4,!0);console.assert(n===1);let r=e.getUint32(8,!0);console.assert(r===i.byteLength);let s=e.getUint32(12,!0),a=e.getUint32(16,!0),o=e.getUint32(20,!0),l=e.getUint32(24,!0),c=new Yc(i.slice(28,28+s+a),0,s,a),h=28+s+a,u=new Fd(i.slice(h,h+o+l),c.getData("BATCH_LENGTH"),0,o,l),d=h+o+l;return{version:n,featureTable:c,batchTable:u,glbBytes:new Uint8Array(i,d,r-d)}}},L0=class extends lo{parse(i){let e=new DataView(i),t=qr(e);console.assert(t==="i3dm");let n=e.getUint32(4,!0);console.assert(n===1);let r=e.getUint32(8,!0);console.assert(r===i.byteLength);let s=e.getUint32(12,!0),a=e.getUint32(16,!0),o=e.getUint32(20,!0),l=e.getUint32(24,!0),c=e.getUint32(28,!0),h=new Yc(i.slice(32,32+s+a),0,s,a),u=32+s+a,d=new Fd(i.slice(u,u+o+l),h.getData("INSTANCES_LENGTH"),0,o,l),f=u+o+l,p=new Uint8Array(i,f,r-f),y=null,m=null,g=null;if(c)y=p,m=Promise.resolve();else{let v=this.resolveExternalURL(R0(p));g=jc(v),m=fetch(v,this.fetchOptions).then(S=>{if(!S.ok)throw Error(`I3DMLoaderBase : Failed to load file "${v}" with status ${S.status} : ${S.statusText}`);return S.arrayBuffer()}).then(S=>{y=new Uint8Array(S)})}return m.then(()=>({version:n,featureTable:h,batchTable:d,glbBytes:y,gltfWorkingPath:g}))}},D0=class extends lo{parse(i){let e=new DataView(i),t=qr(e);console.assert(t==="pnts");let n=e.getUint32(4,!0);console.assert(n===1);let r=e.getUint32(8,!0);console.assert(r===i.byteLength);let s=e.getUint32(12,!0),a=e.getUint32(16,!0),o=e.getUint32(20,!0),l=e.getUint32(24,!0),c=new Yc(i.slice(28,28+s+a),0,s,a),h=28+s+a,u=new Fd(i.slice(h,h+o+l),c.getData("BATCH_LENGTH")||c.getData("POINTS_LENGTH"),0,o,l);return Promise.resolve({version:n,featureTable:c,batchTable:u})}},N0=class extends lo{parse(i){let e=new DataView(i),t=qr(e);console.assert(t==="cmpt",'CMPTLoader: The magic bytes equal "cmpt".');let n=e.getUint32(4,!0);console.assert(n===1,'CMPTLoader: The version listed in the header is "1".');let r=e.getUint32(8,!0);console.assert(r===i.byteLength,"CMPTLoader: The contents buffer length listed in the header matches the file.");let s=e.getUint32(12,!0),a=[],o=16;for(let l=0;l<s;l++){let c=new DataView(i,o,12),h=qr(c),u=c.getUint32(4,!0),d=c.getUint32(8,!0),f=new Uint8Array(i,o,d);a.push({type:h,buffer:f,version:u}),o+=d}return{version:n,tiles:a}}};function U0(i){let e=0;for(let n in i.attributes){let r=i.getAttribute(n);e+=r.count*r.itemSize*r.array.BYTES_PER_ELEMENT}let t=i.getIndex();return e+=t?t.count*t.itemSize*t.array.BYTES_PER_ELEMENT:0,e}function Bd(i,e){if(e===ju)return console.warn("THREE.BufferGeometryUtils.toTrianglesDrawMode(): Geometry already defined as triangles."),i;if(e===Fs||e===Ya){let t=i.getIndex();if(t===null){let s=[],a=i.getAttribute("position");if(a!==void 0){for(let o=0;o<a.count;o++)s.push(o);i.setIndex(s),t=i.getIndex()}else return console.error("THREE.BufferGeometryUtils.toTrianglesDrawMode(): Undefined position attribute. Processing not possible."),i}let n=t.count-2,r=[];if(e===Fs)for(let s=1;s<=n;s++)r.push(t.getX(0)),r.push(t.getX(s)),r.push(t.getX(s+1));else for(let s=0;s<n;s++)s%2===0?(r.push(t.getX(s)),r.push(t.getX(s+1)),r.push(t.getX(s+2))):(r.push(t.getX(s+2)),r.push(t.getX(s+1)),r.push(t.getX(s)));return r.length/3!==n&&console.error("THREE.BufferGeometryUtils.toTrianglesDrawMode(): Unable to generate correct amount of triangles."),i.setIndex(r),i.clearGroups(),i}else return console.error("THREE.BufferGeometryUtils.toTrianglesDrawMode(): Unknown draw mode:",e),i}function O0(i){let e=new Map,t=new Map,n=i.clone();return F0(i,n,function(r,s){e.set(s,r),t.set(r,s)}),n.traverse(function(r){if(!r.isSkinnedMesh)return;let s=r,a=e.get(r),o=a.skeleton.bones;s.skeleton=a.skeleton.clone(),s.bindMatrix.copy(a.bindMatrix),s.skeleton.bones=o.map(function(l){return t.get(l)}),s.bind(s.skeleton,s.bindMatrix)}),n}function F0(i,e,t){t(i,e);for(let n=0;n<i.children.length;n++)F0(i.children[n],e.children[n],t)}var qs=class extends rn{constructor(e){super(e),this.dracoLoader=null,this.ktx2Loader=null,this.meshoptDecoder=null,this.pluginCallbacks=[],this.register(function(t){return new Xd(t)}),this.register(function(t){return new qd(t)}),this.register(function(t){return new tf(t)}),this.register(function(t){return new nf(t)}),this.register(function(t){return new rf(t)}),this.register(function(t){return new Yd(t)}),this.register(function(t){return new $d(t)}),this.register(function(t){return new Zd(t)}),this.register(function(t){return new Kd(t)}),this.register(function(t){return new Wd(t)}),this.register(function(t){return new Jd(t)}),this.register(function(t){return new jd(t)}),this.register(function(t){return new ef(t)}),this.register(function(t){return new Qd(t)}),this.register(function(t){return new Gd(t)}),this.register(function(t){return new $c(t,Ze.EXT_MESHOPT_COMPRESSION)}),this.register(function(t){return new $c(t,Ze.KHR_MESHOPT_COMPRESSION)}),this.register(function(t){return new sf(t)})}load(e,t,n,r){let s=this,a;if(this.resourcePath!=="")a=this.resourcePath;else if(this.path!==""){let c=In.extractUrlBase(e);a=In.resolveURL(c,this.path)}else a=In.extractUrlBase(e);this.manager.itemStart(e);let o=function(c){r?r(c):console.error(c),s.manager.itemError(e),s.manager.itemEnd(e)},l=new Nr(this.manager);l.setPath(this.path),l.setResponseType("arraybuffer"),l.setRequestHeader(this.requestHeader),l.setWithCredentials(this.withCredentials),l.load(e,function(c){try{s.parse(c,a,function(h){t(h),s.manager.itemEnd(e)},o)}catch(h){o(h)}},n,o)}setDRACOLoader(e){return this.dracoLoader=e,this}setKTX2Loader(e){return this.ktx2Loader=e,this}setMeshoptDecoder(e){return this.meshoptDecoder=e,this}register(e){return this.pluginCallbacks.indexOf(e)===-1&&this.pluginCallbacks.push(e),this}unregister(e){return this.pluginCallbacks.indexOf(e)!==-1&&this.pluginCallbacks.splice(this.pluginCallbacks.indexOf(e),1),this}parse(e,t,n,r){let s,a={},o={},l=new TextDecoder;if(typeof e=="string")s=JSON.parse(e);else if(e instanceof ArrayBuffer)if(l.decode(new Uint8Array(e,0,4))===G0){try{a[Ze.KHR_BINARY_GLTF]=new af(e)}catch(u){r&&r(u);return}s=JSON.parse(a[Ze.KHR_BINARY_GLTF].content)}else s=JSON.parse(l.decode(e));else s=e;if(s.asset===void 0||s.asset.version[0]<2){r&&r(new Error("THREE.GLTFLoader: Unsupported asset. glTF versions >=2.0 are supported."));return}let c=new ff(s,{path:t||this.resourcePath||"",crossOrigin:this.crossOrigin,requestHeader:this.requestHeader,manager:this.manager,ktx2Loader:this.ktx2Loader,meshoptDecoder:this.meshoptDecoder});c.fileLoader.setRequestHeader(this.requestHeader);for(let h=0;h<this.pluginCallbacks.length;h++){let u=this.pluginCallbacks[h](c);u.name||console.error("THREE.GLTFLoader: Invalid plugin found: missing name"),o[u.name]=u,a[u.name]=!0}if(s.extensionsUsed)for(let h=0;h<s.extensionsUsed.length;++h){let u=s.extensionsUsed[h],d=s.extensionsRequired||[];switch(u){case Ze.KHR_MATERIALS_UNLIT:a[u]=new Hd;break;case Ze.KHR_DRACO_MESH_COMPRESSION:a[u]=new of(s,this.dracoLoader);break;case Ze.KHR_TEXTURE_TRANSFORM:a[u]=new lf;break;case Ze.KHR_MESH_QUANTIZATION:a[u]=new cf;break;default:d.indexOf(u)>=0&&o[u]===void 0&&console.warn('THREE.GLTFLoader: Unknown extension "'+u+'".')}}c.setExtensions(a),c.setPlugins(o),c.parse(n,r)}parseAsync(e,t){let n=this;return new Promise(function(r,s){n.parse(e,t,r,s)})}};function dT(){let i={};return{get:function(e){return i[e]},add:function(e,t){i[e]=t},remove:function(e){delete i[e]},removeAll:function(){i={}}}}function Lt(i,e,t){let n=i.json.materials[e];return n.extensions&&n.extensions[t]?n.extensions[t]:null}var Ze={KHR_BINARY_GLTF:"KHR_binary_glTF",KHR_DRACO_MESH_COMPRESSION:"KHR_draco_mesh_compression",KHR_LIGHTS_PUNCTUAL:"KHR_lights_punctual",KHR_MATERIALS_CLEARCOAT:"KHR_materials_clearcoat",KHR_MATERIALS_DISPERSION:"KHR_materials_dispersion",KHR_MATERIALS_IOR:"KHR_materials_ior",KHR_MATERIALS_SHEEN:"KHR_materials_sheen",KHR_MATERIALS_SPECULAR:"KHR_materials_specular",KHR_MATERIALS_TRANSMISSION:"KHR_materials_transmission",KHR_MATERIALS_IRIDESCENCE:"KHR_materials_iridescence",KHR_MATERIALS_ANISOTROPY:"KHR_materials_anisotropy",KHR_MATERIALS_UNLIT:"KHR_materials_unlit",KHR_MATERIALS_VOLUME:"KHR_materials_volume",KHR_TEXTURE_BASISU:"KHR_texture_basisu",KHR_TEXTURE_TRANSFORM:"KHR_texture_transform",KHR_MESH_QUANTIZATION:"KHR_mesh_quantization",KHR_MATERIALS_EMISSIVE_STRENGTH:"KHR_materials_emissive_strength",EXT_MATERIALS_BUMP:"EXT_materials_bump",EXT_TEXTURE_WEBP:"EXT_texture_webp",EXT_TEXTURE_AVIF:"EXT_texture_avif",EXT_MESHOPT_COMPRESSION:"EXT_meshopt_compression",KHR_MESHOPT_COMPRESSION:"KHR_meshopt_compression",EXT_MESH_GPU_INSTANCING:"EXT_mesh_gpu_instancing"},Gd=class{constructor(e){this.parser=e,this.name=Ze.KHR_LIGHTS_PUNCTUAL,this.cache={refs:{},uses:{}}}_markDefs(){let e=this.parser,t=this.parser.json.nodes||[];for(let n=0,r=t.length;n<r;n++){let s=t[n];s.extensions&&s.extensions[this.name]&&s.extensions[this.name].light!==void 0&&e._addNodeRef(this.cache,s.extensions[this.name].light)}}_loadLight(e){let t=this.parser,n="light:"+e,r=t.cache.get(n);if(r)return r;let s=t.json,l=((s.extensions&&s.extensions[this.name]||{}).lights||[])[e],c,h=new Ie(16777215);l.color!==void 0&&h.setRGB(l.color[0],l.color[1],l.color[2],li);let u=l.range!==void 0?l.range:0;switch(l.type){case"directional":c=new Or(h),c.target.position.set(0,0,-1),c.add(c.target);break;case"point":c=new Da(h),c.distance=u;break;case"spot":c=new La(h),c.distance=u,l.spot=l.spot||{},l.spot.innerConeAngle=l.spot.innerConeAngle!==void 0?l.spot.innerConeAngle:0,l.spot.outerConeAngle=l.spot.outerConeAngle!==void 0?l.spot.outerConeAngle:Math.PI/4,c.angle=l.spot.outerConeAngle,c.penumbra=1-l.spot.innerConeAngle/l.spot.outerConeAngle,c.target.position.set(0,0,-1),c.add(c.target);break;default:throw new Error("THREE.GLTFLoader: Unexpected light type: "+l.type)}return c.position.set(0,0,0),un(c,l),l.intensity!==void 0&&(c.intensity=l.intensity),c.name=t.createUniqueName(l.name||"light_"+e),r=Promise.resolve(c),t.cache.add(n,r),r}getDependency(e,t){if(e==="light")return this._loadLight(t)}createNodeAttachment(e){let t=this,n=this.parser,s=n.json.nodes[e],o=(s.extensions&&s.extensions[this.name]||{}).light;return o===void 0?null:this._loadLight(o).then(function(l){return n._getNodeRef(t.cache,o,l)})}},Hd=class{constructor(){this.name=Ze.KHR_MATERIALS_UNLIT}getMaterialType(){return Yt}extendParams(e,t,n){let r=[];e.color=new Ie(1,1,1),e.opacity=1;let s=t.pbrMetallicRoughness;if(s){if(Array.isArray(s.baseColorFactor)){let a=s.baseColorFactor;e.color.setRGB(a[0],a[1],a[2],li),e.opacity=a[3]}s.baseColorTexture!==void 0&&r.push(n.assignTexture(e,"map",s.baseColorTexture,bt))}return Promise.all(r)}},Wd=class{constructor(e){this.parser=e,this.name=Ze.KHR_MATERIALS_EMISSIVE_STRENGTH}extendMaterialParams(e,t){let n=Lt(this.parser,e,this.name);return n===null||n.emissiveStrength!==void 0&&(t.emissiveIntensity=n.emissiveStrength),Promise.resolve()}},Xd=class{constructor(e){this.parser=e,this.name=Ze.KHR_MATERIALS_CLEARCOAT}getMaterialType(e){return Lt(this.parser,e,this.name)!==null?bi:null}extendMaterialParams(e,t){let n=Lt(this.parser,e,this.name);if(n===null)return Promise.resolve();let r=[];if(n.clearcoatFactor!==void 0&&(t.clearcoat=n.clearcoatFactor),n.clearcoatTexture!==void 0&&r.push(this.parser.assignTexture(t,"clearcoatMap",n.clearcoatTexture)),n.clearcoatRoughnessFactor!==void 0&&(t.clearcoatRoughness=n.clearcoatRoughnessFactor),n.clearcoatRoughnessTexture!==void 0&&r.push(this.parser.assignTexture(t,"clearcoatRoughnessMap",n.clearcoatRoughnessTexture)),n.clearcoatNormalTexture!==void 0&&(r.push(this.parser.assignTexture(t,"clearcoatNormalMap",n.clearcoatNormalTexture)),n.clearcoatNormalTexture.scale!==void 0)){let s=n.clearcoatNormalTexture.scale;t.clearcoatNormalScale=new Se(s,s)}return Promise.all(r)}},qd=class{constructor(e){this.parser=e,this.name=Ze.KHR_MATERIALS_DISPERSION}getMaterialType(e){return Lt(this.parser,e,this.name)!==null?bi:null}extendMaterialParams(e,t){let n=Lt(this.parser,e,this.name);return n===null||(t.dispersion=n.dispersion!==void 0?n.dispersion:0),Promise.resolve()}},jd=class{constructor(e){this.parser=e,this.name=Ze.KHR_MATERIALS_IRIDESCENCE}getMaterialType(e){return Lt(this.parser,e,this.name)!==null?bi:null}extendMaterialParams(e,t){let n=Lt(this.parser,e,this.name);if(n===null)return Promise.resolve();let r=[];return n.iridescenceFactor!==void 0&&(t.iridescence=n.iridescenceFactor),n.iridescenceTexture!==void 0&&r.push(this.parser.assignTexture(t,"iridescenceMap",n.iridescenceTexture)),n.iridescenceIor!==void 0&&(t.iridescenceIOR=n.iridescenceIor),t.iridescenceThicknessRange===void 0&&(t.iridescenceThicknessRange=[100,400]),n.iridescenceThicknessMinimum!==void 0&&(t.iridescenceThicknessRange[0]=n.iridescenceThicknessMinimum),n.iridescenceThicknessMaximum!==void 0&&(t.iridescenceThicknessRange[1]=n.iridescenceThicknessMaximum),n.iridescenceThicknessTexture!==void 0&&r.push(this.parser.assignTexture(t,"iridescenceThicknessMap",n.iridescenceThicknessTexture)),Promise.all(r)}},Yd=class{constructor(e){this.parser=e,this.name=Ze.KHR_MATERIALS_SHEEN}getMaterialType(e){return Lt(this.parser,e,this.name)!==null?bi:null}extendMaterialParams(e,t){let n=Lt(this.parser,e,this.name);if(n===null)return Promise.resolve();let r=[];if(t.sheenColor=new Ie(0,0,0),t.sheenRoughness=0,t.sheen=1,n.sheenColorFactor!==void 0){let s=n.sheenColorFactor;t.sheenColor.setRGB(s[0],s[1],s[2],li)}return n.sheenRoughnessFactor!==void 0&&(t.sheenRoughness=n.sheenRoughnessFactor),n.sheenColorTexture!==void 0&&r.push(this.parser.assignTexture(t,"sheenColorMap",n.sheenColorTexture,bt)),n.sheenRoughnessTexture!==void 0&&r.push(this.parser.assignTexture(t,"sheenRoughnessMap",n.sheenRoughnessTexture)),Promise.all(r)}},$d=class{constructor(e){this.parser=e,this.name=Ze.KHR_MATERIALS_TRANSMISSION}getMaterialType(e){return Lt(this.parser,e,this.name)!==null?bi:null}extendMaterialParams(e,t){let n=Lt(this.parser,e,this.name);if(n===null)return Promise.resolve();let r=[];return n.transmissionFactor!==void 0&&(t.transmission=n.transmissionFactor),n.transmissionTexture!==void 0&&r.push(this.parser.assignTexture(t,"transmissionMap",n.transmissionTexture)),Promise.all(r)}},Zd=class{constructor(e){this.parser=e,this.name=Ze.KHR_MATERIALS_VOLUME}getMaterialType(e){return Lt(this.parser,e,this.name)!==null?bi:null}extendMaterialParams(e,t){let n=Lt(this.parser,e,this.name);if(n===null)return Promise.resolve();let r=[];t.thickness=n.thicknessFactor!==void 0?n.thicknessFactor:0,n.thicknessTexture!==void 0&&r.push(this.parser.assignTexture(t,"thicknessMap",n.thicknessTexture)),t.attenuationDistance=n.attenuationDistance||1/0;let s=n.attenuationColor||[1,1,1];return t.attenuationColor=new Ie().setRGB(s[0],s[1],s[2],li),Promise.all(r)}},Kd=class{constructor(e){this.parser=e,this.name=Ze.KHR_MATERIALS_IOR}getMaterialType(e){return Lt(this.parser,e,this.name)!==null?bi:null}extendMaterialParams(e,t){let n=Lt(this.parser,e,this.name);return n===null||(t.ior=n.ior!==void 0?n.ior:1.5,t.ior===0&&(t.ior=1e3)),Promise.resolve()}},Jd=class{constructor(e){this.parser=e,this.name=Ze.KHR_MATERIALS_SPECULAR}getMaterialType(e){return Lt(this.parser,e,this.name)!==null?bi:null}extendMaterialParams(e,t){let n=Lt(this.parser,e,this.name);if(n===null)return Promise.resolve();let r=[];t.specularIntensity=n.specularFactor!==void 0?n.specularFactor:1,n.specularTexture!==void 0&&r.push(this.parser.assignTexture(t,"specularIntensityMap",n.specularTexture));let s=n.specularColorFactor||[1,1,1];return t.specularColor=new Ie().setRGB(s[0],s[1],s[2],li),n.specularColorTexture!==void 0&&r.push(this.parser.assignTexture(t,"specularColorMap",n.specularColorTexture,bt)),Promise.all(r)}},Qd=class{constructor(e){this.parser=e,this.name=Ze.EXT_MATERIALS_BUMP}getMaterialType(e){return Lt(this.parser,e,this.name)!==null?bi:null}extendMaterialParams(e,t){let n=Lt(this.parser,e,this.name);if(n===null)return Promise.resolve();let r=[];return t.bumpScale=n.bumpFactor!==void 0?n.bumpFactor:1,n.bumpTexture!==void 0&&r.push(this.parser.assignTexture(t,"bumpMap",n.bumpTexture)),Promise.all(r)}},ef=class{constructor(e){this.parser=e,this.name=Ze.KHR_MATERIALS_ANISOTROPY}getMaterialType(e){return Lt(this.parser,e,this.name)!==null?bi:null}extendMaterialParams(e,t){let n=Lt(this.parser,e,this.name);if(n===null)return Promise.resolve();let r=[];return n.anisotropyStrength!==void 0&&(t.anisotropy=n.anisotropyStrength),n.anisotropyRotation!==void 0&&(t.anisotropyRotation=n.anisotropyRotation),n.anisotropyTexture!==void 0&&r.push(this.parser.assignTexture(t,"anisotropyMap",n.anisotropyTexture)),Promise.all(r)}},tf=class{constructor(e){this.parser=e,this.name=Ze.KHR_TEXTURE_BASISU}loadTexture(e){let t=this.parser,n=t.json,r=n.textures[e];if(!r.extensions||!r.extensions[this.name])return null;let s=r.extensions[this.name],a=t.options.ktx2Loader;if(!a){if(n.extensionsRequired&&n.extensionsRequired.indexOf(this.name)>=0)throw new Error("THREE.GLTFLoader: setKTX2Loader must be called before loading KTX2 textures");return null}return t.loadTextureImage(e,s.source,a)}},nf=class{constructor(e){this.parser=e,this.name=Ze.EXT_TEXTURE_WEBP}loadTexture(e){let t=this.name,n=this.parser,r=n.json,s=r.textures[e];if(!s.extensions||!s.extensions[t])return null;let a=s.extensions[t],o=r.images[a.source],l=n.textureLoader;if(o.uri){let c=n.options.manager.getHandler(o.uri);c!==null&&(l=c)}return n.loadTextureImage(e,a.source,l)}},rf=class{constructor(e){this.parser=e,this.name=Ze.EXT_TEXTURE_AVIF}loadTexture(e){let t=this.name,n=this.parser,r=n.json,s=r.textures[e];if(!s.extensions||!s.extensions[t])return null;let a=s.extensions[t],o=r.images[a.source],l=n.textureLoader;if(o.uri){let c=n.options.manager.getHandler(o.uri);c!==null&&(l=c)}return n.loadTextureImage(e,a.source,l)}},$c=class{constructor(e,t){this.name=t,this.parser=e}loadBufferView(e){let t=this.parser.json,n=t.bufferViews[e];if(n.extensions&&n.extensions[this.name]){let r=n.extensions[this.name],s=this.parser.getDependency("buffer",r.buffer),a=this.parser.options.meshoptDecoder;if(!a||!a.supported){if(t.extensionsRequired&&t.extensionsRequired.indexOf(this.name)>=0)throw new Error("THREE.GLTFLoader: setMeshoptDecoder must be called before loading compressed files");return null}return s.then(function(o){let l=r.byteOffset||0,c=r.byteLength||0,h=r.count,u=r.byteStride,d=new Uint8Array(o,l,c);return a.decodeGltfBufferAsync?a.decodeGltfBufferAsync(h,u,d,r.mode,r.filter).then(function(f){return f.buffer}):a.ready.then(function(){let f=new ArrayBuffer(h*u);return a.decodeGltfBuffer(new Uint8Array(f),h,u,d,r.mode,r.filter),f})})}else return null}},sf=class{constructor(e){this.name=Ze.EXT_MESH_GPU_INSTANCING,this.parser=e}createNodeMesh(e){let t=this.parser.json,n=t.nodes[e];if(!n.extensions||!n.extensions[this.name]||n.mesh===void 0)return null;let r=t.meshes[n.mesh];for(let c of r.primitives)if(c.mode!==Ni.TRIANGLES&&c.mode!==Ni.TRIANGLE_STRIP&&c.mode!==Ni.TRIANGLE_FAN&&c.mode!==void 0)return null;let a=n.extensions[this.name].attributes,o=[],l={};for(let c in a)o.push(this.parser.getDependency("accessor",a[c]).then(h=>(l[c]=h,l[c])));return o.length<1?null:(o.push(this.parser.createNodeMesh(e)),Promise.all(o).then(c=>{let h=c.pop(),u=h.isGroup?h.children:[h],d=c[0].count,f=[];for(let p of u){let y=new ge,m=new P,g=new Ot,v=new P(1,1,1),S=new Cr(p.geometry,p.material,d);for(let M=0;M<d;M++)l.TRANSLATION&&m.fromBufferAttribute(l.TRANSLATION,M),l.ROTATION&&g.fromBufferAttribute(l.ROTATION,M),l.SCALE&&v.fromBufferAttribute(l.SCALE,M),S.setMatrixAt(M,y.compose(m,g,v));let _=null;for(let M in l)if(M==="_COLOR_0"){let w=l[M];S.instanceColor=new Mn(w.array,w.itemSize,w.normalized)}else if(M!=="TRANSLATION"&&M!=="ROTATION"&&M!=="SCALE"){if(_===null){let E=S.geometry;_=new ht,_.name=E.name;for(let x in E.attributes)_.setAttribute(x,E.attributes[x]);for(let x in E.morphAttributes)_.morphAttributes[x]=E.morphAttributes[x];E.index!==null&&_.setIndex(E.index),_.morphTargetsRelative=E.morphTargetsRelative;for(let x of E.groups)_.addGroup(x.start,x.count,x.materialIndex);E.boundingBox!==null&&(_.boundingBox=E.boundingBox.clone()),E.boundingSphere!==null&&(_.boundingSphere=E.boundingSphere.clone()),_.drawRange.start=E.drawRange.start,_.drawRange.count=E.drawRange.count,_.userData=Object.assign({},E.userData),S.geometry=_}let w=l[M];_.setAttribute(M,new Mn(w.array,w.itemSize,w.normalized))}Tt.prototype.copy.call(S,p),this.parser.assignFinalMaterial(S),f.push(S)}return h.isGroup?(h.clear(),h.add(...f),h):f[0]}))}},G0="glTF",co=12,B0={JSON:1313821514,BIN:5130562},af=class{constructor(e){this.name=Ze.KHR_BINARY_GLTF,this.content=null,this.body=null;let t=new DataView(e,0,co),n=new TextDecoder;if(this.header={magic:n.decode(new Uint8Array(e.slice(0,4))),version:t.getUint32(4,!0),length:t.getUint32(8,!0)},this.header.magic!==G0)throw new Error("THREE.GLTFLoader: Unsupported glTF-Binary header.");if(this.header.version<2)throw new Error("THREE.GLTFLoader: Legacy binary file detected.");let r=this.header.length-co,s=new DataView(e,co),a=0;for(;a<r;){let o=s.getUint32(a,!0);a+=4;let l=s.getUint32(a,!0);if(a+=4,l===B0.JSON){let c=new Uint8Array(e,co+a,o);this.content=n.decode(c)}else if(l===B0.BIN){let c=co+a;this.body=e.slice(c,c+o)}a+=o}if(this.content===null)throw new Error("THREE.GLTFLoader: JSON content not found.")}},of=class{constructor(e,t){if(!t)throw new Error("THREE.GLTFLoader: No DRACOLoader instance provided.");this.name=Ze.KHR_DRACO_MESH_COMPRESSION,this.json=e,this.dracoLoader=t,this.dracoLoader.preload()}decodePrimitive(e,t){let n=this.json,r=this.dracoLoader,s=e.extensions[this.name].bufferView,a=e.extensions[this.name].attributes,o={},l={},c={};for(let h in a){let u=uf[h]||h.toLowerCase();o[u]=a[h]}for(let h in e.attributes){let u=uf[h]||h.toLowerCase();if(a[h]!==void 0){let d=n.accessors[e.attributes[h]],f=Xs[d.componentType];c[u]=f.name,l[u]=d.normalized===!0}}return t.getDependency("bufferView",s).then(function(h){return new Promise(function(u,d){r.decodeDracoFile(h,function(f){for(let p in f.attributes){let y=f.attributes[p],m=l[p];m!==void 0&&(y.normalized=m)}u(f)},o,c,li,d)})})}},lf=class{constructor(){this.name=Ze.KHR_TEXTURE_TRANSFORM}extendTexture(e,t){if((t.texCoord===void 0||t.texCoord===e.channel)&&t.offset===void 0&&t.rotation===void 0&&t.scale===void 0)return e;if(e=e.clone(),t.texCoord!==void 0&&(e.channel=t.texCoord),t.offset!==void 0&&e.offset.fromArray(t.offset),t.rotation!==void 0&&(e.rotation=t.rotation),t.scale!==void 0&&e.repeat.fromArray(t.scale),t.rotation!==void 0){let n=Math.cos(e.rotation),r=Math.sin(e.rotation);e.matrix.set(e.repeat.x*n,e.repeat.y*r,e.offset.x,-e.repeat.x*r,e.repeat.y*n,e.offset.y,0,0,1),e.matrixAutoUpdate=!1}return e.needsUpdate=!0,e}},cf=class{constructor(){this.name=Ze.KHR_MESH_QUANTIZATION}},Zc=class extends nn{constructor(e,t,n,r){super(e,t,n,r)}copySampleValue_(e){let t=this.resultBuffer,n=this.sampleValues,r=this.valueSize,s=e*r*3+r;for(let a=0;a!==r;a++)t[a]=n[s+a];return t}interpolate_(e,t,n,r){let s=this.resultBuffer,a=this.sampleValues,o=this.valueSize,l=o*2,c=o*3,h=r-t,u=(n-t)/h,d=u*u,f=d*u,p=e*c,y=p-c,m=-2*f+3*d,g=f-d,v=1-m,S=g-d+u;for(let _=0;_!==o;_++){let M=a[y+_+o],w=a[y+_+l]*h,E=a[p+_+o],x=a[p+_]*h;s[_]=v*M+S*w+m*E+g*x}return s}},fT=new Ot,hf=class extends Zc{interpolate_(e,t,n,r){let s=super.interpolate_(e,t,n,r);return fT.fromArray(s).normalize().toArray(s),s}},Ni={FLOAT:5126,FLOAT_MAT3:35675,FLOAT_MAT4:35676,FLOAT_VEC2:35664,FLOAT_VEC3:35665,FLOAT_VEC4:35666,LINEAR:9729,REPEAT:10497,SAMPLER_2D:35678,POINTS:0,LINES:1,LINE_LOOP:2,LINE_STRIP:3,TRIANGLES:4,TRIANGLE_STRIP:5,TRIANGLE_FAN:6,UNSIGNED_BYTE:5121,UNSIGNED_SHORT:5123},Xs={5120:Int8Array,5121:Uint8Array,5122:Int16Array,5123:Uint16Array,5125:Uint32Array,5126:Float32Array},k0={9728:At,9729:St,9984:Vl,9985:Ds,9986:zr,9987:Ci},z0={33071:Li,33648:vs,10497:$n},kd={SCALAR:1,VEC2:2,VEC3:3,VEC4:4,MAT2:4,MAT3:9,MAT4:16},uf={POSITION:"position",NORMAL:"normal",TANGENT:"tangent",TEXCOORD_0:"uv",TEXCOORD_1:"uv1",TEXCOORD_2:"uv2",TEXCOORD_3:"uv3",COLOR_0:"color",WEIGHTS_0:"skinWeight",JOINTS_0:"skinIndex"},ur={scale:"scale",translation:"position",rotation:"quaternion",weights:"morphTargetInfluences"},pT={CUBICSPLINE:void 0,LINEAR:Tr,STEP:wr},zd={OPAQUE:"OPAQUE",MASK:"MASK",BLEND:"BLEND"};function mT(i){return i.DefaultMaterial===void 0&&(i.DefaultMaterial=new Qn({color:16777215,emissive:0,metalness:1,roughness:1,transparent:!1,depthTest:!0,side:sn})),i.DefaultMaterial}function Yr(i,e,t){for(let n in t.extensions)i[n]===void 0&&(e.userData.gltfExtensions=e.userData.gltfExtensions||{},e.userData.gltfExtensions[n]=t.extensions[n])}function un(i,e){e.extras!==void 0&&(typeof e.extras=="object"?Object.assign(i.userData,e.extras):console.warn("THREE.GLTFLoader: Ignoring primitive type .extras, "+e.extras))}function gT(i,e,t){let n=!1,r=!1,s=!1;for(let c=0,h=e.length;c<h;c++){let u=e[c];if(u.POSITION!==void 0&&(n=!0),u.NORMAL!==void 0&&(r=!0),u.COLOR_0!==void 0&&(s=!0),n&&r&&s)break}if(!n&&!r&&!s)return Promise.resolve(i);let a=[],o=[],l=[];for(let c=0,h=e.length;c<h;c++){let u=e[c];if(n){let d=u.POSITION!==void 0?t.getDependency("accessor",u.POSITION):i.attributes.position;a.push(d)}if(r){let d=u.NORMAL!==void 0?t.getDependency("accessor",u.NORMAL):i.attributes.normal;o.push(d)}if(s){let d=u.COLOR_0!==void 0?t.getDependency("accessor",u.COLOR_0):i.attributes.color;l.push(d)}}return Promise.all([Promise.all(a),Promise.all(o),Promise.all(l)]).then(function(c){let h=c[0],u=c[1],d=c[2];return n&&(i.morphAttributes.position=h),r&&(i.morphAttributes.normal=u),s&&(i.morphAttributes.color=d),i.morphTargetsRelative=!0,i})}function yT(i,e){if(i.updateMorphTargets(),e.weights!==void 0)for(let t=0,n=e.weights.length;t<n;t++)i.morphTargetInfluences[t]=e.weights[t];if(e.extras&&Array.isArray(e.extras.targetNames)){let t=e.extras.targetNames;if(i.morphTargetInfluences.length===t.length){i.morphTargetDictionary={};for(let n=0,r=t.length;n<r;n++)i.morphTargetDictionary[t[n]]=n}else console.warn("THREE.GLTFLoader: Invalid extras.targetNames length. Ignoring names.")}}function _T(i){let e,t=i.extensions&&i.extensions[Ze.KHR_DRACO_MESH_COMPRESSION];if(t?e="draco:"+t.bufferView+":"+t.indices+":"+Vd(t.attributes):e=i.indices+":"+Vd(i.attributes)+":"+i.mode,i.targets!==void 0)for(let n=0,r=i.targets.length;n<r;n++)e+=":"+Vd(i.targets[n]);return e}function Vd(i){let e="",t=Object.keys(i).sort();for(let n=0,r=t.length;n<r;n++)e+=t[n]+":"+i[t[n]]+";";return e}function df(i){switch(i){case Int8Array:return 1/127;case Uint8Array:return 1/255;case Int16Array:return 1/32767;case Uint16Array:return 1/65535;default:throw new Error("THREE.GLTFLoader: Unsupported normalized accessor component type.")}}function xT(i){return i.search(/\.jpe?g($|\?)/i)>0||i.search(/^data\:image\/jpeg/)===0?"image/jpeg":i.search(/\.webp($|\?)/i)>0||i.search(/^data\:image\/webp/)===0?"image/webp":i.search(/\.ktx2($|\?)/i)>0||i.search(/^data\:image\/ktx2/)===0?"image/ktx2":"image/png"}var vT=new ge,ff=class{constructor(e={},t={}){this.json=e,this.extensions={},this.plugins={},this.options=t,this.cache=new dT,this.associations=new Map,this.primitiveCache={},this.nodeCache={},this.meshCache={refs:{},uses:{}},this.cameraCache={refs:{},uses:{}},this.lightCache={refs:{},uses:{}},this.sourceCache={},this.textureCache={},this.nodeNamesUsed={};let n=!1,r=-1,s=!1,a=-1;if(typeof navigator<"u"&&typeof navigator.userAgent<"u"){let o=navigator.userAgent;n=/^((?!chrome|android).)*safari/i.test(o)===!0;let l=o.match(/Version\/(\d+)/);r=n&&l?parseInt(l[1],10):-1,s=o.indexOf("Firefox")>-1,a=s?o.match(/Firefox\/([0-9]+)\./)[1]:-1}typeof createImageBitmap>"u"||n&&r<17||s&&a<98?this.textureLoader=new Pa(this.options.manager):this.textureLoader=new Oa(this.options.manager),this.textureLoader.setCrossOrigin(this.options.crossOrigin),this.textureLoader.setRequestHeader(this.options.requestHeader),this.fileLoader=new Nr(this.options.manager),this.fileLoader.setResponseType("arraybuffer"),this.options.crossOrigin==="use-credentials"&&this.fileLoader.setWithCredentials(!0)}setExtensions(e){this.extensions=e}setPlugins(e){this.plugins=e}parse(e,t){let n=this,r=this.json,s=this.extensions;this.cache.removeAll(),this.nodeCache={},this._invokeAll(function(a){return a._markDefs&&a._markDefs()}),Promise.all(this._invokeAll(function(a){return a.beforeRoot&&a.beforeRoot()})).then(function(){return Promise.all([n.getDependencies("scene"),n.getDependencies("animation"),n.getDependencies("camera")])}).then(function(a){let o={scene:a[0][r.scene||0],scenes:a[0],animations:a[1],cameras:a[2],asset:r.asset,parser:n,userData:{}};return Yr(s,o,r),un(o,r),Promise.all(n._invokeAll(function(l){return l.afterRoot&&l.afterRoot(o)})).then(function(){for(let l of o.scenes)l.updateMatrixWorld();e(o)})}).catch(t)}_markDefs(){let e=this.json.nodes||[],t=this.json.skins||[],n=this.json.meshes||[];for(let r=0,s=t.length;r<s;r++){let a=t[r].joints;for(let o=0,l=a.length;o<l;o++)e[a[o]].isBone=!0}for(let r=0,s=e.length;r<s;r++){let a=e[r];a.mesh!==void 0&&(this._addNodeRef(this.meshCache,a.mesh),a.skin!==void 0&&(n[a.mesh].isSkinnedMesh=!0)),a.camera!==void 0&&this._addNodeRef(this.cameraCache,a.camera)}}_addNodeRef(e,t){t!==void 0&&(e.refs[t]===void 0&&(e.refs[t]=e.uses[t]=0),e.refs[t]++)}_getNodeRef(e,t,n){if(e.refs[t]<=1)return n;let r=n.clone(),s=(a,o)=>{let l=this.associations.get(a);l!=null&&this.associations.set(o,l);for(let[c,h]of a.children.entries())s(h,o.children[c])};return s(n,r),r.name+="_instance_"+e.uses[t]++,r}_invokeOne(e){let t=Object.values(this.plugins);t.push(this);for(let n=0;n<t.length;n++){let r=e(t[n]);if(r)return r}return null}_invokeAll(e){let t=Object.values(this.plugins);t.unshift(this);let n=[];for(let r=0;r<t.length;r++){let s=e(t[r]);s&&n.push(s)}return n}getDependency(e,t){let n=e+":"+t,r=this.cache.get(n);if(!r){switch(e){case"scene":r=this.loadScene(t);break;case"node":r=this._invokeOne(function(s){return s.loadNode&&s.loadNode(t)});break;case"mesh":r=this._invokeOne(function(s){return s.loadMesh&&s.loadMesh(t)});break;case"accessor":r=this.loadAccessor(t);break;case"bufferView":r=this._invokeOne(function(s){return s.loadBufferView&&s.loadBufferView(t)});break;case"buffer":r=this.loadBuffer(t);break;case"material":r=this._invokeOne(function(s){return s.loadMaterial&&s.loadMaterial(t)});break;case"texture":r=this._invokeOne(function(s){return s.loadTexture&&s.loadTexture(t)});break;case"skin":r=this.loadSkin(t);break;case"animation":r=this._invokeOne(function(s){return s.loadAnimation&&s.loadAnimation(t)});break;case"camera":r=this.loadCamera(t);break;default:if(r=this._invokeOne(function(s){return s!=this&&s.getDependency&&s.getDependency(e,t)}),!r)throw new Error("Unknown type: "+e);break}this.cache.add(n,r)}return r}getDependencies(e){let t=this.cache.get(e);if(!t){let n=this,r=this.json[e+(e==="mesh"?"es":"s")]||[];t=Promise.all(r.map(function(s,a){return n.getDependency(e,a)})),this.cache.add(e,t)}return t}loadBuffer(e){let t=this.json.buffers[e],n=this.fileLoader;if(t.type&&t.type!=="arraybuffer")throw new Error("THREE.GLTFLoader: "+t.type+" buffer type is not supported.");if(t.uri===void 0&&e===0)return Promise.resolve(this.extensions[Ze.KHR_BINARY_GLTF].body);let r=this.options;return new Promise(function(s,a){n.load(In.resolveURL(t.uri,r.path),s,void 0,function(){a(new Error('THREE.GLTFLoader: Failed to load buffer "'+t.uri+'".'))})})}loadBufferView(e){let t=this.json.bufferViews[e];return this.getDependency("buffer",t.buffer).then(function(n){let r=t.byteLength||0,s=t.byteOffset||0;return n.slice(s,s+r)})}loadAccessor(e){let t=this,n=this.json,r=this.json.accessors[e];if(r.bufferView===void 0&&r.sparse===void 0){let a=kd[r.type],o=Xs[r.componentType],l=r.normalized===!0,c=new o(r.count*a);return Promise.resolve(new Ye(c,a,l))}let s=[];return r.bufferView!==void 0?s.push(this.getDependency("bufferView",r.bufferView)):s.push(null),r.sparse!==void 0&&(s.push(this.getDependency("bufferView",r.sparse.indices.bufferView)),s.push(this.getDependency("bufferView",r.sparse.values.bufferView))),Promise.all(s).then(function(a){let o=a[0],l=kd[r.type],c=Xs[r.componentType],h=c.BYTES_PER_ELEMENT,u=h*l,d=r.byteOffset||0,f=r.bufferView!==void 0?n.bufferViews[r.bufferView].byteStride:void 0,p=r.normalized===!0,y,m;if(f&&f!==u){let g=Math.floor(d/f),v="InterleavedBuffer:"+r.bufferView+":"+r.componentType+":"+g+":"+r.count,S=t.cache.get(v);S||(y=new c(o,g*f,r.count*f/h),S=new Ar(y,f/h),t.cache.add(v,S)),m=new xi(S,l,d%f/h,p)}else o===null?y=new c(r.count*l):y=new c(o,d,r.count*l),m=new Ye(y,l,p);if(r.sparse!==void 0){let g=kd.SCALAR,v=Xs[r.sparse.indices.componentType],S=r.sparse.indices.byteOffset||0,_=r.sparse.values.byteOffset||0,M=new v(a[1],S,r.sparse.count*g),w=new c(a[2],_,r.sparse.count*l);o!==null&&(m=new Ye(m.array.slice(),m.itemSize,m.normalized)),m.normalized=!1;for(let E=0,x=M.length;E<x;E++){let A=M[E];if(m.setX(A,w[E*l]),l>=2&&m.setY(A,w[E*l+1]),l>=3&&m.setZ(A,w[E*l+2]),l>=4&&m.setW(A,w[E*l+3]),l>=5)throw new Error("THREE.GLTFLoader: Unsupported itemSize in sparse BufferAttribute.")}m.normalized=p}return m})}loadTexture(e){let t=this.json,n=this.options,s=t.textures[e].source,a=t.images[s],o=this.textureLoader;if(a.uri){let l=n.manager.getHandler(a.uri);l!==null&&(o=l)}return this.loadTextureImage(e,s,o)}loadTextureImage(e,t,n){let r=this,s=this.json,a=s.textures[e],o=s.images[t],l=(o.uri||o.bufferView)+":"+a.sampler;if(this.textureCache[l])return this.textureCache[l];let c=this.loadImageSource(t,n).then(function(h){h.flipY=!1,h.name=a.name||o.name||"",h.name===""&&typeof o.uri=="string"&&o.uri.startsWith("data:image/")===!1&&(h.name=o.uri);let d=(s.samplers||{})[a.sampler]||{};return h.magFilter=k0[d.magFilter]||St,h.minFilter=k0[d.minFilter]||Ci,h.wrapS=z0[d.wrapS]||$n,h.wrapT=z0[d.wrapT]||$n,h.generateMipmaps=!h.isCompressedTexture&&h.minFilter!==At&&h.minFilter!==St,r.associations.set(h,{textures:e}),h}).catch(function(){return null});return this.textureCache[l]=c,c}loadImageSource(e,t){let n=this,r=this.json,s=this.options;if(this.sourceCache[e]!==void 0)return this.sourceCache[e].then(u=>u.clone());let a=r.images[e],o=self.URL||self.webkitURL,l=a.uri||"",c=!1;if(a.bufferView!==void 0)l=n.getDependency("bufferView",a.bufferView).then(function(u){c=!0;let d=new Blob([u],{type:a.mimeType});return l=o.createObjectURL(d),l});else if(a.uri===void 0)throw new Error("THREE.GLTFLoader: Image "+e+" is missing URI and bufferView");let h=Promise.resolve(l).then(function(u){return new Promise(function(d,f){let p=d;t.isImageBitmapLoader===!0&&(p=function(y){let m=new Pt(y);m.needsUpdate=!0,d(m)}),t.load(In.resolveURL(u,s.path),p,void 0,f)})}).then(function(u){return c===!0&&o.revokeObjectURL(l),un(u,a),u.userData.mimeType=a.mimeType||xT(a.uri),u}).catch(function(u){throw console.error("THREE.GLTFLoader: Couldn't load texture",l),u});return this.sourceCache[e]=h,h}assignTexture(e,t,n,r){let s=this;return this.getDependency("texture",n.index).then(function(a){if(!a)return null;if(n.texCoord!==void 0&&n.texCoord>0&&(a=a.clone(),a.channel=n.texCoord),s.extensions[Ze.KHR_TEXTURE_TRANSFORM]){let o=n.extensions!==void 0?n.extensions[Ze.KHR_TEXTURE_TRANSFORM]:void 0;if(o){let l=s.associations.get(a);a=s.extensions[Ze.KHR_TEXTURE_TRANSFORM].extendTexture(a,o),s.associations.set(a,l)}}return r!==void 0&&(a.colorSpace=r),e[t]=a,a})}assignFinalMaterial(e){let t=e.geometry,n=e.material,r=t.attributes.tangent===void 0,s=t.attributes.color!==void 0,a=t.attributes.normal===void 0;if(e.isPoints){let o="PointsMaterial:"+n.uuid,l=this.cache.get(o);l||(l=new Tn,hi.prototype.copy.call(l,n),l.color.copy(n.color),l.map=n.map,l.sizeAttenuation=!1,this.cache.add(o,l)),n=l}else if(e.isLine){let o="LineBasicMaterial:"+n.uuid,l=this.cache.get(o);l||(l=new Rr,hi.prototype.copy.call(l,n),l.color.copy(n.color),l.map=n.map,this.cache.add(o,l)),n=l}if(r||s||a){let o="ClonedMaterial:"+n.uuid+":";r&&(o+="derivative-tangents:"),s&&(o+="vertex-colors:"),a&&(o+="flat-shading:");let l=this.cache.get(o);l||(l=n.clone(),s&&(l.vertexColors=!0),a&&(l.flatShading=!0),r&&(l.normalScale&&(l.normalScale.y*=-1),l.clearcoatNormalScale&&(l.clearcoatNormalScale.y*=-1)),this.cache.add(o,l),this.associations.set(l,this.associations.get(n))),n=l}e.material=n}getMaterialType(){return Qn}loadMaterial(e){let t=this,n=this.json,r=this.extensions,s=n.materials[e],a,o={},l=s.extensions||{},c=[];if(l[Ze.KHR_MATERIALS_UNLIT]){let u=r[Ze.KHR_MATERIALS_UNLIT];a=u.getMaterialType(),c.push(u.extendParams(o,s,t))}else{let u=s.pbrMetallicRoughness||{};if(o.color=new Ie(1,1,1),o.opacity=1,Array.isArray(u.baseColorFactor)){let d=u.baseColorFactor;o.color.setRGB(d[0],d[1],d[2],li),o.opacity=d[3]}u.baseColorTexture!==void 0&&c.push(t.assignTexture(o,"map",u.baseColorTexture,bt)),o.metalness=u.metallicFactor!==void 0?u.metallicFactor:1,o.roughness=u.roughnessFactor!==void 0?u.roughnessFactor:1,u.metallicRoughnessTexture!==void 0&&(c.push(t.assignTexture(o,"metalnessMap",u.metallicRoughnessTexture)),c.push(t.assignTexture(o,"roughnessMap",u.metallicRoughnessTexture))),a=this._invokeOne(function(d){return d.getMaterialType&&d.getMaterialType(e)}),c.push(Promise.all(this._invokeAll(function(d){return d.extendMaterialParams&&d.extendMaterialParams(e,o)})))}s.doubleSided===!0&&(o.side=ri);let h=s.alphaMode||zd.OPAQUE;if(h===zd.BLEND?(o.transparent=!0,o.depthWrite=!1):(o.transparent=!1,h===zd.MASK&&(o.alphaTest=s.alphaCutoff!==void 0?s.alphaCutoff:.5)),s.normalTexture!==void 0&&a!==Yt&&(c.push(t.assignTexture(o,"normalMap",s.normalTexture)),o.normalScale=new Se(1,1),s.normalTexture.scale!==void 0)){let u=s.normalTexture.scale;o.normalScale.set(u,u)}if(s.occlusionTexture!==void 0&&a!==Yt&&(c.push(t.assignTexture(o,"aoMap",s.occlusionTexture)),s.occlusionTexture.strength!==void 0&&(o.aoMapIntensity=s.occlusionTexture.strength)),s.emissiveFactor!==void 0&&a!==Yt){let u=s.emissiveFactor;o.emissive=new Ie().setRGB(u[0],u[1],u[2],li)}return s.emissiveTexture!==void 0&&a!==Yt&&c.push(t.assignTexture(o,"emissiveMap",s.emissiveTexture,bt)),Promise.all(c).then(function(){let u=new a(o);return s.name&&(u.name=s.name),un(u,s),t.associations.set(u,{materials:e}),s.extensions&&Yr(r,u,s),u})}createUniqueName(e){let t=mt.sanitizeNodeName(e||"");return t in this.nodeNamesUsed?t+"_"+ ++this.nodeNamesUsed[t]:(this.nodeNamesUsed[t]=0,t)}loadGeometries(e){let t=this,n=this.extensions,r=this.primitiveCache;function s(o){return n[Ze.KHR_DRACO_MESH_COMPRESSION].decodePrimitive(o,t).then(function(l){return V0(l,o,t)})}let a=[];for(let o=0,l=e.length;o<l;o++){let c=e[o],h=_T(c),u=r[h];if(u)a.push(u.promise);else{let d;c.extensions&&c.extensions[Ze.KHR_DRACO_MESH_COMPRESSION]?d=s(c):d=V0(new ht,c,t),c.mode===Ni.TRIANGLE_STRIP?d=d.then(f=>Bd(f,Ya)):c.mode===Ni.TRIANGLE_FAN&&(d=d.then(f=>Bd(f,Fs))),r[h]={primitive:c,promise:d},a.push(d)}}return Promise.all(a)}loadMesh(e){let t=this,n=this.json,r=this.extensions,s=n.meshes[e],a=s.primitives,o=[];for(let l=0,c=a.length;l<c;l++){let h=a[l].material===void 0?mT(this.cache):this.getDependency("material",a[l].material);o.push(h)}return o.push(t.loadGeometries(a)),Promise.all(o).then(async function(l){let c=l.slice(0,l.length-1),h=l[l.length-1],u=[];for(let f=0,p=h.length;f<p;f++){let y=h[f],m=a[f],g,v=c[f];if(m.mode===Ni.TRIANGLES||m.mode===Ni.TRIANGLE_STRIP||m.mode===Ni.TRIANGLE_FAN||m.mode===void 0){let S=s.isSkinnedMesh===!0,_=y.hasAttribute("skinIndex")&&y.hasAttribute("skinWeight");S&&_===!1&&console.warn("THREE.GLTFLoader: Missing skinIndex or skinWeight attributes. Skinning disabled."),g=S&&_?new Sa(y,v):new at(y,v),g.isSkinnedMesh===!0&&g.normalizeSkinWeights()}else if(m.mode===Ni.LINES)g=new As(y,v);else if(m.mode===Ni.LINE_STRIP)g=new Pr(y,v);else if(m.mode===Ni.LINE_LOOP)g=new wa(y,v);else if(m.mode===Ni.POINTS)g=new Zn(y,v);else throw new Error("THREE.GLTFLoader: Primitive mode unsupported: "+m.mode);Object.keys(g.geometry.morphAttributes).length>0&&yT(g,s),g.name=t.createUniqueName(s.name||"mesh_"+e),un(g,s),m.extensions&&Yr(r,g,m),t.assignFinalMaterial(g),u.push(g)}for(let f=0,p=u.length;f<p;f++)t.associations.set(u[f],{meshes:e,primitives:f});if(u.length===1)return s.extensions&&Yr(r,u[0],s),u[0];let d=new Xt;s.extensions&&Yr(r,d,s),t.associations.set(d,{meshes:e});for(let f=0,p=u.length;f<p;f++)d.add(u[f]);return d})}loadCamera(e){let t,n=this.json.cameras[e],r=n[n.type];if(!r){console.warn("THREE.GLTFLoader: Missing camera parameters.");return}return n.type==="perspective"?t=new Rt(ye.radToDeg(r.yfov),r.aspectRatio||1,r.znear||1,r.zfar||2e6):n.type==="orthographic"&&(t=new Wi(-r.xmag,r.xmag,r.ymag,-r.ymag,r.znear,r.zfar)),n.name&&(t.name=this.createUniqueName(n.name)),un(t,n),Promise.resolve(t)}loadSkin(e){let t=this.json.skins[e],n=[];for(let r=0,s=t.joints.length;r<s;r++)n.push(this._loadNodeShallow(t.joints[r]));return t.inverseBindMatrices!==void 0?n.push(this.getDependency("accessor",t.inverseBindMatrices)):n.push(null),Promise.all(n).then(function(r){let s=r.pop(),a=r,o=[],l=[];for(let c=0,h=a.length;c<h;c++){let u=a[c];if(u){o.push(u);let d=new ge;s!==null&&d.fromArray(s.array,c*16),l.push(d)}else console.warn('THREE.GLTFLoader: Joint "%s" could not be found.',t.joints[c])}return new Ma(o,l)})}loadAnimation(e){let t=this.json,n=this,r=t.animations[e],s=r.name?r.name:"animation_"+e,a=[],o=[],l=[],c=[],h=[];for(let u=0,d=r.channels.length;u<d;u++){let f=r.channels[u],p=r.samplers[f.sampler],y=f.target,m=y.node,g=r.parameters!==void 0?r.parameters[p.input]:p.input,v=r.parameters!==void 0?r.parameters[p.output]:p.output;y.node!==void 0&&(a.push(this.getDependency("node",m)),o.push(this.getDependency("accessor",g)),l.push(this.getDependency("accessor",v)),c.push(p),h.push(y))}return Promise.all([Promise.all(a),Promise.all(o),Promise.all(l),Promise.all(c),Promise.all(h)]).then(function(u){let d=u[0],f=u[1],p=u[2],y=u[3],m=u[4],g=[];for(let S=0,_=d.length;S<_;S++){let M=d[S],w=f[S],E=p[S],x=y[S],A=m[S];if(M===void 0)continue;M.updateMatrix&&M.updateMatrix();let C=n._createAnimationTracks(M,w,E,x,A);if(C)for(let D=0;D<C.length;D++)g.push(C[D])}let v=new Ra(s,void 0,g);return un(v,r),v})}createNodeMesh(e){let t=this.json,n=this,r=t.nodes[e];return r.mesh===void 0?null:n.getDependency("mesh",r.mesh).then(function(s){let a=n._getNodeRef(n.meshCache,r.mesh,s);return r.weights!==void 0&&a.traverse(function(o){if(o.isMesh)for(let l=0,c=r.weights.length;l<c;l++)o.morphTargetInfluences[l]=r.weights[l]}),a})}loadNode(e){let t=this.json,n=this,r=t.nodes[e],s=n._loadNodeShallow(e),a=[],o=r.children||[];for(let c=0,h=o.length;c<h;c++)a.push(n.getDependency("node",o[c]));let l=r.skin===void 0?Promise.resolve(null):n.getDependency("skin",r.skin);return Promise.all([s,Promise.all(a),l]).then(function(c){let h=c[0],u=c[1],d=c[2];d!==null&&h.traverse(function(f){f.isSkinnedMesh&&f.bind(d,vT)});for(let f=0,p=u.length;f<p;f++)h.add(u[f]);if(h.userData.pivot!==void 0&&u.length>0){let f=h.userData.pivot,p=u[0];h.pivot=new P().fromArray(f),h.position.x-=f[0],h.position.y-=f[1],h.position.z-=f[2],p.position.set(0,0,0),delete h.userData.pivot}return h})}_loadNodeShallow(e){let t=this.json,n=this.extensions,r=this;if(this.nodeCache[e]!==void 0)return this.nodeCache[e];let s=t.nodes[e],a=s.name?r.createUniqueName(s.name):"",o=[],l=r._invokeOne(function(c){return c.createNodeMesh&&c.createNodeMesh(e)});return l&&o.push(l),s.camera!==void 0&&o.push(r.getDependency("camera",s.camera).then(function(c){return r._getNodeRef(r.cameraCache,s.camera,c)})),r._invokeAll(function(c){return c.createNodeAttachment&&c.createNodeAttachment(e)}).forEach(function(c){o.push(c)}),this.nodeCache[e]=Promise.all(o).then(function(c){let h;if(s.isBone===!0?h=new Es:c.length>1?h=new Xt:c.length===1?h=c[0]:h=new Tt,h!==c[0])for(let u=0,d=c.length;u<d;u++)h.add(c[u]);if(s.name&&(h.userData.name=s.name,h.name=a),un(h,s),s.extensions&&Yr(n,h,s),s.matrix!==void 0){let u=new ge;u.fromArray(s.matrix),h.applyMatrix4(u)}else s.translation!==void 0&&h.position.fromArray(s.translation),s.rotation!==void 0&&h.quaternion.fromArray(s.rotation),s.scale!==void 0&&h.scale.fromArray(s.scale);if(!r.associations.has(h))r.associations.set(h,{});else if(s.mesh!==void 0&&r.meshCache.refs[s.mesh]>1){let u=r.associations.get(h);r.associations.set(h,{...u})}return r.associations.get(h).nodes=e,h}),this.nodeCache[e]}loadScene(e){let t=this.extensions,n=this.json.scenes[e],r=this,s=new Xt;n.name&&(s.name=r.createUniqueName(n.name)),un(s,n),n.extensions&&Yr(t,s,n);let a=n.nodes||[],o=[];for(let l=0,c=a.length;l<c;l++)o.push(r.getDependency("node",a[l]));return Promise.all(o).then(function(l){for(let h=0,u=l.length;h<u;h++){let d=l[h];d.parent!==null?s.add(O0(d)):s.add(d)}let c=h=>{let u=new Map;for(let[d,f]of r.associations)(d instanceof hi||d instanceof Pt)&&u.set(d,f);return h.traverse(d=>{let f=r.associations.get(d);f!=null&&u.set(d,f)}),u};return r.associations=c(s),s})}_createAnimationTracks(e,t,n,r,s){let a=[],o=e.name?e.name:e.uuid,l=[];function c(f){f.morphTargetInfluences&&l.push(f.name?f.name:f.uuid)}ur[s.path]===ur.weights?(c(e),e.isGroup&&e.children.forEach(c)):l.push(o);let h;switch(ur[s.path]){case ur.weights:h=Cn;break;case ur.rotation:h=Rn;break;case ur.translation:case ur.scale:h=er;break;default:n.itemSize===1?h=Cn:h=er;break}let u=r.interpolation!==void 0?pT[r.interpolation]:Tr,d=this._getArrayFromAccessor(n);for(let f=0,p=l.length;f<p;f++){let y=new h(l[f]+"."+ur[s.path],t.array,d,u);r.interpolation==="CUBICSPLINE"&&this._createCubicSplineTrackInterpolant(y),a.push(y)}return a}_getArrayFromAccessor(e){let t=e.array;if(e.normalized){let n=df(t.constructor),r=new Float32Array(t.length);for(let s=0,a=t.length;s<a;s++)r[s]=t[s]*n;t=r}return t}_createCubicSplineTrackInterpolant(e){e.createInterpolant=function(n){let r=this instanceof Rn?hf:Zc;return new r(this.times,this.values,this.getValueSize()/3,n)},e.createInterpolant.isInterpolantFactoryMethodGLTFCubicSpline=!0}};function bT(i,e,t){let n=e.attributes,r=new Mt;if(n.POSITION!==void 0){let o=t.json.accessors[n.POSITION],l=o.min,c=o.max;if(l!==void 0&&c!==void 0){if(r.set(new P(l[0],l[1],l[2]),new P(c[0],c[1],c[2])),o.normalized){let h=df(Xs[o.componentType]);r.min.multiplyScalar(h),r.max.multiplyScalar(h)}}else{console.warn("THREE.GLTFLoader: Missing min/max properties for accessor POSITION.");return}}else return;let s=e.targets;if(s!==void 0){let o=new P,l=new P;for(let c=0,h=s.length;c<h;c++){let u=s[c];if(u.POSITION!==void 0){let d=t.json.accessors[u.POSITION],f=d.min,p=d.max;if(f!==void 0&&p!==void 0){if(l.setX(Math.max(Math.abs(f[0]),Math.abs(p[0]))),l.setY(Math.max(Math.abs(f[1]),Math.abs(p[1]))),l.setZ(Math.max(Math.abs(f[2]),Math.abs(p[2]))),d.normalized){let y=df(Xs[d.componentType]);l.multiplyScalar(y)}o.max(l)}else console.warn("THREE.GLTFLoader: Missing min/max properties for accessor POSITION.")}}r.expandByVector(o)}i.boundingBox=r;let a=new Et;r.getCenter(a.center),a.radius=r.min.distanceTo(r.max)/2,i.boundingSphere=a}function V0(i,e,t){let n=e.attributes,r=[];function s(a,o){return t.getDependency("accessor",a).then(function(l){i.setAttribute(o,l)})}for(let a in n){let o=uf[a]||a.toLowerCase();o in i.attributes||r.push(s(n[a],o))}if(e.indices!==void 0&&!i.index){let a=t.getDependency("accessor",e.indices).then(function(o){i.setIndex(o)});r.push(a)}return je.workingColorSpace!==li&&"COLOR_0"in n&&console.warn(`THREE.GLTFLoader: Converting vertex colors from "srgb-linear" to "${je.workingColorSpace}" not supported.`),un(i,e),bT(i,e,t),Promise.all(r).then(function(){return e.targets!==void 0?gT(i,e.targets,t):i})}var Sf=class extends I0{constructor(i=or){super(),this.manager=i,this.adjustmentTransform=new ge}parse(i){let e=super.parse(i),t=e.glbBytes.slice().buffer;return new Promise((n,r)=>{let s=this.manager,a=this.fetchOptions,o=s.getHandler("path.gltf")||new qs(s);a.credentials==="include"&&a.mode==="cors"&&o.setCrossOrigin("use-credentials"),"credentials"in a&&o.setWithCredentials(a.credentials==="include"),a.headers&&o.setRequestHeader(a.headers);let l=this.workingPath;!/[\\/]$/.test(l)&&l.length&&(l+="/");let c=this.adjustmentTransform;o.parse(t,l,h=>{let{batchTable:u,featureTable:d}=e,{scene:f}=h,p=d.getData("RTC_CENTER",1,"FLOAT","VEC3");p&&(f.position.x+=p[0],f.position.y+=p[1],f.position.z+=p[2]),h.scene.updateMatrix(),h.scene.matrix.multiply(c),h.scene.matrix.decompose(h.scene.position,h.scene.quaternion,h.scene.scale),h.batchTable=u,h.featureTable=d,f.batchTable=u,f.featureTable=d,n(h)},r)})}};function ST(i){let e=i>>11,t=i>>5&63,n=i&31;return[Math.round(e/31*255),Math.round(t/63*255),Math.round(n/31*255)]}var ho=new Se;function MT(i,e,t=new P){ho.set(i,e).divideScalar(256).multiplyScalar(2).subScalar(1),t.set(ho.x,ho.y,1-Math.abs(ho.x)-Math.abs(ho.y));let n=ye.clamp(-t.z,0,1);return t.x>=0?t.setX(t.x-n):t.setX(t.x+n),t.y>=0?t.setY(t.y-n):t.setY(t.y+n),t.normalize(),t}var H0={RGB:"color",POSITION:"position"},Mf=class extends D0{constructor(i=or){super(),this.manager=i}parse(i){return super.parse(i).then(async e=>{let{featureTable:t,batchTable:n}=e,r=new Tn,s=t.header.extensions,a=new P,o;if(s&&s["3DTILES_draco_point_compression"]){let{byteOffset:h,byteLength:u,properties:d}=s["3DTILES_draco_point_compression"],f=this.manager.getHandler("draco.drc");if(f==null)throw Error("PNTSLoader: dracoLoader not available.");let p={};for(let g in d)if(g in H0&&g in d){let v=H0[g];p[v]=d[g]}let y={attributeIDs:p,attributeTypes:{position:"Float32Array",color:"Uint8Array"},useUniqueIDs:!0},m=t.getBuffer(h,u);o=await f.decodeGeometry(m,y),o.attributes.color&&(r.vertexColors=!0)}else{let h=t.getData("POINTS_LENGTH"),u=t.getData("POSITION",h,"FLOAT","VEC3"),d=t.getData("NORMAL",h,"FLOAT","VEC3"),f=t.getData("NORMAL",h,"UNSIGNED_BYTE","VEC2"),p=t.getData("RGB",h,"UNSIGNED_BYTE","VEC3"),y=t.getData("RGBA",h,"UNSIGNED_BYTE","VEC4"),m=t.getData("RGB565",h,"UNSIGNED_SHORT","SCALAR"),g=t.getData("CONSTANT_RGBA",h,"UNSIGNED_BYTE","VEC4"),v=t.getData("POSITION_QUANTIZED",h,"UNSIGNED_SHORT","VEC3"),S=t.getData("QUANTIZED_VOLUME_SCALE",h,"FLOAT","VEC3"),_=t.getData("QUANTIZED_VOLUME_OFFSET",h,"FLOAT","VEC3");if(o=new ht,v){let M=new Float32Array(h*3);for(let w=0;w<h;w++)for(let E=0;E<3;E++){let x=3*w+E;M[x]=v[x]/65535*S[E]}a.x=_[0],a.y=_[1],a.z=_[2],o.setAttribute("position",new Ye(M,3,!1))}else o.setAttribute("position",new Ye(u,3,!1));if(d!==null)o.setAttribute("normal",new Ye(d,3,!1));else if(f!==null){let M=new Float32Array(h*3),w=new P;for(let E=0;E<h;E++){let x=f[E*2],A=f[E*2+1],C=MT(x,A,w);M[E*3]=C.x,M[E*3+1]=C.y,M[E*3+2]=C.z}o.setAttribute("normal",new Ye(M,3,!1))}if(y!==null)o.setAttribute("color",new Ye(y,4,!0)),r.vertexColors=!0,r.transparent=!0,r.depthWrite=!1;else if(p!==null)o.setAttribute("color",new Ye(p,3,!0)),r.vertexColors=!0;else if(m!==null){let M=new Uint8Array(h*3);for(let w=0;w<h;w++){let E=ST(m[w]);for(let x=0;x<3;x++){let A=3*w+x;M[A]=E[x]}}o.setAttribute("color",new Ye(M,3,!0)),r.vertexColors=!0}else if(g!==null){r.color=new Ie(g[0],g[1],g[2]);let M=g[3]/255;M<1&&(r.opacity=M,r.transparent=!0,r.depthWrite=!1)}}let l=new Zn(o,r);l.position.copy(a),e.scene=l,e.scene.featureTable=t,e.scene.batchTable=n;let c=t.getData("RTC_CENTER",1,"FLOAT","VEC3");return c&&(e.scene.position.x+=c[0],e.scene.position.y+=c[1],e.scene.position.z+=c[2]),e})}};function wT(i){let{x:e,y:t,z:n}=i;i.x=n,i.y=e,i.z=t}function TT(i){return-i+Math.PI/2}var W0=new ir,dr=new P,mi=new P,pf=new P,Ui=new ge,dn=new ge,mf=new Et,Mi=new Di,X0=new P,q0=new P,j0=new P,uo=new P,Kc=new vi,ET=1e-12,AT=.1;var ah=class{constructor(i=1,e=1,t=1){this.isEllipsoid=!0,this.name="",this.radius=new P(i,e,t)}intersectRay(i,e){return Ui.makeScale(...this.radius).invert(),mf.center.set(0,0,0),mf.radius=1,Kc.copy(i).applyMatrix4(Ui),Kc.intersectSphere(mf,e)?(Ui.makeScale(...this.radius),e.applyMatrix4(Ui),e):null}getEastNorthUpFrame(i,e,t,n){return t.isMatrix4&&(n=t,t=0,console.warn('Ellipsoid: The signature for "getEastNorthUpFrame" has changed.')),this.getEastNorthUpAxes(i,e,X0,q0,j0),this.getCartographicToPosition(i,e,t,uo),n.makeBasis(X0,q0,j0).setPosition(uo)}getOrientedEastNorthUpFrame(i,e,t,n,r,s,a){return this.getObjectFrame(i,e,t,n,r,s,a,0)}getObjectFrame(i,e,t,n,r,s,a,o=2){return this.getEastNorthUpFrame(i,e,t,Ui),Mi.set(r,s,-n,"ZXY"),a.makeRotationFromEuler(Mi).premultiply(Ui),o===1?(Mi.set(Math.PI/2,0,0,"XYZ"),dn.makeRotationFromEuler(Mi),a.multiply(dn)):o===2&&(Mi.set(-Math.PI/2,0,Math.PI,"XYZ"),dn.makeRotationFromEuler(Mi),a.multiply(dn)),a}getCartographicFromObjectFrame(i,e,t=2){return t===1?(Mi.set(-Math.PI/2,0,0,"XYZ"),dn.makeRotationFromEuler(Mi).premultiply(i)):t===2?(Mi.set(-Math.PI/2,0,Math.PI,"XYZ"),dn.makeRotationFromEuler(Mi).premultiply(i)):dn.copy(i),uo.setFromMatrixPosition(dn),this.getPositionToCartographic(uo,e),this.getEastNorthUpFrame(e.lat,e.lon,0,Ui).invert(),dn.premultiply(Ui),Mi.setFromRotationMatrix(dn,"ZXY"),e.azimuth=-Mi.z,e.elevation=Mi.x,e.roll=Mi.y,e}getEastNorthUpAxes(i,e,t,n,r,s=uo){this.getCartographicToPosition(i,e,0,s),this.getCartographicToNormal(i,e,r),t.set(-s.y,s.x,0).normalize(),n.crossVectors(r,t).normalize()}getCartographicToPosition(i,e,t,n){this.getCartographicToNormal(i,e,dr);let r=this.radius;mi.copy(dr),mi.x*=r.x**2,mi.y*=r.y**2,mi.z*=r.z**2;let s=Math.sqrt(dr.dot(mi));return mi.divideScalar(s),n.copy(mi).addScaledVector(dr,t)}getPositionToCartographic(i,e){this.getPositionToSurfacePoint(i,mi),this.getPositionToNormal(mi,dr);let t=pf.subVectors(i,mi);return e.lon=Math.atan2(dr.y,dr.x),e.lat=Math.asin(dr.z),e.height=Math.sign(t.dot(i))*t.length(),e}getCartographicToNormal(i,e,t){return W0.set(1,TT(i),e),t.setFromSpherical(W0).normalize(),wT(t),t}getPositionToNormal(i,e){let t=this.radius;return e.copy(i),e.x/=t.x**2,e.y/=t.y**2,e.z/=t.z**2,e.normalize(),e}getPositionToSurfacePoint(i,e){let t=this.radius,n=1/t.x**2,r=1/t.y**2,s=1/t.z**2,a=i.x*i.x*n,o=i.y*i.y*r,l=i.z*i.z*s,c=a+o+l,h=Math.sqrt(1/c),u=mi.copy(i).multiplyScalar(h);if(c<AT)return isFinite(h)?e.copy(u):null;let d=pf.set(u.x*n*2,u.y*r*2,u.z*s*2),f=(1-h)*i.length()/(.5*d.length()),p=0,y,m,g,v,S,_,M,w,E,x,A;do{f-=p,g=1/(1+f*n),v=1/(1+f*r),S=1/(1+f*s),_=g*g,M=v*v,w=S*S,E=_*g,x=M*v,A=w*S,y=a*_+o*M+l*w-1,m=a*E*n+o*x*r+l*A*s;let C=-2*m;p=y/C}while(Math.abs(y)>ET);return e.set(i.x*g,i.y*v,i.z*S)}calculateHorizonDistance(i,e){let t=this.calculateEffectiveRadius(i);return Math.sqrt(2*t*e+e**2)}calculateEffectiveRadius(i){let e=this.radius.x,t=1-this.radius.z**2/e**2,n=i*ye.DEG2RAD,r=Math.sin(n)**2;return e/Math.sqrt(1-t*r)}getPositionElevation(i){this.getPositionToSurfacePoint(i,mi);let e=pf.subVectors(i,mi);return Math.sign(e.dot(i))*e.length()}closestPointToRayEstimate(i,e){return this.intersectRay(i,e)?e:(Ui.makeScale(...this.radius).invert(),Kc.copy(i).applyMatrix4(Ui),mi.set(0,0,0),Kc.closestPointToPoint(mi,e).normalize(),Ui.makeScale(...this.radius),e.applyMatrix4(Ui))}copy(i){return this.radius.copy(i.radius),this}clone(){return new this.constructor().copy(this)}},Zs=new ah(Ws,Ws,v0);Zs.name="WGS84 Earth";var Jc=new P,js=new P,Ys=new P,gf=new P,Qc=new Ot,eh=new P,$s=new ge,Y0=new ge,$0=new P,Z0=new ge,yf=new Ot,_f={};function K0(i,e,t,n){if(i=i/t*2-1,e=e/t*2-1,n.x=i,n.y=e,n.z=1-Math.abs(i)-Math.abs(e),n.z<0){let r=n.x;n.x=(1-Math.abs(n.y))*(r>=0?1:-1),n.y=(1-Math.abs(r))*(n.y>=0?1:-1)}return n.normalize(),n}var wf=class extends L0{constructor(i=or){super(),this.manager=i,this.adjustmentTransform=new ge,this.ellipsoid=Zs.clone()}resolveExternalURL(i){return this.manager.resolveURL(super.resolveExternalURL(i))}parse(i){return super.parse(i).then(e=>{let{featureTable:t,batchTable:n}=e,r=e.glbBytes.slice().buffer;return new Promise((s,a)=>{let o=this.fetchOptions,l=this.manager,c=l.getHandler("path.gltf")||new qs(l);o.credentials==="include"&&o.mode==="cors"&&c.setCrossOrigin("use-credentials"),"credentials"in o&&c.setWithCredentials(o.credentials==="include"),o.headers&&c.setRequestHeader(o.headers);let h=e.gltfWorkingPath??this.workingPath;/[\\/]$/.test(h)||(h+="/");let u=this.adjustmentTransform;c.parse(r,h,d=>{let f=t.getData("INSTANCES_LENGTH"),p=t.getData("POSITION",f,"FLOAT","VEC3"),y=t.getData("POSITION_QUANTIZED",f,"UNSIGNED_SHORT","VEC3"),m=t.getData("QUANTIZED_VOLUME_OFFSET",1,"FLOAT","VEC3"),g=t.getData("QUANTIZED_VOLUME_SCALE",1,"FLOAT","VEC3"),v=t.getData("NORMAL_UP",f,"FLOAT","VEC3"),S=t.getData("NORMAL_RIGHT",f,"FLOAT","VEC3"),_=t.getData("NORMAL_UP_OCT32P",f,"UNSIGNED_SHORT","VEC2"),M=t.getData("NORMAL_RIGHT_OCT32P",f,"UNSIGNED_SHORT","VEC2"),w=t.getData("SCALE_NON_UNIFORM",f,"FLOAT","VEC3"),E=t.getData("SCALE",f,"FLOAT","SCALAR"),x=t.getData("RTC_CENTER",1,"FLOAT","VEC3"),A=t.getData("EAST_NORTH_UP");if(!p&&y){p=new Float32Array(f*3);for(let I=0;I<f;I++)p[I*3+0]=m[0]+y[I*3+0]/65535*g[0],p[I*3+1]=m[1]+y[I*3+1]/65535*g[1],p[I*3+2]=m[2]+y[I*3+2]/65535*g[2]}let C=new P;for(let I=0;I<f;I++)C.x+=p[I*3+0]/f,C.y+=p[I*3+1]/f,C.z+=p[I*3+2]/f;let D=[],U=[];d.scene.updateMatrixWorld(),d.scene.traverse(I=>{if(I.isMesh){U.push(I);let{geometry:L,material:k}=I,H=new Cr(L,k,f);H.position.copy(C),x&&(H.position.x+=x[0],H.position.y+=x[1],H.position.z+=x[2]),D.push(H)}});for(let I=0;I<f;I++){gf.set(p[I*3+0]-C.x,p[I*3+1]-C.y,p[I*3+2]-C.z),Qc.identity(),v&&S?(js.set(v[I*3+0],v[I*3+1],v[I*3+2]),Ys.set(S[I*3+0],S[I*3+1],S[I*3+2]),Jc.crossVectors(Ys,js).normalize(),$s.makeBasis(Ys,js,Jc),Qc.setFromRotationMatrix($s)):_&&M&&(K0(_[I*2+0],_[I*2+1],65535,js),K0(M[I*2+0],M[I*2+1],65535,Ys),Jc.crossVectors(Ys,js).normalize(),$s.makeBasis(Ys,js,Jc),Qc.setFromRotationMatrix($s)),eh.set(1,1,1),w&&eh.set(w[I*3+0],w[I*3+1],w[I*3+2]),E&&eh.multiplyScalar(E[I]);for(let L=0,k=D.length;L<k;L++){let H=D[L];yf.copy(Qc),A&&(H.updateMatrixWorld(),$0.copy(gf).applyMatrix4(H.matrixWorld),this.ellipsoid.getPositionToCartographic($0,_f),this.ellipsoid.getEastNorthUpFrame(_f.lat,_f.lon,Z0),yf.setFromRotationMatrix(Z0)),$s.compose(gf,yf,eh).multiply(u);let X=U[L];Y0.multiplyMatrices($s,X.matrixWorld),H.setMatrixAt(I,Y0)}}d.scene.clear(),d.scene.add(...D),d.batchTable=n,d.featureTable=t,d.scene.batchTable=n,d.scene.featureTable=t,s(d)},a)})})}},ry=class extends N0{constructor(i=or){super(),this.manager=i,this.adjustmentTransform=new ge,this.ellipsoid=Zs.clone()}parse(i){let e=super.parse(i),{manager:t,ellipsoid:n,adjustmentTransform:r}=this,s=[];for(let a in e.tiles){let{type:o,buffer:l}=e.tiles[a];switch(o){case"b3dm":{let c=l.slice(),h=new Sf(t);h.workingPath=this.workingPath,h.fetchOptions=this.fetchOptions,h.adjustmentTransform.copy(r);let u=h.parse(c.buffer);s.push(u);break}case"pnts":{let c=l.slice(),h=new Mf(t);h.workingPath=this.workingPath,h.fetchOptions=this.fetchOptions;let u=h.parse(c.buffer);s.push(u);break}case"i3dm":{let c=l.slice(),h=new wf(t);h.workingPath=this.workingPath,h.fetchOptions=this.fetchOptions,h.ellipsoid.copy(n),h.adjustmentTransform.copy(r);let u=h.parse(c.buffer);s.push(u);break}}}return Promise.all(s).then(a=>{let o=new Xt;return a.forEach(l=>{o.add(l.scene)}),{tiles:a,scene:o}})}},fo=new ge,CT=class extends Xt{constructor(i){super(),this.isTilesGroup=!0,this.name="TilesRenderer.TilesGroup",this.tilesRenderer=i,this.matrixWorldInverse=new ge}raycast(i,e){return this.tilesRenderer.raycast(i,e),!1}updateMatrixWorld(i){if(this.matrixAutoUpdate&&this.updateMatrix(),this.matrixWorldNeedsUpdate||i){this.parent===null?fo.copy(this.matrix):fo.multiplyMatrices(this.parent.matrixWorld,this.matrix),this.matrixWorldNeedsUpdate=!1;let e=fo.elements,t=this.matrixWorld.elements,n=!1;for(let r=0;r<16;r++){let s=e[r],a=t[r];if(Math.abs(s-a)>2**-52){n=!0;break}}if(n){this.matrixWorld.copy(fo),this.matrixWorldInverse.copy(fo).invert();let r=this.children;for(let l=0,c=r.length;l<c;l++)r[l].updateMatrixWorld();let{tilesRenderer:s}=this,{activeTiles:a,visibleTiles:o}=s;a.forEach(l=>{o.has(l)||l.engineData.scene.updateMatrixWorld(!0)})}}}updateWorldMatrix(i,e){this.parent&&i&&this.parent.updateWorldMatrix(i,!1),this.updateMatrixWorld(!0)}},RT=new vi;function PT(i,e,t,n){let{scene:r}=i.engineData;t.invokeOnePlugin(s=>s.raycastTile&&s.raycastTile(i,r,e,n))||e.intersectObject(r,!0,n)}function IT(i){return"traversal"in i}function sy(i,e,t,n,r=null){if(!IT(e))return;let{group:s,activeTiles:a}=i,{boundingVolume:o}=e.engineData;if(r===null&&(r=RT,r.copy(t.ray).applyMatrix4(s.matrixWorldInverse)),!e.traversal.used||!o.intersectsRay(r))return;a.has(e)&&PT(e,t,i,n);let l=e.children;for(let c=0,h=l.length;c<h;c++)sy(i,l[c],t,n,r)}var th=new P,ih=new P,wi=new P,nh=new vi,sh=class{constructor(i=new Mt,e=new ge){this.box=i.clone(),this.transform=e.clone(),this.inverseTransform=new ge,this.points=Array(8).fill().map(()=>new P),this.planes=[,,,,,,].fill().map(()=>new qt)}copy(i){return this.box.copy(i.box),this.transform.copy(i.transform),this.update(),this}clone(){return new this.constructor().copy(this)}clampPoint(i,e){return e.copy(i).applyMatrix4(this.inverseTransform).clamp(this.box.min,this.box.max).applyMatrix4(this.transform)}distanceToPoint(i){return this.clampPoint(i,wi).distanceTo(i)}containsPoint(i){return wi.copy(i).applyMatrix4(this.inverseTransform),this.box.containsPoint(wi)}intersectsRay(i){return nh.copy(i).applyMatrix4(this.inverseTransform),nh.intersectsBox(this.box)}intersectRay(i,e){return nh.copy(i).applyMatrix4(this.inverseTransform),nh.intersectBox(this.box,e)?(e.applyMatrix4(this.transform),e):null}update(){let{points:i,inverseTransform:e,transform:t,box:n}=this;e.copy(t).invert();let{min:r,max:s}=n,a=0;for(let o=-1;o<=1;o+=2)for(let l=-1;l<=1;l+=2)for(let c=-1;c<=1;c+=2)i[a].set(o<0?r.x:s.x,l<0?r.y:s.y,c<0?r.z:s.z).applyMatrix4(t),a++;this.updatePlanes()}updatePlanes(){th.copy(this.box.min).applyMatrix4(this.transform),ih.copy(this.box.max).applyMatrix4(this.transform),wi.set(0,0,1).transformDirection(this.transform),this.planes[0].setFromNormalAndCoplanarPoint(wi,th),this.planes[1].setFromNormalAndCoplanarPoint(wi,ih).negate(),wi.set(0,1,0).transformDirection(this.transform),this.planes[2].setFromNormalAndCoplanarPoint(wi,th),this.planes[3].setFromNormalAndCoplanarPoint(wi,ih).negate(),wi.set(1,0,0).transformDirection(this.transform),this.planes[4].setFromNormalAndCoplanarPoint(wi,th),this.planes[5].setFromNormalAndCoplanarPoint(wi,ih).negate()}intersectsSphere(i){return this.clampPoint(i.center,wi),wi.distanceToSquared(i.center)<=i.radius*i.radius}intersectsFrustum(i){return this._intersectsPlaneShape(i.planes,i.points)}intersectsOBB(i){return this._intersectsPlaneShape(i.planes,i.points)}_intersectsPlaneShape(i,e){let t=this.points,n=this.planes;for(let r=0;r<6;r++){let s=i[r],a=-1/0;for(let o=0;o<8;o++){let l=t[o],c=s.distanceToPoint(l);a=a<c?c:a}if(a<0)return!1}for(let r=0;r<6;r++){let s=n[r],a=-1/0;for(let o=0;o<8;o++){let l=e[o],c=s.distanceToPoint(l);a=a<c?c:a}if(a<0)return!1}return!0}},go=Math.PI,xf=go/2,po=new P,$r=new P,Yi=new P,ke=new P,gi=new ge,LT=new Mt,J0=new ge;function fr(i,e){e.radius=Math.max(e.radius,i.distanceToSquared(e.center))}function Q0(i){return i.x!==i.y}var Tf=class extends ah{constructor(i=1,e=1,t=1,n=-xf,r=xf,s=0,a=2*go,o=0,l=0){super(i,e,t),this.latStart=n,this.latEnd=r,this.lonStart=s,this.lonEnd=a,this.heightStart=o,this.heightEnd=l}getBoundingBox(i,e){Q0(this.radius)&&console.warn("EllipsoidRegion: Triaxial ellipsoids are not supported.");let{latStart:t,latEnd:n,lonStart:r,lonEnd:s,heightStart:a,heightEnd:o}=this,l=(t+n)*.5,c=(r+s)*.5,h=t>0,u=n<0,d;d=h?t:u?n:0;let{min:f,max:p}=i;f.setScalar(1/0),p.setScalar(-1/0),s-r<=go?(this.getCartographicToNormal(l,c,Yi),$r.set(0,0,1),po.crossVectors($r,Yi).normalize(),$r.crossVectors(Yi,po).normalize(),e.makeBasis(po,$r,Yi),gi.copy(e).invert(),this.getCartographicToPosition(d,r,o,ke).applyMatrix4(gi),p.x=Math.abs(ke.x),f.x=-p.x,this.getCartographicToPosition(n,r,o,ke).applyMatrix4(gi),p.y=ke.y,this.getCartographicToPosition(n,c,o,ke).applyMatrix4(gi),p.y=Math.max(ke.y,p.y),this.getCartographicToPosition(t,r,o,ke).applyMatrix4(gi),f.y=ke.y,this.getCartographicToPosition(t,c,o,ke).applyMatrix4(gi),f.y=Math.min(ke.y,f.y),this.getCartographicToPosition(l,c,o,ke).applyMatrix4(gi),p.z=ke.z,this.getCartographicToPosition(t,r,a,ke).applyMatrix4(gi),f.z=ke.z,this.getCartographicToPosition(n,r,a,ke).applyMatrix4(gi),f.z=Math.min(ke.z,f.z)):(this.getCartographicToPosition(d,c,o,Yi),Yi.z=0,Yi.length()<1e-10?Yi.set(1,0,0):Yi.normalize(),$r.set(0,0,1),po.crossVectors(Yi,$r).normalize(),e.makeBasis(po,$r,Yi),gi.copy(e).invert(),this.getCartographicToPosition(d,c+xf,o,ke).applyMatrix4(gi),p.x=Math.abs(ke.x),f.x=-p.x,this.getCartographicToPosition(n,0,u?a:o,ke).applyMatrix4(gi),p.y=ke.y,this.getCartographicToPosition(t,0,h?a:o,ke).applyMatrix4(gi),f.y=ke.y,this.getCartographicToPosition(d,c,o,ke).applyMatrix4(gi),p.z=ke.z,this.getCartographicToPosition(d,s,o,ke).applyMatrix4(gi),f.z=ke.z),i.getCenter(ke),i.min.sub(ke).multiplyScalar(1.0000000000001),i.max.sub(ke).multiplyScalar(1.0000000000001),ke.applyMatrix4(e),e.setPosition(ke)}getBoundingSphere(i){Q0(this.radius)&&console.warn("EllipsoidRegion: Triaxial ellipsoids are not supported."),this.getBoundingBox(LT,J0),i.center.setFromMatrixPosition(J0),i.radius=0;let{latStart:e,latEnd:t,lonStart:n,lonEnd:r,heightStart:s,heightEnd:a}=this,o=(e+t)*.5,l=(n+r)*.5,c=e>0,h=t<0,u;u=c?e:h?t:0,this.getCartographicToPosition(u,n,a,ke),fr(ke,i),this.getCartographicToPosition(t,n,a,ke),fr(ke,i),this.getCartographicToPosition(t,l,a,ke),fr(ke,i),this.getCartographicToPosition(e,n,a,ke),fr(ke,i),this.getCartographicToPosition(e,l,a,ke),fr(ke,i),this.getCartographicToPosition(o,l,a,ke),fr(ke,i),this.getCartographicToPosition(e,n,s,ke),fr(ke,i),r-n>go&&(this.getCartographicToPosition(u,l+go,a,ke),fr(ke,i)),i.radius=Math.sqrt(i.radius)*1.0000000000001}},On=new P,Fn=new P,Bn=new P,ey=new P,ty=new P,DT=class{constructor(){this.sphere=null,this.obb=null,this.region=null,this.regionObb=null}intersectsRay(i){let e=this.sphere,t=this.obb||this.regionObb;return!(e&&!i.intersectsSphere(e)||t&&!t.intersectsRay(i))}intersectRay(i,e=null){let t=this.sphere,n=this.obb||this.regionObb,r=-1/0,s=-1/0;t&&i.intersectSphere(t,ey)&&(r=t.containsPoint(i.origin)?0:i.origin.distanceToSquared(ey)),n&&n.intersectRay(i,ty)&&(s=n.containsPoint(i.origin)?0:i.origin.distanceToSquared(ty));let a=Math.max(r,s);return a===-1/0?null:(i.at(Math.sqrt(a),e),e)}distanceToPoint(i){let e=this.sphere,t=this.obb||this.regionObb,n=-1/0,r=-1/0;return e&&(n=Math.max(e.distanceToPoint(i),0)),t&&(r=t.distanceToPoint(i)),n>r?n:r}intersectsFrustum(i){let e=this.obb||this.regionObb,t=this.sphere;return t&&!i.intersectsSphere(t)||e&&!e.intersectsFrustum(i)?!1:!!(t||e)}intersectsSphere(i){let e=this.obb||this.regionObb,t=this.sphere;return t&&!t.intersectsSphere(i)||e&&!e.intersectsSphere(i)?!1:!!(t||e)}intersectsOBB(i){let e=this.obb||this.regionObb,t=this.sphere;return t&&!i.intersectsSphere(t)||e&&!e.intersectsOBB(i)?!1:!!(t||e)}getOBB(i,e){let t=this.obb||this.regionObb;t?(i.copy(t.box),e.copy(t.transform)):(this.getAABB(i),e.identity())}getAABB(i){if(this.sphere)this.sphere.getBoundingBox(i);else{let e=this.obb||this.regionObb;i.copy(e.box).applyMatrix4(e.transform)}}getSphere(i){if(this.sphere)i.copy(this.sphere);else if(this.region)this.region.getBoundingSphere(i);else{let e=this.obb||this.regionObb;e.box.getBoundingSphere(i),i.applyMatrix4(e.transform)}}setObbData(i,e){let t=new sh;On.set(i[3],i[4],i[5]),Fn.set(i[6],i[7],i[8]),Bn.set(i[9],i[10],i[11]);let n=On.length(),r=Fn.length(),s=Bn.length();On.normalize(),Fn.normalize(),Bn.normalize(),n===0&&On.crossVectors(Fn,Bn),r===0&&Fn.crossVectors(On,Bn),s===0&&Bn.crossVectors(On,Fn),t.transform.set(On.x,Fn.x,Bn.x,i[0],On.y,Fn.y,Bn.y,i[1],On.z,Fn.z,Bn.z,i[2],0,0,0,1).premultiply(e),t.box.min.set(-n,-r,-s),t.box.max.set(n,r,s),t.update(),this.obb=t}setSphereData(i,e,t,n,r){let s=new Et;s.center.set(i,e,t),s.radius=n,s.applyMatrix4(r),this.sphere=s}setRegionData(i,e,t,n,r,s,a){let o=new Tf(...i.radius,t,r,e,n,s,a),l=new sh;o.getBoundingBox(l.box,l.transform),l.update(),this.region=o,this.regionObb=l}},NT=new Oe;function UT(i,e,t,n){let r=NT.set(i.normal.x,i.normal.y,i.normal.z,e.normal.x,e.normal.y,e.normal.z,t.normal.x,t.normal.y,t.normal.z);return n.set(-i.constant,-e.constant,-t.constant),n.applyMatrix3(r.invert()),n}var OT=class extends wn{constructor(){super(),this.points=Array(8).fill().map(()=>new P)}setFromProjectionMatrix(...i){return super.setFromProjectionMatrix(...i),this.calculateFrustumPoints(),this}calculateFrustumPoints(){let{planes:i,points:e}=this;[[i[0],i[3],i[4]],[i[1],i[3],i[4]],[i[0],i[2],i[4]],[i[1],i[2],i[4]],[i[0],i[3],i[5]],[i[1],i[3],i[5]],[i[0],i[2],i[5]],[i[1],i[2],i[5]]].forEach((t,n)=>{UT(t[0],t[1],t[2],e[n])})}};var bf=0;function iy(i,e,t,n){try{return Fr.getByteLength(i,e,t,n)}catch{return bf}}function Ef(i){if(!i)return 0;if(i.isExternalTexture)return i.userData?.byteLength??bf;let{format:e,type:t,image:n,mipmaps:r}=i;if(i.isCompressedTexture&&Array.isArray(r)&&r.length>0){let a=0;for(let o of r)o?.data?.byteLength?a+=o.data.byteLength:a+=iy(o.width,o.height,e,t);return a}if(!n)return bf;let s=iy(n.width,n.height,e,t);return s*=i.generateMipmaps?4/3:1,s}function FT(i){let e=new Set,t=0;return i.traverse(n=>{if(n.geometry&&!e.has(n.geometry)&&(t+=U0(n.geometry),e.add(n.geometry)),n.material){let r=n.material;for(let s in r){let a=r[s];a&&a.isTexture&&!e.has(a)&&(t+=Ef(a),e.add(a))}}}),t}var ay=Symbol("INITIAL_FRUSTUM_CULLED"),rh=new ge,mo=new P,vf=new Se,BT=new P(1,0,0),kT=new P(0,1,0),zT=()=>null;function ny(i,e){i.traverse(t=>{t.frustumCulled=t[ay]&&e})}var Af=class extends C0{get autoDisableRendererCulling(){return this._autoDisableRendererCulling}set autoDisableRendererCulling(i){this._autoDisableRendererCulling!==i&&(super._autoDisableRendererCulling=i,this.forEachLoadedModel(e=>{ny(e,!i)}))}constructor(...i){super(...i),this.accelerateRaycast=!0,this.group=new CT(this),this.ellipsoid=Zs.clone(),this.surface=this.ellipsoid,this.cameras=[],this.cameraMap=new Map,this.cameraInfo=[],this._upRotationMatrix=new ge,this._bytesUsed=new WeakMap,this._autoDisableRendererCulling=!0,this.manager=new Rs,this._listeners={}}addEventListener(i,e){jt.prototype.addEventListener.call(this,i,e)}hasEventListener(i,e){return jt.prototype.hasEventListener.call(this,i,e)}removeEventListener(i,e){jt.prototype.removeEventListener.call(this,i,e)}dispatchEvent(i){jt.prototype.dispatchEvent.call(this,i)}getBoundingBox(i){if(!this.root)return!1;let e=this.root.engineData.boundingVolume;return e?(e.getAABB(i),!0):!1}getOrientedBoundingBox(i,e){if(!this.root)return!1;let t=this.root.engineData.boundingVolume;return t?(t.getOBB(i,e),!0):!1}getBoundingSphere(i){if(!this.root)return!1;let e=this.root.engineData.boundingVolume;return e?(e.getSphere(i),!0):!1}forEachLoadedModel(i){this.traverse(e=>{let t=e.engineData&&e.engineData.scene;t&&i(t,e)},null,!1)}raycast(i,e){if(this.root)if(this.accelerateRaycast)sy(this,this.root,i,e);else{let t=i.firstHitOnly?[]:e;for(let n of this.activeTiles){let{scene:r}=n.engineData;this.invokeOnePlugin(s=>s.raycastTile&&s.raycastTile(n,r,i,t))||i.intersectObject(r,!0,t)}i.firstHitOnly&&t.length>0&&(t.sort((n,r)=>n.distance-r.distance),e.push(t[0]))}}hasCamera(i){return this.cameraMap.has(i)}setCamera(i){let e=this.cameras,t=this.cameraMap;return t.has(i)?!1:(t.set(i,new Se),e.push(i),this.dispatchEvent({type:"add-camera",camera:i}),!0)}setResolution(i,e,t){let n=this.cameraMap;if(!n.has(i))return!1;let r=e.isVector2?e.x:e,s=e.isVector2?e.y:t,a=n.get(i);return(a.width!==r||a.height!==s)&&(a.set(r,s),this.dispatchEvent({type:"camera-resolution-change"})),!0}getResolution(i,e){let t=this.cameraMap.get(i);return t?e.copy(t):null}setResolutionFromRenderer(i,e){return e.getSize(vf),this.setResolution(i,vf.x,vf.y)}deleteCamera(i){let e=this.cameras,t=this.cameraMap;if(t.has(i)){let n=e.indexOf(i);return e.splice(n,1),t.delete(i),this.dispatchEvent({type:"delete-camera",camera:i}),!0}return!1}loadRootTileset(...i){return super.loadRootTileset(...i).then(e=>{let{asset:t,extensions:n={}}=e;switch((t&&t.gltfUpAxis||"y").toLowerCase()){case"x":this._upRotationMatrix.makeRotationAxis(kT,-Math.PI/2);break;case"y":this._upRotationMatrix.makeRotationAxis(BT,Math.PI/2);break}if("3DTILES_ellipsoid"in n){let r=n["3DTILES_ellipsoid"],{ellipsoid:s}=this;s.name=r.body,r.radii?s.radius.set(...r.radii):s.radius.set(1,1,1)}return e})}prepareForTraversal(){let i=this.group,e=this.cameras,t=this.cameraMap,n=this.cameraInfo;for(;n.length>e.length;)n.pop();for(;n.length<e.length;)n.push({frustum:new OT,isOrthographic:!1,sseDenominator:-1,position:new P,invScale:-1,pixelSize:0});mo.setFromMatrixScale(i.matrixWorldInverse),Math.abs(Math.max(mo.x-mo.y,mo.x-mo.z))>1e-6&&console.warn("ThreeTilesRenderer : Non uniform scale used for tile which may cause issues when calculating screen space error.");for(let r=0,s=n.length;r<s;r++){let a=e[r],o=n[r],l=o.frustum,c=o.position,h=t.get(a);(h.width===0||h.height===0)&&console.warn("TilesRenderer: resolution for camera error calculation is not set.");let u=a.projectionMatrix.elements;if(o.isOrthographic=u[15]===1,o.isOrthographic){let d=2/u[0],f=2/u[5];o.pixelSize=Math.max(f/h.height,d/h.width)}else o.sseDenominator=2/u[5]/h.height;rh.copy(i.matrixWorld),rh.premultiply(a.matrixWorldInverse),rh.premultiply(a.projectionMatrix),l.setFromProjectionMatrix(rh,a.coordinateSystem,a.reversedDepth),c.set(0,0,0),c.applyMatrix4(a.matrixWorld),c.applyMatrix4(i.matrixWorldInverse)}}update(){if(super.update(),this.cameras.length===0&&this.root){let i=!1;this.invokeAllPlugins(e=>i||(i=!!(e!==this&&e.calculateTileViewError))),i===!1&&console.warn("TilesRenderer: no cameras defined. Cannot update 3d tiles.")}}preprocessNode(i,e,t=null){super.preprocessNode(i,e,t);let n=new ge;if(i.transform){let a=i.transform;for(let o=0;o<16;o++)n.elements[o]=a[o]}t&&n.premultiply(t.engineData.transform);let r=new ge().copy(n).invert(),s=new DT;"sphere"in i.boundingVolume&&s.setSphereData(...i.boundingVolume.sphere,n),"box"in i.boundingVolume&&s.setObbData(i.boundingVolume.box,n),"region"in i.boundingVolume&&s.setRegionData(this.ellipsoid,...i.boundingVolume.region),i.engineData.transform=n,i.engineData.transformInverse=r,i.engineData.boundingVolume=s,i.engineData.geometry=null,i.engineData.materials=null,i.engineData.textures=null,i.toJSON=zT}async parseTile(i,e,t,n,r){let s=e.engineData,a=jc(n),o=this.fetchOptions,l=this.manager,c=null,h=s.transform,u=this._upRotationMatrix,d=(qr(i)||t).toLowerCase();switch(d){case"b3dm":{let S=new Sf(l);S.workingPath=a,S.fetchOptions=o,S.adjustmentTransform.copy(u),c=S.parse(i);break}case"pnts":{let S=new Mf(l);S.workingPath=a,S.fetchOptions=o,c=S.parse(i);break}case"i3dm":{let S=new wf(l);S.workingPath=a,S.fetchOptions=o,S.adjustmentTransform.copy(u),S.ellipsoid.copy(this.ellipsoid),c=S.parse(i);break}case"cmpt":{let S=new ry(l);S.workingPath=a,S.fetchOptions=o,S.adjustmentTransform.copy(u),S.ellipsoid.copy(this.ellipsoid),c=S.parse(i).then(_=>_.scene);break}case"gltf":case"glb":{let S=l.getHandler("path.gltf")||l.getHandler("path.glb")||new qs(l);S.setWithCredentials(o.credentials==="include"),S.setRequestHeader(o.headers||{}),o.credentials==="include"&&o.mode==="cors"&&S.setCrossOrigin("use-credentials");let _=S.resourcePath||S.path||a;!/[\\/]$/.test(_)&&_.length&&(_+="/"),c=S.parseAsync(i,_).then(M=>{M.scene=M.scene||new Xt;let{scene:w}=M;return w.updateMatrix(),w.matrix.multiply(u).decompose(w.position,w.quaternion,w.scale),M});break}default:c=this.invokeOnePlugin(S=>S.parseToMesh&&S.parseToMesh(i,e,t,n,r));break}let f=await c;if(f===null)throw Error(`TilesRenderer: Content type "${d}" not supported.`);let p,y;f.isObject3D?(p=f,y=null):(p=f.scene,y=f),p.updateMatrix(),p.matrix.premultiply(h),p.matrix.decompose(p.position,p.quaternion,p.scale),await this.invokeAllPlugins(S=>S.processTileModel&&S.processTileModel(p,e)),p.traverse(S=>{S[ay]=S.frustumCulled,S.userData.tile=e}),ny(p,!this.autoDisableRendererCulling);let m=[],g=[],v=[];if(p.traverse(S=>{if(S.geometry&&g.push(S.geometry),S.material){let _=S.material;m.push(S.material);for(let M in _){let w=_[M];w&&w.isTexture&&v.push(w)}}}),r.aborted){for(let S=0,_=v.length;S<_;S++){let M=v[S];M.image instanceof ImageBitmap&&M.image.close(),M.dispose()}return}s.materials=m,s.geometry=g,s.textures=v,s.scene=p,s.metadata=y}disposeTile(i){super.disposeTile(i);let e=i.engineData;if(e.scene){let t=e.materials,n=e.geometry,r=e.textures,s=e.scene.parent;e.scene.traverse(a=>{a.userData.meshFeatures&&a.userData.meshFeatures.dispose(),a.userData.structuralMetadata&&a.userData.structuralMetadata.dispose()});for(let a=0,o=n.length;a<o;a++)n[a].dispose();for(let a=0,o=t.length;a<o;a++)t[a].dispose();for(let a=0,o=r.length;a<o;a++){let l=r[a];l.image instanceof ImageBitmap&&l.image.close(),l.dispose()}s&&s.remove(e.scene),e.scene=null,e.materials=null,e.textures=null,e.geometry=null,e.metadata=null}}setTileActive(i,e){super.setTileActive(i,e);let t=i.engineData.scene;t&&(e?(t.parent=this.group,t.updateMatrixWorld(!0)):this.visibleTiles.has(i)||(t.parent=null))}setTileVisible(i,e){let t=i.engineData.scene,{activeTiles:n,group:r}=this;t&&(e?r.add(t):(r.remove(t),n.has(i)&&(t.parent=r))),super.setTileVisible(i,e)}calculateBytesUsed(i,e){let t=this._bytesUsed;return!t.has(i)&&e&&t.set(i,FT(e)),t.get(i)??null}calculateTileViewError(i,e){let t=i.engineData,n=this.cameras,r=this.cameraInfo,s=t.boundingVolume,a=!1,o=0,l=1/0,c=0,h=1/0;for(let u=0,d=n.length;u<d;u++){let f=r[u],p,y;if(f.isOrthographic){let g=f.pixelSize;p=i.geometricError/g,y=1/0}else{let g=f.sseDenominator;y=s.distanceToPoint(f.position),p=y===0?1/0:i.geometricError/(y*g)}let m=r[u].frustum;s.intersectsFrustum(m)&&(a=!0,o=Math.max(o,p),l=Math.min(l,y)),c=Math.max(c,p),h=Math.min(h,y)}a?(e.inView=!0,e.error=o,e.distanceFromCamera=l):(e.inView=!1,e.error=c,e.distanceFromCamera=h)}dispose(){super.dispose(),this.group.removeFromParent()}};var VT=new Wi(-1,1,1,-1,0,1),Cf=class extends ht{constructor(){super(),this.setAttribute("position",new st([-1,3,0,-1,-1,0,3,-1,0],3)),this.setAttribute("uv",new st([0,2,0,0,2,0],2))}},GT=new Cf,oh=class{constructor(e){this._mesh=new at(GT,e)}dispose(){this._mesh.geometry.dispose()}render(e){e.render(this._mesh,VT)}get material(){return this._mesh.material}set material(e){this._mesh.material=e}};var Rf=new P,lh=new P;function HT(i,e,t){let n=1e-5,r=t+n,s=e+n;Math.abs(s)>Math.PI/2&&(s-=n),i.getCartographicToPosition(e,t,0,Rf),i.getCartographicToPosition(s,t,0,lh);let a=Rf.distanceTo(lh)/n;return i.getCartographicToPosition(e,r,0,lh),[Rf.distanceTo(lh)/n,a]}var ch=1e-5,bo=1.340264,So=-.081106,Mo=893e-6,wo=.003796,Sh=Math.sqrt(3)/2,WT=1e-12,XT=12;function kf(i,e,t){let n=Math.asin(Sh*Math.sin(e)),r=n*n,s=r*r*r;return t[0]=i*Math.cos(n)/(Sh*(bo+3*So*r+s*(7*Mo+9*wo*r))),t[1]=n*(bo+So*r+s*(Mo+wo*r)),t}function qT(i,e,t){let n=e,r=n*n,s=r*r*r;for(let a=0;a<XT;a++){let o=(n*(bo+So*r+s*(Mo+wo*r))-e)/(bo+3*So*r+s*(7*Mo+9*wo*r));if(n-=o,r=n*n,s=r*r*r,Math.abs(o)<WT)break}return t[0]=Sh*i*(bo+3*So*r+s*(7*Mo+9*wo*r))/Math.cos(n),t[1]=Math.asin(Math.sin(n)/Sh),t}var yo=kf(Math.PI,0,[0,0])[0],_o=kf(0,Math.PI/2,[0,0])[1],hh=[0,0],uh=[0,0],To=class{get isMercator(){return this.scheme==="EPSG:3857"}get isCartographic(){return this.scheme!=="none"}constructor(i="EPSG:4326"){this.scheme=i,this.tileCountX=1,this.tileCountY=1,this.setScheme(i)}setScheme(i){switch(this.scheme=i,i){case"CRS:84":case"EPSG:4326":this.tileCountX=2,this.tileCountY=1;break;case"EPSG:3857":this.tileCountX=1,this.tileCountY=1;break;case"EPSG:8857":this.tileCountX=1,this.tileCountY=1;break;case"none":this.tileCountX=1,this.tileCountY=1;break;default:throw Error(`ProjectionScheme: Unknown projection scheme "${i}"`)}}getDerivativeAtNormalizedPoint(i,e,t=[0,0]){let n=Math.max(i-ch,0),r=Math.min(i+ch,1),s=Math.max(e-ch,0),a=Math.min(e+ch,1),o=this.fromNormalizedToCartographic(n,e,uh)[0],l=this.fromNormalizedToCartographic(r,e,uh)[0];t[0]=Math.abs(l-o)/(r-n);let c=this.fromNormalizedToCartographic(i,s,uh)[1],h=this.fromNormalizedToCartographic(i,a,uh)[1];return t[1]=Math.abs(h-c)/(a-s),t}getBounds(){return this.scheme==="none"?[0,0,1,1]:[this.fromNormalizedToCartographic(0,.5,hh)[0],this.fromNormalizedToCartographic(.5,0,hh)[1],this.fromNormalizedToCartographic(1,.5,hh)[0],this.fromNormalizedToCartographic(.5,1,hh)[1]]}fromCartographicToNormalized(i,e,t=[0,0]){switch(this.scheme){case"none":t[0]=i,t[1]=e;break;case"EPSG:3857":{let n=Math.log(Math.tan(Math.PI/4+e/2));t[0]=(i+Math.PI)/(2*Math.PI),t[1]=1/2+1*n/(2*Math.PI);break}case"EPSG:8857":kf(i,e,t),t[0]=ye.mapLinear(t[0],-yo,yo,0,1),t[1]=ye.mapLinear(t[1],-_o,_o,0,1);break;default:t[0]=(i+Math.PI)/(2*Math.PI),t[1]=ye.mapLinear(e,-Math.PI/2,Math.PI/2,0,1)}return t}fromCartographicToNormalizedRange(i){return[...this.fromCartographicToNormalized(i[0],i[1]),...this.fromCartographicToNormalized(i[2],i[3])]}fromNormalizedToCartographic(i,e,t=[0,0]){switch(this.scheme){case"none":t[0]=i,t[1]=e;break;case"EPSG:3857":{let n=ye.mapLinear(e,0,1,-1,1);t[0]=ye.mapLinear(i,0,1,-Math.PI,Math.PI),t[1]=2*Math.atan(Math.exp(n*Math.PI))-Math.PI/2;break}case"EPSG:8857":qT(ye.mapLinear(i,0,1,-yo,yo),ye.mapLinear(e,0,1,-_o,_o),t);break;default:t[0]=ye.mapLinear(i,0,1,-Math.PI,Math.PI),t[1]=ye.mapLinear(e,0,1,-Math.PI/2,Math.PI/2)}return t}fromNormalizedToCartographicRange(i){return[...this.fromNormalizedToCartographic(i[0],i[1]),...this.fromNormalizedToCartographic(i[2],i[3])]}getProjectedExtents(){switch(this.scheme){case"EPSG:3857":return[2*Math.PI,2*Math.PI];case"EPSG:8857":return[2*yo,2*_o];case"none":return[1,1];default:return[2*Math.PI,Math.PI]}}clampToBounds(i,e=!1){let t=[...i],n;n=e?[0,0,1,1]:this.getBounds();let[r,s,a,o]=n;return t[0]=ye.clamp(t[0],r,a),t[2]=ye.clamp(t[2],r,a),t[1]=ye.clamp(t[1],s,o),t[3]=ye.clamp(t[3],s,o),t}},jT=[0,0];function Pf(i,e){let[t,n,r,s]=i,[a,o,l,c]=e;return!(t>=l||r<=a||n>=c||s<=o)}var YT=class{get levelCount(){return this._levels.length}get maxLevel(){return this.levelCount-1}get minLevel(){let i=this._levels;for(let e=0;e<i.length;e++)if(i[e]!==null)return e;return-1}get contentBounds(){return this._contentBounds??this.projection.getBounds()}get aspectRatio(){let{pixelWidth:i,pixelHeight:e}=this.getLevel(this.maxLevel);return i/e}constructor(){this.flipY=!1,this.pixelOverlap=0,this._contentBounds=null,this.projection=new To("none"),this._levels=[]}setLevel(i,e={}){let t=this._levels;for(;t.length<i;)t.push(null);let{tileSplitX:n=2,tileSplitY:r=2}=e,{tilePixelWidth:s=256,tilePixelHeight:a=256,tileCountX:o=n**i,tileCountY:l=r**i,tileBounds:c=null}=e,{pixelWidth:h=s*o,pixelHeight:u=a*l}=e;t[i]={tilePixelWidth:s,tilePixelHeight:a,pixelWidth:h,pixelHeight:u,tileCountX:o,tileCountY:l,tileSplitX:n,tileSplitY:r,tileBounds:c}}generateLevels(i,e,t,n={}){let{minLevel:r=0,tilePixelWidth:s=256,tilePixelHeight:a=256}=n,o=i-1,{pixelWidth:l=s*e*2**o,pixelHeight:c=a*t*2**o}=n;for(let h=r;h<i;h++){let u=i-h-1,d=Math.ceil(l*2**-u),f=Math.ceil(c*2**-u),p=Math.ceil(d/s),y=Math.ceil(f/a);this.setLevel(h,{tilePixelWidth:s,tilePixelHeight:a,pixelWidth:d,pixelHeight:f,tileCountX:p,tileCountY:y})}}getLevel(i){return this._levels[i]}setContentBounds(i,e,t,n){this._contentBounds=[i,e,t,n]}setProjection(i){this.projection=i}getTileAtPoint(i,e,t,n=!1){let{flipY:r}=this,{tileCountY:s,tileBounds:a,pixelHeight:o,pixelWidth:l,tilePixelHeight:c,tilePixelWidth:h}=this.getLevel(t),u=h/l,d=c/o;if(n||([i,e]=this.fromCartographicToNormalized(i,e,jT)),a){let y=this.fromCartographicToNormalizedRange(a);i=ye.mapLinear(i,y[0],y[2],0,1),e=ye.mapLinear(e,y[1],y[3],0,1)}let f=Math.floor(i/u),p=Math.floor(e/d);return r&&(p=s-1-p),[f,p]}getTilesInRange(i,e,t,n,r,s=!1){let a=[i,e,t,n],o=this.getContentBounds(s),l=this.getLevel(r).tileBounds;if(!Pf(a,o)||l&&(s&&(l=this.fromCartographicToNormalizedRange(l)),!Pf(a,l)))return[0,0,-1,-1];let[c,h,u,d]=this.clampToContentBounds(a,s),f=this.getTileAtPoint(c,h,r,s),p=this.getTileAtPoint(u,d,r,s);this.flipY&&([f[1],p[1]]=[p[1],f[1]]);let{tileCountX:y,tileCountY:m}=this.getLevel(r),[g,v]=f,[S,_]=p;return S<0||_<0||g>=y||v>=m?[0,0,-1,-1]:[ye.clamp(g,0,y-1),ye.clamp(v,0,m-1),ye.clamp(S,0,y-1),ye.clamp(_,0,m-1)]}getTileExists(i,e,t){let n=this.getTileBounds(i,e,t),[r,s,a,o]=n;return!(r>=a||s>=o)&&Pf(n,this.contentBounds)}getContentBounds(i=!1){return i?this.fromCartographicToNormalizedRange(this.contentBounds):[...this.contentBounds]}getTileContentUVBounds(i,e,t){let[n,r,s,a]=this.getTileBounds(i,e,t,!0,!0),[o,l,c,h]=this.getTileBounds(i,e,t,!0,!1);return[ye.mapLinear(n,o,c,0,1),ye.mapLinear(r,l,h,0,1),ye.mapLinear(s,o,c,0,1),ye.mapLinear(a,l,h,0,1)]}getTileBounds(i,e,t,n=!1,r=!0){let{flipY:s,pixelOverlap:a}=this,{tilePixelWidth:o,tilePixelHeight:l,pixelWidth:c,pixelHeight:h,tileBounds:u}=this.getLevel(t),d=o*i-a,f=l*e-a,p=d+o+a*2,y=f+l+a*2;if(d=Math.max(d,0),f=Math.max(f,0),p=Math.min(p,c),y=Math.min(y,h),d/=c,p/=c,f/=h,y/=h,s){let g=(y-f)/2,v=1-(f+y)/2;f=v-g,y=v+g}let m=[d,f,p,y];if(u){let g=this.fromCartographicToNormalizedRange(u);m[0]=ye.mapLinear(m[0],0,1,g[0],g[2]),m[2]=ye.mapLinear(m[2],0,1,g[0],g[2]),m[1]=ye.mapLinear(m[1],0,1,g[1],g[3]),m[3]=ye.mapLinear(m[3],0,1,g[1],g[3])}return r&&(m=this.clampToBounds(m,!0)),n||(m=this.fromNormalizedToCartographicRange(m)),m}fromCartographicToNormalized(i,e,t){return this.projection.fromCartographicToNormalized(i,e,t)}fromCartographicToNormalizedRange(i){return this.projection.fromCartographicToNormalizedRange(i)}fromNormalizedToCartographic(i,e,t){return this.projection.fromNormalizedToCartographic(i,e,t)}fromNormalizedToCartographicRange(i){return this.projection.fromNormalizedToCartographicRange(i)}clampToContentBounds(i,e=!1){let t=[...i],[n,r,s,a]=this.getContentBounds(e);return t[0]=ye.clamp(t[0],n,s),t[1]=ye.clamp(t[1],r,a),t[2]=ye.clamp(t[2],n,s),t[3]=ye.clamp(t[3],r,a),t}clampToBounds(i,e=!1){return this.projection.clampToBounds(i,e)}},oy=[0,0],$T=class{constructor(i=new To){this.isProjectedSurface=!0,this.projection=i,this.scale=new Se(1,1),this.offset=new Se(0,0)}getCartographicToPosition(i,e,t,n){let{projection:r}=this;if(!r.isCartographic)throw Error("ProjectedSurface: The projection is not cartographic.");let[s,a]=r.fromCartographicToNormalized(e,i,oy);return this.getNormalizedToPosition(s,a,t,n)}getPositionToCartographic(i,e){let{projection:t,scale:n,offset:r}=this;if(!t.isCartographic)throw Error("ProjectedSurface: The projection is not cartographic.");let s=(i.x-r.x)/n.x,a=(i.y-r.y)/n.y,[o,l]=t.fromNormalizedToCartographic(s,a,oy);return e.lon=o,e.lat=l,e.height=i.z,e}getNormalizedToPosition(i,e,t,n){let{scale:r,offset:s}=this;return n.set(i*r.x+s.x,e*r.y+s.y,t)}getCartographicToNormal(i,e,t){return t.set(0,0,1)}getPositionToNormal(i,e){return e.set(0,0,1)}};var ly=class extends DOMException{constructor(){super("DataCache: Item removed","AbortError")}};function xo(...i){return i.join("_")}var zf=class{constructor(){this.cache={},this.count=0,this.cachedBytes=0,this.active=0}fetchItem(i,e){}disposeItem(i,e){}getMemoryUsage(i){return 0}setData(...i){let{cache:e}=this,t=i.pop(),n=xo(...i);if(n in e)throw Error(`DataCache: "${n}" is already present.`);return this.cache[n]={abortController:new AbortController,result:t,count:1,bytes:this.getMemoryUsage(t)},this.count++,this.cachedBytes+=this.cache[n].bytes,t}lock(...i){let{cache:e}=this,t=xo(...i);if(t in e)e[t].count++;else{let n=new AbortController,r={abortController:n,result:null,count:1,bytes:0,args:i};this.active++,r.result=this.fetchItem(i,n.signal),r.result instanceof Promise?r.result=r.result.then(s=>(n.signal.throwIfAborted(),r.result=s,r.bytes=this.getMemoryUsage(s),this.cachedBytes+=r.bytes,s)).finally(()=>{this.active--}):(this.active--,r.bytes=this.getMemoryUsage(r.result),this.cachedBytes+=r.bytes),this.cache[t]=r,this.count++}return e[t].result}release(...i){let e=xo(...i);this.releaseViaFullKey(e)}get(...i){let{cache:e}=this,t=xo(...i);return t in e&&e[t].count>0?e[t].result:null}has(...i){let{cache:e}=this;return xo(...i)in e}forEachItem(i){let{cache:e}=this;for(let t in e){let n=e[t];n.result instanceof Promise||i(n.result,n.args)}}dispose(){let{cache:i}=this;for(let e in i){let{abortController:t}=i[e];t.abort(new ly),this.releaseViaFullKey(e,!0)}this.cache={}}releaseViaFullKey(i,e=!1){let{cache:t}=this;if(i in t&&t[i].count>0){let n=t[i];if(n.count--,n.count===0||e){let r=()=>{if(t[i]!==n)return;let{result:s,abortController:a}=n;a.abort(new ly),s instanceof Promise?s.then(o=>{this.disposeItem(o,n.args)}).catch(()=>{this.disposeItem(null,n.args)}).finally(()=>{this.count--,this.cachedBytes-=n.bytes}):(this.disposeItem(s,n.args),this.count--,this.cachedBytes-=n.bytes),delete t[i]};e?r():queueMicrotask(()=>{n.count===0&&r()})}return!0}throw Error("DataCache: Attempting to release key that does not exist")}},vy=class extends zf{constructor(i={}){super();let{fetchOptions:e={}}=i;this.tiling=new YT,this.fetchOptions=e,this.fetchData=(...t)=>fetch(...t)}init(){}async processBufferToTexture(i){let e=new Blob([i]),t=new Pt(await createImageBitmap(e,{premultiplyAlpha:"none",colorSpaceConversion:"none",imageOrientation:"flipY"}));return t.generateMipmaps=!1,t.colorSpace=bt,t.needsUpdate=!0,t}getMemoryUsage(i){let{format:e,type:t,image:n,generateMipmaps:r}=i,{width:s,height:a}=n,o=Fr.getByteLength(s,a,e,t);return r?o*4/3:o}fetchItem(i,e){let t={...this.fetchOptions,signal:e},n=this.getUrl(...i);return this.fetchData(n,t).then(r=>r.arrayBuffer()).then(r=>this.processBufferToTexture(r))}disposeItem(i){i&&(i.dispose(),i.image instanceof ImageBitmap&&i.image.close())}getUrl(...i){}},by=class extends vy{constructor(i={}){let{levels:e=20,tileDimension:t=256,projection:n="EPSG:3857",url:r=null,...s}=i;super(s),this.tileDimension=t,this.levels=e,this.projection=n,this.url=r}getUrl(i,e,t){return this.url.replace(/{\s*z\s*}/gi,t).replace(/{\s*x\s*}/gi,i).replace(/{\s*(y|reverseY|-\s*y)\s*}/gi,e)}init(){let{tiling:i,tileDimension:e,levels:t,url:n,projection:r}=this;return i.flipY=!/{\s*reverseY|-\s*y\s*}/g.test(n),i.setProjection(new To(r)),i.setContentBounds(...i.projection.getBounds()),Array.isArray(t)?t.forEach((s,a)=>{s!==null&&i.setLevel(a,{tilePixelWidth:e,tilePixelHeight:e,...s})}):i.generateLevels(t,i.projection.tileCountX,i.projection.tileCountY,{tilePixelWidth:e,tilePixelHeight:e}),this.url=n,Promise.resolve()}};function dh(i,e,t,n){let[r,s,a,o]=i,l=(a-r)*1e-4,c=(o-s)*1e-4;s+=c,r+=l,o-=c,a-=l;let h=Math.max(Math.min(e,t.maxLevel),t.minLevel),[u,d,f,p]=t.getTilesInRange(r,s,a,o,h,!0);for(let y=u;y<=f;y++)for(let m=d;m<=p;m++)n(y,m,h)}function ZT(i,e,t){let n=new P,r={},s=[],a=i.getAttribute("position");i.computeBoundingBox(),i.boundingBox.getCenter(n).applyMatrix4(e),t.getPositionToCartographic(n,r);let o=r.lat||0,l=r.lon||0,c=1/0,h=1/0,u=1/0,d=-1/0,f=-1/0,p=-1/0;for(let m=0;m<a.count;m++)n.fromBufferAttribute(a,m).applyMatrix4(e),t.getPositionToCartographic(n,r),Math.abs(Math.abs(r.lat)-Math.PI/2)<1e-5&&(r.lon=l),Math.abs(l-r.lon)>Math.PI&&(r.lon+=Math.sign(l-r.lon)*Math.PI*2),Math.abs(o-r.lat)>Math.PI&&(r.lat+=Math.sign(o-r.lat)*Math.PI*2),s.push(r.lon,r.lat,r.height),c=Math.min(c,r.lat),d=Math.max(d,r.lat),h=Math.min(h,r.lon),f=Math.max(f,r.lon),u=Math.min(u,r.height),p=Math.max(p,r.height);let y=[h,c,f,d];return{uv:s,range:y,region:[...y,u,p]}}function cy(i,e,t=null,n=null,r=null){let s=1/0,a=1/0,o=1/0,l=-1/0,c=-1/0,h=-1/0,u=[],d=new ge;if(i.forEach(f=>{d.copy(f.matrixWorld),t&&d.premultiply(t);let{uv:p,region:y}=ZT(f.geometry,d,e);u.push(p),s=Math.min(s,y[1]),l=Math.max(l,y[3]),a=Math.min(a,y[0]),c=Math.max(c,y[2]),o=Math.min(o,y[4]),h=Math.max(h,y[5])}),n!==null){r===null&&(r=n.clampToBounds([a,s,c,l]),r=n.fromCartographicToNormalizedRange(r));let[f,p,y,m]=r,g=h-o;u.forEach(v=>{for(let S=0,_=v.length;S<_;S+=3){let M=v[S+0],w=v[S+1],E=v[S+2],[x,A]=n.fromCartographicToNormalized(M,w);x=ye.clamp(x,0,1),A=ye.clamp(A,0,1),v[S+0]=ye.mapLinear(x,f,y,0,1),v[S+1]=ye.mapLinear(A,p,m,0,1),v[S+2]=g===0?.5:ye.mapLinear(E,o,h,0,1)}})}return{uvs:u,range:r,region:[a,s,c,l,o,h]}}function KT(i,e){let t=new P,n=[],r=i.getAttribute("position"),s=1/0,a=1/0,o=1/0,l=-1/0,c=-1/0,h=-1/0;for(let u=0;u<r.count;u++)t.fromBufferAttribute(r,u).applyMatrix4(e),n.push(t.x,t.y,t.z),s=Math.min(s,t.x),l=Math.max(l,t.x),a=Math.min(a,t.y),c=Math.max(c,t.y),o=Math.min(o,t.z),h=Math.max(h,t.z);return{uv:n,range:[s,a,l,c],heightRange:[o,h]}}function JT(i,e){let t=1/0,n=1/0,r=1/0,s=-1/0,a=-1/0,o=-1/0,l=[],c=new ge;return i.forEach(h=>{c.copy(h.matrixWorld),e&&c.premultiply(e);let{uv:u,range:d,heightRange:f}=KT(h.geometry,c);l.push(u),t=Math.min(t,d[0]),s=Math.max(s,d[2]),n=Math.min(n,d[1]),a=Math.max(a,d[3]),r=Math.min(r,f[0]),o=Math.max(o,f[1])}),l.forEach(h=>{for(let u=0,d=h.length;u<d;u+=3){let f=h[u+0],p=h[u+1];h[u+0]=ye.mapLinear(f,t,s,0,1),h[u+1]=ye.mapLinear(p,n,a,0,1)}}),{uvs:l,range:[t,n,s,a],heightRange:[r,o]}}var If=Symbol("OVERLAY_PARAMS");function QT(i,e){if(i[If])return i[If];let t={layerMaps:{value:[]},layerInfo:{value:[]}};return i[If]=t,i.defines={...i.defines||{},LAYER_COUNT:0},i.onBeforeCompile=n=>{e&&e(n),n.uniforms={...n.uniforms,...t},n.vertexShader=n.vertexShader.replace(/void main\(\s*\)\s*{/,r=>`

				#pragma unroll_loop_start
					for ( int i = 0; i < 10; i ++ ) {

						#if UNROLLED_LOOP_INDEX < LAYER_COUNT

							attribute vec3 layer_uv_UNROLLED_LOOP_INDEX;
							varying vec3 v_layer_uv_UNROLLED_LOOP_INDEX;

						#endif


					}
				#pragma unroll_loop_end

				${r}

				#pragma unroll_loop_start
					for ( int i = 0; i < 10; i ++ ) {

						#if UNROLLED_LOOP_INDEX < LAYER_COUNT

							v_layer_uv_UNROLLED_LOOP_INDEX = layer_uv_UNROLLED_LOOP_INDEX;

						#endif

					}
				#pragma unroll_loop_end

			`),n.fragmentShader=n.fragmentShader.replace(/void main\(/,r=>`

				#if LAYER_COUNT != 0
					struct LayerInfo {
						vec3 color;
						float opacity;

						int alphaMask;
						int alphaInvert;
					};

					uniform sampler2D layerMaps[ LAYER_COUNT ];
					uniform LayerInfo layerInfo[ LAYER_COUNT ];
				#endif

				#pragma unroll_loop_start
					for ( int i = 0; i < 10; i ++ ) {

						#if UNROLLED_LOOP_INDEX < LAYER_COUNT

							varying vec3 v_layer_uv_UNROLLED_LOOP_INDEX;

						#endif

					}
				#pragma unroll_loop_end

				${r}

			`).replace(/#include <color_fragment>/,r=>`

				${r}

				#if LAYER_COUNT != 0
				{
					vec4 tint;
					vec3 layerUV;
					float layerOpacity;
					float wOpacity;
					float wDelta;
					#pragma unroll_loop_start
						for ( int i = 0; i < 10; i ++ ) {

							#if UNROLLED_LOOP_INDEX < LAYER_COUNT

								layerUV = v_layer_uv_UNROLLED_LOOP_INDEX;
								tint = texture( layerMaps[ i ], layerUV.xy );

								// discard texture outside 0, 1 on w - offset the stepped value by an epsilon to avoid cases
								// where wDelta is near 0 (eg a flat surface) at the w boundary, resulting in artifacts on some
								// hardware.
								wDelta = max( fwidth( layerUV.z ), 1e-7 );
								wOpacity =
									smoothstep( - wDelta, 0.0, layerUV.z ) *
									smoothstep( 1.0 + wDelta, 1.0, layerUV.z );

								// apply tint & opacity
								tint.rgb *= layerInfo[ i ].color;
								tint.rgba *= layerInfo[ i ].opacity * wOpacity;

								// invert the alpha
								if ( layerInfo[ i ].alphaInvert > 0 ) {

									tint.a = 1.0 - tint.a;

								}

								// apply the alpha across all existing layers if alpha mask is true
								if ( layerInfo[ i ].alphaMask > 0 ) {

									diffuseColor.a *= tint.a;

								} else {

									tint.rgb *= tint.a;
									diffuseColor = tint + diffuseColor * ( 1.0 - tint.a );

								}

							#endif

						}
					#pragma unroll_loop_end
				}
				#endif
			`)},t}var kt=0,yr=["a","b","c"],ot=new Xe,hy=new Xe,uy=new Xe,dy=new Xe,e1=class{constructor(){this.attributeList=null,this.splitOperations=[],this.trianglePool=new t1}forEachSplitPermutation(i){let{splitOperations:e}=this,t=(n=0)=>{if(n>=e.length){i();return}e[n].keepPositive=!0,t(n+1),e[n].keepPositive=!1,t(n+1)};t()}addSplitOperation(i,e=!0){this.splitOperations.push({callback:i,keepPositive:e})}clearSplitOperations(){this.splitOperations.length=0}clipObject(i){let e=i.clone(),t=[];return e.traverse(n=>{n.isMesh&&(n.geometry=this.clip(n).geometry,(n.geometry.index?n.geometry.index.count/3:n.attributes.position.count/3)==0&&t.push(n))}),t.forEach(n=>{n.removeFromParent()}),e}clip(i,e=null){let t=this.getClippedData(i,e);return this.constructMesh(t.attributes,t.index,i)}getClippedData(i,e=null,t={}){let{trianglePool:n,splitOperations:r,attributeList:s}=this,a=i.geometry,o=a.attributes.position,l=a.index,c=0,h={};t.index=t.index||[],t.vertexIsClipped=t.vertexIsClipped||[],t.attributes=t.attributes||{};for(let p in a.attributes)s!==null&&(s instanceof Function&&!s(p)||Array.isArray(s)&&!s.includes(p))||(t.attributes[p]=[]);let u=0,d=l?l.count:o.count;e!==null&&(u=e.start,d=e.count);for(let p=u,y=u+d;p<y;p+=3){let m=p+0,g=p+1,v=p+2;l&&(m=l.getX(m),g=l.getX(g),v=l.getX(v));let S=n.get();S.initFromIndices(m,g,v);let _=[S];for(let M=0;M<r.length;M++){let{keepPositive:w,callback:E}=r[M],x=[];for(let A=0;A<_.length;A++){let C=_[A],{indices:D,barycoord:U}=C;C.clipValues.a=E(a,D.a,D.b,D.c,U.a,i.matrixWorld),C.clipValues.b=E(a,D.a,D.b,D.c,U.b,i.matrixWorld),C.clipValues.c=E(a,D.a,D.b,D.c,U.c,i.matrixWorld),this.splitTriangle(C,!w,x)}_=x}for(let M=0,w=_.length;M<w;M++){let E=_[M];f(E,a)}n.reset()}return t;function f(p,y){for(let m=0;m<3;m++){let g=p.getVertexHash(m,y);g in h||(h[g]=c,c++,p.getVertexData(m,y,t.attributes),t.vertexIsClipped.push(p.clipValues[yr[m]]===kt));let v=h[g];t.index.push(v)}}}constructMesh(i,e,t){let n=t.geometry,r=new ht,s=i.position.length/3>65535?new Uint32Array(e):new Uint16Array(e);r.setIndex(new Ye(s,1,!1));for(let o in i){let l=n.getAttribute(o),c=new Ye(new l.array.constructor(i[o]),l.itemSize,l.normalized);c.gpuType=l.gpuType,r.setAttribute(o,c)}let a=new at(r,t.material.clone());return a.position.copy(t.position),a.quaternion.copy(t.quaternion),a.scale.copy(t.scale),a}splitTriangle(i,e,t){let{trianglePool:n}=this,r=[],s=[],a=[];for(let o=0;o<3;o++){let l=yr[o],c=yr[(o+1)%3],h=i.clipValues[l],u=i.clipValues[c];(h<kt!=u<kt||h===kt)&&(r.push(o),s.push([l,c]),h===u?a.push(0):a.push(ye.mapLinear(kt,h,u,0,1)))}if(r.length!==2)Math.min(i.clipValues.a,i.clipValues.b,i.clipValues.c)<kt===e&&t.push(i);else if(r.length===2){let o=n.get().initFromTriangle(i),l=n.get().initFromTriangle(i),c=n.get().initFromTriangle(i);(r[0]+1)%3===r[1]?(o.lerpVertexFromEdge(i,s[0][0],s[0][1],a[0],"a"),o.copyVertex(i,s[0][1],"b"),o.lerpVertexFromEdge(i,s[1][0],s[1][1],a[1],"c"),o.clipValues.a=kt,o.clipValues.c=kt,l.lerpVertexFromEdge(i,s[0][0],s[0][1],a[0],"a"),l.copyVertex(i,s[1][1],"b"),l.copyVertex(i,s[0][0],"c"),l.clipValues.a=kt,c.lerpVertexFromEdge(i,s[0][0],s[0][1],a[0],"a"),c.lerpVertexFromEdge(i,s[1][0],s[1][1],a[1],"b"),c.copyVertex(i,s[1][1],"c"),c.clipValues.a=kt,c.clipValues.b=kt):(o.lerpVertexFromEdge(i,s[0][0],s[0][1],a[0],"a"),o.lerpVertexFromEdge(i,s[1][0],s[1][1],a[1],"b"),o.copyVertex(i,s[0][0],"c"),o.clipValues.a=kt,o.clipValues.b=kt,l.lerpVertexFromEdge(i,s[0][0],s[0][1],a[0],"a"),l.copyVertex(i,s[0][1],"b"),l.lerpVertexFromEdge(i,s[1][0],s[1][1],a[1],"c"),l.clipValues.a=kt,l.clipValues.c=kt,c.copyVertex(i,s[0][1],"a"),c.copyVertex(i,s[1][0],"b"),c.lerpVertexFromEdge(i,s[1][0],s[1][1],a[1],"c"),c.clipValues.c=kt);let h,u;h=Math.min(o.clipValues.a,o.clipValues.b,o.clipValues.c),u=h<kt,u===e&&t.push(o),h=Math.min(l.clipValues.a,l.clipValues.b,l.clipValues.c),u=h<kt,u===e&&t.push(l),h=Math.min(c.clipValues.a,c.clipValues.b,c.clipValues.c),u=h<kt,u===e&&t.push(c)}}},t1=class{constructor(){this.pool=[],this.index=0}get(){if(this.index>=this.pool.length){let e=new i1;this.pool.push(e)}let i=this.pool[this.index];return this.index++,i}reset(){this.index=0}},i1=class{constructor(){this.indices={a:-1,b:-1,c:-1},this.clipValues={a:-1,b:-1,c:-1},this.barycoord=new Vi}getVertexHash(i,e){let{barycoord:t,indices:n}=this,r=t[yr[i]];if(r.x===1)return n[yr[0]];if(r.y===1)return n[yr[1]];if(r.z===1)return n[yr[2]];{let{attributes:s}=e,a="";for(let o in s){let l=s[o];switch(fy(l,n.a,n.b,n.c,r,ot),(o==="normal"||o==="tangent"||o==="bitangent")&&ot.normalize(),l.itemSize){case 4:a+=fh(ot.x,ot.y,ot.z,ot.w);break;case 3:a+=fh(ot.x,ot.y,ot.z);break;case 2:a+=fh(ot.x,ot.y);break;case 1:a+=fh(ot.x);break}a+="|"}return a}}getVertexData(i,e,t){let{barycoord:n,indices:r}=this,s=n[yr[i]],{attributes:a}=e;for(let o in a){if(!t[o])continue;let l=a[o],c=t[o];switch(fy(l,r.a,r.b,r.c,s,ot),(o==="normal"||o==="tangent"||o==="bitangent")&&ot.normalize(),l.itemSize){case 4:c.push(ot.x,ot.y,ot.z,ot.w);break;case 3:c.push(ot.x,ot.y,ot.z);break;case 2:c.push(ot.x,ot.y);break;case 1:c.push(ot.x);break}}}initFromTriangle(i){return this.initFromIndices(i.indices.a,i.indices.b,i.indices.c)}initFromIndices(i,e,t){return this.indices.a=i,this.indices.b=e,this.indices.c=t,this.clipValues.a=-1,this.clipValues.b=-1,this.clipValues.c=-1,this.barycoord.a.set(1,0,0),this.barycoord.b.set(0,1,0),this.barycoord.c.set(0,0,1),this}lerpVertexFromEdge(i,e,t,n,r){this.clipValues[r]=ye.lerp(i.clipValues[e],i.clipValues[t],n),this.barycoord[r].lerpVectors(i.barycoord[e],i.barycoord[t],n)}copyVertex(i,e,t){this.clipValues[t]=i.clipValues[e],this.barycoord[t].copy(i.barycoord[e])}};function fy(i,e,t,n,r,s){switch(hy.fromBufferAttribute(i,e),uy.fromBufferAttribute(i,t),dy.fromBufferAttribute(i,n),s.set(0,0,0,0).addScaledVector(hy,r.x).addScaledVector(uy,r.y).addScaledVector(dy,r.z),i.itemSize){case 3:ot.w=0;break;case 2:ot.w=0,ot.z=0;break;case 1:ot.w=0,ot.z=0,ot.y=0;break}return s}function fh(...i){let e="";for(let t=0,n=i.length;t<n;t++)e+=~~(i[t]*1e5+.5),t!==n-1&&(e+="_");return e}var Sy=class{constructor(){this.canvas=null,this.context=null,this.range=[0,0,1,1]}setTarget(i,e){this.canvas=i.image,this.context=i.image.getContext("2d"),this.range=[...e]}draw(i,e){let{canvas:t,range:n,context:r}=this,{width:s,height:a}=t,{image:o}=i,l=Math.round(ye.mapLinear(e[0],n[0],n[2],0,s)),c=Math.round(ye.mapLinear(e[1],n[1],n[3],0,a)),h=Math.round(ye.mapLinear(e[2],n[0],n[2],0,s)),u=Math.round(ye.mapLinear(e[3],n[1],n[3],0,a)),d=h-l,f=u-c;o instanceof ImageBitmap?(r.save(),r.translate(l,a-c),r.scale(1,-1),r.drawImage(o,0,0,d,f),r.restore()):r.drawImage(o,l,a-c,d,-f)}clear(){let{context:i,canvas:e}=this;i.clearRect(0,0,e.width,e.height)}},n1=1e-10;function r1(i,e,t=0){if(i.length!==e.length)return!1;for(let n=0,r=i.length;n<r;n++)if(Math.abs(i[n]-e[n])>t)return!1;return!0}var s1=class extends zf{hasContent(...i){return!0}},a1=class extends s1{constructor(i){super(),this.tiledImageSource=i,this.tileComposer=new Sy,this.resolution=256}hasContent(i,e,t,n,r){let s=this.tiledImageSource.tiling,a=0;return dh([i,e,t,n],r,s,()=>{a++}),a!==0}async fetchItem([i,e,t,n,r],s){let{tiledImageSource:a,tileComposer:o}=this,l=[i,e,t,n],c=a.tiling;await this._markImages(l,r,!1),s?.throwIfAborted();let h=null;if(dh(l,r,c,(f,p,y)=>{r1(c.getTileBounds(f,p,y,!0,!1),l,n1)&&(h=[f,p,y])}),h!==null){let[f,p,y]=h;return a.get(f,p,y).clone()}let u=document.createElement("canvas");u.width=this.resolution,u.height=this.resolution;let d=new Kn(u);return d.colorSpace=bt,d.generateMipmaps=!1,o.setTarget(d,l),o.clear(16777215,0),dh(l,r,c,(f,p,y)=>{let m=c.getTileBounds(f,p,y,!0,!1),g=a.get(f,p,y);o.draw(g,m)}),d}disposeItem(i,[e,t,n,r,s]){i&&i.dispose(),this._markImages([e,t,n,r],s,!0)}dispose(){super.dispose(),this.tiledImageSource.dispose()}_markImages(i,e,t=!1){let n=this.tiledImageSource,r=n.tiling,s=[];dh(i,e,r,(o,l,c)=>{t?n.release(o,l,c):s.push(n.lock(o,l,c))});let a=s.filter(o=>o instanceof Promise);return a.length===0?null:Promise.all(a)}},gI=Object.freeze({fill:"#cccccc",stroke:"transparent",strokeWidth:1,radius:2,order:0,visible:!0});var o1=class extends vy{constructor(i={}){let{url:e=null,layer:t=null,styles:n=null,contentBoundingBox:r=null,version:s="1.3.0",crs:a="EPSG:4326",format:o="image/png",transparent:l=!1,levels:c=18,tileDimension:h=256,...u}=i;super(u),this.url=e,this.layer=t,this.crs=a,this.format=o,this.tileDimension=h,this.styles=n,this.version=s,this.levels=c,this.transparent=l,this.contentBoundingBox=r}init(){let{tiling:i,levels:e,tileDimension:t,contentBoundingBox:n}=this;return i.setProjection(new To(this.crs)),i.flipY=!0,i.generateLevels(e,i.projection.tileCountX,i.projection.tileCountY,{tilePixelWidth:t,tilePixelHeight:t}),n===null?i.setContentBounds(...i.projection.getBounds()):i.setContentBounds(...n),Promise.resolve()}normalizedToMercatorX(i){return ye.mapLinear(i,0,1,-20037508342789244e-9,20037508342789244e-9)}normalizedToMercatorY(i){return ye.mapLinear(i,0,1,-20037508342789244e-9,20037508342789244e-9)}getUrl(i,e,t){let{tiling:n,layer:r,crs:s,format:a,tileDimension:o,styles:l,version:c,transparent:h}=this,u=c==="1.1.1"?"SRS":"CRS",d;if(s==="EPSG:3857"){let p=n.getTileBounds(i,e,t,!0,!1);d=[this.normalizedToMercatorX(p[0]),this.normalizedToMercatorY(p[1]),this.normalizedToMercatorX(p[2]),this.normalizedToMercatorY(p[3])]}else{let[p,y,m,g]=n.getTileBounds(i,e,t,!1,!1).map(v=>v*ye.RAD2DEG);d=s==="EPSG:4326"?c==="1.1.1"?[p,y,m,g]:[y,p,g,m]:[p,y,m,g]}let f=new URLSearchParams({SERVICE:"WMS",REQUEST:"GetMap",VERSION:c,LAYERS:r,[u]:s,BBOX:d.join(","),WIDTH:o,HEIGHT:o,FORMAT:a,TRANSPARENT:h?"TRUE":"FALSE"});return l!=null&&f.set("STYLES",l),new URL("?"+f.toString(),this.url).toString()}};var Ks=new ge,ph=new P,Lf=new P,Df=new P,fn=new P,l1=new Mt,py=Symbol("SPLIT_TILE_DATA"),mh=Symbol("SPLIT_HASH"),gh=Symbol("ORIGINAL_REFINE"),Bf=new jr;Bf.maxJobs=10,Bf.priorityCallback=(i,e)=>{let t=i.tile,n=e.tile,r=t.internal.renderer,s=n.internal.renderer,a=r.visibleTiles.has(t);return a===s.visibleTiles.has(n)?oo(t,n):a?1:-1};var Vf=class{get enableTileSplitting(){return this._enableTileSplitting}set enableTileSplitting(i){this._enableTileSplitting!==i&&(this._enableTileSplitting=i,this._markNeedsUpdate())}constructor(i={}){let{overlays:e=[],resolution:t=256,enableTileSplitting:n=!0}=i;this.name="IMAGE_OVERLAY_PLUGIN",this.priority=-15,this.resolution=t,this._enableTileSplitting=n,this.overlays=[],this.needsUpdate=!1,this.tiles=null,this.tileComposer=null,this.tileControllers=new Map,this.overlayInfo=new Map,this.meshParams=new WeakMap,this.pendingTiles=new Map,this.processedTiles=new Set,this.processQueue=null,this._onUpdateAfter=null,this._onTileDownloadStart=null,this._onTileVisibilityChange=null,this._virtualChildResetId=0,this._bytesUsed=new WeakMap,e.forEach(r=>{this.addOverlay(r)})}init(i){let e=new Sy;this.tiles=i,this.tileComposer=e,this.processQueue=Bf,i.forEachLoadedModel((t,n)=>{this._processTileModel(t,n,!0)}),this._onUpdateAfter=async()=>{let t=!1;if(this.overlayInfo.forEach((n,r)=>{if(!!r.frame!=!!n.frame||r.frame&&n.frame&&!n.frame.equals(r.frame)){let s=n.order;this.deleteOverlay(r),this.addOverlay(r,s),t=!0}}),t){let{processQueue:n}=this,r=n.maxJobs,s=0;n.items.forEach(a=>{i.visibleTiles.has(a.tile)&&s++}),n.maxJobs=s+n.currJobs,n.tryRunJobs(),n.maxJobs=r,this.needsUpdate=!0}if(this.needsUpdate){this.needsUpdate=!1;let{overlays:n,overlayInfo:r}=this;n.sort((s,a)=>r.get(s).order-r.get(a).order),this.processedTiles.forEach(s=>{this._updateLayers(s)}),this.resetVirtualChildren(!this.enableTileSplitting),i.recalculateBytesUsed(),i.dispatchEvent({type:"needs-render"})}},this._onTileDownloadStart=({tile:t,url:n})=>{!/\.json$/i.test(n)&&!/\.subtree/i.test(n)&&(this.processedTiles.add(t),this._initTileOverlayInfo(t))},this._onTileVisibilityChange=({tile:t,visible:n})=>{this.overlayInfo.forEach(({tileInfo:r},s)=>{if(r.has(t)){let{range:a}=r.get(t);s.setRegionVisible(a,n,t)}})},i.addEventListener("update-after",this._onUpdateAfter),i.addEventListener("tile-download-start",this._onTileDownloadStart),i.addEventListener("tile-visibility-change",this._onTileVisibilityChange),this.overlays.forEach(t=>{this._initOverlay(t)})}_removeVirtualChildren(i){if(!(gh in i))return;let{tiles:e}=this,{virtualChildCount:t}=i.internal,n=i.children.length,r=n-t;for(let s=r;s<n;s++){let a=i.children[s];e.processNodeQueue.remove(a),e.lruCache.remove(a),a.parent=null}i.children.length-=t,i.internal.virtualChildCount=0,i.refine=i[gh],delete i[gh],delete i[mh]}disposeTile(i){let{overlayInfo:e,tileControllers:t,processQueue:n,pendingTiles:r,processedTiles:s}=this;s.delete(i),this._removeVirtualChildren(i),t.has(i)&&(t.get(i).abort(),t.delete(i),r.delete(i)),e.forEach((({tileInfo:a},o)=>{if(a.has(i)){let{meshInfo:l,range:c}=a.get(i);c!==null&&o.releaseTexture(c),a.delete(i),l.clear()}})),n.removeByFilter(a=>a.tile===i)}calculateBytesUsed(i){let{overlayInfo:e}=this,t=this._bytesUsed,n=null;return e.forEach(({tileInfo:r},s)=>{if(r.has(i)){let{target:a}=r.get(i);n||(n=0),n+=Ef(a)}}),n===null?t.has(i)?t.get(i):0:(t.set(i,n),n)}processTileModel(i,e){return this._processTileModel(i,e)}async _processTileModel(i,e,t=!1){let{tileControllers:n,processedTiles:r,pendingTiles:s}=this;n.set(e,new AbortController),t||s.set(e,i),r.add(e),this._wrapMaterials(i),this._initTileOverlayInfo(e),await this._initTileSceneOverlayInfo(i,e),this.expandVirtualChildren(i,e),this._updateLayers(e),s.delete(e)}dispose(){let{tiles:i}=this;[...this.overlays].forEach(e=>{this.deleteOverlay(e)}),this.processedTiles.forEach(e=>{this._updateLayers(e),this.disposeTile(e)}),i.removeEventListener("update-after",this._onUpdateAfter),i.removeEventListener("tile-download-start",this._onTileDownloadStart),i.removeEventListener("tile-visibility-change",this._onTileVisibilityChange),this.resetVirtualChildren(!0)}getAttributions(i){this.overlays.forEach(e=>{e.opacity>0&&e.getAttributions(i)})}parseToMesh(i,e,t,n){if(t==="image_overlay_tile_split")return e[py]}async resetVirtualChildren(i=!1){this._virtualChildResetId++;let e=this._virtualChildResetId;if(await Promise.all(this.overlays.map(r=>r.whenReady())),e!==this._virtualChildResetId)return;let{tiles:t}=this,n=[];this.processedTiles.forEach(r=>{mh in r&&n.push(r)}),n.sort((r,s)=>s.internal.depth-r.internal.depth),n.forEach(r=>{let s=r.engineData.scene.clone();s.updateMatrixWorld(),(i||r[mh]!==this._getSplitVectors(s,r).hash)&&this._removeVirtualChildren(r)}),i||t.forEachLoadedModel((r,s)=>{this.expandVirtualChildren(r,s)})}_getSplitVectors(i,e,t=Lf){let{tiles:n,overlayInfo:r}=this,s=new Mt;s.setFromObject(i),s.getCenter(t);let a=[],o=[];r.forEach(({tileInfo:c},h)=>{let u=c.get(e);if(u&&u.target&&h.shouldSplit(u.range)){h.frame?fn.set(0,0,1).transformDirection(h.frame):(n.surface.getPositionToNormal(t,fn),fn.length()<1e-6&&fn.set(1,0,0));let d=`${fn.x.toFixed(3)},${fn.y.toFixed(3)},${fn.z.toFixed(3)}_`;o.includes(d)||o.push(d);let f=ph.set(0,0,1);Math.abs(fn.dot(f))>.9999&&f.set(1,0,0);let p=new P().crossVectors(fn,f).normalize(),y=new P().crossVectors(fn,p).normalize();a.push(p,y)}});let l=[];for(;a.length!==0;){let c=a.pop().clone(),h=c.clone();for(let u=0;u<a.length;u++){let d=a[u],f=c.dot(d);Math.abs(f)>Math.cos(Math.PI/8)&&(h.addScaledVector(d,Math.sign(f)),c.copy(h).normalize(),a.splice(u,1),u--)}l.push(h.normalize())}return{directions:l,hash:o.join("")}}async expandVirtualChildren(i,e){let{refine:t}=e,n=t==="REPLACE"&&e.children.length===0||t==="ADD",r=e.internal.virtualChildCount!==0;if(this.enableTileSplitting===!1||!n||r)return;let s=i.clone();s.updateMatrixWorld();let{directions:a,hash:o}=this._getSplitVectors(s,e,Lf);if(a.length===0)return;e[mh]=o;let l=new e1;l.attributeList=h=>!/^layer_uv_\d+/.test(h),a.map(h=>{l.addSplitOperation((u,d,f,p,y,m)=>(Vi.getInterpolatedAttribute(u.attributes.position,d,f,p,y,ph),ph.applyMatrix4(m).sub(Lf).dot(h)))});let c=[];l.forEachSplitPermutation(()=>{let h=l.clipObject(s);h.matrix.premultiply(e.engineData.transformInverse).decompose(h.position,h.quaternion,h.scale);let u=[];if(h.traverse(f=>{if(f.isMesh){let p=f.material.clone();f.material=p;for(let y in p){let m=p[y];if(m&&m.isTexture&&m.source.data instanceof ImageBitmap){let g=document.createElement("canvas");g.width=m.image.width,g.height=m.image.height;let v=g.getContext("2d");v.scale(1,-1),v.drawImage(m.source.data,0,0,g.width,-g.height);let S=new Kn(g);S.mapping=m.mapping,S.wrapS=m.wrapS,S.wrapT=m.wrapT,S.minFilter=m.minFilter,S.magFilter=m.magFilter,S.format=m.format,S.type=m.type,S.anisotropy=m.anisotropy,S.colorSpace=m.colorSpace,S.generateMipmaps=m.generateMipmaps,p[y]=S}}u.push(f)}}),u.length===0)return;let d={};if(e.boundingVolume.region&&(d.region=cy(u,this.tiles.surface).region),e.boundingVolume.box||e.boundingVolume.sphere){l1.setFromObject(h,!0).getCenter(Df);let f=0;h.traverse(p=>{let y=p.geometry;if(y){let m=y.attributes.position;for(let g=0,v=m.count;g<v;g++){let S=ph.fromBufferAttribute(m,g).applyMatrix4(p.matrixWorld).distanceToSquared(Df);f=Math.max(f,S)}}}),d.sphere=[...Df,Math.sqrt(f)]}c.push({internal:{isVirtual:!0},refine:"REPLACE",geometricError:e.geometricError*.5,boundingVolume:d,content:{uri:"./child.image_overlay_tile_split"},children:[],[py]:h})}),e[gh]=e.refine,e.refine="REPLACE",e.children.push(...c),e.internal.virtualChildCount+=c.length}fetchData(i,e){if(/image_overlay_tile_split/.test(i))return new ArrayBuffer}addOverlay(i,e=null){let{tiles:t,overlays:n,overlayInfo:r}=this;e===null&&(e=n.reduce((a,o)=>Math.max(a,r.get(o).order+1),0));let s=new AbortController;n.push(i),r.set(i,{order:e,uniforms:{},tileInfo:new Map,controller:s,frame:i.frame?i.frame.clone():null}),t!==null&&this._initOverlay(i)}setOverlayOrder(i,e){this.overlays.indexOf(i)!==-1&&(this.overlayInfo.get(i).order=e,this._markNeedsUpdate())}deleteOverlay(i){let{overlays:e,overlayInfo:t,processQueue:n,processedTiles:r,tiles:s}=this,a=e.indexOf(i);if(a!==-1){let{tileInfo:o,controller:l}=t.get(i);r.forEach(c=>{if(!o.has(c))return;let{meshInfo:h,range:u}=o.get(c);u!==null&&(s.visibleTiles.has(c)&&i.setRegionVisible(u,!1),i.releaseTexture(u)),o.delete(c),h.clear()}),o.clear(),t.delete(i),l.abort(),n.removeByFilter(c=>c.overlay===i&&r.has(c.tile)),e.splice(a,1),r.forEach(c=>{this._updateLayers(c)}),this._markNeedsUpdate()}}_initOverlay(i){let{processedTiles:e}=this;i.init().then(()=>{i.setResolution(this.resolution)});let t=[];e.forEach(async n=>{let r=n.engineData.scene;this._initTileOverlayInfo(n,i);let s=this._initTileSceneOverlayInfo(r,n,i);t.push(s),await s,this._updateLayers(n)}),Promise.all(t).then(()=>{this._markNeedsUpdate()})}_wrapMaterials(i){i.traverse(e=>{if(e.material){let t=QT(e.material,e.material.onBeforeCompile);this.meshParams.set(e,t)}})}_initTileOverlayInfo(i,e=this.overlays){if(Array.isArray(e)){e.forEach(r=>this._initTileOverlayInfo(i,r));return}let{overlayInfo:t}=this;if(t.get(e).tileInfo.has(i))return;let n={range:null,target:null,meshInfo:new Map,failed:!1};if(t.get(e).tileInfo.set(i,n),e.isReady&&!e.isPlanarProjection){let r=i.boundingVolume.region??i.boundingVolume.cartographicRange;if(r){let[s,a,o,l]=r,c=[s,a,o,l];c=e.projection.clampToBounds(c),c=e.projection.fromCartographicToNormalizedRange(c),n.range=c,e.lockTextureSafe(c)}}}async _initTileSceneOverlayInfo(i,e,t=this.overlays){if(Array.isArray(t))return Promise.all(t.map(g=>this._initTileSceneOverlayInfo(i,e,g)));let{tiles:n,overlayInfo:r,tileControllers:s}=this,{surface:a}=n,{controller:o,tileInfo:l}=r.get(t),c=s.get(e);if(t.isReady||await t.whenReady(),o.signal.aborted||c.signal.aborted)return;let h=[];i.updateMatrixWorld(),i.traverse(g=>{g.isMesh&&h.push(g)});let{aspectRatio:u,projection:d}=t,f=l.get(e),p,y,m;if(t.isPlanarProjection){Ks.makeScale(1/u,1,1).multiply(t.frame),i.parent!==null&&Ks.multiply(n.group.matrixWorldInverse);let g;({range:p,uvs:y,heightRange:g}=JT(h,Ks)),m=!(g[0]>1||g[1]<0)}else Ks.identity(),i.parent!==null&&Ks.copy(n.group.matrixWorldInverse),{range:p,uvs:y}=cy(h,a,Ks,d,f.range),m=!0;f.range===null&&(f.range=p,t.lockTextureSafe(p)),n.visibleTiles.has(e)&&t.setRegionVisible(f.range,!0),m&&t.hasContent(p)&&await this._fetchTileOverlayTexture(e,t,f),h.forEach((g,v)=>{let S=new Ye(new Float32Array(y[v]),3);f.meshInfo.set(g,{attribute:S})})}async _fetchTileOverlayTexture(i,e,t){let{tiles:n,overlayInfo:r,tileControllers:s,processQueue:a}=this,{controller:o}=r.get(e),l=s.get(i),{range:c}=t;t.target=await a.add({tile:i,overlay:e},async()=>{if(o.signal.aborted||l.signal.aborted)return null;let h=await e.getTexture(c);return o.signal.aborted||l.signal.aborted?null:h}).catch(h=>(h.name==="AbortError"||(t.failed=!0,n.dispatchEvent({type:"load-error",tile:i,overlay:e,error:h,url:null})),null))}resetFailedOverlays(){let{processedTiles:i,overlayInfo:e,overlays:t}=this,n=[];i.forEach(r=>{t.forEach(s=>{let{tileInfo:a}=e.get(s),o=a.get(r);o.failed&&(o.failed=!1,s.releaseTexture(o.range),n.push({tile:r,overlay:s,info:o}))})}),requestAnimationFrame(()=>{n.forEach(({tile:r,overlay:s,info:a})=>{s.lockTextureSafe(a.range),this._fetchTileOverlayTexture(r,s,a).then(()=>{this._updateLayers(r)}).catch(o=>{if(o.name!=="AbortError")throw o})})})}_updateLayers(i){let{overlayInfo:e,overlays:t,tileControllers:n,meshParams:r}=this,s=n.get(i);if(this.tiles.recalculateBytesUsed(i),!(!s||s.signal.aborted)){if(t.length===0){let a=i.engineData&&i.engineData.scene;a&&a.traverse(o=>{if(o.material&&r.has(o)){let l=r.get(o);l.layerMaps.length=0,l.layerInfo.length=0,o.material.defines.LAYER_COUNT=0,o.material.needsUpdate=!0}});return}t.forEach((a,o)=>{let{tileInfo:l}=e.get(a),{meshInfo:c,target:h}=l.get(i);c.forEach(({attribute:u},d)=>{let{geometry:f,material:p}=d,y=r.get(d),m=`layer_uv_${o}`;f.getAttribute(m)!==u&&(f.setAttribute(m,u),f.dispose()),y.layerMaps.length=t.length,y.layerInfo.length=t.length,y.layerMaps.value[o]=h===null?null:h,y.layerInfo.value[o]=a,p.defines[`LAYER_${o}_EXISTS`]=+(h!==null),p.defines[`LAYER_${o}_ALPHA_INVERT`]=Number(a.alphaInvert),p.defines[`LAYER_${o}_ALPHA_MASK`]=Number(a.alphaMask),p.defines.LAYER_COUNT=t.length,p.needsUpdate=!0})})}}_markNeedsUpdate(){this.needsUpdate===!1&&(this.needsUpdate=!0,this.tiles!==null&&this.tiles.dispatchEvent({type:"needs-update"}))}},My=class{get isPlanarProjection(){return!!this.frame}get downloadQueue(){return this._downloadQueue}set downloadQueue(i){if(i instanceof jr){console.warn('ImageOverlay: "downloadQueue" is no longer valid as a PriorityQueue. Use a DownloadPriorityQueue, instead.');return}this._downloadQueue=i}constructor(i={}){let{opacity:e=1,color:t=16777215,frame:n=null,preprocessURL:r=null,alphaMask:s=!1,alphaInvert:a=!1}=i;this.preprocessURL=r,this.opacity=e,this.color=new Ie(t),this.frame=n===null?null:n.clone(),this.alphaMask=s,this.alphaInvert=a,this.downloadQueue=so,this._whenReady=null,this.isReady=!1,this.isInitialized=!1,this._visibleRegionCounts=new Map}init(){return this.isInitialized||(this.isInitialized=!0,this._whenReady=this._init().then(()=>this.isReady=!0)),this._whenReady}whenReady(){return this._whenReady}_init(){return Promise.resolve()}fetch(i,e={}){this.preprocessURL&&(i=this.preprocessURL(i));let t={priority:-performance.now()};return this.downloadQueue.add(i,t,()=>fetch(i,e),e.signal)}getAttributions(i){}hasContent(i,e=null){return!1}async getTexture(i,e=null){return null}async lockTexture(i,e=null){return null}lockTextureSafe(i){let e=this.lockTexture(i);return e instanceof Promise&&e.catch(t=>{if(t.name!=="AbortError")throw t}),e}releaseTexture(i,e=null){}shouldSplit(i,e=null){return!1}setResolution(i){}setRegionVisible(i,e){let{_visibleRegionCounts:t}=this,n=i.join("_"),r=t.get(n);if(r||(r={range:[...i],count:0},t.set(n,r)),r.count+=e?1:-1,r.count<0)throw Error();r.count===0&&t.delete(n)}},Gf=class extends My{get tiling(){return this.imageSource.tiling}get projection(){return this.tiling.projection}get aspectRatio(){return this.tiling&&this.isReady?this.tiling.aspectRatio:1}get fetchOptions(){return this.imageSource.fetchOptions}set fetchOptions(i){this.imageSource.fetchOptions=i}constructor(i={}){let{imageSource:e=null,...t}=i;super(t),this.imageSource=e,this.regionImageSource=null}_init(){return this._initImageSource().then(()=>{this.imageSource.fetchData=(...i)=>this.fetch(...i),this.regionImageSource=new a1(this.imageSource)})}_initImageSource(){return this.imageSource.init()}calculateLevel(i,e=null){let[t,n,r,s]=i,a=r-t,o=s-n;e===null&&(e=this.regionImageSource.resolution);let l=0,c=this.tiling.maxLevel;for(;l<c;l++){let h=e/a,u=e/o,d=this.tiling.getLevel(l);if(d==null)continue;let{pixelWidth:f,pixelHeight:p}=d;if(f>=h||p>=u)break}return l}hasContent(i,e=this.calculateLevel(i)){return this.regionImageSource.hasContent(...i,e)}getTexture(i,e=this.calculateLevel(i)){return this.regionImageSource.get(...i,e)}lockTexture(i,e=this.calculateLevel(i)){return this.regionImageSource.lock(...i,e)}releaseTexture(i,e=this.calculateLevel(i)){this.regionImageSource.release(...i,e)}shouldSplit(i,e=this.calculateLevel(i)){return this.tiling.maxLevel>e}setResolution(i){this.regionImageSource.resolution=i}},Hf=class extends Gf{constructor(i={}){super(i),this.imageSource=new by(i)}};var Wf=class extends Gf{constructor(i={}){super(i),this.imageSource=new o1(i)}};var Nf=new ge,Xf=class{constructor(){this.name="UPDATE_ON_CHANGE_PLUGIN",this.tiles=null,this.needsUpdate=!1,this.cameraMatrices=new Map}init(i){this.tiles=i,this._needsUpdateCallback=()=>{this.needsUpdate=!0},this._onCameraAdd=({camera:e})=>{this.needsUpdate=!0,this.cameraMatrices.set(e,new ge)},this._onCameraDelete=({camera:e})=>{this.needsUpdate=!0,this.cameraMatrices.delete(e)},i.addEventListener("needs-update",this._needsUpdateCallback),i.addEventListener("add-camera",this._onCameraAdd),i.addEventListener("delete-camera",this._onCameraDelete),i.addEventListener("camera-resolution-change",this._needsUpdateCallback),i.cameras.forEach(e=>{this._onCameraAdd({camera:e})})}doTilesNeedUpdate(){let i=this.tiles,e=!1;this.cameraMatrices.forEach((n,r)=>{Nf.copy(i.group.matrixWorld).premultiply(r.matrixWorldInverse).premultiply(r.projectionMatrixInverse),e||(e=!Nf.equals(n)),n.copy(Nf)});let t=this.needsUpdate;return this.needsUpdate=!1,t||e}preprocessNode(){this.needsUpdate=!0}dispose(){let i=this.tiles;i.removeEventListener("camera-resolution-change",this._needsUpdateCallback),i.removeEventListener("needs-update",this._needsUpdateCallback),i.removeEventListener("add-camera",this._onCameraAdd),i.removeEventListener("delete-camera",this._onCameraDelete)}};var{clamp:yI}=ye;var _I=new oh(new Yt),c1=new Sn(new Uint8Array([255,255,255,255]),1,1);c1.needsUpdate=!0;var h1=0,u1=1,d1=2,f1=3,p1=4,m1=5,g1=6,y1=7,_1=8,x1=9,v1=10,b1=11,xI=Object.freeze({NONE:h1,SCREEN_ERROR:u1,GEOMETRIC_ERROR:d1,DISTANCE:f1,DEPTH:p1,RELATIVE_DEPTH:m1,IS_LEAF:g1,RANDOM_COLOR:y1,RANDOM_NODE_COLOR:_1,CUSTOM_COLOR:x1,LOAD_ORDER:v1,INDEXED_COLOR:b1});var vI=Math.PI/4,bI=3/5;var pr={NONE:0,NOT_READY:1,NO_FIT:2,DEPTH:3,OCCUPANCY:4,SPACING:5,ANGLE:6,FACING:7};var SI=new class{constructor(){this._cache={}}getColor(...i){let e=i.pop(),t=i.join("_"),{_cache:n}=this;return t in n||(e.setHSL(Math.random(),1,.5),n[t]=e.getHex()),e.set(n[t])}};var MI={[pr.NONE]:16777215,[pr.NOT_READY]:7829367,[pr.NO_FIT]:2250239,[pr.DEPTH]:4473924,[pr.OCCUPANCY]:65535,[pr.SPACING]:16776960,[pr.ANGLE]:16711680,[pr.FACING]:16711935};var wy=class extends ht{constructor(i=1,e=1,t=1,n=1){super();let r=t+1,s=n+1,a=r*s,o=[];for(let y=0;y<r;y++)o.push(y);for(let y=1;y<s;y++)o.push(y*r+r-1);for(let y=r-2;y>=0;y--)o.push((s-1)*r+y);for(let y=s-2;y>=1;y--)o.push(y*r);let l=o.length,c=a+l,h=new Float32Array(3*c),u=new Float32Array(3*c),d=new Float32Array(2*c);for(let y=0;y<s;y++)for(let m=0;m<r;m++){let g=y*r+m,v=m/t,S=1-y/n;h[3*g+0]=(v-.5)*i,h[3*g+1]=(S-.5)*e,u[3*g+2]=1,d[2*g+0]=v,d[2*g+1]=S}for(let y=0;y<l;y++){let m=o[y],g=a+y;h[3*g+0]=h[3*m+0],h[3*g+1]=h[3*m+1],h[3*g+2]=h[3*m+2],u[3*g+2]=1,d[2*g+0]=d[2*m+0],d[2*g+1]=d[2*m+1]}let f=new Uint32Array(6*t*n+6*l),p=0;for(let y=0;y<n;y++)for(let m=0;m<t;m++){let g=y*r+m,v=(y+1)*r+m,S=(y+1)*r+m+1,_=y*r+m+1;f[p++]=g,f[p++]=v,f[p++]=_,f[p++]=v,f[p++]=S,f[p++]=_}for(let y=0;y<l;y++){let m=(y+1)%l,g=o[y],v=o[m],S=a+y,_=a+m;f[p++]=g,f[p++]=v,f[p++]=S,f[p++]=v,f[p++]=_,f[p++]=S}this.setIndex(new Ye(f,1)),this.setAttribute("position",new Ye(h,3)),this.setAttribute("normal",new Ye(u,3)),this.setAttribute("uv",new Ye(d,2)),this.surfaceVertexCount=a,this.skirtSourceIndices=new Uint32Array(o)}};function S1(i,e,t){let{width:n,height:r}=i;e.width=n,e.height=r;let s=e.getContext("2d",{willReadFrequently:!0});s.drawImage(i,0,0);let{data:a}=s.getImageData(0,0,n,r);s.clearRect(0,0,n,r);let o=n+2,l=r+2,c=new Float32Array(o*l);for(let u=0;u<r;u++)for(let d=0;d<n;d++){let f=4*(u*n+d);c[(u+1)*o+d+1]=t(a[f],a[f+1],a[f+2])}for(let u=0;u<o;u++){let d=ye.clamp(u,1,o-2);c[u]=c[o+d],c[(l-1)*o+u]=c[(l-2)*o+d]}for(let u=1;u<l-1;u++)c[u*o]=c[u*o+1],c[u*o+o-1]=c[u*o+o-2];let h=new Sn(c,o,l,Os,fi);return h.minFilter=St,h.magFilter=St,h.needsUpdate=!0,h}function my(i,e,t,n){let{data:r,width:s,height:a}=i.image,o=e.image.data,l=s-2,c=a-2,h=1,u=s-2;t===-1?(h=0,u=0):t===1&&(h=s-1,u=s-1);let d=1,f=a-2;n===-1?(d=0,f=0):n===1&&(d=a-1,f=a-1);for(let p=d;p<=f;p++)for(let y=h;y<=u;y++)r[p*s+y]=o[(p-n*c)*s+(y-t*l)];i.needsUpdate=!0}var M1=class extends zf{constructor(i){super(),this.plugin=i,this.canvas=new OffscreenCanvas(1,1)}async fetchItem([i,e,t],n){let{plugin:r}=this,s=await r._source.fetchItem([i,e,t],n),a=S1(s.image,this.canvas,(o,l,c)=>r.decodeElevation(o,l,c));return r._source.disposeItem(s),this.stitchNeighbors(a,i,e,t),a}disposeItem(i){i&&i.dispose()}stitchNeighbors(i,e,t,n){let r=this.plugin._source.tiling,{tileCountX:s}=r.getLevel(n),a=r.flipY?-1:1;for(let o=-1;o<=1;o++)for(let l=-1;l<=1;l++){if(o===0&&l===0)continue;let c=(e+o+s)%s,h=t+l*a,u=this.get(c,h,n);u&&!(u instanceof Promise)&&(my(i,u,o,l),my(u,i,-o,-l))}}},w1=class extends En{constructor(i){super(i),this.onBeforeCompile=e=>{e.fragmentShader=e.fragmentShader.replace("#include <bumpmap_pars_fragment>",`
				#ifdef USE_BUMPMAP

					uniform sampler2D bumpMap;
					uniform float bumpScale;

					// relative determinant threshold below which the geometry is considered edge-on
					const float DEGENERATE_DET_EPSILON = 1e-3;

					// central differences at one texel spacing so the gradient interpolates across texels
					vec2 dHdxy_fwd() {

						vec2 dSTdx = dFdx( vBumpMapUv );
						vec2 dSTdy = dFdy( vBumpMapUv );

						vec2 texelSize = 1.0 / vec2( textureSize( bumpMap, 0 ) );
						vec2 dx = vec2( texelSize.x, 0.0 );
						vec2 dy = vec2( 0.0, texelSize.y );
						float gradU = ( texture2D( bumpMap, vBumpMapUv + dx ).x - texture2D( bumpMap, vBumpMapUv - dx ).x ) / ( 2.0 * texelSize.x );
						float gradV = ( texture2D( bumpMap, vBumpMapUv + dy ).x - texture2D( bumpMap, vBumpMapUv - dy ).x ) / ( 2.0 * texelSize.y );

						float dBx = bumpScale * ( gradU * dSTdx.x + gradV * dSTdx.y );
						float dBy = bumpScale * ( gradU * dSTdy.x + gradV * dSTdy.y );

						return vec2( dBx, dBy );

					}

					// unnormalized surface derivatives so the gradient resolves to the physical slope
					vec3 perturbNormalArb( vec3 surf_pos, vec3 surf_norm, vec2 dHdxy, float faceDirection ) {

						vec3 vSigmaX = dFdx( surf_pos.xyz );
						vec3 vSigmaY = dFdy( surf_pos.xyz );
						vec3 vN = surf_norm; // normalized

						vec3 R1 = cross( vSigmaY, vN );
						vec3 R2 = cross( vN, vSigmaX );

						float fDet = dot( vSigmaX, R1 ) * faceDirection;

						// Edge-on geometry, such as the tile skirts, has a degenerate determinant that
						// amplifies the gradient into a garbage normal, so fall back to the surface normal.
						if ( abs( fDet ) < DEGENERATE_DET_EPSILON * length( vSigmaX ) * length( vSigmaY ) ) {

							return surf_norm;

						}

						vec3 vGrad = sign( fDet ) * ( dHdxy.x * R1 + dHdxy.y * R2 );
						return normalize( abs( fDet ) * surf_norm - vGrad );

					}

				#endif
			`)}}},T1=class extends Yt{constructor(i){super(i),this.displacementMap=null,this.displacementScale=1,this.displacementBias=0,this.onBeforeCompile=e=>{e.uniforms.displacementMap={value:null},e.uniforms.displacementScale={value:1},e.uniforms.displacementBias={value:0},e.uniforms.displacementMapTransform={value:new Oe},e.vertexShader=e.vertexShader.replace("#include <uv_pars_vertex>",`
					#include <uv_pars_vertex>
					uniform sampler2D displacementMap;
					uniform float displacementScale;
					uniform float displacementBias;
				`).replace("#include <begin_vertex>",`
					#include <begin_vertex>
					transformed += normalize( normal ) * ( texture2D( displacementMap, uv ).x * displacementScale + displacementBias );
				`)}}},Zr=Symbol("TILE_X"),Js=Symbol("TILE_Y"),mr=Symbol("TILE_LEVEL"),yh=Symbol("HEIGHT_GRID"),_h=Symbol("SOURCE_TILE"),xh=Symbol("OVERLAY_RANGE"),vh=Symbol("OVERLAY_LEVEL"),vo=Symbol("HEIGHT_RANGE"),Kr=32,gy=-500,yy=9e3,Qs=2,zt=new P,$i=new P,Uf=new Et,Of=[],gr=[0,0],bh=null;function E1(){return bh===null&&(bh=new at(new wy(1,1,Kr,Kr),new Yt),bh.matrixAutoUpdate=!1),bh}function _y(i,e){return Math.min(Qs*Math.floor(i/Qs),e)}function xy(i,e){let{width:t,height:n}=i.image,r=t-2,s=n-2;return[(e[0]*r+1)/t,(e[1]*s+1)/n,(e[2]*r+1)/t,(e[3]*s+1)/n]}function Ff(i,e,t){let{data:n,width:r,height:s}=i.image,a=ye.clamp(e*r-.5,0,r-1),o=ye.clamp(t*s-.5,0,s-1),l=Math.floor(a),c=Math.floor(o),h=Math.min(l+1,r-1),u=Math.min(c+1,s-1),d=a-l,f=o-c,p=n[c*r+l]*(1-d)+n[c*r+h]*d,y=n[u*r+l]*(1-d)+n[u*r+h]*d;return p*(1-f)+y*f}var Ty=class{get shape(){return console.warn('TerrainRGBMeshPlugin: "shape" is deprecated. Use "projection" instead.'),this.projection==="ellipsoid"?"ellipsoid":"planar"}set shape(i){console.warn('TerrainRGBMeshPlugin: "shape" is deprecated. Use "projection" instead.'),this.projection=i==="planar"?"source":"ellipsoid"}get heightScale(){return this._heightScale}set heightScale(i){i!==this._heightScale&&(this._heightScale=i,this._updateHeightScale())}constructor(i={}){let{url:e=null,tileDimension:t=256,maxZoom:n=15,heightScale:r=1,overlay:s=null,applyOverlayTexture:a=!1,unlit:o=!1,shape:l=null,projection:c=null,endCaps:h=!0,useRecommendedSettings:u=!0}=i;this.name="TERRAIN_RGB_MESH_PLUGIN",this.priority=-10,this.tiles=null,this.url=e,this.tileDimension=t,this.maxZoom=n,this.overlay=s,this.applyOverlayTexture=a,this.unlit=o,this.projection=c??"ellipsoid",l!==null&&(console.warn('TerrainRGBMeshPlugin: "shape" is deprecated. Use "projection" instead.'),c===null&&(this.projection=l==="planar"?"source":"ellipsoid")),this.endCaps=h,this.useRecommendedSettings=u,this.heightScale=r,this._source=null,this._gridCache=new M1(this),this._tiling=null,this._maxSourceLevel=-1}init(i){this.useRecommendedSettings&&(i.errorTarget=1),this.tiles=i}async loadRootTileset(){this.overlay&&await this.overlay.init();let{url:i,tileDimension:e,maxZoom:t,overlay:n,applyOverlayTexture:r}=this;this._maxSourceLevel=Qs*Math.floor(t/Qs);let s=this._maxSourceLevel+Qs-1;n&&r&&(s=Math.max(s,n.tiling.maxLevel)),this._source=new by({url:i,tileDimension:e,levels:s+1}),this._source.fetchData=(u,d)=>{let f={priority:-performance.now()};return this.tiles.downloadQueue.add(u,f,()=>fetch(u,d),d.signal)},await this._source.init(),this._tiling=this._source.tiling;let{projection:a}=this,o=a==="ellipsoid"||a==="source"?this._tiling.projection:new To(a),[l,c]=o.getProjectedExtents(),h=l/c;if(this.projection!=="ellipsoid"){let u=new $T(o);u.scale.set(h,1),u.offset.set(-h/2,-.5),this.tiles.surface=u}return this.getTileset()}async parseToMesh(i,e,t,n,r){if(e[Zr]===void 0)return null;let s=e[Zr],a=e[Js],o=e[mr],l=_y(o,this._maxSourceLevel),c=2**(o-l),h=Math.floor(s/c),u=Math.floor(a/c),d;try{d=await this._gridCache.lock(h,u,l)}catch(v){if(v.name!=="AbortError")throw v;return null}if(r.aborted)return this._gridCache.release(h,u,l),null;e[yh]=d,e[_h]=[h,u,l];let f=this._getSubview(e),p=this._createTerrainMesh(e,f),y=d.clone();p.material.displacementMap=y,this.unlit||(p.material.bumpMap=y),e.children.forEach(v=>{v[vo]||(v[vo]=e[vo],this._updateBoundingVolume(v))});let{overlay:m,applyOverlayTexture:g}=this;if(m&&g){let v=this._tiling.getTileBounds(s,a,o,!0,!1);if(m.hasContent(v,o)){try{await m.lockTexture(v,o)}catch(D){if(D.name!=="AbortError")throw D;return this._releaseGrid(e),null}if(e[xh]=v,e[vh]=o,r.aborted)return m.releaseTexture(v,o),delete e[xh],delete e[vh],this._releaseGrid(e),null;let[S,_,M,w]=xy(d,f),E=this._tiling.getTileContentUVBounds(s,a,o),x=(E[2]-E[0])/(M-S),A=(E[3]-E[1])/(w-_),C=m.getTexture(v,o).clone();C.offset.set(E[0]-S*x,E[1]-_*A),C.repeat.set(x,A),p.material.map=C,p.material.needsUpdate=!0}}return p.material.displacementScale=this._heightScale,p.material.bumpScale=this._heightScale,p}raycastTile(i,e,t,n){let r=i[yh];return r?(e.traverse(s=>{if(s.isMesh){let a=E1(),o=s.geometry.attributes.position,l=s.geometry.attributes.normal,c=s.geometry.attributes.uv,h=a.geometry.attributes.position;for(let u=0,d=h.count;u<d;u++){let f=Ff(r,c.getX(u),c.getY(u))*this._heightScale;zt.fromBufferAttribute(o,u),$i.fromBufferAttribute(l,u),zt.addScaledVector($i,f),h.setXYZ(u,zt.x,zt.y,zt.z)}a.geometry.computeBoundingSphere(),a.matrixWorld.copy(s.matrixWorld),Of.length=0,a.raycast(t,Of),Of.forEach(u=>{u.object=s,n.push(u)})}}),!0):!1}sampleCartographicElevation(i,e){let t=this._tiling;if(t===null||!t.projection.isCartographic)return null;let{projection:n}=t,[r,s]=n.fromCartographicToNormalized(e,i,gr);for(let a=this._maxSourceLevel;a>=0;a-=Qs){let[o,l]=t.getTileAtPoint(r,s,a,!0),c=this._gridCache.get(o,l,a);if(c&&!(c instanceof Promise)){let[h,u,d,f]=t.getTileBounds(o,l,a,!0),{width:p,height:y}=c.image,m=(r-h)/(d-h),g=(s-u)/(f-u);return Ff(c,(m*(p-2)+1)/p,(g*(y-2)+1)/y)*this._heightScale}}return null}preprocessNode(i){let e=this._tiling.maxLevel;i[mr]<e&&i.parent!==null&&this.expandChildren(i)}disposeTile(i){let e=i[xh];this.overlay&&e&&(this.overlay.releaseTexture(e,i[vh]),delete i[xh],delete i[vh]),this._releaseGrid(i)}_releaseGrid(i){let e=i[_h];e&&(this._gridCache.release(...e),delete i[_h],delete i[yh])}dispose(){this.tiles.forEachLoadedModel((i,e)=>{this.disposeTile(e)})}_getSubview(i){let e=i[Zr],t=i[Js],n=i[mr],[r,s,a]=i[_h],o=this._tiling.getTileBounds(e,t,n,!0),l=this._tiling.getTileBounds(r,s,a,!0),c=1/(l[2]-l[0]),h=1/(l[3]-l[1]);return[(o[0]-l[0])*c,(o[1]-l[1])*h,(o[2]-l[0])*c,(o[3]-l[1])*h]}_createTerrainMesh(i,e){let{tiles:t,endCaps:n,unlit:r,_heightScale:s,_tiling:a}=this,{surface:o}=t,{projection:l}=a,c=i[mr],h=i[Zr],u=i[Js],[,d,,f]=a.getTileBounds(h,u,c),[p,y,m,g]=a.getTileBounds(h,u,c,!0,!0),v=i[yh],[S,_,M,w]=xy(v,e),E=new wy(1,1,Kr,Kr),x=new at(E,r?new T1:new w1);i.engineData.boundingVolume.getSphere(Uf),x.position.copy(Uf.center);let A=n&&!(o.projection&&o.projection.isMercator),{position:C,normal:D,uv:U}=E.attributes,{surfaceVertexCount:I,skirtSourceIndices:L}=E,k=1/0,H=-1/0;for(let Y=0;Y<I;Y++){let q=Y%33,K=Math.floor(Y/33),N=q/Kr,ie=1-K/Kr,re=l.fromNormalizedToCartographic(ye.mapLinear(N,0,1,p,m),ye.mapLinear(ie,0,1,y,g),gr),De=re[0],Te=re[1];if(l.isMercator&&A&&(g===1&&ie===1&&(Te=Math.PI/2),y===0&&ie===0&&(Te=-Math.PI/2)),l.isMercator&&ie!==0&&ie!==1){let gt=l.fromNormalizedToCartographic(.5,1,gr)[1],He=1/Kr,Qe=ye.mapLinear(ie-He,0,1,d,f),dt=ye.mapLinear(ie+He,0,1,d,f);Te>gt&&Qe<gt&&(Te=gt),Te<-gt&&dt>-gt&&(Te=-gt)}let[$e,$]=l.fromCartographicToNormalized(De,Te,gr),ee=ye.mapLinear($e,p,m,0,1),_e=ye.mapLinear($,y,g,0,1),Be=ye.mapLinear(ee,0,1,S,M),xe=ye.mapLinear(_e,0,1,_,w),Ve=Ff(v,Be,xe);Ve<k&&(k=Ve),Ve>H&&(H=Ve),o.getCartographicToPosition(Te,De,0,zt).sub(Uf.center),o.getCartographicToNormal(Te,De,$i),C.setXYZ(Y,zt.x,zt.y,zt.z),D.setXYZ(Y,$i.x,$i.y,$i.z),U.setXY(Y,Be,xe)}let X=i.geometricError+(H-k)*s;for(let Y=0,q=L.length;Y<q;Y++){let K=L[Y],N=I+Y;zt.fromBufferAttribute(C,K),$i.fromBufferAttribute(D,K),zt.addScaledVector($i,-X),C.setXYZ(N,zt.x,zt.y,zt.z),D.setXYZ(N,$i.x,$i.y,$i.z),U.setXY(N,U.getX(K),U.getY(K))}return i[vo]={min:k,max:H},this._updateBoundingVolume(i),x}_updateBoundingVolume(i){let e=this._heightScale,t=i[mr]===-1?0:i.geometricError,n=i[vo],r,s;n?(r=n.min*e-t-(n.max-n.min)*e,s=n.max*e+t):(r=gy*e-t,s=yy*e);let{boundingVolume:a,engineData:o}=i;if(a.region){let l=a.region;l[4]=r,l[5]=s,o&&o.boundingVolume&&o.boundingVolume.setRegionData(this.tiles.ellipsoid,...l)}else{let l=a.box;l[2]=(r+s)/2,l[11]=(s-r)/2,o&&o.boundingVolume&&o.boundingVolume.setObbData(l,o.transform)}}_updateHeightScale(){let{tiles:i}=this;i&&(i.forEachLoadedModel(e=>{e.traverse(t=>{t.isMesh&&(t.material.displacementScale=this._heightScale,t.material.bumpScale=this._heightScale)})}),i.traverse(e=>{this._updateBoundingVolume(e)},null,!1))}getTileset(){let{tiles:i,_tiling:e}=this,t=e.minLevel,{tileCountX:n,tileCountY:r}=e.getLevel(t),s=[];for(let o=0;o<n;o++)for(let l=0;l<r;l++){let c=this.createChild(o,l,t);c!==null&&s.push(c)}let a={asset:{version:"1.1"},geometricError:1/0,root:{refine:"REPLACE",geometricError:1/0,boundingVolume:this.createBoundingVolume(0,0,-1),children:s,[mr]:-1,[Zr]:0,[Js]:0}};return i.preprocessTileset(a,""),a}getUrl(i,e,t){let n=_y(t,this._maxSourceLevel),r=2**(t-n);return this._source.getUrl(Math.floor(i/r),Math.floor(e/r),n)}fetchData(){return new ArrayBuffer}createBoundingVolume(i,e,t,n=0){let{_tiling:r,endCaps:s,tiles:a}=this,{surface:o}=a,l=t===-1,c=gy*this.heightScale-n,h=yy*this.heightScale;if(o.isEllipsoid){let u,d;return l?(u=r.getContentBounds(!0),d=r.getContentBounds()):(u=r.getTileBounds(i,e,t,!0,!0),d=r.getTileBounds(i,e,t,!1,!0)),s&&(u[3]===1&&(d[3]=Math.PI/2),u[1]===0&&(d[1]=-Math.PI/2)),{region:[...d,c,h]}}else{let u;u=l?r.getContentBounds(!0):r.getTileBounds(i,e,t,!0);let[d,f,p,y]=u,m=ye.clamp(r.projection.fromCartographicToNormalized(0,0,gr)[1],f,y),g=1/0,v=1/0,S=-1/0,_=-1/0;for(let w of[f,y,m])for(let E of[d,p]){let[x,A]=r.projection.fromNormalizedToCartographic(E,w,gr),C=A;s&&!o.projection.isMercator&&(w===1&&(C=Math.PI/2),w===0&&(C=-Math.PI/2)),o.getCartographicToPosition(C,x,0,zt),g=Math.min(g,zt.x),v=Math.min(v,zt.y),S=Math.max(S,zt.x),_=Math.max(_,zt.y)}let M={box:[(g+S)/2,(v+_)/2,(c+h)/2,(S-g)/2,0,0,0,(_-v)/2,0,0,0,(h-c)/2]};return M.cartographicRange=l?r.getContentBounds():r.getTileBounds(i,e,t),M}}createChild(i,e,t){let{_tiling:n,tiles:r}=this,{projection:s}=n,{surface:a}=r;if(!n.getTileExists(i,e,t))return null;let o;if(a.isEllipsoid){let[l,c,h,u]=n.getTileBounds(i,e,t,!0),{tilePixelWidth:d,tilePixelHeight:f}=n.getLevel(t),p=(h-l)/d,y=(u-c)/f,[,m,g,v]=n.getTileBounds(i,e,t),S=m>0==v>0?Math.min(Math.abs(m),Math.abs(v)):0,_=s.fromCartographicToNormalized(0,S,gr)[1],[M,w]=s.getDerivativeAtNormalizedPoint(l,_,gr),[E,x]=HT(r.ellipsoid,S,g);o=Math.max(p*M*E,y*w*x)}else{let{pixelWidth:l,pixelHeight:c}=n.getLevel(t);o=Math.max(a.scale.x/l,a.scale.y/c)}return{refine:"REPLACE",geometricError:o,boundingVolume:this.createBoundingVolume(i,e,t,o),content:{uri:this.getUrl(i,e,t)},children:[],[Zr]:i,[Js]:e,[mr]:t}}expandChildren(i){let e=i[mr],t=i[Zr],n=i[Js],{tileSplitX:r,tileSplitY:s}=this._tiling.getLevel(e);for(let a=0;a<r;a++)for(let o=0;o<s;o++){let l=this.createChild(r*t+a,s*n+o,e+1);l&&i.children.push(l)}}decodeElevation(i,e,t){return-1e4+(i*65536+e*256+t)*.1}},qf=class extends Ty{constructor(i={}){super(i),this.name="TERRARIUM_MESH_PLUGIN"}decodeElevation(i,e,t){return i*256+e+t/256-32768}};var wI=Math.PI/180;var TI=Ws*Math.PI*2;var EI=Ws*Math.PI*2;var Ay={full:{radius:6e3,zoom:12,spacing:[[2e3,30],[4e3,60],[1/0,120]],imagery:128},phone:{radius:3e3,zoom:10,spacing:[[1500,60],[1/0,120]],imagery:128}},Cy=15,A1=32,Yf=512;function C1(i,e){for(let[t,n]of i.spacing)if(e<=t)return n;return i.spacing[i.spacing.length-1][1]}function Ry(i,e,t){return e*Yf/A1>C1(i,t)*1.0001}var jf=6378137,Ey=1/298.257223563,Mh=Ey*(2-Ey);function Py(i,e,t){let n=e*Math.PI/180,r=i*Math.PI/180,s=Math.sin(n),a=Math.cos(n),o=jf/Math.sqrt(1-Mh*s*s);return[(o+t)*a*Math.cos(r),(o+t)*a*Math.sin(r),(o*(1-Mh)+t)*s]}function Iy(i,e){let[t,n,r,s,a,o]=i.affine,l=t+n*e.cx+r*e.cy,c=s+a*e.cx+o*e.cy,h=c*Math.PI/180,u=l*Math.PI/180,d=Math.sin(h),f=Math.cos(h),p=Math.sin(u),y=Math.cos(u),m=[-p,y,0],g=[-d*y,-d*p,f],v=[f*y,f*p,d],S=Py(l,c,e.h0),_=Math.sqrt(1-Mh*d*d),M=jf/_,w=jf*(1-Mh)/(_*_*_),E=Math.PI/180*(M+e.h0)*f,x=Math.PI/180*(w+e.h0),A=E*n,C=E*r,D=x*a,U=x*o,I=A*U-C*D,L=U/I,k=-C/I,H=-D/I,X=A/I,Y=[[L,k,0],[0,0,1],[-H,-X,0]],q=[0,0,0],K=[];for(let N=0;N<3;N++){let ie=[0,1,2].map(re=>Y[N][0]*m[re]+Y[N][1]*g[re]+Y[N][2]*v[re]);K.push(ie[0],ie[1],ie[2],q[N]-(ie[0]*S[0]+ie[1]*S[1]+ie[2]*S[2]))}return K.push(0,0,0,1),K}function Ly(i,e){let[t,n,r,s,a,o]=i.affine;return Py(t+n*e.cx+r*e.cy,s+a*e.cx+o*e.cy,e.h0)}function $f(i){let{left:e,top:t,res:n,width:r,height:s}=i.meta,a=1/0,o=-1,l=1/0,c=-1;for(let h=0;h<s;h++){let u=h*i.cols;for(let d=0;d<r;d++)Number.isNaN(i.heights[u+d])||(h<a&&(a=h),h>o&&(o=h),d<l&&(l=d),d>c&&(c=d))}return o<0?null:{x0:e+l*n,x1:e+(c+1)*n,y0:t-(o+1)*n,y1:t-a*n}}function Dy(i,e){let t=i.x0-e.cx,n=i.x1-e.cx,r=-(i.y1-e.cy),s=-(i.y0-e.cy);return[{normal:[-1,0,0],constant:t},{normal:[1,0,0],constant:-n},{normal:[0,0,-1],constant:r},{normal:[0,0,1],constant:-s}]}function Ny(i,e,t){if(i==="esri"&&t)return[{type:"xyz",url:Fo(t),levels:Oo+1}];if(i!=="ortho"||!e)return[];let n=[];return e.base&&n.push({type:"xyz",url:e.base.url,levels:e.base.max_zoom+1}),e.url&&n.push({type:"wms",url:e.url,layer:e.layer,format:e.base?"image/png":"image/jpeg",transparent:!!e.base}),n}function Uy(i,e=8){let t=$f(i);if(!t)return[];let{left:n,top:r,res:s}=i.meta,a=Math.round((t.x0-n)/s),o=Math.round((t.x1-n)/s)-1,l=Math.round((r-t.y1)/s),c=Math.round((r-t.y0)/s)-1,h=[],u=(d,f)=>{let p=i.heights[d*i.cols+f];Number.isNaN(p)||h.push({x:n+(f+.5)*s,y:r-(d+.5)*s,h:p})};for(let d=a;d<=o;d+=e)u(l,d),u(c,d);for(let d=l+e;d<c;d+=e)u(d,a),u(d,o);return h}function Oy(i){if(!i.length)return null;let e=i.map(Math.abs).sort((n,r)=>n-r),t=n=>e[Math.min(e.length-1,Math.floor(n*(e.length-1)+.5))];return{median:t(.5),p90:t(.9)}}function Fy(){let i=document.querySelector('meta[name="findaline-3d-ring"]'),e=i?i.content.trim():"";return e&&e!=="off"?e:null}var Zf=class extends qf{constructor(t,n){super({url:t,tileDimension:Yf,maxZoom:Cy,useRecommendedSettings:!1});this.textureZoom=n}async loadRootTileset(){let t=await super.loadRootTileset();return this._maxSourceLevel=Math.min(this._maxSourceLevel,this.textureZoom),t}};function R1(i,e){return{name:"FINDALINE_RING_REGION",calculateTileViewError(t,n){let r=t.engineData.boundingVolume.distanceToPoint(e);return n.inView=r<=i.radius,n.error=n.inView&&Ry(i,t.geometricError,r)?1/0:0,n.distance=r,!0}}}function P1(i){return i.type==="xyz"?new Hf({url:i.url,levels:i.levels}):new Wf({url:i.url,layer:i.layer,crs:"EPSG:4326",version:"1.3.0",styles:"",format:i.format,transparent:i.transparent})}function By(i,e,t){let n=Ay[i.level],r=i.toolbar.closest(".ui"),s=U=>{r&&(U===null?delete r.dataset.ring:r.dataset.ring=U)},a=new Af;a.errorTarget=Number.MAX_VALUE,a.loadSiblings=!1,a.loadAncestors=!1;let o=new Zf(t,n.zoom),l=new Vf({overlays:[],renderer:i.renderer,resolution:n.imagery,enableTileSplitting:!1}),c=new P(...Ly(i.meta,i.origin));a.registerPlugin(o),a.registerPlugin(l),a.registerPlugin(new Xf),a.registerPlugin(R1(n,c));let h=a.group;h.matrixAutoUpdate=!1,h.matrix.copy(new ge().set(...Iy(i.meta,i.origin))),h.matrixWorldNeedsUpdate=!0,h.name="ring";let u=$f(i.patch),d=u?Dy(u,i.origin).map(U=>new qt(new P(...U.normal),U.constant)):[];d.length&&(i.renderer.localClippingEnabled=!0);let f=getComputedStyle(i.toolbar).getPropertyValue("--terrain").trim()||"#bba680",p=({scene:U})=>{U.traverse(I=>{let L=I;if(L.isMesh)for(let k of[].concat(L.material))k.clippingPlanes=d,k.clipIntersection=!0,k.color?.set(f)}),i.invalidate()},y=()=>i.invalidate(),m=!1,g=()=>{s(m?"updating":"loading"),i.keepDrawing("ring",!0)},v=()=>{i.keepDrawing("ring",!1),m=!0,_(),r&&(r.dataset.ringTiles=String(a.visibleTiles.size)),s("loaded"),i.invalidate()},S=()=>{r&&(r.dataset.ringErrors=String(Number(r.dataset.ringErrors||0)+1))};a.addEventListener("load-model",p),a.addEventListener("needs-render",y),a.addEventListener("needs-update",y),a.addEventListener("tiles-load-start",g),a.addEventListener("tiles-load-end",v),a.addEventListener("load-error",S);let _=()=>{if(!r)return;let U=[];for(let k of Uy(i.patch)){let[H,X]=i.lonLat(k.x,k.y),Y=o.sampleCartographicElevation(X*Math.PI/180,H*Math.PI/180);Y!==null&&Number.isFinite(Y)&&U.push(Y-k.h)}let I=Oy(U);if(!I)return;let L=[...U].sort((k,H)=>k-H)[Math.floor(U.length/2)];r.dataset.ringOffset=JSON.stringify({...I,signed:L,samples:U.length})},M=[],w=Nc(i.meta.ortho),E=Uo(),x=U=>{for(let I of M)l.deleteOverlay(I);M=Ny(U,w,E).map(P1),M.forEach((I,L)=>l.addOverlay(I,L)),i.invalidate()};x(e.current);let A=e.onChange(x);i.add(h),a.setCamera(i.camera);let C=i.beforeDraw(()=>{a.setResolutionFromRenderer(i.camera,i.renderer),i.camera.updateMatrixWorld(),a.update()});i.credits.set(bd,Ug,Ng),s("loading"),i.invalidate();let D=!1;return{dispose(){D||(D=!0,C(),A(),a.removeEventListener("load-model",p),a.removeEventListener("needs-render",y),a.removeEventListener("needs-update",y),a.removeEventListener("tiles-load-start",g),a.removeEventListener("tiles-load-end",v),a.removeEventListener("load-error",S),i.keepDrawing("ring",!1),i.remove(h),a.dispose(),i.credits.remove(bd),s(null))}}}var Eo=class{constructor(e=257){this.gridSize=e;let t=e-1;if(t&t-1)throw new Error(`Expected grid size to be 2^n+1, got ${e}.`);this.numTriangles=t*t*2-2,this.numParentTriangles=this.numTriangles-t*t,this.indices=new Uint32Array(this.gridSize*this.gridSize),this.coords=new Uint16Array(this.numTriangles*4);for(let n=0;n<this.numTriangles;n++){let r=n+2,s=0,a=0,o=0,l=0,c=0,h=0;for(r&1?o=l=c=t:s=a=h=t;(r>>=1)>1;){let d=s+o>>1,f=a+l>>1;r&1?(o=s,l=a,s=c,a=h):(s=o,a=l,o=c,l=h),c=d,h=f}let u=n*4;this.coords[u+0]=s,this.coords[u+1]=a,this.coords[u+2]=o,this.coords[u+3]=l}}createTile(e){return new Kf(e,this)}},Kf=class{constructor(e,t){let n=t.gridSize;if(e.length!==n*n)throw new Error(`Expected terrain data of length ${n*n} (${n} x ${n}), got ${e.length}.`);this.terrain=e,this.martini=t,this.errors=new Float32Array(e.length),this.update()}update(){let{numTriangles:e,numParentTriangles:t,coords:n,gridSize:r}=this.martini,{terrain:s,errors:a}=this;for(let o=e-1;o>=0;o--){let l=o*4,c=n[l+0],h=n[l+1],u=n[l+2],d=n[l+3],f=c+u>>1,p=h+d>>1,y=f+p-h,m=p+c-f,g=(s[h*r+c]+s[d*r+u])/2,v=p*r+f,S=Math.abs(g-s[v]);if(a[v]=Math.max(a[v],S),o<t){let _=(h+m>>1)*r+(c+y>>1),M=(d+m>>1)*r+(u+y>>1);a[v]=Math.max(a[v],a[_],a[M])}}}getMesh(e=0){let{gridSize:t,indices:n}=this.martini,{errors:r}=this,s=0,a=0,o=t-1;n.fill(0);function l(f,p,y,m,g,v){let S=f+y>>1,_=p+m>>1;Math.abs(f-g)+Math.abs(p-v)>1&&r[_*t+S]>e?(l(g,v,f,p,S,_),l(y,m,g,v,S,_)):(n[p*t+f]=n[p*t+f]||++s,n[m*t+y]=n[m*t+y]||++s,n[v*t+g]=n[v*t+g]||++s,a++)}l(0,0,o,o,o,0),l(o,o,0,0,0,o);let c=new Uint16Array(s*2),h=new Uint32Array(a*3),u=0;function d(f,p,y,m,g,v){let S=f+y>>1,_=p+m>>1;if(Math.abs(f-g)+Math.abs(p-v)>1&&r[_*t+S]>e)d(g,v,f,p,S,_),d(y,m,g,v,S,_);else{let M=n[p*t+f]-1,w=n[m*t+y]-1,E=n[v*t+g]-1;c[2*M]=f,c[2*M+1]=p,c[2*w]=y,c[2*w+1]=m,c[2*E]=g,c[2*E+1]=v,h[u++]=M,h[u++]=w,h[u++]=E}}return d(0,0,o,o,o,0),d(o,o,0,0,0,o),{vertices:c,triangles:h}}};var ky=null;function I1(){return ky||(ky=new Eo(513))}function zy(i){return[(i.rows-1)/512,(i.cols-1)/512]}function L1(i,e,t){let n=(e.x-i.left)/i.res,r=(i.top-e.y)/i.res,s=(t.x-i.left)/i.res,a=(i.top-t.y)/i.res,o=Math.floor(n),l=Math.floor(r),c=Math.floor(s),h=Math.floor(a),u=s-n,d=a-r,f=Math.sign(u),p=Math.sign(d),y=u?Math.abs(1/u):1/0,m=d?Math.abs(1/d):1/0,g=u>0?(o+1-n)/u:u<0?(n-o)/-u:1/0,v=d>0?(l+1-r)/d:d<0?(r-l)/-d:1/0,S=[[l,o]],_=Math.abs(c-o)+Math.abs(h-l)+2;for(let M=0;(l!==h||o!==c)&&M<_&&!(Math.min(g,v)>1);M++)Math.abs(g-v)<1e-12?(S.push([l,o+f],[l+p,o]),l+=p,o+=f,g+=y,v+=m):g<v?(o+=f,g+=y):(l+=p,v+=m),S.push([l,o]);return S}function D1(i,e=i.meta.anchors){let{heights:t,cols:n,rows:r}=i,s=new Uint8Array(n*r),a=L1(i.meta,e[0],e[1]).filter(([o,l])=>o>=0&&l>=0&&o<r&&l<n);for(let[o,l]of a)s[o*n+l]=1;for(let o=0;o<r;o++)for(let l=0;l<n;l++){let c=o*n+l;if(!Number.isNaN(t[c]))for(let h=-1;h<=1;h++){let u=o+h;if(!(u<0||u>=r))for(let d=-1;d<=1;d++){let f=l+d;f<0||f>=n||!Number.isNaN(t[u*n+f])||(s[c]=1,s[u*n+f]=1)}}}return{all:s,line:a}}function N1(i,e,t,n,r){let s=513,a=e*512,o=t*512,{heights:l,cols:c}=i,h=new Float32Array(s*s),u=!1,d=!1;for(let p=0;p<s;p++)for(let y=0;y<s;y++){let m=l[(a+p)*c+o+y];Number.isNaN(m)?h[p*s+y]=r:(h[p*s+y]=m,u=!0)}if(!u)return null;let f=I1().createTile(h);for(let p=0;p<s;p++)for(let y=0;y<s;y++)n[(a+p)*c+o+y]&&(f.errors[p*s+y]=1/0,d=!0);return d&&f.update(),f}function U1(i,e,t,n,r){let{heights:s,cols:a,rows:o}=i,l=i.meta.res,c=s[e*a+t],h=(y,m)=>y<0||m<0||y>=o||m>=a?NaN:s[y*a+m],u=(y,m)=>!Number.isNaN(y)&&!Number.isNaN(m)?(m-y)/(2*l):!Number.isNaN(m)&&!Number.isNaN(c)?(m-c)/l:!Number.isNaN(y)&&!Number.isNaN(c)?(c-y)/l:0,d=u(h(e,t-1),h(e,t+1)),f=u(h(e+1,t),h(e-1,t)),p=Math.hypot(d,1,f);n[r]=-d/p,n[r+1]=1/p,n[r+2]=f/p}function O1(i){return 2+4*i}function F1(i,e,t,n,r,s,a=[]){let o=t*512,l=n*512,{heights:c,cols:h}=i,{left:u,top:d,res:f}=i.meta,[p,y]=zy(i),{vertices:m,triangles:g}=r.getMesh(s),v=m.length/2,S=new Int32Array(v).fill(-1),_=N=>Number.isNaN(c[(o+m[2*N+1])*h+l+m[2*N]]),M=[],w=0;for(let N=0;N<g.length;N+=3){let ie=g[N],re=g[N+1],De=g[N+2];if(!(_(ie)||_(re)||_(De)))for(let Te of[ie,re,De])S[Te]<0&&(S[Te]=w++),M.push(S[Te])}let E=new Int32Array(w*2);for(let N=0;N<v;N++)S[N]>=0&&(E[2*S[N]]=m[2*N],E[2*S[N]+1]=m[2*N+1]);let x=[],A=(N,ie)=>{let re=[];for(let De=0;De<w;De++)N(E[2*De],E[2*De+1])&&re.push(De);return re.sort((De,Te)=>ie(E[2*De],E[2*De+1])-ie(E[2*Te],E[2*Te+1])),re};t>0&&x.push({along:A((N,ie)=>ie===0,N=>N),at:N=>o*h+l+N}),t<p-1&&x.push({along:A((N,ie)=>ie===512,N=>N),at:N=>(o+512)*h+l+N}),n>0&&x.push({along:A(N=>N===0,(N,ie)=>ie),at:N=>(o+N)*h+l}),n<y-1&&x.push({along:A(N=>N===512,(N,ie)=>ie),at:N=>(o+N)*h+l+512});let C=[];for(let{along:N,at:ie}of x)for(let re=1;re<N.length;re++){let De=N[re-1],Te=N[re],$e=E[2*De]===E[2*Te]?E[2*De+1]:E[2*De],$=E[2*De]===E[2*Te]?E[2*Te+1]:E[2*Te],ee=!0;for(let _e=$e;_e<=$&&ee;_e++)ee=!Number.isNaN(c[ie(_e)]);ee&&C.push([De,Te])}let D=new Int32Array(w).fill(-1),U=w;for(let[N,ie]of C)D[N]<0&&(D[N]=U++),D[ie]<0&&(D[ie]=U++);let I=new Float32Array(U*3),L=new Float32Array(U*3),k=new Float64Array(U*2),H=new Int32Array(U),X=O1(s);for(let N=0;N<w;N++){let ie=o+E[2*N+1],re=l+E[2*N],De=ie*h+re,Te=u+(re+.5)*f,$e=d-(ie+.5)*f;I[3*N]=Te-e.cx,I[3*N+1]=c[De]-e.h0,I[3*N+2]=-($e-e.cy),k[2*N]=Te,k[2*N+1]=$e,H[N]=De,U1(i,ie,re,L,3*N)}for(let N=0;N<w;N++){let ie=D[N];ie<0||(I[3*ie]=I[3*N],I[3*ie+1]=I[3*N+1]-X,I[3*ie+2]=I[3*N+2],L.copyWithin(3*ie,3*N,3*N+3),k[2*ie]=k[2*N],k[2*ie+1]=k[2*N+1],H[ie]=H[N])}let Y=new Uint32Array(M.length+C.length*6);Y.set(M);let q=M.length;for(let[N,ie]of C)Y[q++]=N,Y[q++]=ie,Y[q++]=D[ie],Y[q++]=N,Y[q++]=D[ie],Y[q++]=D[N];let K=a.some(([N,ie])=>N>=o&&N<=o+512&&ie>=l&&ie<=l+512);return{ci:t,cj:n,positions:I,normals:L,grid:k,samples:H,indices:Y,surfaceVertices:w,surfaceIndices:M.length,hasLine:K}}function Vy(i,e,t,n){let{all:r,line:s}=D1(i),[a,o]=zy(i),l=[];for(let h=0;h<a;h++)for(let u=0;u<o;u++){let d=N1(i,h,u,r,e.h0);d&&l.push({ci:h,cj:u,tile:d})}let c=t;for(let h=0;;h++){let u=l.map(({ci:f,cj:p,tile:y})=>F1(i,e,f,p,y,c,s)).filter(f=>f.surfaceIndices>0),d=u.reduce((f,p)=>f+p.positions.length/3,0);if(d<=n||h>=12)return{chunks:u,maxError:c,vertices:d};c*=1.5}}var Gy={type:"change"},Qf={type:"start"},Wy={type:"end"},wh=new vi,Hy=new qt,B1=Math.cos(70*ye.DEG2RAD),Gt=new P,Ti=2*Math.PI,ut={NONE:-1,ROTATE:0,DOLLY:1,PAN:2,TOUCH_ROTATE:3,TOUCH_PAN:4,TOUCH_DOLLY_PAN:5,TOUCH_DOLLY_ROTATE:6},Jf=1e-6,Th=class extends Ba{constructor(e,t=null){super(e,t),this.state=ut.NONE,this.target=new P,this.cursor=new P,this.minDistance=0,this.maxDistance=1/0,this.minZoom=0,this.maxZoom=1/0,this.minTargetRadius=0,this.maxTargetRadius=1/0,this.minPolarAngle=0,this.maxPolarAngle=Math.PI,this.minAzimuthAngle=-1/0,this.maxAzimuthAngle=1/0,this.enableDamping=!1,this.dampingFactor=.05,this.enableZoom=!0,this.zoomSpeed=1,this.enableRotate=!0,this.rotateSpeed=1,this.keyRotateSpeed=1,this.enablePan=!0,this.panSpeed=1,this.screenSpacePanning=!0,this.keyPanSpeed=7,this.zoomToCursor=!1,this.autoRotate=!1,this.autoRotateSpeed=2,this.keys={LEFT:"ArrowLeft",UP:"ArrowUp",RIGHT:"ArrowRight",BOTTOM:"ArrowDown"},this.mouseButtons={LEFT:nr.ROTATE,MIDDLE:nr.DOLLY,RIGHT:nr.PAN},this.touches={ONE:rr.ROTATE,TWO:rr.DOLLY_PAN},this.target0=this.target.clone(),this.position0=this.object.position.clone(),this.zoom0=this.object.zoom,this._cursorStyle="auto",this._domElementKeyEvents=null,this._lastPosition=new P,this._lastQuaternion=new Ot,this._lastTargetPosition=new P,this._quat=new Ot().setFromUnitVectors(e.up,new P(0,1,0)),this._quatInverse=this._quat.clone().invert(),this._spherical=new ir,this._sphericalDelta=new ir,this._scale=1,this._panOffset=new P,this._rotateStart=new Se,this._rotateEnd=new Se,this._rotateDelta=new Se,this._panStart=new Se,this._panEnd=new Se,this._panDelta=new Se,this._dollyStart=new Se,this._dollyEnd=new Se,this._dollyDelta=new Se,this._dollyDirection=new P,this._mouse=new Se,this._performCursorZoom=!1,this._pointers=[],this._pointerPositions={},this._controlActive=!1,this._onPointerMove=z1.bind(this),this._onPointerDown=k1.bind(this),this._onPointerUp=V1.bind(this),this._onContextMenu=Y1.bind(this),this._onMouseWheel=W1.bind(this),this._onKeyDown=X1.bind(this),this._onTouchStart=q1.bind(this),this._onTouchMove=j1.bind(this),this._onMouseDown=G1.bind(this),this._onMouseMove=H1.bind(this),this._interceptControlDown=$1.bind(this),this._interceptControlUp=Z1.bind(this),this.domElement!==null&&this.connect(this.domElement),this.update()}set cursorStyle(e){this._cursorStyle=e,e==="grab"?this.domElement.style.cursor="grab":this.domElement.style.cursor="auto"}get cursorStyle(){return this._cursorStyle}connect(e){super.connect(e),this.domElement.addEventListener("pointerdown",this._onPointerDown),this.domElement.addEventListener("pointercancel",this._onPointerUp),this.domElement.addEventListener("contextmenu",this._onContextMenu),this.domElement.addEventListener("wheel",this._onMouseWheel,{passive:!1}),this.domElement.getRootNode().addEventListener("keydown",this._interceptControlDown,{passive:!0,capture:!0}),this.domElement.style.touchAction="none"}disconnect(){this.state=ut.NONE,this.domElement.removeEventListener("pointerdown",this._onPointerDown),this.domElement.ownerDocument.removeEventListener("pointermove",this._onPointerMove),this.domElement.ownerDocument.removeEventListener("pointerup",this._onPointerUp),this.domElement.removeEventListener("pointercancel",this._onPointerUp),this.domElement.removeEventListener("wheel",this._onMouseWheel),this.domElement.removeEventListener("contextmenu",this._onContextMenu),this.stopListenToKeyEvents();let e=this.domElement.getRootNode();e.removeEventListener("keydown",this._interceptControlDown,{capture:!0}),e.removeEventListener("keyup",this._interceptControlUp,{capture:!0}),this._controlActive=!1,this._pointers.length=0,this._pointerPositions={},this.domElement.style.touchAction="",this.domElement.style.cursor="auto"}dispose(){this.disconnect()}getPolarAngle(){return this._spherical.phi}getAzimuthalAngle(){return this._spherical.theta}getDistance(){return this.object.position.distanceTo(this.target)}listenToKeyEvents(e){e.addEventListener("keydown",this._onKeyDown),this._domElementKeyEvents=e}stopListenToKeyEvents(){this._domElementKeyEvents!==null&&(this._domElementKeyEvents.removeEventListener("keydown",this._onKeyDown),this._domElementKeyEvents=null)}saveState(){this.target0.copy(this.target),this.position0.copy(this.object.position),this.zoom0=this.object.zoom}reset(){this.target.copy(this.target0),this.object.position.copy(this.position0),this.object.zoom=this.zoom0,this.object.updateProjectionMatrix(),this.dispatchEvent(Gy),this.update(),this.state=ut.NONE}pan(e,t){this._pan(e,t),this.update()}dollyIn(e){this._dollyIn(e),this.update()}dollyOut(e){this._dollyOut(e),this.update()}rotateLeft(e){this._rotateLeft(e),this.update()}rotateUp(e){this._rotateUp(e),this.update()}update(e=null){let t=this.object.position;Gt.copy(t).sub(this.target),Gt.applyQuaternion(this._quat),this._spherical.setFromVector3(Gt),this.autoRotate&&this.state===ut.NONE&&this._rotateLeft(this._getAutoRotationAngle(e)),this.enableDamping?(this._spherical.theta+=this._sphericalDelta.theta*this.dampingFactor,this._spherical.phi+=this._sphericalDelta.phi*this.dampingFactor):(this._spherical.theta+=this._sphericalDelta.theta,this._spherical.phi+=this._sphericalDelta.phi);let n=this.minAzimuthAngle,r=this.maxAzimuthAngle;isFinite(n)&&isFinite(r)&&(n<-Math.PI?n+=Ti:n>Math.PI&&(n-=Ti),r<-Math.PI?r+=Ti:r>Math.PI&&(r-=Ti),n<=r?this._spherical.theta=Math.max(n,Math.min(r,this._spherical.theta)):this._spherical.theta=this._spherical.theta>(n+r)/2?Math.max(n,this._spherical.theta):Math.min(r,this._spherical.theta)),this._spherical.phi=Math.max(this.minPolarAngle,Math.min(this.maxPolarAngle,this._spherical.phi)),this._spherical.makeSafe(),this.enableDamping===!0?this.target.addScaledVector(this._panOffset,this.dampingFactor):this.target.add(this._panOffset),this.target.sub(this.cursor),this.target.clampLength(this.minTargetRadius,this.maxTargetRadius),this.target.add(this.cursor);let s=!1;if(this.zoomToCursor&&this._performCursorZoom||this.object.isOrthographicCamera)this._spherical.radius=this._clampDistance(this._spherical.radius);else{let a=this._spherical.radius;this._spherical.radius=this._clampDistance(this._spherical.radius*this._scale),s=a!=this._spherical.radius}if(Gt.setFromSpherical(this._spherical),Gt.applyQuaternion(this._quatInverse),t.copy(this.target).add(Gt),this.object.lookAt(this.target),this.enableDamping===!0?(this._sphericalDelta.theta*=1-this.dampingFactor,this._sphericalDelta.phi*=1-this.dampingFactor,this._panOffset.multiplyScalar(1-this.dampingFactor)):(this._sphericalDelta.set(0,0,0),this._panOffset.set(0,0,0)),this.zoomToCursor&&this._performCursorZoom){let a=null;if(this.object.isPerspectiveCamera){let o=Gt.length();a=this._clampDistance(o*this._scale);let l=o-a;this.object.position.addScaledVector(this._dollyDirection,l),this.object.updateMatrixWorld(),s=!!l}else if(this.object.isOrthographicCamera){let o=new P(this._mouse.x,this._mouse.y,0);o.unproject(this.object);let l=this.object.zoom;this.object.zoom=Math.max(this.minZoom,Math.min(this.maxZoom,this.object.zoom/this._scale)),this.object.updateProjectionMatrix(),s=l!==this.object.zoom;let c=new P(this._mouse.x,this._mouse.y,0);c.unproject(this.object),this.object.position.sub(c).add(o),this.object.updateMatrixWorld(),a=Gt.length()}else console.warn("WARNING: OrbitControls.js encountered an unknown camera type - zoom to cursor disabled."),this.zoomToCursor=!1;a!==null&&(this.screenSpacePanning?this.target.set(0,0,-1).transformDirection(this.object.matrix).multiplyScalar(a).add(this.object.position):(wh.origin.copy(this.object.position),wh.direction.set(0,0,-1).transformDirection(this.object.matrix),Math.abs(this.object.up.dot(wh.direction))<B1?this.object.lookAt(this.target):(Hy.setFromNormalAndCoplanarPoint(this.object.up,this.target),wh.intersectPlane(Hy,this.target))))}else if(this.object.isOrthographicCamera){let a=this.object.zoom;this.object.zoom=Math.max(this.minZoom,Math.min(this.maxZoom,this.object.zoom/this._scale)),a!==this.object.zoom&&(this.object.updateProjectionMatrix(),s=!0)}return this._scale=1,this._performCursorZoom=!1,s||this._lastPosition.distanceToSquared(this.object.position)>Jf||8*(1-this._lastQuaternion.dot(this.object.quaternion))>Jf||this._lastTargetPosition.distanceToSquared(this.target)>Jf?(this.dispatchEvent(Gy),this._lastPosition.copy(this.object.position),this._lastQuaternion.copy(this.object.quaternion),this._lastTargetPosition.copy(this.target),!0):!1}_getAutoRotationAngle(e){return e!==null?Ti/60*this.autoRotateSpeed*e:Ti/60/60*this.autoRotateSpeed}_getZoomScale(e){let t=Math.abs(e*.01);return Math.pow(.95,this.zoomSpeed*t)}_rotateLeft(e){this._sphericalDelta.theta-=e}_rotateUp(e){this._sphericalDelta.phi-=e}_panLeft(e,t){Gt.setFromMatrixColumn(t,0),Gt.multiplyScalar(-e),this._panOffset.add(Gt)}_panUp(e,t){this.screenSpacePanning===!0?Gt.setFromMatrixColumn(t,1):(Gt.setFromMatrixColumn(t,0),Gt.crossVectors(this.object.up,Gt)),Gt.multiplyScalar(e),this._panOffset.add(Gt)}_pan(e,t){let n=this.domElement;if(this.object.isPerspectiveCamera){let r=this.object.position;Gt.copy(r).sub(this.target);let s=Gt.length();s*=Math.tan(this.object.fov/2*Math.PI/180),this._panLeft(2*e*s/n.clientHeight,this.object.matrix),this._panUp(2*t*s/n.clientHeight,this.object.matrix)}else this.object.isOrthographicCamera?(this._panLeft(e*(this.object.right-this.object.left)/this.object.zoom/n.clientWidth,this.object.matrix),this._panUp(t*(this.object.top-this.object.bottom)/this.object.zoom/n.clientHeight,this.object.matrix)):(console.warn("WARNING: OrbitControls.js encountered an unknown camera type - pan disabled."),this.enablePan=!1)}_dollyOut(e){this.object.isPerspectiveCamera||this.object.isOrthographicCamera?this._scale/=e:(console.warn("WARNING: OrbitControls.js encountered an unknown camera type - dolly/zoom disabled."),this.enableZoom=!1)}_dollyIn(e){this.object.isPerspectiveCamera||this.object.isOrthographicCamera?this._scale*=e:(console.warn("WARNING: OrbitControls.js encountered an unknown camera type - dolly/zoom disabled."),this.enableZoom=!1)}_updateZoomParameters(e,t){if(!this.zoomToCursor)return;this._performCursorZoom=!0;let n=this.domElement.getBoundingClientRect(),r=e-n.left,s=t-n.top,a=n.width,o=n.height;this._mouse.x=r/a*2-1,this._mouse.y=-(s/o)*2+1,this._dollyDirection.set(this._mouse.x,this._mouse.y,1).unproject(this.object).sub(this.object.position).normalize()}_clampDistance(e){return Math.max(this.minDistance,Math.min(this.maxDistance,e))}_handleMouseDownRotate(e){this._rotateStart.set(e.clientX,e.clientY)}_handleMouseDownDolly(e){this._updateZoomParameters(e.clientX,e.clientX),this._dollyStart.set(e.clientX,e.clientY)}_handleMouseDownPan(e){this._panStart.set(e.clientX,e.clientY)}_handleMouseMoveRotate(e){this._rotateEnd.set(e.clientX,e.clientY),this._rotateDelta.subVectors(this._rotateEnd,this._rotateStart).multiplyScalar(this.rotateSpeed);let t=this.domElement;this._rotateLeft(Ti*this._rotateDelta.x/t.clientHeight),this._rotateUp(Ti*this._rotateDelta.y/t.clientHeight),this._rotateStart.copy(this._rotateEnd),this.update()}_handleMouseMoveDolly(e){this._dollyEnd.set(e.clientX,e.clientY),this._dollyDelta.subVectors(this._dollyEnd,this._dollyStart),this._dollyDelta.y>0?this._dollyOut(this._getZoomScale(this._dollyDelta.y)):this._dollyDelta.y<0&&this._dollyIn(this._getZoomScale(this._dollyDelta.y)),this._dollyStart.copy(this._dollyEnd),this.update()}_handleMouseMovePan(e){this._panEnd.set(e.clientX,e.clientY),this._panDelta.subVectors(this._panEnd,this._panStart).multiplyScalar(this.panSpeed),this._pan(this._panDelta.x,this._panDelta.y),this._panStart.copy(this._panEnd),this.update()}_handleMouseWheel(e){this._updateZoomParameters(e.clientX,e.clientY),e.deltaY<0?this._dollyIn(this._getZoomScale(e.deltaY)):e.deltaY>0&&this._dollyOut(this._getZoomScale(e.deltaY)),this.update()}_handleKeyDown(e){let t=!1;switch(e.code){case this.keys.UP:e.ctrlKey||e.metaKey||e.shiftKey?this.enableRotate&&this._rotateUp(Ti*this.keyRotateSpeed/this.domElement.clientHeight):this.enablePan&&this._pan(0,this.keyPanSpeed),t=!0;break;case this.keys.BOTTOM:e.ctrlKey||e.metaKey||e.shiftKey?this.enableRotate&&this._rotateUp(-Ti*this.keyRotateSpeed/this.domElement.clientHeight):this.enablePan&&this._pan(0,-this.keyPanSpeed),t=!0;break;case this.keys.LEFT:e.ctrlKey||e.metaKey||e.shiftKey?this.enableRotate&&this._rotateLeft(Ti*this.keyRotateSpeed/this.domElement.clientHeight):this.enablePan&&this._pan(this.keyPanSpeed,0),t=!0;break;case this.keys.RIGHT:e.ctrlKey||e.metaKey||e.shiftKey?this.enableRotate&&this._rotateLeft(-Ti*this.keyRotateSpeed/this.domElement.clientHeight):this.enablePan&&this._pan(-this.keyPanSpeed,0),t=!0;break}t&&(e.preventDefault(),this.update())}_handleTouchStartRotate(e){if(this._pointers.length===1)this._rotateStart.set(e.pageX,e.pageY);else{let t=this._getSecondPointerPosition(e),n=.5*(e.pageX+t.x),r=.5*(e.pageY+t.y);this._rotateStart.set(n,r)}}_handleTouchStartPan(e){if(this._pointers.length===1)this._panStart.set(e.pageX,e.pageY);else{let t=this._getSecondPointerPosition(e),n=.5*(e.pageX+t.x),r=.5*(e.pageY+t.y);this._panStart.set(n,r)}}_handleTouchStartDolly(e){let t=this._getSecondPointerPosition(e),n=e.pageX-t.x,r=e.pageY-t.y,s=Math.sqrt(n*n+r*r);this._dollyStart.set(0,s)}_handleTouchStartDollyPan(e){this.enableZoom&&this._handleTouchStartDolly(e),this.enablePan&&this._handleTouchStartPan(e)}_handleTouchStartDollyRotate(e){this.enableZoom&&this._handleTouchStartDolly(e),this.enableRotate&&this._handleTouchStartRotate(e)}_handleTouchMoveRotate(e){if(this._pointers.length==1)this._rotateEnd.set(e.pageX,e.pageY);else{let n=this._getSecondPointerPosition(e),r=.5*(e.pageX+n.x),s=.5*(e.pageY+n.y);this._rotateEnd.set(r,s)}this._rotateDelta.subVectors(this._rotateEnd,this._rotateStart).multiplyScalar(this.rotateSpeed);let t=this.domElement;this._rotateLeft(Ti*this._rotateDelta.x/t.clientHeight),this._rotateUp(Ti*this._rotateDelta.y/t.clientHeight),this._rotateStart.copy(this._rotateEnd)}_handleTouchMovePan(e){if(this._pointers.length===1)this._panEnd.set(e.pageX,e.pageY);else{let t=this._getSecondPointerPosition(e),n=.5*(e.pageX+t.x),r=.5*(e.pageY+t.y);this._panEnd.set(n,r)}this._panDelta.subVectors(this._panEnd,this._panStart).multiplyScalar(this.panSpeed),this._pan(this._panDelta.x,this._panDelta.y),this._panStart.copy(this._panEnd)}_handleTouchMoveDolly(e){let t=this._getSecondPointerPosition(e),n=e.pageX-t.x,r=e.pageY-t.y,s=Math.sqrt(n*n+r*r);this._dollyEnd.set(0,s),this._dollyDelta.set(0,Math.pow(this._dollyEnd.y/this._dollyStart.y,this.zoomSpeed)),this._dollyOut(this._dollyDelta.y),this._dollyStart.copy(this._dollyEnd);let a=(e.pageX+t.x)*.5,o=(e.pageY+t.y)*.5;this._updateZoomParameters(a,o)}_handleTouchMoveDollyPan(e){this.enableZoom&&this._handleTouchMoveDolly(e),this.enablePan&&this._handleTouchMovePan(e)}_handleTouchMoveDollyRotate(e){this.enableZoom&&this._handleTouchMoveDolly(e),this.enableRotate&&this._handleTouchMoveRotate(e)}_addPointer(e){this._pointers.push(e.pointerId)}_removePointer(e){delete this._pointerPositions[e.pointerId];for(let t=0;t<this._pointers.length;t++)if(this._pointers[t]==e.pointerId){this._pointers.splice(t,1);return}}_isTrackingPointer(e){for(let t=0;t<this._pointers.length;t++)if(this._pointers[t]==e.pointerId)return!0;return!1}_trackPointer(e){let t=this._pointerPositions[e.pointerId];t===void 0&&(t=new Se,this._pointerPositions[e.pointerId]=t),t.set(e.pageX,e.pageY)}_getSecondPointerPosition(e){let t=e.pointerId===this._pointers[0]?this._pointers[1]:this._pointers[0];return this._pointerPositions[t]}_customWheelEvent(e){let t=e.deltaMode,n={clientX:e.clientX,clientY:e.clientY,deltaY:e.deltaY};switch(t){case 1:n.deltaY*=16;break;case 2:n.deltaY*=100;break}return e.ctrlKey&&!this._controlActive&&(n.deltaY*=10),n}};function k1(i){this.enabled!==!1&&(this._pointers.length===0&&(this.domElement.setPointerCapture(i.pointerId),this.domElement.ownerDocument.addEventListener("pointermove",this._onPointerMove),this.domElement.ownerDocument.addEventListener("pointerup",this._onPointerUp)),!this._isTrackingPointer(i)&&(this._addPointer(i),i.pointerType==="touch"?this._onTouchStart(i):this._onMouseDown(i),this._cursorStyle==="grab"&&(this.domElement.style.cursor="grabbing")))}function z1(i){this.enabled!==!1&&(i.pointerType==="touch"?this._onTouchMove(i):this._onMouseMove(i))}function V1(i){switch(this._removePointer(i),this._pointers.length){case 0:this.domElement.releasePointerCapture(i.pointerId),this.domElement.ownerDocument.removeEventListener("pointermove",this._onPointerMove),this.domElement.ownerDocument.removeEventListener("pointerup",this._onPointerUp),this.dispatchEvent(Wy),this.state=ut.NONE,this._cursorStyle==="grab"&&(this.domElement.style.cursor="grab");break;case 1:let e=this._pointers[0],t=this._pointerPositions[e];this._onTouchStart({pointerId:e,pageX:t.x,pageY:t.y});break}}function G1(i){let e;switch(i.button){case 0:e=this.mouseButtons.LEFT;break;case 1:e=this.mouseButtons.MIDDLE;break;case 2:e=this.mouseButtons.RIGHT;break;default:e=-1}switch(e){case nr.DOLLY:if(this.enableZoom===!1)return;this._handleMouseDownDolly(i),this.state=ut.DOLLY;break;case nr.ROTATE:if(i.ctrlKey||i.metaKey||i.shiftKey){if(this.enablePan===!1)return;this._handleMouseDownPan(i),this.state=ut.PAN}else{if(this.enableRotate===!1)return;this._handleMouseDownRotate(i),this.state=ut.ROTATE}break;case nr.PAN:if(i.ctrlKey||i.metaKey||i.shiftKey){if(this.enableRotate===!1)return;this._handleMouseDownRotate(i),this.state=ut.ROTATE}else{if(this.enablePan===!1)return;this._handleMouseDownPan(i),this.state=ut.PAN}break;default:this.state=ut.NONE}this.state!==ut.NONE&&this.dispatchEvent(Qf)}function H1(i){switch(this.state){case ut.ROTATE:if(this.enableRotate===!1)return;this._handleMouseMoveRotate(i);break;case ut.DOLLY:if(this.enableZoom===!1)return;this._handleMouseMoveDolly(i);break;case ut.PAN:if(this.enablePan===!1)return;this._handleMouseMovePan(i);break}}function W1(i){this.enabled===!1||this.enableZoom===!1||this.state!==ut.NONE||(i.preventDefault(),this.dispatchEvent(Qf),this._handleMouseWheel(this._customWheelEvent(i)),this.dispatchEvent(Wy))}function X1(i){this.enabled!==!1&&this._handleKeyDown(i)}function q1(i){switch(this._trackPointer(i),this._pointers.length){case 1:switch(this.touches.ONE){case rr.ROTATE:if(this.enableRotate===!1)return;this._handleTouchStartRotate(i),this.state=ut.TOUCH_ROTATE;break;case rr.PAN:if(this.enablePan===!1)return;this._handleTouchStartPan(i),this.state=ut.TOUCH_PAN;break;default:this.state=ut.NONE}break;case 2:switch(this.touches.TWO){case rr.DOLLY_PAN:if(this.enableZoom===!1&&this.enablePan===!1)return;this._handleTouchStartDollyPan(i),this.state=ut.TOUCH_DOLLY_PAN;break;case rr.DOLLY_ROTATE:if(this.enableZoom===!1&&this.enableRotate===!1)return;this._handleTouchStartDollyRotate(i),this.state=ut.TOUCH_DOLLY_ROTATE;break;default:this.state=ut.NONE}break;default:this.state=ut.NONE}this.state!==ut.NONE&&this.dispatchEvent(Qf)}function j1(i){switch(this._trackPointer(i),this.state){case ut.TOUCH_ROTATE:if(this.enableRotate===!1)return;this._handleTouchMoveRotate(i),this.update();break;case ut.TOUCH_PAN:if(this.enablePan===!1)return;this._handleTouchMovePan(i),this.update();break;case ut.TOUCH_DOLLY_PAN:if(this.enableZoom===!1&&this.enablePan===!1)return;this._handleTouchMoveDollyPan(i),this.update();break;case ut.TOUCH_DOLLY_ROTATE:if(this.enableZoom===!1&&this.enableRotate===!1)return;this._handleTouchMoveDollyRotate(i),this.update();break;default:this.state=ut.NONE}}function Y1(i){this.enabled!==!1&&i.preventDefault()}function $1(i){i.key==="Control"&&(this._controlActive=!0,this.domElement.getRootNode().addEventListener("keyup",this._interceptControlUp,{passive:!0,capture:!0}))}function Z1(i){i.key==="Control"&&(this._controlActive=!1,this.domElement.getRootNode().removeEventListener("keyup",this._interceptControlUp,{passive:!0,capture:!0}))}function Xy(i,e,t,n){let r=document.createElement("canvas");r.className="v3-canvas";let s=new eo({canvas:r,antialias:e==="full"});s.setPixelRatio(Math.min(devicePixelRatio||1,2)),i.appendChild(r);let a=new xa;a.background=new Ie(t),a.add(new Na(16777215,1.1));let o=new Or(16777215,2);o.position.set(-.6,1,-.4),a.add(o);let l=new Rt(50,1,.5,6e4),c=new Th(l,r);c.maxPolarAngle=Math.PI*.495,c.screenSpacePanning=!1,c.enableDamping=!1;let h=new Set,u=new Set,d=new Set,f=[],p=[],y=0,m=0,g=!1,v=E=>{if(y=0,!g){if(u.size){let x=m?Math.max(0,(E-m)/1e3):0;m=E;for(let A of[...h])A(x)}else m=0;for(let x of[...d])x();s.render(a,l);for(let x of p)x();u.size&&S()}},S=()=>{!y&&!g&&(y=requestAnimationFrame(v))},_=new Se,M=()=>{let E=i.clientWidth||1,x=i.clientHeight||1;s.setSize(E,x,!1),l.aspect=E/x,l.updateProjectionMatrix(),_.set(E,x);for(let A of f)A(_);S()},w=new ResizeObserver(M);return w.observe(i),c.addEventListener("change",S),r.addEventListener("webglcontextlost",E=>{E.preventDefault(),g=!0,y&&cancelAnimationFrame(y),y=0,n()}),M(),{scene:a,camera:l,renderer:s,add(E){a.add(E),S()},remove(E){a.remove(E),S()},look(E,x,A){l.position.copy(E),c.target.copy(x),A&&(c.maxDistance=A,l.far=A*4,l.updateProjectionMatrix()),c.update(),S()},invalidate:S,onFrame(E){return h.add(E),()=>{h.delete(E)}},beforeDraw(E){return d.add(E),()=>{d.delete(E)}},keepDrawing(E,x){x?u.add(E):u.delete(E),S()},onResize(E){f.push(E),E(_)},onDrawn(E){p.push(E)},dispose(){g=!0,y&&cancelAnimationFrame(y),w.disconnect(),c.dispose(),s.dispose(),r.remove()}}}var K1={full:.25,phone:1.5},J1={full:3e5,phone:13e4};function Q1(i){let e=new Map,t=()=>{let n=[...e.values()].sort((r,s)=>r.order-s.order);i.innerHTML=n.map(r=>`<span class="v3-credit">${r.html}</span>`).join(" "),i.classList.toggle("v3-hidden",!n.length)};return t(),{set(n,r,s=0){e.set(n,{html:r,order:s}),t()},remove(n){e.delete(n),t()}}}function eE(i,e,t,n){let r=new ht;r.setAttribute("position",new Ye(i.positions,3)),r.setAttribute("normal",new Ye(i.normals,3)),r.setIndex(new Ye(i.indices,1)),r.computeBoundingSphere();let s=new at(r,t);s.name=`chunk-${i.ci}-${i.cj}`;let{left:a,top:o,res:l}=e.meta,c=i.ci*512,h=i.cj*512,u={x0:a+h*l,x1:a+(h+512+1)*l,y0:o-(c+512+1)*l,y1:o-c*l},d=null;return{ci:i.ci,cj:i.cj,mesh:s,bounds:u,hasLine:i.hasLine,setTexture(f,p){if(d&&(d.dispose(),d=null),!f||!p)s.material=t,r.getAttribute("uv")&&r.deleteAttribute("uv");else{let y=i.grid.length/2,m=new Float32Array(2*y);for(let g=0;g<y;g++){let[v,S]=p(i.grid[2*g],i.grid[2*g+1]);m[2*g]=v,m[2*g+1]=S}r.setAttribute("uv",new st(m,2)),s.material=d=new Yt({map:f,side:ri})}n()}}}function qy(i,e,t){let{left:n,top:r,res:s,width:a,height:o}=i.meta,l=(e-n)/s-.5,c=(r-t)/s-.5;if(!(l>=0&&c>=0&&l<=a-1&&c<=o-1))return null;let h=Math.min(a-2,Math.floor(l)),u=Math.min(o-2,Math.floor(c)),d=l-h,f=c-u,p=(m,g)=>i.heights[m*i.cols+g],y=(p(u,h)*(1-d)+p(u,h+1)*d)*(1-f)+(p(u+1,h)*(1-d)+p(u+1,h+1)*d)*f;return Number.isNaN(y)?null:y}function tE(i,e,t){let[n,r]=e.meta.anchors,s=Math.hypot(r.x-n.x,r.y-n.y)||1,a=(n.x+r.x)/2,o=(n.y+r.y)/2,l=(n.h+r.h)/2,c=-(r.y-n.y)/s,h=(r.x-n.x)/s,u=2*Math.hypot(.85,.45)*Math.tan(i.camera.fov*Math.PI/360)*i.camera.aspect,d=Math.max(60,s*1.25,s*1.15/u),f=_=>qy(e,a+_*c*d*.5,o+_*h*d*.5)??1/0,p=f(1)<=f(-1)?1:-1,y=new P(...Hr(t,a,o,l-s*.05)),m=new P(...Hr(t,a+p*c*d*.85,o+p*h*d*.85,l+d*.45)),{width:g,height:v,res:S}=e.meta;i.look(m,y,Math.max(g,v)*S*1.5)}function jy(i,e,t,n){let r=t.stage.closest(".ui")||document.documentElement,s=getComputedStyle(r),a=y=>s.getPropertyValue(y).trim()||"#888888",o=Xy(t.stage,e,a("--map-bg"),n),l=zg(i.meta),c=Vy(i,l,K1[e],J1[e]),h=new En({color:a("--terrain"),side:ri}),u=c.chunks.map(y=>eE(y,i,h,o.invalidate));for(let y of u)o.scene.add(y.mesh);tE(o,i,l);let d=[],f=!1,p={level:e,patch:i,meta:i.meta,origin:l,chunks:u,view:o,terrain:c,token:a,pickTargets:u.map(y=>y.mesh),credits:Q1(t.credits),toolbar:t.toolbar,invalidate:o.invalidate,onFrame:o.onFrame,beforeDraw:o.beforeDraw,keepDrawing:o.keepDrawing,camera:o.camera,renderer:o.renderer,add(y){o.add(y)},remove(y){o.remove(y)},toScene(y,m,g){return new P(...Hr(l,y,m,g))},fromScene(y){return{x:y.x+l.cx,y:l.cy-y.z,h:y.y+l.h0}},heightAt(y,m){return qy(i,y,m)},lonLat(y,m){return Dc(i.meta.affine,y,m)},onDispose(y){d.push(y)},dispose(){if(!f){f=!0;for(let y of d.splice(0).reverse())try{y()}catch(m){console.error(m)}for(let y of u)y.setTexture(null),y.mesh.geometry.dispose();h.dispose(),o.dispose()}}};return o.invalidate(),p}function yi(i,e,t){let n=document.createElement(i);return n.className=e,t!==void 0&&(n.textContent=t),n}function iE(i,e){document.title=tt("ui.view3d.title");let t=yi("header","v3-top"),n=yi("a","u-btn v3-back",tt("ui.view3d.back"));n.href=p0(e),t.append(n,yi("h1","v3-title",tt("ui.view3d.title")));let r=yi("div","v3-stage"),s=yi("div","v3-status");s.setAttribute("role","status");let a=yi("div","v3-credits v3-hidden");a.setAttribute("aria-label",tt("ui.view3d.credits")),r.append(s,a);let o=yi("div","v3-bar"),l=yi("div","v3-toolbar"),c=yi("div","v3-readout");c.setAttribute("aria-live","polite");let h=yi("p","v3-note",tt("ui.view3d.preview_note"));return o.append(c,l,h),e.level==="phone"&&o.append(yi("p","v3-note",tt("ui.view3d.phone_level"))),i.append(t,r,o),{stage:r,toolbar:l,credits:a,readout:c,say(u,d=!1){if(s.replaceChildren(),s.className="v3-status"+(u===null?" v3-hidden":"")+(d?" v3-error":""),u!==null&&(d?(s.setAttribute("role","alert"),s.append(yi("b","v3-error-title",tt("ui.view3d.error_title")))):s.append(yi("span","v3-spin")),s.append(yi("p","v3-message",u)),d)){let f=yi("button","u-btn",tt("ui.view3d.reload"));f.type="button",f.onclick=()=>location.reload(),s.append(f)}}}}var ea=class extends Error{};async function nE(i){if(!globalThis.crypto?.subtle)return null;let e=await crypto.subtle.digest("SHA-256",i);return[...new Uint8Array(e)].map(t=>t.toString(16).padStart(2,"0")).join("")}async function rE(i){let e;try{e=await fetch(f0(i),{headers:{"X-Findaline-Patch":"1"}})}catch(a){throw new ea(a.message)}if(!e.ok){let a=await e.json().catch(()=>({}));throw new ea(zh(a.detail,e.statusText||String(e.status)))}let{meta:t,body:n}=Ap(await e.arrayBuffer()),r=await nE(n);if(r!==null&&r!==t.sha256)throw new ea(tt("error.patch_damaged"));let s=Rp(await Cp(n),t.width,t.height);return{meta:t,values:s,...Pp(s,t.width,t.height,t.base_dm)}}async function sE(i){let e=await fetch("/api/profile?run="+encodeURIComponent(i.run)+"&line="+encodeURIComponent(i.line||""),{headers:{"X-Findaline-Profile":"1"}}),t=await e.json().catch(()=>({}));if(!e.ok)throw new Error(zh(t.detail,e.statusText||"error"));return t}async function aE(){let i=document.getElementById("view3d");if(!i)return;let e=d0(),t=iE(i,e);if(!e.run||!e.line){t.say(tt("error.patch_line"),!0);return}t.say(tt("ui.view3d.loading_terrain"));let n=null,r=null,s=null,a=()=>t.say(tt("ui.view3d.context_lost"),!0);addEventListener("pagehide",()=>{s?.dispose(),s=null,r?.dispose(),r=null,n?.dispose()}),addEventListener("pageshow",f=>{f.persisted&&location.reload()});let o;try{o=await rE(e)}catch(f){t.say(f instanceof ea?f.message:tt("error.patch_damaged"),!0),console.error(f);return}try{n=jy(o,e.level,t,a)}catch(f){t.say(tt("ui.view3d.no_webgl"),!0),console.error(f);return}let l=u0(n,t.readout);i.dataset.vertices=String(n.terrain.vertices),i.dataset.maxError=String(n.terrain.maxError);let c=!1,h=!1,u=0,d=()=>{c&&h&&(i.dataset.ready="1")};n.view.onDrawn(()=>{if(i.dataset.triangles=String(n.view.renderer.info.render.triangles),i.dataset.frames=String(++u),!c){c=!0,t.say(null),r=e0(n,{runId:e.run,esriKey:Uo()});let f=Fy();f&&(s=By(n,r,f)),d()}}),n.invalidate();try{let f=await sE(e);l?.setProfile(f)}catch(f){l?.setProfile(null),i.dataset.profileError=f.message,console.error(f)}h=!0,d()}aE();})();
