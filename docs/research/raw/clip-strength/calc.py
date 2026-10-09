import math
E=1200.0
def arm(t,L,w,d,Q=1.0):
    # root strain (%) and tip force (N); Q = deflection gain of a half-taper arm (Bayer ~1.6)
    eps=3*t*d/(2*Q*L*L)
    F=E*w*t*t*eps/(6*L)
    return 100*eps,F
def push(N,tana,mu):  # both arms on a symmetric ramp
    return 2*N*(tana+mu)/(1-mu*tana)
def pull(N,tana,mu):
    return 2*N*(mu-tana)/(1+mu*tana)
rows=[]
# 0 current
e_h,F_h=arm(2.4,20,16,0.7); e_s,F_s=arm(2.4,20,16,1.4); e_w,_=arm(2.4,20,16,1.6)
print("current: held %.2f%% %.1fN/arm  snap %.2f%% worst %.2f%%  peak %.1fN push(30deg,mu.3) %.0fN"%(e_h,F_h,e_s,e_w,F_s,push(F_s,math.tan(math.radians(30)),0.3)))
# 1 upgraded snap: half-taper, w20, barb 0.5, preload 0.7
for t in (3.2,3.6,4.0):
    e_h,F_h=arm(t,20,20,0.7,1.6); e_s,F_s=arm(t,20,20,1.2,1.6); e_w,_=arm(t,20,20,1.4,1.6)
    print("snap+taper t%.1f w20: held %.2f%% %.1fN  snap %.2f%% worst %.2f%% peak %.1fN push30 %.0fN"%(t,e_h,F_h,e_s,e_w,F_s,push(F_s,math.tan(math.radians(30)),0.3)))
# 2 ramp-ratchet: half-taper, w16, ramp 1:8, final deflection 0.8 nominal (0.6-1.0 by teeth), tooth step 0.2
for t in (4.0,4.4,4.8):
    for d in (0.6,0.8,1.0):
        e_h,F_h=arm(t,20,16,d,1.6); e_o,F_o=arm(t,20,16,d+0.2+0.2,1.6)
        print("ramp t%.1f d%.1f: held %.2f%% %.1fN/arm (%.2f N/mm @25)  over %.2f%%  push(1:8 lead 1:6) mu.3 %.0fN mu.4 %.0fN  pull mu.3 %.0fN mu.15 %.0fN"%(t,d,e_h,F_h,F_h/25,e_o,push(F_h,1/6,0.3),push(F_h,1/6,0.4),pull(F_h,1/8,0.3),pull(F_h,1/8,0.15)))
# 3 expansion +0.25 on ramp clip t4.4 d0.8
e,F=arm(4.4,20,16,1.05,1.6); print("ramp t4.4 +0.25 expansion: %.2f%% %.1fN"%(e,F))
# 4 axial taper rail 1:20, 60 mm, 1.0 N/mm per arm
N=60; print("rail 60mm 1N/mm/arm: push mu.3 %.0fN  pull %.0fN"%(push(N,0.05,0.3),pull(N,0.05,0.3)))
