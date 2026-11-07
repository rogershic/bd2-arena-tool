# -*- coding: utf-8 -*-
"""复核执行体（从 bd2tool.do_verify 抽出来，exe 才能调）"""
import io
import os
import sys

import _data

import sys as _bd2sys
HERE = (os.environ.get('BD2_HOME') or
        (os.path.dirname(os.path.abspath(_bd2sys.executable))
         if getattr(_bd2sys, 'frozen', False)
         else os.path.dirname(os.path.abspath(__file__))))
CFG = sys.argv[1]
LO = int(sys.argv[2])
HI = int(sys.argv[3])
NREP = int(sys.argv[4])


def main():
    import io,os,sys,json,copy,pickle,random
    os.environ['USE_POT_MAX']='0'; os.environ['ENEMY_ALWAYS_CRIT']='1'; os.environ['CRIT_RANDOM']='1'
    sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    sys.path.insert(0,HERE)
    import _sim3 as S
    S.bless_points([])
    try:
        BOX=json.load(io.open(os.path.join(HERE,'my_box.json'),encoding='utf-8'))
    except Exception:
        BOX={}   # 没个人数据也能复核
    BURST={}
    for k,v in BOX.items():
        if k=='_說明' or '·' not in k: continue
        ch,co=k.split('·',1); BURST[(ch,co)]=max(BURST.get((ch,co),0),v.get('burst') or 0)
    # ★★★ 2026-11-07 关键修正: 没有 my_box 时上面会得到空 BURST → 我方全部按爆0算
    #   → 复核出来的胜率离谱地低（实测同一套阵容：复核 19% / 测试阵容 92%）
    #   跟 _s49fast / bs4 / bs5 保持一致：该服饰【有爆发】就按爆3
    try:
        import _zh as _zhx
        for _c in json.load(io.open(_data.p('chars_db.json'), encoding='utf-8')):
            for _x in (_c.get('costumes') or []):
                if _x.get('burst'):
                    BURST[(_c.get('character'), _x.get('costumeName'))] = 3
                    try:
                        BURST[(_zhx.t2s(_c.get('character')), _zhx.t2s(_x.get('costumeName')))] = 3
                    except Exception:
                        pass
    except Exception:
        pass
    POOL,_=pickle.load(io.open(os.path.join(HERE,'_opp_cache.pkl'),'rb'))
    C=json.load(io.open(os.path.join(HERE,CFG),encoding='utf-8'))
    def en(u):
        X=S.clone_team(u)
        for x in X:
            q=x.get('pos')
            if not isinstance(q,int):
                try: q=int(q)
                except Exception: q=0
            x['pos']=q if q>=0 else 0
        return X
    t=[]
    for i,(ch,co,pos) in enumerate(C['team']):
        u=S.unit_stats(ch,co,i+1,pos,5,BURST.get((ch,co),0)); u['pos']=pos; u['order']=i+1; t.append(u)
    g=[y for y in POOL if LO<=(y[3] or 0)<=HI]
    N=NREP
    a=b=0
    for _i,y in enumerate(g):
        for r in range(N):
            random.seed(1000+r+_i*17); a+= S.battle(S.clone_team(t),en(y[0]),True,list(C['bf']),y[2])[0]=='A'
            random.seed(2000+r+_i*17); b+= S.battle(S.clone_team(t),en(y[0]),False,list(C['bs']),y[1])[0]=='A'
    n=len(g)*N
    print()
    print('  %s套 N=%d  先 %.1f%%  后 %.1f%%  综合 %.1f%%' % (len(g),N,100.0*a/n,100.0*b/n,50.0*(a+b)/n))
    print('__SCORES__ %.4f %.4f' % (100.0*a/n, 100.0*b/n))

if __name__ == '__main__':
    main()
