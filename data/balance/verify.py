import csv, numpy as np, sys
sys.path.insert(0,".")
from dose_detect import DoseDetector

D=1.088
t=[];m=[];st=[]
for r in csv.DictReader(open("Paper_1.csv")):
    t.append(float(r["elapsed_s"])); m.append(float(r["mass"])); st.append(r["stable"]=="True")
t=np.array(t); m=np.array(m)
print("rows",len(t),"span_s",t[-1],"span_h",t[-1]/3600)
print("mass g: min",m.min(),"max",m.max(),"-> mg max",m.max()*1e3)

# replicate script dose detection
det=DoseDetector(density=D); dose_t=[]; dose_ul=[]
for ti,mi,si in zip(t,m,st):
    ev=det.push(ti,mi,si)
    if ev and ev[0]=="dose" and 5 < ev[2]*1e3 < 40:
        dose_t.append(ti); dose_ul.append(ev[2]*1e3/D)
dose_t=np.array(dose_t); dose_ul=np.array(dose_ul)
print("\nRAW detected doses (before cut):",len(dose_t))
if len(dose_t)>1:
    d=np.diff(dose_t)
    brk=np.where(d>600)[0]
    print("gaps>600s at idx",brk, "gap values", d[brk] if len(brk) else None)
    if len(brk):
        dose_t=dose_t[:brk[0]+1]; dose_ul=dose_ul[:brk[0]+1]
T_END=dose_t[-1]+300.0
print("\nAFTER CUT:")
print("n_doses",len(dose_t))
print("T_END_s",T_END,"T_END_h",T_END/3600)
print("last dose t_s",dose_t[-1],"h",dose_t[-1]/3600)
print("mean_uL",np.mean(dose_ul))
print("total_mL",np.sum(dose_ul)/1000.0)
print("min/max dose uL",dose_ul.min(),dose_ul.max())
print("cadence median s",np.median(np.diff(dose_t)))
# check axis containment
mr=m[t<=T_END]*1e3
print("\nAXIS CHECK: raw mg max in-window",mr.max(),"(top ylim 1600)")
print("dose uL max",dose_ul.max(),"(bottom ylim 20)")
print("cumulative mL",np.sum(dose_ul)/1000.0,"(cum ylim 1.6)")
