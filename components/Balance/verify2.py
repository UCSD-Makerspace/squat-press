import csv, numpy as np
D=1.088
t=[];m=[]
for r in csv.DictReader(open("Paper_1.csv")):
    t.append(float(r["elapsed_s"])); m.append(float(r["mass"]))
t=np.array(t); m=np.array(m)
T_END=29004.922
# net mass gain within session as independent cross-check of total volume
i0=np.searchsorted(t,0); 
mstart=np.median(m[(t<60)])
mend=np.median(m[(t>T_END-120)&(t<=T_END)])
print("median mass first 60s (g):",mstart)
print("median mass last 2min of session (g):",mend)
gain_g=mend-mstart
print("net gain g:",gain_g,"-> mL:",gain_g/D)
# end bump magnitude
mend_file=np.median(m[t>t[-1]-120])
print("median mass last 2min of FILE (g):",mend_file,"-> mg",mend_file*1e3, "(exceeds 1600 ylim, must be cut)")
# playback ratio
print("ratio T_END/22 =",T_END/22, "round=",round(T_END/22))
print("N_FRAMES=",22*30,"video_len=",22*30/30,"s")
