# Fix-loop experiment, kept for reproducibility. Run from the repo root: python scripts/experiments/NAME.py out/scan_A out/scan_B
import sys, json
import numpy as np, cv2
sys.path.insert(0,'.'); sys.path.insert(0,'scripts')
from repeatability import align, load

def typical_dims(poly, res=0.02):
    P=np.array(poly); o=P.min(0)-0.1
    size=((P.max(0)-o)/res).astype(int)+6
    m=np.zeros((size[1],size[0]),np.uint8)
    cv2.fillPoly(m,[((P-o)/res).astype(np.int32)],1)
    def runs(mat):
        out=[]
        for row in mat:
            idx=np.nonzero(row)[0]
            if len(idx): out.append((idx.max()-idx.min()+1)*res)   # extent of that row
        return np.array(out)
    rx=runs(m); ry=runs(m.T)
    return float(np.median(rx)), float(np.median(ry)), float(np.ptp(P[:,0])), float(np.ptp(P[:,1]))

A,wa=load(sys.argv[1]); B,wb=load(sys.argv[2]); R,t,_=align(wb,wa)
swap=abs(R[0,0])<0.5
def raster(poly,o,shape,res=0.05):
    img=np.zeros(shape,np.uint8); cv2.fillPoly(img,[((np.array(poly)-o)/res).astype(np.int32)],1); return img
for r in B['rooms']: r['pA']=(np.array(r['polygon'])@R.T+t).tolist()
allp=np.vstack([r['polygon'] for r in A['rooms']]+[r['pA'] for r in B['rooms']]); o=allp.min(0)-1
shape=tuple((np.ptp(allp,0)/0.05+40).astype(int)[::-1])
d_typ=[];d_ext=[];ok=0
print('%-4s %-4s %9s %9s | %9s %9s'%('A','B','typ A','typ B','ext A','ext B'))
for ra in A['rooms']:
    ma=raster(ra['polygon'],o,shape); best=None;bi=0
    for rb in B['rooms']:
        mb=raster(rb['pA'],o,shape); iou=(ma&mb).sum()/max((ma|mb).sum(),1)
        if iou>bi: best,bi=rb,iou
    if best is None or bi<0.5: continue
    ta=typical_dims(ra['polygon']); tb=typical_dims(best['polygon'])
    if swap: tb=(tb[1],tb[0],tb[3],tb[2])
    for k in (0,1):
        d_typ.append(abs(ta[k]-tb[k])); d_ext.append(abs(ta[2+k]-tb[2+k]))
        tol=max(0.01,0.005*max(ta[k],tb[k])); ok+= abs(ta[k]-tb[k])<=tol
    print('%-4s %-4s %4.2fx%4.2f %4.2fx%4.2f | %4.2fx%4.2f %4.2fx%4.2f'%(ra['id'],best['id'],ta[0],ta[1],tb[0],tb[1],ta[2],ta[3],tb[2],tb[3]))
d_typ=np.array(d_typ)*100; d_ext=np.array(d_ext)*100
print('typical: median %.1f cm  max %.1f  pass %d/%d'%(np.median(d_typ),d_typ.max(),ok,len(d_typ)))
print('extent (current polygons, bbox): median %.1f cm max %.1f'%(np.median(d_ext),d_ext.max()))
