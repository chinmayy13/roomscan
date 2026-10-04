# Fix-loop experiment, kept for reproducibility. Run from the repo root: python scripts/experiments/NAME.py out/scan_A out/scan_B
import sys
import numpy as np, cv2
sys.path.insert(0,'.'); sys.path.insert(0,'scripts')
from repeatability import align, load
A,wa=load(sys.argv[1]); B,wb=load(sys.argv[2]); R,t,_=align(wb,wa); swap=abs(R[0,0])<0.5

def bounded(room):
    """per axis: True only if the outermost faces on BOTH ends of the room were snapped to real wall points"""
    res={}
    for ax in (0,1):
        E=[]
        for w in room['walls']:
            p,q=np.array(w['start']),np.array(w['end'])
            a=0 if abs(q[0]-p[0])<abs(q[1]-p[1]) else 1
            if a==ax: E.append(((p[ax]+q[ax])/2, w['face_measured'], abs(q[1-ax]-p[1-ax])))
        if not E: res[ax]=False; continue
        lo=min(E,key=lambda e:e[0]); hi=max(E,key=lambda e:e[0])
        res[ax]=bool(lo[1] and hi[1])
    return res
def raster(poly,o,shape,res=0.05):
    img=np.zeros(shape,np.uint8); cv2.fillPoly(img,[((np.array(poly)-o)/res).astype(np.int32)],1); return img
for r in B['rooms']: r['pA']=(np.array(r['polygon'])@R.T+t).tolist()
allp=np.vstack([r['polygon'] for r in A['rooms']]+[r['pA'] for r in B['rooms']]); o=allp.min(0)-1
shape=tuple((np.ptp(allp,0)/0.05+40).astype(int)[::-1])
rows=[]
for ra in A['rooms']:
    ma=raster(ra['polygon'],o,shape); best=None;bi=0
    for rb in B['rooms']:
        iou=(ma&raster(rb['pA'],o,shape)).sum()/max((ma|raster(rb['pA'],o,shape)).sum(),1)
        if iou>bi: best,bi=rb,iou
    if best is None or bi<0.5: continue
    ba,bb=bounded(ra),bounded(best)
    for ax in (0,1):
        bax=(1-ax) if swap else ax
        xa=np.ptp(np.array(ra['polygon'])[:,ax]); xb=np.ptp(np.array(best['polygon'])[:,bax])
        both=ba[ax] and bb[bax]
        rows.append((ra['id'],best['id'],'xy'[ax],xa,xb,abs(xa-xb)*100,both))
print('%-4s %-4s %-3s %7s %7s %8s  both sides wall-bounded in A and B'%('A','B','ax','A m','B m','|d| cm'))
for r in rows: print('%-4s %-4s %-3s %7.2f %7.2f %8.1f  %s'%(*r[:6],'YES' if r[6] else 'no'))
for name,sel in (('all',rows),('wall-bounded in both',[r for r in rows if r[6]]),('NOT bounded',[r for r in rows if not r[6]])):
    if sel:
        d=np.array([r[5] for r in sel]); print('%-22s n=%2d median %5.1f cm  max %5.1f'%(name,len(d),np.median(d),d.max()))
