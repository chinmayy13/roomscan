# Fix-loop experiment, kept for reproducibility. Run from the repo root: python scripts/experiments/NAME.py out/scan_A out/scan_B
import sys
import numpy as np
sys.path.insert(0,'.'); sys.path.insert(0,'scripts')
from repeatability import align, load
from roomscan.drift import icp_2d
from scipy.spatial import cKDTree

def faces_of(room, R=np.eye(2), t=np.zeros(2)):
    out=[]
    for w in room['walls']:
        if not w['face_measured']: continue
        p,q=np.array(w['start'])@R.T+t, np.array(w['end'])@R.T+t
        ax=0 if abs(q[0]-p[0])<abs(q[1]-p[1]) else 1
        out.append((ax,(p[ax]+q[ax])/2,sorted([p[1-ax],q[1-ax]]),w['length_m']))
    return out

A,wa=load(sys.argv[1]); B,wb=load(sys.argv[2])
R,t,_=align(wb,wa); wbA=wb@R.T+t
allgaps=[]; rows=[]
for ra in A['rooms']:
    poly=np.array(ra['polygon']); lo,hi=poly.min(0)-0.3,poly.max(0)+0.3
    sa=wa[(wa>lo).all(1)&(wa<hi).all(1)]; sb=wbA[(wbA>lo).all(1)&(wbA<hi).all(1)]
    if len(sa)<200 or len(sb)<200: continue
    # local alignment, translation only (rotation of a single room is tiny; keeps it from sliding)
    Rl,tl,_=icp_2d(sb,cKDTree(sa),sa,iterations=40)
    Rl=np.eye(2)
    # translation-only refinement
    tr=np.zeros(2)
    for _ in range(20):
        d,i=cKDTree(sa).query(sb+tr,distance_upper_bound=0.10); ok=np.isfinite(d)
        if ok.sum()<50: break
        tr+= (sa[i[ok]]-(sb[ok]+tr)).mean(0)
    fa=faces_of(ra)
    fb=[f for rb in B['rooms'] for f in faces_of(rb,R,t+tr)]  # B faces in A frame + local shift
    for ax,pos,(s0,s1),L in fa:
        c=[(abs(pos-p),p) for a2,p,(u0,u1),_ in fb if a2==ax and abs(pos-p)<0.15 and min(s1,u1)-max(s0,u0)>0.3]
        if c: allgaps.append((ra['id'],ax,L,min(c)[0]*100))
g=np.array([x[3] for x in allgaps]); L=np.array([x[2] for x in allgaps])
tol=np.maximum(1.0,0.5*L)   # cm: max(1 cm, 0.5% of length m*100 -> 0.5*L cm)
print('faces matched',len(g),'| median %.1f cm | within 1cm %.0f%% | within gate(1cm or 0.5%%) %.0f%% | within 2cm %.0f%% | within 5cm %.0f%%'%(np.median(g),100*np.mean(g<=1),100*np.mean(g<=tol),100*np.mean(g<=2),100*np.mean(g<=5)))
