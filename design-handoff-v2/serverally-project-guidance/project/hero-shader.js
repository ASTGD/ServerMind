/* hero-shader.js — layered WebGL hero background for Axion Studio.
   Recreates the spec'd shader stack: Swirl (#fff/#f0f0f0, detail 1.7),
   ChromaFlow (orange #ff5f03 flowing from edges + pointer momentum),
   FlutedGlass (angle 31, frequency 8, refraction 4, aberration 0.61,
   highlight 0.12, speed 0.15) and FilmGrain (0.05).
   Registers <hero-shader glow="#ff5f03" motion="1" grain="1">. */
(function () {
  'use strict';
  if (window.customElements && customElements.get('hero-shader')) return;

  var VERT = 'attribute vec2 aP;void main(){gl_Position=vec4(aP,0.0,1.0);}';

  var FRAG = [
    'precision highp float;',
    'uniform vec2 uRes;',
    'uniform float uTime;',
    'uniform vec2 uPtr;',
    'uniform float uVel;',
    'uniform vec3 uGlow;',
    'uniform float uMotion;',
    'uniform float uGrain;',
    '',
    'float hash(vec2 q){return fract(sin(dot(q,vec2(127.1,311.7)))*43758.5453123);}',
    '',
    'float vnoise(vec2 q){',
    '  vec2 i=floor(q); vec2 f=fract(q);',
    '  f=f*f*(3.0-2.0*f);',
    '  float a=hash(i);',
    '  float b=hash(i+vec2(1.0,0.0));',
    '  float c=hash(i+vec2(0.0,1.0));',
    '  float d=hash(i+vec2(1.0,1.0));',
    '  return mix(mix(a,b,f.x),mix(c,d,f.x),f.y);',
    '}',
    '',
    'float fbm(vec2 q){',
    '  float v=0.0; float a=0.5;',
    '  for(int i=0;i<4;i++){ v+=a*vnoise(q); q=q*2.03+vec2(19.7,7.3); a*=0.5; }',
    '  return v;',
    '}',
    '',
    '/* Swirl base + orange chroma flow */',
    'vec3 scene(vec2 uv){',
    '  float t=uTime*uMotion;',
    '  float aspX=uRes.x/uRes.y;',
    '  vec2 p=(uv-0.5)*vec2(aspX,1.0);',
    '',
    '  float r=length(p);',
    '  float twist=1.7*exp(-r*0.9)*(1.1+0.4*sin(t*0.07));',
    '  float cA=cos(twist); float sA=sin(twist);',
    '  vec2 sp=mat2(cA,-sA,sA,cA)*p;',
    '  float sw=fbm(sp*2.3+vec2(t*0.03,-t*0.022));',
    '  vec3 col=mix(vec3(1.0),vec3(0.9412),smoothstep(0.34,0.78,sw));',
    '',
    '  float edgeD=min(min(uv.x,1.0-uv.x)*aspX,min(uv.y,1.0-uv.y));',
    '  float edge=1.0-smoothstep(0.0,0.55,edgeD);',
    '  float warp=fbm(p*2.1-vec2(t*0.02,t*0.016));',
    '  float fl=fbm(p*1.25+vec2(warp*1.15)+vec2(t*0.045,-t*0.03));',
    '  float field=smoothstep(0.44,0.92,fl)*edge;',
    '',
    '  vec2 pd=(uv-uPtr)*vec2(aspX,1.0);',
    '  float d2=dot(pd,pd);',
    '  float glow=exp(-d2*5.5)*(0.16+min(uVel*10.0,0.85));',
    '  float halo=clamp(field*0.55+exp(-d2*2.0)*(0.05+min(uVel*4.0,0.30)),0.0,1.0);',
    '  float amt=clamp(field*0.9+glow,0.0,1.0);',
    '',
    '  col=mix(col,mix(col,uGlow,0.4),halo);',
    '  col=mix(col,uGlow,amt);',
    '  return col;',
    '}',
    '',
    'void main(){',
    '  vec2 uv=gl_FragCoord.xy/uRes;',
    '  float aspX=uRes.x/uRes.y;',
    '  vec2 asp=vec2(aspX,1.0);',
    '',
    '  /* Fluted glass: rotate 31deg, 8 flutes, rounded profile */',
    '  float ang=radians(31.0);',
    '  float cA=cos(ang); float sA=sin(ang);',
    '  mat2 Rf=mat2(cA,-sA,sA,cA);',
    '  mat2 Rb=mat2(cA,sA,-sA,cA);',
    '',
    '  vec2 q=Rf*((uv-0.5)*asp);',
    '  float freq=8.0;',
    '  float xr=q.x*freq+uTime*uMotion*0.0375;',
    '  float y=(fract(xr)-0.5)*2.0;',
    '  float prof=sqrt(max(1.0-y*y,0.0));',
    '  float dx=-y*mix(0.35,1.0,prof)*(4.0*0.22/freq);',
    '',
    '  /* chromatic aberration 0.61 */',
    '  vec2 oR=(Rb*vec2(dx*1.11,0.0))/asp;',
    '  vec2 oG=(Rb*vec2(dx,0.0))/asp;',
    '  vec2 oB=(Rb*vec2(dx*0.89,0.0))/asp;',
    '  vec3 col=vec3(scene(uv+oR).r,scene(uv+oG).g,scene(uv+oB).b);',
    '',
    '  /* crisp highlight streak per flute (lightAngle -90, strength 0.12) */',
    '  float lit=-y;',
    '  float hl=smoothstep(0.78,0.86,lit)*(1.0-smoothstep(0.93,1.0,lit));',
    '  col+=hl*0.12;',
    '  col*=1.0-smoothstep(0.982,1.0,abs(y))*0.07;',
    '',
    '  /* film grain 0.05, animated */',
    '  float g=hash(gl_FragCoord.xy+vec2(fract(uTime*7.13)*191.0,fract(uTime*3.77)*127.0));',
    '  col+=(g-0.5)*0.05*uGrain;',
    '',
    '  gl_FragColor=vec4(clamp(col,0.0,1.0),1.0);',
    '}'
  ].join('\n');

  function hexToRgb(s) {
    s = String(s || '').trim();
    if (s.charAt(0) === '#') s = s.slice(1);
    if (s.length === 3) {
      s = s.charAt(0) + s.charAt(0) + s.charAt(1) + s.charAt(1) + s.charAt(2) + s.charAt(2);
    }
    var n = parseInt(s, 16);
    if (s.length !== 6 || isNaN(n)) return [1.0, 0.3725, 0.0118];
    return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
  }

  class HeroShader extends HTMLElement {
    static get observedAttributes() { return ['glow', 'motion', 'grain']; }

    connectedCallback() {
      if (this._running) return;
      this._running = true;
      if (!this.style.display) this.style.display = 'block';
      if (!this.style.width) this.style.width = '100%';
      if (!this.style.height) this.style.height = '100%';

      var c = this._canvas = document.createElement('canvas');
      c.style.cssText = 'width:100%;height:100%;display:block;';
      this.appendChild(c);

      var gl = this._gl = c.getContext('webgl', { antialias: false, alpha: false, depth: false, stencil: false });
      if (!gl) return;

      var vs = gl.createShader(gl.VERTEX_SHADER);
      gl.shaderSource(vs, VERT);
      gl.compileShader(vs);
      var fs = gl.createShader(gl.FRAGMENT_SHADER);
      gl.shaderSource(fs, FRAG);
      gl.compileShader(fs);
      if (!gl.getShaderParameter(fs, gl.COMPILE_STATUS)) {
        console.error('hero-shader fragment compile failed: ' + gl.getShaderInfoLog(fs));
        return;
      }
      var pr = this._pr = gl.createProgram();
      gl.attachShader(pr, vs);
      gl.attachShader(pr, fs);
      gl.linkProgram(pr);
      if (!gl.getProgramParameter(pr, gl.LINK_STATUS)) {
        console.error('hero-shader link failed: ' + gl.getProgramInfoLog(pr));
        return;
      }
      gl.useProgram(pr);

      var buf = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, buf);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
      var loc = gl.getAttribLocation(pr, 'aP');
      gl.enableVertexAttribArray(loc);
      gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);

      this._u = {
        res: gl.getUniformLocation(pr, 'uRes'),
        time: gl.getUniformLocation(pr, 'uTime'),
        ptr: gl.getUniformLocation(pr, 'uPtr'),
        vel: gl.getUniformLocation(pr, 'uVel'),
        glow: gl.getUniformLocation(pr, 'uGlow'),
        motion: gl.getUniformLocation(pr, 'uMotion'),
        grain: gl.getUniformLocation(pr, 'uGrain')
      };

      this._ptr = [0.5, 0.55];
      this._ptrT = [0.5, 0.55];
      this._vel = 0;
      var self = this;
      this._onMove = function (e) {
        var r = self.getBoundingClientRect();
        if (r.width < 2 || r.height < 2) return;
        self._ptrT[0] = (e.clientX - r.left) / r.width;
        self._ptrT[1] = 1 - (e.clientY - r.top) / r.height;
      };
      window.addEventListener('pointermove', this._onMove, { passive: true });

      this._ro = new ResizeObserver(function () { self._resize(); });
      this._ro.observe(this);
      this._resize();

      this._t0 = performance.now();
      var loop = function () {
        self._raf = requestAnimationFrame(loop);
        if (!document.hidden && self._running) self._draw();
      };
      loop();
    }

    disconnectedCallback() {
      this._running = false;
      if (this._raf) cancelAnimationFrame(this._raf);
      if (this._ro) this._ro.disconnect();
      if (this._onMove) window.removeEventListener('pointermove', this._onMove);
      if (this._canvas && this._canvas.parentNode === this) this.removeChild(this._canvas);
      this._gl = null;
    }

    _resize() {
      var gl = this._gl;
      if (!gl) return;
      var w = Math.max(this.clientWidth, 2);
      var h = Math.max(this.clientHeight, 2);
      var dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      var scale = Math.min(1, Math.sqrt(1800000 / (w * dpr * h * dpr)));
      var cw = Math.max(2, Math.round(w * dpr * scale));
      var ch = Math.max(2, Math.round(h * dpr * scale));
      if (this._canvas.width !== cw || this._canvas.height !== ch) {
        this._canvas.width = cw;
        this._canvas.height = ch;
        gl.viewport(0, 0, cw, ch);
      }
    }

    _draw() {
      var gl = this._gl;
      if (!gl || gl.isContextLost()) return;
      /* momentum: sluggish pointer follow + velocity-driven glow */
      var dxp = this._ptrT[0] - this._ptr[0];
      var dyp = this._ptrT[1] - this._ptr[1];
      this._ptr[0] += dxp * 0.06;
      this._ptr[1] += dyp * 0.06;
      var sp = Math.sqrt(dxp * dxp + dyp * dyp);
      this._vel += (sp - this._vel) * 0.08;

      var u = this._u;
      gl.uniform2f(u.res, this._canvas.width, this._canvas.height);
      gl.uniform1f(u.time, (performance.now() - this._t0) / 1000);
      gl.uniform2f(u.ptr, this._ptr[0], this._ptr[1]);
      gl.uniform1f(u.vel, this._vel);
      var rgb = hexToRgb(this.getAttribute('glow') || '#ff5f03');
      gl.uniform3f(u.glow, rgb[0], rgb[1], rgb[2]);
      var m = parseFloat(this.getAttribute('motion'));
      if (isNaN(m)) m = 1;
      gl.uniform1f(u.motion, m);
      var gr = parseFloat(this.getAttribute('grain'));
      if (isNaN(gr)) gr = 1;
      gl.uniform1f(u.grain, gr);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    }
  }

  customElements.define('hero-shader', HeroShader);
})();
